"""Proposals for characters, world entries and notes follow the chapter rules."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from story_construction_plugin.obsidian_repository import ObsidianProjectRepository
from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.proposal_service import ProposalError, StoryProposalService
from story_construction_plugin.proposal_store import ChapterHistory, ProposalStore
from story_construction_plugin.repository import NotFoundError
from story_construction_plugin.tools import StoryToolService

SCOPE = {"profile": "writer", "connection_id": "local"}
REPLACE = {"op": "replace", "old_text": "少年", "new_text": "青年"}
ADD = {"op": "append", "new_text": "他怕黑。"}


class Env:
    def __init__(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        self.vault = vault
        self.repository = ObsidianProjectRepository(vault)
        self.repository.create_project("Novel", slug="novel")
        self.character = self.repository.create_character("novel", "林远", "少年，住在阁楼。")
        self.entry = self.repository.create_world_entry("novel", "钟楼", "镇上最高的建筑，少年常去。")
        self.note = self.repository.create_note("novel", "灵感", "少年发现钥匙。")
        data = tmp_path / "plugin-data"
        self.store = ProposalStore(
            data / "proposals.json", now=lambda: datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        )
        self.history = ChapterHistory(data / "history")
        self.service = StoryProposalService(self.repository, self.store, self.history)

    def doc(self, target_type: str):
        return {
            "character": self.repository.get_character,
            "world_entry": self.repository.get_world_entry,
            "note": self.repository.get_note,
        }[target_type]("novel", {"character": self.character, "world_entry": self.entry, "note": self.note}[target_type].id)

    def propose(self, target_type: str, edits, **extra) -> dict:
        record = self.doc(target_type)
        return self.service.propose_edit(
            project_id="novel", session_id="s1", **SCOPE, target_type=target_type,
            target_id=extra.pop("target_id", record.id),
            base_version=extra.pop("base_version", record.version), raw_edits=edits,
        )

    def propose_new(self, target_type: str, title: str, content: str, **extra) -> dict:
        return self.service.propose_new(
            project_id="novel", session_id="s1", **SCOPE,
            target_type=target_type, title=title, content=content, **extra,
        )

    def approve(self, proposal_id: str, **extra) -> dict:
        return self.service.approve(project_id="novel", proposal_id=proposal_id, **SCOPE, **extra)

    def apply(self, proposal_id: str) -> dict:
        return self.service.apply(project_id="novel", proposal_id=proposal_id, **SCOPE)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


TYPES = ["character", "world_entry", "note"]
NAME_OF = {"character": "name", "world_entry": "title", "note": "title"}


# ------------------------------------------------------------------- editing
@pytest.mark.parametrize("target_type", TYPES)
def test_proposing_an_edit_changes_nothing_until_it_is_approved_and_applied(env, target_type) -> None:
    before = env.doc(target_type)

    summary = env.propose(target_type, [REPLACE])

    assert summary["status"] == "pending" and summary["target_type"] == target_type
    assert env.doc(target_type) == before
    with pytest.raises(ProposalError) as error:
        env.apply(summary["proposal_id"])
    assert error.value.code == "not_approved"

    env.approve(summary["proposal_id"])
    result = env.apply(summary["proposal_id"])

    after = env.doc(target_type)
    assert result["status"] == "applied" and result["target_id"] == before.id
    assert "青年" in after.content and "少年" not in after.content
    assert getattr(after, NAME_OF[target_type]) == getattr(before, NAME_OF[target_type])
    assert after.version != before.version


@pytest.mark.parametrize("target_type", TYPES)
def test_an_applied_edit_can_be_undone_until_the_person_edits_it(env, target_type) -> None:
    original = env.doc(target_type)
    proposal_id = env.propose(target_type, [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)

    restored = env.service.undo(project_id="novel", target_id=original.id, target_type=target_type)

    assert restored["target_type"] == target_type
    assert env.doc(target_type).content == original.content
    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", target_id=original.id, target_type=target_type)
    assert error.value.code == "nothing_to_undo"


def test_undo_is_refused_once_the_record_was_edited_by_hand(env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)
    current = env.doc("character")
    env.repository.save_character("novel", current.id, "我改的。", expected_version=current.version)

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", target_id=current.id, target_type="character")

    assert error.value.code == "chapter_changed"
    assert env.doc("character").content == "我改的。"


def test_undo_looks_only_at_the_named_kind_of_record(env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", target_id=env.character.id, target_type="note")

    assert error.value.code == "nothing_to_undo"


def test_a_stale_version_is_refused_for_every_kind(env) -> None:
    with pytest.raises(ProposalError) as error:
        env.propose("note", [REPLACE], base_version="stale")

    assert error.value.code == "version_changed"
    assert error.value.details["current_version"] == env.note.version


def test_an_edit_that_no_longer_matches_is_a_conflict_at_apply_time(env) -> None:
    proposal_id = env.propose("world_entry", [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    current = env.doc("world_entry")
    env.repository.save_world_entry("novel", current.id, "已经改写。", expected_version=current.version)

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "conflict" and error.value.details["reason"] == "edit_not_found"


def test_edits_with_curly_quotes_in_the_record_match_straight_quotes(env) -> None:
    current = env.doc("note")
    env.repository.save_note(
        "novel", current.id, "他说：“走吧”。", expected_version=current.version
    )
    note = env.doc("note")

    proposal_id = env.service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="note", target_id=note.id,
        base_version=note.version,
        raw_edits=[{"op": "replace", "old_text": '"走吧"', "new_text": "“再等等”"}],
    )["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)

    assert env.doc("note").content == "他说：“再等等”。"


# ----------------------------------------------------------------- addressing
def test_a_record_can_be_named_by_its_title_instead_of_its_id(env) -> None:
    summary = env.propose("character", [REPLACE], target_id="林远")

    assert summary["target_id"] == env.character.id
    assert env.propose("world_entry", [REPLACE], target_id="钟楼")["target_id"] == env.entry.id


def test_names_match_without_regard_to_case(env) -> None:
    repo = env.repository
    entry = repo.create_world_entry("novel", "Clock Tower", "少年常去。")

    summary = env.service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="world_entry",
        target_id="clock tower", base_version=entry.version, raw_edits=[REPLACE],
    )

    assert summary["target_id"] == entry.id


def test_a_name_shared_by_two_records_lists_the_candidates(env) -> None:
    (env.vault / "novel" / "characters" / "character-099.md").write_text(
        "---\ntype: character\nid: novel:character-99\nproject_id: novel\nname: 林远\n---\n\n另一个林远。\n",
        encoding="utf-8",
    )
    env.repository._invalidate_records()

    with pytest.raises(ProposalError) as error:
        env.propose("character", [REPLACE], target_id="林远")

    assert error.value.code == "ambiguous_target"
    assert {row["id"] for row in error.value.details["candidates"]} == {env.character.id, "novel:character-99"}
    # An id is never ambiguous.
    other = env.repository.get_character("novel", "novel:character-99")
    summary = env.propose(
        "character", [{"op": "replace", "old_text": "另一个", "new_text": "又一个"}],
        target_id=other.id, base_version=other.version,
    )
    assert summary["target_id"] == other.id


def test_an_unknown_name_is_not_found(env) -> None:
    with pytest.raises(NotFoundError):
        env.propose("character", [REPLACE], target_id="没有这个人")


def test_an_unknown_kind_of_target_is_refused(env) -> None:
    with pytest.raises(ProposalError) as error:
        env.service.propose_edit(
            project_id="novel", session_id="s1", **SCOPE, target_type="volume",
            target_id="novel:volume-1", base_version="x", raw_edits=[REPLACE],
        )

    assert error.value.code == "invalid_target_type"


# ------------------------------------------------------------------ read-only
def _reference_note(env: Env):
    path = env.vault / "novel" / "notes" / "note-050.md"
    path.write_text(
        "---\ntype: note\nid: novel:note-50\nproject_id: novel\ntitle: 资料\nreference: true\n---\n\n少年的资料。\n",
        encoding="utf-8",
    )
    env.repository._invalidate_records()
    return env.repository.get_note("novel", "novel:note-50")


def test_a_reference_note_cannot_be_proposed_for_change(env) -> None:
    reference = _reference_note(env)

    with pytest.raises(ProposalError) as error:
        env.service.propose_edit(
            project_id="novel", session_id="s1", **SCOPE, target_type="note", target_id=reference.id,
            base_version=reference.version, raw_edits=[REPLACE],
        )

    assert error.value.code == "read_only"
    assert env.repository.get_note("novel", reference.id).content == "少年的资料。"


def test_a_note_that_became_a_reference_after_approval_is_not_written(env) -> None:
    proposal_id = env.propose("note", [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    path = env.vault / "novel" / "notes" / "note-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace("title: 灵感", "title: 灵感\nreference: true"), encoding="utf-8")
    env.repository._invalidate_records()

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "read_only"
    assert "少年" in env.repository.get_note("novel", env.note.id).content


# ------------------------------------------------------------------- creating
@pytest.mark.parametrize("target_type", TYPES)
def test_a_new_record_is_created_only_after_approval(env, target_type) -> None:
    count = lambda: len(_rows(env, target_type))  # noqa: E731
    before = count()

    summary = env.propose_new(target_type, "新条目", "只有正文。")
    assert summary["kind"] == "new_record" and summary["target_type"] == target_type
    assert count() == before

    env.approve(summary["proposal_id"])
    result = env.apply(summary["proposal_id"])

    assert count() == before + 1
    assert result["status"] == "applied" and result["title"] == "新条目" and result["target_type"] == target_type
    created = next(row for row in _rows(env, target_type) if row.id == result["target_id"])
    assert created.content == "只有正文。"


def _rows(env: Env, target_type: str):
    tree = env.repository.get_project("novel")
    return {"character": tree.characters, "world_entry": tree.world_info_entries, "note": tree.notes}[target_type]


@pytest.mark.parametrize("target_type", TYPES)
def test_a_name_already_in_use_is_flagged_and_numbered_when_written(env, target_type) -> None:
    existing = getattr(env.doc(target_type), NAME_OF[target_type])

    summary = env.propose_new(target_type, existing, "另一份。")

    assert [warning["kind"] for warning in summary["warnings"]] == ["name_in_use"]
    env.approve(summary["proposal_id"])
    result = env.apply(summary["proposal_id"])
    assert result["title"] == f"{existing} (2)"
    assert getattr(env.doc(target_type), NAME_OF[target_type]) == existing


def test_a_new_chapter_still_needs_a_volume_and_may_share_a_title(env) -> None:
    with pytest.raises(ProposalError) as missing:
        env.propose_new("chapter", "第二章", "正文。")
    assert missing.value.code == "invalid_request"
    with pytest.raises(NotFoundError):
        env.propose_new("chapter", "第二章", "正文。", volume_id="novel:volume-9")

    first = env.propose_new("chapter", "第一章", "正文。", volume_id="novel:volume-1")
    assert first["warnings"] == []


def test_a_new_note_can_name_an_existing_category_only(env) -> None:
    (env.vault / "novel" / "notes" / "category-001.md").write_text(
        "---\ntype: note_category\nid: novel:category-1\nproject_id: novel\nname: 设定\n---\n", encoding="utf-8"
    )
    env.repository._invalidate_records()

    summary = env.propose_new("note", "分类笔记", "正文。", category_id="novel:category-1")
    env.approve(summary["proposal_id"])
    result = env.apply(summary["proposal_id"])
    assert env.repository.get_note("novel", result["target_id"]).category_id == "novel:category-1"

    with pytest.raises(NotFoundError):
        env.propose_new("note", "x", "正文。", category_id="novel:category-9")


def test_new_record_text_is_checked_like_chapter_text(env) -> None:
    summary = env.propose_new("character", "苏晴", "好的，这是角色设定：\n冷静的医生。")

    assert "leading_guidance" in [warning["kind"] for warning in summary["warnings"]]
    with pytest.raises(ProposalError):
        env.propose_new("character", "苏晴", "   ")


def test_approving_hand_edited_text_creates_that_text(env) -> None:
    summary = env.propose_new("world_entry", "河流", "宽而浅。")
    env.approve(summary["proposal_id"], text="窄而深。")
    result = env.apply(summary["proposal_id"])

    assert env.repository.get_world_entry("novel", result["target_id"]).content == "窄而深。"


def test_a_newer_proposal_for_the_same_new_name_replaces_the_older_one(env) -> None:
    first = env.propose_new("character", "苏晴", "版本一。")
    second = env.propose_new("character", "苏晴", "版本二。")
    other_kind = env.propose_new("note", "苏晴", "笔记。")

    assert env.store.get(first["proposal_id"])["status"] == "superseded"
    assert env.store.get(second["proposal_id"])["status"] == "pending"
    assert env.store.get(other_kind["proposal_id"])["status"] == "pending"


def test_a_created_record_cannot_be_undone_here(env) -> None:
    summary = env.propose_new("character", "苏晴", "医生。")
    env.approve(summary["proposal_id"])
    result = env.apply(summary["proposal_id"])

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", target_id=result["target_id"], target_type="character")

    assert error.value.code == "undo_unsupported"


# ------------------------------------------------------------ the Desktop's view
def test_the_desktop_view_and_write_log_name_the_target(env) -> None:
    edit = env.propose("character", [REPLACE])["proposal_id"]
    new = env.propose_new("note", "新笔记", "正文。")["proposal_id"]
    views = {row["id"]: row for row in env.service.list_open(project_id="novel", **SCOPE)}

    assert views[edit]["target_type"] == "character" and views[edit]["target_title"] == "林远"
    assert views[edit]["current_version"] == env.character.version
    assert views[new]["target_type"] == "note" and views[new]["target_title"] == "新笔记"
    assert views[new]["current_version"] is None

    env.approve(edit)
    env.apply(edit)
    log = env.service.writes(project_id="novel")
    assert log[0]["target_type"] == "character" and log[0]["target_id"] == env.character.id
    assert log[0]["target_title"] == "林远" and log[0]["undone"] is False


def test_proposals_saved_before_other_targets_existed_still_read_as_chapters(env) -> None:
    old = env.store.create({
        "project_id": "novel", "profile": "writer", "connection_id": "local", "session_id": "s1",
        "kind": "edit", "chapter_id": "novel:chapter-1", "chapter_title": "第一章",
        "base_version": "v", "edits": [], "result_text": "", "previews": [], "warnings": [],
    })

    view = env.service.list_open(project_id="novel", **SCOPE)[0]

    assert view["id"] == old["id"] and view["target_type"] == "chapter"
    assert view["target_id"] == "novel:chapter-1" and view["target_title"] == "第一章"


# -------------------------------------------------------------- through the tools
def _tools(env: Env, *, bound: bool = True) -> StoryToolService:
    permissions = StoryPermissionGate({"novel": ("writer", "local")}, locked_profile="writer")
    if bound:
        permissions.bind_session(SessionScope("s1", "desktop", "writer", "local", "novel"), "novel")
    return StoryToolService(env.repository, permissions, proposals_provider=lambda: env.service)


def _tool(service: StoryToolService, name: str, args: dict) -> dict:
    scope = {"session_id": "s1", "source": "desktop", "profile": "writer", "connection_id": "local"}
    return json.loads(service.handle(name, args, **scope))


def test_list_records_gives_summaries_without_text(env) -> None:
    response = _tool(_tools(env), "story.list_records", {"target_type": "note"})

    assert response["ok"] is True
    row = response["data"][0]
    assert row["id"] == env.note.id and row["title"] == "灵感" and row["version"] == env.note.version
    assert row["reference"] is False and "content" not in row and row["content_length"] == len(env.note.content)


def test_get_record_reads_by_id_or_name_and_returns_the_version(env) -> None:
    tools = _tools(env)

    by_id = _tool(tools, "story.get_record", {"target_type": "character", "target_id": env.character.id})
    by_name = _tool(tools, "story.get_record", {"target_type": "character", "target_id": "林远"})

    assert by_id["data"] == by_name["data"]
    assert by_id["data"]["content"] == "少年，住在阁楼。" and by_id["data"]["version"] == env.character.version


def test_the_record_tools_use_the_sessions_project_only(env) -> None:
    env.repository.create_project("Other", slug="other")
    tools = _tools(env)

    response = _tool(tools, "story.list_records", {"target_type": "character", "project_id": "other"})
    assert response["project_id"] == "novel"
    assert _tool(_tools(env, bound=False), "story.list_records", {"target_type": "note"})["error"]["code"] == "session_not_bound"
    assert _tool(tools, "story.get_record", {"target_type": "character", "target_id": "nobody"})["error"]["code"] == "not_found"
    assert _tool(tools, "story.list_records", {"target_type": "volume"})["ok"] is False


def test_the_tools_propose_and_apply_a_character_change(env) -> None:
    tools = _tools(env)
    proposed = _tool(tools, "story.propose_edit", {
        "target_type": "character", "target_id": "林远",
        "base_version": env.character.version, "edits": [REPLACE],
    })
    assert proposed["ok"] is True and proposed["data"]["target_type"] == "character"
    proposal_id = proposed["data"]["proposal_id"]

    blocked = _tool(tools, "story.apply_edit", {"proposal_id": proposal_id})
    assert blocked["error"]["code"] == "not_approved"

    env.approve(proposal_id)
    applied = _tool(tools, "story.apply_edit", {"proposal_id": proposal_id})

    assert applied["ok"] is True and "青年" in env.doc("character").content


def test_the_tools_propose_a_new_record_and_report_its_final_name(env) -> None:
    tools = _tools(env)
    proposed = _tool(tools, "story.propose_new", {
        "target_type": "character", "title": "林远", "content": "另一个林远。",
    })
    assert proposed["ok"] is True and proposed["data"]["warnings"][0]["kind"] == "name_in_use"

    env.approve(proposed["data"]["proposal_id"])
    applied = _tool(tools, "story.apply_edit", {"proposal_id": proposed["data"]["proposal_id"]})

    assert applied["data"]["title"] == "林远 (2)" and applied["data"]["target_type"] == "character"


def test_the_older_chapter_argument_names_still_work(env) -> None:
    tools = _tools(env)
    chapter = env.repository.get_chapter("novel", "novel:chapter-1")
    env.repository.save_chapter("novel", chapter.id, "少年出门。", expected_version=chapter.version)
    chapter = env.repository.get_chapter("novel", "novel:chapter-1")

    legacy = _tool(tools, "story.propose_edit", {
        "chapter_id": chapter.id, "base_version": chapter.version, "edits": [REPLACE],
    })
    new_chapter = _tool(tools, "story.propose_new", {
        "volume_id": "novel:volume-1", "title": "第二章", "content": "正文。",
    })

    assert legacy["ok"] is True and legacy["data"]["target_type"] == "chapter"
    assert new_chapter["ok"] is True and new_chapter["data"]["kind"] == "new_chapter"
    assert _tool(tools, "story.propose_edit", {"base_version": "x", "edits": [REPLACE]})["error"]["code"] == "invalid_request"


# ------------------------------------------------------------------ hardening
def test_a_world_entry_needs_the_projects_world_info_and_the_proposal_says_so(env) -> None:
    env.repository.create_project("Bare", slug="bare")
    project_file = env.vault / "bare" / "project.md"
    lines = project_file.read_text(encoding="utf-8").splitlines(keepends=True)
    project_file.write_text("".join(line for line in lines if not line.startswith("world_info_id")), encoding="utf-8")
    env.repository._invalidate_records()

    with pytest.raises(ProposalError) as error:
        env.service.propose_new(
            project_id="bare", session_id="s1", **SCOPE,
            target_type="world_entry", title="河流", content="宽而浅。",
        )

    assert error.value.code == "no_world_info"
    assert env.store.list_for_project(project_id="bare", **SCOPE) == []


def test_the_write_log_shows_the_title_a_new_record_really_got(env) -> None:
    summary = env.propose_new("character", "林远", "另一个林远。")
    env.approve(summary["proposal_id"])
    env.apply(summary["proposal_id"])

    entry = env.service.writes(project_id="novel")[0]

    assert entry["target_title"] == "林远 (2)" and entry["target_type"] == "character"


def test_snapshots_of_a_character_are_not_filed_under_a_bare_id(env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)
    snapshot_id = env.store.get(proposal_id)["applied"]["snapshot_id"]

    kept = env.history.load(project_id="novel", target_id=f"character.{env.character.id}", snapshot_id=snapshot_id)
    bare = env.history.load(project_id="novel", target_id=env.character.id, snapshot_id=snapshot_id)

    assert kept is not None and kept["text"] == "少年，住在阁楼。"
    assert bare is None


def test_two_kinds_of_record_with_the_same_id_keep_separate_snapshots(env) -> None:
    (env.vault / "novel" / "characters" / "character-077.md").write_text(
        "---\ntype: character\nid: novel:shared-1\nproject_id: novel\nname: 同号角色\n---\n\n少年甲。\n", encoding="utf-8"
    )
    (env.vault / "novel" / "notes" / "note-077.md").write_text(
        "---\ntype: note\nid: novel:shared-1\nproject_id: novel\ntitle: 同号笔记\n---\n\n少年乙。\n", encoding="utf-8"
    )
    env.repository._invalidate_records()
    for target_type, record in (
        ("character", env.repository.get_character("novel", "novel:shared-1")),
        ("note", env.repository.get_note("novel", "novel:shared-1")),
    ):
        proposal_id = env.service.propose_edit(
            project_id="novel", session_id="s1", **SCOPE, target_type=target_type,
            target_id=record.id, base_version=record.version, raw_edits=[REPLACE],
        )["proposal_id"]
        env.approve(proposal_id)
        env.apply(proposal_id)

    character = env.service.undo(project_id="novel", target_id="novel:shared-1", target_type="character")
    assert env.repository.get_character("novel", "novel:shared-1").content == "少年甲。"
    assert "青年" in env.repository.get_note("novel", "novel:shared-1").content
    note = env.service.undo(project_id="novel", target_id="novel:shared-1", target_type="note")
    assert env.repository.get_note("novel", "novel:shared-1").content == "少年乙。"
    assert character["target_type"] == "character" and note["target_type"] == "note"
