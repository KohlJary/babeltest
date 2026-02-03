#!/usr/bin/env node
/**
 * BabelTest JavaScript Runner
 *
 * Reads test specs from stdin, executes them, and outputs results as JSON.
 *
 * Usage: node runner.mjs < test_spec.json
 *
 * Input format (one JSON object per line):
 * {"action": "run", "test": {...}, "config": {...}}
 * {"action": "exit"}
 *
 * Output format (one JSON object per line):
 * {"status": "passed|failed|error", "message": "...", "actual": ..., "duration_ms": ...}
 */

import { createRequire } from 'module';
import { pathToFileURL } from 'url';
import { createInterface } from 'readline';
import path from 'path';
import fs from 'fs';

// For CommonJS support
const require = createRequire(import.meta.url);

// Configuration
let config = {
  projectRoot: process.cwd(),
  factoriesPath: 'babel/factories',
  moduleType: 'auto',  // 'esm', 'cjs', or 'auto'
  debug: false,
};

// Instance cache for shared lifecycle
const instanceCache = new Map();
const factoryCache = new Map();

// Mock storage for cleanup
const installedMocks = [];

/**
 * Log debug message if debug mode is enabled.
 */
function debug(...args) {
  if (config.debug) {
    console.error('[DEBUG]', ...args);
  }
}

/**
 * Import a module by path, handling both ESM and CommonJS.
 */
async function importModule(modulePath) {
  const absolutePath = path.isAbsolute(modulePath)
    ? modulePath
    : path.resolve(config.projectRoot, modulePath);

  // Check if file exists
  const extensions = ['', '.js', '.mjs', '.cjs', '/index.js', '/index.mjs'];
  let resolvedPath = null;

  for (const ext of extensions) {
    const tryPath = absolutePath + ext;
    if (fs.existsSync(tryPath) && fs.statSync(tryPath).isFile()) {
      resolvedPath = tryPath;
      break;
    }
  }

  if (!resolvedPath) {
    // Try as a node module
    try {
      return require(modulePath);
    } catch (e) {
      throw new Error(`Module not found: ${modulePath}`);
    }
  }

  const moduleType = config.moduleType === 'auto'
    ? (resolvedPath.endsWith('.mjs') ? 'esm' :
       resolvedPath.endsWith('.cjs') ? 'cjs' :
       detectModuleType(resolvedPath))
    : config.moduleType;

  if (moduleType === 'esm') {
    return await import(pathToFileURL(resolvedPath).href);
  } else {
    return require(resolvedPath);
  }
}

/**
 * Detect if a file is ESM or CommonJS.
 */
function detectModuleType(filePath) {
  // Check package.json for type: module
  let dir = path.dirname(filePath);
  while (dir !== path.dirname(dir)) {
    const pkgPath = path.join(dir, 'package.json');
    if (fs.existsSync(pkgPath)) {
      try {
        const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
        return pkg.type === 'module' ? 'esm' : 'cjs';
      } catch {
        break;
      }
    }
    dir = path.dirname(dir);
  }
  return 'cjs';
}

/**
 * Convert a target path to module path and parts.
 *
 * Examples:
 *   "myapp/services/UserService.getById" -> ["myapp/services/UserService", "getById"]
 *   "utils.math.add" -> ["utils/math", "add"] (for module-level functions)
 */
function parseTarget(target) {
  // Support both dot and slash notation
  const normalized = target.replace(/\./g, '/');
  const lastSlash = normalized.lastIndexOf('/');

  if (lastSlash === -1) {
    throw new Error(`Invalid target format: ${target}. Use 'module.function' or 'module/Class.method'`);
  }

  const modulePath = normalized.substring(0, lastSlash);
  const memberPath = target.substring(lastSlash + 1).split('.');

  return { modulePath, memberPath };
}

/**
 * Convert CamelCase to camelCase (for factory function names).
 */
function toCamelCase(name) {
  return name.charAt(0).toLowerCase() + name.slice(1);
}

/**
 * Convert snake_case to camelCase.
 */
function snakeToCamel(name) {
  return name.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
}

/**
 * Get all naming variants for a method name.
 * Tries the original name, then snake_case -> camelCase conversion.
 */
function getNameVariants(name) {
  const variants = [name];

  // If it looks like snake_case, add camelCase variant
  if (name.includes('_')) {
    variants.push(snakeToCamel(name));
  }

  return variants;
}

/**
 * Try to find a factory function for a class.
 */
