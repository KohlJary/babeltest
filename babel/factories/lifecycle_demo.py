"""Factories for lifecycle_demo module."""

from example.lifecycle_demo import StatefulService


def stateful_service() -> StatefulService:
    """Create a StatefulService instance."""
    return StatefulService()
