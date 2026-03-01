"""Edge case tests for all three parsers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from perf_lint.parsers.jmeter import JMeterParser
from perf_lint.parsers.k6 import K6Parser
from perf_lint.parsers.gatling import GatlingParser


def _tmp_file(content: str, suffix: str) -> Path:
    """Write content to a temp file and return its Path."""
    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        return Path(f.name)


class TestK6ParserEdgeCases:
    def test_empty_file(self) -> None:
        p = _tmp_file("", ".js")
        try:
            ir = K6Parser().parse(p)
            assert ir.parsed_data.get("http_call_count", 0) == 0
        finally:
            os.unlink(p)

    def test_comment_only_file(self) -> None:
        p = _tmp_file("// This is just a comment\n/* no code here */\n", ".js")
        try:
            ir = K6Parser().parse(p)
            assert ir.parsed_data.get("has_sleep", False) is False
        finally:
            os.unlink(p)

    def test_no_newlines_file(self) -> None:
        p = _tmp_file(
            "import http from 'k6/http'; export default function() { http.get('http://test.k6.io'); }",
            ".js",
        )
        try:
            ir = K6Parser().parse(p)
            assert ir is not None
        finally:
            os.unlink(p)

    def test_unicode_content(self) -> None:
        p = _tmp_file(
            "// Test with unicode: \u4f60\u597d\u4e16\u754c\nexport default function() {}\n",
            ".js",
        )
        try:
            ir = K6Parser().parse(p)
            assert ir is not None
        finally:
            os.unlink(p)

    def test_large_content_does_not_crash(self) -> None:
        # 2MB file -- should be handled gracefully (scan cap applies)
        large_content = "// comment\n" * 200_000
        p = _tmp_file(large_content, ".js")
        try:
            ir = K6Parser().parse(p)
            assert ir is not None
        finally:
            os.unlink(p)


class TestJMeterParserEdgeCases:
    def test_malformed_xml_raises_or_returns_ir(self) -> None:
        """Malformed XML should raise an exception during parsing."""
        p = _tmp_file("this is not xml", ".jmx")
        try:
            # The JMeter parser calls etree.fromstring which raises on bad XML
            with pytest.raises(Exception):
                JMeterParser().parse(p)
        finally:
            os.unlink(p)

    def test_empty_jmx_file(self) -> None:
        p = _tmp_file("", ".jmx")
        try:
            # Empty file is also invalid XML, should raise
            with pytest.raises(Exception):
                JMeterParser().parse(p)
        finally:
            os.unlink(p)

    def test_disabled_elements_not_counted(self) -> None:
        """Elements with enabled='false' should not be counted by the parser."""
        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">30</stringProp>
      </ThreadGroup>
      <hashTree>
        <BeanShellSampler testname="Disabled Bean" enabled="false"/>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>"""
        p = _tmp_file(xml, ".jmx")
        try:
            ir = JMeterParser().parse(p)
            # Disabled BeanShell should NOT be counted
            assert ir.parsed_data.get("beanshell_count", 0) == 0
        finally:
            os.unlink(p)


class TestGatlingParserEdgeCases:
    def test_empty_file(self) -> None:
        p = _tmp_file("", ".scala")
        try:
            ir = GatlingParser().parse(p)
            assert ir is not None
            assert ir.parsed_data.get("exec_count", 0) == 0
        finally:
            os.unlink(p)

    def test_comment_only_file(self) -> None:
        p = _tmp_file("// Just a comment\n// No simulation here\n", ".scala")
        try:
            ir = GatlingParser().parse(p)
            assert ir is not None
        finally:
            os.unlink(p)

    def test_exec_with_check_does_not_cross_boundaries(self) -> None:
        """Verify _EXEC_WITH_CHECK_RE does not count checks from a different exec block."""
        source = """\
class TestSim extends Simulation {
  val scn = scenario("Test")
    .exec(http("Unchecked").get("/a"))
    .exec(http("Checked").get("/b").check(status.is(200)))
  setUp(scn.inject(atOnceUsers(1)))
}"""
        p = _tmp_file(source, ".scala")
        try:
            ir = GatlingParser().parse(p)
            # exec_http_count = 2, exec_with_check_count should be 1 (not 2)
            assert ir.parsed_data.get("exec_http_count", 0) == 2
            assert ir.parsed_data.get("exec_with_check_count", 0) == 1
        finally:
            os.unlink(p)
