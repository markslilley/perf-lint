"""Tests for JMeter rules."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from perf_lint.ir.models import Framework, Severity
from perf_lint.parsers.jmeter import JMeterParser
from perf_lint.rules.jmeter.rules import (
    JMX001MissingCacheManager,
    JMX002MissingCookieManager,
    JMX003ConstantTimerOnly,
    JMX009MissingHeaderManager,
    JMX010NoHTTPDefaults,
    JMX012NoResultCollector,
    JMX013MissingTransactionController,
    JMX014BeanShellUsage,
    JMX023NoBackendListener,
)


def parse(fixture: Path) -> object:
    return JMeterParser().parse(fixture)


def _make_ir(xml: str):
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


class TestJMX001MissingCacheManager:
    def test_triggers_when_no_cache_manager(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "missing_managers.jmx")
        rule = JMX001MissingCacheManager()
        violations = rule.check(ir)
        assert any(v.rule_id == "JMX001" for v in violations)

    def test_passes_when_cache_manager_present(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "good.jmx")
        rule = JMX001MissingCacheManager()
        violations = rule.check(ir)
        assert violations == []

    def test_violation_severity(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "missing_managers.jmx")
        violations = JMX001MissingCacheManager().check(ir)
        assert all(v.severity == Severity.WARNING for v in violations)


class TestJMX002MissingCookieManager:
    def test_triggers_when_no_cookie_manager(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "missing_managers.jmx")
        violations = JMX002MissingCookieManager().check(ir)
        assert any(v.rule_id == "JMX002" for v in violations)

    def test_passes_when_cookie_manager_present(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "good.jmx")
        violations = JMX002MissingCookieManager().check(ir)
        assert violations == []


class TestJMX003ConstantTimerOnly:
    def test_passes_when_no_timers(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "missing_managers.jmx")
        violations = JMX003ConstantTimerOnly().check(ir)
        assert violations == []

    def test_passes_when_gaussian_timer(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "good.jmx")
        violations = JMX003ConstantTimerOnly().check(ir)
        assert violations == []


class TestJMX001ApplyFix:
    def test_inserts_cache_manager(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "missing_managers.jmx")
        fixed = JMX001MissingCacheManager().apply_fix(ir)
        assert fixed is not None
        assert "CacheManager" in fixed

    def test_fixed_source_no_longer_triggers_rule(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX001MissingCacheManager().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = JMX001MissingCacheManager().check(ir2)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert JMX001MissingCacheManager.fixable is True

    def test_returns_none_on_bad_xml(self) -> None:
        from pathlib import Path as P

        from perf_lint.ir.models import ScriptIR
        ir = ScriptIR(
            framework=Framework.JMETER,
            source_path=P("bad.jmx"),
            raw_content="not xml at all",
        )
        result = JMX001MissingCacheManager().apply_fix(ir)
        assert result is None


class TestJMX002ApplyFix:
    def test_inserts_cookie_manager(self, jmeter_fixtures_dir: Path) -> None:
        ir = parse(jmeter_fixtures_dir / "missing_managers.jmx")
        fixed = JMX002MissingCookieManager().apply_fix(ir)
        assert fixed is not None
        assert "CookieManager" in fixed

    def test_fixed_source_no_longer_triggers_rule(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX002MissingCookieManager().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = JMX002MissingCookieManager().check(ir2)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert JMX002MissingCookieManager.fixable is True


# ---------------------------------------------------------------------------
# Fixtures for JMX009–JMX013
# ---------------------------------------------------------------------------

_MULTI_SAMPLER_JMX = """\
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
        <HTTPSamplerProxy testname="R1" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/1</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R2" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/2</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R3" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/3</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R4" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/4</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R5" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/5</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_HEADER_MANAGER = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Headers" enabled="true"/>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_CONFIG_DEFAULTS = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" testname="HTTP Defaults" enabled="true">
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
            <collectionProp name="Arguments.arguments"/>
          </elementProp>
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
        </ConfigTestElement>
        <hashTree/>
        <HTTPSamplerProxy testname="R1" enabled="true">
          <stringProp name="HTTPSampler.path">/1</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R2" enabled="true">
          <stringProp name="HTTPSampler.path">/2</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_DURATION_ASSERTION = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <DurationAssertion guiclass="DurationAssertionGui" testclass="DurationAssertion" testname="Duration Assertion" enabled="true">
          <stringProp name="DurationAssertion.duration">5000</stringProp>
        </DurationAssertion>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_RESULT_COLLECTOR = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
      <ResultCollector guiclass="SummaryReport" testclass="ResultCollector" testname="Summary" enabled="true"/>
      <hashTree/>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_TRANSACTION_CONTROLLER = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <TransactionController guiclass="TransactionControllerGui" testclass="TransactionController" testname="Login" enabled="true"/>
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
  </hashTree>
