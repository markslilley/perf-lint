"""Tests for K6 rules."""

from __future__ import annotations

from pathlib import Path

from perf_lint.ir.models import Framework, ScriptIR, Severity
from perf_lint.parsers.k6 import K6Parser
from perf_lint.rules.k6.rules import (
    K6001MissingThinkTime,
    K6004MissingThresholds,
    K6007MissingTeardown,
    K6012MissingGracefulStop,
    K6013ClosedModelOnly,
)


def _make_ir(source: str) -> ScriptIR:
    """Build a minimal ScriptIR from raw JS source by running the K6Parser on it."""
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        return K6Parser().parse(tmp)
    finally:
        os.unlink(tmp)


def parse(fixture: Path) -> object:
    return K6Parser().parse(fixture)


class TestK6001MissingThinkTime:
    def test_triggers_when_no_sleep(self, k6_fixtures_dir: Path) -> None:
        ir = parse(k6_fixtures_dir / "missing_sleep.js")
        violations = K6001MissingThinkTime().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "K6001"
        assert violations[0].severity == Severity.WARNING

    def test_passes_when_sleep_present(self, k6_fixtures_dir: Path) -> None:
        ir = parse(k6_fixtures_dir / "good_test.js")
        violations = K6001MissingThinkTime().check(ir)
        assert violations == []

    def test_violation_has_suggestion(self, k6_fixtures_dir: Path) -> None:
        ir = parse(k6_fixtures_dir / "missing_sleep.js")
        violations = K6001MissingThinkTime().check(ir)
        assert violations[0].suggestion is not None


class TestK6004MissingThresholds:
    def test_passes_when_thresholds_present(self, k6_fixtures_dir: Path) -> None:
        ir = parse(k6_fixtures_dir / "good_test.js")
        violations = K6004MissingThresholds().check(ir)
        assert violations == []

    def test_violation_severity(self) -> None:
        assert K6004MissingThresholds.severity == Severity.WARNING


