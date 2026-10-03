"""Desktop endpoints for chapter proposals, against a real Vault."""

from __future__ import annotations

import importlib

import pytest

from test_dashboard_api import (
    PACKAGE_ROOT,
    _assert_http_error,
    _build_profile_lab,
    select_story_target,
)

pytestmark = pytest.mark.hermes_integration

BODY = "他推开门。\n\n雨下得很大，街上没有人。\n\n她在屋里等着。"
CHAPTER = "novel:chapter-1"
SCOPE = {"profile": "writer", "connection_id": "local"}
RAIN = {"op": "replace", "old_text": "雨下得很大", "new_text": "雨下得很急"}


@pytest.fixture
def api(monkeypatch, tmp_path):
    from dashboard import plugin_api

    lab = _build_profile_lab(monkeypatch, tmp_path, PACKAGE_ROOT)
    select_story_target(PACKAGE_ROOT, lab.default_home, "writer", str(lab.vault))
    backend = plugin_api.load_api_backend(PACKAGE_ROOT)
    runtime_module = importlib.import_module(f"{backend.__name__}.runtime")
    repository_module = importlib.import_module(f"{backend.__name__}.obsidian_repository")
    repository = repository_module.ObsidianProjectRepository(lab.vault)
    repository.create_project("Novel", slug="novel")
    chapter = repository.get_chapter("novel", CHAPTER)
    repository.save_chapter("novel", CHAPTER, BODY, expected_version=chapter.version)
    monkeypatch.setattr(runtime_module, "_default_repository_factory", lambda _: repository)
    _runtime, state = plugin_api._require_runtime()

    class Api:
        module = plugin_api
        repo = repository

        def service(self):
            return runtime_module.proposal_service_for(plugin_api._require_runtime()[1])

        def propose(self, edits=(RAIN,)):
            return self.service().propose_edit(
                project_id="novel", session_id="s1", **SCOPE, chapter_id=CHAPTER,
                base_version=repository.get_chapter("novel", CHAPTER).version, raw_edits=list(edits),
            )["proposal_id"]

        def approve(self, proposal_id, **body):
            return plugin_api.approve_proposal("novel", proposal_id, {**SCOPE, **body})

    return Api()


def test_open_proposals_are_listed_with_their_diff(api) -> None:
    proposal_id = api.propose()

    listed = api.module.list_proposals("novel", **SCOPE)["proposals"]

    assert [row["id"] for row in listed] == [proposal_id]
    row = listed[0]
    assert row["status"] == "pending" and row["chapter_id"] == CHAPTER and row["approval"] is None
    assert row["previews"][0]["regions"][0]["new"].startswith("雨下得很急")
    assert row["edits"] == [RAIN] and row["result_text"].count("很急") == 1


def test_listing_checks_scope_and_project(api) -> None:
    _assert_http_error(lambda: api.module.list_proposals("novel", profile="other", connection_id="local"), 403)
    _assert_http_error(lambda: api.module.list_proposals("missing", **SCOPE), 404)
    _assert_http_error(lambda: api.module.list_proposals("novel", profile="writer"), 422)
    assert api.module.list_proposals("novel", profile="writer", connection_id="remote") == {"proposals": []}


def test_approving_reports_the_deadline_and_unlocks_the_write(api) -> None:
    proposal_id = api.propose()

    approved = api.approve(proposal_id)["proposal"]

    assert approved["status"] == "approved" and approved["approval"]["mode"] == "edits"
    assert approved["approval"]["expires_at"] > approved["approval"]["approved_at"]
    result = api.service().apply(project_id="novel", proposal_id=proposal_id, **SCOPE)
    assert result["status"] == "applied"
    assert "雨下得很急" in api.repo.get_chapter("novel", CHAPTER).content


def test_approving_an_edited_text_needs_the_version_it_was_edited_against(api) -> None:
    proposal_id = api.propose()
    version = api.repo.get_chapter("novel", CHAPTER).version

    approved = api.approve(proposal_id, text="完全不同的正文。", base_version=version)["proposal"]

    assert approved["approval"]["mode"] == "text"
    _assert_http_error(lambda: api.approve(proposal_id, text="x", base_version="stale"), 409, "version_changed")


def test_approval_errors_have_stable_statuses(api) -> None:
    proposal_id = api.propose()

    _assert_http_error(lambda: api.approve(proposal_id, selected=[9]), 422, "invalid_selection")
    _assert_http_error(lambda: api.approve(proposal_id, selected="all"), 422, "invalid_selection")
    _assert_http_error(lambda: api.approve(proposal_id, selected=[True]), 422, "invalid_selection")
    _assert_http_error(lambda: api.approve(proposal_id, text=5), 422, "invalid_request")
    _assert_http_error(lambda: api.approve(proposal_id, profile="other"), 403, "profile_lock_mismatch")
    _assert_http_error(lambda: api.approve("missing"), 404)
    _assert_http_error(
        lambda: api.approve(proposal_id, text="---\nid: x\n---\n正文", base_version="x"), 422, "frontmatter_not_allowed"
    )
    _assert_http_error(lambda: api.module.approve_proposal("novel", proposal_id, {"profile": "writer"}), 422)


