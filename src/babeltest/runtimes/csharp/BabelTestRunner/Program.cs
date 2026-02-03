using System.Reflection;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace BabelTestRunner;

/// <summary>
/// BabelTest C# Runner - reads test specs from stdin, executes them, outputs results as JSON.
/// </summary>
public class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false
    };

    private static Config _config = new();
    private static readonly Dictionary<string, object> InstanceCache = new();
    private static readonly Dictionary<string, Assembly> AssemblyCache = new();
    private static bool _debug;

    public static async Task Main(string[] args)
    {
        // Read commands from stdin
        string? line;
        while ((line = Console.ReadLine()) != null)
        {
            if (string.IsNullOrWhiteSpace(line)) continue;

            try
            {
                var command = JsonSerializer.Deserialize<Command>(line, JsonOptions);
                if (command == null)
                {
                    WriteResult(new TestResult { Status = "error", Message = "Invalid command" });
                    continue;
                }

                // Update config if provided
                if (command.Config != null)
                {
                    _config = command.Config;
                    _debug = _config.Debug;
                    Debug($"Config updated: ProjectPath={_config.ProjectPath}");
                }

                switch (command.Action)
                {
                    case "run":
                        var result = await RunTest(command.Test!);
                        WriteResult(result);
                        break;

                    case "lifecycle":
                        HandleLifecycle(command.Lifecycle!, command.Data);
                        WriteResult(new TestResult { Status = "ok" });
                        break;

                    case "exit":
                        WriteResult(new TestResult { Status = "ok", Message = "exit" });
                        return;

                    default:
                        WriteResult(new TestResult { Status = "error", Message = $"Unknown action: {command.Action}" });
                        break;
                }
            }
            catch (Exception ex)
            {
                WriteResult(new TestResult
                {
                    Status = "error",
                    Message = $"Runner error: {ex.Message}",
                    Error = new ErrorInfo { Type = ex.GetType().Name, Message = ex.Message, Stack = ex.StackTrace }
                });
            }
        }
    }

    private static void WriteResult(TestResult result)
    {
        Console.WriteLine(JsonSerializer.Serialize(result, JsonOptions));
    }

    private static void Debug(string message)
    {
        if (_debug)
        {
            Console.Error.WriteLine($"[DEBUG] {message}");
        }
    }

    private static async Task<TestResult> RunTest(TestSpec test)
    {
        var startTime = DateTime.UtcNow;

        try
        {
            var (obj, method) = await Resolve(test.Target);

            // Build parameters
            var parameters = BuildParameters(method, test.Given);

            // Invoke the method
            object? result;
            if (method.ReturnType.IsAssignableTo(typeof(Task)))
            {
                // Async method
                var task = (Task)method.Invoke(obj, parameters)!;
                await task;

                // Get result if Task<T>
                if (method.ReturnType.IsGenericType)
                {
                    var resultProperty = method.ReturnType.GetProperty("Result");
                    result = resultProperty?.GetValue(task);
                }
                else
                {
                    result = null;
                }
            }
            else
            {
                result = method.Invoke(obj, parameters);
            }

            var duration = (DateTime.UtcNow - startTime).TotalMilliseconds;

            // If we expected an exception but didn't get one
            if (test.Throws != null)
            {
                return new TestResult
                {
                    Status = "failed",
                    Message = $"Expected exception {test.Throws.Type ?? "any"} but call succeeded",
                    Actual = result,
                    DurationMs = duration
                };
            }

            // Check expectation
            if (test.Expect != null)
            {
                var (passed, message) = CheckExpectation(result, test.Expect);
                return new TestResult
                {
                    Status = passed ? "passed" : "failed",
                    Message = message,
                    Actual = result,
                    Expected = test.Expect.Value,
                    DurationMs = duration
                };
            }

            return new TestResult
            {
                Status = "passed",
                Actual = result,
                DurationMs = duration
            };
        }
        catch (TargetInvocationException ex) when (ex.InnerException != null)
        {
            return HandleException(ex.InnerException, test, startTime);
        }
        catch (Exception ex)
        {
            return HandleException(ex, test, startTime);
        }
    }

    private static TestResult HandleException(Exception ex, TestSpec test, DateTime startTime)
    {
        var duration = (DateTime.UtcNow - startTime).TotalMilliseconds;

        if (test.Throws != null)
        {
            var (passed, message) = CheckThrows(ex, test.Throws);
            return new TestResult
            {
                Status = passed ? "passed" : "failed",
                Message = message,
                Error = new ErrorInfo { Type = ex.GetType().Name, Message = ex.Message },
                DurationMs = duration
            };
        }

        return new TestResult
        {
            Status = "error",
            Message = $"{ex.GetType().Name}: {ex.Message}",
            Error = new ErrorInfo { Type = ex.GetType().Name, Message = ex.Message, Stack = ex.StackTrace },
            DurationMs = duration
        };
    }

    private static async Task<(object? obj, MethodInfo method)> Resolve(string target)
    {
        var parts = target.Split('.');
        if (parts.Length < 2)
        {
            throw new Exception($"Invalid target format: {target}");
        }

        // Try progressively shorter type paths
        for (int i = parts.Length - 1; i >= 1; i--)
        {
            var typePath = string.Join(".", parts.Take(i));
            var memberPath = parts.Skip(i).ToArray();

            Debug($"Trying: type={typePath}, members={string.Join(".", memberPath)}");

            var type = FindType(typePath);
            if (type == null)
            {
                Debug($"  Type not found: {typePath}");
                continue;
            }

            try
            {
                object? obj = null;

                // Navigate to the target
                for (int j = 0; j < memberPath.Length - 1; j++)
                {
                    var memberName = memberPath[j];

                    if (obj == null)
                    {
                        // First member - might be a nested type or static member
                        var nestedType = type.GetNestedType(memberName);
                        if (nestedType != null)
                        {
                            type = nestedType;
                            continue;
                        }

                        // If it looks like a class name, instantiate it
                        if (char.IsUpper(memberName[0]))
                        {
                            var memberType = FindType($"{typePath}.{memberName}") ?? type.GetNestedType(memberName);
                            if (memberType != null)
                            {
                                obj = await GetInstance(memberType);
                                type = memberType;
                                continue;
                            }
                        }
                    }

                    // Try to get property or field
                    var prop = type.GetProperty(memberName);
                    if (prop != null)
                    {
                        obj = prop.GetValue(obj);
                        type = prop.PropertyType;
                        continue;
                    }

                    var field = type.GetField(memberName);
                    if (field != null)
                    {
                        obj = field.GetValue(obj);
                        type = field.FieldType;
                        continue;
                    }

                    throw new Exception($"'{memberName}' not found on {type.Name}");
                }

                // Get the method
                var methodName = memberPath.Last();
                var method = type.GetMethod(methodName, BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static);

                if (method == null)
                {
                    throw new Exception($"Method '{methodName}' not found on {type.Name}");
                }

                // If instance method and no instance, create one
                if (!method.IsStatic && obj == null)
                {
                    obj = await GetInstance(type);
                }

                Debug($"  Resolved: {type.FullName}.{methodName}");
                return (obj, method);
            }
            catch (Exception ex)
            {
                Debug($"  Resolution failed: {ex.Message}");
                continue;
            }
        }

        throw new Exception($"Cannot resolve target: {target}");
    }

    private static Type? FindType(string typePath)
    {
        // Search in loaded assemblies first
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            var type = asm.GetType(typePath);
            if (type != null) return type;
        }

        // Try to load from project
        if (!string.IsNullOrEmpty(_config.ProjectPath))
        {
            var projectDir = Path.GetDirectoryName(_config.ProjectPath) ?? ".";
            var binDir = Path.Combine(projectDir, "bin", "Debug", "net8.0");

            if (Directory.Exists(binDir))
            {
                foreach (var dllPath in Directory.GetFiles(binDir, "*.dll"))
                {
                    try
                    {
                        if (!AssemblyCache.TryGetValue(dllPath, out var asm))
                        {
                            asm = Assembly.LoadFrom(dllPath);
                            AssemblyCache[dllPath] = asm;
                        }

                        var type = asm.GetType(typePath);
                        if (type != null) return type;
                    }
                    catch
                    {
                        // Skip assemblies that can't be loaded
                    }
                }
            }
        }

        return null;
    }

    private static async Task<object> GetInstance(Type type)
    {
        var cacheKey = type.FullName ?? type.Name;

        if (InstanceCache.TryGetValue(cacheKey, out var cached))
        {
            return cached;
        }

        // Try factory first
        var instance = await TryFactory(type);
        if (instance != null)
        {
            InstanceCache[cacheKey] = instance;
            return instance;
        }

        // Try parameterless constructor
        var ctor = type.GetConstructor(Type.EmptyTypes);
        if (ctor != null)
        {
            instance = ctor.Invoke(null);
            InstanceCache[cacheKey] = instance;
            return instance;
        }

        throw new Exception($"Cannot construct {type.Name}: no parameterless constructor and no factory found");
    }

    private static async Task<object?> TryFactory(Type type)
    {
        var factoryMethodName = char.ToLower(type.Name[0]) + type.Name.Substring(1);

        // Look for factory in babel/factories directory
        if (!string.IsNullOrEmpty(_config.FactoriesPath))
        {
            var factoriesDir = Path.IsPathRooted(_config.FactoriesPath)
                ? _config.FactoriesPath
                : Path.Combine(_config.ProjectRoot ?? ".", _config.FactoriesPath);

            Debug($"Looking for factories in: {factoriesDir}");

            // For now, factories need to be compiled into the project
            // Look for a static factory method in any loaded type
        }

        // Look for [BabelFactory] attribute or naming convention in loaded assemblies
        foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
        {
            foreach (var factoryType in asm.GetTypes())
            {
                if (!factoryType.Name.EndsWith("Factory") && !factoryType.Name.EndsWith("Factories"))
                    continue;

                var method = factoryType.GetMethod(factoryMethodName, BindingFlags.Public | BindingFlags.Static);
                if (method != null && method.ReturnType.IsAssignableTo(type))
                {
                    Debug($"Found factory: {factoryType.Name}.{factoryMethodName}()");

                    if (method.ReturnType.IsAssignableTo(typeof(Task)))
                    {
                        var task = (Task)method.Invoke(null, null)!;
                        await task;
                        var resultProp = task.GetType().GetProperty("Result");
                        return resultProp?.GetValue(task);
                    }

                    return method.Invoke(null, null);
                }
            }
        }

        return null;
    }

    private static object?[] BuildParameters(MethodInfo method, Dictionary<string, JsonElement>? given)
    {
        var methodParams = method.GetParameters();
        var args = new object?[methodParams.Length];

        if (given == null || given.Count == 0)
        {
            return args;
        }

        for (int i = 0; i < methodParams.Length; i++)
        {
            var param = methodParams[i];
            var paramName = param.Name ?? $"arg{i}";

            // Try exact name match first, then case-insensitive
            if (!given.TryGetValue(paramName, out var value))
            {
                var key = given.Keys.FirstOrDefault(k =>
                    string.Equals(k, paramName, StringComparison.OrdinalIgnoreCase));
                if (key != null)
                {
                    value = given[key];
                }
            }

            if (value.ValueKind != JsonValueKind.Undefined)
            {
                args[i] = ConvertValue(value, param.ParameterType);
            }
            else if (param.HasDefaultValue)
            {
                args[i] = param.DefaultValue;
            }
        }

        return args;
    }

    private static object? ConvertValue(JsonElement element, Type targetType)
    {
        return element.ValueKind switch
        {
            JsonValueKind.Null => null,
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Number when targetType == typeof(int) => element.GetInt32(),
            JsonValueKind.Number when targetType == typeof(long) => element.GetInt64(),
            JsonValueKind.Number when targetType == typeof(float) => element.GetSingle(),
            JsonValueKind.Number when targetType == typeof(double) => element.GetDouble(),
            JsonValueKind.Number when targetType == typeof(decimal) => element.GetDecimal(),
            JsonValueKind.Number => element.GetDouble(),
            JsonValueKind.String when targetType == typeof(string) => element.GetString(),
            JsonValueKind.String when targetType == typeof(Guid) => Guid.Parse(element.GetString()!),
            JsonValueKind.String when targetType == typeof(DateTime) => DateTime.Parse(element.GetString()!),
            JsonValueKind.String => element.GetString(),
            _ => JsonSerializer.Deserialize(element.GetRawText(), targetType, JsonOptions)
        };
    }

    private static (bool passed, string? message) CheckExpectation(object? actual, Expectation expect)
    {
        return expect.Type switch
        {
            "exact" => CheckExact(actual, expect.Value),
            "contains" => CheckContains(actual, expect.Value, ""),
            "type" => CheckType(actual, expect.Value),
            "null" => actual == null ? (true, null) : (false, $"Expected null, got {FormatValue(actual)}"),
            "not_null" => actual != null ? (true, null) : (false, "Expected non-null value, got null"),
            "true" => actual is true ? (true, null) : (false, $"Expected true, got {FormatValue(actual)}"),
            "false" => actual is false ? (true, null) : (false, $"Expected false, got {FormatValue(actual)}"),
            _ => (false, $"Unknown expectation type: {expect.Type}")
        };
    }

    private static (bool passed, string? message) CheckExact(object? actual, JsonElement? expected)
    {
        if (expected == null) return actual == null ? (true, null) : (false, $"Expected null, got {FormatValue(actual)}");

        var expectedObj = JsonSerializer.Deserialize<object>(expected.Value.GetRawText(), JsonOptions);
        if (Equals(actual, expectedObj) || JsonEquals(actual, expected.Value))
        {
            return (true, null);
        }

        return (false, $"Expected {expected}, got {FormatValue(actual)}");
    }

    private static (bool passed, string? message) CheckContains(object? actual, JsonElement? expected, string path)
    {
        if (expected == null || expected.Value.ValueKind == JsonValueKind.Null)
        {
            return actual == null ? (true, null) : (false, $"Expected null at '{path}', got {FormatValue(actual)}");
        }

        if (expected.Value.ValueKind == JsonValueKind.Object)
        {
            if (actual == null)
            {
                return (false, $"Expected object at '{path}', got null");
            }

            var actualDict = ObjectToDictionary(actual);
            if (actualDict == null)
            {
                return (false, $"Expected object at '{path}', got {actual.GetType().Name}");
            }

            foreach (var prop in expected.Value.EnumerateObject())
            {
                var keyPath = string.IsNullOrEmpty(path) ? prop.Name : $"{path}.{prop.Name}";

                if (!actualDict.TryGetValue(prop.Name, out var actualValue))
                {
                    // Try case-insensitive match
                    var key = actualDict.Keys.FirstOrDefault(k =>
                        string.Equals(k, prop.Name, StringComparison.OrdinalIgnoreCase));
                    if (key == null)
                    {
                        return (false, $"Missing key '{prop.Name}' at '{path}'");
                    }
                    actualValue = actualDict[key];
                }

                var (passed, message) = CheckContains(actualValue, prop.Value, keyPath);
                if (!passed) return (false, message);
            }

            return (true, null);
        }

        if (expected.Value.ValueKind == JsonValueKind.Array)
        {
            if (actual is not System.Collections.IEnumerable actualEnum)
            {
                return (false, $"Expected array at '{path}', got {actual?.GetType().Name ?? "null"}");
            }

            var actualList = actualEnum.Cast<object?>().ToList();
            int i = 0;
            foreach (var expectedItem in expected.Value.EnumerateArray())
            {
                bool found = false;
                foreach (var actualItem in actualList)
                {
                    var (passed, _) = CheckContains(actualItem, expectedItem, "");
                    if (passed)
                    {
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    return (false, $"Expected item {expectedItem} not found in array at '{path}'");
                }
                i++;
            }

            return (true, null);
        }

        // Primitive comparison
        var expectedValue = JsonElementToObject(expected.Value);
        if (!Equals(actual, expectedValue))
        {
            return (false, $"Expected {FormatValue(expectedValue)} at '{path}', got {FormatValue(actual)}");
        }

        return (true, null);
    }

    private static (bool passed, string? message) CheckType(object? actual, JsonElement? expected)
    {
        if (expected == null) return (false, "Expected type name not provided");

        var expectedTypeName = expected.Value.GetString();
        var actualTypeName = actual?.GetType().Name ?? "null";

        if (actualTypeName == expectedTypeName)
        {
            return (true, null);
        }

        return (false, $"Expected type {expectedTypeName}, got {actualTypeName}");
    }

    private static (bool passed, string? message) CheckThrows(Exception ex, ThrowsExpectation throws)
    {
        if (throws.Type != null && ex.GetType().Name != throws.Type)
        {
            return (false, $"Expected {throws.Type}, got {ex.GetType().Name}");
        }

        if (throws.Message != null && !ex.Message.Contains(throws.Message))
        {
            return (false, $"Expected message containing '{throws.Message}', got '{ex.Message}'");
        }

        return (true, null);
    }

    private static void HandleLifecycle(string lifecycle, Dictionary<string, object>? data)
    {
        switch (lifecycle)
        {
            case "clear_cache":
                InstanceCache.Clear();
                break;
        }
    }

    private static bool JsonEquals(object? actual, JsonElement expected)
    {
        var actualJson = JsonSerializer.Serialize(actual, JsonOptions);
        var expectedJson = expected.GetRawText();
        return actualJson == expectedJson;
    }

    private static Dictionary<string, object?>? ObjectToDictionary(object obj)
    {
        if (obj is Dictionary<string, object?> dict) return dict;
        if (obj is System.Collections.IDictionary idict)
        {
            return idict.Keys.Cast<object>().ToDictionary(k => k.ToString()!, k => idict[k]);
        }

        var result = new Dictionary<string, object?>();
        foreach (var prop in obj.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
        {
            result[prop.Name] = prop.GetValue(obj);
        }
        return result;
    }

    private static object? JsonElementToObject(JsonElement element)
    {
        return element.ValueKind switch
        {
            JsonValueKind.Null => null,
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Number when element.TryGetInt32(out var i) => i,
            JsonValueKind.Number when element.TryGetInt64(out var l) => l,
            JsonValueKind.Number => element.GetDouble(),
            JsonValueKind.String => element.GetString(),
            _ => element.GetRawText()
        };
    }

    private static string FormatValue(object? value)
    {
        if (value == null) return "null";
        if (value is string s) return $"\"{s}\"";
        return JsonSerializer.Serialize(value, JsonOptions);
    }
}

// DTOs for JSON communication

public class Command
{
    public string Action { get; set; } = "";
    public TestSpec? Test { get; set; }
    public Config? Config { get; set; }
    public string? Lifecycle { get; set; }
    public Dictionary<string, object>? Data { get; set; }
}

public class Config
{
    public string? ProjectRoot { get; set; }
    public string? ProjectPath { get; set; }
    public string? FactoriesPath { get; set; }
    public bool Debug { get; set; }
}

public class TestSpec
{
    public string Target { get; set; } = "";
    public string? Description { get; set; }
    public Dictionary<string, JsonElement>? Given { get; set; }
    public Expectation? Expect { get; set; }
    public ThrowsExpectation? Throws { get; set; }
    public int? TimeoutMs { get; set; }
}

public class Expectation
{
    public string Type { get; set; } = "exact";
    public JsonElement? Value { get; set; }
}

public class ThrowsExpectation
{
    public string? Type { get; set; }
    public string? Message { get; set; }
    public string? Code { get; set; }
}

public class TestResult
{
    public string Status { get; set; } = "error";
    public string? Message { get; set; }
    public object? Actual { get; set; }
    public object? Expected { get; set; }
    public ErrorInfo? Error { get; set; }
    public double DurationMs { get; set; }
}

public class ErrorInfo
{
    public string? Type { get; set; }
    public string? Message { get; set; }
    public string? Stack { get; set; }
}