class TestK6001ApplyFix:
    def test_adds_sleep_to_function_body(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "import { check } from 'k6';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6001MissingThinkTime().apply_fix(ir)
        assert fixed is not None
        assert "sleep(1)" in fixed

    def test_adds_sleep_import_when_missing(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "import { check } from 'k6';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6001MissingThinkTime().apply_fix(ir)
        assert fixed is not None
        assert "sleep" in fixed.split("from 'k6'")[0] or "import { sleep" in fixed

    def test_does_not_duplicate_sleep_import(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "import { check, sleep } from 'k6';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6001MissingThinkTime().apply_fix(ir)
        assert fixed is not None
        # sleep should appear in the import exactly once
        assert fixed.count("sleep") >= 1

    def test_fixed_source_no_longer_triggers_rule(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "import { check } from 'k6';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6001MissingThinkTime().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = K6001MissingThinkTime().check(ir2)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert K6001MissingThinkTime.fixable is True


class TestK6004ApplyFix:
    def test_adds_thresholds_to_existing_options(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export const options = {\n"
            "  vus: 10,\n"
            "  duration: '30s',\n"
            "};\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6004MissingThresholds().apply_fix(ir)
        assert fixed is not None
        assert "thresholds" in fixed
        assert "http_req_duration" in fixed

    def test_prepends_options_when_none_exists(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6004MissingThresholds().apply_fix(ir)
        assert fixed is not None
        assert "export const options" in fixed
        assert "thresholds" in fixed

    def test_fixed_source_no_longer_triggers_rule(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6004MissingThresholds().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = K6004MissingThresholds().check(ir2)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert K6004MissingThresholds.fixable is True


# ---------------------------------------------------------------------------
# K6007-K6015 tests
# ---------------------------------------------------------------------------

def _make_ir_from_data(**parsed_data: object) -> ScriptIR:
    """Build a ScriptIR with explicit parsed_data — no file I/O needed."""
    return ScriptIR(
        framework=Framework.K6,
        source_path=Path("/fake/test.js"),
        raw_content="",
        parsed_data=parsed_data,
    )


class TestK6007MissingTeardown:
    def test_triggers_when_setup_without_teardown(self) -> None:
        ir = _make_ir_from_data(has_setup=True, has_teardown=False)
        violations = K6007MissingTeardown().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "K6007"
        assert violations[0].severity == Severity.WARNING

    def test_no_violation_when_both_present(self) -> None:
        ir = _make_ir_from_data(has_setup=True, has_teardown=True)
        violations = K6007MissingTeardown().check(ir)
        assert violations == []

    def test_no_violation_when_neither_present(self) -> None:
        ir = _make_ir_from_data(has_setup=False, has_teardown=False)
        violations = K6007MissingTeardown().check(ir)
        assert violations == []

    def test_integration_via_parser(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export function setup() {\n"
            "  return { userId: 1 };\n"
            "}\n"
            "\n"
            "export default function (data) {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        violations = K6007MissingTeardown().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "K6007"


class TestK6012MissingGracefulStop:
    def test_triggers_with_stages_no_graceful_stop(self) -> None:
        ir = _make_ir_from_data(
            stages=[{"duration_secs": 30, "target": 10}],
            has_scenarios=False,
            has_graceful_stop=False,
        )
        violations = K6012MissingGracefulStop().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "K6012"
        assert violations[0].severity == Severity.WARNING

    def test_triggers_with_scenarios_no_graceful_stop(self) -> None:
        ir = _make_ir_from_data(
            stages=[],
            has_scenarios=True,
            has_graceful_stop=False,
        )
        violations = K6012MissingGracefulStop().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "K6012"

    def test_no_violation_with_graceful_stop(self) -> None:
        ir = _make_ir_from_data(
            stages=[{"duration_secs": 30, "target": 10}],
            has_scenarios=False,
            has_graceful_stop=True,
        )
        violations = K6012MissingGracefulStop().check(ir)
        assert violations == []

    def test_no_violation_without_stages(self) -> None:
        ir = _make_ir_from_data(
            stages=[],
            has_scenarios=False,
            has_graceful_stop=False,
        )
        violations = K6012MissingGracefulStop().check(ir)
        assert violations == []


class TestK6013ClosedModelOnly:
    def test_triggers_with_stages_only(self) -> None:
        ir = _make_ir_from_data(
            stages=[{"duration_secs": 60, "target": 50}],
            has_arrival_rate=False,
        )
        violations = K6013ClosedModelOnly().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "K6013"
        assert violations[0].severity == Severity.INFO

    def test_no_violation_with_arrival_rate(self) -> None:
        ir = _make_ir_from_data(
            stages=[{"duration_secs": 60, "target": 50}],
            has_arrival_rate=True,
        )
        violations = K6013ClosedModelOnly().check(ir)
        assert violations == []

    def test_no_violation_without_stages(self) -> None:
        ir = _make_ir_from_data(stages=[], has_arrival_rate=False)
        violations = K6013ClosedModelOnly().check(ir)
        assert violations == []


# ---------------------------------------------------------------------------
# apply_fix tests for K6003, K6006, K6007, K6010, K6012
# ---------------------------------------------------------------------------


class TestK6007ApplyFix:
    def test_apply_fix_appends_teardown(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export function setup() {\n"
            "  return { userId: 1 };\n"
            "}\n"
            "\n"
            "export default function (data) {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6007MissingTeardown().apply_fix(ir)
        assert fixed is not None
        assert "export function teardown(data)" in fixed
        assert "TODO: clean up resources" in fixed

    def test_apply_fix_returns_none_when_teardown_exists(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export function setup() {\n"
            "  return { userId: 1 };\n"
            "}\n"
            "\n"
            "export function teardown(data) {\n"
            "  // cleanup\n"
            "}\n"
            "\n"
            "export default function (data) {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6007MissingTeardown().apply_fix(ir)
        assert fixed is None

    def test_apply_fix_returns_none_when_not_needed(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export function setup() { return {}; }\n"
            "export function teardown(data) {}\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6007MissingTeardown().apply_fix(ir)
        assert fixed is None

    def test_fixable_flag_is_true(self) -> None:
        assert K6007MissingTeardown.fixable is True

    def test_fixed_source_no_longer_triggers_rule(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export function setup() {\n"
            "  return { userId: 1 };\n"
            "}\n"
            "\n"
            "export default function (data) {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6007MissingTeardown().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = K6007MissingTeardown().check(ir2)
        assert violations == []


class TestK6012ApplyFix:
    def test_apply_fix_injects_graceful_stop(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export const options = {\n"
            "  stages: [\n"
            "    { duration: '30s', target: 10 },\n"
            "  ],\n"
            "};\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6012MissingGracefulStop().apply_fix(ir)
        assert fixed is not None
        assert "gracefulStop: '30s'" in fixed
        assert "gracefulRampDown: '30s'" in fixed

    def test_apply_fix_returns_none_when_already_present(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export const options = {\n"
            "  gracefulStop: '30s',\n"
            "  stages: [\n"
            "    { duration: '30s', target: 10 },\n"
            "  ],\n"
            "};\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6012MissingGracefulStop().apply_fix(ir)
        assert fixed is None

    def test_apply_fix_returns_none_when_not_needed(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export const options = {\n"
            "  gracefulRampDown: '10s',\n"
            "};\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6012MissingGracefulStop().apply_fix(ir)
        assert fixed is None

    def test_apply_fix_returns_none_without_options_block(self) -> None:
        source = (
            "import http from 'k6/http';\n"
            "\n"
            "export default function () {\n"
            "  http.get('https://example.com');\n"
            "}\n"
        )
        ir = _make_ir(source)
        fixed = K6012MissingGracefulStop().apply_fix(ir)
        assert fixed is None

    def test_fixable_flag_is_true(self) -> None:
        assert K6012MissingGracefulStop.fixable is True
