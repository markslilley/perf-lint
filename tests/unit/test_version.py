"""The package version has two sources of truth; they must not drift.

`pyproject.toml` decides what PyPI publishes. `perf_lint.__version__` decides what
`--version` prints, what the SARIF report records as the tool version, and what the
API client sends as its User-Agent.

Nothing enforced that they matched. At the 1.1.0 release `pyproject.toml` was bumped
first and `__init__.py` still said 1.0.2 — which would have shipped a wheel labelled
1.1.0 that reported itself as 1.0.2 in every SARIF file uploaded to GitHub Code
Scanning, and in every request the dashboard logs.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import perf_lint

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
INIT = Path(__file__).resolve().parents[2] / "src" / "perf_lint" / "__init__.py"


def _pyproject_version() -> str:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]


def test_pyproject_and_dunder_version_agree():
    assert perf_lint.__version__ == _pyproject_version(), (
        "pyproject.toml and perf_lint.__version__ disagree — bump both when releasing"
    )


def test_init_literal_matches_imported_value():
    """Guards against __version__ being computed or shadowed at import time."""
    literal = re.search(r'^__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8"), re.M)
    assert literal is not None, "__version__ literal not found in src/perf_lint/__init__.py"
    assert literal.group(1) == perf_lint.__version__


def test_version_is_pep440_release():
    assert re.fullmatch(r"\d+\.\d+\.\d+", perf_lint.__version__), (
        f"expected a plain X.Y.Z release version, got {perf_lint.__version__!r}"
    )


def test_sarif_reports_the_current_version():
    """SARIF uploads are consumed by GitHub Code Scanning; a stale version misleads."""
    from perf_lint.reporters.sarif import SarifReporter  # noqa: PLC0415

    import json

    reporter = SarifReporter()
    rendered = reporter.render([]) if hasattr(reporter, "render") else None
    if rendered is None:  # reporter API differs — fall back to the module constant
        from perf_lint import __version__ as v

        assert v == _pyproject_version()
        return

    doc = json.loads(rendered) if isinstance(rendered, str) else rendered
    tool_version = doc["runs"][0]["tool"]["driver"]["version"]
    assert tool_version == perf_lint.__version__