async function tryFactory(className, modulePath) {
  const factoryFuncName = toCamelCase(className);
  const moduleBase = modulePath.split('/').pop();

  // Search paths for factories
  const searchPaths = [
    // Flat: babel/factories/services.js
    path.join(config.factoriesPath, `${moduleBase}.js`),
    path.join(config.factoriesPath, `${moduleBase}.mjs`),
    // Class-named: babel/factories/userService.js
    path.join(config.factoriesPath, `${factoryFuncName}.js`),
    path.join(config.factoriesPath, `${factoryFuncName}.mjs`),
  ];

  for (const factoryPath of searchPaths) {
    const fullPath = path.resolve(config.projectRoot, factoryPath);
    debug(`Looking for factory at: ${fullPath}`);

    if (!fs.existsSync(fullPath)) {
      continue;
    }

    try {
      let factoryModule = factoryCache.get(fullPath);
      if (!factoryModule) {
        factoryModule = await importModule(fullPath);
        factoryCache.set(fullPath, factoryModule);
      }

      const factory = factoryModule[factoryFuncName] || factoryModule.default?.[factoryFuncName];
      if (typeof factory === 'function') {
        debug(`Found factory: ${factoryPath}::${factoryFuncName}()`);
        return await factory();
      }
    } catch (e) {
      debug(`Failed to load factory ${factoryPath}: ${e.message}`);
    }
  }

  return null;
}

/**
 * Get or create an instance of a class.
 */
async function getInstance(cls, className, modulePath) {
  const cacheKey = `${modulePath}.${className}`;

  // Check cache
  if (instanceCache.has(cacheKey)) {
    return instanceCache.get(cacheKey);
  }

  // Try factory
  const instance = await tryFactory(className, modulePath);
  if (instance) {
    instanceCache.set(cacheKey, instance);
    return instance;
  }

  // Try zero-arg constructor
  try {
    const newInstance = new cls();
    instanceCache.set(cacheKey, newInstance);
    return newInstance;
  } catch (e) {
    throw new Error(
      `Cannot construct ${className}: ${e.message}. ` +
      `Create a factory function in ${config.factoriesPath}/${modulePath.split('/').pop()}.js`
    );
  }
}

/**
 * Resolve a target to a callable function.
 *
 * Tries progressively shorter module paths until one works.
 * E.g., for "example.services.UserService.getById":
 *   1. Try import "example/js/services/UserService" (fails)
 *   2. Try import "example/js/services", get UserService.getById (works)
 */
async function resolve(target) {
  // Split target into parts (dots become path separators)
  let parts = target.split('.');

  // Map "example." prefix to "example/js/" for unified test files
  if (parts[0] === 'example') {
    parts = ['example', 'js', ...parts.slice(1)];
  }

  if (parts.length < 2) {
    throw new Error(`Invalid target format: ${target}. Use 'module.function' or 'module.Class.method'`);
  }

  // Try progressively shorter module paths
  for (let i = parts.length - 1; i >= 1; i--) {
    const modulePath = parts.slice(0, i).join('/');
    const memberPath = parts.slice(i);

    debug(`Trying: module=${modulePath}, members=${memberPath.join('.')}`);

    let module;
    try {
      module = await importModule(modulePath);
    } catch (e) {
      debug(`  Failed to import: ${e.message}`);
      continue;
    }

    // Try to navigate to the target
    try {
      let obj = module;
      for (let j = 0; j < memberPath.length - 1; j++) {
        const part = memberPath[j];
        const next = obj[part] || obj.default?.[part];

        if (next === undefined) {
          throw new Error(`'${part}' not found`);
        }

        // If it's a class (starts with uppercase), instantiate it
        if (typeof next === 'function' && /^[A-Z]/.test(part)) {
          obj = await getInstance(next, part, modulePath);
        } else {
          obj = next;
        }
      }

      const methodName = memberPath[memberPath.length - 1];

      // Try different naming conventions (snake_case -> camelCase)
      for (const nameVariant of getNameVariants(methodName)) {
        const method = obj[nameVariant] || obj.default?.[nameVariant];

        if (typeof method === 'function') {
          debug(`  Resolved: ${modulePath} -> ${memberPath.slice(0, -1).join('.')}.${nameVariant}`);
          return { obj, method, methodName: nameVariant };
        }
      }

      throw new Error(`'${methodName}' is not a function`);

    } catch (e) {
      debug(`  Navigation failed: ${e.message}`);
      continue;
    }
  }

  throw new Error(`Cannot resolve ${target}: module not found or member not accessible`);
}

