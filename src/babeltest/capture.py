"""Output capture for BabelTest.

Captures stdout/stderr during test execution for debugging.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import dataclass
from io import StringIO
from typing import Any, Generator, TextIO


@dataclass
class CapturedOutput:
    """Container for captured stdout/stderr."""

    stdout: str = ""
    stderr: str = ""

    @property
    def has_output(self) -> bool:
        """Whether any output was captured."""
        return bool(self.stdout or self.stderr)

    def as_logs(self) -> list[str]:
        """Convert captured output to log lines for TestResult."""
        logs = []
        if self.stdout:
            logs.append(f"[stdout]\n{self.stdout}")
        if self.stderr:
            logs.append(f"[stderr]\n{self.stderr}")
        return logs

    def format(self, prefix: str = "  ") -> str:
        """Format captured output for display."""
        lines = []
        if self.stdout:
            lines.append(f"{prefix}stdout:")
            for line in self.stdout.rstrip().split("\n"):
                lines.append(f"{prefix}  {line}")
        if self.stderr:
            lines.append(f"{prefix}stderr:")
            for line in self.stderr.rstrip().split("\n"):
                lines.append(f"{prefix}  {line}")
        return "\n".join(lines)


@contextmanager
def capture_output() -> Generator[CapturedOutput, None, None]:
    """Context manager that captures stdout and stderr.

    Usage:
        with capture_output() as captured:
            print("hello")
            sys.stderr.write("error\\n")

        assert captured.stdout == "hello\\n"
        assert captured.stderr == "error\\n"
    """
    captured = CapturedOutput()

    # Save original streams
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    # Create new string buffers
    new_stdout = StringIO()
    new_stderr = StringIO()

    try:
        # Redirect streams
        sys.stdout = new_stdout
        sys.stderr = new_stderr

        yield captured

    finally:
        # Restore original streams
        sys.stdout = old_stdout
        sys.stderr = old_stderr

        # Capture the output
        captured.stdout = new_stdout.getvalue()
        captured.stderr = new_stderr.getvalue()


class OutputCapture:
    """Reusable output capture that can be enabled/disabled.

    This class provides a more flexible interface for the adapter/runner
    to control output capture based on configuration.
    """

    def __init__(self, enabled: bool = True):
        """Initialize the capture.

        Args:
            enabled: Whether capture is enabled. If False, acts as a no-op.
        """
        self.enabled = enabled
        self._captured: CapturedOutput | None = None
        self._old_stdout: TextIO | Any | None = None
        self._old_stderr: TextIO | Any | None = None
        self._new_stdout: StringIO | None = None
        self._new_stderr: StringIO | None = None

    def start(self) -> None:
        """Start capturing output."""
        if not self.enabled:
            return

        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        self._new_stdout = StringIO()
        self._new_stderr = StringIO()

        sys.stdout = self._new_stdout
        sys.stderr = self._new_stderr

    def stop(self) -> CapturedOutput:
        """Stop capturing and return captured output."""
        if not self.enabled or self._old_stdout is None:
            return CapturedOutput()

        # Restore original streams
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr

        # Build captured output
        captured = CapturedOutput(
            stdout=self._new_stdout.getvalue() if self._new_stdout else "",
            stderr=self._new_stderr.getvalue() if self._new_stderr else "",
        )

        # Reset state
        self._old_stdout = None
        self._old_stderr = None
        self._new_stdout = None
        self._new_stderr = None

        return captured

    def __enter__(self) -> "OutputCapture":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self._captured = self.stop()

    @property
    def captured(self) -> CapturedOutput:
        """Get captured output after context exit."""
        return self._captured or CapturedOutput()
