"""JavaScript/Node.js adapter for BabelTest.

Spawns a Node.js subprocess to execute tests against JavaScript code.
Communicates via JSON over stdin/stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from babeltest.adapters.base import Adapter, ResultStatus, TestResult
from babeltest.compiler.ir import TestSpec
from babeltest.diagnostics import ResolutionError

if TYPE_CHECKING:
    from babeltest.config import JSAdapterConfig


class JSAdapter(Adapter):
    """Adapter for executing tests against JavaScript/Node.js code."""

    def __init__(
        self,
        project_root: Path | None = None,
        config: JSAdapterConfig | None = None,
    ):
        """Initialize the JavaScript adapter.

        Args:
            project_root: Root directory of the project. Defaults to cwd.
            config: Adapter configuration. If None, uses defaults.
        """
        from babeltest.config import JSAdapterConfig

        self.project_root = project_root or Path.cwd()
        self.config = config or JSAdapterConfig()

        # Find the runner script
        self._runner_path = self._find_runner()

        # Node.js subprocess (lazy init)
        self._process: subprocess.Popen | None = None

    @property
    def debug_mode(self) -> bool:
        """Whether debug mode is enabled."""
        return self.config.debug_mode

    @property
    def capture_output(self) -> bool:
        """Whether to capture stdout/stderr."""
        return self.config.capture_output

    @property
    def default_timeout_ms(self) -> int | None:
        """Default timeout in milliseconds."""
        return self.config.timeout_ms

    def _find_runner(self) -> Path:
        """Find the Node.js runner script."""
        # Look in the babeltest package
        pkg_dir = Path(__file__).parent.parent
        runner = pkg_dir / "runtimes" / "js" / "runner.mjs"

        if runner.exists():
            return runner

        raise FileNotFoundError(
            f"JavaScript runner not found at {runner}. "
            "Make sure babeltest is properly installed."
        )

    def _start_node(self) -> subprocess.Popen:
        """Start the Node.js subprocess."""
        if self._process is not None and self._process.poll() is None:
            return self._process

        node_path = self.config.node_path or "node"

        self._process = subprocess.Popen(
            [node_path, str(self._runner_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if not self.debug_mode else None,
            cwd=str(self.project_root),
            text=True,
            bufsize=1,  # Line buffered
        )

        return self._process

    def _send_command(self, command: dict) -> dict:
        """Send a command to the Node.js runner and get the response."""
        proc = self._start_node()

        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError("Node.js process pipes not available")

        # Add config to first command
        if "config" not in command:
            command["config"] = {
                "projectRoot": str(self.project_root),
                "factoriesPath": self.config.factories,
                "moduleType": self.config.module_type,
                "debug": self.debug_mode,
            }

        # Send command
        try:
            proc.stdin.write(json.dumps(command) + "\n")
            proc.stdin.flush()
        except BrokenPipeError:
            # Process died, get error
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"Node.js process died: {stderr}")

        # Read response
        response_line = proc.stdout.readline()
        if not response_line:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"No response from Node.js runner: {stderr}")

        try:
            return json.loads(response_line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from Node.js runner: {response_line!r}") from e

    def resolve(self, target: str) -> tuple[Any, str]:
        """Resolve is not used directly - JS runner handles resolution."""
        # For JS, we don't pre-resolve - the runner does it
        # Return a placeholder that run_test understands
        parts = target.rsplit(".", 1)
        if len(parts) < 2:
            raise ResolutionError(f"Invalid target format: {target}")
        return (target, parts[-1])

    def invoke(self, target: str, params: dict[str, Any]) -> Any:
        """Invoke is handled by run_test which calls the Node.js runner."""
        raise NotImplementedError("Use run_test() for JS adapter")

    def run_test(self, test: TestSpec) -> TestResult:
        """Run a single test via the Node.js runner."""
        import time

        start = time.perf_counter()

        try:
            # Send test to runner (including mocks)
            result = self._send_command({
                "action": "run",
                "test": {
                    "target": test.target,
                    "description": test.description,
                    "given": test.given,
                    "expect": test.expect.model_dump() if test.expect else None,
                    "throws": test.throws.model_dump() if test.throws else None,
                    "timeout_ms": test.timeout_ms,
                    "mocks": [m.model_dump() for m in test.mocks] if test.mocks else [],
                },
            })

            duration_ms = result.get("duration_ms", (time.perf_counter() - start) * 1000)

            status_map = {
                "passed": ResultStatus.PASSED,
                "failed": ResultStatus.FAILED,
                "error": ResultStatus.ERROR,
            }

            return TestResult(
                test=test,
                status=status_map.get(result["status"], ResultStatus.ERROR),
                message=result.get("message"),
                actual_value=result.get("actual"),
                expected_value=result.get("expected"),
                duration_ms=duration_ms,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return TestResult(
                test=test,
                status=ResultStatus.ERROR,
                message=f"JS adapter error: {e}",
                exception=e,
                duration_ms=duration_ms,
            )

    def on_suite_start(self, suite_name: str) -> None:
        """Called when a test suite starts."""
        try:
            self._send_command({
                "action": "lifecycle",
                "lifecycle": "suite_start",
                "data": {"name": suite_name},
            })
        except Exception:
            pass  # Lifecycle events are best-effort

    def on_suite_end(self, suite_name: str) -> None:
        """Called when a test suite ends."""
        try:
            self._send_command({
                "action": "lifecycle",
                "lifecycle": "suite_end",
                "data": {"name": suite_name},
            })
        except Exception:
            pass

    def on_test_start(self, test_name: str) -> None:
        """Called when a test starts."""
        try:
            self._send_command({
                "action": "lifecycle",
                "lifecycle": "test_start",
                "data": {"name": test_name},
            })
        except Exception:
            pass

    def on_test_end(self, test_name: str) -> None:
        """Called when a test ends."""
        try:
            self._send_command({
                "action": "lifecycle",
                "lifecycle": "test_end",
                "data": {"name": test_name},
            })
        except Exception:
            pass

    def shutdown(self) -> None:
        """Shutdown the Node.js subprocess."""
        if self._process is not None and self._process.poll() is None:
            try:
                self._send_command({"action": "exit"})
            except Exception:
                pass
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None

    def __del__(self) -> None:
        """Cleanup on deletion."""
        self.shutdown()
