"""Compressed and delegated sessions act as the Story session they came from."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import story_construction_plugin
from story_construction_plugin import register, runtime
from story_construction_plugin.obsidian_repository import ObsidianProjectRepository
from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.session_lineage import (
    SessionLineage,
    ancestry,
    parent_link,
    state_db_ancestry,
    state_db_session,
)
from story_construction_plugin.session_store import StorySessionRegistry
from story_construction_plugin.tools import WRITE_TOOLS, StoryToolService

from test_story_tools import FakeRepository


def _bound(*ids: str):
    return lambda session_id: session_id in ids


def _lookup(links: dict[str, tuple[str, bool]], calls: list[str] | None = None):
    """A database walk: every link above the asked id, as Hermes' rows would give it."""

    def lookup(session_id: str):
        if calls is not None:
            calls.append(session_id)
        found, current = {}, session_id
        while current in links and current not in found:
            found[current] = links[current]
            current = links[current][0]
        return found

    return lookup


# ------------------------------------------------------------------ walking the chain
def test_a_bound_session_resolves_to_itself() -> None:
    resolved = SessionLineage().resolve("root", _bound("root"))

    assert resolved is not None
    assert (resolved.session_id, resolved.delegated) == ("root", False)


def test_a_session_compressed_twice_resolves_to_the_bound_root() -> None:
    lineage = SessionLineage(_lookup({"c2": ("c1", False), "c1": ("root", False)}))

    resolved = lineage.resolve("c2", _bound("root"))

    assert resolved is not None
    assert (resolved.session_id, resolved.delegated) == ("root", False)


def test_a_long_novel_session_compressed_many_times_still_resolves() -> None:
    # Real compression chains run about 180 deep.
    chain = {f"c{n}": (f"c{n - 1}" if n > 1 else "root", False) for n in range(1, 301)}
    calls: list[str] = []
    lineage = SessionLineage(_lookup(chain, calls))

    resolved = lineage.resolve("c300", _bound("root"))

    assert resolved is not None and resolved.session_id == "root"
    assert calls == ["c300"]  # one database walk, not one per hop


def test_a_subagent_announced_by_the_hook_resolves_as_delegated() -> None:
    lineage = SessionLineage()
    lineage.note_subagent(parent_session_id="root", child_session_id="sub", child_role="leaf")

    resolved = lineage.resolve("sub", _bound("root"))

    assert resolved is not None
    assert (resolved.session_id, resolved.delegated) == ("root", True)


def test_a_subagent_of_a_compressed_session_stays_delegated() -> None:
    lineage = SessionLineage(_lookup({"c1": ("root", False)}))
    lineage.note_subagent(parent_session_id="c1", child_session_id="sub")

    resolved = lineage.resolve("sub", _bound("root"))

    assert resolved is not None
    assert (resolved.session_id, resolved.delegated) == ("root", True)


def test_an_ordinary_chat_resolves_to_nothing() -> None:
    lineage = SessionLineage(_lookup({"c1": ("other", False)}))

    assert lineage.resolve("c1", _bound("root")) is None
    assert lineage.resolve("", _bound("root")) is None


def test_a_failing_lookup_or_a_loop_resolves_to_nothing() -> None:
    def broken(_session_id):
        raise OSError("state.db is locked")

    assert SessionLineage(broken).resolve("c1", _bound("root")) is None
    looped = SessionLineage(_lookup({"a": ("b", False), "b": ("a", False)}))
    assert looped.resolve("a", _bound("root")) is None


def test_a_found_parent_is_looked_up_once() -> None:
    calls: list[str] = []
    lineage = SessionLineage(_lookup({"c2": ("c1", False), "c1": ("root", False)}, calls))

    lineage.resolve("c2", _bound("root"))
    lineage.resolve("c2", _bound("root"))
    lineage.resolve("c1", _bound("root"))

    assert calls == ["c2"]


# ------------------------------------------------------------------ reading Hermes rows
class FakeSessionDb:
    def __init__(self, rows: dict[str, dict]) -> None:
        self.rows = {key: {"id": key, **row} for key, row in rows.items()}
        self.reads: list[str] = []

    def get_session(self, session_id):
        self.reads.append(session_id)
        return self.rows.get(session_id)


