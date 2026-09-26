"""Behavioral tests for the temporary single-profile Story runtime lock."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from story_construction_plugin import register
from story_construction_plugin import runtime
from story_construction_plugin.permissions import SessionScope
from story_construction_plugin.session_store import (
    SessionBindingStoreError,
    StorySessionRegistry,
)


class RegistrationContext:
    def __init__(self, settings: dict[str, object]) -> None:
        self.settings = settings
        self.skills: list[object] = []
        self.sections: list[object] = []
        self.tools: list[dict[str, object]] = []

    def get_config(self, key: str, default=None):
        return self.settings.get(key, default)

    def register_skill(self, *args) -> None:
        self.skills.append(args)

    def register_system_prompt_section(self, *args, **kwargs) -> None:
        self.sections.append((args, kwargs))

    def register_tool(self, **kwargs) -> None:
        self.tools.append(kwargs)


def _settings(*, home: Path, vault: Path, profile: str = "writer") -> dict[str, object]:
    return {
        "locked_profile": profile,
        "vault_root": str(vault),
        "locked_hermes_home": str(home),
    }


def test_register_rejects_incomplete_configuration(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    context = RegistrationContext({"locked_profile": "writer", "vault_root": str(vault)})

    register(context)

    assert context.tools == []
    state = runtime.runtime_state_for(Path(__file__).resolve().parents[1], home)
    assert state is not None
    assert state.status.code == "configuration_incomplete"
    assert state.status.vault_root_configured is True
    assert state.status.home_matches is False


def test_register_rejects_non_directory_vault(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    vault_file = tmp_path / "vault.md"
    vault_file.write_text("not a vault", encoding="utf-8")
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    context = RegistrationContext(_settings(home=home, vault=vault_file))

    register(context)

    assert context.tools == []
    state = runtime.runtime_state_for(Path(__file__).resolve().parents[1], home)
    assert state is not None
    assert state.status.code == "vault_not_directory"
    assert "vault.md" not in state.status.as_dict().__repr__()


def test_register_rejects_home_mismatch(tmp_path: Path, monkeypatch) -> None:
    current_home = tmp_path / "current-home"
    locked_home = tmp_path / "locked-home"
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: current_home)
    context = RegistrationContext(_settings(home=locked_home, vault=vault))

    register(context)

    assert context.tools == []
    state = runtime.runtime_state_for(Path(__file__).resolve().parents[1], current_home)
    assert state is not None
    assert state.status.code == "hermes_home_mismatch"
    assert state.status.home_matches is False


def test_locked_scope_registers_story_tools(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    context = RegistrationContext(_settings(home=home, vault=vault))

    register(context)

    assert context.tools
    state = runtime.runtime_state_for(Path(__file__).resolve().parents[1], home)
    assert state is not None
    assert state.status.ready is True
    assert state.repository is not None


def test_runtime_state_isolated_by_home(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    home_a = tmp_path / "home-a"
    home_b = tmp_path / "home-b"
    vault_a = tmp_path / "vault-a"
    vault_b = tmp_path / "vault-b"
    vault_a.mkdir()
    vault_b.mkdir()
    repository_a = object()
    repository_b = object()

    state_a = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home_a, vault=vault_a),
        current_home=home_a,
        repository_factory=lambda _: repository_a,
    )
    state_b = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home_b, vault=vault_b),
        current_home=home_b,
        repository_factory=lambda _: repository_b,
    )

    assert state_a is not state_b
    assert state_a.repository is repository_a
    assert state_b.repository is repository_b
    assert runtime.runtime_state_for(plugin_root, home_a) is state_a
    assert runtime.runtime_state_for(plugin_root, home_b) is state_b


def test_runtime_bindings_restore_from_each_profile_home_a_b_a(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    home_a = tmp_path / "home-a"
    home_b = tmp_path / "home-b"
    vault_a = tmp_path / "vault-a"
    vault_b = tmp_path / "vault-b"
    vault_a.mkdir()
    vault_b.mkdir()

    state_a = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home_a, vault=vault_a, profile="writer-a"),
        current_home=home_a,
        repository_factory=lambda _: object(),
    )
    state_a.sessions.bind(
        stored_session_id="stored-a",
        runtime_session_id="runtime-a",
        profile="writer-a",
        connection_id="local",
        source="desktop",
        project_id="novel-a",
        project_name="Novel A",
        title="Story: Novel A",
    )

    state_b = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home_b, vault=vault_b, profile="writer-b"),
        current_home=home_b,
        repository_factory=lambda _: object(),
    )
    state_b.sessions.bind(
        stored_session_id="stored-b",
        runtime_session_id="runtime-b",
        profile="writer-b",
        connection_id="remote",
        source="desktop",
        project_id="novel-b",
        project_name="Novel B",
        title="Story: Novel B",
    )

    restored_a = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home_a, vault=vault_a, profile="writer-a"),
        current_home=home_a,
        repository_factory=lambda _: object(),
    )

    assert restored_a.sessions.path == (
        home_a / "plugin-data" / "story-construction" / "sessions.json"
    )
    assert restored_a.sessions.get(
        stored_session_id="stored-a",
        profile="writer-a",
        connection_id="local",
    ).project_id == "novel-a"
    assert (
        restored_a.sessions.get(
            stored_session_id="stored-b",
            profile="writer-b",
            connection_id="remote",
        )
        is None
    )
    assert restored_a.permissions.bound_scope("stored-a").project_id == "novel-a"
    assert restored_a.permissions.bound_scope("runtime-a").project_id == "novel-a"


def test_concurrent_prepare_keeps_each_request_state_consistent(tmp_path: Path) -> None:
    """A second request's rebuild must never rewrite the state a request is using."""

    plugin_root = tmp_path / "plugin"
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = _settings(home=home, vault=vault)
    repository_a = object()
    repository_b = object()
    first_prepared = threading.Event()
    second_done = threading.Event()
    captured: dict[str, object] = {}
    errors: list[BaseException] = []

    def first_request() -> None:
        try:
            state_a = runtime.prepare_story_runtime(
                plugin_root,
                settings,
                current_home=home,
                repository_factory=lambda _: repository_a,
            )
            permissions_a = state_a.permissions
            sessions_a = state_a.sessions
            # Mid-request work in both the in-memory gate and the persistent registry.
            permissions_a.bind_session(
                SessionScope("mid-a", "desktop", "writer", "local", "p1"), "p1"
            )
            sessions_a.bind(
                stored_session_id="stored-a",
                profile="writer",
                connection_id="local",
                source="desktop",
                project_id="p1",
            )
            captured["state_a"] = state_a
            captured["permissions_a"] = permissions_a
            captured["sessions_a"] = sessions_a
            first_prepared.set()
            assert second_done.wait(timeout=10)
            captured["after_repository"] = state_a.repository
            captured["after_permissions"] = state_a.permissions
            captured["after_sessions"] = state_a.sessions
            captured["after_gate"] = state_a.permissions.bound_scope("mid-a")
            captured["after_row"] = state_a.sessions.get(
                stored_session_id="stored-a",
                profile="writer",
                connection_id="local",
            )
        except BaseException as exc:  # noqa: BLE001  re-raised on the main thread
            errors.append(exc)
            first_prepared.set()

    def second_request() -> None:
        try:
            assert first_prepared.wait(timeout=10)
            captured["state_b"] = runtime.prepare_story_runtime(
                plugin_root,
                settings,
                current_home=home,
                repository_factory=lambda _: repository_b,
            )
        except BaseException as exc:  # noqa: BLE001  re-raised on the main thread
            errors.append(exc)
        finally:
            second_done.set()

    threads = [
        threading.Thread(target=first_request),
        threading.Thread(target=second_request),
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        first_prepared.set()
        second_done.set()
        for thread in threads:
            thread.join(timeout=10)

    assert not errors, errors
    state_a = captured["state_a"]
    state_b = captured["state_b"]
    # Each request owns its state; a later rebuild cannot rewrite an older one.
    assert state_a is not state_b
    assert captured["after_repository"] is repository_a
    assert captured["after_permissions"] is captured["permissions_a"]
    assert captured["after_sessions"] is captured["sessions_a"]
    assert captured["after_gate"] is not None
    assert captured["after_row"] is not None
    # The Gateway lookup still exposes the most recently prepared state.
    assert runtime.runtime_state_for(plugin_root, home) is state_b


def test_corrupt_binding_state_fails_closed_without_rewriting(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    profile_home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    binding_path = (
        profile_home / "plugin-data" / "story-construction" / "sessions.json"
    )
    binding_path.parent.mkdir(parents=True)
    binding_path.write_text("{broken", encoding="utf-8")

    state = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=profile_home, vault=vault),
        current_home=profile_home,
        repository_factory=lambda _: object(),
    )

    assert state.ready is False
    assert state.status.code == "binding_state_invalid"
    assert state.repository is None
    assert state.sessions.path is None
    assert state.sessions.locked_profile == "writer"
    assert state.sessions.all() == ()
    assert binding_path.read_text(encoding="utf-8") == "{broken"


