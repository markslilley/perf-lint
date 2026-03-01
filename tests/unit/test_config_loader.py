"""Tests for config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from perf_lint.config.loader import find_config_file, load_config
from perf_lint.config.schema import PerfLintConfig, RuleConfig


class TestPerfLintConfig:
    def test_default_config(self) -> None:
        config = PerfLintConfig.default()
        assert config.severity_threshold == "warning"
        assert config.version == 1
        assert config.rules == {}
        assert config.custom_rules == []
        assert config.ignore_paths == []

    def test_invalid_severity_threshold(self) -> None:
        with pytest.raises(ValidationError):
            PerfLintConfig(severity_threshold="critical")

    def test_rule_config_default(self) -> None:
        rule = RuleConfig()
        assert rule.enabled is True
        assert rule.severity is None

    def test_rule_config_with_severity(self) -> None:
        rule = RuleConfig(severity="error")
        assert rule.severity == "error"

    def test_rule_config_invalid_severity(self) -> None:
        with pytest.raises(ValidationError):
            RuleConfig(severity="critical")


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.yml"
        config_data = {
            "version": 1,
            "severity_threshold": "error",
            "rules": {
                "JMX001": {"enabled": False},
                "K6001": {"severity": "error"},
            },
        }
        config_file.write_text(yaml.dump(config_data))

        config = load_config(config_file)
        assert config.severity_threshold == "error"
        assert config.rules["JMX001"].enabled is False
        assert config.rules["K6001"].severity == "error"

    def test_load_from_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.toml"
        config_file.write_text(
            '[rules.JMX001]\nenabled = false\n'
        )
        config = load_config(config_file)
        assert config.rules["JMX001"].enabled is False

    def test_load_returns_default_when_no_file(self) -> None:
        config = load_config(Path("/nonexistent/path/.perf-lint.yml"))
        assert config == PerfLintConfig.default()

    def test_load_none_returns_default(self, tmp_path: Path) -> None:
        # Change to tmp_path where there's no config
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            config = load_config(None)
            assert config.severity_threshold == "warning"
        finally:
            os.chdir(old_cwd)

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.yml"
        config_file.write_text("")
        config = load_config(config_file)
        assert config == PerfLintConfig.default()


class TestFindConfigFile:
    def test_finds_yml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.yml"
        config_file.write_text("version: 1")
        found = find_config_file(tmp_path)
        assert found == config_file

    def test_finds_yaml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.yaml"
        config_file.write_text("version: 1")
        found = find_config_file(tmp_path)
        assert found == config_file

    def test_finds_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.toml"
        config_file.write_text('version = 1\n')
        found = find_config_file(tmp_path)
        assert found == config_file

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        found = find_config_file(tmp_path)
        assert found is None

    def test_walks_up_directory(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.yml"
        config_file.write_text("version: 1")
        subdir = tmp_path / "a" / "b" / "c"
        subdir.mkdir(parents=True)
        found = find_config_file(subdir)
        assert found == config_file
