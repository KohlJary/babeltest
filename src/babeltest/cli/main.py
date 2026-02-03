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
    "--lang",
    "-l",
    type=click.Choice(["python", "py", "javascript", "js", "csharp", "cs"]),
    default="python",
    help="Target language adapter to use.",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug output.",
)
def run(
    path: Path,
    project: Path | None,
    config: Path | None,
    lang: str,
    debug: bool,
) -> None:
    """Run tests from a .babel or IR JSON file.

    PATH is the path to a .babel file or JSON file containing the test IR.
    """
    from babeltest.compiler.ir import IRDocument
    from babeltest.config import load_config
    from babeltest.runner import format_results, load_ir, run_tests

    project_root = project or Path.cwd()

    # Load config
    cfg = load_config(config_path=config, project_root=project_root)

    # Normalize language name
    if lang in ("python", "py"):
        lang_norm = "python"
    elif lang in ("javascript", "js"):
        lang_norm = "javascript"
    else:
        lang_norm = "csharp"

    # Override debug mode if flag is set
    if debug:
        if lang_norm == "python":
            cfg.adapters.python.debug_mode = True
        elif lang_norm == "javascript":
            cfg.adapters.javascript.debug_mode = True
        else:
            cfg.adapters.csharp.debug_mode = True

    show_all_logs = {
        "python": cfg.adapters.python.debug_mode,
        "javascript": cfg.adapters.javascript.debug_mode,
        "csharp": cfg.adapters.csharp.debug_mode,
    }.get(lang_norm, False)

    if show_all_logs:
        console.print(f"[dim]Config: {cfg.model_dump_json(indent=2)}[/dim]\n")

    # Load IR - either from .babel file or JSON
    ir: IRDocument
    try:
        if path.suffix == ".babel":
            from babeltest.compiler.parser import parse_file

            ir = parse_file(path)
        else:
            ir = load_ir(path)
    except Exception as e:
        console.print(f"[red]Error loading tests:[/red] {e}")
        raise SystemExit(1)

    console.print(f"[dim]Running tests from {path} (adapter: {lang_norm})[/dim]\n")

    # Create adapter based on language
    if lang_norm == "python":
        from babeltest.adapters.python import PythonAdapter

        adapter = PythonAdapter(project_root=project_root, config=cfg.adapters.python)
    elif lang_norm == "javascript":
        from babeltest.adapters.javascript import JSAdapter

        adapter = JSAdapter(project_root=project_root, config=cfg.adapters.javascript)
    else:
        from babeltest.adapters.csharp import CSharpAdapter

        adapter = CSharpAdapter(project_root=project_root, config=cfg.adapters.csharp)

    # Run tests
    try:
        results = run_tests(ir, adapter)
    finally:
        # Cleanup JS adapter if used
        if hasattr(adapter, "shutdown"):
            adapter.shutdown()

    # Format and display results (show all logs in debug mode)
    output = format_results(results, show_all_logs=show_all_logs)

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
    """Validate a .babel or IR JSON file without running tests.

    PATH is the path to a .babel file or JSON file containing the test IR.
    """
    from babeltest.compiler.ir import IRDocument
    from babeltest.runner import load_ir

    ir: IRDocument
    try:
        if path.suffix == ".babel":
            from babeltest.compiler.parser import parse_file

            ir = parse_file(path)
        else:
            ir = load_ir(path)

        test_count = len(ir.tests) + sum(len(s.tests) for s in ir.suites)
        suite_count = len(ir.suites)

        console.print(f"[green]\u2713[/green] Valid: {test_count} tests in {suite_count} suites")
    except Exception as e:
        console.print(f"[red]\u2717[/red] Invalid: {e}")
        raise SystemExit(1)


@cli.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for IR JSON. Defaults to stdout.",
)
@click.option(
    "--pretty",
    is_flag=True,
    default=True,
    help="Pretty-print JSON output (default: true).",
)
def compile(path: Path, output: Path | None, pretty: bool) -> None:
    """Compile a .babel file to IR JSON.

    PATH is the path to a .babel file to compile.
    """
    from babeltest.compiler.parser import parse_file

    try:
        ir = parse_file(path)
    except Exception as e:
        console.print(f"[red]Parse error:[/red] {e}")
        raise SystemExit(1)

    # Convert to JSON
    json_output = ir.model_dump_json(indent=2 if pretty else None)

    if output:
        output.write_text(json_output)
        console.print(f"[green]\u2713[/green] Compiled to {output}")
    else:
        console.print(json_output)


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
