"""Base rule class and rule registry for perf-lint."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from perf_lint.ir.models import Framework, Severity, Violation

if TYPE_CHECKING:
    from perf_lint.ir.models import ScriptIR


class RuleRegistry:
    """Singleton registry for all rules.

    Rules are auto-registered via @RuleRegistry.register decorator on import.
    """

    _rules: ClassVar[dict[str, type[BaseRule]]] = {}

    @classmethod
    def register(cls, rule_class: type[BaseRule]) -> type[BaseRule]:
        """Register a rule class. Used as a class decorator."""
        cls._rules[rule_class.rule_id] = rule_class
        return rule_class

    @classmethod
    def get_all(cls) -> dict[str, type[BaseRule]]:
        """Return all registered rules."""
        return dict(cls._rules)

    @classmethod
    def get(cls, rule_id: str) -> type[BaseRule] | None:
        """Return a rule class by ID, or None."""
        return cls._rules.get(rule_id)

    @classmethod
    def get_for_framework(cls, framework: Framework) -> list[type[BaseRule]]:
        """Return all rules applicable to a framework."""
        return [r for r in cls._rules.values() if framework in r.frameworks]

    @classmethod
    def clear(cls) -> None:
        """Clear all registered rules. Used in tests."""
        cls._rules.clear()


class BaseRule(ABC):
    """Abstract base class for all perf-lint rules.

    Rules use class attributes (not instance) for metadata, enabling registry
    introspection without instantiation.
    """

    rule_id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str]
    severity: ClassVar[Severity]
    frameworks: ClassVar[list[Framework]]
    tags: ClassVar[tuple[str, ...]] = ()
    fixable: ClassVar[bool] = False
    tier: ClassVar[str] = "free"  # "free" | "pro" | "team"

    @abstractmethod
    def check(self, ir: ScriptIR) -> list[Violation]:
        """Run this rule against an IR and return any violations found."""
        ...

    def apply_fix(self, ir: ScriptIR) -> str | None:
        """Return rewritten source with this rule's violation corrected.

        Return None if the fix is not safe or not implemented for this rule.
        Subclasses override this and set fixable = True to provide auto-fix capability.
        """
        return None

    @classmethod
    def to_dict(cls) -> dict:
        """Return rule metadata as a dict."""
        return {
            "rule_id": cls.rule_id,
            "name": cls.name,
            "description": cls.description,
            "severity": cls.severity.value,
            "frameworks": [f.value for f in cls.frameworks],
            "tags": list(cls.tags),
            "tier": cls.tier,
        }
