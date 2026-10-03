"""The Agent can propose renaming and deleting records; both follow the approval rules."""

from __future__ import annotations

import json

import pytest

from story_construction_plugin import approval_gate as gate
from story_construction_plugin.proposal_service import ProposalError

from test_record_proposals import Env, SCOPE
from test_session_approval import Chat


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


@pytest.fixture
def chat(env) -> Chat:
    return Chat(env)


def rename(env: Env, target_type: str, target, new_title: str, **extra) -> dict:
    return env.service.propose_rename(
        project_id="novel", session_id="s1", **SCOPE,
        target_type=target_type, target_id=target, new_title=new_title, **extra,
    )


def delete(env: Env, target_type: str, target) -> dict:
    return env.service.propose_delete(
        project_id="novel", session_id="s1", **SCOPE, target_type=target_type, target_id=target,
    )


def writes(env: Env) -> list[dict]:
    return env.service.writes(project_id="novel")


# ----------------------------------------------------------------- proposing
def test_a_rename_proposal_names_the_record_and_the_new_name(env) -> None:
    summary = rename(env, "character", env.character.id, "江昼")

    assert summary["status"] == "pending" and summary["kind"] == "rename"
    assert summary["target_type"] == "character" and summary["target_id"] == env.character.id
    stored = env.store.get(summary["proposal_id"])
    assert stored["new_title"] == "江昼" and stored["target_title"] == "林远"
    assert stored["base_version"] == env.character.version and stored["edits"] == []
    assert env.doc("character").name == "林远"


def test_a_record_can_be_named_by_its_current_name(env) -> None:
    summary = rename(env, "world_entry", "钟楼", "旧钟楼")

    assert summary["target_id"] == env.entry.id


def test_renaming_to_the_same_name_or_a_reference_note_is_refused(env) -> None:
    with pytest.raises(ProposalError) as same:
        rename(env, "character", env.character.id, " 林远 ")
    assert same.value.code == "no_change"

    reference = env.repository.create_note("novel", "参考")
    path = env.vault / reference.source_ref
    path.write_text(path.read_text(encoding="utf-8").replace("type: note", "type: note\nreference: true"), encoding="utf-8")
    with pytest.raises(ProposalError) as refused:
        rename(env, "note", reference.id, "别的名字")
    assert refused.value.code == "read_only"


def test_a_name_another_record_has_is_flagged_and_numbered_when_written(env) -> None:
    other = env.repository.create_character("novel", "江昼")
    summary = rename(env, "character", other.id, "林远")

    assert [warning["kind"] for warning in summary["warnings"]] == ["name_in_use"]
    proposal_id = summary["proposal_id"]
    env.approve(proposal_id)
    assert env.apply(proposal_id)["title"] == "林远 (2)"


def test_a_blank_new_name_is_refused(env) -> None:
    with pytest.raises(ProposalError) as error:
        rename(env, "character", env.character.id, "   ")
    assert error.value.code == "invalid_title"


def test_a_newer_proposal_for_the_same_record_replaces_the_older_one(env) -> None:
    first = rename(env, "character", env.character.id, "甲")["proposal_id"]
    second = rename(env, "character", env.character.id, "乙")["proposal_id"]

    assert env.store.get(first)["status"] == "superseded" and env.store.get(second)["status"] == "pending"


def test_delete_covers_characters_entries_and_notes_but_never_chapters_or_references(env) -> None:
    for target_type, record in (("character", env.character), ("world_entry", env.entry), ("note", env.note)):
        assert delete(env, target_type, record.id)["kind"] == "delete"
    with pytest.raises(ProposalError) as chapter:
        delete(env, "chapter", "novel:chapter-1")
    assert chapter.value.code == "unsupported"


# ------------------------------------------------------------------ renaming
def test_an_approved_rename_changes_only_the_name_and_can_be_undone(env) -> None:
    proposal_id = rename(env, "character", env.character.id, "江昼")["proposal_id"]
    approval = env.approve(proposal_id)
    assert approval["status"] == "approved" and approval["new_title"] == "江昼"

    result = env.apply(proposal_id)

    assert result["status"] == "applied" and result["title"] == "江昼"
    renamed = env.doc("character")
    assert renamed.name == "江昼" and renamed.content == "少年，住在阁楼。" and renamed.id == env.character.id
    assert writes(env)[0]["kind"] == "rename" and writes(env)[0]["target_title"] == "江昼"

    env.service.undo(project_id="novel", target_id=env.character.id, target_type="character")

    assert env.doc("character").name == "林远"
    assert writes(env)[0]["undone"] is True