def test_a_compression_child_links_to_its_parent() -> None:
    db = FakeSessionDb({
        "root": {"end_reason": "compression"},
        "c1": {"parent_session_id": "root", "model_config": "{}"},
    })

    assert parent_link(db, "c1") == ("root", False)


def test_a_delegated_child_links_to_its_parent_as_a_subagent() -> None:
    db = FakeSessionDb({
        "root": {},
        "sub": {"parent_session_id": "root", "model_config": json.dumps({"_delegate_from": "root"})},
    })

    assert parent_link(db, "sub") == ("root", True)


def test_a_compressed_subagent_keeps_its_main_session_marker_but_links_to_the_subagent() -> None:
    # Hermes copies the subagent's model_config onto its compression child.
    db = FakeSessionDb({
        "root": {},
        "sub": {"parent_session_id": "root", "end_reason": "compression",
                "model_config": {"_delegate_from": "root"}},
        "sub2": {"parent_session_id": "sub", "model_config": {"_delegate_from": "root"}},
    })

    assert ancestry(db, "sub2") == {"sub2": ("sub", False), "sub": ("root", True)}


def test_branches_resets_tool_children_and_unrelated_rows_have_no_link() -> None:
    db = FakeSessionDb({
        "root": {"end_reason": "compression"},
        "branch": {"parent_session_id": "root", "model_config": {"_branched_from": "root"}},
        "reset": {"parent_session_id": "root", "model_config": {"_reset_from": "root"}},
        "tool": {"parent_session_id": "root", "source": "tool"},
        "open": {"end_reason": None},
        "after_open": {"parent_session_id": "open"},
        "orphan": {},
    })

    for session_id in ("branch", "reset", "tool", "after_open", "orphan", "missing"):
        assert parent_link(db, session_id) is None


def test_a_walk_reads_each_row_once() -> None:
    db = FakeSessionDb({
        "root": {"end_reason": "compression"},
        "c1": {"parent_session_id": "root", "end_reason": "compression"},
        "c2": {"parent_session_id": "c1"},
    })

    assert ancestry(db, "c2") == {"c2": ("c1", False), "c1": ("root", False)}
    assert db.reads == ["c2", "c1", "root"]


def test_no_session_database_means_no_links(tmp_path) -> None:
    assert state_db_ancestry(tmp_path, "c1") == {}


