"""Tests for JMeter parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from perf_lint.ir.models import Framework
from perf_lint.parsers.jmeter import JMeterParser


class TestJMeterParser:
    def setup_method(self) -> None:
        self.parser = JMeterParser()

    def test_framework(self) -> None:
        assert self.parser.framework == Framework.JMETER

    def test_supported_extensions(self) -> None:
        assert ".jmx" in self.parser.supported_extensions

    def test_can_parse_jmx_file(self, jmeter_fixtures_dir: Path) -> None:
        assert self.parser.can_parse(jmeter_fixtures_dir / "good.jmx")

    def test_cannot_parse_js_file(self, k6_fixtures_dir: Path) -> None:
        assert not self.parser.can_parse(k6_fixtures_dir / "good_test.js")

    def test_parse_good_script(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "good.jmx")
        assert ir.framework == Framework.JMETER
        assert ir.parsed_data["sampler_count"] >= 1
        assert ir.parsed_data["assertion_count"] >= 1
        assert ir.parsed_data["csv_data_set_count"] >= 1
        assert ir.parsed_data["uses_variables"] is True

    def test_parse_detects_cache_manager(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "good.jmx")
        assert any("CacheManager" in el for el in ir.parsed_data["config_elements"])

    def test_parse_detects_cookie_manager(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "good.jmx")
        assert any("CookieManager" in el for el in ir.parsed_data["config_elements"])

    def test_parse_thread_groups(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "good.jmx")
        tgs = ir.parsed_data["thread_groups"]
        assert len(tgs) >= 1
        assert tgs[0]["num_threads"] == 10
        assert tgs[0]["ramp_time"] == 60

    def test_parse_bad_rampup_values(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "bad_rampup.jmx")
        tgs = ir.parsed_data["thread_groups"]
        assert tgs[0]["num_threads"] == 200
        assert tgs[0]["ramp_time"] == 5

    def test_parse_detects_hardcoded_ip(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "hardcoded_ip.jmx")
        samplers = ir.parsed_data["samplers"]
        assert any(s["is_hardcoded_ip"] for s in samplers)

    def test_parse_good_script_no_hardcoded_ip(self, jmeter_fixtures_dir: Path) -> None:
        ir = self.parser.parse(jmeter_fixtures_dir / "good.jmx")
        samplers = ir.parsed_data["samplers"]
        assert not any(s["is_hardcoded_ip"] for s in samplers)
