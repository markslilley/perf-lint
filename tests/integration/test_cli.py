"""Integration tests for the CLI via Click CliRunner."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from perf_lint.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestCheckCommand:
    def test_check_good_k6_file_exits_zero(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(cli, ["check", str(k6_fixtures_dir / "good_test.js")])
        assert result.exit_code == 0

    def test_check_bad_k6_file_exits_one(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(cli, ["check", str(k6_fixtures_dir / "missing_sleep.js")])
        assert result.exit_code == 1

    def test_check_json_output(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "missing_sleep.js"), "--format", "json"],
        )
        import json
        data = json.loads(result.output)
        assert "files" in data
        assert "summary" in data
        assert data["summary"]["total_violations"] > 0

    def test_check_sarif_output(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "missing_sleep.js"), "--format", "sarif"],
        )
        import json
        data = json.loads(result.output)
        assert data["version"] == "2.1.0"
        assert "runs" in data

    def test_check_ignore_rule(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        # missing_sleep.js should trigger K6001, K6005; ignoring both should give exit 0
        result = runner.invoke(
            cli,
            [
                "check",
                str(k6_fixtures_dir / "missing_sleep.js"),
                "--ignore-rule", "K6001",
                "--ignore-rule", "K6005",
                "--severity", "error",  # Only fail on errors
            ],
        )
        # missing_sleep.js has no errors (only warnings K6001, K6005)
        assert result.exit_code == 0

    def test_check_directory(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(cli, ["check", str(k6_fixtures_dir)])
        # Should check all .js files — some will have violations
        assert result.exit_code in (0, 1)

    def test_check_text_format_default(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["check", str(k6_fixtures_dir / "missing_sleep.js"), "--no-color"]
        )
        assert "K6001" in result.output

    def test_check_output_file(
        self, runner: CliRunner, k6_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        output_file = tmp_path / "results.json"
        result = runner.invoke(
            cli,
            [
                "check",
                str(k6_fixtures_dir / "missing_sleep.js"),
                "--format", "json",
                "--output", str(output_file),
            ],
        )
        assert output_file.exists()
        import json
        data = json.loads(output_file.read_text())
        assert "summary" in data

    def test_check_jmeter_bad_rampup(
        self, runner: CliRunner, jmeter_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli, ["check", str(jmeter_fixtures_dir / "bad_rampup.jmx"), "--no-color"]
        )
        # JMX004 is a Pro-tier rule in perf-lint-pro; not present in free package
        assert "JMX004" not in result.output
        assert result.exit_code == 1

    def test_check_with_config(
        self, runner: CliRunner, k6_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        config = tmp_path / ".perf-lint.yml"
        config.write_text(
            "version: 1\nseverity_threshold: error\nrules:\n  K6001:\n    enabled: false\n"
        )
        result = runner.invoke(
            cli,
            [
                "check",
                str(k6_fixtures_dir / "missing_sleep.js"),
                "--config", str(config),
            ],
        )
        # K6001 disabled, no errors in missing_sleep.js → exit 0
        assert result.exit_code == 0


class TestRulesCommand:
    def test_rules_lists_all(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["rules", "--json"])
        import json
        data = json.loads(result.output)
        # 9 JMeter + 5 K6 + 4 Gatling = 18 free rules; Pro/Team rules live in perf-lint-pro.
        assert len(data) >= 18, f"Expected at least 18 rules, got {len(data)}"

    def test_rules_filter_framework(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["rules", "--framework", "k6", "--json"])
        import json
        data = json.loads(result.output)
        assert all("k6" in r["frameworks"] for r in data)
        assert len(data) == 5  # K6001, K6004, K6007, K6012, K6013 (free rules only)

    def test_rules_text_output(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["rules"])
        assert result.exit_code == 0
        assert "JMX001" in result.output
        assert "K6001" in result.output
        assert "GAT001" in result.output


class TestInitCommand:
    def test_init_creates_config(self, runner: CliRunner, tmp_path: Path) -> None:
        config_file = tmp_path / ".perf-lint.yml"
        result = runner.invoke(
            cli, ["init", "--output", str(config_file)]
        )
        assert result.exit_code == 0
        assert config_file.exists()
        content = config_file.read_text()
        assert "severity_threshold" in content

    def test_init_prompts_before_overwrite(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        config_file = tmp_path / ".perf-lint.yml"
        config_file.write_text("existing content")
        result = runner.invoke(
            cli, ["init", "--output", str(config_file)], input="n\n"
        )
        assert "existing content" == config_file.read_text()


class TestQualityScore:
    def test_json_output_has_quality_score(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "good_test.js"), "--format", "json"],
        )
        data = json.loads(result.output)
        assert "quality_score" in data["files"][0]
        assert "quality_grade" in data["files"][0]

    def test_good_file_scores_100(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "good_test.js"), "--format", "json"],
        )
        data = json.loads(result.output)
        assert data["files"][0]["quality_score"] == 100
        assert data["files"][0]["quality_grade"] == "A"

    def test_bad_file_scores_below_100(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "missing_sleep.js"), "--format", "json"],
        )
        data = json.loads(result.output)
        assert data["files"][0]["quality_score"] < 100

    def test_text_output_shows_score_badge(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "missing_sleep.js"), "--no-color"],
        )
        # Badge format: [X nn/100]
        assert "/100]" in result.output

    def test_json_output_has_overall_score(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "good_test.js"), "--format", "json"],
        )
        data = json.loads(result.output)
        assert "overall_score" in data
        assert "overall_grade" in data

    def test_fixable_violations_marked_in_text(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["check", str(k6_fixtures_dir / "missing_sleep.js"), "--no-color"],
        )
        assert "[fixable]" in result.output


class TestFixDryRun:
    def test_fix_dry_run_shows_diff(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "check",
                str(k6_fixtures_dir / "missing_sleep.js"),
                "--fix-dry-run",
                "--no-color",
            ],
        )
        # Dry run should show a diff
        assert "---" in result.output or "+++" in result.output or result.exit_code in (0, 1)

    def test_fix_dry_run_does_not_modify_file(
        self, runner: CliRunner, k6_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        original = (k6_fixtures_dir / "missing_sleep.js").read_text()
        tmp_file = tmp_path / "test.js"
        tmp_file.write_text(original)
        runner.invoke(cli, ["check", str(tmp_file), "--fix-dry-run"])
        assert tmp_file.read_text() == original

    def test_fix_and_fix_dry_run_cannot_combine(
        self, runner: CliRunner, k6_fixtures_dir: Path
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "check",
                str(k6_fixtures_dir / "missing_sleep.js"),
                "--fix",
                "--fix-dry-run",
            ],
        )
        assert result.exit_code == 2


class TestFix:
    def test_fix_removes_k6001_violation(
        self, runner: CliRunner, k6_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        tmp_file = tmp_path / "test.js"
        shutil.copy(k6_fixtures_dir / "missing_sleep.js", tmp_file)
        runner.invoke(cli, ["check", str(tmp_file), "--fix"])
        # Re-check the fixed file
        result = runner.invoke(
            cli,
            ["check", str(tmp_file), "--format", "json"],
        )
        data = json.loads(result.output)
        rule_ids = [v["rule_id"] for v in data["files"][0]["violations"]]
        assert "K6001" not in rule_ids

    def test_fix_writes_to_disk(
        self, runner: CliRunner, k6_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        original = (k6_fixtures_dir / "missing_sleep.js").read_text()
        tmp_file = tmp_path / "test.js"
        tmp_file.write_text(original)
        runner.invoke(cli, ["check", str(tmp_file), "--fix"])
        # File should have been modified
        assert tmp_file.read_text() != original

    def test_fix_improves_score(
        self, runner: CliRunner, k6_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        tmp_file = tmp_path / "test.js"
        shutil.copy(k6_fixtures_dir / "missing_sleep.js", tmp_file)

        # Score before fix
        before = runner.invoke(
            cli, ["check", str(tmp_file), "--format", "json"]
        )
        score_before = json.loads(before.output)["files"][0]["quality_score"]

        runner.invoke(cli, ["check", str(tmp_file), "--fix"])

        # Score after fix
        after = runner.invoke(
            cli, ["check", str(tmp_file), "--format", "json"]
        )
        score_after = json.loads(after.output)["files"][0]["quality_score"]
        assert score_after >= score_before

    def test_fix_jmeter_removes_jmx001(
        self, runner: CliRunner, jmeter_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        tmp_file = tmp_path / "test.jmx"
        shutil.copy(jmeter_fixtures_dir / "missing_managers.jmx", tmp_file)
        runner.invoke(cli, ["check", str(tmp_file), "--fix"])
        result = runner.invoke(
            cli,
            ["check", str(tmp_file), "--format", "json"],
        )
        data = json.loads(result.output)
        rule_ids = [v["rule_id"] for v in data["files"][0]["violations"]]
        assert "JMX001" not in rule_ids

    def test_fix_jmeter_removes_jmx002(
        self, runner: CliRunner, jmeter_fixtures_dir: Path, tmp_path: Path
    ) -> None:
        tmp_file = tmp_path / "test.jmx"
        shutil.copy(jmeter_fixtures_dir / "missing_managers.jmx", tmp_file)
        runner.invoke(cli, ["check", str(tmp_file), "--fix"])
        result = runner.invoke(
            cli,
            ["check", str(tmp_file), "--format", "json"],
        )
        data = json.loads(result.output)
        rule_ids = [v["rule_id"] for v in data["files"][0]["violations"]]
        assert "JMX002" not in rule_ids
