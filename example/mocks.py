"""Mock implementations for testing."""


class MockDatabase:
    """In-memory mock database."""

    def __init__(self):
        self._users = {
            1: {"id": 1, "name": "Kohl", "email": "kohl@example.com", "active": True},
            2: {"id": 2, "name": "Alice", "email": "alice@example.com", "active": True},
        }
        self._next_id = 3

    def get_user(self, user_id: int) -> dict | None:
        return self._users.get(user_id)

    def save_user(self, user: dict) -> dict:
        if "id" not in user:
            user["id"] = self._next_id
            self._next_id += 1
        self._users[user["id"]] = user
        return user


class NullLogger:
    """Logger that discards all messages."""

    def info(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


class CapturingLogger:
    """Logger that captures messages for assertion."""

    def __init__(self):
        self.messages: list[tuple[str, str]] = []

    def info(self, message: str) -> None:
        self.messages.append(("info", message))

    def error(self, message: str) -> None:
        self.messages.append(("error", message))
