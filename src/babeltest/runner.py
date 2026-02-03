"""Test runner - orchestrates adapter execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from babeltest.adapters.base import Adapter, ResultStatus, TestResult
from babeltest.compiler.ir import IRDocument

if TYPE_CHECKING:
    pass


def load_ir(path: Path) -> IRDocument:
    """Load an IR document from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    return IRDocument.model_validate(data)


def run_tests(
    ir: IRDocument,
    adapter: Adapter,
) -> list[TestResult]:
    """Run all tests in an IR document.

    Args:
        ir: The IR document containing test specs.
        adapter: The adapter to use for execution.

    Returns:
        List of test results.
    """
    results: list[TestResult] = []

    # Run top-level tests (no suite)
    for test in ir.tests:
        test_name = test.description or test.target
        _call_lifecycle(adapter, "on_test_start", test_name)
        result = adapter.run_test(test)
        _call_lifecycle(adapter, "on_test_end", test_name)
        results.append(result)

    # Run suite tests
    for suite in ir.suites:
        _call_lifecycle(adapter, "on_suite_start", suite.name)

        for test in suite.tests:
            # Apply suite's default target if test target is relative
            if test.target.startswith("."):
                if suite.target:
                    test = test.model_copy(update={"target": suite.target + test.target})
                else:
                    # Error: relative target but no suite target
                    results.append(
                        TestResult(
                            test=test,
                            status=ResultStatus.ERROR,
                            message=f"Relative target {test.target!r} but suite has no default target",
                        )
                    )
                    continue

            test_name = test.description or test.target
            _call_lifecycle(adapter, "on_test_start", test_name)
            result = adapter.run_test(test)
            _call_lifecycle(adapter, "on_test_end", test_name)
            results.append(result)

        _call_lifecycle(adapter, "on_suite_end", suite.name)

    return results


def _call_lifecycle(adapter: Adapter, method: str, name: str) -> None:
    """Call a lifecycle method on the adapter if it exists."""
    if hasattr(adapter, method):
        getattr(adapter, method)(name)


def format_results(results: list[TestResult], show_all_logs: bool = False) -> str:
    """Format test results for display.

    Args:
        results: List of test results.
        show_all_logs: If True, show captured output for all tests (not just failures).

    Returns:
        Formatted string for display.
    """
    lines = []
    passed = 0
    failed = 0
    errors = 0

    for result in results:
        status_icon = {
            ResultStatus.PASSED: "\u2713",  # checkmark
            ResultStatus.FAILED: "\u2717",  # x mark
            ResultStatus.ERROR: "!",
            ResultStatus.SKIPPED: "-",
        }[result.status]

        desc = result.test.description or result.test.target
        line = f"  {status_icon} {desc}"

        if result.status == ResultStatus.PASSED:
            passed += 1
            # Show logs for passing tests only if show_all_logs is True
            if show_all_logs and result.logs:
                line += _format_logs(result.logs)
        elif result.status == ResultStatus.FAILED:
            failed += 1
            if result.message:
                line += f"\n      {result.message}"
            # Always show logs for failed tests
            if result.logs:
                line += _format_logs(result.logs)
        elif result.status == ResultStatus.ERROR:
            errors += 1
            if result.message:
                line += f"\n      {result.message}"
            # Always show logs for errors
            if result.logs:
                line += _format_logs(result.logs)

        lines.append(line)

    # Summary
    total = len(results)
    summary = f"\n{passed} passed, {failed} failed, {errors} errors ({total} total)"

    return "\n".join(lines) + summary


def _format_logs(logs: list[str]) -> str:
    """Format captured logs for display."""
    formatted = []
    for log in logs:
        # Indent each line of the log
        for line in log.split("\n"):
            formatted.append(f"      {line}")
    return "\n" + "\n".join(formatted)
