"""Tests for IR models."""

from __future__ import annotations

from pathlib import Path

import pytest

from perf_lint.ir.models import Framework, Location, ScriptIR, Severity, Violation


class TestSeverity:
    def test_ordering_error_gt_warning(self) -> None:
        assert Severity.ERROR > Severity.WARNING

    def test_ordering_warning_gt_info(self) -> None:
        assert Severity.WARNING > Severity.INFO

    def test_ordering_error_gt_info(self) -> None:
        assert Severity.ERROR > Severity.INFO

    def test_equality(self) -> None:
        assert Severity.ERROR == Severity.ERROR

    def test_ge(self) -> None:
        assert Severity.ERROR >= Severity.WARNING
        assert Severity.WARNING >= Severity.WARNING

    def test_le(self) -> None:
        assert Severity.INFO <= Severity.WARNING
        assert Severity.WARNING <= Severity.WARNING


class TestLocation:
    def test_str_with_line(self) -> None:
        loc = Location(line=42)
        assert "42" in str(loc)

    def test_str_with_line_and_column(self) -> None:
        loc = Location(line=10, column=5)
        assert "10" in str(loc)
        assert "5" in str(loc)

    def test_str_with_element_path(self) -> None:
        loc = Location(element_path="/jmeterTestPlan//ThreadGroup")
        assert "/jmeterTestPlan" in str(loc)

    def test_str_unknown(self) -> None:
        loc = Location()
        assert "unknown" in str(loc)

    def test_frozen(self) -> None:
        loc = Location(line=1)
        with pytest.raises(AttributeError):
            loc.line = 2  # type: ignore


class TestViolation:
    def test_to_dict(self) -> None:
        v = Violation(
            rule_id="JMX001",
            severity=Severity.WARNING,
            message="Test message",
            location=Location(line=5),
            suggestion="Fix it",
        )
        d = v.to_dict()
        assert d["rule_id"] == "JMX001"
        assert d["severity"] == "warning"
        assert d["message"] == "Test message"
        assert d["suggestion"] == "Fix it"
        assert d["location"]["line"] == 5

    def test_to_dict_no_optional_fields(self) -> None:
        v = Violation(
            rule_id="K6001",
            severity=Severity.ERROR,
            message="Msg",
            location=Location(),
        )
        d = v.to_dict()
        assert d["fix_example"] is None
        assert d["suggestion"] is None

    def test_violation_is_frozen(self) -> None:
        """Violation is a frozen dataclass — mutations raise an error."""
        v = Violation(
            rule_id="K6001",
            severity=Severity.WARNING,
            message="No sleep",
            location=Location(line=1),
        )
        with pytest.raises(AttributeError):
            v.rule_id = "K6002"  # type: ignore

    def test_dataclasses_replace_severity(self) -> None:
        """dataclasses.replace() is the correct way to create modified copies."""
        import dataclasses
        v = Violation(
            rule_id="K6001",
            severity=Severity.WARNING,
            message="No sleep",
            location=Location(line=1),
        )
        v2 = dataclasses.replace(v, severity=Severity.ERROR)
        assert v2.severity == Severity.ERROR
        assert v2.rule_id == "K6001"  # unchanged


class TestScriptIR:
    def test_default_empty_parsed_data(self) -> None:
        ir = ScriptIR(
            framework=Framework.GATLING,
            source_path=Path("test.scala"),
            raw_content="",
        )
        assert ir.parsed_data == {}

    def test_raw_content_is_mutable(self) -> None:
        """raw_content is intentionally mutable for the auto-fixer."""
        ir = ScriptIR(
            framework=Framework.K6,
            source_path=Path("test.js"),
            raw_content="original",
        )
        ir.raw_content = "modified"
        assert ir.raw_content == "modified"