/**
 * Install a mock for a target.
 *
 * @param {Object} mockSpec - The mock specification
 * @returns {Object} - Cleanup info for restoring the original
 */
async function installMock(mockSpec) {
  debug(`Installing mock for: ${mockSpec.target}`);

  // Parse the mock target to find the class/module and method
  let parts = mockSpec.target.split('.');

  // Map "example." prefix to "example/js/" for unified test files
  if (parts[0] === 'example') {
    parts = ['example', 'js', ...parts.slice(1)];
  }

  // Try to find the class/module and method
  for (let i = parts.length - 1; i >= 1; i--) {
    const modulePath = parts.slice(0, i).join('/');
    const memberPath = parts.slice(i);

    debug(`  Mock trying: module=${modulePath}, members=${memberPath.join('.')}`);

    let module;
    try {
      module = await importModule(modulePath);
    } catch (e) {
      continue;
    }

    // If there's a class name, mock on the prototype
    if (memberPath.length === 2) {
      const className = memberPath[0];
      const methodName = memberPath[1];

      const cls = module[className] || module.default?.[className];
      if (typeof cls === 'function' && cls.prototype) {
        // Try both the original method name and camelCase variant
        for (const nameVariant of getNameVariants(methodName)) {
          if (typeof cls.prototype[nameVariant] === 'function') {
            const original = cls.prototype[nameVariant];

            // Pre-resolve the error class if needed
            let ErrorClass = null;
            if (mockSpec.throws) {
              ErrorClass = await findErrorClass(mockSpec.throws.type, mockSpec.target);
            }

            // Create mock function
            const mockFn = function(...args) {
              if (mockSpec.throws) {
                throw new ErrorClass(mockSpec.throws.message || '');
              }
              return mockSpec.returns;
            };

            // Install on prototype (affects all instances)
            cls.prototype[nameVariant] = mockFn;

            // Store cleanup info
            const cleanup = { obj: cls.prototype, methodName: nameVariant, original };
            installedMocks.push(cleanup);

            debug(`  Mock installed on prototype: ${className}.prototype.${nameVariant} -> ${mockSpec.throws ? 'throws' : 'returns'}`);
            return cleanup;
          }
        }
      }
    }

    // Fall back to module-level function
    if (memberPath.length === 1) {
      const methodName = memberPath[0];

      for (const nameVariant of getNameVariants(methodName)) {
        const method = module[nameVariant] || module.default?.[nameVariant];
        if (typeof method === 'function') {
          const obj = module.default || module;
          const original = obj[nameVariant];

          // Pre-resolve the error class if needed
          let ErrorClass = null;
          if (mockSpec.throws) {
            ErrorClass = await findErrorClass(mockSpec.throws.type, mockSpec.target);
          }

          // Create mock function
          const mockFn = function(...args) {
            if (mockSpec.throws) {
              throw new ErrorClass(mockSpec.throws.message || '');
            }
            return mockSpec.returns;
          };

          obj[nameVariant] = mockFn;

          const cleanup = { obj, methodName: nameVariant, original };
          installedMocks.push(cleanup);

          debug(`  Mock installed: ${nameVariant} -> ${mockSpec.throws ? 'throws' : 'returns'}`);
          return cleanup;
        }
      }
    }
  }

  throw new Error(`Cannot resolve mock target: ${mockSpec.target}`);
}

/**
 * Cache for resolved error classes from modules.
 */
const errorClassCache = new Map();

/**
 * Find an error class by name.
 * Searches in the module that's being mocked, then falls back to global errors.
 */
