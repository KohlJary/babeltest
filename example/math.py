"""Example math utilities - unified target: example.math"""


def add(a: int, b: int) -> int:
    return a + b


def subtract(a: int, b: int) -> int:
    return a - b


def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("divide by zero")
    return a / b


def is_even(n: int) -> bool:
    return n % 2 == 0
