"""K6 rules K6001-K6006."""

from __future__ import annotations

import re

from perf_lint.ir.models import Framework, Location, ScriptIR, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry


@RuleRegistry.register
class K6001MissingThinkTime(BaseRule):
    rule_id = "K6001"
    name = "MissingThinkTime"
    description = "No sleep() calls found. Without think time, virtual users hammer the server as fast as possible, creating unrealistic load."
    severity = Severity.WARNING
    frameworks = [Framework.K6]
    tags = ("think-time", "realism")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        if not ir.parsed_data.get("has_sleep"):
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message="No sleep() calls found. Add think time to simulate realistic user behaviour.",
                    location=Location(line=1),
                    suggestion="Import sleep from 'k6' and add sleep(1) between requests to simulate user think time.",
                    fix_example="import { sleep } from 'k6';\n\nexport default function () {\n  http.get('https://example.com');\n  sleep(1); // 1 second think time\n}",
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        if ir.parsed_data.get("has_sleep"):
            return None  # Already has sleep — nothing to fix
        source = ir.raw_content

        # 1. Ensure sleep is imported from 'k6'
        k6_import_re = re.compile(r"(import\s*\{)([^}]*?)(\}\s*from\s*['\"]k6['\"])")
        k6_match = k6_import_re.search(source)
        if k6_match:
            imports_str = k6_match.group(2)
            if "sleep" not in imports_str:
                # Add sleep to existing import
                new_imports = imports_str.rstrip() + ", sleep"
                source = (
                    source[: k6_match.start(2)]
                    + new_imports
                    + source[k6_match.end(2) :]
                )
        else:
            # No k6 import found; add one at the top
            source = "import { sleep } from 'k6';\n" + source

        # 2. Insert sleep(1) before the closing brace of export default function
        func_re = re.compile(r"export\s+default\s+function\s*\w*\s*\([^)]*\)\s*\{")
        func_match = func_re.search(source)
        if not func_match:
            return None

        # NOTE: The brace-depth counter does not account for '{' or '}' characters
        # inside string literals, template literals, or comments. For the vast
        # majority of real K6 scripts this is safe; pathological cases may result
        # in sleep(1) being inserted at the wrong position.

        # Walk forward tracking brace depth to find the matching closing }
        start = func_match.end()
        depth = 1
        pos = start
        while pos < len(source) and depth > 0:
            ch = source[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1

        if depth != 0:
            return None  # Unmatched braces — bail out

        closing_pos = pos - 1
        # Determine indentation of the closing brace line
        line_start = source.rfind("\n", 0, closing_pos) + 1
        indent = len(source[line_start:closing_pos]) - len(
            source[line_start:closing_pos].lstrip()
        )
        pad = " " * (indent + 2)
        source = source[:closing_pos] + f"{pad}sleep(1);\n" + source[closing_pos:]
        return source


@RuleRegistry.register
class K6004MissingThresholds(BaseRule):
    rule_id = "K6004"
    name = "MissingThresholds"
    description = "No thresholds defined in options. Without thresholds, K6 won't fail the test when SLOs are breached."
    severity = Severity.WARNING
    frameworks = [Framework.K6]
    tags = ("thresholds", "slo", "ci-integration")
    fixable = True

    _THRESHOLDS_BLOCK = (
        "  thresholds: {\n"
        "    http_req_duration: ['p(95)<500'],\n"
        "    http_req_failed: ['rate<0.01'],\n"
        "  },\n"
    )

    def check(self, ir: ScriptIR) -> list[Violation]:
        if not ir.parsed_data.get("has_thresholds"):
            return [
                Violation(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message="No thresholds defined. Add thresholds to define pass/fail criteria and enforce SLOs in CI.",
                    location=Location(line=1),
                    suggestion="Define thresholds in the options object to set performance SLOs.",
                    fix_example="export const options = {\n  thresholds: {\n    http_req_duration: ['p(95)<500'], // 95% of requests must complete < 500ms\n    http_req_failed: ['rate<0.01'],    // Error rate must be < 1%\n  },\n};",
                )
            ]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        source = ir.raw_content

        # Try to inject into an existing options object
        options_re = re.compile(r"export\s+const\s+options\s*=\s*\{")
        options_match = options_re.search(source)
        if options_match:
            insert_pos = options_match.end()
            source = source[:insert_pos] + "\n" + self._THRESHOLDS_BLOCK + source[insert_pos:]
        else:
            # No options block — prepend a minimal one
            options_block = (
                "export const options = {\n"
                + self._THRESHOLDS_BLOCK
                + "};\n\n"
            )
            source = options_block + source

        return source


@RuleRegistry.register
class K6007MissingTeardown(BaseRule):
    rule_id = "K6007"
    name = "MissingTeardown"
    description = (
        "setup() is exported but teardown() is missing. "
        "Data or state created in setup() (users, orders, sessions) will leak "
        "into the target system. teardown() is the contract for cleanup."
    )
    severity = Severity.WARNING
    frameworks = [Framework.K6]
    tags = ("lifecycle", "correctness")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        if ir.parsed_data.get("has_setup") and not ir.parsed_data.get("has_teardown"):
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="setup() is defined but teardown() is missing. Clean up test data to avoid polluting the target system.",
                location=Location(line=1),
                suggestion="Export a teardown(data) function to clean up any state created in setup().",
                fix_example="export function teardown(data) {\n  // Clean up: delete created users, sessions, orders, etc.\n  http.del(`${BASE_URL}/api/users/${data.userId}`);\n}",
            )]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        if ir.parsed_data.get("has_teardown"):
            return None
        source = ir.raw_content
        teardown = (
            "\nexport function teardown(data) {\n"
            "  // TODO: clean up resources created in setup()\n"
            "  // e.g. http.del(`${BASE_URL}/api/users/${data.userId}`);\n"
            "}\n"
        )
        return source.rstrip() + "\n" + teardown


