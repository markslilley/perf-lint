"""Sample custom rule plugin for testing perf-lint's plugin system.

This demonstrates how to write a custom rule that perf-lint will discover
and execute via the plugin system.
"""

from __future__ import annotations

from perf_lint.ir.models import Framework, Location, ScriptIR, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry


@RuleRegistry.register
class CUSTOM001ExampleRule(BaseRule):
    """Example custom rule — detects any K6 script."""

    rule_id = "CUSTOM001"
    name = "ExampleCustomRule"
    description = "Example custom rule — always triggers on K6 scripts for testing."
    severity = Severity.INFO
    frameworks = [Framework.K6]
    tags = ["custom", "example"]

    def check(self, ir: ScriptIR) -> list[Violation]:
        return [
            Violation(
                rule_id=self.rule_id,
                severity=self.severity,
                message="Custom rule triggered (this is a test).",
                location=Location(line=1),
                suggestion="This is just an example custom rule.",
            )
        ]
