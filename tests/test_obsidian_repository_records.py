"""Characters, world entries and notes can be created and have their text saved."""

from __future__ import annotations

from pathlib import Path

import pytest

from story_construction_plugin.obsidian_repository import ObsidianProjectRepository
from story_construction_plugin.repository import (
    DomainValidationError,
    NotFoundError,
    RepositoryError,
    VersionConflictError,
)


@pytest.fixture
def repository(tmp_path: Path) -> ObsidianProjectRepository:
    repository = ObsidianProjectRepository(tmp_path)
    repository.create_project("Novel", slug="novel")
    return repository


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _add_category(tmp_path: Path, repository: ObsidianProjectRepository) -> str:
    (tmp_path / "novel" / "notes" / "category-001.md").write_text(
        "---\ntype: note_category\nid: novel:category-1\nproject_id: novel\nname: 设定\n---\n",
        encoding="utf-8",
    )
    repository._invalidate_records()
    return "novel:category-1"


# ---------------------------------------------------------------- characters
def test_a_new_character_is_a_numbered_record_with_its_text(repository, tmp_path) -> None:
    character = repository.create_character("novel", "林远", "少年，住在阁楼。")

    assert character.id == "novel:character-1"
    assert character.name == "林远" and character.content == "少年，住在阁楼。"
    assert character.source_ref == "novel/characters/character-001.md"
    assert repository.get_character("novel", character.id) == character
    written = _read(tmp_path / "novel" / "characters" / "character-001.md")
    assert "type: character" in written and "project_id: novel" in written


def test_a_character_name_already_in_use_gets_a_number(repository) -> None:
    first = repository.create_character("novel", "林远")
    second = repository.create_character("novel", "林远")
    third = repository.create_character("novel", "林远")

    assert (first.name, second.name, third.name) == ("林远", "林远 (2)", "林远 (3)")
    assert second.id == "novel:character-2"


@pytest.mark.parametrize("name", ["", "   ", "a\x00b", "x" * 121])
def test_invalid_character_names_are_refused(repository, name) -> None:
    with pytest.raises(DomainValidationError):
        repository.create_character("novel", name)


def test_saving_a_character_keeps_its_frontmatter_and_checks_the_version(repository, tmp_path) -> None:
    character = repository.create_character("novel", "林远", "旧的。")

    saved = repository.save_character("novel", character.id, "新的。", expected_version=character.version)

    assert saved.content == "新的。" and saved.version != character.version
    assert saved.name == "林远"
    assert "id: novel:character-1" in _read(tmp_path / "novel" / "characters" / "character-001.md")
    with pytest.raises(VersionConflictError):
        repository.save_character("novel", character.id, "再改。", expected_version=character.version)
    assert repository.get_character("novel", character.id).content == "新的。"


# ------------------------------------------------------------- world entries
def test_a_new_world_entry_belongs_to_the_projects_world_info(repository, tmp_path) -> None:
    entry = repository.create_world_entry("novel", "钟楼", "镇上最高的建筑。")

    assert entry.id == "novel:world-entry-1"
    assert entry.title == "钟楼" and entry.content == "镇上最高的建筑。"
    assert entry.project_id == "novel"
    assert entry.source_ref == "novel/world/entry-001.md"
    assert repository.get_world_entry("novel", entry.id) == entry
    assert [row.id for row in repository.search_world_info("novel", "钟楼")] == [entry.id]
    assert "type: world_info_entry" in _read(tmp_path / "novel" / "world" / "entry-001.md")


def test_a_world_entry_title_already_in_use_gets_a_number(repository) -> None:
    repository.create_world_entry("novel", "钟楼")

    assert repository.create_world_entry("novel", "钟楼").title == "钟楼 (2)"


def test_saving_a_world_entry_checks_the_version(repository) -> None:
    entry = repository.create_world_entry("novel", "钟楼", "旧的。")

    saved = repository.save_world_entry("novel", entry.id, "新的。", expected_version=entry.version)

    assert saved.content == "新的。" and saved.title == "钟楼"
    with pytest.raises(VersionConflictError):
        repository.save_world_entry("novel", entry.id, "x", expected_version=entry.version)


# --------------------------------------------------------------------- notes
def test_a_new_note_has_no_category_unless_one_is_given(repository, tmp_path) -> None:
    note = repository.create_note("novel", "灵感", "钟声突然停了。")

    assert note.id == "novel:note-1" and note.category_id is None and note.reference is False
    assert note.source_ref == "novel/notes/note-001.md"
    assert "category_id" not in _read(tmp_path / "novel" / "notes" / "note-001.md")
    assert repository.get_note("novel", note.id) == note


