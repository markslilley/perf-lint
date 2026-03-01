"""K6 (.js/.ts) parser for perf-lint.

Regex-based extraction — no AST dependency for MVP.
Auto-detects K6 scripts via 'from k6...' import signature.
"""

from __future__ import annotations

import re
from pathlib import Path

from perf_lint.ir.models import Framework, ScriptIR
from perf_lint.parsers.base import BaseParser

# Patterns for K6 feature detection
_K6_IMPORT_RE = re.compile(r"""from\s+['"]k6""", re.MULTILINE)
_SLEEP_RE = re.compile(r"""\bsleep\s*\(""", re.MULTILINE)
_CHECK_RE = re.compile(r"""\bcheck\s*\(""", re.MULTILINE)
_THRESHOLD_RE = re.compile(r"""\bthresholds\s*:""", re.MULTILINE)
_ERROR_HANDLING_RE = re.compile(
    r"""try\s*\{|\.catch\s*\(|if\s*\(\s*res\.status\s*[><=!]|\bif\s*\(.*error|\bif\s*\(!?\s*ok\b""",
    re.MULTILINE | re.IGNORECASE,
)
# Detect any http.method() call
_HTTP_CALL_ANY_RE = re.compile(
    r"""http\.(get|post|put|del|patch|head|options)\s*\(""",
    re.MULTILINE | re.IGNORECASE,
)
# Detect http.method() with a literal string URL (for hardcoded IP check)
_HTTP_CALL_LITERAL_RE = re.compile(
    r"""http\.(get|post|put|del|patch|head|options)\s*\(\s*['"]([^'"]+)['"]""",
    re.MULTILINE | re.IGNORECASE,
)
_IP_URL_RE = re.compile(r"""https?://\d{1,3}(\.\d{1,3}){3}""")

# Lifecycle & structure detection
_SETUP_RE = re.compile(r"""export\s+function\s+setup\s*\(""", re.MULTILINE)
_TEARDOWN_RE = re.compile(r"""export\s+function\s+teardown\s*\(""", re.MULTILINE)
_GROUP_RE = re.compile(r"""\bgroup\s*\(""", re.MULTILINE)
_TAGS_IN_HTTP_RE = re.compile(r"""http\.\w+\s*\([^)]*tags\s*:""", re.MULTILINE | re.DOTALL)
_SHARED_ARRAY_RE = re.compile(r"""SharedArray""", re.MULTILINE)
_GRACEFUL_STOP_RE = re.compile(r"""\bgracefulStop\b|\bgracefulRampDown\b""", re.MULTILINE)
_SCENARIOS_RE = re.compile(r"""\bscenarios\s*:""", re.MULTILINE)
_ARRIVAL_RATE_RE = re.compile(r"""constant-arrival-rate|ramping-arrival-rate""", re.MULTILINE)
_HARDCODED_AUTH_RE = re.compile(
    r"""headers\s*:.*?['"](Authorization)['"]\s*:\s*['"](?!__ENV|`\$\{)(Bearer\s+[A-Za-z0-9._-]{20,}|Basic\s+[A-Za-z0-9+/=]{10,})""",
    re.MULTILINE | re.DOTALL,
)
_TREND_RATE_COUNTER_GAUGE_RE = re.compile(r"""\b(?:new\s+)?(?:Trend|Rate|Counter|Gauge)\s*\(""", re.MULTILINE)
_HTTP_TIMEOUT_RE = re.compile(r"""timeout\s*:\s*['"]?\d""", re.MULTILINE)
_OPEN_CALL_RE = re.compile(r"""\bopen\s*\(""", re.MULTILINE)

# Stage pattern: { duration: '...', target: N }
_STAGE_RE = re.compile(
    r"""\{\s*duration\s*:\s*['"](\d+)([smh])['"]\s*,\s*target\s*:\s*(\d+)\s*\}""",
    re.MULTILINE,
)


def _duration_to_secs(value: int, unit: str) -> int:
    """Convert duration value+unit to seconds."""
    multipliers = {"s": 1, "m": 60, "h": 3600}
    return value * multipliers.get(unit, 1)


class K6Parser(BaseParser):
    """Parses K6 JavaScript/TypeScript files into ScriptIR."""

    @property
    def framework(self) -> Framework:
        return Framework.K6

    @property
    def supported_extensions(self) -> list[str]:
        return [".js", ".ts"]

    def _can_parse_content(self, path: Path) -> bool:
        """Detect K6 scripts via import signature."""
        try:
            content = self._read_and_cache(path)
            return bool(_K6_IMPORT_RE.search(content))
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
        """Extract K6-relevant data from script content."""
        # Cap content scanned by heavy regex patterns to prevent ReDoS on adversarial input
        _scan_content = content[:1_048_576] if len(content) > 1_048_576 else content

        # Collect all http calls (including template literal URLs)
        literal_calls: dict[int, dict] = {}
        for match in _HTTP_CALL_LITERAL_RE.finditer(content):
            url = match.group(2)
            literal_calls[match.start()] = {
                "method": match.group(1).upper(),
                "url": url,
                "is_hardcoded_ip": bool(_IP_URL_RE.match(url)),
            }

        http_calls = []
        for match in _HTTP_CALL_ANY_RE.finditer(content):
            if match.start() in literal_calls:
                http_calls.append(literal_calls[match.start()])
            else:
                http_calls.append({
                    "method": match.group(1).upper(),
                    "url": None,
                    "is_hardcoded_ip": False,
                })

        # Extract stages
        stages = []
        for match in _STAGE_RE.finditer(content):
            duration_val = int(match.group(1))
            duration_unit = match.group(2)
            target = int(match.group(3))
            stages.append({
                "duration_secs": _duration_to_secs(duration_val, duration_unit),
                "target": target,
            })

        return {
            "has_sleep": bool(_SLEEP_RE.search(content)),
            "has_check": bool(_CHECK_RE.search(content)),
            "has_thresholds": bool(_THRESHOLD_RE.search(content)),
            "has_error_handling": bool(_ERROR_HANDLING_RE.search(content)),
            "http_calls": http_calls,
            "stages": stages,
            "has_setup": bool(_SETUP_RE.search(content)),
            "has_teardown": bool(_TEARDOWN_RE.search(content)),
            "has_group": bool(_GROUP_RE.search(content)),
            "has_request_tags": bool(_TAGS_IN_HTTP_RE.search(_scan_content)),
            "uses_shared_array": bool(_SHARED_ARRAY_RE.search(content)),
            "has_graceful_stop": bool(_GRACEFUL_STOP_RE.search(content)),
            "has_scenarios": bool(_SCENARIOS_RE.search(content)),
            "has_arrival_rate": bool(_ARRIVAL_RATE_RE.search(content)),
            "has_hardcoded_auth_token": bool(_HARDCODED_AUTH_RE.search(_scan_content)),
            "has_custom_metrics": bool(_TREND_RATE_COUNTER_GAUGE_RE.search(content)),
            "has_http_timeout": bool(_HTTP_TIMEOUT_RE.search(content)),
            "has_open_call": bool(_OPEN_CALL_RE.search(content)),
            "http_call_count": len(http_calls),
        }
