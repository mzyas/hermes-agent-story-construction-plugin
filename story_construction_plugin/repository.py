"""Repository contracts and relationship validation for story records."""

from __future__ import annotations

import re
import unicodedata

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from .domain import (
    Chapter,
    Character,
    Note,
    NoteCategory,
    Project,
    Volume,
    WorldInfo,
    WorldInfoEntry,
)


class RepositoryError(RuntimeError):
    """Base class for structured repository failures."""


class ProjectAlreadyExistsError(RepositoryError):
    """A project directory or stable project ID already exists."""


class DomainValidationError(RepositoryError, ValueError):
    """A project relationship violates the story domain contract."""


class NotFoundError(RepositoryError):
    """A stable project object ID could not be found."""


class ProjectScopeError(RepositoryError):
    """An object does not belong to the requested project."""


class VersionConflictError(RepositoryError):
    """A write used a stale object version."""


@dataclass(frozen=True, slots=True)
class ProjectTree:
    """A complete parsed project tree returned by a repository read."""

    project: Project
    world_info: WorldInfo | None
    world_info_entries: tuple[WorldInfoEntry, ...]
    characters: tuple[Character, ...]
    categories: tuple[NoteCategory, ...]
    notes: tuple[Note, ...]
    volumes: tuple[Volume, ...]
    chapters: tuple[Chapter, ...]


class StoryRepository(Protocol):
    """Read/write boundary consumed by tools and the Desktop API."""

    def create_project(self, name: str, *, slug: str | None = None) -> ProjectTree: ...

    def list_projects(self) -> Sequence[Project]: ...

    def get_project(self, project_id: str) -> ProjectTree: ...

    def get_world_info(self, project_id: str) -> WorldInfo | None: ...

    def search_world_info(self, project_id: str, query: str) -> Sequence[WorldInfoEntry]: ...

    def get_character(self, project_id: str, character_id: str) -> Character: ...

    def list_volumes(self, project_id: str) -> Sequence[Volume]: ...

    def list_chapters(self, project_id: str, volume_id: str | None = None) -> Sequence[Chapter]: ...

    def get_chapter(self, project_id: str, chapter_id: str) -> Chapter: ...

    def search_notes(self, project_id: str, query: str) -> Sequence[Note]: ...

    def search_reference_notes(self, project_id: str, query: str) -> Sequence[Note]: ...

    def save_chapter(
        self, project_id: str, chapter_id: str, content: str, *, expected_version: str
    ) -> Chapter: ...


_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def normalize_project_slug(name: str, requested_slug: str | None = None) -> str:
    normalized_name = unicodedata.normalize("NFKC", name).strip()
    if not normalized_name:
        raise DomainValidationError("project name is required")
    raw = unicodedata.normalize("NFKC", requested_slug).strip() if requested_slug is not None else normalized_name
    if requested_slug is not None and ("/" in raw or "\\" in raw or ".." in raw):
        raise DomainValidationError("project slug contains an unsafe path segment")
    slug = re.sub(r"[-\s_]+", "-", "".join(char for char in raw if char.isalnum() or char in "- _")).strip("-")
    if not slug or len(slug) > 80 or slug.casefold() in _WINDOWS_RESERVED:
        raise DomainValidationError("project slug is invalid")
    return slug


def create_project_with_default_volume(project_id: str, name: str) -> tuple[Project, tuple[Volume, ...]]:
    """Create a project aggregate with its mandatory first volume."""

    if not project_id or not name.strip():
        raise DomainValidationError("project id and name are required")
    project = Project(id=project_id, name=name)
    return project, (Volume(id=f"{project_id}:volume-1", project_id=project_id, title="Volume I"),)


def validate_category_hierarchy(categories: Iterable[NoteCategory]) -> None:
    """Reject missing parents, cross-project parents, and a third level."""

    rows = tuple(categories)
    by_id = {category.id: category for category in rows}
    if len(by_id) != len(rows):
        raise DomainValidationError("category IDs must be unique")

    for category in rows:
        if category.parent_id is None:
            continue
        parent = by_id.get(category.parent_id)
        if parent is None:
            raise DomainValidationError(f"category parent {category.parent_id!r} is missing")
        if parent.project_id != category.project_id:
            raise DomainValidationError("category parent must belong to the same project")
        if parent.parent_id is not None:
            raise DomainValidationError("note categories are limited to two levels")


def validate_chapter_relationship(chapter: Chapter, volume: Volume) -> None:
    if chapter.volume_id != volume.id:
        raise DomainValidationError("chapter volume relationship does not match")
    if chapter.project_id != volume.project_id:
        raise DomainValidationError("chapter and volume must belong to the same project")


def validate_project_has_volume(project_id: str, volumes: Iterable[Volume]) -> None:
    if not any(volume.project_id == project_id for volume in volumes):
        raise DomainValidationError("a project must have at least one volume")
