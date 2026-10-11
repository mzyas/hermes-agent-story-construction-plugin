"""Story tools follow the saved selection instead of the state at plugin load."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from story_construction_plugin import register
from story_construction_plugin import runtime
from story_construction_plugin.session_store import StorySessionRegistry


class RegistrationContext:
    def __init__(self, settings: dict[str, object] | None = None) -> None:
        self.settings = dict(settings or {})
        self.sections: list[object] = []
        self.tools: list[dict[str, object]] = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_skill(self, *args) -> None:
        pass

    def register_system_prompt_section(self, *args, **kwargs) -> None:
        self.sections.append((args, kwargs))

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)


def _settings(home: Path, vault: Path) -> dict[str, object]:
    return {
        "locked_profile": "writer",
        "vault_root": str(vault),
        "locked_hermes_home": str(home),
    }


def _call(context: RegistrationContext, name: str = "story.get_project") -> dict:
    handler = {tool["name"]: tool["handler"] for tool in context.tools}[name]
    return json.loads(handler({"project_id": "p1"}, session_id="s1"))


def _environment(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    home.mkdir()
    vault.mkdir()
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    return home, vault


def test_selection_saved_after_load_enables_tools_and_prompt(tmp_path, monkeypatch) -> None:
    home, vault = _environment(tmp_path, monkeypatch)
    context = RegistrationContext()
    register(context)
    check = context.tools[0]["check_fn"]
    (_name, render), _kwargs = context.sections[-1]
    StorySessionRegistry(runtime._session_state_path(home), locked_profile="writer").bind(
        stored_session_id="s1", profile="writer", connection_id="local", project_id="p1"
    )
    bound = {"profile": "writer", "session_id": "s1"}
    assert check() is False
    assert render(bound) == ""

    context.settings.update(_settings(home, vault))

    assert check() is True
    assert _call(context)["error"]["code"] != "configuration_incomplete"
    assert render(bound)
    assert render({"profile": "writer", "session_id": "chat"}) == ""


def test_settings_broken_after_ready_hides_tools_again(tmp_path, monkeypatch) -> None:
    home, vault = _environment(tmp_path, monkeypatch)
    context = RegistrationContext(_settings(home, vault))
    register(context)
    check = context.tools[0]["check_fn"]
    assert check() is True

    context.settings["vault_root"] = str(tmp_path / "missing")

    assert check() is False
    assert _call(context)["error"]["code"] == "vault_not_directory"


def test_hermes_home_change_recomputes(tmp_path, monkeypatch) -> None:
    home, vault = _environment(tmp_path, monkeypatch)
    context = RegistrationContext(_settings(home, vault))
    register(context)
    check = context.tools[0]["check_fn"]
    assert check() is True

    other = tmp_path / "other-home"
    other.mkdir()
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: other)

    assert check() is False
    assert _call(context)["error"]["code"] == "hermes_home_mismatch"


def test_ready_state_is_cached_and_not_ready_is_recomputed(tmp_path, monkeypatch) -> None:
    home, vault = _environment(tmp_path, monkeypatch)
    calls = []
    real = runtime.prepare_story_runtime

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(runtime, "prepare_story_runtime", counting)
    context = RegistrationContext()
    register(context)
    check = context.tools[0]["check_fn"]
    before = len(calls)
    check()
    check()
    assert len(calls) == before + 2  # not ready: recomputed every time

    context.settings.update(_settings(home, vault))
    check()
    ready_calls = len(calls)
    for _ in range(3):
        assert check() is True
        _call(context)
    assert len(calls) == ready_calls  # ready and unchanged: reused


def test_all_tools_share_one_check_fn(tmp_path, monkeypatch) -> None:
    _environment(tmp_path, monkeypatch)
    context = RegistrationContext()
    register(context)

    assert len({id(tool["check_fn"]) for tool in context.tools}) == 1


def test_check_fn_is_marked_uncached_when_host_helper_exists(tmp_path, monkeypatch) -> None:
    _environment(tmp_path, monkeypatch)
    marked = []
    registry = types.ModuleType("tools.registry")
    registry.no_cache_check_fn = lambda fn: (marked.append(fn), fn)[1]
    monkeypatch.setitem(sys.modules, "tools", types.ModuleType("tools"))
    monkeypatch.setitem(sys.modules, "tools.registry", registry)
    context = RegistrationContext()

    register(context)

    assert marked == [context.tools[0]["check_fn"]]


def test_missing_host_helper_falls_back_to_plain_check_fn(tmp_path, monkeypatch) -> None:
    _environment(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "tools.registry", None)  # import raises ImportError
    context = RegistrationContext()

    register(context)

    assert callable(context.tools[0]["check_fn"])
    assert context.tools[0]["check_fn"]() is False


def test_runtime_errors_fail_closed(tmp_path, monkeypatch) -> None:
    home, vault = _environment(tmp_path, monkeypatch)
    context = RegistrationContext(_settings(home, vault))
    register(context)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    context.settings["vault_root"] = str(tmp_path / "changed")
    monkeypatch.setattr(runtime, "prepare_story_runtime", boom)

    assert context.tools[0]["check_fn"]() is False
    assert _call(context)["error"]["code"] == "runtime_unavailable"
