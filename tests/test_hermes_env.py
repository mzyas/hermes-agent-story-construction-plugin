"""Unit tests for the test-suite Hermes discovery helper (no Hermes required)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from hermes_env import HermesEnv, discover_hermes, ensure_hermes


def _write_source(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "hermes_constants.py").write_text("", encoding="utf-8")
    (root / "hermes_cli").mkdir()
    (root / "hermes_cli" / "config.py").write_text("", encoding="utf-8")
    return root


def _fail_import(name):
    raise ImportError(name)


def test_explicit_hermes_source_wins(tmp_path):
    explicit = _write_source(tmp_path / "explicit")
    sibling = _write_source(tmp_path / "home" / "hermes-agent")
    env = discover_hermes(
        environ={"HERMES_SOURCE": str(explicit)},
        roots=[tmp_path / "home"],
        import_module=_fail_import,
    )
    assert env == HermesEnv(True, f"source:{explicit}", explicit)
    assert env.source == explicit
    assert env.source != sibling


def test_invalid_explicit_source_falls_through_to_checkout(tmp_path):
    sibling = _write_source(tmp_path / "home" / "hermes-agent")
    env = discover_hermes(
        environ={"HERMES_SOURCE": str(tmp_path / "missing")},
        roots=[tmp_path / "home"],
        import_module=_fail_import,
    )
    assert env == HermesEnv(True, f"checkout:{sibling}", sibling)


def test_installed_hermes_is_used_without_a_checkout(tmp_path):
    calls = []

    def fake_import(name):
        calls.append(name)
        return types.ModuleType(name)

    env = discover_hermes(
        environ={},
        roots=[tmp_path],
        import_module=fake_import,
    )
    assert env == HermesEnv(True, "installed", None)
    assert "hermes_constants" in calls
    assert "hermes_cli.config" in calls


def test_missing_hermes_reports_unavailable_without_raising(tmp_path):
    def raise_import(name):
        raise ImportError(name)

    env = discover_hermes(environ={}, roots=[tmp_path], import_module=raise_import)
    assert env == HermesEnv(False, "unavailable", None)


def test_ensure_hermes_puts_source_on_sys_path(tmp_path):
    explicit = _write_source(tmp_path / "explicit")
    env = ensure_hermes(
        environ={"HERMES_SOURCE": str(explicit)},
        roots=[],
        import_module=_fail_import,
    )
    try:
        assert env.source == explicit
        assert str(explicit) in sys.path
    finally:
        while str(explicit) in sys.path:
            sys.path.remove(str(explicit))
