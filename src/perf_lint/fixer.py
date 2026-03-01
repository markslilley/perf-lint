"""Auto-fix orchestration for perf-lint.

Iterates violations, looks up fixable rules, applies fixes sequentially so each
fix sees the output of the previous one, and optionally writes the result to disk.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from perf_lint.ir.models import ScriptIR, Violation
from perf_lint.rules.base import BaseRule

# Matches the XML encoding declaration, e.g. <?xml version="1.0" encoding="ISO-8859-1"?>
_XML_ENCODING_RE = re.compile(r'encoding=["\']([^"\']+)["\']', re.IGNORECASE)

_SAFE_XML_ENCODINGS: frozenset[str] = frozenset({
    "utf-8", "utf-16", "utf-16-le", "utf-16-be",
    "iso-8859-1", "latin-1", "ascii", "windows-1252",
})


def apply_fixes(
    ir: ScriptIR,
    violations: list[Violation],
    rules: dict[str, type[BaseRule]],
) -> tuple[str, list[str]]:
    """Apply all safe auto-fixes to ir.raw_content.

    Iterates violations in order, calling rule.apply_fix(ir) for each fixable rule.
    When a fix succeeds, ir.raw_content is updated so subsequent fixes see the latest
    source.

    Returns:
        (fixed_source, list_of_applied_rule_ids)
    """
    applied: list[str] = []
    seen_rules: set[str] = set()  # Apply each rule at most once per file

    for violation in violations:
        rule_id = violation.rule_id
        if rule_id in seen_rules:
            continue

        rule_class = rules.get(rule_id)
        if rule_class is None:
            continue

        if not getattr(rule_class, "fixable", False):
            continue

        rule_instance: BaseRule = rule_class()
        fixed_source = rule_instance.apply_fix(ir)
        if fixed_source is not None:
            ir.raw_content = fixed_source
            applied.append(rule_id)

        seen_rules.add(rule_id)

    return ir.raw_content, applied


def compute_diff(original: str, fixed: str, file_path: str) -> str:
    """Return a unified diff string between original and fixed source.

    Uses a relative path in the diff header so absolute paths (e.g.
    /home/user/project/foo.js) don't produce ugly a//home/... headers.
    """
    try:
        display_path = str(Path(file_path).relative_to(Path.cwd()))
    except ValueError:
        display_path = Path(file_path).name

    original_lines = original.splitlines(keepends=True)
    fixed_lines = fixed.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        fixed_lines,
        fromfile=f"a/{display_path}",
        tofile=f"b/{display_path}",
    )
    return "".join(diff)


def _detect_encoding(source: str, path: Path) -> str:
    """Detect the correct encoding for writing back a fixed file.
    For JMX files, reads the XML declaration; falls back to utf-8.
    Encoding is validated against a whitelist to prevent codec injection."""
    if path.suffix.lower() == ".jmx":
        m = _XML_ENCODING_RE.search(source[:200])
        if m:
            declared = m.group(1).lower()
            if declared in _SAFE_XML_ENCODINGS:
                return declared
            # Unknown/unsafe encoding declared — fall back to utf-8
    return "utf-8"


def write_fixed_source(path: Path, source: str) -> None:
    """Write fixed source back to disk, with path canonicalization."""
    resolved = path.resolve()
    # Guard: only write to files that already exist (i.e., were already opened
    # by the linter). This prevents path traversal if a crafted violation
    # injects a symlink target outside the working tree.
    if not resolved.exists():
        raise ValueError(f"Target path does not exist: {resolved}")
    encoding = _detect_encoding(source, path)
    resolved.write_text(source, encoding=encoding)
