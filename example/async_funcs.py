"""Example async functions for testing async support."""

import asyncio


async def async_add(a: int, b: int) -> int:
    """Async function that adds two numbers."""
    await asyncio.sleep(0.01)  # Simulate some async work
    return a + b


async def async_fetch_data(key: str) -> dict:
    """Async function that simulates fetching data."""
    await asyncio.sleep(0.05)  # Simulate network delay
    data = {
        "user": {"id": 1, "name": "Kohl"},
        "config": {"theme": "dark", "lang": "en"},
    }
    return data.get(key, {})


async def async_slow_operation(delay_ms: int) -> str:
    """Async function that takes a configurable amount of time."""
    await asyncio.sleep(delay_ms / 1000.0)
    return f"completed after {delay_ms}ms"


async def async_failing() -> None:
    """Async function that raises an error."""
    await asyncio.sleep(0.01)
    raise ValueError("Async operation failed")


# Sync function that takes too long (for testing sync timeout)
def slow_sync_function(delay_ms: int) -> str:
    """Sync function that sleeps for a given time."""
    import time
    time.sleep(delay_ms / 1000.0)
    return f"completed after {delay_ms}ms"
