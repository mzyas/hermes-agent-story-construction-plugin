"""Domain invariants for story projects."""

from __future__ import annotations

import pytest

from story_construction_plugin.domain import (
    Chapter,
    Character,
    Note,
    NoteCategory,
    Project,
    Volume,
    WorldInfo,
    WorldInfoEntry,
)
from story_construction_plugin.repository import (
    DomainValidationError,
    create_project_with_default_volume,
    validate_category_hierarchy,
    validate_chapter_relationship,
    validate_project_has_volume,
)


def test_project_creation_creates_one_default_volume() -> None:
    project, volumes = create_project_with_default_volume("project-1", "Novel")

    assert project == Project(id="project-1", name="Novel")
    assert len(volumes) == 1
    assert volumes[0].project_id == project.id


def test_domain_records_keep_the_approved_relationships() -> None:
    world_info = WorldInfo(id="world-1", name="World", project_id=None)
    entry = WorldInfoEntry(id="entry-1", world_info_id=world_info.id, title="Rule", content="Magic")
    character = Character(id="character-1", project_id="project-1", name="A", content="Lead")
    root_note = Note(id="note-1", project_id="project-1", title="Reference", content="Fact")

    assert world_info.project_id is None
    assert entry.world_info_id == world_info.id
    assert character.project_id == "project-1"
    assert root_note.category_id is None


def test_category_hierarchy_stops_at_two_levels() -> None:
    root = NoteCategory(id="root", project_id="project-1", name="Characters")
    child = NoteCategory(id="child", project_id="project-1", name="Allies", parent_id=root.id)
    grandchild = NoteCategory(id="grandchild", project_id="project-1", name="Close", parent_id=child.id)

    validate_category_hierarchy([root, child])

    with pytest.raises(DomainValidationError, match="two levels"):
        validate_category_hierarchy([root, child, grandchild])


def test_chapter_must_match_volume_project() -> None:
    volume = Volume(id="volume-1", project_id="project-1", title="Volume I")
    chapter = Chapter(
        id="chapter-1",
        project_id="project-2",
        volume_id=volume.id,
        title="Chapter 1",
        content="Body",
    )

    with pytest.raises(DomainValidationError, match="project"):
        validate_chapter_relationship(chapter, volume)


def test_a_project_cannot_lose_its_last_volume() -> None:
    with pytest.raises(DomainValidationError, match="at least one volume"):
        validate_project_has_volume("project-1", [])
