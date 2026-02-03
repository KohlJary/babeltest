"""Example services with dependencies - tests DI/factory pattern."""

from dataclasses import dataclass
from typing import Protocol


# Protocols for dependencies
class Database(Protocol):
    def get_user(self, user_id: int) -> dict | None: ...
    def save_user(self, user: dict) -> dict: ...


class Logger(Protocol):
    def info(self, message: str) -> None: ...
    def error(self, message: str) -> None: ...


# Domain models
@dataclass
class User:
    id: int
    name: str
    email: str
    active: bool = True


# Service with dependencies
class UserService:
    """User service that requires database and logger."""

    def __init__(self, db: Database, logger: Logger):
        self._db = db
        self._logger = logger

    def get_by_id(self, user_id: int) -> User | None:
        """Get a user by ID."""
        self._logger.info(f"Fetching user {user_id}")
        data = self._db.get_user(user_id)
        if data is None:
            return None
        return User(**data)

    def create(self, name: str, email: str) -> User:
        """Create a new user."""
        self._logger.info(f"Creating user: {name}")
        data = self._db.save_user({"name": name, "email": email, "active": True})
        return User(**data)

    def deactivate(self, user_id: int) -> bool:
        """Deactivate a user. Returns True if user existed."""
        user = self.get_by_id(user_id)
        if user is None:
            self._logger.error(f"User {user_id} not found")
            return False
        user.active = False
        self._db.save_user({"id": user.id, "name": user.name, "email": user.email, "active": False})
        self._logger.info(f"Deactivated user {user_id}")
        return True


# Service without dependencies (zero-arg constructor)
class Calculator:
    """Simple calculator - no DI needed."""

    def add(self, a: int, b: int) -> int:
        return a + b

    def multiply(self, a: int, b: int) -> int:
        return a * b
