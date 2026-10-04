"""Creating volumes and chapters writes new Markdown records and nothing else."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from story_construction_plugin.obsidian_repository import (
    ObsidianProjectRepository,
    RepositoryError,
)
from story_construction_plugin.repository import DomainValidationError, NotFoundError


@pytest.fixture
def repository(tmp_path: Path) -> ObsidianProjectRepository:
    repository = ObsidianProjectRepository(tmp_path)
    repository.create_project("Novel", slug="novel")
    return repository


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_new_volume_is_appended_after_the_existing_ones(repository, tmp_path) -> None:
    volume = repository.create_volume("novel", "第二卷")

    assert volume.id == "novel:volume-2"
    assert volume.title == "第二卷"
    assert [row.id for row in repository.get_project("novel").volumes] == [
        "novel:volume-1",
        "novel:volume-2",
    ]
    written = _read(tmp_path / "novel" / "volumes" / "volume-002" / "volume-002.md")
    assert written.startswith("---\nproject_id: novel\ntype: volume\n")
    assert "type: volume" in written
    assert "id: novel:volume-2" in written
    assert "project_id: novel" in written


def test_new_chapter_is_empty_and_belongs_to_the_chosen_volume(repository, tmp_path) -> None:
    second = repository.create_volume("novel", "第二卷")

    chapter = repository.create_chapter("novel", second.id, "雨夜")

    assert chapter.id == "novel:chapter-2"
    assert chapter.volume_id == second.id
    assert chapter.title == "雨夜"
    assert chapter.content == ""
    assert chapter.source_ref == "novel/volumes/volume-002/chapter-002.md"
    assert repository.get_chapter("novel", chapter.id) == chapter
    assert [row.id for row in repository.list_chapters("novel", second.id)] == [chapter.id]
    assert "volume_id: novel:volume-2" in _read(tmp_path / "novel" / "volumes" / "volume-002" / "chapter-002.md")


def test_numbering_continues_after_the_highest_id_even_with_gaps(repository, tmp_path) -> None:
    gap = tmp_path / "novel" / "volumes" / "volume-001" / "chapter-007.md"
    gap.write_text(
        "---\ntype: chapter\nid: novel:chapter-7\nproject_id: novel\n"
        "volume_id: novel:volume-1\ntitle: Seven\n---\n\nbody\n",
        encoding="utf-8",
    )

    chapter = repository.create_chapter("novel", "novel:volume-1", "Eight")

    assert chapter.id == "novel:chapter-8"
    assert (tmp_path / "novel" / "volumes" / "volume-001" / "chapter-008.md").is_file()


@pytest.mark.parametrize(
    "title",
    ["", "   ", "x" * 121, "line\nbreak", "tab\there", "nul\x00"],
)
def test_unusable_titles_are_rejected_before_anything_is_written(repository, tmp_path, title) -> None:
    before = sorted(path.name for path in (tmp_path / "novel").rglob("*.md"))

    with pytest.raises(DomainValidationError):
        repository.create_volume("novel", title)
    with pytest.raises(DomainValidationError):
        repository.create_chapter("novel", "novel:volume-1", title)

    assert sorted(path.name for path in (tmp_path / "novel").rglob("*.md")) == before


def test_unknown_project_or_volume_is_not_found_and_writes_nothing(repository, tmp_path) -> None:
    before = sorted(path.name for path in tmp_path.rglob("*.md"))

    with pytest.raises(NotFoundError):
        repository.create_volume("missing", "Anything")
    with pytest.raises(NotFoundError):
        repository.create_chapter("novel", "novel:volume-9", "Anything")

    assert sorted(path.name for path in tmp_path.rglob("*.md")) == before


def test_an_existing_file_at_the_target_path_is_never_overwritten(repository, tmp_path) -> None:
    squatter = tmp_path / "novel" / "volumes" / "volume-002" / "volume-002.md"
    squatter.parent.mkdir()
    squatter.write_text("---\ntype: note\nid: keep\nproject_id: novel\ntitle: Keep\n---\n\nmine\n", encoding="utf-8")
    before = squatter.read_bytes()

    with pytest.raises(RepositoryError):
        repository.create_volume("novel", "Second")

    assert squatter.read_bytes() == before
    assert [path.name for path in squatter.parent.glob(".volume-002.md.*")] == []


def test_a_surrounding_title_is_trimmed(repository) -> None:
    assert repository.create_volume("novel", "  Second  ").title == "Second"


def test_other_projects_are_untouched(tmp_path) -> None:
    repository = ObsidianProjectRepository(tmp_path)
    repository.create_project("Novel", slug="novel")
    repository.create_project("Other", slug="other")
    before = {path: path.read_bytes() for path in (tmp_path / "other").rglob("*.md")}

    repository.create_chapter("novel", "novel:volume-1", "Two")

    assert {path: path.read_bytes() for path in (tmp_path / "other").rglob("*.md")} == before
    assert not list((tmp_path / "other" / "volumes").rglob("chapter-002.md"))


def test_concurrent_creates_get_distinct_ids_and_files(repository, tmp_path) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        chapters = list(pool.map(
            lambda index: repository.create_chapter("novel", "novel:volume-1", f"Chapter {index}"),
            range(8),
        ))

    ids = [chapter.id for chapter in chapters]
    assert len(set(ids)) == 8
    assert len(list((tmp_path / "novel" / "volumes" / "volume-001").glob("chapter-*.md"))) == 9
    assert len(repository.get_project("novel").chapters) == 9


def test_trashing_a_project_moves_the_folder_and_hides_it(repository, tmp_path) -> None:
    repository.create_project("Other", slug="other")

    destination = repository.trash_project("novel")

    assert destination.parent == tmp_path / ".story-trash"
    assert destination.name.startswith("novel-")
    assert (destination / "project.md").is_file()
    assert (destination / "volumes" / "volume-001" / "chapter-001.md").is_file()
    assert not (tmp_path / "novel").exists()
    assert [row.id for row in repository.list_projects()] == ["other"]
    with pytest.raises(NotFoundError):
        repository.get_project("novel")


def test_a_trashed_project_name_can_be_used_again(repository, tmp_path) -> None:
    first = repository.trash_project("novel")
    repository.create_project("Novel", slug="novel")
    second = repository.trash_project("novel")

    assert first != second
    assert first.is_dir() and second.is_dir()
    assert repository.list_projects() == ()


def test_trashing_a_missing_project_changes_nothing(repository, tmp_path) -> None:
    with pytest.raises(NotFoundError):
        repository.trash_project("missing")

    assert (tmp_path / "novel" / "project.md").is_file()
    assert not (tmp_path / ".story-trash").exists()


def test_a_new_chapter_can_start_with_its_text(repository, tmp_path) -> None:
    chapter = repository.create_chapter("novel", "novel:volume-1", "第二章", "天亮了。\n\n雨停了。\n")

    assert chapter.id == "novel:chapter-2" and chapter.content == "天亮了。\n\n雨停了。"
    written = _read(tmp_path / "novel" / "volumes" / "volume-001" / "chapter-002.md")
    assert written.startswith("---\n") and written.endswith("---\n\n天亮了。\n\n雨停了。\n")
    assert repository.create_chapter("novel", "novel:volume-1", "空章").content == ""
