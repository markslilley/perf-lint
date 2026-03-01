"""Click CLI for perf-lint.

Commands:
  check  — analyse performance test scripts
  rules  — list available rules
  init   — generate a starter .perf-lint.yml
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import click
from rich.console import Console

import perf_lint.rules.gatling  # noqa: F401
import perf_lint.rules.jmeter  # noqa: F401
import perf_lint.rules.k6  # noqa: F401
from perf_lint import __version__
from perf_lint.config.loader import load_config
from perf_lint.engine import LintEngine, LintResult
from perf_lint.fixer import apply_fixes, compute_diff, write_fixed_source
from perf_lint.ir.models import Severity
from perf_lint.parsers.base import detect_parser
from perf_lint.plugins.loader import load_plugins
from perf_lint.reporters.base import BaseReporter
from perf_lint.reporters.json_reporter import JsonReporter
from perf_lint.reporters.sarif import SarifReporter
from perf_lint.reporters.text import TextReporter
from perf_lint.rules.base import RuleRegistry


def _should_exit_nonzero(result: LintResult, threshold: str) -> bool:
    """Return True if any violations meet/exceed the severity threshold."""
    threshold_sev = Severity(threshold)
    for file_result in result.file_results:
        if file_result.parse_error:
            return True
        for v in file_result.violations:
            if v.severity >= threshold_sev:
                return True
    return False


def _make_reporter(output_format: str, no_color: bool) -> BaseReporter:
    """Factory: return the appropriate reporter for the requested format."""
    if output_format == "json":
        return JsonReporter()
    if output_format == "sarif":
        return SarifReporter()
    return TextReporter(no_color=no_color)


def _filter_to_free(result: LintResult, free_rule_ids: set[str]) -> LintResult:
    """Return a copy of result containing only free-tier violations.

    Scores are recomputed based on the filtered violations so the displayed
    grade reflects what the free user actually sees.
    """
    from perf_lint.engine import FileResult, _score_to_grade

    filtered_files = []
    for fr in result.file_results:
        filtered_violations = [v for v in fr.violations if v.rule_id in free_rule_ids]
        new_fr = FileResult(
            path=fr.path,
            framework=fr.framework,
            violations=filtered_violations,
            parse_error=fr.parse_error,
        )
        # Recompute score based on free violations only
        if fr.parse_error:
            new_fr.quality_score = 0
            new_fr.quality_grade = "F"
        else:
            score = max(
                0,
                100
                - new_fr.error_count * 15
                - new_fr.warning_count * 5
                - new_fr.info_count * 1,
            )
            new_fr.quality_score = score
            new_fr.quality_grade = _score_to_grade(score)
        filtered_files.append(new_fr)

    filtered_result = LintResult(file_results=filtered_files)
    if not filtered_files:
        filtered_result.overall_score = 100
        filtered_result.overall_grade = "A"
    else:
        avg = round(
            sum(r.quality_score for r in filtered_files) / len(filtered_files)
        )
        filtered_result.overall_score = avg
        filtered_result.overall_grade = _score_to_grade(avg)
    return filtered_result


def _hidden_tiers(result: LintResult, free_rule_ids: set[str]) -> str:
    """Return a label like 'Pro · Team' for tiers that have hidden violations."""
    all_rules = RuleRegistry.get_all()
    hidden_pro = any(
        v.rule_id not in free_rule_ids
        and all_rules.get(v.rule_id) is not None
        and all_rules[v.rule_id].tier == "pro"
        for fr in result.file_results
        for v in fr.violations
    )
    hidden_team = any(
        v.rule_id not in free_rule_ids
        and all_rules.get(v.rule_id) is not None
        and all_rules[v.rule_id].tier == "team"
        for fr in result.file_results
        for v in fr.violations
    )
    parts = []
    if hidden_pro:
        parts.append("Pro")
    if hidden_team:
        parts.append("Team")
    return " · ".join(parts) if parts else "Pro"


def _print_hint(hidden_count: int, tiers: str, api_key: str | None) -> None:
    """Print the hidden-violations hint block to stderr."""
    noun = "violation" if hidden_count == 1 else "violations"
    if api_key:
        msg = f"{hidden_count} {noun} hidden ({tiers}) — view in your dashboard"
    else:
        msg = (
            f"{hidden_count} {noun} hidden ({tiers})\n"
            "Sign up free at https://perflint.martkos-it.co.uk\n"
            "Set PERF_LINT_API_KEY to send full results to your dashboard."
        )
    click.echo(f"\n── {msg}", err=False)


def _post_results_async(api_key: str, api_url: str, result: LintResult) -> None:
    """Fire-and-forget POST of full results to the dashboard API.

    Uses only stdlib (urllib) — no new dependencies. Failures are silently
    swallowed so a network error never blocks or fails the CLI.
    """
    try:
        payload = json.dumps(result.to_dict()).encode("utf-8")
        url = api_url.rstrip("/") + "/v1/scan"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": f"perf-lint/{__version__}",
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)  # noqa: S310 — user-supplied URL from config
    except Exception:
        pass  # Silent — never block the CLI exit


def _run_fix_pass(
    result: LintResult,
    engine: LintEngine,
    all_rules: dict,
    do_fix: bool,
    fix_dry_run: bool,
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Apply auto-fixes to all files in result.

    Returns:
        fixed_by_file: {file_path: [rule_ids_applied]}
        dry_run_diffs: {file_path: unified_diff_str}  (only when fix_dry_run)
    """
    fixed_by_file: dict[str, list[str]] = {}
    dry_run_diffs: dict[str, str] = {}

    for file_result in result.file_results:
        if file_result.parse_error or not file_result.violations:
            continue

        parser = detect_parser(file_result.path, engine._parsers)
        if parser is None:
            continue
        try:
            ir = parser.parse(file_result.path)
        except Exception:
            continue

        original_source = ir.raw_content
        fixed_source, applied = apply_fixes(ir, file_result.violations, all_rules)

        if applied:
            file_key = str(file_result.path)
            if fix_dry_run:
                diff = compute_diff(original_source, fixed_source, file_key)
                if diff:
                    dry_run_diffs[file_key] = diff
            else:
                write_fixed_source(file_result.path, fixed_source)
            fixed_by_file[file_key] = applied

    return fixed_by_file, dry_run_diffs


