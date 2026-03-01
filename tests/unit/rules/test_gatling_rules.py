"""Tests for Gatling rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from perf_lint.ir.models import Severity
from perf_lint.parsers.gatling import GatlingParser
from perf_lint.rules.gatling.rules import (
    GAT001MissingPause,
    GAT005MissingFeeder,
    GAT011AssertionLacksThreshold,
    GAT013MissingHTTP2,
)


def parse(fixture: Path) -> object:
    return GatlingParser().parse(fixture)


class TestGAT001MissingPause:
    def test_triggers_when_no_pause(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "MissingPauseSimulation.scala")
        violations = GAT001MissingPause().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "GAT001"
        assert violations[0].severity == Severity.WARNING

    def test_passes_when_pause_present(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "GoodSimulation.scala")
        violations = GAT001MissingPause().check(ir)
        assert violations == []


class TestGAT005MissingFeeder:
    def test_triggers_when_no_feeder_multiple_execs(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "MissingPauseSimulation.scala")
        violations = GAT005MissingFeeder().check(ir)
        # MissingPauseSimulation has 3 exec() and no feeder
        assert len(violations) == 1
        assert violations[0].rule_id == "GAT005"
        assert violations[0].severity == Severity.INFO

    def test_passes_when_feeder_present(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "GoodSimulation.scala")
        violations = GAT005MissingFeeder().check(ir)
        assert violations == []


class TestGAT011AssertionLacksThreshold:
    def test_triggers_assertions_without_slo(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "AssertionNoSLOSimulation.scala")
        violations = GAT011AssertionLacksThreshold().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "GAT011"
        assert violations[0].severity == Severity.INFO

    def test_no_violation_with_response_time_assertion(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "GoodSimulation.scala")
        violations = GAT011AssertionLacksThreshold().check(ir)
        assert violations == []

    def test_no_violation_without_assertions(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "MissingAssertionsSimulation.scala")
        violations = GAT011AssertionLacksThreshold().check(ir)
        assert violations == []


class TestGAT013MissingHTTP2:
    def test_triggers_https_without_http2(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "HttpsNoHttp2Simulation.scala")
        violations = GAT013MissingHTTP2().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "GAT013"
        assert violations[0].severity == Severity.INFO

    def test_no_violation_with_http2(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "WithHttp2Simulation.scala")
        violations = GAT013MissingHTTP2().check(ir)
        assert violations == []

    def test_no_violation_for_http_url(self, gatling_fixtures_dir: Path) -> None:
        ir = parse(gatling_fixtures_dir / "HttpNoHttp2Simulation.scala")
        violations = GAT013MissingHTTP2().check(ir)
        assert violations == []


# ---------------------------------------------------------------------------
# Helper for apply_fix tests
# ---------------------------------------------------------------------------

from perf_lint.ir.models import Framework, ScriptIR


def _make_gatling_ir(source: str, **extra_parsed_data: object) -> ScriptIR:
    """Build a ScriptIR from raw Scala source by running the GatlingParser on it."""
    import os
    import tempfile

    with tempfile.NamedTemporaryFile(
        suffix=".scala", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        ir = GatlingParser().parse(tmp)
        # Allow overriding parsed_data for edge cases
        ir.parsed_data.update(extra_parsed_data)
        return ir
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# GAT003 apply_fix tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GAT004 apply_fix tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GAT006 apply_fix tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GAT008 apply_fix tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GAT009 apply_fix tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GAT012 apply_fix tests
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GAT013 apply_fix tests
# ---------------------------------------------------------------------------


class TestGAT013ApplyFix:
    def test_adds_enable_http2_after_base_url(self) -> None:
        source = (
            'class Sim extends Simulation {\n'
            '  val httpProtocol = http\n'
            '    .baseUrl("https://example.com")\n'
            '    .acceptHeader("application/json")\n'
            '  val scn = scenario("Test").exec(http("Home").get("/"))\n'
            '  setUp(scn.inject(rampUsers(10).during(10))).protocols(httpProtocol)\n'
            '}\n'
        )
        ir = _make_gatling_ir(source)
        result = GAT013MissingHTTP2().apply_fix(ir)
        assert result is not None
        assert ".enableHttp2" in result

    def test_returns_none_when_http2_present(self) -> None:
        source = (
            'class Sim extends Simulation {\n'
            '  val httpProtocol = http\n'
            '    .baseUrl("https://example.com")\n'
            '    .enableHttp2\n'
            '  val scn = scenario("Test").exec(http("Home").get("/"))\n'
            '  setUp(scn.inject(rampUsers(10).during(10))).protocols(httpProtocol)\n'
            '}\n'
        )
        ir = _make_gatling_ir(source)
        result = GAT013MissingHTTP2().apply_fix(ir)
        assert result is None

    def test_returns_none_when_no_base_url(self) -> None:
        source = (
            'class Sim extends Simulation {\n'
            '  val scn = scenario("Test").exec(http("Home").get("/"))\n'
            '  setUp(scn.inject(rampUsers(10).during(10)))\n'
            '}\n'
        )
        ir = _make_gatling_ir(source)
        result = GAT013MissingHTTP2().apply_fix(ir)
        assert result is None

    def test_fixable_flag_is_true(self) -> None:
        assert GAT013MissingHTTP2.fixable is True
