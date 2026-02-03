"""Example functions that produce output - for testing capture."""

import sys


def noisy_add(a: int, b: int) -> int:
    """Add two numbers, printing debug info."""
    print(f"Adding {a} + {b}")
    result = a + b
    print(f"Result: {result}")
    return result


def failing_with_output(value: int) -> int:
    """Function that prints and then raises an error."""
    print(f"Processing value: {value}")
    sys.stderr.write(f"Warning: about to fail with {value}\n")
    raise ValueError(f"Cannot process {value}")


def prints_and_returns(message: str) -> str:
    """Function that prints the message and returns it."""
    print(f"Message received: {message}")
    return message
