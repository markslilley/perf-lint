"""JMeter (.jmx) parser for perf-lint.

Extracts test plan structure into parsed_data using lxml with a secure
parser (no XXE, no network access) to handle untrusted .jmx files safely.
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path

from lxml import etree

from perf_lint.ir.models import Framework, ScriptIR
from perf_lint.parsers.base import BaseParser
from perf_lint.xml_utils import _SECURE_PARSER

# IP address regex (IPv4)
_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")

# JMeter expression pattern (e.g. ${__P(threads,10)} or ${VARIABLE})
_JMETER_EXPR_RE = re.compile(r"\$\{")

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_GREEDY_RE = re.compile(r"\(\.[+*]\)")  # matches (.+) or (.*) without ?

# Explicit sets prevent false positives from tags that happen to contain
# "Manager" or "Config" as a substring (e.g., AuthorizationManager).
_CONFIG_ELEMENT_TAGS: frozenset[str] = frozenset({
    "CacheManager",
    "CookieManager",
    "HeaderManager",
    "ConfigTestElement",
    "AuthManager",
    "KeystoreConfig",
    "DNSCacheManager",
})

_LISTENER_TAGS: frozenset[str] = frozenset({
    "ResultCollector",
    "BackendListener",
    "Summariser",
})

_ASSERTION_TAGS: frozenset[str] = frozenset({
    "ResponseAssertion",
    "DurationAssertion",
    "SizeAssertion",
    "JSONPathAssertion",
    "XPathAssertion",
    "MD5HexAssertion",
    "HTMLAssertion",
    "SMIMEAssertion",
    "XPath2Assertion",
    "CompareAssertion",
})

_BEANSHELL_TAGS: frozenset[str] = frozenset({
    "BeanShellSampler",
    "BeanShellPreProcessor",
    "BeanShellPostProcessor",
    "BeanShellListener",
})

_TIMER_TAGS: frozenset[str] = frozenset({
    "ConstantTimer",
    "GaussianRandomTimer",
    "UniformRandomTimer",
    "PoissonRandomTimer",
    "SyncTimer",
    "ConstantThroughputTimer",
    "PreciseThroughputTimer",
})

_EXTRACTOR_TAGS: frozenset[str] = frozenset({
    "RegexExtractor",
    "JSONPathExtractor",
    "XPathExtractor",
    "XPath2Extractor",
    "BoundaryExtractor",
})

# Tags recognised as assertion elements in the original parser's assertion list.
# This is the subset used for the assertions list in parsed_data.
_ASSERTION_LIST_TAGS: frozenset[str] = frozenset({
    "ResponseAssertion",
    "DurationAssertion",
    "SizeAssertion",
    "JSONPathAssertion",
    "XPathAssertion",
    "BeanShellAssertion",
    "JSR223Assertion",
})

_SAMPLER_TAGS: frozenset[str] = frozenset({
    "HTTPSamplerProxy",
    "GenericSampler",
    "JDBCSampler",
})


def _safe_int(text: str | None, default: int) -> int:
    """Parse an int from JMeter property text.

    Returns default for JMeter expressions like ${__P(...)} or ${VAR}.
    Callers should check has_dynamic_values in thread_group_data when the
    accuracy of the result matters (e.g. JMX004 ramp-up check).
    """
    if not text:
        return default
    try:
        return int(text.strip())
    except (ValueError, AttributeError):
        return default


class JMeterParser(BaseParser):
    """Parses JMeter .jmx files into ScriptIR."""

    @property
    def framework(self) -> Framework:
        return Framework.JMETER

    @property
    def supported_extensions(self) -> list[str]:
        return [".jmx"]

    def parse(self, path: Path) -> ScriptIR:
        # Read once — content is reused for both raw_content and XML parsing.
        content = self._read_file(path)
        root = etree.fromstring(content.encode("utf-8"), _SECURE_PARSER)
        parsed_data = self._extract(root, content)

        return ScriptIR(
            framework=self.framework,
            source_path=path,
            raw_content=content,
            parsed_data=parsed_data,
        )

    def _extract(self, root: etree._Element, raw_content: str = "") -> dict:
        """Extract all relevant data from the JMX tree in a single pass."""

        # Limit content scanned for regex-heavy patterns to prevent ReDoS on adversarial input
        _content_for_regex = raw_content[:1_048_576] if len(raw_content) > 1_048_576 else raw_content

        # ---- Accumulators ----
        # Samplers
        sampler_count = 0
        http_sampler_count = 0
        http_samplers: list[etree._Element] = []
        all_samplers: list[etree._Element] = []

        # Config / structure
        config_elements: list[str] = []
        timers: list[str] = []
        assertion_tags: list[str] = []
        csv_data_set_names: list[str] = []
        csv_data_set_count = 0
        listener_count = 0
        backend_listener_count = 0
        transaction_controller_count = 0
        thread_groups: list[etree._Element] = []
        thread_group_count = 0
        has_setup_thread_group = False
        has_size_assertion = False
        http_defaults_has_args_prop = False

        # BeanShell
        beanshell_count = 0

        # ConstantTimer delays
        constant_timer_delays: list[int] = []

        # Extractors
        extractors_found: list[str] = []
        extractor_count = 0
        greedy_regex_extractors: list[str] = []

        # Timeouts
        connection_timeout: int | None = None
        response_timeout: int | None = None

        # Infinite loop detection (deferred to thread group processing)
        has_infinite_loop = False

        # Hardcoded ports
        hardcoded_ports: list[int] = []

        # POST samplers without content type
        has_content_type_header = False

        # ---- Single-pass element scan ----
        for elem in root.iter():
            tag = elem.tag

            # Samplers
            if tag == "HTTPSamplerProxy":
                if elem.get("enabled", "true").lower() != "false":
                    sampler_count += 1
                    http_sampler_count += 1
                http_samplers.append(elem)
                all_samplers.append(elem)

                # JMX020: Hardcoded non-standard ports
                if elem.get("enabled", "true").lower() != "false":
                    port_el = elem.find("./stringProp[@name='HTTPSampler.port']")
                    if port_el is not None and port_el.text and "${" not in port_el.text:
                        port_str = port_el.text.strip()
                        if port_str:
                            try:
                                port = int(port_str)
                                if port not in (0, 80, 443):
                                    hardcoded_ports.append(port)
                            except ValueError:
                                pass

            elif tag in ("GenericSampler", "JDBCSampler"):
                if elem.get("enabled", "true").lower() != "false":
                    sampler_count += 1
                all_samplers.append(elem)

            # Config elements
            elif tag in _CONFIG_ELEMENT_TAGS:
                config_elements.append(tag)
                if tag == "ConfigTestElement":
                    # Track whether the required elementProp is present.
                    # JMeter's UrlConfigGui.configure() reads HTTPsampler.Arguments
                    # unconditionally; if absent it passes null to ArgumentsPanel,
                    # causing a NullPointerException when the file is opened in the GUI.
                    if elem.find("./elementProp[@name='HTTPsampler.Arguments']") is not None:
                        http_defaults_has_args_prop = True
                    # JMX017/JMX018: Timeouts
                    ct_el = elem.find("./stringProp[@name='HTTPSampler.connect_timeout']")
                    rt_el = elem.find("./stringProp[@name='HTTPSampler.response_timeout']")
                    if ct_el is not None and ct_el.text and ct_el.text.strip() not in ("", "0") and "${" not in ct_el.text:
                        with contextlib.suppress(ValueError):
                            connection_timeout = int(ct_el.text.strip())
                    if rt_el is not None and rt_el.text and rt_el.text.strip() not in ("", "0") and "${" not in rt_el.text:
                        with contextlib.suppress(ValueError):
                            response_timeout = int(rt_el.text.strip())
                elif tag == "HeaderManager":
                    # Check for Content-Type header
                    for entry in elem.findall(".//elementProp[@elementType='Header']"):
                        name_el = entry.find("./stringProp[@name='Header.name']")
                        if name_el is not None and (name_el.text or "").lower() == "content-type":
                            has_content_type_header = True
                            break

            # Timers
            elif tag in _TIMER_TAGS:
                timers.append(tag)
                # JMX015: ConstantTimer delays
                if tag == "ConstantTimer" and elem.get("enabled", "true").lower() != "false":
                        delay_el = elem.find("./stringProp[@name='ConstantTimer.delay']")
                        if delay_el is not None and delay_el.text and "${" not in delay_el.text:
                            with contextlib.suppress(ValueError):
                                constant_timer_delays.append(int(delay_el.text.strip()))

            # Assertions
            elif tag in _ASSERTION_LIST_TAGS:
                assertion_tags.append(tag)
                if tag == "SizeAssertion":
                    has_size_assertion = True

            # Listeners
            elif tag in _LISTENER_TAGS:
                if tag in ("ResultCollector", "BackendListener"):
                    listener_count += 1
                if tag == "BackendListener":
                    backend_listener_count += 1

            # CSV Data Set
            elif tag == "CSVDataSet":
                csv_data_set_names.append(elem.get("name", ""))
                csv_data_set_count += 1

            # Transaction Controller
            elif tag == "TransactionController":
                transaction_controller_count += 1

            # Thread Groups
            elif tag == "ThreadGroup":
                thread_groups.append(elem)
                thread_group_count += 1

            elif tag == "SetupThreadGroup":
                has_setup_thread_group = True

            # BeanShell elements
            elif tag in _BEANSHELL_TAGS:
                if elem.get("enabled", "true").lower() != "false":
                    beanshell_count += 1

            # Extractors
            elif tag in _EXTRACTOR_TAGS:
                extractors_found.append(tag)
                extractor_count += 1
                # JMX025: Greedy regex extractors
                if tag == "RegexExtractor" and elem.get("enabled", "true").lower() != "false":
                        regex_el = elem.find("./stringProp[@name='RegexExtractor.regex']")
                        if regex_el is not None and regex_el.text and _GREEDY_RE.search(regex_el.text):
                            greedy_regex_extractors.append(regex_el.text)

        # ---- Thread group data extraction ----
        thread_group_data = []
        for tg in thread_groups:
            num_threads_el = tg.find("./stringProp[@name='ThreadGroup.num_threads']")
            ramp_time_el = tg.find("./stringProp[@name='ThreadGroup.ramp_time']")
            num_threads_text = num_threads_el.text if num_threads_el is not None else None
            ramp_time_text = ramp_time_el.text if ramp_time_el is not None else None
            has_dynamic = bool(
                (num_threads_text and _JMETER_EXPR_RE.search(num_threads_text))
                or (ramp_time_text and _JMETER_EXPR_RE.search(ramp_time_text))
            )
            thread_group_data.append(
                {
                    "num_threads": _safe_int(num_threads_text, 1),
                    "ramp_time": _safe_int(ramp_time_text, 1),
                    "has_dynamic_values": has_dynamic,
                }
            )

        # ---- JMX019: Infinite loop detection ----
        for tg in thread_groups:
            scheduler_el = tg.find("./boolProp[@name='ThreadGroup.scheduler']")
            scheduler_enabled = scheduler_el is not None and (scheduler_el.text or "").lower() == "true"
            # Check <LoopController> element (direct tag)
            loop_ctrl = tg.find(".//LoopController")
            if loop_ctrl is not None:
                loops_el = loop_ctrl.find("./stringProp[@name='LoopController.loops']")
                if loops_el is not None and (loops_el.text or "").strip() == "-1" and not scheduler_enabled:
                    has_infinite_loop = True
                    break
            # Check elementProp with elementType="LoopController" (JMeter's standard format)
            loop_ep = tg.find(".//elementProp[@elementType='LoopController']")
            if loop_ep is not None:
                loops_el = loop_ep.find("./stringProp[@name='LoopController.loops']")
                if loops_el is not None and (loops_el.text or "").strip() == "-1" and not scheduler_enabled:
                    has_infinite_loop = True
                    break
            # Also check intProp directly on thread group
            loop_el2 = tg.find("./intProp[@name='LoopController.loops']")
            if loop_el2 is not None and (loop_el2.text or "").strip() == "-1" and not scheduler_enabled:
                has_infinite_loop = True
                break

        # ---- Variable usage check ----
        uses_variables = False
        for sampler in all_samplers:
            for prop in sampler.iter():
                if prop.text and "${" in prop.text:
                    uses_variables = True
                    break
            if uses_variables:
                break

        # ---- Sampler domain data ----
        sampler_data = []
        for sampler in all_samplers:
            domain_el = sampler.find("./stringProp[@name='HTTPSampler.domain']")
            domain = domain_el.text if domain_el is not None else None
            is_hardcoded_ip = bool(domain and _IP_RE.match(domain.strip()))
            sampler_data.append({"domain": domain, "is_hardcoded_ip": is_hardcoded_ip})

        # ---- JMX016: Correlation check — dynamic values in POST bodies ----
        post_body_texts: list[str] = []
        for hs in http_samplers:
            method_el = hs.find("./stringProp[@name='HTTPSampler.method']")
            method = (method_el.text or "").upper() if method_el is not None else ""
            if method in ("POST", "PUT", "PATCH"):
                body_el = hs.find("./stringProp[@name='HTTPSampler.postBody']")
                if body_el is not None and body_el.text:
                    post_body_texts.append(body_el.text)
                for param in hs.findall(".//elementProp[@elementType='HTTPArgument']"):
                    val_el = param.find("./stringProp[@name='Argument.value']")
                    if val_el is not None and val_el.text:
                        post_body_texts.append(val_el.text)

        has_potential_dynamic_values = any(
            _UUID_RE.search(t) or _JWT_RE.search(t) for t in post_body_texts
        )

        # ---- JMX021: POST samplers without Content-Type ----
        post_method_count = sum(
            1 for hs in http_samplers
            if hs.get("enabled", "true").lower() != "false"
            and (hs.find("./stringProp[@name='HTTPSampler.method']") is not None
                and (hs.find("./stringProp[@name='HTTPSampler.method']").text or "").upper() in ("POST", "PUT", "PATCH"))
        )
        post_samplers_without_content_type = 0 if has_content_type_header else post_method_count

        # ---- Duration assertion count ----
        duration_assertion_count = sum(
            1 for tag in assertion_tags if tag == "DurationAssertion"
        )

        return {
            "thread_groups": thread_group_data,
            "samplers": sampler_data,
            "sampler_count": sampler_count,
            "http_sampler_count": http_sampler_count,
            "config_elements": config_elements,
            "timers": timers,
            "assertions": assertion_tags,
            "assertion_count": len(assertion_tags),
            "duration_assertion_count": duration_assertion_count,
            "csv_data_sets": csv_data_set_names,
            "csv_data_set_count": csv_data_set_count,
            "uses_variables": uses_variables,
            "listener_count": listener_count,
            "transaction_controller_count": transaction_controller_count,
            "beanshell_count": beanshell_count,
            "constant_timer_delays": constant_timer_delays,
            "extractors": extractors_found,
            "extractor_count": extractor_count,
            "has_regex_extractor": any(t == "RegexExtractor" for t in extractors_found),
            "has_json_path_extractor": any(t == "JSONPathExtractor" for t in extractors_found),
            "has_potential_dynamic_values": has_potential_dynamic_values,
            "connection_timeout": connection_timeout,
            "response_timeout": response_timeout,
            "has_infinite_loop": has_infinite_loop,
            "hardcoded_ports": hardcoded_ports,
            "post_samplers_without_content_type": post_samplers_without_content_type,
            "has_size_assertion": has_size_assertion,
            "backend_listener_count": backend_listener_count,
            "thread_group_count": thread_group_count,
            "has_setup_thread_group": has_setup_thread_group,
            "greedy_regex_extractors": greedy_regex_extractors,
            "http_defaults_has_args_prop": http_defaults_has_args_prop,
        }
