"""Example code with nested structures for testing CONTAINS depth."""

from dataclasses import dataclass
from typing import Any


@dataclass
class Address:
    street: str
    city: str
    country: str


@dataclass
class Profile:
    bio: str
    address: Address
    tags: list[str]


@dataclass
class User:
    id: int
    name: str
    profile: Profile


def get_user_with_profile() -> User:
    """Return a user with nested profile data."""
    return User(
        id=1,
        name="Kohl",
        profile=Profile(
            bio="Builder of things",
            address=Address(
                street="123 Main St",
                city="Portland",
                country="USA"
            ),
            tags=["developer", "architect", "writer"]
        )
    )


def get_nested_dict() -> dict[str, Any]:
    """Return a deeply nested dictionary."""
    return {
        "level1": {
            "level2": {
                "level3": {
                    "value": 42,
                    "items": ["a", "b", "c"]
                }
            }
        },
        "metadata": {
            "version": "1.0",
            "features": [
                {"name": "feature1", "enabled": True},
                {"name": "feature2", "enabled": False}
            ]
        }
    }


def get_list_of_users() -> list[dict]:
    """Return a list of user dicts."""
    return [
        {"id": 1, "name": "Alice", "role": "admin"},
        {"id": 2, "name": "Bob", "role": "user"},
        {"id": 3, "name": "Charlie", "role": "user"},
    ]
