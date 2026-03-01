"""Lint engine — orchestrates parsing, rule evaluation, and result collection."""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from perf_lint.config.schema import PerfLintConfig, RuleConfig
from perf_lint.ir.models import Framework, ScriptIR, Severity, Violation
from perf_lint.parsers.base import BaseParser, detect_parser
from perf_lint.parsers.gatling import GatlingParser
from perf_lint.parsers.jmeter import JMeterParser
from perf_lint.parsers.k6 import K6Parser
from perf_lint.rules.base import BaseRule, RuleRegistry

# Import rule modules to trigger registration
import perf_lint.rules.jmeter  # noqa: F401
import perf_lint.rules.k6  # noqa: F401
import perf_lint.rules.gatling  # noqa: F401


@dataclass
class FileResult:
    """Lint results for a single file."""

    path: Path
    framework: Framework
    violations: list[Violation] = field(default_factory=list)
    parse_error: str | None = None
    quality_score: int = field(default=100)
    quality_grade: str = field(default="A")

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == Severity.INFO)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "framework": self.framework.value,
            "parse_error": self.parse_error,
            "violations": [v.to_dict() for v in self.violations],
            "quality_score": self.quality_score,
            "quality_grade": self.quality_grade,
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "infos": self.info_count,
                "total": len(self.violations),
            },
        }


@dataclass
class LintResult:
    """Aggregated lint results across all files."""

    file_results: list[FileResult] = field(default_factory=list)
    overall_score: int = field(default=100)
    overall_grade: str = field(default="A")

    @property
    def total_violations(self) -> int:
        return sum(len(r.violations) for r in self.file_results)

    @property
    def error_count(self) -> int:
        return sum(r.error_count for r in self.file_results)

    @property
    def warning_count(self) -> int:
        return sum(r.warning_count for r in self.file_results)

    @property
    def info_count(self) -> int:
        return sum(r.info_count for r in self.file_results)

    @property
    def files_with_violations(self) -> int:
        """Number of files that have violations or parse errors."""
        return sum(1 for r in self.file_results if r.violations or r.parse_error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": [r.to_dict() for r in self.file_results],
            "overall_score": self.overall_score,
            "overall_grade": self.overall_grade,
            "summary": {
                "files_checked": len(self.file_results),
                "files_with_violations": self.files_with_violations,
                "total_violations": self.total_violations,
                "errors": self.error_count,
                "warnings": self.warning_count,
                "infos": self.info_count,
            },
        }


def _score_to_grade(score: int) -> str:
    """Map a 0-100 quality score to an A-F letter grade."""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