async function findErrorClass(name, mockTarget) {
  if (!name) return Error;

  // Check global error types first
  const globalErrors = {
    Error, TypeError, RangeError, ReferenceError, SyntaxError, URIError,
  };

  if (globalErrors[name]) return globalErrors[name];

  // Try to find the error class in the mock target's module
  if (mockTarget) {
    let parts = mockTarget.split('.');

    // Map "example." prefix to "example/js/"
    if (parts[0] === 'example') {
      parts = ['example', 'js', ...parts.slice(1)];
    }

    // Try progressively shorter module paths
    for (let i = parts.length - 1; i >= 1; i--) {
      const modulePath = parts.slice(0, i).join('/');

      // Check cache
      const cacheKey = `${modulePath}:${name}`;
      if (errorClassCache.has(cacheKey)) {
        const cached = errorClassCache.get(cacheKey);
        if (cached) return cached;
        continue;  // Cache says it's not in this module
      }

      try {
        const module = await importModule(modulePath);
        const ErrorClass = module[name] || module.default?.[name];

        if (typeof ErrorClass === 'function' && ErrorClass.prototype instanceof Error) {
          errorClassCache.set(cacheKey, ErrorClass);
          debug(`  Found error class ${name} in ${modulePath}`);
          return ErrorClass;
        }

        // Mark as not found in cache to avoid re-checking
        errorClassCache.set(cacheKey, null);
      } catch (e) {
        errorClassCache.set(cacheKey, null);
      }
    }
  }

  // Return generic Error but set the name property
  class CustomError extends Error {
    constructor(message) {
      super(message);
      this.name = name;
    }
  }
  return CustomError;
}

/**
 * Clean up all installed mocks.
 */
function cleanupMocks() {
  while (installedMocks.length > 0) {
    const { obj, methodName, original } = installedMocks.pop();
    obj[methodName] = original;
    debug(`  Mock cleaned up: ${methodName}`);
  }
}

/**
 * Run a single test.
 */
async function runTest(test) {
  const startTime = performance.now();

  // Install mocks before running the test
  try {
    if (test.mocks && test.mocks.length > 0) {
      for (const mockSpec of test.mocks) {
        await installMock(mockSpec);
      }
    }
  } catch (error) {
    cleanupMocks();
    return {
      status: 'error',
      message: `Failed to install mock: ${error.message}`,
      duration_ms: performance.now() - startTime,
    };
  }

  try {
    const { obj, method } = await resolve(test.target);

    // Call the method with params
    const params = test.given || {};
    let result;

    // Support both object params and positional params
    if (Array.isArray(params)) {
      result = await method.apply(obj, params);
    } else if (typeof params === 'object' && Object.keys(params).length > 0) {
      // Try to call with object destructuring or as single object param
      // Most JS functions expect positional args, so we pass the object
      const paramValues = Object.values(params);
      result = await method.apply(obj, paramValues);
    } else {
      result = await method.call(obj);
    }

    const duration = performance.now() - startTime;

    // If we expected a throw but didn't get one
    if (test.throws) {
      cleanupMocks();
      return {
        status: 'failed',
        message: `Expected exception ${test.throws.type || 'any'} but call succeeded`,
        actual: result,
        duration_ms: duration,
      };
    }

    // Check expectation
    if (test.expect) {
      cleanupMocks();
      const { passed, message } = checkExpectation(result, test.expect);
      return {
        status: passed ? 'passed' : 'failed',
        message,
        actual: result,
        expected: test.expect.value,
        duration_ms: duration,
      };
    }

    // No assertion - just check it didn't throw
    cleanupMocks();
    return {
      status: 'passed',
      actual: result,
      duration_ms: duration,
    };

  } catch (error) {
    cleanupMocks();
    const duration = performance.now() - startTime;

    // If we expected a throw, check it matches
    if (test.throws) {
      const { passed, message } = checkThrows(error, test.throws);
      return {
        status: passed ? 'passed' : 'failed',
        message,
        error: { type: error.constructor.name, message: error.message },
        duration_ms: duration,
      };
    }

    // Unexpected error
    return {
      status: 'error',
      message: `${error.constructor.name}: ${error.message}`,
      error: { type: error.constructor.name, message: error.message, stack: error.stack },
      duration_ms: duration,
    };
  }
}

/**
 * Check if result matches expectation.
 */
function checkExpectation(actual, expect) {
  switch (expect.type) {
    case 'exact':
      if (deepEqual(actual, expect.value)) {
        return { passed: true };
      }
      return { passed: false, message: `Expected ${JSON.stringify(expect.value)}, got ${JSON.stringify(actual)}` };

    case 'contains':
      return checkContains(actual, expect.value, '');

    case 'type':
      const typeName = actual?.constructor?.name || typeof actual;
      if (typeName === expect.value) {
        return { passed: true };
      }
      return { passed: false, message: `Expected type ${expect.value}, got ${typeName}` };

    case 'null':
      if (actual === null || actual === undefined) {
        return { passed: true };
      }
      return { passed: false, message: `Expected null, got ${JSON.stringify(actual)}` };

    case 'not_null':
      if (actual !== null && actual !== undefined) {
        return { passed: true };
      }
      return { passed: false, message: 'Expected non-null value, got null' };

    case 'true':
      if (actual === true) {
        return { passed: true };
      }
      return { passed: false, message: `Expected true, got ${JSON.stringify(actual)}` };

    case 'false':
      if (actual === false) {
        return { passed: true };
      }
      return { passed: false, message: `Expected false, got ${JSON.stringify(actual)}` };

    default:
      return { passed: false, message: `Unknown expectation type: ${expect.type}` };
  }
}

