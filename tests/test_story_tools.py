"""Story tool schemas, structured results, and registration behavior."""

from __future__ import annotations

import json

import pytest

from story_construction_plugin.domain import Character, Chapter, Note, Project, Volume, WorldInfo
from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.repository import ProjectTree
from story_construction_plugin.runtime import permission_snapshot, prepare_story_runtime
from story_construction_plugin.session_store import StorySessionRegistry
from story_construction_plugin.tools import TOOL_SCHEMAS, StoryToolService, register_story_tools


class FakeRepository:
    def __init__(self) -> None:
        self.tree = ProjectTree(
            project=Project("p1", "Demo"),
            world_info=WorldInfo("w1", "World", "p1"),
            world_info_entries=(),
            characters=(Character("c1", "p1", "Hero", "Brave"),),
            categories=(),
            notes=(Note("n1", "p1", "Reference", "Rain", reference=True),),
            volumes=(Volume("v1", "p1", "Volume I"),),
            chapters=(Chapter("ch1", "p1", "v1", "Chapter 1", "Opening"),),
        )

    def get_project(self, project_id):
        assert project_id == "p1"
        return self.tree

    def get_world_info(self, project_id):
        return self.tree.world_info

    def search_world_info(self, project_id, query):
        return ()

    def get_character(self, project_id, character_id):
        return self.tree.characters[0]

    def list_volumes(self, project_id):
        return self.tree.volumes

    def list_chapters(self, project_id, volume_id=None):
        return self.tree.chapters

    def get_chapter(self, project_id, chapter_id):
        return self.tree.chapters[0]

    def search_notes(self, project_id, query):
        return self.tree.notes

    def search_reference_notes(self, project_id, query):
        return self.tree.notes


def _service() -> StoryToolService:
    permissions = StoryPermissionGate({"p1": ("default", "local")})
    permissions.bind_session(SessionScope("s", "desktop", "default", "local", "p1"), "p1")
    return StoryToolService(FakeRepository(), permissions)


def _call(service: StoryToolService, name: str, args: dict) -> dict:
    raw = service.handle(name, args, session_id="s", source="desktop", profile="default", connection_id="local", project_id="p1")
    return json.loads(raw)


@pytest.fixture
def fake_repository() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def ready_state(tmp_path):
    """One ready writer-profile runtime whose durable bindings live on disk."""

    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    state = prepare_story_runtime(
        tmp_path / "plugin",
        {
            "locked_profile": "writer",
            "vault_root": str(vault),
            "locked_hermes_home": str(home),
        },
        current_home=home,
        repository_factory=lambda _: FakeRepository(),
    )
    assert state.ready is True
    return state


def test_story_tools_return_structured_project_scoped_data() -> None:
    service = _service()

    project = _call(service, "story.get_project", {"project_id": "p1"})
    character = _call(service, "story.get_character", {"project_id": "p1", "character_id": "c1"})
    chapters = _call(service, "story.list_chapters", {"project_id": "p1"})

    assert project["ok"] is True
    assert project["project_id"] == "p1"
    assert project["data"]["project"]["name"] == "Demo"
    assert character["data"]["id"] == "c1"
    assert chapters["data"][0]["id"] == "ch1"


def test_missing_project_and_cross_project_reads_are_explicit_errors() -> None:
    service = _service()

    missing = json.loads(service.handle("story.get_project", {}, session_id="s", source="desktop"))
    cross_project = json.loads(
        service.handle("story.get_project", {"project_id": "p2"}, session_id="s", source="desktop", profile="default", connection_id="local")
    )

    assert missing["ok"] is False
    assert missing["error"]["code"] == "missing_project_id"
    assert cross_project["ok"] is False
    assert cross_project["error"]["code"] == "permission_denied"