@RuleRegistry.register
class K6012MissingGracefulStop(BaseRule):
    rule_id = "K6012"
    name = "MissingGracefulStop"
    description = (
        "stages or scenarios defined but no gracefulStop configured. "
        "Without graceful stop, K6 kills VUs mid-request at test end, "
        "producing artificial errors that inflate the final error rate."
    )
    severity = Severity.WARNING
    frameworks = [Framework.K6]
    tags = ("lifecycle", "correctness")
    fixable = True

    def check(self, ir: ScriptIR) -> list[Violation]:
        has_stages = bool(ir.parsed_data.get("stages"))
        has_scenarios = ir.parsed_data.get("has_scenarios", False)
        if (has_stages or has_scenarios) and not ir.parsed_data.get("has_graceful_stop"):
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="Test uses stages/scenarios but has no gracefulStop. VUs will be killed mid-request, inflating error rates.",
                location=Location(line=None),
                suggestion="Add gracefulStop and gracefulRampDown to your options to allow in-flight requests to complete.",
                fix_example="export const options = {\n  stages: [...],\n  gracefulStop: '30s',\n  gracefulRampDown: '30s',\n};",
            )]
        return []

    def apply_fix(self, ir: ScriptIR) -> str | None:
        source = ir.raw_content
        if "gracefulStop" in source or "gracefulRampDown" in source:
            return None
        options_re = re.compile(r"export\s+const\s+options\s*=\s*\{")
        m = options_re.search(source)
        if not m:
            return None
        insert_pos = m.end()
        graceful_block = "\n  gracefulStop: '30s',\n  gracefulRampDown: '30s',"
        return source[:insert_pos] + graceful_block + source[insert_pos:]


@RuleRegistry.register
class K6013ClosedModelOnly(BaseRule):
    rule_id = "K6013"
    name = "ClosedModelOnly"
    description = (
        "Test uses VU-based stages (closed model) with no arrival-rate executor. "
        "Under slow responses, throughput drops because VUs queue. "
        "Consider constant-arrival-rate for throughput-based SLOs."
    )
    severity = Severity.INFO
    frameworks = [Framework.K6]
    tags = ("load-model", "realism")

    def check(self, ir: ScriptIR) -> list[Violation]:
        has_stages = bool(ir.parsed_data.get("stages"))
        has_arrival = ir.parsed_data.get("has_arrival_rate", False)
        if has_stages and not has_arrival:
            return [Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="Test uses VU-based (closed model) stages. For RPS-based SLOs, consider constant-arrival-rate executor.",
                location=Location(line=None),
                suggestion="Use a constant-arrival-rate scenario for throughput-based load goals.",
                fix_example="export const options = {\n  scenarios: {\n    api_load: {\n      executor: 'constant-arrival-rate',\n      rate: 100,      // 100 RPS\n      timeUnit: '1s',\n      duration: '5m',\n      preAllocatedVUs: 50,\n    },\n  },\n};",
            )]
        return []


