"""Example for testing instance lifecycle.

Each service tracks its instance ID to verify lifecycle behavior.
"""

_instance_counter = 0


def reset_counter() -> None:
    """Reset the instance counter (for testing)."""
    global _instance_counter
    _instance_counter = 0


def get_counter() -> int:
    """Get the current instance counter."""
    return _instance_counter


class StatefulService:
    """A service that tracks its instance ID and call count."""

    def __init__(self):
        global _instance_counter
        _instance_counter += 1
        self.instance_id = _instance_counter
        self.call_count = 0

    def do_work(self) -> dict:
        """Do some work, incrementing call count."""
        self.call_count += 1
        return {
            "instance_id": self.instance_id,
            "call_count": self.call_count,
        }

    def get_state(self) -> dict:
        """Get current state without incrementing."""
        return {
            "instance_id": self.instance_id,
            "call_count": self.call_count,
        }
