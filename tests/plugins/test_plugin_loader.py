"""Tests for the plugin loading system."""

from __future__ import annotations

from pathlib import Path

from perf_lint.config.schema import CustomRuleConfig, PerfLintConfig
from perf_lint.plugins.loader import load_plugins
from perf_lint.rules.base import RuleRegistry


class TestPluginLoader:
    def test_load_file_plugin(self, tmp_path: Path) -> None:
        """Test that a custom rule file is loaded and registered."""
        # Write a minimal plugin
        plugin_file = tmp_path / "my_rule.py"
        plugin_file.write_text(
            """
from perf_lint.ir.models import Framework, Location, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry

@RuleRegistry.register
class PLUGIN001TestRule(BaseRule):
    rule_id = "PLUGIN001"
    name = "TestRule"
    description = "Test plugin rule"
    severity = Severity.INFO
    frameworks = [Framework.K6]
    tags = []

    def check(self, ir):
        return []
"""
        )

        config = PerfLintConfig(
            custom_rules=[CustomRuleConfig(path=str(plugin_file))]
        )

        # Remove any pre-existing registration
        RuleRegistry.get_all()
        loaded = load_plugins(config)

        assert str(plugin_file) in loaded
        assert "PLUGIN001" in RuleRegistry.get_all()

    def test_load_glob_plugin(self, tmp_path: Path) -> None:
        """Test that glob patterns in plugin paths are expanded."""
        plugin_dir = tmp_path / "rules"
        plugin_dir.mkdir()

        plugin_file = plugin_dir / "rule_glob.py"
        plugin_file.write_text(
            """
from perf_lint.ir.models import Framework, Location, Severity, Violation
from perf_lint.rules.base import BaseRule, RuleRegistry

@RuleRegistry.register
class GLOBRULE001(BaseRule):
    rule_id = "GLOBRULE001"
    name = "GlobRule"
    description = "Glob test"
    severity = Severity.INFO
    frameworks = [Framework.GATLING]
    tags = []

    def check(self, ir):
        return []
"""
        )

        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = PerfLintConfig(
                custom_rules=[CustomRuleConfig(path="rules/*.py")]
            )
            loaded = load_plugins(config)
            assert len(loaded) >= 1
            assert "GLOBRULE001" in RuleRegistry.get_all()
        finally:
            os.chdir(old_cwd)

    def test_bad_plugin_does_not_crash(self, tmp_path: Path) -> None:
        """Malformed plugins should be reported but not crash the tool."""
        plugin_file = tmp_path / "broken_rule.py"
        plugin_file.write_text("this is not valid python code !!!")

        config = PerfLintConfig(
            custom_rules=[CustomRuleConfig(path=str(plugin_file))]
        )
        # Should not raise
        loaded = load_plugins(config)
        assert str(plugin_file) not in loaded

    def test_sample_plugin_can_be_loaded(self) -> None:
        """Test the actual sample plugin from the test fixtures."""
        plugin_path = (
            Path(__file__).parent / "sample_plugin" / "custom_rule.py"
        )
        config = PerfLintConfig(
            custom_rules=[CustomRuleConfig(path=str(plugin_path))]
        )
        load_plugins(config)
        assert "CUSTOM001" in RuleRegistry.get_all()