def test_a_note_can_be_filed_in_an_existing_category_only(repository, tmp_path) -> None:
    category = _add_category(tmp_path, repository)

    note = repository.create_note("novel", "灵感", "x", category_id=category)

    assert note.category_id == category
    with pytest.raises(NotFoundError):
        repository.create_note("novel", "灵感", "x", category_id="novel:category-9")


def test_note_titles_are_unique_per_category_not_across_them(repository, tmp_path) -> None:
    category = _add_category(tmp_path, repository)
    repository.create_note("novel", "灵感")

    same_place = repository.create_note("novel", "灵感")
    other_place = repository.create_note("novel", "灵感", category_id=category)

    assert same_place.title == "灵感 (2)"
    assert other_place.title == "灵感"


def test_saving_a_note_keeps_its_category_and_checks_the_version(repository, tmp_path) -> None:
    category = _add_category(tmp_path, repository)
    note = repository.create_note("novel", "灵感", "旧的。", category_id=category)

    saved = repository.save_note("novel", note.id, "新的。", expected_version=note.version)

    assert saved.content == "新的。" and saved.category_id == category
    with pytest.raises(VersionConflictError):
        repository.save_note("novel", note.id, "x", expected_version=note.version)


# -------------------------------------------------------------------- scoping
def test_records_are_never_found_through_another_project(repository) -> None:
    repository.create_project("Other", slug="other")
    note = repository.create_note("novel", "灵感")
    character = repository.create_character("novel", "林远")
    entry = repository.create_world_entry("novel", "钟楼")

    with pytest.raises(NotFoundError):
        repository.get_note("other", note.id)
    with pytest.raises(NotFoundError):
        repository.save_character("other", character.id, "x", expected_version=character.version)
    with pytest.raises(NotFoundError):
        repository.get_world_entry("other", entry.id)


def test_a_chapter_save_still_behaves_as_before(repository) -> None:
    chapter = repository.get_chapter("novel", "novel:chapter-1")

    saved = repository.save_chapter("novel", chapter.id, "正文。", expected_version=chapter.version)

    assert saved.content == "正文。"
    with pytest.raises(VersionConflictError):
        repository.save_chapter("novel", chapter.id, "x", expected_version=chapter.version)


# -------------------------------------------------------------------- renaming
def test_renaming_a_character_changes_only_its_name(repository, tmp_path) -> None:
    character = repository.create_character("novel", "江昼", "少年，住在阁楼。")
    path = tmp_path / "novel" / "characters" / "character-001.md"
    before = _read(path)

    renamed = repository.rename_record(
        "novel", "character", character.id, "沈疏白", expected_version=character.version
    )

    assert renamed.name == "沈疏白" and renamed.id == character.id
    assert renamed.content == "少年，住在阁楼。" and renamed.source_ref == character.source_ref
    assert renamed.version != character.version
    assert _read(path) == before.replace("name: 江昼", "name: 沈疏白")


def test_renaming_keeps_windows_line_endings_and_other_frontmatter(repository, tmp_path) -> None:
    entry = repository.create_world_entry("novel", "钟楼", "最高的建筑。")
    path = tmp_path / "novel" / "world" / "entry-001.md"
    path.write_bytes(_read(path).replace("\n", "\r\n").encode("utf-8"))
    version = repository.get_world_entry("novel", entry.id).version

    repository.rename_record("novel", "world_entry", entry.id, "旧钟楼", expected_version=version)

    raw = path.read_bytes().decode("utf-8")
    assert "title: 旧钟楼\r\n" in raw
    assert "\n" not in raw.replace("\r\n", "")
    assert raw.startswith("---\r\nproject_id: novel") or raw.startswith("---\nproject_id: novel")


def test_a_name_already_in_use_gets_a_number_when_renaming(repository) -> None:
    first = repository.create_character("novel", "林远")
    second = repository.create_character("novel", "江昼")

    renamed = repository.rename_record("novel", "character", second.id, "林远", expected_version=second.version)

    assert renamed.name == "林远 (2)" and repository.get_character("novel", first.id).name == "林远"


def test_renaming_a_note_only_competes_within_its_category(repository, tmp_path) -> None:
    category = _add_category(tmp_path, repository)
    repository.create_note("novel", "灵感")
    filed = repository.create_note("novel", "想法", category_id=category)

    renamed = repository.rename_record("novel", "note", filed.id, "灵感", expected_version=filed.version)

    assert renamed.title == "灵感" and renamed.category_id == category


