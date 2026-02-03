"""BabelTest CLI entry point."""

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from babeltest import __version__

console = Console()


@click.group()
@click.version_option(__version__, prog_name="babeltest")
def cli() -> None:
    """BabelTest - GraphQL for unit testing."""
    pass


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory. Defaults to current directory.",
)
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to babeltest.yaml config file.",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug output.",
)
def run(path: Path, project: Path | None, config: Path | None, debug: bool) -> None:
    """Run tests from an IR JSON file.

    PATH is the path to a JSON file containing the test IR.
    """
    from babeltest.adapters.python import PythonAdapter
    from babeltest.config import load_config
    from babeltest.runner import format_results, load_ir, run_tests

    project_root = project or Path.cwd()

    # Load config
    cfg = load_config(config_path=config, project_root=project_root)

    # Override debug mode if flag is set
    if debug:
        cfg.adapters.python.debug_mode = True

    if cfg.adapters.python.debug_mode:
        console.print(f"[dim]Config: {cfg.model_dump_json(indent=2)}[/dim]\n")

    # Load IR
    try:
        ir = load_ir(path)
    except Exception as e:
        console.print(f"[red]Error loading IR:[/red] {e}")
        raise SystemExit(1)

    console.print(f"[dim]Running tests from {path}[/dim]\n")

    # Create adapter with config
    adapter = PythonAdapter(project_root=project_root, config=cfg.adapters.python)

    # Run tests
    results = run_tests(ir, adapter)

    # Format and display results (show all logs in debug mode)
    output = format_results(results, show_all_logs=cfg.adapters.python.debug_mode)

    # Color the output based on results
    has_failures = any(r.status.value in ("failed", "error") for r in results)
    if has_failures:
        console.print(Panel(output, title="[red]Tests Failed[/red]", border_style="red"))
        raise SystemExit(1)
    else:
        console.print(Panel(output, title="[green]Tests Passed[/green]", border_style="green"))


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
def check(path: Path) -> None:
    """Validate an IR JSON file without running tests.

    PATH is the path to a JSON file containing the test IR.
    """
    from babeltest.runner import load_ir

    try:
        ir = load_ir(path)
        test_count = len(ir.tests) + sum(len(s.tests) for s in ir.suites)
        suite_count = len(ir.suites)

        console.print(f"[green]\u2713[/green] Valid IR: {test_count} tests in {suite_count} suites")
    except Exception as e:
        console.print(f"[red]\u2717[/red] Invalid IR: {e}")
        raise SystemExit(1)


@cli.command()
def init() -> None:
    """Initialize BabelTest in the current directory.

    Creates:
    - babel/tests/
    - babel/factories/
    - babel/fixtures/
    - babeltest.yaml
    """
    project_root = Path.cwd()

    dirs = [
        project_root / "babel" / "tests",
        project_root / "babel" / "factories",
        project_root / "babel" / "fixtures",
    ]

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]\u2713[/green] Created {d.relative_to(project_root)}/")

    config_file = project_root / "babeltest.yaml"
    if not config_file.exists():
        config_file.write_text(
            """\
# BabelTest configuration
version: "0.1"

adapters:
  python:
    # Paths to add to Python's sys.path for module resolution
    # source_paths:
    #   - "./src"

    # Directory containing factory functions (default: babel/factories)
    # factories: "./babel/factories"

    # Instance lifecycle: shared | per_test | per_suite
    #   shared: One instance per class across all tests (fastest, default)
    #   per_test: Fresh instance for each test (best isolation)
    #   per_suite: Fresh instance per suite (balance)
    # instance_lifecycle: shared

    # Capture stdout/stderr during test execution
    # capture_output: false

    # Enable verbose debug output
    # debug_mode: false

# Directories to search for test files
# test_paths:
#   - babel/tests

# Directories to search for fixture files
# fixture_paths:
#   - babel/fixtures
"""
        )
        console.print(f"[green]\u2713[/green] Created {config_file.name}")
    else:
        console.print(f"[yellow]-[/yellow] {config_file.name} already exists")

    console.print("\n[dim]BabelTest initialized. Create tests in babel/tests/[/dim]")


@cli.command()
@click.option(
    "--project",
    "-p",
    type=click.Path(exists=True, path_type=Path),
    help="Project root directory. Defaults to current directory.",
)
def config(project: Path | None) -> None:
    """Show the current configuration."""
    from babeltest.config import load_config

    project_root = project or Path.cwd()
    cfg = load_config(project_root=project_root)

    console.print(Panel(cfg.model_dump_json(indent=2), title="BabelTest Config"))


if __name__ == "__main__":
    cli()
