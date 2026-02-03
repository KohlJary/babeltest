"""C#/.NET adapter for BabelTest.

Spawns a .NET subprocess to execute tests against C# code.
Communicates via JSON over stdin/stdout.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from babeltest.adapters.base import Adapter, ResultStatus, TestResult
from babeltest.compiler.ir import TestSpec
from babeltest.diagnostics import ResolutionError

if TYPE_CHECKING:
    from babeltest.config import CSharpAdapterConfig


class CSharpAdapter(Adapter):
    """Adapter for executing tests against C#/.NET code."""

    def __init__(
        self,
        project_root: Path | None = None,
        config: CSharpAdapterConfig | None = None,
    ):
        """Initialize the C# adapter.

        Args:
            project_root: Root directory of the project. Defaults to cwd.
            config: Adapter configuration. If None, uses defaults.
        """
        from babeltest.config import CSharpAdapterConfig

        self.project_root = project_root or Path.cwd()
        self.config = config or CSharpAdapterConfig()

        # Find the target project if not specified
        if not self.config.project_path:
            self.config.project_path = self._find_project()

        # Find the runner project
        self._runner_path = self._find_runner()

        # Build the runner if needed
        self._ensure_runner_built()

        # .NET subprocess (lazy init)
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

    def _find_project(self) -> str | None:
        """Find a .csproj file in the project root or subdirectories."""
        # Check project root
        for csproj in self.project_root.glob("*.csproj"):
            return str(csproj)

        # Check common subdirectories (example/cs for unified examples)
        for subdir in ["src", "lib", "example/cs", "example_csharp"]:
            subpath = self.project_root / subdir
            if subpath.exists():
                for csproj in subpath.glob("*.csproj"):
                    return str(csproj)

        return None

    def _find_runner(self) -> Path:
        """Find the C# runner project."""
        # Look in the babeltest package
        pkg_dir = Path(__file__).parent.parent
        runner = pkg_dir / "runtimes" / "csharp" / "BabelTestRunner"

        if runner.exists() and (runner / "BabelTestRunner.csproj").exists():
            return runner

        raise FileNotFoundError(
            f"C# runner not found at {runner}. "
            "Make sure babeltest is properly installed."
        )

    def _ensure_runner_built(self) -> None:
        """Build the runner project if needed."""
        dll_path = self._runner_path / "bin" / "Debug" / "net8.0" / "BabelTestRunner.dll"
        dotnet = self.config.dotnet_path or "dotnet"

        if not dll_path.exists():
            if self.debug_mode:
                print(f"[DEBUG] Building C# runner at {self._runner_path}")

            result = subprocess.run(
                [dotnet, "build", "-c", "Debug"],
                cwd=str(self._runner_path),
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to build C# runner:\n{result.stderr}\n{result.stdout}"
                )

        # Also build the target project if specified
        if self.config.project_path:
            project_dir = Path(self.config.project_path).parent
            if self.debug_mode:
                print(f"[DEBUG] Building target project at {project_dir}")

            result = subprocess.run(
                [dotnet, "build", "-c", "Debug"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to build target project:\n{result.stderr}\n{result.stdout}"
                )

    def _start_dotnet(self) -> subprocess.Popen:
        """Start the .NET subprocess."""
        if self._process is not None and self._process.poll() is None:
            return self._process

        dotnet_path = self.config.dotnet_path or "dotnet"

        self._process = subprocess.Popen(
            [dotnet_path, "run", "--project", str(self._runner_path), "--no-build"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE if not self.debug_mode else None,
            cwd=str(self.project_root),
            text=True,
            bufsize=1,
        )

        return self._process

    def _send_command(self, command: dict) -> dict:
        """Send a command to the .NET runner and get the response."""
        proc = self._start_dotnet()

        if proc.stdin is None or proc.stdout is None:
            raise RuntimeError(".NET process pipes not available")

        # Add config to command
        if "config" not in command:
            command["config"] = {
                "project_root": str(self.project_root),
                "project_path": self.config.project_path,
                "factories_path": self.config.factories,
                "debug": self.debug_mode,
            }

        # Send command
        try:
            proc.stdin.write(json.dumps(command) + "\n")
            proc.stdin.flush()
        except BrokenPipeError:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f".NET process died: {stderr}")

        # Read response
        response_line = proc.stdout.readline()
        if not response_line:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"No response from .NET runner: {stderr}")

        try:
            return json.loads(response_line)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from .NET runner: {response_line!r}") from e

    def resolve(self, target: str) -> tuple[Any, str]:
        """Resolve is not used directly - .NET runner handles resolution."""
        parts = target.rsplit(".", 1)
        if len(parts) < 2:
            raise ResolutionError(f"Invalid target format: {target}")
        return (target, parts[-1])

    def invoke(self, target: str, params: dict[str, Any]) -> Any:
        """Invoke is handled by run_test which calls the .NET runner."""
        raise NotImplementedError("Use run_test() for C# adapter")

    def run_test(self, test: TestSpec) -> TestResult:
        """Run a single test via the .NET runner."""
        import time

        start = time.perf_counter()

        try:
            result = self._send_command({
                "action": "run",
                "test": {
                    "target": test.target,
                    "description": test.description,
                    "given": test.given,
                    "types": test.types,
                    "expect": test.expect.model_dump() if test.expect else None,
                    "throws": test.throws.model_dump() if test.throws else None,
                    "timeout_ms": test.timeout_ms,
                    "mocks": [m.model_dump() for m in test.mocks] if test.mocks else [],
                    "mutates": test.mutates.model_dump() if test.mutates else None,
                },
            })

            duration_ms = result.get("duration_ms", (time.perf_counter() - start) * 1000)

            status_map = {
                "passed": ResultStatus.PASSED,
                "failed": ResultStatus.FAILED,
                "error": ResultStatus.ERROR,
                "ok": ResultStatus.PASSED,
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
                message=f"C# adapter error: {e}",
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
            pass

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
        """Shutdown the .NET subprocess."""
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
