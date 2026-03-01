"""Shared XML utilities for perf-lint."""
from __future__ import annotations

from lxml import etree

# Secure lxml parser — prevents XXE, entity expansion, and network access.
# Both the JMeter parser and JMeter rules use this instance to ensure the
# security configuration cannot diverge between modules.
_SECURE_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,
)
