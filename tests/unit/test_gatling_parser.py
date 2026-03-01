"""Tests for Gatling parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from perf_lint.ir.models import Framework
from perf_lint.parsers.gatling import GatlingParser


class TestGatlingParser:
    def setup_method(self) -> None:
        self.parser = GatlingParser()

    def test_framework(self) -> None:
        assert self.parser.framework == Framework.GATLING

    def test_supported_extensions(self) -> None:
        assert ".scala" in self.parser.supported_extensions
        assert ".kt" in self.parser.supported_extensions

    def test_can_parse_gatling_file(self, gatling_fixtures_dir: Path) -> None:
        assert self.parser.can_parse(gatling_fixtures_dir / "GoodSimulation.scala")

    def test_cannot_parse_jmx_file(self, jmeter_fixtures_dir: Path) -> None:
        assert not self.parser.can_parse(jmeter_fixtures_dir / "good.jmx")

    def test_parse_good_script(self, gatling_fixtures_dir: Path) -> None:
        ir = self.parser.parse(gatling_fixtures_dir / "GoodSimulation.scala")
        assert ir.framework == Framework.GATLING
        assert ir.parsed_data["has_assertions"] is True
        assert ir.parsed_data["has_pause"] is True
        assert ir.parsed_data["has_feeder"] is True
        assert ir.parsed_data["base_url_is_ip"] is False

    def test_parse_detects_missing_pause(self, gatling_fixtures_dir: Path) -> None:
        ir = self.parser.parse(gatling_fixtures_dir / "MissingPauseSimulation.scala")
        assert ir.parsed_data["has_pause"] is False
        assert ir.parsed_data["exec_count"] >= 1

    def test_parse_detects_missing_assertions(self, gatling_fixtures_dir: Path) -> None:
        ir = self.parser.parse(gatling_fixtures_dir / "MissingAssertionsSimulation.scala")
        assert ir.parsed_data["has_assertions"] is False

    def test_parse_detects_hardcoded_ip(self, gatling_fixtures_dir: Path) -> None:
        ir = self.parser.parse(gatling_fixtures_dir / "HardcodedIPSimulation.scala")
        assert ir.parsed_data["base_url_is_ip"] is True

    def test_parse_detects_aggressive_rampup(self, gatling_fixtures_dir: Path) -> None:
        ir = self.parser.parse(gatling_fixtures_dir / "AggressiveRampupSimulation.scala")
        injections = ir.parsed_data["injections"]
        assert len(injections) >= 1
        # 1000 users in 5 seconds = 200 users/second
        ramp = next(i for i in injections if i["type"] == "ramp")
        assert ramp["users"] == 1000
        assert ramp["duration_secs"] == 5
