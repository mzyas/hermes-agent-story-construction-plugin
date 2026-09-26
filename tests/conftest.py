"""Shared test configuration: Hermes integration marker and loud, non-silent skips."""

from __future__ import annotations

import pytest

from hermes_env import (
    HERMES_AVAILABLE,
    HERMES_MODE,
    INTEGRATION_SKIP_REASON,
    REQUIRE_HERMES,
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "hermes_integration: needs importable Hermes (HERMES_SOURCE, sibling "
        "checkout, or installed package)",
    )
    if REQUIRE_HERMES and not HERMES_AVAILABLE:
        raise pytest.UsageError(
            "REQUIRE_HERMES=1 but no Hermes is importable — refusing to skip "
            f"integration tests (discovery mode: {HERMES_MODE})."
        )


def pytest_collection_modifyitems(config, items):
    if HERMES_AVAILABLE:
        return
    skip = pytest.mark.skip(reason=INTEGRATION_SKIP_REASON)
    for item in items:
        if item.get_closest_marker("hermes_integration") is not None:
            item.add_marker(skip)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    terminalreporter.write_line(f"hermes discovery mode: {HERMES_MODE}")
    if not HERMES_AVAILABLE:
        terminalreporter.write_line(
            "INTEGRATION TESTS SKIPPED (hermes_integration): Hermes is unavailable. "
            "This run is NOT a full acceptance result."
        )
