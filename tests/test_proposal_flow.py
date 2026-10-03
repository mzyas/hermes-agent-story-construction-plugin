"""The Agent proposes, the person approves, the Agent applies - against a real Vault."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from story_construction_plugin.edits import EditError
from story_construction_plugin.obsidian_repository import ObsidianProjectRepository
from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.proposal_service import ProposalError, StoryProposalService
from story_construction_plugin.proposal_store import ChapterHistory, ProposalStore
from story_construction_plugin.repository import NotFoundError
from story_construction_plugin.tools import StoryToolService

BODY = "他推开门。\n\n雨下得很大，街上没有人。\n\n她在屋里等着。"
CHAPTER = "novel:chapter-1"
SCOPE = {"profile": "writer", "connection_id": "local"}


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.vault = tmp_path / "vault"
        self.vault.mkdir()
        self.repository = ObsidianProjectRepository(self.vault)
        self.repository.create_project("Novel", slug="novel")
        first = self.repository.get_chapter("novel", CHAPTER)
        self.repository.save_chapter("novel", CHAPTER, BODY, expected_version=first.version)
        self.clock = Clock()
        self.data = tmp_path / "plugin-data"
        self.store = ProposalStore(self.data / "proposals.json", now=self.clock)
        self.history = ChapterHistory(self.data / "history")
        self.service = StoryProposalService(self.repository, self.store, self.history)

    @property
    def chapter(self):
        return self.repository.get_chapter("novel", CHAPTER)

    @property
    def file_text(self) -> str:
        return (self.vault / "novel" / "chapters" / "chapter-001.md").read_text(encoding="utf-8")

    def propose(self, edits, version: str | None = None) -> dict:
        return self.service.propose_edit(
            project_id="novel", session_id="s1", **SCOPE, chapter_id=CHAPTER,
            base_version=self.chapter.version if version is None else version, raw_edits=edits,
        )

    def approve(self, proposal_id: str, **extra) -> dict:
        return self.service.approve(project_id="novel", proposal_id=proposal_id, **SCOPE, **extra)

    def apply(self, proposal_id: str, **overrides) -> dict:
        return self.service.apply(project_id="novel", proposal_id=proposal_id, **{**SCOPE, **overrides})


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


RAIN = {"op": "replace", "old_text": "雨下得很大", "new_text": "雨下得很急"}
OPEN = {"op": "replace", "old_text": "他推开门。", "new_text": "他推开了旧木门。"}


def test_proposing_changes_nothing_in_the_vault(env) -> None:
    before = (env.file_text, env.chapter.version)

    summary = env.propose([RAIN])

    assert summary["status"] == "pending" and summary["edits"] == 1 and summary["warnings"] == []
    assert "story.apply_edit" in summary["next"]
    assert (env.file_text, env.chapter.version) == before


def test_applying_before_approval_is_refused(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "not_approved"
    assert "雨下得很大" in env.chapter.content


def test_an_approved_proposal_writes_exactly_the_approved_edit(env) -> None:
    original = env.chapter
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)

    result = env.apply(proposal_id)

    assert result["status"] == "applied" and result["version"] == env.chapter.version
    assert env.chapter.content == BODY.replace("很大", "很急")
    assert env.file_text.startswith("---\n") and "id: novel:chapter-1" in env.file_text
    stored = env.store.get(proposal_id)
    assert stored["status"] == "applied" and stored["applied"]["version_before"] == original.version
    snapshot = env.history.load(project_id="novel", target_id=CHAPTER, snapshot_id=stored["applied"]["snapshot_id"])
    assert snapshot["text"] == BODY and snapshot["version"] == original.version


def test_a_proposal_can_only_be_applied_once(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "already_applied"


def test_only_the_selected_edits_are_written(env) -> None:
    proposal_id = env.propose([OPEN, RAIN])["proposal_id"]
    env.approve(proposal_id, selected=[1])

    env.apply(proposal_id)

    assert "雨下得很急" in env.chapter.content and "旧木门" not in env.chapter.content


def test_an_empty_or_invalid_selection_is_refused(env) -> None:
    proposal_id = env.propose([OPEN, RAIN])["proposal_id"]

    for selected in ([], [5], [-1]):
        with pytest.raises(ProposalError) as error:
            env.approve(proposal_id, selected=selected)
        assert error.value.code == "invalid_selection"


def test_edits_still_apply_after_the_person_changed_another_part(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.repository.save_chapter(
        "novel", CHAPTER, BODY.replace("她在屋里等着。", "她在屋里等了很久。"), expected_version=env.chapter.version
    )

    env.apply(proposal_id)

    assert env.chapter.content == BODY.replace("很大", "很急").replace("等着", "等了很久")


def test_an_edit_whose_text_disappeared_conflicts_and_writes_nothing(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    changed = env.repository.save_chapter(
        "novel", CHAPTER, BODY.replace("雨下得很大", "雨一直下"), expected_version=env.chapter.version
    )

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "conflict" and error.value.details["reason"] == "edit_not_found"
    assert env.chapter.version == changed.version and "雨一直下" in env.chapter.content
    assert env.store.get(proposal_id)["status"] == "approved"


def test_approving_against_a_chapter_that_no_longer_matches_is_refused(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.repository.save_chapter(
        "novel", CHAPTER, BODY.replace("雨下得很大", "雨一直下"), expected_version=env.chapter.version
    )

    with pytest.raises(ProposalError) as error:
        env.approve(proposal_id)

    assert error.value.code == "conflict"
    assert env.store.get(proposal_id)["status"] == "pending"


def test_an_approval_runs_out_after_fifteen_minutes(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.clock.moment += timedelta(minutes=14)
    assert env.store.get(proposal_id)["status"] == "approved"
    env.clock.moment += timedelta(minutes=2)

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "approval_expired" and "雨下得很大" in env.chapter.content


def test_an_expired_approval_can_be_given_again(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.clock.moment += timedelta(minutes=16)
    assert env.store.get(proposal_id)["status"] == "expired"

    env.approve(proposal_id)
    env.apply(proposal_id)

    assert "雨下得很急" in env.chapter.content


def test_a_revoked_approval_cannot_be_used(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.service.revoke(project_id="novel", proposal_id=proposal_id, **SCOPE)

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "not_approved"


def test_a_discarded_or_replaced_proposal_cannot_be_approved(env) -> None:
    first = env.propose([RAIN])["proposal_id"]
    second = env.propose([OPEN])["proposal_id"]
    env.service.discard(project_id="novel", proposal_id=second, **SCOPE)

    for proposal_id in (first, second):
        with pytest.raises(ProposalError) as error:
            env.approve(proposal_id)
        assert error.value.code == "proposal_closed"


def test_tampering_with_the_stored_approval_is_detected(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    path = env.data / "proposals.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["proposals"][0]["approval"]["digest"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "approval_mismatch" and "雨下得很大" in env.chapter.content


def test_an_edited_approved_text_is_written_as_the_person_left_it(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    version = env.chapter.version
    env.approve(proposal_id, text="他推开门。\n\n雨下得很急，我改了这句。", base_version=version)

    env.apply(proposal_id)

    assert env.chapter.content == "他推开门。\n\n雨下得很急，我改了这句。"


def test_an_edited_text_is_tied_to_the_version_it_was_edited_against(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    stale = env.chapter.version
    env.repository.save_chapter("novel", CHAPTER, BODY + "\n\n新的一段。", expected_version=stale)

    with pytest.raises(ProposalError) as error:
        env.approve(proposal_id, text="x 正文", base_version=stale)
    assert error.value.code == "version_changed"

    env.approve(proposal_id, text="正文替换", base_version=env.chapter.version)
    env.repository.save_chapter("novel", CHAPTER, "又改了。", expected_version=env.chapter.version)
    with pytest.raises(ProposalError) as again:
        env.apply(proposal_id)
    assert again.value.code == "version_changed" and env.chapter.content == "又改了。"


def test_an_edited_text_with_frontmatter_is_refused(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]

    with pytest.raises(ProposalError) as error:
        env.approve(proposal_id, text="---\nid: x\n---\n正文", base_version=env.chapter.version)

    assert error.value.code == "frontmatter_not_allowed"


def test_a_proposal_against_an_old_version_is_rejected_with_the_current_one(env) -> None:
    with pytest.raises(ProposalError) as error:
        env.propose([RAIN], version="stale")

    assert error.value.code == "version_changed"
    assert error.value.details["current_version"] == env.chapter.version


def test_unmatched_ambiguous_and_no_op_proposals_are_rejected(env) -> None:
    with pytest.raises(EditError) as missing:
        env.propose([{"op": "replace", "old_text": "没有这句", "new_text": "x"}])
    with pytest.raises(EditError) as ambiguous:
        env.propose([{"op": "replace", "old_text": "。", "new_text": "！"}])
    with pytest.raises(ProposalError) as same:
        env.propose([{"op": "replace", "old_text": "雨下得很大", "new_text": "雨下得很大"}])

    assert (missing.value.code, ambiguous.value.code, same.value.code) == (
        "edit_not_found", "edit_ambiguous", "no_change",
    )
    assert env.store.list_for_project(project_id="novel", profile="writer", connection_id="local") == []


def test_the_list_carries_the_chapters_current_version(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    (row,) = env.service.list_open(project_id="novel", **SCOPE)
    assert row["id"] == proposal_id and row["current_version"] == row["base_version"] == env.chapter.version

    env.repository.save_chapter("novel", CHAPTER, BODY + "\n\n新的一段。", expected_version=env.chapter.version)
    (row,) = env.service.list_open(project_id="novel", **SCOPE)
    assert row["current_version"] == env.chapter.version != row["base_version"]


def test_guidance_text_is_flagged_for_the_person_not_hidden(env) -> None:
    summary = env.propose([
        {"op": "append", "new_text": "好的，这是新的一段：\n天亮了。\n希望你喜欢。"},
    ])

    kinds = {warning["kind"] for warning in summary["warnings"]}
    assert kinds == {"leading_guidance", "trailing_guidance"}
    view = env.service.list_open(project_id="novel", **SCOPE)[0]
    assert view["warnings"] and view["previews"][0]["regions"]


def test_a_new_chapter_is_created_with_its_text_after_approval(env) -> None:
    summary = env.service.propose_chapter(
        project_id="novel", session_id="s1", **SCOPE,
        volume_id="novel:volume-1", title="第二章 天亮", content="天亮了。\n\n雨停了。",
    )
    assert [c.id for c in env.repository.get_project("novel").chapters] == [CHAPTER]
    env.approve(summary["proposal_id"])

    result = env.apply(summary["proposal_id"])

    created = env.repository.get_chapter("novel", result["chapter_id"])
    assert created.title == "第二章 天亮" and created.content == "天亮了。\n\n雨停了。"
    assert created.volume_id == "novel:volume-1"


def test_a_new_chapter_needs_a_real_volume_and_a_title(env) -> None:
    with pytest.raises(NotFoundError):
        env.service.propose_chapter(
            project_id="novel", session_id="s1", **SCOPE, volume_id="novel:volume-9", title="X", content="y"
        )
    with pytest.raises(ProposalError) as error:
        env.service.propose_chapter(
            project_id="novel", session_id="s1", **SCOPE, volume_id="novel:volume-1", title="  ", content="y"
        )
    assert error.value.code == "invalid_title"


def test_undo_restores_the_text_from_before_the_write(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)

    restored = env.service.undo(project_id="novel", chapter_id=CHAPTER)

    assert env.chapter.content == BODY and restored["version"] == env.chapter.version
    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", chapter_id=CHAPTER)
    assert error.value.code == "nothing_to_undo"
    assert env.service.writes(project_id="novel")[0]["undone"] is True


def test_undo_refuses_when_the_person_edited_after_the_write(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)
    env.repository.save_chapter("novel", CHAPTER, "我自己改的。", expected_version=env.chapter.version)

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", chapter_id=CHAPTER)

    assert error.value.code == "chapter_changed" and env.chapter.content == "我自己改的。"


def test_a_chapter_the_agent_created_has_no_undo(env) -> None:
    summary = env.service.propose_chapter(
        project_id="novel", session_id="s1", **SCOPE,
        volume_id="novel:volume-1", title="新章", content="正文。",
    )
    env.approve(summary["proposal_id"])
    created = env.apply(summary["proposal_id"])

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", chapter_id=created["chapter_id"])

    assert error.value.code == "undo_unsupported"


def test_other_profiles_and_projects_cannot_touch_a_proposal(env) -> None:
    proposal_id = env.propose([RAIN])["proposal_id"]

    with pytest.raises(NotFoundError):
        env.service.approve(project_id="novel", proposal_id=proposal_id, profile="other", connection_id="local")
    with pytest.raises(NotFoundError):
        env.service.approve(project_id="other", proposal_id=proposal_id, **SCOPE)
    with pytest.raises(NotFoundError):
        env.apply(proposal_id, connection_id="remote")
    with pytest.raises(NotFoundError):
        env.apply("missing")


# ------------------------------------------------------------ through the tool
def _tools(env: Env, *, bound: bool = True) -> StoryToolService:
    permissions = StoryPermissionGate({"novel": ("writer", "local")}, locked_profile="writer")
    if bound:
        permissions.bind_session(SessionScope("s1", "desktop", "writer", "local", "novel"), "novel")
    return StoryToolService(
        env.repository, permissions, proposals_provider=lambda: env.service
    )


def _tool(service: StoryToolService, name: str, args: dict) -> dict:
    scope = {"session_id": "s1", "source": "desktop", "profile": "writer", "connection_id": "local"}
    return json.loads(service.handle(name, args, **scope))


def test_the_tools_propose_wait_for_approval_and_then_apply(env) -> None:
    tools = _tools(env)
    proposed = _tool(tools, "story.propose_edit", {
        "chapter_id": CHAPTER, "base_version": env.chapter.version, "edits": [RAIN],
    })
    assert proposed["ok"] is True and proposed["data"]["status"] == "pending"
    proposal_id = proposed["data"]["proposal_id"]

    blocked = _tool(tools, "story.apply_edit", {"proposal_id": proposal_id})
    assert blocked["ok"] is False and blocked["error"]["code"] == "not_approved"
    assert "雨下得很大" in env.chapter.content

    env.approve(proposal_id)
    applied = _tool(tools, "story.apply_edit", {"proposal_id": proposal_id})

    assert applied["ok"] is True and applied["data"]["status"] == "applied"
    assert "雨下得很急" in env.chapter.content


def test_the_apply_tool_takes_no_content_so_it_cannot_write_other_text(env) -> None:
    tools = _tools(env)
    proposal_id = _tool(tools, "story.propose_edit", {
        "chapter_id": CHAPTER, "base_version": env.chapter.version, "edits": [RAIN],
    })["data"]["proposal_id"]
    env.approve(proposal_id)

    _tool(tools, "story.apply_edit", {"proposal_id": proposal_id, "content": "别的内容", "new_text": "别的内容"})

    assert "别的内容" not in env.chapter.content and "雨下得很急" in env.chapter.content


def test_tool_errors_are_structured_and_an_unbound_session_cannot_propose(env) -> None:
    tools = _tools(env)
    failed = _tool(tools, "story.propose_edit", {
        "chapter_id": CHAPTER, "base_version": env.chapter.version,
        "edits": [{"op": "replace", "old_text": "。", "new_text": "！"}],
    })
    assert failed["ok"] is False and failed["error"]["code"] == "edit_ambiguous" and failed["edit"] == 0

    unbound = _tool(_tools(env, bound=False), "story.propose_edit", {
        "chapter_id": CHAPTER, "base_version": "x", "edits": [RAIN],
    })
    assert unbound["error"]["code"] == "session_not_bound"


def test_the_model_cannot_name_another_project(env) -> None:
    env.repository.create_project("Other", slug="other")
    tools = _tools(env)

    response = _tool(tools, "story.propose_edit", {
        "project_id": "other", "chapter_id": "other:chapter-1", "base_version": "x", "edits": [RAIN],
    })

    assert response["ok"] is False
    assert env.store.list_for_project(project_id="other", profile="writer", connection_id="local") == []


def test_without_a_proposal_service_the_tools_say_so(env) -> None:
    permissions = StoryPermissionGate({"novel": ("writer", "local")}, locked_profile="writer")
    permissions.bind_session(SessionScope("s1", "desktop", "writer", "local", "novel"), "novel")
    tools = StoryToolService(env.repository, permissions)

    response = _tool(tools, "story.propose_edit", {"chapter_id": CHAPTER, "base_version": "x", "edits": [RAIN]})

    assert response["error"]["code"] == "proposals_unavailable"
