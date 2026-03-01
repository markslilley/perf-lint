"""JMeter rules JMX001-JMX008."""

from __future__ import annotations

import copy

from lxml import etree

from perf_lint.ir.models import Framework, Location, ScriptIR, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry
from perf_lint.xml_utils import _SECURE_PARSER


def _parse_jmx(raw: str) -> etree._Element | None:
    """Parse a JMX string into an lxml Element, or return None on failure."""
    try:
        return etree.fromstring(raw.encode("utf-8"), _SECURE_PARSER)
    except etree.XMLSyntaxError:
        return None


def _serialize_jmx(root: etree._Element) -> str:
    """Serialize an lxml Element back to a UTF-8 XML string with declaration.

    Uses lxml's built-in pretty_print — no post-processing needed.
    Mirrors jmeter-cli-editor's JMXSerializer.serialize_to_string().
    """
    xml_bytes = etree.tostring(
        root,
        encoding="UTF-8",
        xml_declaration=True,
        pretty_print=True,
    )
    return xml_bytes.decode("UTF-8")


def _find_thread_group_hashtree(root: etree._Element) -> etree._Element | None:
    """Return the hashTree that immediately follows the first ThreadGroup element.

    Uses lxml's getnext() — the idiom from jmeter-cli-editor's JMXDocument —
    which is more robust than walking by list index because it doesn't depend
    on element count or ordering.

    JMeter structure:
      jmeterTestPlan > hashTree > hashTree
        ThreadGroup
        hashTree   ← this is what we return (ThreadGroup's direct children)
          CacheManager, CookieManager, HTTPSamplerProxy, ...
    """
    tg = root.find(".//ThreadGroup")
    if tg is None:
        return None
    tg_ht = tg.getnext()
    if tg_ht is None or tg_ht.tag != "hashTree":
        return None
    return tg_ht


def _insert_into_tg_hashtree(root: etree._Element, elem: etree._Element) -> bool:
    """Insert elem + companion hashTree at position 0 of the thread group hashTree.
    Returns True if insertion was successful, False if no thread group hashTree found."""
    tg_ht = _find_thread_group_hashtree(root)
    if tg_ht is None:
        return False
    tg_ht.insert(0, etree.Element("hashTree"))
    tg_ht.insert(0, elem)
    return True


def _make_cache_manager() -> etree._Element:
    """Create a CacheManager element matching the style of the test fixtures."""
    elem = etree.Element("CacheManager")
    elem.set("guiclass", "CacheManagerGui")
    elem.set("testclass", "CacheManager")
    elem.set("testname", "HTTP Cache Manager")
    elem.set("enabled", "true")
    return elem


def _make_cookie_manager() -> etree._Element:
    """Create a CookieManager element using jmeter-cli-editor's template structure."""
    elem = etree.Element("CookieManager")
    elem.set("guiclass", "CookiePanel")
    elem.set("testclass", "CookieManager")
    elem.set("testname", "HTTP Cookie Manager")
    elem.set("enabled", "true")
    # Properties — from jmeter-cli-editor's ELEMENT_TEMPLATES["CookieManager"]
    for name, value in (
        ("CookieManager.clearEachIteration", "false"),
        ("CookieManager.controlledByThreadGroup", "false"),
    ):
        prop = etree.SubElement(elem, "boolProp")
        prop.set("name", name)
        prop.text = value
    coll = etree.SubElement(elem, "collectionProp")
    coll.set("name", "CookieManager.cookies")
    return elem