def test_a_rename_cannot_be_undone_after_the_person_edited_the_record(env) -> None:
    proposal_id = rename(env, "character", env.character.id, "江昼")["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)
    current = env.doc("character")
    env.repository.save_character("novel", current.id, "我改的。", expected_version=current.version)

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", target_id=current.id, target_type="character")

    assert error.value.code == "chapter_changed" and env.doc("character").name == "江昼"


def test_approving_or_applying_after_the_record_changed_writes_nothing(env) -> None:
    stale = rename(env, "character", env.character.id, "江昼")["proposal_id"]
    current = env.doc("character")
    env.repository.save_character("novel", current.id, "新的描述。", expected_version=current.version)
    with pytest.raises(ProposalError) as at_approval:
        env.approve(stale)
    assert at_approval.value.code == "version_changed"

    fresh = rename(env, "character", env.character.id, "沈疏白")["proposal_id"]
    env.approve(fresh)
    current = env.doc("character")
    env.repository.save_character("novel", current.id, "又改了。", expected_version=current.version)
    with pytest.raises(ProposalError) as at_apply:
        env.apply(fresh)
    assert at_apply.value.code == "version_changed" and env.doc("character").name == "林远"


def test_an_action_proposal_has_nothing_to_select_or_edit(env) -> None:
    proposal_id = rename(env, "character", env.character.id, "江昼")["proposal_id"]

    for extra in ({"selected": [0]}, {"text": "x", "base_version": env.character.version}):
        with pytest.raises(ProposalError) as error:
            env.approve(proposal_id, **extra)
        assert error.value.code == "invalid_request"


def test_an_approval_is_bound_to_the_name_that_was_approved(env) -> None:
    proposal_id = rename(env, "character", env.character.id, "江昼")["proposal_id"]
    env.approve(proposal_id)
    env.store.mutate(proposal_id, lambda row: row.update(new_title="别的名字"))

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "approval_mismatch" and env.doc("character").name == "林远"


def test_a_chapter_can_be_renamed_too(env) -> None:
    chapter = env.repository.get_chapter("novel", "novel:chapter-1")
    proposal_id = rename(env, "chapter", chapter.id, "新的第一章")["proposal_id"]
    env.approve(proposal_id)

    assert env.apply(proposal_id)["title"] == "新的第一章"
    assert env.repository.get_chapter("novel", chapter.id).title == "新的第一章"


# ------------------------------------------------------------------ deleting
def test_an_approved_delete_moves_the_record_to_the_trash_and_can_be_undone(env) -> None:
    proposal_id = delete(env, "character", env.character.id)["proposal_id"]
    env.approve(proposal_id)

    result = env.apply(proposal_id)

    assert result["status"] == "applied" and result["deleted"] is True and result["title"] == "林远"
    assert env.repository.get_project("novel").characters == ()
    info = env.store.get(proposal_id)["applied"]
    assert (env.vault / info["trash_ref"]).is_file()
    assert writes(env)[0]["kind"] == "delete" and writes(env)[0]["target_title"] == "林远"

    env.service.undo(project_id="novel", target_id=env.character.id, target_type="character")

    assert env.doc("character").name == "林远" and env.doc("character").content == "少年，住在阁楼。"
    assert not (env.vault / info["trash_ref"]).exists()


def test_undoing_a_delete_refuses_when_something_took_its_place(env) -> None:
    proposal_id = delete(env, "note", env.note.id)["proposal_id"]
    env.approve(proposal_id)
    env.apply(proposal_id)
    (env.vault / env.note.source_ref).write_text("someone wrote here", encoding="utf-8")

    with pytest.raises(ProposalError) as error:
        env.service.undo(project_id="novel", target_id=env.note.id, target_type="note")

    assert error.value.code == "restore_failed"
    assert (env.vault / env.note.source_ref).read_text(encoding="utf-8") == "someone wrote here"


def test_a_delete_of_a_record_edited_since_the_proposal_is_refused(env) -> None:
    proposal_id = delete(env, "world_entry", env.entry.id)["proposal_id"]
    env.approve(proposal_id)
    entry = env.doc("world_entry")
    env.repository.save_world_entry("novel", entry.id, "刚写的内容。", expected_version=entry.version)

    with pytest.raises(ProposalError) as error:
        env.apply(proposal_id)

    assert error.value.code == "version_changed" and env.doc("world_entry").content == "刚写的内容。"


# ------------------------------------------------------------- risk and prompt
def test_deleting_is_always_high_risk_and_renaming_is_not(env) -> None:
    removal = env.store.get(delete(env, "character", env.character.id)["proposal_id"])
    naming = env.store.get(rename(env, "world_entry", env.entry.id, "旧钟楼")["proposal_id"])

    risk = env.service.assess(project_id="novel", proposal=removal)

    assert risk.high and risk.reasons == ("deletes_record",) and risk.total == len("少年，住在阁楼。")
    assert not env.service.assess(project_id="novel", proposal=naming).high


def test_the_prompt_says_what_is_being_renamed_or_deleted(env) -> None:
    naming = env.store.get(rename(env, "character", env.character.id, "江昼")["proposal_id"])
    removal = env.store.get(delete(env, "character", env.character.id)["proposal_id"])

    rename_text = gate.approval_message(naming, gate.NORMAL)
    risk = env.service.assess(project_id="novel", proposal=removal)
    delete_text = gate.approval_message(removal, risk)

    assert rename_text.splitlines()[0] == "重命名角色「林远」→「江昼」"
    assert delete_text.splitlines()[0] == "删除角色「林远」"
    assert "高风险" in delete_text and "回收站" in delete_text and "总是允许" in delete_text


# ------------------------------------------------------- in the chat, end to end
def _tool(chat: Chat, name: str, args: dict) -> dict:
    kwargs = {"session_id": "s1", "source": "desktop", "profile": "writer", "connection_id": "local"}
    return json.loads(chat.tools.handle(name, args, **kwargs))


def test_renaming_through_the_tools_and_the_chat_approval(chat, env) -> None:
    proposed = _tool(chat, "story.propose_rename", {
        "target_type": "character", "target_id": "林远", "new_title": "江昼",
    })
    assert proposed["ok"] is True and proposed["data"]["kind"] == "rename"
    proposal_id = proposed["data"]["proposal_id"]

    directive = chat.ask(proposal_id)
    assert directive["action"] == "approve" and directive["rule_key"] == "story.apply"
    applied = chat.apply(proposal_id)

    assert applied["ok"] is True and applied["data"]["title"] == "江昼"
    assert env.doc("character").name == "江昼"


def test_deleting_through_the_tools_always_gets_a_rule_of_its_own(chat, env) -> None:
    first = _tool(chat, "story.propose_delete", {"target_type": "character", "target_id": env.character.id})
    proposal_id = first["data"]["proposal_id"]

    directive = chat.ask(proposal_id)

    assert directive["rule_key"] == f"story.apply:{proposal_id}"
    assert "高风险" in directive["message"]
    assert chat.apply(proposal_id)["data"]["deleted"] is True
    assert env.repository.get_project("novel").characters == ()


def test_deleting_without_the_chat_approval_is_refused(chat, env) -> None:
    proposal_id = _tool(chat, "story.propose_delete", {
        "target_type": "character", "target_id": env.character.id,
    })["data"]["proposal_id"]

    result = chat.apply(proposal_id)

    assert result["ok"] is False and result["error"]["code"] == "not_approved"
    assert env.doc("character").name == "林远"


def test_the_tools_report_bad_arguments_instead_of_failing(chat) -> None:
    missing_name = _tool(chat, "story.propose_rename", {"target_id": "林远"})
    no_target = _tool(chat, "story.propose_delete", {"target_type": "character"})
    chapter = _tool(chat, "story.propose_delete", {"target_type": "chapter", "target_id": "novel:chapter-1"})

    assert missing_name["ok"] is False and no_target["ok"] is False
    assert chapter["ok"] is False and chapter["error"]["code"] == "unsupported"
