"""Integration tests for the full lint pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest

from perf_lint.config.schema import PerfLintConfig, RuleConfig
from perf_lint.engine import LintEngine
from perf_lint.ir.models import Severity


class TestFullPipeline:
    def test_good_k6_script_produces_no_violations(self, k6_fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths([k6_fixtures_dir / "good_test.js"])
        assert result.total_violations == 0
        assert result.error_count == 0

    def test_bad_k6_script_produces_violations(self, k6_fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths([k6_fixtures_dir / "missing_sleep.js"])
        assert result.total_violations > 0

    def test_good_jmeter_script_produces_no_violations(
        self, jmeter_fixtures_dir: Path
    ) -> None:
        engine = LintEngine()
        result = engine.lint_paths([jmeter_fixtures_dir / "good.jmx"])
        assert result.total_violations == 0

    def test_bad_jmeter_rampup_produces_violations(self, jmeter_fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths([jmeter_fixtures_dir / "bad_rampup.jmx"])
        # JMX004 (ramp-up) is a Pro rule; free tier still flags other issues
        assert result.total_violations >= 1

    def test_good_gatling_script_produces_no_violations(
        self, gatling_fixtures_dir: Path
    ) -> None:
        engine = LintEngine()
        result = engine.lint_paths([gatling_fixtures_dir / "GoodSimulation.scala"])
        assert result.total_violations == 0

    def test_bad_gatling_produces_violations(self, gatling_fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths([gatling_fixtures_dir / "MissingPauseSimulation.scala"])
        assert result.total_violations > 0

    def test_lint_directory(self, fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths([fixtures_dir])
        # Should find files in all sub-directories
        assert len(result.file_results) > 0

    def test_unknown_files_skipped(self, tmp_path: Path) -> None:
        txt_file = tmp_path / "readme.txt"
        txt_file.write_text("not a test script")
        engine = LintEngine()
        result = engine.lint_paths([txt_file])
        assert len(result.file_results) == 0

    def test_config_disables_rule(self, k6_fixtures_dir: Path) -> None:
        config = PerfLintConfig(rules={"K6001": RuleConfig(enabled=False)})
        engine = LintEngine(config=config)
        result = engine.lint_paths([k6_fixtures_dir / "missing_sleep.js"])
        rule_ids = {
            v.rule_id for fr in result.file_results for v in fr.violations
        }
        assert "K6001" not in rule_ids

    def test_config_escalates_severity(self, k6_fixtures_dir: Path) -> None:
        config = PerfLintConfig(rules={"K6001": RuleConfig(severity="error")})
        engine = LintEngine(config=config)
        result = engine.lint_paths([k6_fixtures_dir / "missing_sleep.js"])
        for fr in result.file_results:
            for v in fr.violations:
                if v.rule_id == "K6001":
                    assert v.severity == Severity.ERROR

    def test_ignored_rules_excluded(self, jmeter_fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths(
            [jmeter_fixtures_dir / "missing_managers.jmx"],
            ignored_rules=["JMX001", "JMX002"],
        )
        rule_ids = {
            v.rule_id for fr in result.file_results for v in fr.violations
        }
        assert "JMX001" not in rule_ids
        assert "JMX002" not in rule_ids

    def test_result_to_dict_structure(self, k6_fixtures_dir: Path) -> None:
        engine = LintEngine()
        result = engine.lint_paths([k6_fixtures_dir / "missing_sleep.js"])
        d = result.to_dict()
        assert "files" in d
        assert "summary" in d
        assert "total_violations" in d["summary"]
        assert "errors" in d["summary"]
        assert "warnings" in d["summary"]