def _make_http_defaults(
    domain: str = "${HOST}",
    port: str = "${PORT}",
    protocol: str = "${PROTOCOL}",
    connect_timeout: str = "5000",
    response_timeout: str = "30000",
) -> etree._Element:
    """Create a ConfigTestElement (HTTP Request Defaults) with the structure
    that JMeter's HttpDefaultsGui.configure() requires.

    JMeter's UrlConfigGui.configure() unconditionally reads
    'HTTPsampler.Arguments' (note lowercase 's') and passes the result to
    ArgumentsPanel.configure(). If the elementProp is absent the value is null
    and JMeter throws a NullPointerException when loading the file.
    """
    elem = etree.Element("ConfigTestElement")
    elem.set("guiclass", "HttpDefaultsGui")
    elem.set("testclass", "ConfigTestElement")
    elem.set("testname", "HTTP Request Defaults")
    elem.set("enabled", "true")
    # Required by HttpDefaultsGui — must be present even when empty.
    args_prop = etree.SubElement(elem, "elementProp")
    args_prop.set("name", "HTTPsampler.Arguments")
    args_prop.set("elementType", "Arguments")
    coll = etree.SubElement(args_prop, "collectionProp")
    coll.set("name", "Arguments.arguments")
    for name, value in [
        ("HTTPSampler.domain", domain),
        ("HTTPSampler.port", port),
        ("HTTPSampler.protocol", protocol),
        ("HTTPSampler.connect_timeout", connect_timeout),
        ("HTTPSampler.response_timeout", response_timeout),
    ]:
        prop = etree.SubElement(elem, "stringProp")
        prop.set("name", name)
        prop.text = value
    return elem


_BEANSHELL_TO_JSR223 = {
    "BeanShellSampler": ("JSR223Sampler", "TestBeanGUI"),
    "BeanShellPreProcessor": ("JSR223PreProcessor", "TestBeanGUI"),
    "BeanShellPostProcessor": ("JSR223PostProcessor", "TestBeanGUI"),
    "BeanShellListener": ("JSR223Listener", "TestBeanGUI"),
}


@RuleRegistry.register
class JMX001MissingCacheManager(BaseRule):
    rule_id = "JMX001"
    name = "MissingCacheManager"
    description = "HTTP Cache Manager is missing. Without it, JMeter won't simulate browser caching, producing unrealistically high load."
    severity = Severity.WARNING
    frameworks = [Framework.JMETER]
    tags = ("realism", "http")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        config_elements = ir.parsed_data.get("config_elements", [])
        has_cache = any("CacheManager" in el for el in config_elements)
        if not has_cache:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message="No HTTP Cache Manager found. Add one to simulate realistic browser caching behaviour.",
                    location=Location(element_path="/jmeterTestPlan"),
                    suggestion="Add an HTTP Cache Manager config element to your Thread Group.",
                    fix_example='<CacheManager guiclass="CacheManagerGui" testclass="CacheManager" testname="HTTP Cache Manager" enabled="true"/>',
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        if root.findall(".//CacheManager"):
            return None
        if not _insert_into_tg_hashtree(root, _make_cache_manager()):
            return None
        return _serialize_jmx(root)


@RuleRegistry.register
class JMX002MissingCookieManager(BaseRule):
    rule_id = "JMX002"
    name = "MissingCookieManager"
    description = "HTTP Cookie Manager is missing. Sessions won't be maintained between requests."
    severity = Severity.WARNING
    frameworks = [Framework.JMETER]
    tags = ("realism", "http", "sessions")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        config_elements = ir.parsed_data.get("config_elements", [])
        has_cookies = any("CookieManager" in el for el in config_elements)
        if not has_cookies:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message="No HTTP Cookie Manager found. Sessions won't be maintained between requests, producing unrealistic results.",
                    location=Location(element_path="/jmeterTestPlan"),
                    suggestion="Add an HTTP Cookie Manager config element to your Thread Group.",
                    fix_example='<CookieManager guiclass="CookiePanel" testclass="CookieManager" testname="HTTP Cookie Manager" enabled="true"/>',
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        if root.findall(".//CookieManager"):
            return None
        if not _insert_into_tg_hashtree(root, _make_cookie_manager()):
            return None
        return _serialize_jmx(root)