def test_a_chapter_can_be_renamed_and_titles_may_repeat(repository) -> None:
    chapter = repository.get_chapter("novel", "novel:chapter-1")

    renamed = repository.rename_record(
        "novel", "chapter", chapter.id, chapter.title, expected_version=chapter.version
    )

    assert renamed.title == chapter.title


def test_renaming_refuses_a_stale_version_a_blank_name_and_unknown_kinds(repository) -> None:
    character = repository.create_character("novel", "林远")

    with pytest.raises(VersionConflictError):
        repository.rename_record("novel", "character", character.id, "x", expected_version="stale")
    with pytest.raises(DomainValidationError):
        repository.rename_record("novel", "character", character.id, "  ", expected_version=character.version)
    with pytest.raises(DomainValidationError):
        repository.rename_record("novel", "volume", character.id, "x", expected_version=character.version)
    with pytest.raises(NotFoundError):
        repository.rename_record("novel", "character", "novel:character-9", "x", expected_version="v")
    assert repository.get_character("novel", character.id).name == "林远"


# -------------------------------------------------------------------- trashing
def test_a_trashed_record_leaves_the_project_but_stays_on_disk(repository, tmp_path) -> None:
    character = repository.create_character("novel", "江昼", "少年。")

    trash_ref, source_ref = repository.trash_record(
        "novel", "character", character.id, expected_version=character.version
    )

    assert source_ref == "novel/characters/character-001.md"
    assert trash_ref.startswith(".story-trash/records/novel/") and trash_ref.endswith("character-001.md")
    assert (tmp_path / trash_ref).is_file() and not (tmp_path / source_ref).exists()
    assert repository.get_project("novel").characters == ()
    with pytest.raises(NotFoundError):
        repository.get_character("novel", character.id)


def test_a_trashed_record_can_be_put_back_exactly(repository, tmp_path) -> None:
    entry = repository.create_world_entry("novel", "钟楼", "最高的建筑。")
    original = (tmp_path / entry.source_ref).read_bytes()
    trash_ref, source_ref = repository.trash_record("novel", "world_entry", entry.id, expected_version=entry.version)

    repository.restore_record("novel", trash_ref, source_ref)

    assert repository.get_world_entry("novel", entry.id) == entry
    assert (tmp_path / source_ref).read_bytes() == original and not (tmp_path / trash_ref).exists()


def test_trashing_refuses_chapters_stale_versions_and_unknown_records(repository) -> None:
    note = repository.create_note("novel", "灵感")

    with pytest.raises(DomainValidationError):
        repository.trash_record("novel", "chapter", "novel:chapter-1", expected_version="v")
    with pytest.raises(VersionConflictError):
        repository.trash_record("novel", "note", note.id, expected_version="stale")
    with pytest.raises(NotFoundError):
        repository.trash_record("novel", "note", "novel:note-9", expected_version="v")
    assert repository.get_note("novel", note.id) == note


def test_restoring_never_overwrites_and_only_touches_trashed_records(repository, tmp_path) -> None:
    character = repository.create_character("novel", "林远", "少年。")
    trash_ref, source_ref = repository.trash_record(
        "novel", "character", character.id, expected_version=character.version
    )
    (tmp_path / source_ref).write_text("someone wrote here", encoding="utf-8")

    with pytest.raises(RepositoryError):
        repository.restore_record("novel", trash_ref, source_ref)
    (tmp_path / source_ref).unlink()
    with pytest.raises(RepositoryError):
        repository.restore_record("novel", "novel/project.md", source_ref)
    with pytest.raises(RepositoryError):
        repository.restore_record("novel", "../outside.md", source_ref)
    with pytest.raises(RepositoryError):
        repository.restore_record("novel", trash_ref, ".story-trash/records/x.md")
    assert (tmp_path / trash_ref).is_file()


def test_trashing_twice_in_a_second_keeps_both_copies(repository, tmp_path) -> None:
    one = repository.create_character("novel", "甲")
    two = repository.create_character("novel", "乙")
    first = repository.trash_record("novel", "character", one.id, expected_version=one.version)
    second = repository.trash_record("novel", "character", two.id, expected_version=two.version)

    assert first[0] != second[0] and (tmp_path / first[0]).is_file() and (tmp_path / second[0]).is_file()