def test_story_tool_rejects_profile_outside_runtime_lock() -> None:
    permissions = StoryPermissionGate(
        {"p1": ("writer", "local")},
        locked_profile="writer",
    )
    permissions.bind_session(SessionScope("s", "desktop", "writer", "local", "p1"), "p1")
    service = StoryToolService(FakeRepository(), permissions)

    response = json.loads(
        service.handle(
            "story.get_project",
            {"project_id": "p1"},
            session_id="s",
            source="desktop",
            profile="other",
            connection_id="local",
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "profile_lock_mismatch"
    assert "locked profile" in response["error"]["message"]

def test_registration_exposes_only_the_story_read_toolset() -> None:
    calls = []

    class Context:
        def register_tool(self, **kwargs):
            calls.append(kwargs)

    register_story_tools(Context(), FakeRepository(), StoryPermissionGate({"p1": ("default", "local")}))

    names = {call["name"] for call in calls}
    assert names == {
        "story.get_project",
        "story.get_world_info",
        "story.search_world_info",
        "story.get_character",
        "story.list_volumes",
        "story.list_chapters",
        "story.get_chapter",
        "story.search_notes",
        "story.search_reference_notes",
    }
    assert {call["toolset"] for call in calls} == {"story"}


def test_registration_uses_hermes_function_schema_and_preserves_parameters() -> None:
    calls = []

    class Context:
        def register_tool(self, **kwargs):
            calls.append(kwargs)

    register_story_tools(Context(), FakeRepository(), StoryPermissionGate({"p1": ("default", "local")}))

    registered = {call["name"]: call for call in calls}
    assert set(registered) == set(TOOL_SCHEMAS)
    for name, definition in TOOL_SCHEMAS.items():
        schema = registered[name]["schema"]
        assert schema["name"] == name
        assert schema["description"] == "Scoped story project read."
        assert schema["parameters"] == definition["schema"]


def test_gateway_sees_bind_and_unbind_without_reregister(tmp_path, ready_state, fake_repository):
    state = ready_state
    service = StoryToolService(
        fake_repository, state.permissions,
        permissions_provider=lambda: permission_snapshot(state),
    )
    writer = StorySessionRegistry(state.sessions.path, locked_profile="writer")
    writer.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    kwargs = dict(
        session_id="runtime-1", source="desktop", profile="writer", connection_id="local"
    )
    assert json.loads(service.handle("story.get_project", {"project_id": "p1"}, **kwargs))["ok"]
    writer.unbind(stored_session_id="stored-1", profile="writer", connection_id="local")
    assert not json.loads(service.handle("story.get_project", {"project_id": "p1"}, **kwargs))["ok"]


def test_deleted_binding_file_denies_next_call(ready_state, fake_repository):
    state = ready_state
    service = StoryToolService(
        fake_repository, state.permissions,
        permissions_provider=lambda: permission_snapshot(state),
    )
    writer = StorySessionRegistry(state.sessions.path, locked_profile="writer")
    writer.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    kwargs = dict(
        session_id="runtime-1", source="desktop", profile="writer", connection_id="local"
    )
    assert json.loads(service.handle("story.get_project", {"project_id": "p1"}, **kwargs))["ok"]

    state.sessions.path.unlink()

    denied = json.loads(service.handle("story.get_project", {"project_id": "p1"}, **kwargs))
    assert denied["ok"] is False
    assert denied["error"]["code"] != "internal_error"


def test_malformed_binding_file_reports_binding_state_invalid(ready_state, fake_repository):
    state = ready_state
    service = StoryToolService(
        fake_repository, state.permissions,
        permissions_provider=lambda: permission_snapshot(state),
    )
    writer = StorySessionRegistry(state.sessions.path, locked_profile="writer")
    writer.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    state.sessions.path.write_text("{broken", encoding="utf-8")

    response = json.loads(
        service.handle(
            "story.get_project",
            {"project_id": "p1"},
            session_id="runtime-1",
            source="desktop",
            profile="writer",
            connection_id="local",
        )
    )

    assert response["ok"] is False
    assert response["error"]["code"] == "binding_state_invalid"


def test_wrong_connection_profile_or_project_is_denied(ready_state, fake_repository):
    state = ready_state
    service = StoryToolService(
        fake_repository, state.permissions,
        permissions_provider=lambda: permission_snapshot(state),
    )
    StorySessionRegistry(state.sessions.path, locked_profile="writer").bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )

    wrong_claims = (
        dict(
            session_id="runtime-1",
            source="desktop",
            profile="writer",
            connection_id="remote",
        ),
        dict(
            session_id="runtime-1",
            source="desktop",
            profile="other",
            connection_id="local",
        ),
        dict(
            session_id="runtime-1",
            source="desktop",
            profile="writer",
            connection_id="local",
        ),
    )
    for kwargs, project_id in zip(wrong_claims, ("p1", "p1", "p2")):
        response = json.loads(
            service.handle("story.get_project", {"project_id": project_id}, **kwargs)
        )
        assert response["ok"] is False
