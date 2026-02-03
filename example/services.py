"""Example services - unified target: example.services"""

from dataclasses import dataclass


@dataclass
class User:
    id: int
    name: str
    email: str
    active: bool = True


class UserService:
    def __init__(self):
        self._users = [
            User(id=1, name="Kohl", email="kohl@example.com", active=True),
            User(id=2, name="Alice", email="alice@example.com", active=True),
        ]

    def get_by_id(self, user_id: int) -> User | None:
        return next((u for u in self._users if u.id == user_id), None)

    def create(self, name: str, email: str) -> User:
        user = User(id=len(self._users) + 1, name=name, email=email, active=True)
        self._users.append(user)
        return user

    def deactivate(self, user_id: int) -> bool:
        user = self.get_by_id(user_id)
        if user is None:
            return False
        user.active = False
        return True


class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b

    def multiply(self, a: int, b: int) -> int:
        return a * b
