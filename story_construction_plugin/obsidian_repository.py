"""Obsidian Markdown repository with project scoping and atomic chapter writes."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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
from .repository import (
    DomainValidationError,
    NotFoundError,
    ProjectAlreadyExistsError,
    ProjectTree,
    RepositoryError,
    VersionConflictError,
    normalize_project_slug,
    validate_category_hierarchy,
    validate_chapter_relationship,
    validate_project_has_volume,
)


@dataclass(frozen=True, slots=True)
class _Document:
    path: Path
    metadata: dict[str, Any]
    content: str
    version: str


class ObsidianProjectRepository:
    """Read and write stable-id Markdown records below one configured Vault."""

    def __init__(self, vault_root: Path | str) -> None:
        root = Path(vault_root).expanduser().resolve()
        if not root.is_dir():
            raise RepositoryError(f"Vault root does not exist: {root}")
        self.vault_root = root

    def create_project(self, name: str, *, slug: str | None = None) -> ProjectTree:
        project_slug = normalize_project_slug(name, slug)
        final_root = (self.vault_root / project_slug).resolve()
        if self.vault_root not in final_root.parents or final_root.exists():
            raise ProjectAlreadyExistsError(f"project {project_slug!r} already exists")

        project_id = project_slug
        world_id = f"{project_id}:world"
        volume_id = f"{project_id}:volume-1"
        chapter_id = f"{project_id}:chapter-1"
        generated_ids = {
            "project": project_id,
            "world_info": world_id,
            "volume": volume_id,
            "chapter": chapter_id,
        }
        existing_records = self._records()
        if any(
            any(row.id == object_id for row in existing_records[kind])
            for kind, object_id in generated_ids.items()
        ):
            raise ProjectAlreadyExistsError(f"project {project_slug!r} already exists")

        staging_parent = Path(tempfile.mkdtemp(prefix=".story-create-", dir=self.vault_root))
        staging_root = staging_parent / project_slug
        try:
            for relative in ("world", "characters", "notes", "volumes", "chapters"):
                (staging_root / relative).mkdir(parents=True, exist_ok=True)
            _write_story_document(staging_root / "project.md", {
                "type": "project", "id": project_id, "name": name.strip(),
                "world_info_id": world_id,
            })
            _write_story_document(staging_root / "world" / "world.md", {
                "type": "world_info", "id": world_id, "name": "世界设定",
                "project_id": project_id,
            })
            _write_story_document(staging_root / "volumes" / "volume-001.md", {
                "type": "volume", "id": volume_id, "project_id": project_id,
                "title": "第一卷",
            })
            _write_story_document(staging_root / "chapters" / "chapter-001.md", {
                "type": "chapter", "id": chapter_id, "project_id": project_id,
                "volume_id": volume_id, "title": "第一章",
            })
            tree = ObsidianProjectRepository(staging_parent).get_project(project_id)
            try:
                os.replace(staging_root, final_root)
            except OSError as exc:
                if final_root.exists():
                    raise ProjectAlreadyExistsError(f"project {project_slug!r} already exists") from exc
                raise
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        return tree

    def get_project(self, project_id: str) -> ProjectTree:
        records = self._records()
        project = self._one(records["project"], project_id, "project")
        world_info = next(
            (row for row in records["world_info"] if row.id == project.world_info_id),
            None,
        )
        entries = tuple(
            row for row in records["world_info_entry"]
            if world_info is not None and row.world_info_id == world_info.id
        )
        characters = tuple(row for row in records["character"] if row.project_id == project.id)
        categories = tuple(row for row in records["note_category"] if row.project_id == project.id)
        notes = tuple(row for row in records["note"] if row.project_id == project.id)
        volumes = tuple(row for row in records["volume"] if row.project_id == project.id)
        chapters = tuple(row for row in records["chapter"] if row.project_id == project.id)

        validate_category_hierarchy(categories)
        validate_project_has_volume(project.id, volumes)
        volumes_by_id = {volume.id: volume for volume in volumes}
        for chapter in chapters:
            volume = volumes_by_id.get(chapter.volume_id)
            if volume is None:
                raise DomainValidationError(f"chapter {chapter.id!r} refers to a missing volume")
            validate_chapter_relationship(chapter, volume)

        return ProjectTree(
            project=project,
            world_info=world_info,
            world_info_entries=entries,
            characters=characters,
            categories=categories,
            notes=notes,
            volumes=volumes,
            chapters=chapters,
        )

    def list_projects(self) -> tuple[Project, ...]:
        return tuple(self._records()["project"])

    def get_world_info(self, project_id: str) -> WorldInfo | None:
        return self.get_project(project_id).world_info

    def search_world_info(self, project_id: str, query: str) -> tuple[WorldInfoEntry, ...]:
        needle = query.casefold().strip()
        return tuple(
            row for row in self.get_project(project_id).world_info_entries
            if not needle or needle in f"{row.title}\n{row.content}".casefold()
        )

    def get_character(self, project_id: str, character_id: str) -> Character:
        return self._one(self.get_project(project_id).characters, character_id, "character")

    def list_volumes(self, project_id: str) -> tuple[Volume, ...]:
        return self.get_project(project_id).volumes

    def list_chapters(self, project_id: str, volume_id: str | None = None) -> tuple[Chapter, ...]:
        chapters = self.get_project(project_id).chapters
        return tuple(chapter for chapter in chapters if volume_id is None or chapter.volume_id == volume_id)

    def get_chapter(self, project_id: str, chapter_id: str) -> Chapter:
        return self._one(self.get_project(project_id).chapters, chapter_id, "chapter")

    def search_notes(self, project_id: str, query: str) -> tuple[Note, ...]:
        needle = query.casefold().strip()
        return tuple(
            row for row in self.get_project(project_id).notes
            if not needle or needle in f"{row.title}\n{row.content}".casefold()
        )

    def search_reference_notes(self, project_id: str, query: str) -> tuple[Note, ...]:
        return tuple(row for row in self.search_notes(project_id, query) if row.reference)

    def resolve_source_path(self, source_ref: str) -> Path:
        if not source_ref or "\x00" in source_ref:
            raise RepositoryError("invalid Vault source reference")
        candidate = (self.vault_root / source_ref).resolve()
        if candidate == self.vault_root or self.vault_root not in candidate.parents:
            raise RepositoryError("source reference escapes the configured Vault root")
        if not candidate.is_file():
            raise RepositoryError(f"source reference is not a file in the Vault: {source_ref}")
        return candidate

    def save_chapter(
        self,
        project_id: str,
        chapter_id: str,
        content: str,
        *,
        expected_version: str,
    ) -> Chapter:
        chapter = self.get_chapter(project_id, chapter_id)
        path = self.resolve_source_path(chapter.source_ref)
        current_bytes = path.read_bytes()
        current_version = _version(current_bytes)
        if current_version != expected_version:
            raise VersionConflictError(
                f"chapter {chapter_id!r} changed since version {expected_version!r}"
            )

        original_text = current_bytes.decode("utf-8")
        prefix = _frontmatter_prefix(original_text)
        rendered = f"{prefix}{content.rstrip(chr(10))}\n"
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if temporary_name and Path(temporary_name).exists():
                Path(temporary_name).unlink()
        return self.get_chapter(project_id, chapter_id)

    def _records(self) -> dict[str, tuple[Any, ...]]:
        records: dict[str, list[Any]] = {
            "project": [],
            "world_info": [],
            "world_info_entry": [],
            "character": [],
            "note_category": [],
            "note": [],
            "volume": [],
            "chapter": [],
        }
        for path in sorted(self.vault_root.rglob("*.md")):
            relative = path.relative_to(self.vault_root)
            if (
                len(relative.parts) > 1
                and relative.parts[0].startswith(".story-create-")
            ) or not path.is_file():
                continue
            document = _read_document(path)
            kind = str(document.metadata.get("type", "")).strip()
            if kind not in records:
                continue
            records[kind].append(_to_record(kind, document, self.vault_root))
        result = {kind: tuple(rows) for kind, rows in records.items()}
        for kind, rows in result.items():
            ids = [row.id for row in rows]
            if len(ids) != len(set(ids)):
                raise RepositoryError(f"duplicate {kind} ID in Vault")
        return result

    @staticmethod
    def _one(rows: tuple[Any, ...], object_id: str, kind: str) -> Any:
        for row in rows:
            if row.id == object_id:
                return row
        raise NotFoundError(f"{kind} {object_id!r} was not found")


def _write_story_document(path: Path, metadata: dict[str, Any], content: str = "") -> None:
    frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip("\n")
    rendered = f"---\n{frontmatter}\n---\n\n{content.rstrip(chr(10))}"
    path.write_text(f"{rendered}\n", encoding="utf-8", newline="")


def _read_document(path: Path) -> _Document:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryError(f"Markdown is not UTF-8: {path}") from exc
    metadata, content = _split_document(text)
    return _Document(path=path, metadata=metadata, content=content.rstrip("\r\n"), version=_version(raw))


def _split_document(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        raise RepositoryError("Markdown frontmatter is not closed")
    raw_frontmatter = "".join(lines[1:end])
    metadata = yaml.safe_load(raw_frontmatter) or {}
    if not isinstance(metadata, dict):
        raise RepositoryError("Markdown frontmatter must be a mapping")
    return dict(metadata), "".join(lines[end + 1:]).lstrip("\r\n")


def _to_record(kind: str, document: _Document, vault_root: Path) -> Any:
    metadata = document.metadata
    object_id = _required(metadata, "id", kind)
    source_ref = document.path.relative_to(vault_root).as_posix()
    common = {"source_ref": source_ref, "version": document.version}
    if kind == "project":
        return Project(id=object_id, name=_text(metadata, "name", document.path.stem), world_info_id=_optional(metadata, "world_info_id"))
    if kind == "world_info":
        return WorldInfo(id=object_id, name=_text(metadata, "name", document.path.stem), project_id=_optional(metadata, "project_id"))
    if kind == "world_info_entry":
        return WorldInfoEntry(id=object_id, world_info_id=_required(metadata, "world_info_id", kind), title=_text(metadata, "title", document.path.stem), content=document.content, **common)
    if kind == "character":
        return Character(id=object_id, project_id=_required(metadata, "project_id", kind), name=_text(metadata, "name", document.path.stem), content=document.content, **common)
    if kind == "note_category":
        return NoteCategory(id=object_id, project_id=_required(metadata, "project_id", kind), name=_text(metadata, "name", document.path.stem), parent_id=_optional(metadata, "parent_id"))
    if kind == "note":
        return Note(id=object_id, project_id=_required(metadata, "project_id", kind), title=_text(metadata, "title", document.path.stem), content=document.content, category_id=_optional(metadata, "category_id"), reference=bool(metadata.get("reference", False)), **common)
    if kind == "volume":
        return Volume(id=object_id, project_id=_required(metadata, "project_id", kind), title=_text(metadata, "title", document.path.stem))
    if kind == "chapter":
        return Chapter(id=object_id, project_id=_required(metadata, "project_id", kind), volume_id=_required(metadata, "volume_id", kind), title=_text(metadata, "title", document.path.stem), content=document.content, **common)
    raise RepositoryError(f"unsupported Markdown type: {kind}")


def _required(metadata: dict[str, Any], key: str, kind: str) -> str:
    value = metadata.get(key)
    if value is None or not str(value).strip():
        raise RepositoryError(f"{kind} frontmatter requires {key}")
    return str(value)


def _optional(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return None if value is None or not str(value).strip() else str(value)


def _text(metadata: dict[str, Any], key: str, fallback: str) -> str:
    value = metadata.get(key)
    return fallback if value is None else str(value)


def _version(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _frontmatter_prefix(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return ""
    end = next((index for index in range(1, len(lines)) if lines[index].strip() == "---"), None)
    if end is None:
        raise RepositoryError("Markdown frontmatter is not closed")
    prefix = "".join(lines[:end + 1])
    return prefix if prefix.endswith(("\n", "\r")) else f"{prefix}\n"
