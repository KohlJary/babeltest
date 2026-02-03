"""Factories for example.services classes."""

from example.mocks import MockDatabase, NullLogger
from example.services import UserService


def user_service() -> UserService:
    """Factory for UserService with mock dependencies."""
    return UserService(
        db=MockDatabase(),
        logger=NullLogger(),
    )