def test_a_conflicting_approval_is_a_409_naming_the_edit(api) -> None:
    proposal_id = api.propose()
    chapter = api.repo.get_chapter("novel", CHAPTER)
    api.repo.save_chapter("novel", CHAPTER, BODY.replace("雨下得很大", "雨一直下"), expected_version=chapter.version)

    with pytest.raises(Exception) as error:
        api.approve(proposal_id)

    assert error.value.status_code == 409
    assert error.value.detail["code"] == "conflict" and error.value.detail["reason"] == "edit_not_found"


def test_revoke_and_discard_close_the_way_to_a_write(api) -> None:
    first = api.propose()
    api.approve(first)

    revoked = api.module.revoke_proposal("novel", first, dict(SCOPE))["proposal"]
    assert revoked["status"] == "pending" and revoked["approval"] is None

    discarded = api.module.discard_proposal("novel", first, **SCOPE)["proposal"]
    assert discarded["status"] == "discarded"
    _assert_http_error(lambda: api.approve(first), 409, "proposal_closed")
    assert api.module.list_proposals("novel", **SCOPE) == {"proposals": []}


def test_undo_and_the_write_log(api) -> None:
    proposal_id = api.propose()
    api.approve(proposal_id)
    api.service().apply(project_id="novel", proposal_id=proposal_id, **SCOPE)

    log = api.module.list_agent_writes("novel", **SCOPE)["writes"]
    assert [row["proposal_id"] for row in log] == [proposal_id] and log[0]["undone"] is False

    restored = api.module.undo_agent_write("novel", CHAPTER, dict(SCOPE))["restored"]

    assert api.repo.get_chapter("novel", CHAPTER).content == BODY
    assert restored["chapter_id"] == CHAPTER
    assert api.module.list_agent_writes("novel", **SCOPE)["writes"][0]["undone"] is True
    _assert_http_error(lambda: api.module.undo_agent_write("novel", CHAPTER, dict(SCOPE)), 409, "nothing_to_undo")


def test_undo_refuses_after_the_person_edited(api) -> None:
    proposal_id = api.propose()
    api.approve(proposal_id)
    api.service().apply(project_id="novel", proposal_id=proposal_id, **SCOPE)
    chapter = api.repo.get_chapter("novel", CHAPTER)
    api.repo.save_chapter("novel", CHAPTER, "我改的。", expected_version=chapter.version)

    _assert_http_error(lambda: api.module.undo_agent_write("novel", CHAPTER, dict(SCOPE)), 409, "chapter_changed")
    assert api.repo.get_chapter("novel", CHAPTER).content == "我改的。"


def test_deleting_a_project_closes_its_open_proposals(api) -> None:
    proposal_id = api.propose()
    api.approve(proposal_id)

    result = api.module.delete_project("novel", **SCOPE, confirm_name="Novel")

    assert result["closed_proposals"] == 1
    assert api.service().store.get(proposal_id)["status"] == "discarded"


# ------------------------------------------------- characters, entries and notes
CHARACTER_EDIT = {"op": "replace", "old_text": "少年", "new_text": "青年"}


def test_open_proposals_and_the_write_log_name_the_kind_of_record(api) -> None:
    character = api.repo.create_character("novel", "林远", "少年，住在阁楼。")
    service = api.service()
    edit_id = service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="character",
        target_id=character.id, base_version=character.version, raw_edits=[CHARACTER_EDIT],
    )["proposal_id"]
    new_id = service.propose_new(
        project_id="novel", session_id="s1", **SCOPE, target_type="note", title="灵感", content="钟声停了。",
    )["proposal_id"]

    rows = {row["id"]: row for row in api.module.list_proposals("novel", **SCOPE)["proposals"]}

    assert rows[edit_id]["target_type"] == "character" and rows[edit_id]["target_title"] == "林远"
    assert rows[edit_id]["current_version"] == character.version
    assert rows[new_id]["target_type"] == "note" and rows[new_id]["kind"] == "new_record"

    api.approve(edit_id)
    service.apply(project_id="novel", proposal_id=edit_id, **SCOPE)
    log = api.module.list_agent_writes("novel", **SCOPE)["writes"]
    assert log[0]["target_type"] == "character" and log[0]["target_id"] == character.id


