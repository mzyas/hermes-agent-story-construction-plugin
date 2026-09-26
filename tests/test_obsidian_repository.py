"""Behavior tests for the Obsidian Markdown repository."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, local

import pytest

import story_construction_plugin.obsidian_repository as obsidian_repository
from story_construction_plugin.obsidian_repository import (
    ObsidianProjectRepository,
    RepositoryError,
    VersionConflictError,
)
from story_construction_plugin.repository import (
    DomainValidationError,
    ProjectAlreadyExistsError,
)


def _write(root: Path, relative: str, frontmatter: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}\n", encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    _write(tmp_path, "project.md", "type: project\nid: p1\nname: Demo\nworld_info_id: w1", "")
    _write(tmp_path, "world/index.md", "type: world_info\nid: w1\nname: World", "")
    _write(
        tmp_path,
        "world/entry.md",
        "type: world_info_entry\nid: e1\nworld_info_id: w1\ntitle: Magic\nproject_id: p1",
        "Magic has a price.",
    )
    _write(tmp_path, "characters/hero.md", "type: character\nid: c1\nproject_id: p1\nname: Hero", "Brave")
    _write(tmp_path, "notes/root.md", "type: note\nid: n1\nproject_id: p1\ntitle: Reference\nreference: true", "Use rain.")
    _write(tmp_path, "notes/category.md", "type: note_category\nid: cat1\nproject_id: p1\nname: Lore", "")
    _write(tmp_path, "notes/child.md", "type: note_category\nid: cat2\nproject_id: p1\nname: Places\nparent_id: cat1", "")
    _write(tmp_path, "volumes/v1.md", "type: volume\nid: v1\nproject_id: p1\ntitle: Volume I", "")
    _write(
        tmp_path,
        "volumes/ch1.md",
        "type: chapter\nid: ch1\nproject_id: p1\nvolume_id: v1\ntitle: Chapter 1",
        "Opening.",
    )
    _write(tmp_path, "other/project.md", "type: project\nid: p2\nname: Other", "")
    _write(tmp_path, "other/note.md", "type: note\nid: n2\nproject_id: p2\ntitle: Secret", "Do not leak.")
    return tmp_path


def test_create_project_initializes_readable_minimum_tree(tmp_path: Path) -> None:
    repository = ObsidianProjectRepository(tmp_path)

    tree = repository.create_project("星海纪事", slug="星海-纪事")

    assert tree.project.id == "星海-纪事"
    assert tree.project.name == "星海纪事"
    assert tree.world_info is not None
    assert tree.world_info.project_id == tree.project.id
    assert [row.title for row in tree.volumes] == ["第一卷"]
    assert [row.title for row in tree.chapters] == ["第一章"]
    assert tree.chapters[0].content == ""
    assert (tmp_path / "星海-纪事" / "project.md").is_file()
    assert (tmp_path / "星海-纪事" / "world" / "world.md").is_file()
    assert (tmp_path / "星海-纪事" / "characters").is_dir()
    assert (tmp_path / "星海-纪事" / "notes").is_dir()
    assert (tmp_path / "星海-纪事" / "volumes" / "volume-001.md").is_file()
    chapter_path = tmp_path / "星海-纪事" / "chapters" / "chapter-001.md"
    assert chapter_path.is_file()
    assert not chapter_path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_create_project_rejects_existing_project_id_before_publish(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "legacy/project.md",
        "type: project\nid: p1\nname: Legacy\nworld_info_id: legacy-world",
        "",
    )
    _write(
        tmp_path,
        "legacy/world/world.md",
        "type: world_info\nid: legacy-world\nname: Legacy World\nproject_id: p1",
        "",
    )
    _write(
        tmp_path,
        "legacy/volumes/volume.md",
        "type: volume\nid: legacy-volume\nproject_id: p1\ntitle: Legacy Volume",
        "",
    )
    _write(
        tmp_path,
        "legacy/chapters/chapter.md",
        (
            "type: chapter\nid: legacy-chapter\nproject_id: p1\n"
            "volume_id: legacy-volume\ntitle: Legacy Chapter"
        ),
        "",
    )
    repository = ObsidianProjectRepository(tmp_path)

    with pytest.raises(ProjectAlreadyExistsError):
        repository.create_project("Replacement", slug="p1")

    assert not (tmp_path / "p1").exists()
    assert repository.get_project("p1").project.name == "Legacy"


@pytest.mark.parametrize(
    ("relative", "frontmatter"),
    [
        (
            "legacy/world.md",
            "type: world_info\nid: p1:world\nname: Existing World\nproject_id: other",
        ),
        (
            "legacy/volume.md",
            "type: volume\nid: p1:volume-1\nproject_id: other\ntitle: Existing Volume",
        ),
        (
            "legacy/chapter.md",
            (
                "type: chapter\nid: p1:chapter-1\nproject_id: other\n"
                "volume_id: other:volume\ntitle: Existing Chapter"
            ),
        ),
    ],
)
def test_create_project_rejects_existing_generated_id_before_publish(
    tmp_path: Path, relative: str, frontmatter: str
) -> None:
    _write(tmp_path, relative, frontmatter, "")
    repository = ObsidianProjectRepository(tmp_path)

    with pytest.raises(ProjectAlreadyExistsError):
        repository.create_project("Novel", slug="p1")

    assert not (tmp_path / "p1").exists()


@pytest.mark.parametrize("slug", ["../outside", "a/b", "a\\b", "CON", "x" * 81])
def test_create_project_rejects_unsafe_explicit_slug(tmp_path: Path, slug: str) -> None:
    repository = ObsidianProjectRepository(tmp_path)

    with pytest.raises(DomainValidationError):
        repository.create_project("Novel", slug=slug)

    assert list(tmp_path.iterdir()) == []


def test_concurrent_same_slug_leaves_one_complete_project(tmp_path: Path) -> None:
    repository = ObsidianProjectRepository(tmp_path)

    def create() -> str:
        try:
            return repository.create_project("Novel", slug="novel").project.id
        except ProjectAlreadyExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: create(), range(2)))

    assert sorted(results) == ["exists", "novel"]
    assert repository.get_project("novel").chapters[0].title == "第一章"
    assert list(tmp_path.glob(".story-create-*")) == []


def test_concurrent_create_ignores_unpublished_staging_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ObsidianProjectRepository(tmp_path)
    both_ready_to_publish = Barrier(2)
    release_loser = Event()
    worker = local()
    replace = obsidian_repository.os.replace

    def coordinated_replace(source: Path, destination: Path) -> None:
        both_ready_to_publish.wait(timeout=5)
        if worker.role == "loser" and not release_loser.wait(timeout=5):
            raise TimeoutError("winner did not finish its post-publish read")
        replace(source, destination)

    monkeypatch.setattr(obsidian_repository.os, "replace", coordinated_replace)

    def create(role: str) -> str:
        worker.role = role
        try:
            return repository.create_project("Novel", slug="novel").chapters[0].title
        except ProjectAlreadyExistsError:
            return "exists"

    with ThreadPoolExecutor(max_workers=2) as pool:
        winner = pool.submit(create, "winner")
        loser = pool.submit(create, "loser")
        try:
            winner_result = winner.result(timeout=5)
        finally:
            release_loser.set()
        loser_result = loser.result(timeout=5)

    assert winner_result == "第一章"
    assert loser_result == "exists"


def test_create_project_cleans_staging_when_document_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ObsidianProjectRepository(tmp_path)
    write_document = obsidian_repository._write_story_document

    def fail_on_chapter(path: Path, metadata: dict[str, object], content: str = "") -> None:
        if path.name == "chapter-001.md":
            raise OSError("injected chapter write failure")
        write_document(path, metadata, content)

    monkeypatch.setattr(obsidian_repository, "_write_story_document", fail_on_chapter)

    with pytest.raises(OSError, match="injected chapter write failure"):
        repository.create_project("Novel", slug="novel")

    assert not (tmp_path / "novel").exists()
    assert list(tmp_path.glob(".story-create-*")) == []


def test_create_project_cleans_staging_when_tree_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = ObsidianProjectRepository(tmp_path)

    def fail_validation(self, project_id: str):
        raise DomainValidationError("injected project tree validation failure")

    monkeypatch.setattr(ObsidianProjectRepository, "get_project", fail_validation)

    with pytest.raises(DomainValidationError, match="injected project tree validation failure"):
        repository.create_project("Novel", slug="novel")

    assert not (tmp_path / "novel").exists()
    assert list(tmp_path.glob(".story-create-*")) == []


def test_loads_project_tree_and_returns_relative_source_refs(vault: Path) -> None:
    repository = ObsidianProjectRepository(vault)

    tree = repository.get_project("p1")

    assert tree.project.name == "Demo"
    assert tree.world_info is not None
    assert [entry.id for entry in tree.world_info_entries] == ["e1"]
    assert [character.id for character in tree.characters] == ["c1"]
    assert [note.id for note in tree.notes] == ["n1"]
    assert [chapter.id for chapter in tree.chapters] == ["ch1"]
    assert tree.chapters[0].source_ref == "volumes/ch1.md"
    assert tree.chapters[0].version


def test_project_scoped_search_does_not_leak_other_project(vault: Path) -> None:
    repository = ObsidianProjectRepository(vault)

    assert [entry.id for entry in repository.search_world_info("p1", "price")] == ["e1"]
    assert repository.search_notes("p1", "secret") == ()
    assert [note.id for note in repository.search_reference_notes("p1", "rain")] == ["n1"]


def test_chapter_write_requires_current_version_and_is_atomic(vault: Path) -> None:
    repository = ObsidianProjectRepository(vault)
    original = repository.get_chapter("p1", "ch1")

    updated = repository.save_chapter("p1", "ch1", "Rewritten.", expected_version=original.version)

    assert updated.content == "Rewritten."
    assert repository.get_chapter("p1", "ch1").content == "Rewritten."
    with pytest.raises(VersionConflictError):
        repository.save_chapter("p1", "ch1", "Stale.", expected_version=original.version)


def test_source_ref_cannot_escape_configured_vault(vault: Path) -> None:
    repository = ObsidianProjectRepository(vault)

    with pytest.raises(RepositoryError, match="Vault root"):
        repository.resolve_source_path("../../outside.md")
