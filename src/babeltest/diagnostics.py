"""Diagnostics and error reporting for BabelTest.

Provides detailed error messages with actionable suggestions.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SearchAttempt:
    """Record of a single search attempt during resolution."""

    location: str  # What was searched (file path, module path, etc.)
    found: bool  # Whether anything was found
    reason: str | None = None  # Why it failed (if not found)


@dataclass
class DiagnosticContext:
    """Accumulated context during a resolution attempt."""

    target: str  # What we're trying to resolve
    searches: list[SearchAttempt] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def add_search(self, location: str, found: bool, reason: str | None = None) -> None:
        """Record a search attempt."""
        self.searches.append(SearchAttempt(location, found, reason))

    def add_suggestion(self, suggestion: str) -> None:
        """Add a suggested fix."""
        self.suggestions.append(suggestion)

    def format_error(self, summary: str) -> str:
        """Format a detailed error message.

        Args:
            summary: The main error message.

        Returns:
            Formatted error with search history and suggestions.
        """
        lines = [summary, ""]

        # Show what was searched
        if self.searches:
            lines.append("Searched:")
            for attempt in self.searches:
                icon = "✓" if attempt.found else "✗"
                line = f"  {icon} {attempt.location}"
                if attempt.reason:
                    line += f" ({attempt.reason})"
                lines.append(line)
            lines.append("")

        # Show suggestions
        if self.suggestions:
            lines.append("Suggestions:")
            for i, suggestion in enumerate(self.suggestions, 1):
                lines.append(f"  {i}. {suggestion}")

        return "\n".join(lines)


class ResolutionError(Exception):
    """Raised when a target cannot be resolved.

    Includes diagnostic context about what was searched.
    """

    def __init__(self, message: str, context: DiagnosticContext | None = None):
        self.context = context
        if context:
            message = context.format_error(message)
        super().__init__(message)


class ConstructionError(Exception):
    """Raised when an instance cannot be constructed.

    Includes diagnostic context about factory search.
    """

    def __init__(self, message: str, context: DiagnosticContext | None = None):
        self.context = context
        if context:
            message = context.format_error(message)
        super().__init__(message)


def format_value_diff(expected: Any, actual: Any, max_length: int = 100) -> str:
    """Format a diff between expected and actual values.

    Args:
        expected: The expected value.
        actual: The actual value.
        max_length: Max length for value repr before truncation.

    Returns:
        Formatted diff string.
    """
    expected_repr = _truncate_repr(expected, max_length)
    actual_repr = _truncate_repr(actual, max_length)

    return f"Expected: {expected_repr}\n  Actual: {actual_repr}"


def format_dict_diff(expected: dict, actual: dict, path: str = "") -> list[str]:
    """Format a detailed diff between two dicts.

    Shows which keys are missing, extra, or have different values.

    Args:
        expected: The expected dict.
        actual: The actual dict.
        path: Current path for nested diffs.

    Returns:
        List of diff lines.
    """
    lines = []

    expected_keys = set(expected.keys())
    actual_keys = set(actual.keys())

    # Missing keys
    for key in sorted(expected_keys - actual_keys):
        key_path = f"{path}.{key}" if path else key
        lines.append(f"  - Missing: {key_path}")

    # Extra keys (not necessarily an error for CONTAINS, but informative)
    # for key in sorted(actual_keys - expected_keys):
    #     key_path = f"{path}.{key}" if path else key
    #     lines.append(f"  + Extra: {key_path}")

    # Different values
    for key in sorted(expected_keys & actual_keys):
        key_path = f"{path}.{key}" if path else key
        exp_val = expected[key]
        act_val = actual[key]

        if isinstance(exp_val, dict) and isinstance(act_val, dict):
            # Recurse for nested dicts
            nested = format_dict_diff(exp_val, act_val, key_path)
            lines.extend(nested)
        elif exp_val != act_val:
            lines.append(f"  ≠ {key_path}: expected {exp_val!r}, got {act_val!r}")

    return lines


def _truncate_repr(value: Any, max_length: int) -> str:
    """Get repr of value, truncating if too long."""
    r = repr(value)
    if len(r) > max_length:
        return r[: max_length - 3] + "..."
    return r


def suggest_factory_creation(
    class_name: str,
    module_path: str,
    factories_dir: str | Path,
) -> str:
    """Generate a suggestion for creating a factory function.

    Args:
        class_name: Name of the class that needs a factory.
        module_path: Full module path (e.g., "myapp.services").
        factories_dir: Path to the factories directory.

    Returns:
        Formatted suggestion with example code.
    """
    # Convert CamelCase to snake_case
    func_name = _to_snake_case(class_name)

    # Determine factory file path
    module_parts = module_path.split(".")
    if module_parts:
        factory_file = f"{factories_dir}/{module_parts[-1]}.py"
    else:
        factory_file = f"{factories_dir}/{func_name}.py"

    return f"""Create a factory function:

  # {factory_file}
  from {module_path} import {class_name}

  def {func_name}() -> {class_name}:
      # Construct with required dependencies
      return {class_name}(...)
"""


def _to_snake_case(name: str) -> str:
    """Convert CamelCase to snake_case."""
    result = []
    for i, char in enumerate(name):
        if char.isupper() and i > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result)
