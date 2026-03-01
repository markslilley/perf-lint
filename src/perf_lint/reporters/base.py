"""Base reporter abstract class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from perf_lint.engine import LintResult


class BaseReporter(ABC):
    """Abstract base class for all output reporters."""

    @abstractmethod
    def report(self, result: LintResult, output_path: Path | None = None, **kwargs: object) -> str:
        """Generate a report string and optionally write to a file.

        Subclasses may accept additional keyword arguments (e.g. TextReporter
        accepts fixed_by_file and dry_run_diffs). Callers should pass only
        arguments that the concrete reporter understands.

        Returns the report as a string.
        """
        ...

    def _write_output(self, content: str, output_path: Path | None) -> None:
        """Write content to a file if output_path is specified."""
        if output_path is not None:
            output_path.write_text(content, encoding="utf-8")