@RuleRegistry.register
class JMX003ConstantTimerOnly(BaseRule):
    rule_id = "JMX003"
    name = "ConstantTimerOnly"
    description = "Only Constant Timers used. Real users don't think at perfectly regular intervals — use Gaussian or Uniform random timers."
    severity = Severity.INFO
    frameworks = [Framework.JMETER]
    tags = ("realism", "think-time")

    def check(self, ir: ScriptIR) -> list[Violation]:
        timers = ir.parsed_data.get("timers", [])
        if timers and all("ConstantTimer" in t for t in timers):
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=f"Only ConstantTimer found ({len(timers)} timer(s)). Real think times are variable.",
                    location=Location(element_path="/jmeterTestPlan//ConstantTimer"),
                    suggestion="Replace ConstantTimer with GaussianRandomTimer or UniformRandomTimer for more realistic think times.",
                    fix_example='<GaussianRandomTimer guiclass="GaussianRandomTimerGui" testname="Random Think Time">\n  <stringProp name="ConstantTimer.delay">1000</stringProp>\n  <stringProp name="RandomTimer.range">500</stringProp>\n</GaussianRandomTimer>',
                )
            ]
        return []


# ---------------------------------------------------------------------------
# Helpers for JMX009 and JMX011
# ---------------------------------------------------------------------------

def _make_header_manager() -> etree._Element:
    """Create an HTTP Header Manager with a realistic default set of headers.

    Structure mirrors the perf-recorder output format.
    """
    elem = etree.Element("HeaderManager")
    elem.set("guiclass", "HeaderPanel")
    elem.set("testclass", "HeaderManager")
    elem.set("testname", "HTTP Headers")
    elem.set("enabled", "true")
    coll = etree.SubElement(elem, "collectionProp")
    coll.set("name", "HeaderManager.headers")
    for name, value in (
        ("User-Agent", "Mozilla/5.0 (compatible; perf-test)"),
        ("Accept", "application/json, text/html, */*"),
        ("Accept-Encoding", "gzip, deflate, br"),
        ("Accept-Language", "en-GB,en;q=0.9"),
    ):
        entry = etree.SubElement(coll, "elementProp")
        entry.set("name", name)
        entry.set("elementType", "Header")
        name_prop = etree.SubElement(entry, "stringProp")
        name_prop.set("name", "Header.name")
        name_prop.text = name
        val_prop = etree.SubElement(entry, "stringProp")
        val_prop.set("name", "Header.value")
        val_prop.text = value
    return elem


# ---------------------------------------------------------------------------
# JMX009–JMX013
# ---------------------------------------------------------------------------

@RuleRegistry.register
class JMX009MissingHeaderManager(BaseRule):
    rule_id = "JMX009"
    name = "MissingHeaderManager"
    description = (
        "No HTTP Header Manager found. Without common request headers "
        "(User-Agent, Accept-Encoding, Accept), requests won't simulate real browser behaviour "
        "and the server may serve different content or skip compression."
    )
    severity = Severity.WARNING
    frameworks = [Framework.JMETER]
    tags = ("realism", "http")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        if ir.parsed_data.get("http_sampler_count", 0) == 0:
            return []
        config_elements = ir.parsed_data.get("config_elements", [])
        has_headers = any("HeaderManager" in el for el in config_elements)
        if not has_headers:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=(
                        "No HTTP Header Manager found. Without it, requests lack browser-like "
                        "headers such as User-Agent and Accept-Encoding."
                    ),
                    location=Location(element_path="/jmeterTestPlan"),
                    suggestion="Add an HTTP Header Manager to your Thread Group with realistic browser headers.",
                    fix_example=(
                        '<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" '
                        'testname="HTTP Headers" enabled="true">\n'
                        '  <collectionProp name="HeaderManager.headers">\n'
                        '    <elementProp name="User-Agent" elementType="Header">\n'
                        '      <stringProp name="Header.name">User-Agent</stringProp>\n'
                        '      <stringProp name="Header.value">Mozilla/5.0 (compatible; perf-test)</stringProp>\n'
                        '    </elementProp>\n'
                        '  </collectionProp>\n'
                        '</HeaderManager>'
                    ),
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        if root.findall(".//HeaderManager"):
            return None
        if not _insert_into_tg_hashtree(root, _make_header_manager()):
            return None
        return _serialize_jmx(root)


