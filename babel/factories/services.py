"""Factories for example.services classes."""

from example.services import UserService


def user_service() -> UserService:
    """Factory for UserService - uses parameterless constructor."""
    return UserService()
