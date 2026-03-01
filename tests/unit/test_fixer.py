"""Tests for the fixer module: apply_fixes() orchestration, idempotency, and write_fixed_source()."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from perf_lint.fixer import apply_fixes, write_fixed_source
from perf_lint.ir.models import Framework, ScriptIR
from perf_lint.parsers.jmeter import JMeterParser
from perf_lint.parsers.k6 import K6Parser
from perf_lint.rules.base import RuleRegistry
from perf_lint.rules.jmeter.rules import (
    JMX001MissingCacheManager,
    JMX002MissingCookieManager,
)
from perf_lint.rules.k6.rules import K6001MissingThinkTime

_MINIMAL_JMX = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">30</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


def _make_jmx_ir(xml: str) -> ScriptIR:
    """Write xml to a temp .jmx file and parse it."""
    with tempfile.NamedTemporaryFile(
        suffix=".jmx", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(xml)
        tmp = Path(f.name)
    try:
        return JMeterParser().parse(tmp)
    finally:
        os.unlink(tmp)


def _make_k6_ir(source: str) -> ScriptIR:
    """Write JS source to a temp .js file and parse it."""
    with tempfile.NamedTemporaryFile(
        suffix=".js", mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        return K6Parser().parse(tmp)
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# A JMX that already has CacheManager, CookieManager, and ResponseAssertion
# ---------------------------------------------------------------------------
_GOOD_JMX = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">30</stringProp>
      </ThreadGroup>
      <hashTree>
        <CacheManager guiclass="CacheManagerGui" testclass="CacheManager" testname="Cache" enabled="true"/>
        <hashTree/>
        <CookieManager guiclass="CookiePanel" testclass="CookieManager" testname="Cookies" enabled="true"/>
        <hashTree/>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree>
          <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="Assert" enabled="true"/>
          <hashTree/>
        </hashTree>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


class TestApplyFixesOrchestration:
    def test_apply_fixes_returns_fixed_source_and_applied_ids(self) -> None:
        """Apply JMX001 fix on minimal JMX missing CacheManager."""
        ir = _make_jmx_ir(_MINIMAL_JMX)
        violations = JMX001MissingCacheManager().check(ir)
        assert len(violations) >= 1

        rules = RuleRegistry.get_all()
        fixed_source, applied_ids = apply_fixes(ir, violations, rules)

        assert "CacheManager" in fixed_source
        assert "JMX001" in applied_ids

    def test_apply_fixes_returns_empty_applied_list_when_nothing_to_fix(self) -> None:
        """Run fixes on a JMX that already satisfies JMX001/JMX002."""
        ir = _make_jmx_ir(_GOOD_JMX)
        # These rules should not trigger violations on _GOOD_JMX
        violations = (
            JMX001MissingCacheManager().check(ir)
            + JMX002MissingCookieManager().check(ir)
        )
        rules = RuleRegistry.get_all()
        fixed_source, applied_ids = apply_fixes(ir, violations, rules)

        assert applied_ids == []
        # Source should be unchanged
        assert fixed_source == ir.raw_content

    def test_apply_fixes_applies_two_fixes_sequentially(self) -> None:
        """Use a JMX missing both CacheManager and CookieManager."""
        ir = _make_jmx_ir(_MINIMAL_JMX)
        violations = (
            JMX001MissingCacheManager().check(ir)
            + JMX002MissingCookieManager().check(ir)
        )
        rules = RuleRegistry.get_all()
        fixed_source, applied_ids = apply_fixes(ir, violations, rules)

        assert "CacheManager" in fixed_source
        assert "CookieManager" in fixed_source
        assert "JMX001" in applied_ids
        assert "JMX002" in applied_ids
        # Verify valid XML
        from lxml import etree
        etree.fromstring(fixed_source.encode("utf-8"))

    def test_apply_fixes_updates_ir_raw_content(self) -> None:
        """Verify that after apply_fixes(), ir.raw_content contains the fixed source."""
        ir = _make_jmx_ir(_MINIMAL_JMX)
        violations = JMX001MissingCacheManager().check(ir)
        rules = RuleRegistry.get_all()
        fixed_source, applied_ids = apply_fixes(ir, violations, rules)

        assert ir.raw_content == fixed_source
        assert "CacheManager" in ir.raw_content

    def test_apply_fixes_skips_unfixable_rules(self) -> None:
        """Rules without apply_fix (fixable=False) don't appear in applied_ids."""
        from perf_lint.rules.jmeter.rules import JMX013MissingTransactionController
        assert JMX013MissingTransactionController.fixable is False

        # JMX013 needs > 3 samplers, build a JMX with 5
        multi_sampler_jmx = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">10</stringProp>
        <stringProp name="ThreadGroup.ramp_time">30</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="R1" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/1</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R2" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/2</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R3" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/3</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R4" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/4</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R5" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/5</stringProp></HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
        ir = _make_jmx_ir(multi_sampler_jmx)
        violations = JMX013MissingTransactionController().check(ir)
        assert len(violations) >= 1

        rules = RuleRegistry.get_all()
        _fixed_source, applied_ids = apply_fixes(ir, violations, rules)
        assert "JMX013" not in applied_ids