</jmeterTestPlan>
"""


class TestJMX009MissingHeaderManager:
    def test_triggers_when_no_header_manager(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        violations = JMX009MissingHeaderManager().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX009"
        assert violations[0].severity == Severity.WARNING

    def test_passes_when_header_manager_present(self) -> None:
        ir = _make_ir(_JMX_WITH_HEADER_MANAGER)
        violations = JMX009MissingHeaderManager().check(ir)
        assert violations == []

    def test_no_violation_when_no_http_samplers(self) -> None:
        # A JMX with no HTTPSamplerProxy should not trigger
        no_http_jmx = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree/>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""
        ir = _make_ir(no_http_jmx)
        violations = JMX009MissingHeaderManager().check(ir)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert JMX009MissingHeaderManager.fixable is True

    def test_fix_inserts_header_manager(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX009MissingHeaderManager().apply_fix(ir)
        assert fixed is not None
        assert "HeaderManager" in fixed

    def test_fix_resolves_violation(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX009MissingHeaderManager().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = JMX009MissingHeaderManager().check(ir2)
        assert violations == []

    def test_fix_includes_companion_hashtree(self) -> None:
        from lxml import etree as lxml_et
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX009MissingHeaderManager().apply_fix(ir)
        assert fixed is not None
        root = lxml_et.fromstring(fixed.encode())
        for hm in root.iter("HeaderManager"):
            nxt = hm.getnext()
            assert nxt is not None and nxt.tag == "hashTree", (
                "HeaderManager must be followed by a companion <hashTree/>"
            )


class TestJMX010NoHTTPDefaults:
    def test_triggers_when_multiple_samplers_no_defaults(self) -> None:
        ir = _make_ir(_MULTI_SAMPLER_JMX)
        violations = JMX010NoHTTPDefaults().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX010"
        assert violations[0].severity == Severity.INFO

    def test_passes_when_config_test_element_present(self) -> None:
        ir = _make_ir(_JMX_WITH_CONFIG_DEFAULTS)
        violations = JMX010NoHTTPDefaults().check(ir)
        assert violations == []

    def test_no_violation_for_single_sampler(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        violations = JMX010NoHTTPDefaults().check(ir)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert JMX010NoHTTPDefaults.fixable is True


class TestJMX012NoResultCollector:
    def test_triggers_when_no_listeners(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        violations = JMX012NoResultCollector().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX012"
        assert violations[0].severity == Severity.INFO

    def test_passes_when_result_collector_present(self) -> None:
        ir = _make_ir(_JMX_WITH_RESULT_COLLECTOR)
        violations = JMX012NoResultCollector().check(ir)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert JMX012NoResultCollector.fixable is True


class TestJMX013MissingTransactionController:
    def test_no_violation_for_few_samplers(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)  # only 1 sampler
        violations = JMX013MissingTransactionController().check(ir)
        assert violations == []

    def test_triggers_when_many_samplers_no_controller(self) -> None:
        ir = _make_ir(_MULTI_SAMPLER_JMX)  # 5 samplers, no TransactionController
        violations = JMX013MissingTransactionController().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX013"
        assert violations[0].severity == Severity.INFO

    def test_passes_when_transaction_controller_present(self) -> None:
        ir = _make_ir(_JMX_WITH_TRANSACTION_CONTROLLER)
        violations = JMX013MissingTransactionController().check(ir)
        assert violations == []

    def test_not_fixable(self) -> None:
        assert JMX013MissingTransactionController.fixable is False


# ---------------------------------------------------------------------------
# Structural invariant tests — companion <hashTree/> validation (M7)
# Every element inserted by an apply_fix() method must be followed by a
# companion <hashTree/> sibling or JMeter's HashTreeConverter will throw a
# ClassCastException when loading the file.
# ---------------------------------------------------------------------------

def _assert_companion_hashtrees(xml_str: str) -> None:
    """Assert every non-hashTree element inside a hashTree has a following sibling
    that is itself a hashTree. This is the structural invariant JMeter requires."""
    from lxml import etree
    root = etree.fromstring(xml_str.encode("utf-8"))
    for elem in root.iter():
        parent = elem.getparent()
        if parent is not None and parent.tag == "hashTree" and elem.tag != "hashTree":
            nxt = elem.getnext()
            assert nxt is not None and nxt.tag == "hashTree", (
                f"Element <{elem.tag}> (testname={elem.get('testname', '?')!r}) "
                f"is missing a companion <hashTree/> sibling. "
                f"JMeter's HashTreeConverter will throw ClassCastException."
            )


class TestCompanionHashTreeInvariant:
    """Verify that all apply_fix() methods produce structurally valid JMX."""

    def test_jmx001_fix_has_companion_hashtrees(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX001MissingCacheManager().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)

    def test_jmx002_fix_has_companion_hashtrees(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX002MissingCookieManager().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)

    def test_jmx009_fix_has_companion_hashtrees(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX009MissingHeaderManager().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)

    def test_all_fixes_combined_maintain_invariant(self) -> None:
        """Applying all fixable JMX rules sequentially must still satisfy the invariant."""
        from perf_lint.fixer import apply_fixes
        from perf_lint.rules.base import RuleRegistry
        ir = _make_ir(_MINIMAL_JMX)
        # Run a full fix pass using free rules only
        all_rules = RuleRegistry.get_all()
        violations = (
            JMX001MissingCacheManager().check(ir)
            + JMX002MissingCookieManager().check(ir)
            + JMX009MissingHeaderManager().check(ir)
        )
        fixed_source, applied = apply_fixes(ir, violations, all_rules)
        assert len(applied) > 0
        _assert_companion_hashtrees(fixed_source)


# ---------------------------------------------------------------------------
# JMX014–JMX025 test fixtures
# ---------------------------------------------------------------------------

_JMX_BEANSHELL = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <BeanShellSampler testname="BS" enabled="true"/>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_JSR223 = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <JSR223Sampler testname="Groovy" enabled="true">
          <stringProp name="scriptLanguage">groovy</stringProp>
        </JSR223Sampler>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_ZERO_TIMER = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <ConstantTimer testname="CT" enabled="true">
          <stringProp name="ConstantTimer.delay">{delay}</stringProp>
        </ConstantTimer>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_JWT_NO_EXTRACTOR = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/api/data</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
          <stringProp name="HTTPSampler.postBody">{"token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"}</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_JWT_WITH_EXTRACTOR = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Login" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/login</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
        </HTTPSamplerProxy>
        <hashTree>
          <RegexExtractor testname="Extract Token" enabled="true">
            <stringProp name="RegexExtractor.regex">"token":"([^"]+)"</stringProp>
          </RegexExtractor>
          <hashTree/>
        </hashTree>
        <HTTPSamplerProxy testname="API" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/api/data</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
          <stringProp name="HTTPSampler.postBody">{"token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"}</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_CONFIG_NO_TIMEOUT = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <ConfigTestElement testname="HTTP Defaults" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
        </ConfigTestElement>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_CONFIG_ZERO_TIMEOUT = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <ConfigTestElement testname="HTTP Defaults" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.connect_timeout">0</stringProp>
          <stringProp name="HTTPSampler.response_timeout">0</stringProp>
        </ConfigTestElement>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_CONFIG_WITH_TIMEOUT = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <ConfigTestElement testname="HTTP Defaults" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.connect_timeout">5000</stringProp>
          <stringProp name="HTTPSampler.response_timeout">30000</stringProp>
        </ConfigTestElement>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_INFINITE_LOOP = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController">
          <stringProp name="LoopController.loops">-1</stringProp>
        </elementProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_INFINITE_LOOP_WITH_SCHEDULER = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
        <boolProp name="ThreadGroup.scheduler">true</boolProp>
        <stringProp name="ThreadGroup.duration">300</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController">
          <stringProp name="LoopController.loops">-1</stringProp>
        </elementProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_HARDCODED_PORT = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.port">{port}</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_POST_NO_CONTENT_TYPE = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/api</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_POST_WITH_CONTENT_TYPE = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HeaderManager testname="Headers" enabled="true">
          <collectionProp name="HeaderManager.headers">
            <elementProp name="Content-Type" elementType="Header">
              <stringProp name="Header.name">Content-Type</stringProp>
              <stringProp name="Header.value">application/json</stringProp>
            </elementProp>
          </collectionProp>
        </HeaderManager>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/api</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_MANY_SAMPLERS_NO_SIZE_ASSERTION = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="R1" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/1</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R2" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/2</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R3" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/3</stringProp></HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_SIZE_ASSERTION = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="R1" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/1</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R2" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/2</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <HTTPSamplerProxy testname="R3" enabled="true"><stringProp name="HTTPSampler.domain">example.com</stringProp><stringProp name="HTTPSampler.path">/3</stringProp></HTTPSamplerProxy>
        <hashTree/>
        <SizeAssertion testname="Size Assertion" enabled="true">
          <stringProp name="SizeAssertion.size">1</stringProp>
        </SizeAssertion>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_WITH_BACKEND_LISTENER = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
      <BackendListener testname="influxdb" enabled="true"/>
      <hashTree/>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_MULTIPLE_THREAD_GROUPS = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG1" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">10</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req1" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/1</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
      <ThreadGroup testname="TG2" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">10</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req2" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/2</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_MULTIPLE_TG_WITH_SETUP = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <SetupThreadGroup testname="setUp" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </SetupThreadGroup>
      <hashTree/>
      <ThreadGroup testname="TG1" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">10</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req1" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/1</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
      <ThreadGroup testname="TG2" enabled="true">
        <stringProp name="ThreadGroup.num_threads">5</stringProp>
        <stringProp name="ThreadGroup.ramp_time">10</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req2" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/2</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_GREEDY_REGEX = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree>
          <RegexExtractor testname="Extract" enabled="true">
            <stringProp name="RegexExtractor.regex">{regex}</stringProp>
          </RegexExtractor>
          <hashTree/>
        </hashTree>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


# ---------------------------------------------------------------------------
# JMX014–JMX025 tests
# ---------------------------------------------------------------------------


class TestJMX014BeanShellUsage:
    def test_detects_beanshell_sampler(self) -> None:
        ir = _make_ir(_JMX_BEANSHELL)
        violations = JMX014BeanShellUsage().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX014"
        assert violations[0].severity == Severity.WARNING

    def test_no_violation_for_jsr223(self) -> None:
        ir = _make_ir(_JMX_JSR223)
        violations = JMX014BeanShellUsage().check(ir)
        assert violations == []


class TestJMX023NoBackendListener:
    def test_no_backend_listener_triggers(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        violations = JMX023NoBackendListener().check(ir)
        assert len(violations) == 1
        assert violations[0].rule_id == "JMX023"

    def test_backend_listener_present_no_violation(self) -> None:
        ir = _make_ir(_JMX_WITH_BACKEND_LISTENER)
        violations = JMX023NoBackendListener().check(ir)
        assert violations == []


# ---------------------------------------------------------------------------
# JMX fixture for hardcoded IP
# ---------------------------------------------------------------------------

_JMX_HARDCODED_IP = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">192.168.1.100</stringProp>
          <stringProp name="HTTPSampler.path">/</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""

_JMX_POST_WITH_HEADER_MANAGER_NO_CT = """\
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.5">
  <hashTree>
    <TestPlan testname="Test" enabled="true"/>
    <hashTree>
      <ThreadGroup testname="TG" enabled="true">
        <stringProp name="ThreadGroup.num_threads">1</stringProp>
        <stringProp name="ThreadGroup.ramp_time">1</stringProp>
      </ThreadGroup>
      <hashTree>
        <HeaderManager testname="Headers" enabled="true">
          <collectionProp name="HeaderManager.headers">
            <elementProp name="Accept" elementType="Header">
              <stringProp name="Header.name">Accept</stringProp>
              <stringProp name="Header.value">application/json</stringProp>
            </elementProp>
          </collectionProp>
        </HeaderManager>
        <hashTree/>
        <HTTPSamplerProxy testname="Req" enabled="true">
          <stringProp name="HTTPSampler.domain">example.com</stringProp>
          <stringProp name="HTTPSampler.path">/api</stringProp>
          <stringProp name="HTTPSampler.method">POST</stringProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
