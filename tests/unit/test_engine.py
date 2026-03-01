"""Unit tests for the scoring formula in LintEngine."""

from __future__ import annotations

from perf_lint.engine import LintEngine, FileResult, LintResult
from pathlib import Path
from perf_lint.ir.models import Framework, Severity
from perf_lint.rules.base import BaseRule, RuleRegistry


class TestScoreToGrade:
    def test_100_is_A(self) -> None:
        assert LintEngine._score_to_grade(100) == "A"

    def test_90_is_A(self) -> None:
        assert LintEngine._score_to_grade(90) == "A"

    def test_89_is_B(self) -> None:
        assert LintEngine._score_to_grade(89) == "B"

    def test_75_is_B(self) -> None:
        assert LintEngine._score_to_grade(75) == "B"

    def test_74_is_C(self) -> None:
        assert LintEngine._score_to_grade(74) == "C"

    def test_60_is_C(self) -> None:
        assert LintEngine._score_to_grade(60) == "C"

    def test_59_is_D(self) -> None:
        assert LintEngine._score_to_grade(59) == "D"

    def test_40_is_D(self) -> None:
        assert LintEngine._score_to_grade(40) == "D"

    def test_39_is_F(self) -> None:
        assert LintEngine._score_to_grade(39) == "F"

    def test_0_is_F(self) -> None:
        assert LintEngine._score_to_grade(0) == "F"


class TestComputeScore:
    def _make_file_result(
        self, errors: int = 0, warnings: int = 0, infos: int = 0
    ) -> FileResult:
        from perf_lint.ir.models import Location, Violation

        violations = []
        for _ in range(errors):
            violations.append(
                Violation("X001", Severity.ERROR, "err", Location(line=1))
            )
        for _ in range(warnings):
            violations.append(
                Violation("X002", Severity.WARNING, "warn", Location(line=1))
            )
        for _ in range(infos):
            violations.append(
                Violation("X003", Severity.INFO, "info", Location(line=1))
            )
        return FileResult(path=Path("test.js"), framework=Framework.K6, violations=violations)

    def test_clean_file_scores_100(self) -> None:
        engine = LintEngine()
        fr = self._make_file_result()
        engine._compute_score(fr)
        assert fr.quality_score == 100
        assert fr.quality_grade == "A"

    def test_two_errors_three_warnings(self) -> None:
        # 100 - 2*15 - 3*5 = 100 - 30 - 15 = 55
        engine = LintEngine()
        fr = self._make_file_result(errors=2, warnings=3)
        engine._compute_score(fr)
        assert fr.quality_score == 55
        assert fr.quality_grade == "D"

    def test_score_clamped_at_zero(self) -> None:
        engine = LintEngine()
        fr = self._make_file_result(errors=10)
        engine._compute_score(fr)
        assert fr.quality_score == 0

    def test_parse_error_scores_zero_F(self) -> None:
        engine = LintEngine()
        fr = FileResult(path=Path("bad.js"), framework=Framework.K6, parse_error="syntax error")
        engine._compute_score(fr)
        assert fr.quality_score == 0
        assert fr.quality_grade == "F"

    def test_only_infos_small_penalty(self) -> None:
        engine = LintEngine()
        fr = self._make_file_result(infos=5)
        engine._compute_score(fr)
        assert fr.quality_score == 95  # 100 - 5*1


class TestComputeOverallScore:
    def _file_result_with_score(self, score: int) -> FileResult:
        fr = FileResult(path=Path("f.js"), framework=Framework.K6)
        fr.quality_score = score
        fr.quality_grade = LintEngine._score_to_grade(score)
        return fr

    def test_no_files_gives_100_A(self) -> None:
        engine = LintEngine()
        lr = LintResult(file_results=[])
        engine._compute_overall_score(lr)
        assert lr.overall_score == 100
        assert lr.overall_grade == "A"

    def test_average_of_scores(self) -> None:
        engine = LintEngine()
        lr = LintResult(
            file_results=[
                self._file_result_with_score(80),
                self._file_result_with_score(60),
            ]
        )
        engine._compute_overall_score(lr)
        assert lr.overall_score == 70  # round((80+60)/2) == 70
        assert lr.overall_grade == "C"

    def test_average_rounds_half_up(self) -> None:
        """Verify round() is used instead of floor division."""
        engine = LintEngine()
        lr = LintResult(
            file_results=[
                self._file_result_with_score(85),
                self._file_result_with_score(86),
            ]
        )
        engine._compute_overall_score(lr)
        # round(171/2) = round(85.5) = 86 (banker's rounding in Python rounds to even,
        # but 85.5→86 since 86 is even, so both floor and round give same here).
        # Use a clearer case: 75 + 76 = 151 → round(75.5) = 76 ≥ floor = 75.
        lr2 = LintResult(
            file_results=[
                self._file_result_with_score(75),
                self._file_result_with_score(76),
            ]
        )
        engine._compute_overall_score(lr2)
        assert lr2.overall_score == round((75 + 76) / 2)


class TestFileResultToDict:
    def test_to_dict_includes_quality_fields(self) -> None:
        fr = FileResult(path=Path("x.js"), framework=Framework.K6, quality_score=72, quality_grade="C")
        d = fr.to_dict()
        assert d["quality_score"] == 72
        assert d["quality_grade"] == "C"


class TestLintResultToDict:
    def test_to_dict_includes_overall_score(self) -> None:
        lr = LintResult(file_results=[], overall_score=88, overall_grade="B")
        d = lr.to_dict()
        assert d["overall_score"] == 88
        assert d["overall_grade"] == "B"


class TestInjectableRules:
    def test_engine_accepts_custom_rules(self) -> None:
        """LintEngine should use injected rules instead of global registry."""
        from perf_lint.ir.models import Violation, Location

        class AlwaysFiresRule(BaseRule):
            rule_id = "TEST001"
            name = "AlwaysFires"
            description = "Test rule that always fires"
            severity = Severity.WARNING
            frameworks = [Framework.K6]

            def check(self, ir):
                return [Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message="Always fires",
                    location=Location(line=1),
                )]

        # LintEngine supports the rules= parameter
        engine = LintEngine(rules={"TEST001": AlwaysFiresRule})
        assert engine is not None
        # Verify the engine only has our custom rule
        assert "TEST001" in engine._rule_classes
        # Verify no other rules are present
        assert len(engine._rule_classes) == 1

    def test_engine_with_empty_rule_dict_produces_no_violations(
        self, k6_fixtures_dir: Path
    ) -> None:
        """Engine with no rules should produce no violations."""
        engine = LintEngine(rules={})
        result = engine.lint_file(k6_fixtures_dir / "missing_sleep.js")
        assert result is not None
        assert len(result.violations) == 0

    def test_engine_with_injected_rule_fires_on_file(
        self, k6_fixtures_dir: Path
    ) -> None:
        """Engine with a custom rule should produce violations from that rule."""
        from perf_lint.ir.models import Violation, Location

        class AlwaysFiresRule(BaseRule):
            rule_id = "TEST002"
            name = "AlwaysFires"
            description = "Test rule that always fires for K6"
            severity = Severity.WARNING
            frameworks = [Framework.K6]

            def check(self, ir):
                return [Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message="Always fires",
                    location=Location(line=1),
                )]

        engine = LintEngine(rules={"TEST002": AlwaysFiresRule})
        result = engine.lint_file(k6_fixtures_dir / "missing_sleep.js")
        assert result is not None
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "TEST002"