class TestIdempotency:
    def test_jmx001_apply_fix_idempotent(self) -> None:
        """Call JMX001.apply_fix(ir) twice; second call should return None."""
        ir = _make_jmx_ir(_MINIMAL_JMX)
        rule = JMX001MissingCacheManager()

        first_fix = rule.apply_fix(ir)
        assert first_fix is not None
        ir.raw_content = first_fix
        # Re-parse to update parsed_data
        ir2 = _make_jmx_ir(first_fix)
        second_fix = rule.apply_fix(ir2)
        assert second_fix is None

    def test_jmx002_apply_fix_idempotent(self) -> None:
        """Call JMX002.apply_fix(ir) twice; second call should return None."""
        ir = _make_jmx_ir(_MINIMAL_JMX)
        rule = JMX002MissingCookieManager()

        first_fix = rule.apply_fix(ir)
        assert first_fix is not None
        ir2 = _make_jmx_ir(first_fix)
        second_fix = rule.apply_fix(ir2)
        assert second_fix is None

    def test_k6001_apply_fix_idempotent(self, k6_fixtures_dir: Path) -> None:
        """Call K6001.apply_fix(ir) on missing_sleep.js; second call returns None."""
        ir = K6Parser().parse(k6_fixtures_dir / "missing_sleep.js")
        rule = K6001MissingThinkTime()

        first_fix = rule.apply_fix(ir)
        assert first_fix is not None
        assert "sleep(1)" in first_fix
        ir2 = _make_k6_ir(first_fix)
        second_fix = rule.apply_fix(ir2)
        assert second_fix is None

    def test_apply_fixes_twice_does_not_duplicate_elements(self) -> None:
        """Call apply_fixes() twice on same JMX IR; verify no duplicate CacheManagers."""
        ir = _make_jmx_ir(_MINIMAL_JMX)
        violations = JMX001MissingCacheManager().check(ir)
        rules = RuleRegistry.get_all()

        # First pass
        fixed_source_1, applied_1 = apply_fixes(ir, violations, rules)
        assert "JMX001" in applied_1

        # Second pass on the already-fixed IR
        # Re-parse to get fresh violations (should be empty for JMX001)
        ir2 = _make_jmx_ir(fixed_source_1)
        violations_2 = JMX001MissingCacheManager().check(ir2)
        fixed_source_2, applied_2 = apply_fixes(ir2, violations_2, rules)

        # No duplicates
        assert applied_2 == []
        assert fixed_source_2.count("CacheManager") == fixed_source_1.count("CacheManager")