def test_permission_snapshot_reflects_latest_durable_bindings(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    state = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home, vault=vault),
        current_home=home,
        repository_factory=lambda _: object(),
    )
    assert state.ready is True

    assert runtime.permission_snapshot(state).bound_scope("stored-a") is None

    writer = StorySessionRegistry(state.sessions.path, locked_profile="writer")
    writer.bind(
        stored_session_id="stored-a",
        runtime_session_id="runtime-a",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    snapshot_bound = runtime.permission_snapshot(state)
    assert snapshot_bound.bound_scope("stored-a").project_id == "p1"
    assert snapshot_bound.bound_scope("runtime-a").project_id == "p1"
    # A snapshot never mutates the state's own in-memory gate.
    assert state.permissions.bound_scope("stored-a") is None

    writer.unbind(stored_session_id="stored-a", profile="writer", connection_id="local")
    assert runtime.permission_snapshot(state).bound_scope("stored-a") is None


def test_permission_snapshot_denies_after_binding_file_deleted(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    state = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home, vault=vault),
        current_home=home,
        repository_factory=lambda _: object(),
    )
    state.sessions.bind(
        stored_session_id="stored-a",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    assert runtime.permission_snapshot(state).bound_scope("stored-a") is not None

    state.sessions.path.unlink()

    assert runtime.permission_snapshot(state).bound_scope("stored-a") is None


def test_permission_snapshot_fails_closed_on_malformed_bindings(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    state = runtime.prepare_story_runtime(
        plugin_root,
        _settings(home=home, vault=vault),
        current_home=home,
        repository_factory=lambda _: object(),
    )
    state.sessions.bind(
        stored_session_id="stored-a",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    state.sessions.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(SessionBindingStoreError):
        runtime.permission_snapshot(state)

    # Malformed durable state must never fall back to the in-memory gate.
    assert state.permissions.bound_scope("stored-a") is None
