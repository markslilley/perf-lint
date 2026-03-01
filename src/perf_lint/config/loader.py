"""Config file discovery and loading for perf-lint.

Searches upward from CWD for .perf-lint.yml / .perf-lint.yaml / .perf-lint.toml.
Validated with Pydantic v2.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

import yaml

from perf_lint.config.schema import PerfLintConfig

CONFIG_FILENAMES = (".perf-lint.yml", ".perf-lint.yaml", ".perf-lint.toml")


_MAX_WALK_LEVELS = 10  # Stop after this many directory levels to avoid slow network FS walks


def find_config_file(start_dir: Path | None = None) -> Path | None:
    """Walk upward from start_dir searching for a config file.

    Stops at the first of: a config file found, a VCS root (.git /
    pyproject.toml), or after _MAX_WALK_LEVELS levels. Returns None if none
    found.
    """
    current = (start_dir or Path.cwd()).resolve()

    for level, directory in enumerate([current, *current.parents]):
        if level >= _MAX_WALK_LEVELS:
            break

        for name in CONFIG_FILENAMES:
            candidate = directory / name
            if candidate.is_file():
                return candidate

        # Stop at VCS or project root — config is unlikely to live higher.
        if (directory / ".git").is_dir() or (
            directory / "pyproject.toml"
        ).is_file():
            break

    return None


def load_config(config_path: Path | None = None) -> PerfLintConfig:
    """Load and validate config from a file path.

    If config_path is None, searches upward from CWD. If still not found,
    returns the default configuration.
    """
    if config_path is None:
        config_path = find_config_file()

    if config_path is None:
        default = PerfLintConfig.default()
        _inject_env_vars(default)
        return default

    if not config_path.is_file():
        default = PerfLintConfig.default()
        _inject_env_vars(default)
        return default

    raw = _read_config_file(config_path)
    config = PerfLintConfig.model_validate(raw)
    _inject_env_vars(config)
    return config


def _inject_env_vars(config: PerfLintConfig) -> None:
    """Inject PERF_LINT_API_KEY and PERF_LINT_API_URL from environment if not set."""
    if not config.api_key:
        config.api_key = os.environ.get("PERF_LINT_API_KEY")
    if os.environ.get("PERF_LINT_API_URL"):
        config.api_url = os.environ["PERF_LINT_API_URL"]


def _read_config_file(path: Path) -> dict:
    """Read and parse a YAML or TOML config file."""
    content = path.read_text(encoding="utf-8")

    if path.suffix == ".toml":
        return tomllib.loads(content)

    # YAML (covers .yml and .yaml)
    data = yaml.safe_load(content)
    return data if data is not None else {}
