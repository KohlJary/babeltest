"""Base adapter interface for BabelTest.

Each language adapter implements this interface to execute tests
against code in that language.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, is_dataclass, asdict
from enum import Enum
from typing import Any

from babeltest.compiler.ir import Expectation, ExpectationType, TestSpec, ThrowsExpectation


class ResultStatus(str, Enum):
    """Test result status."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"  # Test couldn't run (setup failure, etc.)
    SKIPPED = "skipped"


@dataclass
class TestResult:
    """Result of running a single test."""

    test: TestSpec
    status: ResultStatus
    message: str | None = None
    actual_value: Any = None
    expected_value: Any = None
    exception: Exception | None = None
    duration_ms: float = 0.0
    logs: list[str] = field(default_factory=list)


class Adapter(ABC):
    """Base class for language-specific test adapters."""

    @property
    def capture_output(self) -> bool:
        """Whether to capture stdout/stderr during tests. Override in subclass."""
        return False

    @property
    def debug_mode(self) -> bool:
        """Whether debug mode is enabled. Override in subclass."""
        return False

    @property
    def default_timeout_ms(self) -> int | None:
        """Default timeout in milliseconds. Override in subclass."""
        return None

    @abstractmethod
    def resolve(self, target: str) -> Any:
        """Resolve a target path to an invocable reference.

        Args:
            target: Dot-notation path like "myapp.services.UserService.get_by_id"

        Returns:
            A tuple of (instance_or_module, method/function) that can be invoked.

        Raises:
            ResolutionError: If the target cannot be resolved.
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

        Raises:
            Any exception raised by the target.
        """
        ...

    def run_test(self, test: TestSpec) -> TestResult:
        """Run a single test and return the result."""
        import time

        from babeltest.async_runner import TimeoutError as BabelTimeoutError
        from babeltest.async_runner import run_with_timeout
        from babeltest.capture import OutputCapture

        start = time.perf_counter()
        capture = OutputCapture(enabled=self.capture_output)
        logs: list[str] = []

        # Determine timeout: test-specific > default > None
        timeout_ms = test.timeout_ms if test.timeout_ms is not None else self.default_timeout_ms

        try:
            capture.start()

            # Get the callable and run with timeout support
            obj, method_name = self.resolve(test.target)
            method = getattr(obj, method_name)
            result = run_with_timeout(method, kwargs=test.given, timeout_ms=timeout_ms)

            captured = capture.stop()
            duration_ms = (time.perf_counter() - start) * 1000

            # Collect logs from captured output
            if captured.has_output:
                logs = captured.as_logs()

            # If we expected an exception but didn't get one
            if test.throws:
                return TestResult(
                    test=test,
                    status=ResultStatus.FAILED,
                    message=f"Expected exception {test.throws.type} but call succeeded",
                    actual_value=result,
                    duration_ms=duration_ms,
                    logs=logs,
                )

            # Check return value assertion
            if test.expect:
                passed, message = self._check_expectation(result, test.expect)
                return TestResult(
                    test=test,
                    status=ResultStatus.PASSED if passed else ResultStatus.FAILED,
                    message=message,
                    actual_value=result,
                    expected_value=test.expect.value,
                    duration_ms=duration_ms,
                    logs=logs,
                )

            # No assertion - just check it didn't throw
            return TestResult(
                test=test,
                status=ResultStatus.PASSED,
                duration_ms=duration_ms,
                logs=logs,
            )

        except BabelTimeoutError as e:
            captured = capture.stop()
            duration_ms = (time.perf_counter() - start) * 1000

            if captured.has_output:
                logs = captured.as_logs()

            return TestResult(
                test=test,
                status=ResultStatus.FAILED,
                message=f"Test timed out after {e.timeout_ms}ms",
                duration_ms=duration_ms,
                logs=logs,
            )

        except Exception as e:
            captured = capture.stop()
            duration_ms = (time.perf_counter() - start) * 1000

            # Collect logs from captured output
            if captured.has_output:
                logs = captured.as_logs()

            # If we expected an exception, check it matches
            if test.throws:
                passed, message = self._check_throws(e, test.throws)
                return TestResult(
                    test=test,
                    status=ResultStatus.PASSED if passed else ResultStatus.FAILED,
                    message=message,
                    exception=e,
                    duration_ms=duration_ms,
                    logs=logs,
                )

            # Unexpected exception
            return TestResult(
                test=test,
                status=ResultStatus.ERROR,
                message=f"{type(e).__name__}: {e}",
                exception=e,
                duration_ms=duration_ms,
                logs=logs,
            )

    def _check_expectation(self, actual: Any, expect: Expectation) -> tuple[bool, str | None]:
        """Check if actual value matches expectation."""
        match expect.type:
            case ExpectationType.EXACT:
                if actual == expect.value:
                    return True, None
                return False, f"Expected {expect.value!r}, got {actual!r}"

            case ExpectationType.CONTAINS:
                return self._check_contains(actual, expect.value, path="")

            case ExpectationType.TYPE:
                type_name = type(actual).__name__
                if type_name == expect.value:
                    return True, None
                return False, f"Expected type {expect.value}, got {type_name}"

            case ExpectationType.NULL:
                if actual is None:
                    return True, None
                return False, f"Expected None, got {actual!r}"

            case ExpectationType.NOT_NULL:
                if actual is not None:
                    return True, None
                return False, "Expected non-None value, got None"

            case ExpectationType.TRUE:
                if actual is True:
                    return True, None
                return False, f"Expected True, got {actual!r}"

            case ExpectationType.FALSE:
                if actual is False:
                    return True, None
                return False, f"Expected False, got {actual!r}"

        return False, f"Unknown expectation type: {expect.type}"

    def _check_contains(
        self, actual: Any, expected: Any, path: str = ""
    ) -> tuple[bool, str | None]:
        """Recursively check if actual contains expected values.

        Handles:
        - Nested dicts
        - Dataclasses
        - Pydantic models
        - Lists (subset matching)
        - Primitive values

        Args:
            actual: The actual value from the test.
            expected: The expected value/structure.
            path: Current path for error messages (e.g., "user.profile.name").

        Returns:
            Tuple of (passed, error_message).
        """
        # Format path for error messages
        def fmt_path(p: str) -> str:
            return f" at '{p}'" if p else ""

        # Convert actual to dict if it's a complex object
        actual_dict = self._to_dict(actual)

        # Handle dict expectations (most common case)
        if isinstance(expected, dict):
            if actual_dict is None:
                return False, f"Expected object with keys{fmt_path(path)}, got {type(actual).__name__}"

            for key, expected_val in expected.items():
                key_path = f"{path}.{key}" if path else key

                if key not in actual_dict:
                    return False, f"Missing key '{key}'{fmt_path(path)}"

                actual_val = actual_dict[key]

                # Recursive check for nested structures
                if isinstance(expected_val, dict):
                    passed, msg = self._check_contains(actual_val, expected_val, key_path)
                    if not passed:
                        return False, msg
                elif isinstance(expected_val, list):
                    passed, msg = self._check_list_contains(actual_val, expected_val, key_path)
                    if not passed:
                        return False, msg
                else:
                    # Direct value comparison
                    if actual_val != expected_val:
                        return False, (
                            f"Mismatch at '{key_path}': "
                            f"expected {expected_val!r}, got {actual_val!r}"
                        )

            return True, None

        # Handle list expectations
        if isinstance(expected, list):
            return self._check_list_contains(actual, expected, path)

        # Handle primitive expectations (direct comparison)
        if actual != expected:
            return False, f"Expected {expected!r}{fmt_path(path)}, got {actual!r}"

        return True, None

    def _check_list_contains(
        self, actual: Any, expected: list, path: str
    ) -> tuple[bool, str | None]:
        """Check if actual list contains expected items.

        Supports:
        - Exact item matching
        - Subset matching (all expected items exist in actual)
        - Nested structure matching within list items
        """
        def fmt_path(p: str) -> str:
            return f" at '{p}'" if p else ""

        if not isinstance(actual, (list, tuple)):
            return False, f"Expected list{fmt_path(path)}, got {type(actual).__name__}"

        # For each expected item, find a matching item in actual
        for i, expected_item in enumerate(expected):
            item_path = f"{path}[{i}]"

            found = False
            for actual_item in actual:
                if isinstance(expected_item, dict):
                    # For dict items, use contains matching
                    passed, _ = self._check_contains(actual_item, expected_item, "")
                    if passed:
                        found = True
                        break
                else:
                    # For primitives, use direct comparison
                    if actual_item == expected_item:
                        found = True
                        break

            if not found:
                return False, f"Expected item {expected_item!r} not found in list{fmt_path(path)}"

        return True, None

    def _to_dict(self, obj: Any) -> dict | None:
        """Convert an object to a dict for comparison.

        Handles:
        - dict (returned as-is)
        - dataclass (via asdict)
        - Pydantic model (via model_dump)
        - Objects with __dict__

        Returns None if conversion is not possible.
        """
        if isinstance(obj, dict):
            return obj

        if is_dataclass(obj) and not isinstance(obj, type):
            return asdict(obj)

        if hasattr(obj, "model_dump"):  # Pydantic v2
            return obj.model_dump()

        if hasattr(obj, "dict"):  # Pydantic v1
            return obj.dict()

        if hasattr(obj, "__dict__"):
            return vars(obj)

        return None

    def _check_throws(self, exc: Exception, throws: ThrowsExpectation) -> tuple[bool, str | None]:
        """Check if exception matches throws expectation."""
        exc_type = type(exc).__name__

        if throws.type and exc_type != throws.type:
            return False, f"Expected {throws.type}, got {exc_type}"

        if throws.message and throws.message not in str(exc):
            return False, f"Expected message containing {throws.message!r}, got {str(exc)!r}"

        return True, None


# Re-export exceptions from diagnostics for backward compatibility
from babeltest.diagnostics import ConstructionError, ResolutionError

__all__ = [
    "Adapter",
    "TestResult",
    "ResultStatus",
    "ResolutionError",
    "ConstructionError",
]
