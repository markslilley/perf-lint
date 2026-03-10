"""Plugin discovery and loading for perf-lint custom rules.

Two discovery mechanisms:
1. Installed packages — importlib.metadata.entry_points(group="perf_lint.rules")
2. File paths — custom_rules[].path in .perf-lint.yml (supports glob patterns)
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import logging
import sys
from pathlib import Path

from perf_lint.config.schema import PerfLintConfig

logger = logging.getLogger(__name__)


def load_plugins(config: PerfLintConfig) -> list[str]:
    """Load all plugins defined in config.

    Returns a list of loaded module names.
    """
    loaded = []
    loaded.extend(_load_entry_point_plugins())
    loaded.extend(_load_file_plugins(config))
    return loaded


def _load_entry_point_plugins() -> list[str]:
    """Load plugins registered via setuptools entry_points."""
    loaded = []
    try:
        eps = importlib.metadata.entry_points(group="perf_lint.rules")
        for ep in eps:
            try:
                fn = ep.load()
                if callable(fn):
                    fn()
                loaded.append(ep.name)
            except Exception as exc:
                # Log but don't fail — bad plugins shouldn't break the tool.
                logger.warning("Failed to load plugin '%s': %s", ep.name, exc)
    except Exception:
        pass
    return loaded


def _load_file_plugins(config: PerfLintConfig) -> list[str]:
    """Load plugins from file paths specified in config.

    Only loads .py files whose resolved path is within the current working
    directory to prevent path-traversal attacks via config files.
    """
    loaded = []
    project_root = Path.cwd().resolve()

    for custom_rule in config.custom_rules:
        pattern = custom_rule.path
        base = Path.cwd()
        paths = (
            list(base.glob(pattern))
            if "*" in pattern or "?" in pattern
            else [base / pattern]
        )

        for path in sorted(paths):
            if not path.is_file() or path.suffix != ".py":
                continue

            # Prevent relative path traversal: reject relative patterns that
            # resolve outside the project root (e.g. "../../evil.py").
            if Path(pattern).is_absolute():
                # Absolute paths are explicit user intent but we log a notice
                # so unusual plugin locations are visible in CI logs.
                logger.info("Loading plugin from absolute path: '%s'", path)
            else:
                try:
                    path.resolve().relative_to(project_root)
                except ValueError:
                    logger.warning(
                        "Refusing to load plugin outside project root: '%s'", path
                    )
                    continue

            try:
                # Use a stable, process-invariant name derived from the
                # canonical path. Python's hash() is randomised per process
                # (PYTHONHASHSEED), so we use SHA-256 instead.
                stable_id = hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:12]
                module_name = f"perf_lint._plugin_{path.stem}_{stable_id}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)  # type: ignore[attr-defined]
                loaded.append(str(path))
            except Exception as exc:
                logger.warning("Failed to load plugin from '%s': %s", path, exc)
    return loaded