@click.group()
@click.version_option(__version__, prog_name="perf-lint")
def cli() -> None:
    """perf-lint — Static analyser for performance test scripts (JMeter, K6, Gatling)."""


@cli.command("check")
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "sarif"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to .perf-lint.yml config file.",
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"], case_sensitive=False),
    default=None,
    help="Override severity threshold for non-zero exit code.",
)
@click.option("--no-color", is_flag=True, default=False, help="Disable colour output.")
@click.option(
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write output to FILE instead of stdout.",
)
@click.option(
    "--ignore-rule",
    "ignored_rules",
    multiple=True,
    metavar="RULE_ID",
    help="Ignore a specific rule (may be repeated).",
)
@click.option(
    "--fix",
    "do_fix",
    is_flag=True,
    default=False,
    help="Automatically fix problems. Fixes are applied to the file system.",
)
@click.option(
    "--fix-dry-run",
    "fix_dry_run",
    is_flag=True,
    default=False,
    help="Automatically fix problems without saving the changes to the file system.",
)
def check_command(
    paths: tuple[Path, ...],
    output_format: str,
    config_path: Path | None,
    severity: str | None,
    no_color: bool,
    output_file: Path | None,
    ignored_rules: tuple[str, ...],
    do_fix: bool,
    fix_dry_run: bool,
) -> None:
    """Analyse performance test scripts for quality issues."""
    if do_fix and fix_dry_run:
        click.echo("Error: --fix and --fix-dry-run cannot be used together.", err=True)
        sys.exit(2)

    try:
        config = load_config(config_path)
    except Exception as exc:
        click.echo(f"Error loading config: {exc}", err=True)
        sys.exit(2)

    load_plugins(config)

    engine = LintEngine(config=config)

    try:
        result = engine.lint_paths(
            list(paths),
            severity_override=severity,
            ignored_rules=list(ignored_rules),
        )
    except Exception as exc:
        click.echo(f"Error during analysis: {exc}", err=True)
        sys.exit(2)

    # Determine free-tier rule IDs for display filtering
    all_rules = RuleRegistry.get_all()
    free_rule_ids = {rid for rid, cls in all_rules.items() if cls.tier == "free"}

    # Apply fixes if requested (free-tier rules only for local fix)
    fixed_by_file: dict[str, list[str]] = {}
    dry_run_diffs: dict[str, str] = {}

    if do_fix or fix_dry_run:
        free_rules = {rid: cls for rid, cls in all_rules.items() if cls.tier == "free"}
        fixed_by_file, dry_run_diffs = _run_fix_pass(
            result, engine, free_rules, do_fix, fix_dry_run
        )

        # After --fix, re-lint to report remaining violations.
        if do_fix and fixed_by_file:
            try:
                result = engine.lint_paths(
                    list(paths),
                    severity_override=severity,
                    ignored_rules=list(ignored_rules),
                )
            except Exception as exc:
                click.echo(f"Error during re-analysis: {exc}", err=True)
                sys.exit(2)

    # Build display result (free violations only) and count hidden
    display_result = _filter_to_free(result, free_rule_ids)
    hidden_count = result.total_violations - display_result.total_violations

    # Render output (always show free violations only)
    threshold = severity or config.severity_threshold
    reporter = _make_reporter(output_format, no_color)

    try:
        if output_format == "text":
            report_content = reporter.report(
                display_result,
                output_path=output_file,
                fixed_by_file=fixed_by_file if (do_fix or fix_dry_run) else None,
                dry_run_diffs=dry_run_diffs if fix_dry_run else None,
            )
        else:
            report_content = reporter.report(display_result, output_path=output_file)
    except Exception as exc:
        click.echo(f"Error generating report: {exc}", err=True)
        sys.exit(2)

    if output_file is None:
        click.echo(report_content, nl=False)

    # Print hint when there are hidden pro/team violations
    if hidden_count > 0 and output_format == "text":
        tiers = _hidden_tiers(result, free_rule_ids)
        _print_hint(hidden_count, tiers, config.api_key)

    # Silent POST of full results if API key configured
    if config.api_key:
        _post_results_async(config.api_key, config.api_url, result)

    # Exit code based on free violations only
    if _should_exit_nonzero(display_result, threshold):
        sys.exit(1)