def test_undo_follows_the_kind_of_record_named_in_the_body(api) -> None:
    character = api.repo.create_character("novel", "林远", "少年，住在阁楼。")
    service = api.service()
    proposal_id = service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="character",
        target_id=character.id, base_version=character.version, raw_edits=[CHARACTER_EDIT],
    )["proposal_id"]
    api.approve(proposal_id)
    service.apply(project_id="novel", proposal_id=proposal_id, **SCOPE)

    # Read as a chapter id it matches nothing, so nothing is touched.
    _assert_http_error(lambda: api.module.undo_agent_write("novel", character.id, dict(SCOPE)), 409, "nothing_to_undo")
    assert "青年" in api.repo.get_character("novel", character.id).content

    restored = api.module.undo_agent_write(
        "novel", character.id, {**SCOPE, "target_type": "character"}
    )["restored"]

    assert restored["target_type"] == "character"
    assert api.repo.get_character("novel", character.id).content == "少年，住在阁楼。"


# ------------------------------------------------------------ reading one record
BOUND = {**SCOPE, "session_id": "s1"}


@pytest.fixture
def bound(api):
    api.module.bind_session({**BOUND, "project_id": "novel"})
    return api


def test_a_character_world_entry_or_note_can_be_read_with_its_text(bound) -> None:
    api = bound
    character = api.repo.create_character("novel", "林远", "少年，住在阁楼。")
    entry = api.repo.create_world_entry("novel", "钟楼", "镇上最高的建筑。")
    note = api.repo.create_note("novel", "灵感", "钟声停了。")

    read_character = api.module.get_record("novel", "character", character.id, **BOUND)["record"]
    read_entry = api.module.get_record("novel", "world_entry", entry.id, **BOUND)["record"]
    read_note = api.module.get_record("novel", "note", note.id, **BOUND)["record"]

    assert (read_character["title"], read_character["content"]) == ("林远", "少年，住在阁楼。")
    assert read_character["target_type"] == "character" and read_character["version"] == character.version
    assert (read_entry["title"], read_entry["content"]) == ("钟楼", "镇上最高的建筑。")
    assert (read_note["title"], read_note["content"], read_note["reference"]) == ("灵感", "钟声停了。", False)


def test_reading_a_record_checks_kind_scope_and_existence(bound) -> None:
    api = bound
    character = api.repo.create_character("novel", "林远", "少年。")

    _assert_http_error(lambda: api.module.get_record("novel", "chapter", character.id, **BOUND), 422)
    _assert_http_error(lambda: api.module.get_record("novel", "note", character.id, **BOUND), 404)
    _assert_http_error(lambda: api.module.get_record("novel", "character", "novel:character-9", **BOUND), 404)
    _assert_http_error(
        lambda: api.module.get_record("novel", "character", character.id, session_id="s1", profile="other", connection_id="local"), 403
    )


# ------------------------------------------------------------ renaming and deleting
def test_the_panel_lists_approves_and_undoes_a_rename_and_a_delete(api) -> None:
    character = api.repo.create_character("novel", "江昼", "少年。")
    service = api.service()
    rename_id = service.propose_rename(
        project_id="novel", session_id="s1", **SCOPE, target_type="character",
        target_id=character.id, new_title="沈疏白",
    )["proposal_id"]

    listed = api.module.list_proposals("novel", **SCOPE)["proposals"]
    assert listed[0]["kind"] == "rename" and listed[0]["new_title"] == "沈疏白"
    assert listed[0]["current_version"] == character.version and listed[0]["edits"] == []

    approved = api.approve(rename_id)["proposal"]
    assert approved["status"] == "approved" and approved["approval"]["mode"] == "action"
    service.apply(project_id="novel", proposal_id=rename_id, **SCOPE)
    assert api.repo.get_character("novel", character.id).name == "沈疏白"
    api.module.undo_agent_write("novel", character.id, {**SCOPE, "target_type": "character"})
    assert api.repo.get_character("novel", character.id).name == "江昼"

    delete_id = service.propose_delete(
        project_id="novel", session_id="s1", **SCOPE, target_type="character", target_id=character.id,
    )["proposal_id"]
    api.approve(delete_id)
    service.apply(project_id="novel", proposal_id=delete_id, **SCOPE)
    assert api.repo.get_project("novel").characters == ()
    log = api.module.list_agent_writes("novel", **SCOPE)["writes"]
    assert log[0]["kind"] == "delete" and log[0]["target_title"] == "江昼"
    api.module.undo_agent_write("novel", character.id, {**SCOPE, "target_type": "character"})
    assert api.repo.get_character("novel", character.id).name == "江昼"


def test_a_panel_approval_of_a_rename_refuses_a_selection(api) -> None:
    character = api.repo.create_character("novel", "江昼", "少年。")
    rename_id = api.service().propose_rename(
        project_id="novel", session_id="s1", **SCOPE, target_type="character",
        target_id=character.id, new_title="沈疏白",
    )["proposal_id"]

    _assert_http_error(lambda: api.approve(rename_id, selected=[0]), 422, "invalid_request")
