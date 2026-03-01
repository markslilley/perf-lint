"""Gatling (.scala/.kt) parser for perf-lint.

Regex-based extraction — method call syntax is the same in Scala and Kotlin.
"""

from __future__ import annotations

import re
from pathlib import Path

from perf_lint.ir.models import Framework, ScriptIR
from perf_lint.parsers.base import BaseParser

# Gatling detection: look for Simulation class or gatling import
_GATLING_IMPORT_RE = re.compile(r"""import\s+io\.gatling""", re.MULTILINE)
_SIMULATION_CLASS_RE = re.compile(r"""class\s+\w+\s+extends\s+Simulation""", re.MULTILINE)

# Base URL patterns
_BASE_URL_RE = re.compile(
    r"""baseUrl\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)
_IP_RE = re.compile(r"""https?://\d{1,3}(\.\d{1,3}){3}""")

# Assertion detection
_ASSERTION_RE = re.compile(r"""\.assertions?\s*\(""", re.MULTILINE)

# Pause detection
_PAUSE_RE = re.compile(r"""\.pause\s*\(""", re.MULTILINE)

# Exec detection
_EXEC_RE = re.compile(r"""\.exec\s*\(""", re.MULTILINE)

# Feeder detection
_FEEDER_RE = re.compile(
    r"""\.feed\s*\(|csv\s*\(|jsonFile\s*\(|feeder\s*\(""",
    re.MULTILINE,
)

# Ramp-up patterns: rampUsers(N) during (Xseconds)
_RAMP_USERS_RE = re.compile(
    r"""rampUsers\s*\(\s*(\d+)\s*\)\s*\.?\s*(?:during|over)\s*\(\s*(\d+)""",
    re.MULTILINE,
)
_AT_ONCE_RE = re.compile(r"""atOnceUsers\s*\(\s*(\d+)\s*\)""", re.MULTILINE)

# GAT006-GAT013 patterns
_MAX_DURATION_RE = re.compile(r"""\.maxDuration\s*\(""", re.MULTILINE)
_CHECK_RE = re.compile(r"""\.check\s*\(""", re.MULTILINE)
_EXEC_HTTP_RE = re.compile(r"""\.exec\s*\(\s*http\s*\(""", re.MULTILINE)
# Tempered greedy token prevents matching across .exec() boundaries.
# Limitation: fragile on deeply nested Scala DSL chains (>3 levels deep).
# In practice, standard Gatling simulation patterns are reliably detected.
_EXEC_WITH_CHECK_RE = re.compile(
    r"\.exec\s*\(\s*http\s*\((?:(?!\.exec\s*\()[\s\S])*?\.check\s*\(",
    re.MULTILINE,
)
_SAVE_AS_RE = re.compile(r"""\.saveAs\s*\(""", re.MULTILINE)
_CONNECTION_TIMEOUT_RE = re.compile(
    r"""\.(?:connectionTimeout|readTimeout)\s*\(""", re.MULTILINE
)
_ENABLE_HTTP2_RE = re.compile(r"""\.enableHttp2\b""", re.MULTILINE)
_PAUSE_UNIFORM_RE = re.compile(r"""\.pause\s*\(\s*\d+\s*,\s*\d+""", re.MULTILINE)
_PAUSE_FIXED_RE = re.compile(r"""\.pause\s*\(\s*\d+\s*\)""", re.MULTILINE)
_RESPONSE_TIME_ASSERTION_RE = re.compile(
    r"""responseTime|failedRequests""", re.MULTILINE
)
_HTTPS_BASE_URL_RE = re.compile(
    r"""baseUrl\s*\(\s*['"]https://""", re.MULTILINE
)


class GatlingParser(BaseParser):
    """Parses Gatling Scala/Kotlin simulation files into ScriptIR."""

    @property
    def framework(self) -> Framework:
        return Framework.GATLING

    @property
    def supported_extensions(self) -> list[str]:
        return [".scala", ".kt"]

    def _can_parse_content(self, path: Path) -> bool:
        """Detect Gatling simulations via import or class signature."""
        try:
            content = self._read_and_cache(path)
            return bool(
                _GATLING_IMPORT_RE.search(content)
                or _SIMULATION_CLASS_RE.search(content)
            )
        except OSError:
            return False

    def parse(self, path: Path) -> ScriptIR:
        # Reuse content read during can_parse() to avoid a second I/O round-trip.
        content = self._pop_cached_content(path) or self._read_file(path)
        parsed_data = self._extract(content)

        return ScriptIR(
            framework=self.framework,
            source_path=path,
            raw_content=content,
            parsed_data=parsed_data,
        )

    def _extract(self, content: str) -> dict:
        """Extract Gatling-relevant data from simulation content."""
        # Base URL
        base_url_match = _BASE_URL_RE.search(content)
        base_url = base_url_match.group(1) if base_url_match else None
        base_url_is_ip = bool(base_url and _IP_RE.match(base_url))

        exec_count = len(_EXEC_RE.findall(content))
        pause_count = len(_PAUSE_RE.findall(content))

        # Ramp injection data
        injections = []
        for match in _RAMP_USERS_RE.finditer(content):
            users = int(match.group(1))
            duration_secs = int(match.group(2))
            injections.append({"users": users, "duration_secs": duration_secs, "type": "ramp"})
        for match in _AT_ONCE_RE.finditer(content):
            users = int(match.group(1))
            injections.append({"users": users, "duration_secs": 0, "type": "at_once"})

        exec_http_count = len(_EXEC_HTTP_RE.findall(content))
        exec_with_check_count = len(_EXEC_WITH_CHECK_RE.findall(content))
        at_once_users_values = [
            i["users"] for i in injections if i["type"] == "at_once"
        ]

        return {
            "base_url": base_url,
            "base_url_is_ip": base_url_is_ip,
            "has_assertions": bool(_ASSERTION_RE.search(content)),
            "has_pause": pause_count > 0,
            "exec_count": exec_count,
            "pause_count": pause_count,
            "has_feeder": bool(_FEEDER_RE.search(content)),
            "injections": injections,
            "has_max_duration": bool(_MAX_DURATION_RE.search(content)),
            "exec_http_count": exec_http_count,
            "exec_with_check_count": exec_with_check_count,
            "has_save_as": bool(_SAVE_AS_RE.search(content)),
            "has_connection_timeout": bool(
                _CONNECTION_TIMEOUT_RE.search(content)
            ),
            "has_http2_enabled": bool(_ENABLE_HTTP2_RE.search(content)),
            "at_once_users_values": at_once_users_values,
            "has_uniform_pause": bool(_PAUSE_UNIFORM_RE.search(content)),
            "has_fixed_pause": bool(_PAUSE_FIXED_RE.search(content)),
            "has_response_time_assertion": bool(
                _RESPONSE_TIME_ASSERTION_RE.search(content)
            ),
            "base_url_is_https": bool(_HTTPS_BASE_URL_RE.search(content)),
        }
