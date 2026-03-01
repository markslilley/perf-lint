"""Machine-readable JSON reporter."""

from __future__ import annotations

import json
from pathlib import Path

from perf_lint.engine import LintResult
from perf_lint.reporters.base import BaseReporter


class JsonReporter(BaseReporter):
    """Produces machine-readable JSON output."""

    def report(self, result: LintResult, output_path: Path | None = None, **kwargs: object) -> str:
        data = result.to_dict()
        output = json.dumps(data, indent=2, default=str)
        self._write_output(output, output_path)
        return output
