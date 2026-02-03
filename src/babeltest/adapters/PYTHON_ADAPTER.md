# Python Adapter Implementation Notes

This document covers Python-specific implementation details for the BabelTest Python adapter.

## Architecture

```
PythonAdapter
├── resolve(target)      # Import modules, navigate to method
├── invoke(target, params)
├── _get_instance()      # Factory discovery + caching
├── _try_factory()       # Search babel/factories/
├── _try_zero_arg()      # Fallback to parameterless constructor
└── Lifecycle hooks      # on_suite_start, on_test_start, etc.
```

## Module Resolution

The adapter uses `importlib` to dynamically import modules:

```python
# Target: "myapp.services.UserService.get_by_id"
#          ^^^^^^^^^^^^^^ ^^^^^^^^^^^ ^^^^^^^^^
#          module path    class       method

# Resolution strategy:
# 1. Try importing "myapp.services.UserService" (fails - not a module)
# 2. Try importing "myapp.services" (success)
# 3. Get UserService from module
# 4. Construct instance (via factory or zero-arg)
# 5. Return (instance, "get_by_id")
```

### sys.path Management

The adapter adds paths to `sys.path` for module discovery:

1. Project root (always)
2. Config `source_paths` (user-specified)

```python
# babeltest.yaml
adapters:
  python:
    source_paths:
      - "./src"
      - "./lib"
```

## Factory Discovery

### Search Order

For target `myapp.services.UserService`:

1. **Nested**: `babel/factories/myapp/services.py::user_service()`
2. **Flat**: `babel/factories/services.py::user_service()`
3. **Class-named**: `babel/factories/user_service.py::user_service()`
4. **Zero-arg**: `UserService()` (no constructor params)

### Factory Function Convention

```python
# babel/factories/services.py

from myapp.services import UserService
from myapp.mocks import MockDatabase, NullLogger

def user_service() -> UserService:
    """Factory for UserService with test dependencies."""
    return UserService(
        db=MockDatabase(),
        logger=NullLogger(),
    )
```

- Function name: `snake_case` version of class name
- Returns: Fully constructed instance
- Location: `babel/factories/{module}.py`

### Factory Module Loading

Factories are loaded dynamically using `importlib.util`:

```python
spec = importlib.util.spec_from_file_location(
    f"babeltest_factory_{factory_file.stem}_{id(factory_file)}",
    factory_file,
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
```

This allows factories to live outside the normal Python path.

## Instance Lifecycle

### Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `shared` | One instance per class, cached forever | Fast, stateless services |
| `per_test` | Fresh instance for each test | Tests that modify state |
| `per_suite` | Fresh instance per suite | Balance of isolation/speed |

### Implementation

```python
def _get_instance(self, class_path: str, cls: type) -> Any:
    # per_test: Never use cache
    if self._lifecycle == InstanceLifecycle.PER_TEST:
        return self._construct_instance(class_path, cls)

    # shared/per_suite: Check cache first
    if class_path in self._instance_cache:
        return self._instance_cache[class_path]

    instance = self._construct_instance(class_path, cls)
    self._instance_cache[class_path] = instance
    return instance

def on_suite_start(self, suite_name: str) -> None:
    if self._lifecycle == InstanceLifecycle.PER_SUITE:
        self._instance_cache.clear()

def on_test_start(self, test_name: str) -> None:
    if self._lifecycle == InstanceLifecycle.PER_TEST:
        self._instance_cache.clear()
```

## Async Support

### Detection

```python
import asyncio

def is_async_callable(func: Any) -> bool:
    if asyncio.iscoroutinefunction(func):
        return True
    if hasattr(func, "__call__"):
        return asyncio.iscoroutinefunction(func.__call__)
    return False
```

### Execution

Async functions are run via `asyncio.run()`:

```python
async def run_with_optional_timeout() -> Any:
    coro = func(*args, **kwargs)
    if timeout_ms is None:
        return await coro
    return await asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)

return asyncio.run(run_with_optional_timeout())
```

### Sync Timeout

Sync functions use `ThreadPoolExecutor` for timeout:

```python
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(func, *args, **kwargs)
    return future.result(timeout=timeout_ms / 1000.0)
```

Note: This is best-effort. Some blocking operations (C extensions, I/O) may not be interruptible.

## Output Capture

Uses `sys.stdout`/`sys.stderr` redirection:

```python
old_stdout = sys.stdout
sys.stdout = StringIO()
try:
    # Run test
finally:
    sys.stdout = old_stdout
    captured = new_stdout.getvalue()
```

Captured output is stored in `TestResult.logs`.

## Type Handling

### JSON to Python

IR JSON types map directly to Python:

| JSON | Python |
|------|--------|
| `string` | `str` |
| `number` | `int` or `float` |
| `boolean` | `bool` |
| `null` | `None` |
| `array` | `list` |
| `object` | `dict` |

### Object Comparison (CONTAINS)

For `CONTAINS` assertions, objects are converted to dicts:

```python
def _to_dict(self, obj: Any) -> dict | None:
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    if hasattr(obj, "model_dump"):  # Pydantic v2
        return obj.model_dump()
    if hasattr(obj, "dict"):  # Pydantic v1
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return None
```

## Configuration

```yaml
# babeltest.yaml
adapters:
  python:
    # Paths to add to sys.path
    source_paths:
      - "./src"

    # Factory directory (default: babel/factories)
    factories: "./babel/factories"

    # Instance lifecycle: shared | per_test | per_suite
    instance_lifecycle: shared

    # Capture stdout/stderr
    capture_output: true

    # Default timeout (ms)
    timeout_ms: 5000

    # Verbose output
    debug_mode: false
```

## Known Limitations

1. **Sync timeout is best-effort**: Blocking C extensions may not be interruptible
2. **No mock injection**: Mocks must be wired via factories
3. **No coverage integration**: Coverage must be run externally (`pytest-cov`)
4. **Single Python version**: Adapter runs in same Python as BabelTest

## Future Improvements

- [ ] Support for `MUTATES` assertions (spy/mock verification)
- [ ] Coverage integration
- [ ] Parallel test execution
- [ ] Subprocess isolation (run tests in separate process)
- [ ] Property-based testing support
