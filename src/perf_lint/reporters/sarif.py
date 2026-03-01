"""SARIF 2.1.0 reporter for GitHub/GitLab integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from perf_lint import __version__
from perf_lint.engine import LintResult
from perf_lint.ir.models import Severity
from perf_lint.reporters.base import BaseReporter
from perf_lint.rules.base import RuleRegistry

_SARIF_LEVEL = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "note",
}


class SarifReporter(BaseReporter):
    """Produces SARIF 2.1.0 output for GitHub Code Scanning and GitLab SAST."""

    def report(self, result: LintResult, output_path: Path | None = None, **kwargs: object) -> str:
        sarif = self._build_sarif(result)
        output = json.dumps(sarif, indent=2, default=str)
        self._write_output(output, output_path)
        return output

    def _build_sarif(self, result: LintResult) -> dict[str, Any]:
        rules = self._build_rules()
        results = self._build_results(result)

        return {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "perf-lint",
                            "version": __version__,
                            "informationUri": "https://github.com/perf-lint/perf-lint",
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }

    def _build_rules(self) -> list[dict[str, Any]]:
        """Build SARIF rule descriptors from registered rules."""
        sarif_rules = []
        for rule_class in RuleRegistry.get_all().values():
            sarif_rules.append({
                "id": rule_class.rule_id,
                "name": rule_class.name,
                "shortDescription": {"text": rule_class.description},
                "defaultConfiguration": {
                    "level": _SARIF_LEVEL.get(rule_class.severity, "warning")
                },
                "properties": {
                    "tags": rule_class.tags,
                    "frameworks": [f.value for f in rule_class.frameworks],
                },
            })
        return sarif_rules

    def _build_results(self, result: LintResult) -> list[dict[str, Any]]:
        """Build SARIF result entries from all violations."""
        sarif_results = []
        for file_result in result.file_results:
            for violation in file_result.violations:
                sarif_result: dict[str, Any] = {
                    "ruleId": violation.rule_id,
                    "level": _SARIF_LEVEL.get(violation.severity, "warning"),
                    "message": {"text": violation.message},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {
                                    "uri": str(file_result.path).replace("\\", "/"),
                                }
                            }
                        }
                    ],
                }

                loc = violation.location
                if loc and loc.line is not None:
                    region = {"startLine": loc.line}
                    if loc.column is not None:
                        region["startColumn"] = loc.column
                    sarif_result["locations"][0]["physicalLocation"]["region"] = region

                # Note: SARIF 2.1.0 fixes require artifactChanges with character-level
                # replacements which we cannot generate without AST position data.
                # Instead, surface the suggestion in the message text so it appears
                # in GitHub Code Scanning / GitLab SAST annotation UI.
                if violation.suggestion:
                    sarif_result["message"]["text"] += (
                        f" Suggestion: {violation.suggestion}"
                    )

                sarif_results.append(sarif_result)

        return sarif_results