/**
 * Check if actual contains expected (recursive partial match).
 */
function checkContains(actual, expected, path) {
  const formatPath = (p) => p ? ` at '${p}'` : '';

  if (expected === null || expected === undefined) {
    if (actual === null || actual === undefined) {
      return { passed: true };
    }
    return { passed: false, message: `Expected null${formatPath(path)}, got ${JSON.stringify(actual)}` };
  }

  if (typeof expected === 'object' && !Array.isArray(expected)) {
    if (typeof actual !== 'object' || actual === null) {
      return { passed: false, message: `Expected object${formatPath(path)}, got ${typeof actual}` };
    }

    for (const [key, expectedVal] of Object.entries(expected)) {
      const keyPath = path ? `${path}.${key}` : key;

      if (!(key in actual)) {
        return { passed: false, message: `Missing key '${key}'${formatPath(path)}` };
      }

      const result = checkContains(actual[key], expectedVal, keyPath);
      if (!result.passed) {
        return result;
      }
    }

    return { passed: true };
  }

  if (Array.isArray(expected)) {
    if (!Array.isArray(actual)) {
      return { passed: false, message: `Expected array${formatPath(path)}, got ${typeof actual}` };
    }

    for (let i = 0; i < expected.length; i++) {
      const found = actual.some(item => checkContains(item, expected[i], '').passed);
      if (!found) {
        return { passed: false, message: `Expected item ${JSON.stringify(expected[i])} not found in array${formatPath(path)}` };
      }
    }

    return { passed: true };
  }

  // Primitive comparison
  if (actual !== expected) {
    return { passed: false, message: `Expected ${JSON.stringify(expected)}${formatPath(path)}, got ${JSON.stringify(actual)}` };
  }

  return { passed: true };
}

/**
 * Check if error matches throws expectation.
 */
function checkThrows(error, throws) {
  if (throws.type && error.constructor.name !== throws.type) {
    return { passed: false, message: `Expected ${throws.type}, got ${error.constructor.name}` };
  }

  if (throws.message && !error.message.includes(throws.message)) {
    return { passed: false, message: `Expected message containing '${throws.message}', got '${error.message}'` };
  }

  return { passed: true };
}

/**
 * Deep equality check.
 */
function deepEqual(a, b) {
  if (a === b) return true;
  if (a === null || b === null) return false;
  if (typeof a !== typeof b) return false;

  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) return false;
    return a.every((val, i) => deepEqual(val, b[i]));
  }

  if (typeof a === 'object') {
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    return keysA.every(key => deepEqual(a[key], b[key]));
  }

  return false;
}

/**
 * Handle lifecycle events.
 */
function handleLifecycle(action, data) {
  switch (action) {
    case 'suite_start':
      // Could clear cache for per_suite lifecycle
      break;
    case 'suite_end':
      break;
    case 'test_start':
      // Could clear cache for per_test lifecycle
      break;
    case 'test_end':
      break;
    case 'clear_cache':
      instanceCache.clear();
      break;
  }
  return { status: 'ok' };
}

/**
 * Main entry point - read from stdin and process commands.
 */
async function main() {
  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false,
  });

  for await (const line of rl) {
    if (!line.trim()) continue;

    try {
      const command = JSON.parse(line);

      // Update config if provided
      if (command.config) {
        Object.assign(config, command.config);
        debug('Config updated:', config);
      }

      let result;

      switch (command.action) {
        case 'run':
          result = await runTest(command.test);
          break;

        case 'lifecycle':
          result = handleLifecycle(command.lifecycle, command.data);
          break;

        case 'exit':
          console.log(JSON.stringify({ status: 'ok', action: 'exit' }));
          process.exit(0);
          break;

        default:
          result = { status: 'error', message: `Unknown action: ${command.action}` };
      }

      console.log(JSON.stringify(result));

    } catch (error) {
      console.log(JSON.stringify({
        status: 'error',
        message: `Runner error: ${error.message}`,
        stack: error.stack,
      }));
    }
  }
}

main().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
