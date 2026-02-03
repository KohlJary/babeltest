# BabelTest Adapter Development Guide

This guide explains how to create a language adapter for BabelTest.

## Overview

BabelTest separates **test specification** (what to test) from **test execution** (how to run it). Adapters bridge this gap by:

1. **Resolving** target paths to callable references
2. **Invoking** those callables with test parameters
3. **Handling** language-specific construction (DI, factories)

```
┌──────────┐     ┌──────────┐     ┌──────────────────┐     ┌──────────┐
│ .babel   │────▸│ BabelTest│────▸│ Adapter          │────▸│ Test     │
│ files    │     │ Compiler │     │ (Python/JS/C#)   │     │ Results  │
└──────────┘     └──────────┘     └──────────────────┘     └──────────┘
                      │
                      ▼
                 ┌──────────┐
                 │ IR (JSON)│
                 └──────────┘
```

## Adapter Interface

All adapters extend `babeltest.adapters.base.Adapter`:

```python
from abc import ABC, abstractmethod
from typing import Any

class Adapter(ABC):
    """Base class for language-specific test adapters."""

    @abstractmethod
    def resolve(self, target: str) -> tuple[Any, str]:
        """Resolve a target path to (instance/module, method_name).

        Args:
            target: Dot-notation path like "myapp.services.UserService.get_by_id"

        Returns:
            Tuple of (object to call method on, method name)

        Raises:
            ResolutionError: If target cannot be resolved.
        """
        ...

    @abstractmethod
    def invoke(self, target: str, params: dict[str, Any]) -> Any:
        """Invoke a target with the given parameters.

        Args:
            target: Dot-notation path to the method/function.
            params: Keyword arguments to pass.

        Returns:
            The return value from the invocation.
        """
        ...
```

### Required Methods

| Method | Purpose |
|--------|---------|
| `resolve(target)` | Convert dot-path to callable reference |
| `invoke(target, params)` | Execute the callable with params |

### Optional Properties

Override these to enable features:

```python
@property
def capture_output(self) -> bool:
    """Enable stdout/stderr capture during tests."""
    return False

@property
def debug_mode(self) -> bool:
    """Enable verbose debug output."""
    return False

@property
def default_timeout_ms(self) -> int | None:
    """Default timeout for all tests (None = no timeout)."""
    return None
```

### Optional Lifecycle Hooks

Implement these to support instance lifecycle modes:

```python
def on_suite_start(self, suite_name: str) -> None:
    """Called when a test suite starts."""
    pass

def on_suite_end(self, suite_name: str) -> None:
    """Called when a test suite ends."""
    pass

def on_test_start(self, test_name: str) -> None:
    """Called before each test."""
    pass

def on_test_end(self, test_name: str) -> None:
    """Called after each test."""
    pass
```

## Universal vs Language-Specific

### Universal (handled by base Adapter)

These are implemented once in `base.py` and work for all adapters:

- **Test execution flow** (`run_test`)
- **Assertion checking** (`_check_expectation`, `_check_contains`, `_check_throws`)
- **Output capture** (via `capture.py`)
- **Timeout enforcement** (via `async_runner.py`)
- **Result formatting**

### Language-Specific (implement per adapter)

Each adapter must handle:

| Concern | Python | JavaScript | C# |
|---------|--------|------------|-----|
| **Module loading** | `importlib` | `require`/`import` | `Assembly.Load` |
| **Class instantiation** | Factory discovery | Factory discovery | Reflection + DI |
| **Method invocation** | `getattr` + call | Property access + call | `MethodInfo.Invoke` |
| **Async handling** | `asyncio` | `Promise`/`async-await` | `Task`/`async-await` |
| **Type coercion** | Duck typing | Duck typing | Reflection |

## Factory Discovery Pattern

The Python adapter uses convention-based factory discovery:

```
Target: myapp.services.UserService.get_by_id
                       ^^^^^^^^^^^
                       Need instance of this

Factory search order:
1. babel/factories/myapp/services.py::user_service()
2. babel/factories/services.py::user_service()
3. babel/factories/user_service.py::user_service()
4. UserService() (zero-arg constructor)
```

Other adapters can use similar conventions or language-specific DI:

- **JavaScript**: Look for `babel/factories/services.js` with `userService()` export
- **C#**: Use `[BabelTestFactory]` attribute or DI container integration

## Configuration Integration

Adapters receive configuration via their constructor:

```python
class PythonAdapter(Adapter):
    def __init__(
        self,
        project_root: Path | None = None,
        config: PythonAdapterConfig | None = None,
    ):
        self.config = config or PythonAdapterConfig()
        # Use config.source_paths, config.factories, etc.
```

### Adding a New Adapter Config

1. Add config class to `babeltest/config.py`:

```python
class JavaScriptAdapterConfig(BaseModel):
    entry_point: str = "index.js"
    node_modules: str = "node_modules"
    timeout_ms: int | None = None
```

2. Add to `AdaptersConfig`:

```python
class AdaptersConfig(BaseModel):
    python: PythonAdapterConfig = Field(default_factory=PythonAdapterConfig)
    javascript: JavaScriptAdapterConfig = Field(default_factory=JavaScriptAdapterConfig)
```

3. Update CLI to select adapter based on config or file type.

## Example: Skeleton Adapter

```python
"""Example adapter skeleton for a new language."""

from pathlib import Path
from typing import Any

from babeltest.adapters.base import Adapter
from babeltest.diagnostics import ResolutionError, ConstructionError


class ExampleAdapter(Adapter):
    """Adapter for ExampleLang."""

    def __init__(self, project_root: Path | None = None, config: Any = None):
        self.project_root = project_root or Path.cwd()
        self.config = config
        self._instance_cache: dict[str, Any] = {}

    @property
    def capture_output(self) -> bool:
        return getattr(self.config, 'capture_output', False)

    @property
    def debug_mode(self) -> bool:
        return getattr(self.config, 'debug_mode', False)

    @property
    def default_timeout_ms(self) -> int | None:
        return getattr(self.config, 'timeout_ms', None)

    def resolve(self, target: str) -> tuple[Any, str]:
        """Resolve target to (object, method_name)."""
        parts = target.split(".")

        if len(parts) < 2:
            raise ResolutionError(f"Invalid target: {target}")

        # Language-specific module/class loading here
        module_path = ".".join(parts[:-1])
        method_name = parts[-1]

        # Load module and get object
        obj = self._load_and_construct(module_path)

        return (obj, method_name)

    def invoke(self, target: str, params: dict[str, Any]) -> Any:
        """Invoke target with params."""
        obj, method_name = self.resolve(target)
        method = getattr(obj, method_name)
        return method(**params)

    def _load_and_construct(self, path: str) -> Any:
        """Language-specific loading logic."""
        # Check cache
        if path in self._instance_cache:
            return self._instance_cache[path]

        # Load module/class
        # Construct instance (factory or direct)
        # Cache and return

        raise NotImplementedError("Implement for your language")

    # Lifecycle hooks
    def on_suite_start(self, suite_name: str) -> None:
        pass  # Clear cache if per_suite lifecycle

    def on_test_start(self, test_name: str) -> None:
        pass  # Clear cache if per_test lifecycle

    def clear_cache(self) -> None:
        self._instance_cache.clear()
```

## Testing Your Adapter

1. Create test fixtures in your target language
2. Write factories in `babel/factories/`
3. Create IR JSON files (parser not required)
4. Run with `babel run`

Example test flow:

```bash
# 1. Create target code
echo 'export function add(a, b) { return a + b; }' > src/math.js

# 2. Create test IR
cat > babel/tests/math.json << 'EOF'
{
  "version": "0.1",
  "tests": [{
    "target": "src.math.add",
    "given": { "a": 2, "b": 3 },
    "expect": { "type": "exact", "value": 5 }
  }]
}
EOF

# 3. Run
babel run babel/tests/math.json --adapter javascript
```

## Error Handling

Use `DiagnosticContext` for helpful error messages:

```python
from babeltest.diagnostics import DiagnosticContext, ResolutionError

def resolve(self, target: str) -> tuple[Any, str]:
    ctx = DiagnosticContext(target=target)

    # Track what you searched
    ctx.add_search("module foo.bar", found=False, reason="not found")
    ctx.add_search("module foo", found=True)

    # Add suggestions on failure
    ctx.add_suggestion("Check that the module is in your source path")

    raise ResolutionError("Could not resolve target", context=ctx)
```

This produces output like:

```
Could not resolve target: foo.bar.baz

Searched:
  ✗ module foo.bar (not found)
  ✓ module foo

Suggestions:
  1. Check that the module is in your source path
```

## Checklist for New Adapters

- [ ] Extend `babeltest.adapters.base.Adapter`
- [ ] Implement `resolve()` and `invoke()`
- [ ] Add config class to `babeltest/config.py`
- [ ] Support factory discovery pattern
- [ ] Handle async functions (if language supports)
- [ ] Implement lifecycle hooks (if supporting instance modes)
- [ ] Use `DiagnosticContext` for helpful errors
- [ ] Add tests for the adapter itself
- [ ] Document language-specific conventions

## Current Adapters

| Adapter | Status | Location |
|---------|--------|----------|
| Python | ✓ Complete | `babeltest/adapters/python.py` |
| JavaScript | Planned | - |
| C# | Planned | - |
| Go | Planned | - |
| Rust | Planned | - |