@cli.command("rules")
@click.option(
    "--framework",
    type=click.Choice(["jmeter", "k6", "gatling"], case_sensitive=False),
    default=None,
    help="Filter rules by framework.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def rules_command(framework: str | None, as_json: bool) -> None:
    """List all available lint rules."""
    config = load_config(None)
    load_plugins(config)
    all_rules = RuleRegistry.get_all()

    if framework:
        from perf_lint.ir.models import Framework
        fw = Framework(framework.lower())
        filtered = {k: v for k, v in all_rules.items() if fw in v.frameworks}
    else:
        filtered = all_rules

    rules_data = [v.to_dict() for v in sorted(filtered.values(), key=lambda r: r.rule_id)]

    if as_json:
        click.echo(json.dumps(rules_data, indent=2))
        return

    console = Console()
    from rich.table import Table
    table = Table(title=f"perf-lint rules ({len(rules_data)} total)", show_lines=True)
    table.add_column("ID", style="bold cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Severity")
    table.add_column("Frameworks")
    table.add_column("Description")

    _sev_style = {"error": "bold red", "warning": "bold yellow", "info": "bold blue"}

    for rule in rules_data:
        sev = rule["severity"]
        table.add_row(
            rule["rule_id"],
            rule["name"],
            f"[{_sev_style.get(sev, '')}]{sev}[/]",
            ", ".join(rule["frameworks"]),
            rule["description"][:80] + ("..." if len(rule["description"]) > 80 else ""),
        )

    console.print(table)


@cli.command("init")
@click.option(
    "--output",
    "output_file",
    type=click.Path(path_type=Path),
    default=Path(".perf-lint.yml"),
    show_default=True,
    help="Output path for the generated config.",
)
def init_command(output_file: Path) -> None:
    """Generate a starter .perf-lint.yml configuration file."""
    if output_file.exists():
        click.confirm(f"{output_file} already exists. Overwrite?", abort=True)

    config_content = """\
# perf-lint configuration
# https://github.com/perf-lint/perf-lint

version: 1

# Severity threshold: violations at or above this level cause exit code 1
# Options: error | warning | info
severity_threshold: warning

# Rule-specific overrides
rules:
  # Disable a rule
  # JMX003:
  #   enabled: false
  #
  # Escalate severity
  # K6001:
  #   severity: error

# Custom rule plugins
# custom_rules:
#   - path: ./lint_rules/*.py

# Paths to ignore (supports glob patterns including **)
# ignore_paths:
#   - "**/node_modules/**"
#   - "**/vendor/**"
"""

    output_file.write_text(config_content, encoding="utf-8")
    click.echo(f"Created {output_file}")
    click.echo("Edit the file to customise your lint configuration.")
