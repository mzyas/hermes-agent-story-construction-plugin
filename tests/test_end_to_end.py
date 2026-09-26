"""Reproducible Story tool -> ToolMessage -> draft -> confirmed Obsidian save flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from story_construction_plugin import register
from story_construction_plugin import runtime
from story_construction_plugin.obsidian_repository import ObsidianProjectRepository
from story_construction_plugin.permissions import SessionScope
from story_construction_plugin.prompt_templates import (
    build_story_request_messages,
    compose_story_system_prompt,
)
from story_construction_plugin.repository import RepositoryError
from story_construction_plugin.save_service import SaveRequest, StorySaveService
from story_construction_plugin.session_store import StorySessionRegistry
from story_construction_plugin.tools import StoryToolService


class RegistrationContext:
    def __init__(self, settings: dict[str, object] | None = None) -> None:
        self.settings = dict(settings or {})
        self.skills = []
        self.sections = []
        self.tools = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_skill(self, *args):
        self.skills.append(args)

    def register_system_prompt_section(self, *args, **kwargs):
        self.sections.append((args, kwargs))

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)


def test_normal_session_without_vault_does_not_receive_story_tools() -> None:
    context = RegistrationContext()
    register(context)
    assert context.tools == []
    assert context.skills
    assert context.sections


def test_configured_vault_registers_only_story_toolset(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    context = RegistrationContext({
        "locked_profile": "writer",
        "vault_root": str(tmp_path),
        "locked_hermes_home": str(home),
    })
    register(context)
    assert context.tools
    assert {tool["toolset"] for tool in context.tools} == {"story"}
    assert {tool["name"] for tool in context.tools} >= {"story.get_project", "story.get_chapter"}


def test_unreachable_vault_is_unavailable_instead_of_falling_back(tmp_path: Path) -> None:
    with pytest.raises(RepositoryError, match="Vault root does not exist"):
        ObsidianProjectRepository(tmp_path / "remote-vault")


def test_project_session_lifecycle_and_confirmed_save_round_trip(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    hermes_home = tmp_path / "hermes-home"
    vault.mkdir()
    hermes_home.mkdir()
    plugin_root = tmp_path / "plugin"
    repository = ObsidianProjectRepository(vault)
    created = repository.create_project("Novel", slug="novel")
    project = created.project
    chapter = created.chapters[0]
    settings = {
        "locked_profile": "writer",
        "vault_root": str(vault),
        "locked_hermes_home": str(hermes_home),
    }

    initial = runtime.prepare_story_runtime(
        plugin_root, settings, current_home=hermes_home,
    )
    assert initial.ready is True
    initial_registry = initial.sessions
    state = runtime.prepare_story_runtime(
        plugin_root, settings, current_home=hermes_home,
    )
    assert state.ready is True
    assert state.sessions is not initial_registry

    stable_before_binding = compose_story_system_prompt(
        "Hermes base",
        state.sessions.render_system_prompt({"profile": "writer"}),
    )
    binding = state.sessions.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="desktop-1",
        project_id=project.id,
        project_name=project.name,
        title="Story: Novel",
    )
    for session_id in (binding.stored_session_id, binding.runtime_session_id):
        assert session_id is not None
        state.permissions.bind_session(
            SessionScope(
                session_id, "desktop", "writer", "desktop-1", project.id,
            ),
            project.id,
        )
    stable_after_binding = compose_story_system_prompt(
        "Hermes base",
        state.sessions.render_system_prompt({"profile": "writer"}),
    )
    assert stable_after_binding == stable_before_binding
    assert project.id not in stable_after_binding
    assert chapter.id not in stable_after_binding

    tools = StoryToolService(state.repository, state.permissions)
    tool_result = tools.handle(
        "story.get_chapter",
        {"project_id": project.id, "chapter_id": chapter.id},
        session_id="runtime-1",
        source="desktop",
        profile="writer",
        connection_id="desktop-1",
        project_id=project.id,
    )
    parsed = json.loads(tool_result)
    assert parsed["ok"] is True
    assert parsed["data"]["id"] == chapter.id

    messages = build_story_request_messages(
        stable_system_prompt=stable_after_binding,
        history=[{"role": "tool", "name": "story.get_chapter", "content": tool_result}],
        current_user_message=(
            f"project_id: {project.id}\nchapter_id: {chapter.id}\nDraft the opening."
        ),
    )
    assert messages[0]["content"] == stable_after_binding
    assert project.id not in messages[0]["content"]
    assert chapter.id not in messages[0]["content"]
    assert messages[1]["role"] == "tool"
    assert chapter.id in messages[1]["content"]
    assert f"project_id: {project.id}" in messages[-1]["content"]
    assert f"chapter_id: {chapter.id}" in messages[-1]["content"]

    saved = StorySaveService(state.repository, state.permissions).save(SaveRequest(
        session_id="runtime-1",
        profile="writer",
        connection_id="desktop-1",
        project_id=project.id,
        chapter_id=chapter.id,
        content="The opening scene begins with a memory oath.",
        expected_version=chapter.version,
        confirmed=True,
    ))
    assert saved.chapter.content.startswith("The opening scene")
    raw = (vault / chapter.source_ref).read_text(encoding="utf-8")
    assert raw.startswith("---\ntype: chapter")
    assert f"id: {chapter.id}" in raw
    assert f"project_id: {project.id}" in raw
    assert f"volume_id: {chapter.volume_id}" in raw
    assert "The opening scene begins with a memory oath." in raw

    restored = runtime.prepare_story_runtime(
        plugin_root, settings, current_home=hermes_home,
    )
    restored_binding = restored.sessions.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="desktop-1",
    )
    assert restored_binding == binding
    assert restored.permissions.bound_scope("stored-1").project_id == project.id
    assert restored.permissions.bound_scope("runtime-1").project_id == project.id


def test_registered_tools_authorize_from_durable_bindings_without_reregistering(
    tmp_path: Path, monkeypatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    project = ObsidianProjectRepository(vault).create_project("Novel", slug="novel").project
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    context = RegistrationContext({
        "locked_profile": "writer",
        "vault_root": str(vault),
        "locked_hermes_home": str(home),
    })
    register(context)
    assert context.tools
    handlers = {tool["name"]: tool["handler"] for tool in context.tools}
    state = runtime.runtime_state_for(Path(__file__).resolve().parents[1], home)
    assert state is not None and state.ready is True
    (_section_name, render_section), _section_kwargs = context.sections[-1]
    stable_before_binding = render_section({"profile": "writer"})
    assert stable_before_binding

    writer = StorySessionRegistry(state.sessions.path, locked_profile="writer")
    writer.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id=project.id,
    )
    kwargs = dict(
        session_id="runtime-1", source="desktop", profile="writer", connection_id="local"
    )
    bound = json.loads(handlers["story.get_project"]({"project_id": project.id}, **kwargs))
    assert bound["ok"] is True

    # The prompt section renders identically before and after binding.
    stable_after_binding = render_section({"profile": "writer"})
    assert stable_after_binding == stable_before_binding

    writer.unbind(stored_session_id="stored-1", profile="writer", connection_id="local")
    denied = json.loads(handlers["story.get_project"]({"project_id": project.id}, **kwargs))
    assert denied["ok"] is False
