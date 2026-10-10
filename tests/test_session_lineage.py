"""Compressed and delegated sessions act as the Story session they came from."""

from __future__ import annotations

import json

from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.session_lineage import SessionLineage, parent_link
from story_construction_plugin.tools import StoryToolService

from test_story_tools import FakeRepository


def _bound(*ids: str):
    return lambda session_id: session_id in ids


def _lookup(links: dict[str, tuple[str, bool]], calls: list[str] | None = None):
    def lookup(session_id: str):
        if calls is not None:
            calls.append(session_id)
        return links.get(session_id)

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
    lineage = SessionLineage(_lookup({"c1": ("root", False)}, calls))

    lineage.resolve("c1", _bound("root"))
    lineage.resolve("c1", _bound("root"))

    assert calls == ["c1"]


# ------------------------------------------------------------------ reading Hermes rows
class FakeSessionDb:
    def __init__(self, rows: dict[str, dict], forks: set[str] = frozenset()) -> None:
        self.rows = rows
        self.forks = forks

    def get_session(self, session_id):
        return self.rows.get(session_id)

    def is_explicit_fork_child(self, session_id):
        return session_id in self.forks


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


def test_branches_resets_and_unrelated_rows_have_no_link() -> None:
    db = FakeSessionDb(
        {
            "root": {"end_reason": "compression"},
            "branch": {"parent_session_id": "root", "model_config": {"_branched_from": "root"}},
            "reset": {"parent_session_id": "root", "model_config": {"_reset_from": "root"}},
            "open": {"end_reason": None},
            "after_open": {"parent_session_id": "open"},
            "orphan": {},
        },
        forks={"branch"},
    )

    for session_id in ("branch", "reset", "after_open", "orphan", "missing"):
        assert parent_link(db, session_id) is None


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
    for tool in ("story.propose_edit", "story.propose_new", "story.apply_edit"):
        response = _call(service, tool, "sub", {"proposal_id": "x", "target_id": "ch1"})
        assert response["ok"] is False
        assert response["error"]["code"] == "subagent_read_only"


def test_an_ordinary_chat_is_still_not_bound() -> None:
    service = _service(SessionLineage(_lookup({})))

    response = _call(service, "story.get_session_project", "chat")

    assert response["error"]["code"] == "session_not_bound"
