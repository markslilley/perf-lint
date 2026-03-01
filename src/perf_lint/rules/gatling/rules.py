"""Gatling rules GAT001-GAT005."""

from __future__ import annotations

import re

from perf_lint.ir.models import Framework, Location, ScriptIR, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry


@RuleRegistry.register
class GAT001MissingPause(BaseRule):
    rule_id = "GAT001"
    name = "MissingPause"
    description = "Scenario has exec() calls but no pause() calls. Without think time, virtual users hammer the server unrealistically."
    severity = Severity.WARNING
    frameworks = [Framework.GATLING]
    tags = ("think-time", "realism")

    def check(self, ir: ScriptIR) -> list[Violation]:
        exec_count = ir.parsed_data.get("exec_count", 0)
        has_pause = ir.parsed_data.get("has_pause", False)
        if exec_count > 0 and not has_pause:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=f"Found {exec_count} exec() call(s) but no pause() calls. Add think time to simulate realistic user behaviour.",
                    location=Location(line=1),
                    suggestion="Add .pause(1) or .pause(1, 3) between exec() calls to simulate user think time.",
                    fix_example=".exec(http('Homepage').get('/'))\n.pause(1, 3)  // Pause between 1 and 3 seconds\n.exec(http('Search').get('/search?q=test'))",
                )
            ]
        return []


@RuleRegistry.register
class GAT005MissingFeeder(BaseRule):
    rule_id = "GAT005"
    name = "MissingFeeder"
    description = "Multiple exec() calls found but no feeder (data source) configured. All virtual users will send identical requests."
    severity = Severity.INFO
    frameworks = [Framework.GATLING]
    tags = ("parameterization", "realism")

    def check(self, ir: ScriptIR) -> list[Violation]:
        exec_count = ir.parsed_data.get("exec_count", 0)
        has_feeder = ir.parsed_data.get("has_feeder", False)
        if exec_count > 1 and not has_feeder:
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=f"Found {exec_count} exec() calls but no feeder/data source. Consider parameterising test data.",
                    location=Location(line=1),
                    suggestion="Add a CSV feeder or other data source to vary request parameters across virtual users.",
                    fix_example='val feeder = csv("test-data.csv").random\n\nval scn = scenario("My Scenario")\n  .feed(feeder)\n  .exec(http("Request").get("/api/users/${userId}"))',
                )
            ]
        return []


@RuleRegistry.register
class GAT011AssertionLacksThreshold(BaseRule):
    rule_id = "GAT011"
    name = "AssertionLacksThreshold"
    description = (
        "Assertions present but none reference responseTime or failedRequests. "
        "Assertions without SLO thresholds (e.g. percentile response time, error rate) "
        "do not enforce meaningful performance requirements."
    )
    severity = Severity.INFO
    frameworks = [Framework.GATLING]
    tags = ("assertions", "slo")

    def check(self, ir: ScriptIR) -> list[Violation]:
        if ir.parsed_data.get("has_assertions") and not ir.parsed_data.get("has_response_time_assertion"):
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="Assertions found but none enforce response time or error rate SLOs.",
                location=Location(line=None),
                suggestion="Add responseTime.percentile(95).lt(500) and failedRequests.percent.lt(1) assertions.",
                fix_example=".assertions(\n  global.responseTime.percentile(95).lt(500),\n  global.failedRequests.percent.lt(1)\n)",
            )]
        return []


@RuleRegistry.register
class GAT013MissingHTTP2(BaseRule):
    rule_id = "GAT013"
    name = "MissingHTTP2"
    description = (
        "HTTPS base URL configured but HTTP/2 not enabled. Modern web backends expect "
        "HTTP/2 multiplexing. Without it, Gatling opens a new connection per request, "
        "over-stressing the connection layer rather than the application."
    )
    severity = Severity.INFO
    frameworks = [Framework.GATLING]
    tags = ("http", "realism", "configuration")
    fixable = True

    def apply_fix(self, ir: ScriptIR) -> str | None:
        source = ir.raw_content
        if re.search(r'\.enableHttp2\b', source):
            return None

        # Insert after .baseUrl line
        base_url_re = re.compile(r'(\.baseUrl\s*\([^)]*\))', re.MULTILINE)
        m = base_url_re.search(source)
        if m:
            return source[:m.end()] + "\n    .enableHttp2" + source[m.end():]
        return None

    def check(self, ir: ScriptIR) -> list[Violation]:
        if (
            ir.parsed_data.get("exec_http_count", 0) > 0
            and ir.parsed_data.get("base_url_is_https")
            and not ir.parsed_data.get("has_http2_enabled")
        ):
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="HTTPS endpoint detected but HTTP/2 not enabled. Enable HTTP/2 to match real browser connection behaviour.",
                location=Location(line=None),
                suggestion="Add .enableHttp2 to your HTTP protocol configuration.",
                fix_example="val httpProtocol = http\n  .baseUrl(baseUrl)\n  .enableHttp2",
            )]
        return []