@RuleRegistry.register
class JMX010NoHTTPDefaults(BaseRule):
    rule_id = "JMX010"
    name = "NoHTTPDefaults"
    description = (
        "No HTTP Request Defaults (ConfigTestElement) found. Without it, host, port, and protocol "
        "are duplicated in every sampler, making it difficult to point the test at a different environment."
    )
    severity = Severity.INFO
    frameworks = [Framework.JMETER]
    tags = ("portability", "maintainability")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        if ir.parsed_data.get("http_sampler_count", 0) < 2:
            return []
        config_elements = ir.parsed_data.get("config_elements", [])
        has_defaults = any("ConfigTestElement" in el for el in config_elements)
        if not has_defaults:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=(
                        "No HTTP Request Defaults found. Host, port, and protocol are repeated in "
                        f"{ir.parsed_data.get('http_sampler_count', 0)} samplers."
                    ),
                    location=Location(element_path="/jmeterTestPlan"),
                    suggestion=(
                        "Add an HTTP Request Defaults config element with the target host/port/protocol. "
                        "Leave those fields empty in each sampler."
                    ),
                    fix_example=(
                        '<ConfigTestElement guiclass="HttpDefaultsGui" testclass="ConfigTestElement" '
                        'testname="HTTP Request Defaults" enabled="true">\n'
                        '  <elementProp name="HTTPsampler.Arguments" elementType="Arguments">\n'
                        '    <collectionProp name="Arguments.arguments"/>\n'
                        '  </elementProp>\n'
                        '  <stringProp name="HTTPSampler.domain">${HOST}</stringProp>\n'
                        '  <stringProp name="HTTPSampler.port">${PORT}</stringProp>\n'
                        '  <stringProp name="HTTPSampler.protocol">${PROTOCOL}</stringProp>\n'
                        '  <stringProp name="HTTPSampler.connect_timeout">5000</stringProp>\n'
                        '  <stringProp name="HTTPSampler.response_timeout">30000</stringProp>\n'
                        '</ConfigTestElement>'
                    ),
                )
            ]
        # Detect an existing ConfigTestElement that is missing the required
        # elementProp — this was created by an older perf-lint --fix and will
        # crash JMeter's GUI with a NullPointerException when loaded.
        if not ir.parsed_data.get("http_defaults_has_args_prop", True):
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=(
                        "HTTP Request Defaults exists but is missing the required "
                        "'HTTPsampler.Arguments' elementProp. JMeter will throw a "
                        "NullPointerException (cannot invoke getName() because element is null) "
                        "when this file is opened in the GUI."
                    ),
                    location=Location(element_path="/jmeterTestPlan//ConfigTestElement"),
                    suggestion="Run perf-lint check --fix to repair the element automatically.",
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        existing = root.findall(".//ConfigTestElement[@guiclass='HttpDefaultsGui']")
        if existing:
            # Repair any existing element missing the required elementProp.
            # JMeter's UrlConfigGui.configure() reads HTTPsampler.Arguments
            # unconditionally; if absent it passes null to ArgumentsPanel,
            # causing a NullPointerException when the file is loaded in the GUI.
            changed = False
            for cte in existing:
                if cte.find("./elementProp[@name='HTTPsampler.Arguments']") is None:
                    args_prop = etree.Element("elementProp")
                    args_prop.set("name", "HTTPsampler.Arguments")
                    args_prop.set("elementType", "Arguments")
                    coll = etree.SubElement(args_prop, "collectionProp")
                    coll.set("name", "Arguments.arguments")
                    cte.insert(0, args_prop)
                    changed = True
            return _serialize_jmx(root) if changed else None
        if not _insert_into_tg_hashtree(root, _make_http_defaults()):
            return None
        return _serialize_jmx(root)


