"""Intermediate Representation (IR) models for perf-lint.

All parsers produce a ScriptIR. Rules consume ir.parsed_data — a structured
dict extracted once at parse time. Rules never re-scan raw content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TypedDict


class JMeterParsedData(TypedDict, total=False):
    """Type hints for JMeter parser output. All keys are optional (total=False)."""
    sampler_count: int
    http_sampler_count: int
    has_cache_manager: bool
    has_cookie_manager: bool
    has_assertion: bool
    has_timer: bool
    thread_group_count: int
    has_setup_thread_group: bool
    has_header_manager: bool
    has_csv_data_set: bool
    has_variable_usage: bool
    transaction_controller_count: int
    listener_count: int
    backend_listener_count: int
    has_duration_assertion: bool
    has_size_assertion: bool
    beanshell_count: int
    constant_timer_delays: list[int]
    connection_timeout: int | None
    response_timeout: int | None
    has_infinite_loop: bool
    hardcoded_ports: list[int]
    post_samplers_without_content_type: int
    greedy_regex_extractors: list[str]
    has_regex_extractor: bool
    has_json_path_extractor: bool
    extractor_count: int
    has_potential_dynamic_values: bool
    ramp_time: int
    thread_count: int
    has_http_defaults: bool


class K6ParsedData(TypedDict, total=False):
    """Type hints for K6 parser output."""
    has_sleep: bool
    has_checks: bool
    has_thresholds: bool
    has_stages: bool
    stages: list[dict]
    http_call_count: int
    has_setup: bool
    has_teardown: bool
    has_group: bool
    has_request_tags: bool
    uses_shared_array: bool
    has_graceful_stop: bool
    has_scenarios: bool
    has_arrival_rate: bool
    has_hardcoded_auth_token: bool
    has_custom_metrics: bool
    has_http_timeout: bool
    has_open_call: bool
    base_url: str


class GatlingParsedData(TypedDict, total=False):
    """Type hints for Gatling parser output."""
    exec_count: int
    exec_http_count: int
    exec_with_check_count: int
    has_pause: bool
    has_feeder: bool
    has_assertions: bool
    has_max_duration: bool
    has_save_as: bool
    has_connection_timeout: bool
    has_http2_enabled: bool
    at_once_users_values: list[int]
    has_uniform_pause: bool
    has_fixed_pause: bool
    has_response_time_assertion: bool
    base_url_is_https: bool
    base_url_is_ip: bool
    base_url: str
    injections: list[dict]


class Severity(str, Enum):
    """Violation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def __lt__(self, other: Severity) -> bool:
        order = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}
        return order[self] < order[other]

    def __le__(self, other: Severity) -> bool:
        return self == other or self < other

    def __gt__(self, other: Severity) -> bool:
        return not self <= other

    def __ge__(self, other: Severity) -> bool:
        return not self < other


class Framework(str, Enum):
    """Supported performance testing frameworks."""

    JMETER = "jmeter"
    K6 = "k6"
    GATLING = "gatling"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Location:
    """Source location for a violation."""

    line: int | None = None
    column: int | None = None
    element_path: str | None = None  # For XML parsers (XPath-like)

    def __str__(self) -> str:
        if self.element_path:
            return self.element_path
        if self.line is not None and self.column is not None:
            return f"line {self.line}, col {self.column}"
        if self.line is not None:
            return f"line {self.line}"
        return "unknown location"


@dataclass(frozen=True)
class Violation:
    """A single rule violation found in a script.

    Frozen so that violations are treated as value objects. Use
    dataclasses.replace() to create modified copies (e.g. severity override).
    """

    rule_id: str
    severity: Severity
    message: str
    location: Location
    suggestion: str | None = None
    fix_example: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "location": {
                "line": self.location.line,
                "column": self.location.column,
                "element_path": self.location.element_path,
            },
            "suggestion": self.suggestion,
            "fix_example": self.fix_example,
        }


@dataclass
class ScriptIR:
    """Intermediate representation of a parsed performance test script.

    All parsers produce a ScriptIR. Rules consume parsed_data — a structured
    dict extracted once at parse time. Rules never re-scan raw content.

    raw_content is intentionally mutable: the auto-fixer updates it between
    sequential fix passes so each rule sees the output of the previous fix.
    """

    framework: Framework
    source_path: Path
    raw_content: str
    # Keys conform to the framework-specific TypedDict above
    # (JMeterParsedData, K6ParsedData, or GatlingParsedData).
    parsed_data: dict[str, object] = field(default_factory=dict)
