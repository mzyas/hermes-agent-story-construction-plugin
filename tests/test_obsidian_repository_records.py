"""Characters, world entries and notes can be created and have their text saved."""

from __future__ import annotations

from pathlib import Path

import pytest

from story_construction_plugin.obsidian_repository import ObsidianProjectRepository
from story_construction_plugin.repository import (
    DomainValidationError,
    NotFoundError,
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
    assert entry.world_info_id == "novel:world"
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