@RuleRegistry.register
class JMX012NoResultCollector(BaseRule):
    rule_id = "JMX012"
    name = "NoResultCollector"
    description = (
        "No result listener (ResultCollector or BackendListener) found. "
        "Without one, the test has no persistent results when run from the GUI."
    )
    severity = Severity.INFO
    frameworks = [Framework.JMETER]
    tags = ("observability", "results")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        if ir.parsed_data.get("sampler_count", 0) == 0:
            return []
        if ir.parsed_data.get("listener_count", 0) == 0:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=(
                        "No ResultCollector or BackendListener found. "
                        "Add a listener to capture results when running from the GUI."
                    ),
                    location=Location(element_path="/jmeterTestPlan"),
                    suggestion=(
                        "Add a View Results Tree or Summary Report listener for local runs, "
                        "or a BackendListener (e.g. InfluxDB) for CI/CD pipelines."
                    ),
                    fix_example=(
                        '<ResultCollector guiclass="SummaryReport" testclass="ResultCollector" '
                        'testname="Summary Report" enabled="true">\n'
                        '  <boolProp name="ResultCollector.error_logging">false</boolProp>\n'
                        '  <stringProp name="filename">results.jtl</stringProp>\n'
                        '</ResultCollector>'
                    ),
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        if root.findall(".//ResultCollector") or root.findall(".//BackendListener"):
            return None
        # Find the outer hashTree (child of root that contains TestPlan)
        outer_ht = root.find("./hashTree")
        if outer_ht is None:
            return None
        # The inner hashTree is the second child of outer_ht (after TestPlan)
        inner_ht = outer_ht.find("./hashTree")
        if inner_ht is None:
            return None
        elem = etree.Element("ResultCollector")
        elem.set("guiclass", "SummaryReport")
        elem.set("testclass", "ResultCollector")
        elem.set("testname", "Summary Report")
        elem.set("enabled", "true")
        bool_prop = etree.SubElement(elem, "boolProp")
        bool_prop.set("name", "ResultCollector.error_logging")
        bool_prop.text = "false"
        str_prop = etree.SubElement(elem, "stringProp")
        str_prop.set("name", "filename")
        str_prop.text = "results.jtl"
        inner_ht.append(elem)
        inner_ht.append(etree.Element("hashTree"))
        return _serialize_jmx(root)


@RuleRegistry.register
class JMX013MissingTransactionController(BaseRule):
    rule_id = "JMX013"
    name = "MissingTransactionController"
    description = (
        "Multiple samplers but no Transaction Controller. Without transaction grouping, "
        "JMeter cannot report end-to-end response times for logical user journeys "
        "(e.g. login + browse + checkout as one transaction)."
    )
    severity = Severity.INFO
    frameworks = [Framework.JMETER]
    tags = ("structure", "reporting")

    def check(self, ir: ScriptIR) -> list[Violation]:
        sampler_count = ir.parsed_data.get("sampler_count", 0)
        if sampler_count < 5:
            return []
        if ir.parsed_data.get("transaction_controller_count", 0) == 0:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=(
                        f"Found {sampler_count} samplers but no Transaction Controller. "
                        "Group related requests into transactions for meaningful end-to-end metrics."
                    ),
                    location=Location(element_path="/jmeterTestPlan"),
                    suggestion=(
                        "Wrap logical user journeys (login, browse, checkout) in Transaction Controllers "
                        "so JMeter reports composite response times."
                    ),
                    fix_example=(
                        '<TransactionController guiclass="TransactionControllerGui" '
                        'testclass="TransactionController" testname="Login Journey" enabled="true">\n'
                        '  <boolProp name="TransactionController.includeTimers">false</boolProp>\n'
                        '</TransactionController>'
                    ),
                )
            ]
        return []


# ---------------------------------------------------------------------------
# JMX014–JMX025
# ---------------------------------------------------------------------------


