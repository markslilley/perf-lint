"""Base parser abstract class for perf-lint."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from perf_lint.ir.models import Framework, ScriptIR


class BaseParser(ABC):
    """Abstract base class for all script parsers.

    Each parser reads a source file, extracts relevant data into parsed_data,
    and returns a ScriptIR ready for rule evaluation.

    Content caching: _can_parse_content() must read the file to detect whether
    it belongs to this framework (e.g. K6 import signature). That content is
    cached so parse() can reuse it without a second I/O round-trip.
    """

    def __init__(self) -> None:
        # Cache keyed by absolute path; cleared after each parse() call.
        self._content_cache: dict[Path, str] = {}

    @property
    @abstractmethod
    def framework(self) -> Framework:
        """The framework this parser handles."""
        ...

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions this parser supports (e.g. ['.jmx'])."""
        ...

    def can_parse(self, path: Path) -> bool:
        """Return True if this parser can handle the given file."""
        if path.suffix.lower() not in self.supported_extensions:
            return False
        return self._can_parse_content(path)

    def _can_parse_content(self, path: Path) -> bool:
        """Override to add content-based detection (e.g., K6 import signature).

        Subclasses that read the file here should call _read_and_cache() so
        parse() can avoid a second I/O round-trip.
        """
        return True

    @abstractmethod
    def parse(self, path: Path) -> ScriptIR:
        """Parse a file and return a ScriptIR.

        The IR's parsed_data must be populated with all data needed by rules.
        Subclasses should call _pop_cached_content(path) to retrieve content
        that was already read by _can_parse_content().
        """
        ...

    def _read_file(self, path: Path) -> str:
        """Read file content, handling encoding gracefully."""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="latin-1")

    def _read_and_cache(self, path: Path) -> str:
        """Read file content and cache it for reuse by parse()."""
        content = self._read_file(path)
        self._content_cache[path.resolve()] = content
        return content

    def _pop_cached_content(self, path: Path) -> str | None:
        """Return and remove cached content for path, or None if not cached."""
        return self._content_cache.pop(path.resolve(), None)


def detect_parser(path: Path, parsers: list[BaseParser]) -> BaseParser | None:
    """Find the first parser that can handle the given file."""
    for parser in parsers:
        if parser.can_parse(path):
            return parser
    return None
