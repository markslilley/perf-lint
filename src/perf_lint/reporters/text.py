"""Rich-colored terminal text reporter."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from perf_lint.engine import FileResult, LintResult
from perf_lint.ir.models import Severity
from perf_lint.reporters.base import BaseReporter
from perf_lint.rules.base import RuleRegistry

_SEVERITY_STYLE = {
    Severity.ERROR: "bold red",
    Severity.WARNING: "bold yellow",
    Severity.INFO: "bold blue",
}

_SEVERITY_ICON = {
    Severity.ERROR: "E",
    Severity.WARNING: "W",
    Severity.INFO: "I",
}

_GRADE_STYLE = {
    "A": "bold green",
    "B": "bold cyan",
    "C": "bold yellow",
    "D": "bold red",
    "F": "bold red",
}


def _grade_badge(score: int, grade: str) -> str:
    """Return a Rich markup string for a score badge."""
    style = _GRADE_STYLE.get(grade, "bold")
    return f"[{style}][{grade} {score}/100][/{style}]"


def _is_rule_fixable(rule_id: str) -> bool:
    """Return True if the rule with this ID provides an auto-fix."""
    rule_class = RuleRegistry.get(rule_id)
    return rule_class is not None and getattr(rule_class, "fixable", False)


class TextReporter(BaseReporter):
    """Produces Rich-colored terminal output."""

    def __init__(self, no_color: bool = False) -> None:
        self.no_color = no_color

    def report(
        self,
        result: LintResult,
        output_path: Path | None = None,
        fixed_by_file: dict[str, list[str]] | None = None,
        dry_run_diffs: dict[str, str] | None = None,
        **kwargs: object,
    ) -> str:
        buf = StringIO()
        console = Console(file=buf, no_color=self.no_color, highlight=False)

        for file_result in result.file_results:
            self._render_file(console, file_result)

        if fixed_by_file:
            self._render_fix_summary(console, fixed_by_file)

        if dry_run_diffs:
            self._render_dry_run_diffs(console, dry_run_diffs)

        self._render_summary(console, result)

        output = buf.getvalue()
        self._write_output(output, output_path)
        return output

    def _render_file(self, console: Console, file_result: FileResult) -> None:
        if file_result.parse_error:
            console.print(
                f"[bold red]PARSE ERROR[/] {file_result.path}: {file_result.parse_error}"
            )
            return

        if not file_result.violations:
            badge = _grade_badge(file_result.quality_score, file_result.quality_grade)
            console.print(f"[green]OK[/] {file_result.path}  {badge}")
            return

        badge = _grade_badge(file_result.quality_score, file_result.quality_grade)
        console.print(
            f"\n[bold]{file_result.path}[/] [dim]({file_result.framework})[/]  {badge}"
        )

        for v in sorted(file_result.violations, key=lambda x: x.severity, reverse=True):
            style = _SEVERITY_STYLE[v.severity]
            icon = _SEVERITY_ICON[v.severity]
            loc = str(v.location) if v.location else ""
            fixable = _is_rule_fixable(v.rule_id)

            line = Text()
            line.append(f"  {icon} ", style=style)
            line.append(f"[{v.rule_id}] ", style="bold")
            line.append(v.message)
            if loc:
                line.append(f" ({loc})", style="dim")
            if fixable:
                line.append("  [fixable]", style="dim green")
            console.print(line)

            if v.suggestion:
                console.print(f"    [dim]Suggestion:[/] {v.suggestion}")

            if v.fix_example:
                console.print(f"    [dim]Example:[/]")
                for example_line in v.fix_example.split("\n"):
                    console.print(f"      [cyan]{example_line}[/]")

    def _render_fix_summary(
        self, console: Console, fixed_by_file: dict[str, list[str]]
    ) -> None:
        console.print()
        for file_path, rule_ids in fixed_by_file.items():
            console.print(
                f"[bold green]Fixed {len(rule_ids)} violation(s) in {file_path}:[/]"
            )
            for rule_id in rule_ids:
                rule_class = RuleRegistry.get(rule_id)
                name = rule_class.name if rule_class else rule_id
                console.print(f"  [green]✓[/] {rule_id}  {name}")

    def _render_dry_run_diffs(
        self, console: Console, dry_run_diffs: dict[str, str]
    ) -> None:
        console.print()
        for file_path, diff in dry_run_diffs.items():
            console.print(f"[bold cyan]--- Dry-run diff for {file_path} ---[/]")
            for diff_line in diff.splitlines():
                if diff_line.startswith("+") and not diff_line.startswith("+++"):
                    console.print(f"[green]{diff_line}[/]")
                elif diff_line.startswith("-") and not diff_line.startswith("---"):
                    console.print(f"[red]{diff_line}[/]")
                else:
                    console.print(diff_line)

    def _render_summary(self, console: Console, result: LintResult) -> None:
        console.print()

        if result.total_violations == 0:
            badge = _grade_badge(result.overall_score, result.overall_grade)
            console.print(
                Panel(
                    f"[bold green]All {len(result.file_results)} file(s) passed with no violations.[/]  {badge}",
                    title="perf-lint summary",
                    border_style="green",
                )
            )
            return

        table = Table(title="perf-lint summary", show_header=True, header_style="bold")
        table.add_column("Metric", style="dim")
        table.add_column("Count", justify="right")

        table.add_row("Files checked", str(len(result.file_results)))
        table.add_row("Files with violations", str(result.files_with_violations))
        table.add_row("[bold red]Errors[/]", f"[bold red]{result.error_count}[/]")
        table.add_row("[bold yellow]Warnings[/]", f"[bold yellow]{result.warning_count}[/]")
        table.add_row("[bold blue]Info[/]", f"[bold blue]{result.info_count}[/]")
        table.add_row("[bold]Total violations[/]", f"[bold]{result.total_violations}[/]")

        grade_style = _GRADE_STYLE.get(result.overall_grade, "bold")
        table.add_row(
            "Quality score",
            f"[{grade_style}]{result.overall_grade} {result.overall_score}/100[/{grade_style}]",
        )

        console.print(table)