@RuleRegistry.register
class JMX014BeanShellUsage(BaseRule):
    rule_id = "JMX014"
    name = "BeanShellUsage"
    description = (
        "BeanShell sampler or processor detected. BeanShell is single-threaded, "
        "GC-unfriendly, and deprecated since JMeter 3.1. Under load it serialises "
        "execution and collapses throughput. Use JSR223 with Groovy instead."
    )
    severity = Severity.WARNING
    frameworks = [Framework.JMETER]
    tags = ("performance", "deprecated")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        count = ir.parsed_data.get("beanshell_count", 0)
        if count > 0:
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message=f"Found {count} BeanShell element(s). Replace with JSR223 (Groovy) for correct behaviour under load.",
                location=Location(element_path="/jmeterTestPlan"),
                suggestion="Replace BeanShellSampler/PreProcessor/PostProcessor with JSR223Sampler/PreProcessor/PostProcessor using Groovy.",
                fix_example='<JSR223Sampler guiclass="TestBeanGUI" testname="JSR223 Sampler">\n  <stringProp name="scriptLanguage">groovy</stringProp>\n  <stringProp name="script">// your Groovy script here</stringProp>\n</JSR223Sampler>',
            )]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        changed = False
        for old_tag, (new_tag, gui) in _BEANSHELL_TO_JSR223.items():
            for elem in root.findall(f".//{old_tag}"):
                parent = elem.getparent()
                if parent is None:
                    continue
                idx = list(parent).index(elem)
                new_elem = copy.deepcopy(elem)
                new_elem.tag = new_tag
                new_elem.set("guiclass", gui)
                new_elem.set("testclass", new_tag)
                # Add/update scriptLanguage property
                lang_el = new_elem.find("./stringProp[@name='scriptLanguage']")
                if lang_el is None:
                    lang_el = etree.SubElement(new_elem, "stringProp")
                    lang_el.set("name", "scriptLanguage")
                lang_el.text = "groovy"
                # Rename BeanShell.query to script if present
                script_el = new_elem.find("./stringProp[@name='BeanShell.query']")
                if script_el is not None:
                    script_el.set("name", "script")
                parent.remove(elem)
                parent.insert(idx, new_elem)
                changed = True
        return _serialize_jmx(root) if changed else None


@RuleRegistry.register
class JMX023NoBackendListener(BaseRule):
    rule_id = "JMX023"
    name = "NoBackendListener"
    description = (
        "No BackendListener found. BackendListener (InfluxDB, Graphite) enables "
        "real-time results streaming, essential for long-duration CI runs."
    )
    severity = Severity.INFO
    frameworks = [Framework.JMETER]
    tags = ("observability", "ci-integration")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        if ir.parsed_data.get("sampler_count", 0) == 0:
            return []
        if ir.parsed_data.get("backend_listener_count", 0) == 0:
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="No BackendListener found. Add one to stream results to InfluxDB or Graphite for real-time dashboards.",
                location=Location(element_path="/jmeterTestPlan"),
                suggestion="Add a BackendListener configured for InfluxDB or Graphite for CI/CD observability.",
                fix_example='<BackendListener guiclass="BackendListenerGui" testname="influxdb">\n  <elementProp name="arguments" elementType="Arguments">\n    <collectionProp name="Arguments.arguments"/>\n  </elementProp>\n  <stringProp name="classname">org.apache.jmeter.visualizers.backend.influxdb.InfluxdbBackendListenerClient</stringProp>\n</BackendListener>',
            )]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        root = _parse_jmx(ir.raw_content)
        if root is None:
            return None
        if root.findall(".//BackendListener"):
            return None
        outer_ht = root.find("./hashTree")
        if outer_ht is None:
            return None
        inner_ht = outer_ht.find("./hashTree")
        if inner_ht is None:
            return None
        elem = etree.Element("BackendListener")
        elem.set("guiclass", "BackendListenerGui")
        elem.set("testclass", "BackendListener")
        elem.set("testname", "InfluxDB Backend Listener")
        elem.set("enabled", "true")
        args_ep = etree.SubElement(elem, "elementProp")
        args_ep.set("name", "arguments")
        args_ep.set("elementType", "Arguments")
        coll = etree.SubElement(args_ep, "collectionProp")
        coll.set("name", "Arguments.arguments")
        classname = etree.SubElement(elem, "stringProp")
        classname.set("name", "classname")
        classname.text = "org.apache.jmeter.visualizers.backend.influxdb.InfluxdbBackendListenerClient"
        inner_ht.append(elem)
        inner_ht.append(etree.Element("hashTree"))
        return _serialize_jmx(root)