class LintEngine:
    """Orchestrates parsing, rule evaluation, and result collection.

    Args:
        config: Lint configuration. Defaults to PerfLintConfig.default().
        parsers: Override the list of parsers. Defaults to the three built-in
            parsers (JMeter, K6, Gatling). Inject custom parsers for testing.
    """

    def __init__(
        self,
        config: PerfLintConfig | None = None,
        parsers: list[BaseParser] | None = None,
        rules: dict[str, type[BaseRule]] | None = None,
    ) -> None:
        self.config = config or PerfLintConfig.default()
        self._parsers: list[BaseParser] = parsers if parsers is not None else [
            JMeterParser(),
            K6Parser(),
            GatlingParser(),
        ]
        # Allow injecting a custom rule set (useful for testing and plugins)
        self._rule_classes: dict[str, type[BaseRule]] = (
            rules if rules is not None else RuleRegistry.get_all()
        )
        # Instantiate rule classes once and cache them — rules are stateless.
        self._rule_instances: dict[str, BaseRule] = {
            rule_id: cls() for rule_id, cls in self._rule_classes.items()
        }

    def lint_paths(
        self,
        paths: list[Path],
        severity_override: str | None = None,
        ignored_rules: list[str] | None = None,
    ) -> LintResult:
        """Lint a list of paths (files or directories)."""
        files = self._collect_files(paths)
        results = []
        for file_path in files:
            if self._is_ignored(file_path):
                continue
            result = self.lint_file(
                file_path,
                severity_override=severity_override,
                ignored_rules=ignored_rules,
            )
            if result is not None:
                results.append(result)

        lint_result = LintResult(file_results=results)
        self._compute_overall_score(lint_result)
        return lint_result

    def lint_file(
        self,
        path: Path,
        severity_override: str | None = None,
        ignored_rules: list[str] | None = None,
    ) -> FileResult | None:
        """Lint a single file. Returns None if no parser supports the file."""
        parser = detect_parser(path, self._parsers)
        if parser is None:
            return None

        try:
            ir = parser.parse(path)
        except Exception as exc:
            fr = FileResult(
                path=path,
                framework=parser.framework,
                parse_error=str(exc),
            )
            fr.quality_score = 0
            fr.quality_grade = "F"
            return fr

        violations = self._run_rules(ir, severity_override, ignored_rules or [])
        file_result = FileResult(
            path=path,
            framework=ir.framework,
            violations=violations,
        )
        self._compute_score(file_result)
        return file_result

    def _run_rules(
        self,
        ir: ScriptIR,
        severity_override: str | None,
        ignored_rules: list[str],
    ) -> list[Violation]:
        """Run all applicable rules against an IR."""
        violations: list[Violation] = []

        for rule_id, rule_class in self._rule_classes.items():
            if ir.framework not in rule_class.frameworks:
                continue

            rule_cfg: RuleConfig = self.config.rules.get(rule_id, RuleConfig())
            if not rule_cfg.enabled:
                continue
            if rule_id in ignored_rules:
                continue

            rule = self._rule_instances[rule_id]
            found = rule.check(ir)

            for violation in found:
                # Apply config severity override using dataclasses.replace()
                # so that any future Violation fields are not silently dropped.
                if rule_cfg.severity:
                    violation = dataclasses.replace(
                        violation, severity=Severity(rule_cfg.severity)
                    )
                violations.append(violation)

        return violations

    @staticmethod
    def _score_to_grade(score: int) -> str:
        """Delegate to module-level function (kept for test compatibility)."""
        return _score_to_grade(score)

    def _compute_score(self, file_result: FileResult) -> None:
        if file_result.parse_error:
            file_result.quality_score = 0
            file_result.quality_grade = "F"
            return
        score = max(
            0,
            100
            - file_result.error_count * 15
            - file_result.warning_count * 5
            - file_result.info_count * 1,
        )
        file_result.quality_score = score
        file_result.quality_grade = _score_to_grade(score)

    def _compute_overall_score(self, lint_result: LintResult) -> None:
        if not lint_result.file_results:
            lint_result.overall_score = 100
            lint_result.overall_grade = "A"
            return
        # Use round() for correct half-up behaviour instead of floor division.
        avg = round(
            sum(r.quality_score for r in lint_result.file_results)
            / len(lint_result.file_results)
        )
        lint_result.overall_score = avg
        lint_result.overall_grade = _score_to_grade(avg)

    def _collect_files(self, paths: list[Path]) -> list[Path]:
        """Expand directories to files, preserving explicit file paths.

        Uses os.walk with followlinks=False to prevent infinite loops on
        symlink cycles.
        """
        files: list[Path] = []
        for path in paths:
            if path.is_file():
                files.append(path)
            elif path.is_dir():
                for dirpath, _dirnames, filenames in sorted(
                    os.walk(path, followlinks=False)
                ):
                    for filename in sorted(filenames):
                        files.append(Path(dirpath) / filename)
        return files

    def _is_ignored(self, path: Path) -> bool:
        """Return True if the path matches any ignore_paths pattern.

        Uses Path.match() which supports the ** glob syntax documented in the
        generated config (fnmatch does not handle ** correctly).
        """
        for pattern in self.config.ignore_paths:
            if path.match(pattern):
                return True
        return False
