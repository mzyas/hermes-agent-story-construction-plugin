"""Hermes discovery for the test suite: explicit source, sibling checkout, or installed.

Discovery never raises at import time. ``HERMES_SOURCE`` is the explicit
test-only source path and wins over everything else; next comes a ``hermes-agent``
checkout next to a test-file ancestor; last, an already-installed Hermes is used
in place. Integration tests carry the ``hermes_integration`` marker and skip
with a loud reason when nothing is importable — set ``REQUIRE_HERMES=1`` to turn
that skip into a session error for acceptance runs.
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.dont_write_bytecode = True


def _valid_source(candidate: Path) -> bool:
    return (candidate / "hermes_constants.py").is_file() and (
        candidate / "hermes_cli" / "config.py"
    ).is_file()


@dataclass(frozen=True, slots=True)
class HermesEnv:
    """One discovery verdict: mode ``source:<path>``/``checkout:<path>``/``installed``/``unavailable``."""

    available: bool
    mode: str
    source: Path | None


def discover_hermes(*, environ=None, roots=None, import_module=importlib.import_module) -> HermesEnv:
    """Resolve Hermes without raising; ``roots``/``import_module`` are test seams."""

    env = os.environ if environ is None else environ
    explicit = (env.get("HERMES_SOURCE") or "").strip()
    if explicit and _valid_source(Path(explicit)):
        source = Path(explicit)
        return HermesEnv(True, f"source:{source}", source)
    search_roots = (
        list(Path(__file__).resolve().parents) if roots is None else [Path(r) for r in roots]
    )
    for parent in search_roots:
        candidate = parent / "hermes-agent"
        if _valid_source(candidate):
            return HermesEnv(True, f"checkout:{candidate}", candidate)
    try:
        import_module("hermes_constants")
        import_module("hermes_cli.config")
    except ImportError:
        return HermesEnv(False, "unavailable", None)
    return HermesEnv(True, "installed", None)


def ensure_hermes(**kwargs) -> HermesEnv:
    """Discover Hermes and put a source checkout on ``sys.path`` when one was found."""

    result = discover_hermes(**kwargs)
    if result.source is not None and str(result.source) not in sys.path:
        sys.path.insert(0, str(result.source))
    return result


HERMES = ensure_hermes()
HERMES_AVAILABLE = HERMES.available
HERMES_MODE = HERMES.mode
REQUIRE_HERMES = (os.environ.get("REQUIRE_HERMES") or "").strip().lower() in {
    "1",
    "true",
    "yes",
}
INTEGRATION_SKIP_REASON = (
    "Hermes integration test NOT RUN: no importable Hermes (set HERMES_SOURCE to a "
    "source checkout or install hermes). Standalone plugin tests still run; set "
    "REQUIRE_HERMES=1 to fail instead of skipping."
)


def read_user_config_raw(path=None):
    """Lazy passthrough to ``hermes_cli.config`` so imports never require Hermes."""

    from hermes_cli.config import read_user_config_raw as _impl

    return _impl(path) if path is not None else _impl()