class TestWriteFixedSource:
    def test_write_fixed_source_writes_to_existing_file(self) -> None:
        """Create temp file, write fixed content, verify content changed."""
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write("// original content\n")
            tmp = Path(f.name)
        try:
            write_fixed_source(tmp, "// fixed content\n")
            result = tmp.read_text(encoding="utf-8")
            assert result == "// fixed content\n"
        finally:
            os.unlink(tmp)

    def test_write_fixed_source_raises_on_nonexistent_path(self) -> None:
        """Passing a path that doesn't exist should raise ValueError."""
        fake_path = Path("/tmp/perf_lint_test_nonexistent_file_12345.js")
        # Ensure it really doesn't exist
        if fake_path.exists():
            fake_path.unlink()
        with pytest.raises(ValueError, match="does not exist"):
            write_fixed_source(fake_path, "content")

    def test_write_fixed_source_preserves_utf8_for_js_files(self) -> None:
        """JS files always written as utf-8."""
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write("// original\n")
            tmp = Path(f.name)
        try:
            content_with_unicode = "// content with unicode: \u4f60\u597d\n"
            write_fixed_source(tmp, content_with_unicode)
            result = tmp.read_text(encoding="utf-8")
            assert result == content_with_unicode
        finally:
            os.unlink(tmp)

    def test_write_fixed_source_uses_declared_encoding_for_jmx(self) -> None:
        """JMX with encoding='ISO-8859-1' declaration gets written as iso-8859-1."""
        with tempfile.NamedTemporaryFile(
            suffix=".jmx", mode="w", delete=False, encoding="utf-8"
        ) as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<root/>\n')
            tmp = Path(f.name)
        try:
            iso_content = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<root/>\n'
            write_fixed_source(tmp, iso_content)
            # Read back as bytes and verify encoding
            raw_bytes = tmp.read_bytes()
            assert b"ISO-8859-1" in raw_bytes
            # Should be decodable as ISO-8859-1
            raw_bytes.decode("iso-8859-1")
        finally:
            os.unlink(tmp)


class TestEdgeCases:
    def test_apply_fixes_on_empty_js_file(self) -> None:
        """Pass an empty .js file; should not crash, return (source, [])."""
        ir = ScriptIR(
            framework=Framework.K6,
            source_path=Path("/fake/empty.js"),
            raw_content="",
            parsed_data={},
        )
        rules = RuleRegistry.get_all()
        # No violations to fix
        fixed_source, applied_ids = apply_fixes(ir, [], rules)
        assert fixed_source == ""
        assert applied_ids == []

    def test_apply_fixes_on_comment_only_js_file(self) -> None:
        """JS with only comments; should not crash."""
        source = "// This is a comment\n/* block comment */\n"
        ir = ScriptIR(
            framework=Framework.K6,
            source_path=Path("/fake/comments.js"),
            raw_content=source,
            parsed_data={},
        )
        rules = RuleRegistry.get_all()
        fixed_source, applied_ids = apply_fixes(ir, [], rules)
        assert fixed_source == source
        assert applied_ids == []

    def test_apply_fixes_on_malformed_jmx(self) -> None:
        """Invalid XML; apply_fixes should gracefully return (source, [])."""
        bad_xml = "this is not xml at all <broken>"
        ir = ScriptIR(
            framework=Framework.JMETER,
            source_path=Path("/fake/bad.jmx"),
            raw_content=bad_xml,
            parsed_data={},
        )
        # Create violations manually for JMX001 (which would try to parse XML)
        from perf_lint.ir.models import Location, Severity, Violation
        violations = [
            Violation(
                rule_id="JMX001",
                severity=Severity.WARNING,
                message="Missing CacheManager",
                location=Location(line=1),
            )
        ]
        rules = RuleRegistry.get_all()
        fixed_source, applied_ids = apply_fixes(ir, violations, rules)
        # JMX001's apply_fix should return None on bad XML, so nothing applied
        assert fixed_source == bad_xml
        assert applied_ids == []

    def test_k6_parser_handles_file_with_no_newlines(self) -> None:
        """Single-line JS file; parser should not crash."""
        source = "import http from 'k6/http'; export default function() { http.get('http://test.k6.io'); }"
        ir = _make_k6_ir(source)
        assert ir is not None
        assert ir.parsed_data.get("http_call_count", 0) >= 1
