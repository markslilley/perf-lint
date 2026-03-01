"""Shared test fixtures for perf-lint tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
JMETER_FIXTURES = FIXTURES_DIR / "jmeter"
K6_FIXTURES = FIXTURES_DIR / "k6"
GATLING_FIXTURES = FIXTURES_DIR / "gatling"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def jmeter_fixtures_dir() -> Path:
    return JMETER_FIXTURES


@pytest.fixture
def k6_fixtures_dir() -> Path:
    return K6_FIXTURES


@pytest.fixture
def gatling_fixtures_dir() -> Path:
    return GATLING_FIXTURES
