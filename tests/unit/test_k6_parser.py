"""Tests for K6 parser."""

from __future__ import annotations

from pathlib import Path

from perf_lint.ir.models import Framework
from perf_lint.parsers.k6 import K6Parser


class TestK6Parser:
    def setup_method(self) -> None:
        self.parser = K6Parser()

    def test_framework(self) -> None:
        assert self.parser.framework == Framework.K6

    def test_supported_extensions(self) -> None:
        assert ".js" in self.parser.supported_extensions
        assert ".ts" in self.parser.supported_extensions

    def test_can_parse_k6_file(self, k6_fixtures_dir: Path) -> None:
        assert self.parser.can_parse(k6_fixtures_dir / "good_test.js")

    def test_cannot_parse_jmx_file(self, jmeter_fixtures_dir: Path) -> None:
        assert not self.parser.can_parse(jmeter_fixtures_dir / "good.jmx")

    def test_parse_good_script(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "good_test.js")
        assert ir.framework == Framework.K6
        assert ir.parsed_data["has_sleep"] is True
        assert ir.parsed_data["has_check"] is True
        assert ir.parsed_data["has_thresholds"] is True
        assert ir.parsed_data["has_error_handling"] is True

    def test_parse_missing_sleep(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "missing_sleep.js")
        assert ir.parsed_data["has_sleep"] is False

    def test_parse_missing_checks(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "missing_checks.js")
        assert ir.parsed_data["has_check"] is False

    def test_parse_http_calls(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "good_test.js")
        assert len(ir.parsed_data["http_calls"]) >= 1

    def test_parse_detects_hardcoded_ip(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "hardcoded_ip.js")
        calls = ir.parsed_data["http_calls"]
        assert any(c["is_hardcoded_ip"] for c in calls)

    def test_parse_stages(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "good_test.js")
        stages = ir.parsed_data["stages"]
        assert len(stages) >= 1

    def test_parse_aggressive_stages(self, k6_fixtures_dir: Path) -> None:
        ir = self.parser.parse(k6_fixtures_dir / "aggressive_stages.js")
        stages = ir.parsed_data["stages"]
        assert stages[0]["target"] == 500
        assert stages[0]["duration_secs"] == 5