@pytest.mark.hermes_integration
def test_links_match_a_real_hermes_session_database(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from hermes_state import SessionDB

    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("root", "desktop")
        db.end_session("root", "compression")
        db.create_session("c1", "desktop", parent_session_id="root")
        db.end_session("c1", "compression")
        db.create_session("c2", "desktop", parent_session_id="c1")
        db.create_session("sub", "subagent", parent_session_id="c2", model_config={"_delegate_from": "c2"})
        db.end_session("sub", "compression")
        db.create_session("sub2", "subagent", parent_session_id="sub", model_config={"_delegate_from": "c2"})
        db.create_session("branch", "desktop", parent_session_id="c2", model_config={"_branched_from": "c2"})
        db.create_session("tool", "tool", parent_session_id="c2")
        expected_lineage = db.get_compression_lineage("c2")
    finally:
        db.close()

    links = state_db_ancestry(tmp_path, "sub2")

    assert links == {
        "sub2": ("sub", False), "sub": ("c2", True), "c2": ("c1", False), "c1": ("root", False),
    }
    assert expected_lineage == ["root", "c1", "c2"]
    assert state_db_ancestry(tmp_path, "branch") == {}
    assert state_db_ancestry(tmp_path, "tool") == {}


@pytest.mark.hermes_integration
def test_a_real_session_row_shows_its_messages_and_stored_prompt(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from hermes_state import SessionDB

    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("fresh", "desktop")
        db.create_session("busy", "desktop", system_prompt="Hermes base\n\n# StoryConstructionAgentPrompt v11")
        db.append_message("busy", role="user", content="hello")
    finally:
        db.close()

    fresh = state_db_session(tmp_path, "fresh")
    busy = state_db_session(tmp_path, "busy")

    assert fresh["message_count"] == 0 and not fresh["system_prompt"]
    assert busy["message_count"] == 1
    assert "# StoryConstructionAgentPrompt" in busy["system_prompt"]
    assert state_db_session(tmp_path, "missing") is None
    assert state_db_session(tmp_path / "no-home", "fresh") is None


# ------------------------------------------------------------------ the tools
def _service(lineage: SessionLineage) -> StoryToolService:
    permissions = StoryPermissionGate({"p1": ("default", "local")})
    permissions.bind_session(SessionScope("root", "desktop", "default", "local", "p1"), "p1")
    return StoryToolService(FakeRepository(), permissions, lineage=lineage)


def _call(service: StoryToolService, tool: str, session_id: str, args: dict | None = None) -> dict:
    # Hermes passes only the session id; the binding supplies the rest of the scope.
    return json.loads(service.handle(tool, args, session_id=session_id, task_id="t"))


def test_a_compressed_session_keeps_its_story_tools() -> None:
    service = _service(SessionLineage(_lookup({"c2": ("c1", False), "c1": ("root", False)})))

    response = _call(service, "story.get_session_project", "c2")

    assert response["ok"] is True
    assert response["project_id"] == "p1"


def test_a_subagent_can_read_the_story_but_not_change_it() -> None:
    lineage = SessionLineage()
    lineage.note_subagent(parent_session_id="root", child_session_id="sub")
    service = _service(lineage)

    assert _call(service, "story.get_session_project", "sub")["ok"] is True
    for tool in sorted(WRITE_TOOLS):
        response = _call(service, tool, "sub", {"proposal_id": "x", "target_id": "ch1"})
        assert response["ok"] is False
        assert response["error"]["code"] == "subagent_read_only"
    assert {"story.propose_rename", "story.propose_delete"} <= WRITE_TOOLS


def test_an_ordinary_chat_is_still_not_bound() -> None:
    service = _service(SessionLineage(_lookup({})))

    response = _call(service, "story.get_session_project", "chat")

    assert response["error"]["code"] == "session_not_bound"


# ------------------------------------------------------------------ the approval prompt
class RegistrationContext:
    def __init__(self, settings: dict[str, object]) -> None:
        self.settings = settings
        self.tools: dict[str, object] = {}
        self.hooks: dict[str, object] = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_skill(self, *args) -> None:
        pass

    def register_system_prompt_section(self, *args, **kwargs) -> None:
        pass

    def register_tool(self, **kwargs) -> None:
        self.tools[kwargs["name"]] = kwargs["handler"]

    def register_hook(self, name, callback) -> None:
        self.hooks[name] = callback


def test_the_approval_prompt_follows_compression_but_never_reaches_a_subagent(
    tmp_path: Path, monkeypatch
) -> None:
    home, vault = tmp_path / "home", tmp_path / "vault"
    home.mkdir()
    vault.mkdir()
    ObsidianProjectRepository(vault).create_project("Novel", slug="novel")
    monkeypatch.setattr(runtime, "get_hermes_home", lambda: home)
    monkeypatch.setattr(
        story_construction_plugin, "state_db_ancestry",
        lambda _home, session_id: {"c1": ("root", False)} if session_id == "c1" else {},
    )
    ctx = RegistrationContext(
        {"locked_profile": "writer", "vault_root": str(vault), "locked_hermes_home": str(home)}
    )
    register(ctx)
    StorySessionRegistry(runtime._session_state_path(home), locked_profile="writer").bind(
        stored_session_id="root", profile="writer", connection_id="local", project_id="novel"
    )
    proposed = json.loads(ctx.tools["story.propose_new"](
        {"target_type": "character", "title": "苏晴", "content": "冷静的医生。"}, session_id="c1"
    ))
    assert proposed["ok"] is True, proposed
    proposal_id = proposed["data"]["proposal_id"]
    ask = ctx.hooks["pre_tool_call"]

    directive = ask(tool_name="story.apply_edit", args={"proposal_id": proposal_id}, session_id="c1")

    assert directive is not None and directive["action"] == "approve"
    ctx.hooks["subagent_start"](parent_session_id="root", child_session_id="sub")
    assert ask(tool_name="story.apply_edit", args={"proposal_id": proposal_id}, session_id="sub") is None
    refused = json.loads(ctx.tools["story.apply_edit"]({"proposal_id": proposal_id}, session_id="sub"))
    assert refused["error"]["code"] == "subagent_read_only"