"""


# ---------------------------------------------------------------------------
# Apply-fix tests for JMX006–JMX025
# ---------------------------------------------------------------------------


class TestJMX010ApplyFix:
    def test_apply_fix_inserts_config_test_element(self) -> None:
        ir = _make_ir(_MULTI_SAMPLER_JMX)
        rule = JMX010NoHTTPDefaults()
        fixed = rule.apply_fix(ir)
        assert fixed is not None
        assert "ConfigTestElement" in fixed
        assert "${HOST}" in fixed
        assert "${PORT}" in fixed

    def test_apply_fix_returns_none_when_already_correct(self) -> None:
        ir = _make_ir(_JMX_WITH_CONFIG_DEFAULTS)
        rule = JMX010NoHTTPDefaults()
        fixed = rule.apply_fix(ir)
        assert fixed is None

    def test_fix_produces_valid_jmx(self) -> None:
        ir = _make_ir(_MULTI_SAMPLER_JMX)
        fixed = JMX010NoHTTPDefaults().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)


class TestJMX012ApplyFix:
    def test_apply_fix_inserts_result_collector(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        rule = JMX012NoResultCollector()
        fixed = rule.apply_fix(ir)
        assert fixed is not None
        assert "ResultCollector" in fixed
        assert "SummaryReport" in fixed

    def test_apply_fix_returns_none_when_already_correct(self) -> None:
        ir = _make_ir(_JMX_WITH_RESULT_COLLECTOR)
        rule = JMX012NoResultCollector()
        fixed = rule.apply_fix(ir)
        assert fixed is None

    def test_fix_resolves_violation(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX012NoResultCollector().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = JMX012NoResultCollector().check(ir2)
        assert violations == []

    def test_fix_produces_valid_jmx(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX012NoResultCollector().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)


class TestJMX014ApplyFix:
    def test_apply_fix_replaces_beanshell_with_jsr223(self) -> None:
        ir = _make_ir(_JMX_BEANSHELL)
        rule = JMX014BeanShellUsage()
        fixed = rule.apply_fix(ir)
        assert fixed is not None
        assert "JSR223Sampler" in fixed
        assert "BeanShellSampler" not in fixed
        assert "groovy" in fixed

    def test_apply_fix_returns_none_when_already_correct(self) -> None:
        ir = _make_ir(_JMX_JSR223)
        rule = JMX014BeanShellUsage()
        fixed = rule.apply_fix(ir)
        assert fixed is None

    def test_fix_resolves_violation(self) -> None:
        ir = _make_ir(_JMX_BEANSHELL)
        fixed = JMX014BeanShellUsage().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = JMX014BeanShellUsage().check(ir2)
        assert violations == []

    def test_fixable_flag_is_true(self) -> None:
        assert JMX014BeanShellUsage.fixable is True

    def test_fix_produces_valid_jmx(self) -> None:
        ir = _make_ir(_JMX_BEANSHELL)
        fixed = JMX014BeanShellUsage().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)


class TestJMX023ApplyFix:
    def test_apply_fix_inserts_backend_listener(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        rule = JMX023NoBackendListener()
        fixed = rule.apply_fix(ir)
        assert fixed is not None
        assert "BackendListener" in fixed
        assert "InfluxdbBackendListenerClient" in fixed

    def test_apply_fix_returns_none_when_already_correct(self) -> None:
        ir = _make_ir(_JMX_WITH_BACKEND_LISTENER)
        rule = JMX023NoBackendListener()
        fixed = rule.apply_fix(ir)
        assert fixed is None

    def test_fix_resolves_violation(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX023NoBackendListener().apply_fix(ir)
        assert fixed is not None
        ir2 = _make_ir(fixed)
        violations = JMX023NoBackendListener().check(ir2)
        assert violations == []

    def test_fix_produces_valid_jmx(self) -> None:
        ir = _make_ir(_MINIMAL_JMX)
        fixed = JMX023NoBackendListener().apply_fix(ir)
        assert fixed is not None
        _assert_companion_hashtrees(fixed)

    def test_fixable_flag_is_true(self) -> None:
        assert JMX023NoBackendListener.fixable is True


