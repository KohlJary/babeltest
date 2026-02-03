"""Python adapter for BabelTest.

Resolves targets like "myapp.services.UserService.get_by_id" and invokes them.
Uses factory discovery from babel/factories/ to construct class instances.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from babeltest.adapters.base import Adapter
from babeltest.diagnostics import (
    ConstructionError,
    DiagnosticContext,
    ResolutionError,
    suggest_factory_creation,
)

if TYPE_CHECKING:
    from babeltest.config import PythonAdapterConfig


class PythonAdapter(Adapter):
    """Adapter for executing tests against Python code."""

    def __init__(
        self,
        project_root: Path | None = None,
        config: PythonAdapterConfig | None = None,
    ):
        """Initialize the Python adapter.

        Args:
            project_root: Root directory of the project. Defaults to cwd.
            config: Adapter configuration. If None, uses defaults.
        """
        from babeltest.config import PythonAdapterConfig

        self.project_root = project_root or Path.cwd()
        self.config = config or PythonAdapterConfig()

        # Resolve factories path
        factories = self.config.factories
        if not Path(factories).is_absolute():
            self.factories_path = self.project_root / factories
        else:
            self.factories_path = Path(factories)

        # Add project root to sys.path
        project_root_str = str(self.project_root)
        if project_root_str not in sys.path:
            sys.path.insert(0, project_root_str)

        # Add configured source paths to sys.path
        for source_path in self.config.source_paths:
            if not Path(source_path).is_absolute():
                source_path = str(self.project_root / source_path)
            if source_path not in sys.path:
                sys.path.insert(0, source_path)

        # Instance lifecycle management
        self._lifecycle = self.config.instance_lifecycle

        # Cache for constructed instances
        self._instance_cache: dict[str, Any] = {}
        # Cache for loaded factory modules
        self._factory_cache: dict[str, Any] = {}

        # Track current suite for per_suite lifecycle
        self._current_suite: str | None = None

    @property
    def debug_mode(self) -> bool:
        """Whether debug mode is enabled."""
        return self.config.debug_mode

    @property
    def capture_output(self) -> bool:
        """Whether to capture stdout/stderr."""
        return self.config.capture_output

    @property
    def default_timeout_ms(self) -> int | None:
        """Default timeout in milliseconds."""
        return self.config.timeout_ms

    def resolve(self, target: str) -> tuple[Any, str]:
        """Resolve a target path to (instance/module, method_name).

        Target formats:
        - "module.function" -> (module, "function")
        - "module.Class.method" -> (instance, "method")
        - "module.submodule.Class.method" -> (instance, "method")

        Returns:
            Tuple of (object to call method on, method name)
        """
        parts = target.split(".")
        ctx = DiagnosticContext(target=target)

        if len(parts) < 2:
            ctx.add_suggestion("Use format: 'module.function' or 'module.Class.method'")
            raise ResolutionError(
                f"Invalid target format: {target}",
                context=ctx,
            )

        # Try progressively longer module paths
        for i in range(len(parts) - 1, 0, -1):
            module_path = ".".join(parts[:i])
            remaining = parts[i:]

            try:
                module = importlib.import_module(module_path)
                ctx.add_search(f"import {module_path}", found=True)
            except ImportError as e:
                ctx.add_search(f"import {module_path}", found=False, reason=str(e))
                continue

            # Navigate to the target
            obj = module
            for j, part in enumerate(remaining[:-1]):
                if not hasattr(obj, part):
                    ctx.add_search(f"{module_path}.{part}", found=False, reason="attribute not found")
                    break
                attr = getattr(obj, part)

                # If it's a class, we need to construct an instance
                if isinstance(attr, type):
                    class_path = f"{module_path}.{'.'.join(remaining[:j+1])}"
                    obj = self._get_instance(class_path, attr)
                else:
                    obj = attr
            else:
                # Successfully navigated to the parent, return with method name
                method_name = remaining[-1]
                if not hasattr(obj, method_name):
                    ctx.add_search(f"{target}", found=False, reason=f"no attribute '{method_name}'")
                    ctx.add_suggestion(f"Check that '{method_name}' exists on {type(obj).__name__}")
                    raise ResolutionError(f"Object {type(obj).__name__} has no attribute '{method_name}'", context=ctx)
                return (obj, method_name)

        ctx.add_suggestion(f"Ensure the module is importable from: {self.project_root}")
        ctx.add_suggestion("Check that source_paths in babeltest.yaml includes your source directory")
        raise ResolutionError(f"Could not resolve target: {target}", context=ctx)

    def invoke(self, target: str, params: dict[str, Any]) -> Any:
        """Invoke the target with given parameters."""
        obj, method_name = self.resolve(target)
        method = getattr(obj, method_name)
        return method(**params)

    def _get_instance(self, class_path: str, cls: type) -> Any:
        """Get or create an instance of a class.

        Resolution order:
        1. Check instance cache (respects lifecycle setting)
        2. Look for factory function in babel/factories/
        3. Try zero-arg constructor
        4. Raise ConstructionError with helpful message
        """
        from babeltest.config import InstanceLifecycle

        # For per_test lifecycle, never use cache (handled by clear_cache calls)
        # For shared/per_suite, check cache
        if self._lifecycle != InstanceLifecycle.PER_TEST:
            if class_path in self._instance_cache:
                return self._instance_cache[class_path]

        # Try factory (with diagnostic tracking)
        ctx = DiagnosticContext(target=class_path)
        instance = self._try_factory(class_path, cls, ctx)
        if instance is not None:
            if self._lifecycle != InstanceLifecycle.PER_TEST:
                self._instance_cache[class_path] = instance
            return instance

        # Try zero-arg constructor
        instance, error = self._try_zero_arg(cls)
        if instance is not None:
            ctx.add_search(f"{cls.__name__}() (zero-arg constructor)", found=True)
            if self._lifecycle != InstanceLifecycle.PER_TEST:
                self._instance_cache[class_path] = instance
            return instance
        else:
            ctx.add_search(f"{cls.__name__}() (zero-arg constructor)", found=False, reason=error)

        # Failed - provide helpful error with diagnostics
        parts = class_path.split(".")
        module_path = ".".join(parts[:-1])

        ctx.add_suggestion(suggest_factory_creation(cls.__name__, module_path, self.config.factories))
        ctx.add_suggestion(f"Add a zero-argument constructor to {cls.__name__}")

        raise ConstructionError(f"Cannot construct {cls.__name__}", context=ctx)

    def _try_factory(self, class_path: str, cls: type, ctx: DiagnosticContext) -> Any | None:
        """Try to find and invoke a factory function for this class.

        Convention: babel/factories/{module_path}.py contains function {class_name_snake}()

        Example:
            class_path = "myapp.services.UserService"
            -> looks for babel/factories/myapp/services.py::user_service()
        """
        parts = class_path.split(".")
        class_name = parts[-1]
        module_parts = parts[:-1]

        # Convert class name to snake_case for factory function name
        factory_func_name = self._to_snake_case(class_name)

        # Build factory module path - try multiple locations
        search_paths: list[tuple[Path, str]] = []  # (path, description)

        # 1. Nested structure: babel/factories/myapp/services.py
        if len(module_parts) > 1:
            nested_path = self.factories_path / "/".join(module_parts[:-1]) / f"{module_parts[-1]}.py"
            search_paths.append((nested_path, "nested structure"))

        # 2. Flat structure: babel/factories/services.py
        if module_parts:
            flat_path = self.factories_path / f"{module_parts[-1]}.py"
            search_paths.append((flat_path, "flat structure"))

        # 3. Class-named file: babel/factories/user_service.py
        class_path_file = self.factories_path / f"{factory_func_name}.py"
        search_paths.append((class_path_file, "class-named file"))

        # Try each path
        for factory_file, desc in search_paths:
            if not factory_file.exists():
                ctx.add_search(f"{factory_file} ({desc})", found=False, reason="file not found")
                continue

            factory_module = self._load_factory_module(factory_file)
            if factory_module is None:
                ctx.add_search(f"{factory_file} ({desc})", found=False, reason="failed to load module")
                continue

            if hasattr(factory_module, factory_func_name):
                ctx.add_search(f"{factory_file}::{factory_func_name}()", found=True)
                factory_func = getattr(factory_module, factory_func_name)
                if self.debug_mode:
                    print(f"[DEBUG] Using factory {factory_file}::{factory_func_name}()")
                return factory_func()
            else:
                ctx.add_search(
                    f"{factory_file} ({desc})",
                    found=False,
                    reason=f"no function '{factory_func_name}'"
                )

        return None

    def _load_factory_module(self, factory_file: Path) -> Any | None:
        """Load a factory module from file."""
        cache_key = str(factory_file.resolve())

        if cache_key in self._factory_cache:
            return self._factory_cache[cache_key]

        if not factory_file.exists():
            return None

        # Import the factory module
        spec = importlib.util.spec_from_file_location(
            f"babeltest_factory_{factory_file.stem}_{id(factory_file)}",
            factory_file,
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module

        try:
            spec.loader.exec_module(module)
        except Exception as e:
            if self.debug_mode:
                print(f"[DEBUG] Failed to load factory {factory_file}: {e}")
            return None

        self._factory_cache[cache_key] = module
        return module

    def _try_zero_arg(self, cls: type) -> tuple[Any | None, str | None]:
        """Try to construct with zero arguments.

        Returns:
            Tuple of (instance, error_message). Instance is None on failure.
        """
        try:
            return cls(), None
        except TypeError as e:
            return None, str(e)

    def _to_snake_case(self, name: str) -> str:
        """Convert CamelCase to snake_case."""
        result = []
        for i, char in enumerate(name):
            if char.isupper() and i > 0:
                result.append("_")
            result.append(char.lower())
        return "".join(result)

    # Lifecycle management methods

    def on_suite_start(self, suite_name: str) -> None:
        """Called when a test suite starts. Clears cache if per_suite lifecycle."""
        from babeltest.config import InstanceLifecycle

        self._current_suite = suite_name
        if self._lifecycle == InstanceLifecycle.PER_SUITE:
            self.clear_instance_cache()

    def on_suite_end(self, suite_name: str) -> None:
        """Called when a test suite ends."""
        self._current_suite = None

    def on_test_start(self, test_name: str) -> None:
        """Called when a test starts. Clears cache if per_test lifecycle."""
        from babeltest.config import InstanceLifecycle

        if self._lifecycle == InstanceLifecycle.PER_TEST:
            self.clear_instance_cache()

    def on_test_end(self, test_name: str) -> None:
        """Called when a test ends."""
        pass

    def clear_instance_cache(self) -> None:
        """Clear the instance cache. Factory cache is preserved."""
        self._instance_cache.clear()

    def clear_cache(self) -> None:
        """Clear all caches (instances and factories)."""
        self._instance_cache.clear()
        self._factory_cache.clear()
