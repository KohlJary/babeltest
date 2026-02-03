"""Configuration management for BabelTest.

Loads and validates babeltest.yaml configuration files.
"""

from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class InstanceLifecycle(str, Enum):
    """Instance lifecycle strategy for test execution."""

    SHARED = "shared"  # One instance per class across all tests (fastest)
    PER_TEST = "per_test"  # Fresh instance for each test (best isolation)
    PER_SUITE = "per_suite"  # Fresh instance per suite (balance)


class PythonAdapterConfig(BaseModel):
    """Configuration for the Python adapter."""

    source_paths: list[str] = Field(default_factory=list)
    """Paths to add to sys.path for module resolution."""

    factories: str = "babel/factories"
    """Directory containing factory functions."""

    instance_lifecycle: InstanceLifecycle = InstanceLifecycle.SHARED
    """How to manage class instance lifecycle."""

    capture_output: bool = False
    """Capture stdout/stderr during test execution."""

    timeout_ms: int | None = None
    """Default timeout for all tests (can be overridden per-test)."""

    debug_mode: bool = False
    """Enable verbose debug output."""

    @field_validator("source_paths", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


class AdaptersConfig(BaseModel):
    """Configuration for all adapters."""

    python: PythonAdapterConfig = Field(default_factory=PythonAdapterConfig)

    # Future adapters
    # javascript: JavaScriptAdapterConfig = Field(default_factory=JavaScriptAdapterConfig)
    # csharp: CSharpAdapterConfig = Field(default_factory=CSharpAdapterConfig)


class BabelTestConfig(BaseModel):
    """Root configuration for BabelTest."""

    version: str = "0.1"
    """Config file version."""

    adapters: AdaptersConfig = Field(default_factory=AdaptersConfig)
    """Adapter-specific configuration."""

    test_paths: list[str] = Field(default_factory=lambda: ["babel/tests"])
    """Directories to search for test files."""

    fixture_paths: list[str] = Field(default_factory=lambda: ["babel/fixtures"])
    """Directories to search for fixture files."""

    @field_validator("test_paths", "fixture_paths", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v


def load_config(config_path: Path | None = None, project_root: Path | None = None) -> BabelTestConfig:
    """Load configuration from a YAML file.

    Args:
        config_path: Explicit path to config file. If None, searches for babeltest.yaml.
        project_root: Project root directory. Defaults to cwd.

    Returns:
        Parsed configuration. Returns default config if no file found.
    """
    project_root = project_root or Path.cwd()

    # Find config file
    if config_path is None:
        candidates = [
            project_root / "babeltest.yaml",
            project_root / "babeltest.yml",
            project_root / ".babeltest.yaml",
            project_root / ".babeltest.yml",
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = candidate
                break

    # No config file - return defaults
    if config_path is None or not config_path.exists():
        return BabelTestConfig()

    # Load and parse YAML
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    return BabelTestConfig.model_validate(data)


def resolve_paths(config: BabelTestConfig, project_root: Path) -> BabelTestConfig:
    """Resolve relative paths in config to absolute paths.

    Args:
        config: The configuration to update.
        project_root: Base directory for relative paths.

    Returns:
        Config with resolved paths (new instance).
    """
    python_config = config.adapters.python

    # Resolve source paths
    resolved_source_paths = [
        str((project_root / p).resolve()) if not Path(p).is_absolute() else p
        for p in python_config.source_paths
    ]

    # Resolve factories path
    factories_path = python_config.factories
    if not Path(factories_path).is_absolute():
        factories_path = str((project_root / factories_path).resolve())

    # Resolve test and fixture paths
    resolved_test_paths = [
        str((project_root / p).resolve()) if not Path(p).is_absolute() else p
        for p in config.test_paths
    ]
    resolved_fixture_paths = [
        str((project_root / p).resolve()) if not Path(p).is_absolute() else p
        for p in config.fixture_paths
    ]

    # Create updated config
    return BabelTestConfig(
        version=config.version,
        adapters=AdaptersConfig(
            python=PythonAdapterConfig(
                source_paths=resolved_source_paths,
                factories=factories_path,
                instance_lifecycle=python_config.instance_lifecycle,
                capture_output=python_config.capture_output,
                timeout_ms=python_config.timeout_ms,
                debug_mode=python_config.debug_mode,
            )
        ),
        test_paths=resolved_test_paths,
        fixture_paths=resolved_fixture_paths,
    )
