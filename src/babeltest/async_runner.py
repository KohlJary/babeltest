"""Async execution support for BabelTest.

Handles running async functions with timeout enforcement.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Coroutine


class TimeoutError(Exception):
    """Raised when a test exceeds its timeout."""

    def __init__(self, timeout_ms: int, message: str | None = None):
        self.timeout_ms = timeout_ms
        msg = message or f"Test timed out after {timeout_ms}ms"
        super().__init__(msg)


def is_async_callable(func: Any) -> bool:
    """Check if a function is async (coroutine function or has __call__ that is async)."""
    if asyncio.iscoroutinefunction(func):
        return True

    # Check for async __call__ (async callable objects)
    if hasattr(func, "__call__"):
        return asyncio.iscoroutinefunction(func.__call__)

    return False


def run_with_timeout(
    func: Callable[..., Any],
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    timeout_ms: int | None = None,
) -> Any:
    """Run a function (sync or async) with optional timeout.

    Args:
        func: The function to run.
        args: Positional arguments.
        kwargs: Keyword arguments.
        timeout_ms: Timeout in milliseconds. None means no timeout.

    Returns:
        The return value from the function.

    Raises:
        TimeoutError: If the function exceeds the timeout.
        Any exception raised by the function.
    """
    kwargs = kwargs or {}

    if is_async_callable(func):
        return _run_async(func, args, kwargs, timeout_ms)
    else:
        return _run_sync(func, args, kwargs, timeout_ms)


def _run_sync(
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict[str, Any],
    timeout_ms: int | None,
) -> Any:
    """Run a synchronous function with optional timeout.

    Note: For sync functions, timeout is implemented via threading.
    This is a best-effort timeout - some blocking operations may not be interruptible.
    """
    if timeout_ms is None:
        # No timeout - just call directly
        return func(*args, **kwargs)

    import concurrent.futures
    import threading

    # Use a thread pool to run with timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_ms / 1000.0)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(timeout_ms)


def _run_async(
    func: Callable[..., Coroutine[Any, Any, Any]],
    args: tuple,
    kwargs: dict[str, Any],
    timeout_ms: int | None,
) -> Any:
    """Run an async function with optional timeout."""

    async def run_with_optional_timeout() -> Any:
        coro = func(*args, **kwargs)
        if timeout_ms is None:
            return await coro
        try:
            return await asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            raise TimeoutError(timeout_ms)

    # Get or create event loop
    try:
        loop = asyncio.get_running_loop()
        # We're already in an async context
        # This can happen if tests are run from within async code
        # In this case, we need to run in a new thread to avoid nested event loops
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, run_with_optional_timeout())
            return future.result()
    except RuntimeError:
        # No running loop - create one (normal case)
        return asyncio.run(run_with_optional_timeout())


class AsyncTestRunner:
    """Runner for async test execution with proper event loop management."""

    def __init__(self, default_timeout_ms: int | None = None):
        """Initialize the async runner.

        Args:
            default_timeout_ms: Default timeout for all tests. Can be overridden per-test.
        """
        self.default_timeout_ms = default_timeout_ms

    def run(
        self,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> Any:
        """Run a function with timeout.

        Args:
            func: The function to run (sync or async).
            args: Positional arguments.
            kwargs: Keyword arguments.
            timeout_ms: Timeout in milliseconds. If None, uses default_timeout_ms.

        Returns:
            The return value from the function.
        """
        effective_timeout = timeout_ms if timeout_ms is not None else self.default_timeout_ms
        return run_with_timeout(func, args, kwargs, effective_timeout)
