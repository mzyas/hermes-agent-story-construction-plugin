"""Obsidian Markdown repository with project scoping and atomic chapter writes."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
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


TRASH_DIRECTORY = ".story-trash"


class ObsidianProjectRepository:
    """Read and write stable-id Markdown records below one configured Vault."""

    def __init__(self, vault_root: Path | str) -> None:
        root = Path(vault_root).expanduser().resolve()
        if not root.is_dir():
            raise RepositoryError(f"Vault root does not exist: {root}")
        self.vault_root = root
        self._cache_lock = threading.Lock()
        self._create_lock = threading.Lock()
        self._records_cache: tuple[tuple[Any, ...], dict[str, tuple[Any, ...]]] | None = None

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

    def create_volume(self, project_id: str, title: str) -> Volume:
        """Append a new empty volume to a project."""

        clean_title = _clean_title(title, "volume")
        with self._create_lock:
            tree = self.get_project(project_id)
            root = self._project_root(tree.project.id)
            number, volume_id = _next_numbered_id(
                tree.project.id, "volume", (row.id for row in tree.volumes)
            )
            _write_new_story_document(
                root / "volumes" / f"volume-{number:03d}.md",
                {
                    "type": "volume", "id": volume_id,
                    "project_id": tree.project.id, "title": clean_title,
                },
            )
            self._invalidate_records()
        return self._one(self.get_project(project_id).volumes, volume_id, "volume")

    def create_chapter(
        self, project_id: str, volume_id: str, title: str, content: str = ""
    ) -> Chapter:
        """Append a new chapter, empty or with its first text, at the end of a volume."""

        clean_title = _clean_title(title, "chapter")
        with self._create_lock:
            tree = self.get_project(project_id)
            self._one(tree.volumes, volume_id, "volume")
            root = self._project_root(tree.project.id)
            number, chapter_id = _next_numbered_id(
                tree.project.id, "chapter", (row.id for row in tree.chapters)
            )
            _write_new_story_document(
                root / "chapters" / f"chapter-{number:03d}.md",
                {
                    "type": "chapter", "id": chapter_id,
                    "project_id": tree.project.id, "volume_id": volume_id,
                    "title": clean_title,
                },
                content,
            )
            self._invalidate_records()
        return self._one(self.get_project(project_id).chapters, chapter_id, "chapter")

    def trash_project(self, project_id: str) -> Path:
        """Move a whole project folder into ``.story-trash`` and return its new path.

        Nothing is deleted: the folder is renamed in one step, so it can be moved
        back by hand. The trash folder is invisible to the record scan.
        """

        with self._create_lock:
            root = self._project_root(self.get_project(project_id).project.id)
            if root == self.vault_root or self.vault_root not in root.parents:
                raise RepositoryError("project folder is outside the Vault subfolders")
            if root.parts[len(self.vault_root.parts)] == TRASH_DIRECTORY:
                raise NotFoundError(f"project {project_id!r} was not found")
            nested = [
                path for path in self._markdown_files()
                if root in path.parents and path.name == "project.md" and path.parent != root
            ]
            if nested:
                raise RepositoryError("project folder contains another project")
            trash = self.vault_root / TRASH_DIRECTORY
            trash.mkdir(exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            destination = trash / f"{root.name}-{stamp}"
            suffix = 1
            while destination.exists():
                suffix += 1
                destination = trash / f"{root.name}-{stamp}-{suffix}"
            os.replace(root, destination)
            self._invalidate_records()
        return destination

    def _project_root(self, project_id: str) -> Path:
        """Directory holding a project's ``project.md``; created files go below it."""

        # ``project.md`` is where this repository writes the record, so look at
        # those first and only fall back to reading every other file.
        for path in sorted(self._markdown_files(), key=lambda candidate: candidate.name != "project.md"):
            document = _read_document(path)
            if (
                str(document.metadata.get("type", "")).strip() == "project"
                and str(document.metadata.get("id", "")).strip() == project_id
            ):
                return path.parent
        raise NotFoundError(f"project {project_id!r} was not found")

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
        self._save_body(chapter.source_ref, "chapter", chapter_id, content, expected_version)
        return self.get_chapter(project_id, chapter_id)

    def get_note(self, project_id: str, note_id: str) -> Note:
        return self._one(self.get_project(project_id).notes, note_id, "note")

    def get_world_entry(self, project_id: str, entry_id: str) -> WorldInfoEntry:
        return self._one(self.get_project(project_id).world_info_entries, entry_id, "world info entry")

    def save_character(
        self, project_id: str, character_id: str, content: str, *, expected_version: str
    ) -> Character:
        character = self.get_character(project_id, character_id)
        self._save_body(character.source_ref, "character", character_id, content, expected_version)
        return self.get_character(project_id, character_id)

    def save_note(
        self, project_id: str, note_id: str, content: str, *, expected_version: str
    ) -> Note:
        note = self.get_note(project_id, note_id)
        self._save_body(note.source_ref, "note", note_id, content, expected_version)
        return self.get_note(project_id, note_id)

    def save_world_entry(
        self, project_id: str, entry_id: str, content: str, *, expected_version: str
    ) -> WorldInfoEntry:
        entry = self.get_world_entry(project_id, entry_id)
        self._save_body(entry.source_ref, "world info entry", entry_id, content, expected_version)
        return self.get_world_entry(project_id, entry_id)

    def create_character(self, project_id: str, name: str, content: str = "") -> Character:
        """Add a character; a name already in use gets a number after it."""

        clean = _clean_title(name, "character")
        with self._create_lock:
            tree = self.get_project(project_id)
            root = self._project_root(tree.project.id)
            number, character_id = _next_numbered_id(
                tree.project.id, "character", (row.id for row in tree.characters)
            )
            _write_new_story_document(
                root / "characters" / f"character-{number:03d}.md",
                {
                    "type": "character", "id": character_id,
                    "project_id": tree.project.id,
                    "name": _unique_title(clean, (row.name for row in tree.characters)),
                },
                content,
            )
            self._invalidate_records()
        return self._one(self.get_project(project_id).characters, character_id, "character")

    def create_world_entry(self, project_id: str, title: str, content: str = "") -> WorldInfoEntry:
        """Add a world info entry; a title already in use gets a number after it."""

        clean = _clean_title(title, "world info entry")
        with self._create_lock:
            tree = self.get_project(project_id)
            if tree.world_info is None:
                raise DomainValidationError("the project has no world info to add an entry to")
            root = self._project_root(tree.project.id)
            number, entry_id = _next_numbered_id(
                tree.project.id, "world-entry", (row.id for row in tree.world_info_entries)
            )
            _write_new_story_document(
                root / "world" / f"entry-{number:03d}.md",
                {
                    "type": "world_info_entry", "id": entry_id,
                    "world_info_id": tree.world_info.id,
                    "title": _unique_title(clean, (row.title for row in tree.world_info_entries)),
                },
                content,
            )
            self._invalidate_records()
        return self._one(self.get_project(project_id).world_info_entries, entry_id, "world info entry")

    def create_note(
        self, project_id: str, title: str, content: str = "", category_id: str | None = None
    ) -> Note:
        """Add a note, optionally in a category; a title already in use there gets a number."""

        clean = _clean_title(title, "note")
        with self._create_lock:
            tree = self.get_project(project_id)
            if category_id is not None:
                self._one(tree.categories, category_id, "note category")
            root = self._project_root(tree.project.id)
            number, note_id = _next_numbered_id(
                tree.project.id, "note", (row.id for row in tree.notes)
            )
            metadata: dict[str, Any] = {
                "type": "note", "id": note_id, "project_id": tree.project.id,
                "title": _unique_title(
                    clean, (row.title for row in tree.notes if row.category_id == category_id)
                ),
            }
            if category_id is not None:
                metadata["category_id"] = category_id
            _write_new_story_document(root / "notes" / f"note-{number:03d}.md", metadata, content)
            self._invalidate_records()
        return self._one(self.get_project(project_id).notes, note_id, "note")

    def _save_body(
        self, source_ref: str, label: str, record_id: str, content: str, expected_version: str
    ) -> None:
        """Replace a record's text and keep its frontmatter; refuse a stale version."""

        path = self.resolve_source_path(source_ref)
        current_bytes = path.read_bytes()
        current_version = _version(current_bytes)
        if current_version != expected_version:
            raise VersionConflictError(
                f"{label} {record_id!r} changed since version {expected_version!r}"
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
        self._invalidate_records()

    def _records(self) -> dict[str, tuple[Any, ...]]:
        """Parsed Vault records, reused until any Markdown file changes.

        Each call still walks the Vault and stats every Markdown file, but files
        are only read and parsed again when the (path, mtime, size, inode)
        signature differs. The signature is taken before reading, so a file
        edited mid-parse is picked up by the next call. Parse failures are never
        cached. Records are frozen dataclasses in tuples, safe to share.
        """

        files = self._markdown_files()
        signature = tuple(_file_signature(path, self.vault_root) for path in files)
        with self._cache_lock:
            cached = self._records_cache
        if cached is not None and cached[0] == signature:
            return cached[1]
        result = self._scan_records(files)
        with self._cache_lock:
            self._records_cache = (signature, result)
        return result

    def _invalidate_records(self) -> None:
        with self._cache_lock:
            self._records_cache = None

    def _markdown_files(self) -> list[Path]:
        files: list[Path] = []
        for path in sorted(self.vault_root.rglob("*.md")):
            relative = path.relative_to(self.vault_root)
            if (
                len(relative.parts) > 1
                and (
                    relative.parts[0].startswith(".story-create-")
                    or relative.parts[0] == TRASH_DIRECTORY
                )
            ) or not path.is_file():
                continue
            files.append(path)
        return files

    def _scan_records(self, files: list[Path]) -> dict[str, tuple[Any, ...]]:
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
        for path in files:
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


_MAX_TITLE_LENGTH = 120


def _clean_title(title: str, kind: str) -> str:
    text = unicodedata.normalize("NFKC", title or "").strip()
    if not text:
        raise DomainValidationError(f"{kind} title is required")
    if len(text) > _MAX_TITLE_LENGTH:
        raise DomainValidationError(f"{kind} title is longer than {_MAX_TITLE_LENGTH} characters")
    if any(unicodedata.category(char).startswith("C") for char in text):
        raise DomainValidationError(f"{kind} title contains control characters")
    return text


def _unique_title(title: str, taken: Any) -> str:
    """``title``, or ``title (2)``, ``title (3)`` ... when the name is already used."""

    used = {name.casefold() for name in taken}
    if title.casefold() not in used:
        return title
    number = 2
    while f"{title} ({number})".casefold() in used:
        number += 1
    return f"{title} ({number})"


def _next_numbered_id(project_id: str, kind: str, existing_ids: Any) -> tuple[int, str]:
    """Next ``<project>:<kind>-N`` after the highest N already used."""

    pattern = re.compile(rf"^{re.escape(project_id)}:{kind}-(\d+)$")
    used = {row_id for row_id in existing_ids}
    highest = 0
    for row_id in used:
        match = pattern.match(row_id)
        if match:
            highest = max(highest, int(match.group(1)))
    number = highest + 1
    while f"{project_id}:{kind}-{number}" in used:
        number += 1
    return number, f"{project_id}:{kind}-{number}"


def _write_new_story_document(path: Path, metadata: dict[str, Any], content: str = "") -> None:
    """Create a Markdown record without ever replacing an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RepositoryError(f"refusing to overwrite an existing file: {path.name}")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary_name = handle.name
            frontmatter = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip("\n")
            body = content.rstrip("\n")
            handle.write(f"---\n{frontmatter}\n---\n" + (f"\n{body}\n" if body else ""))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def _file_signature(path: Path, vault_root: Path) -> tuple[str, int, int, int]:
    try:
        stat = path.stat()
    except OSError:
        # Vanished between listing and stat: a distinct signature forces a rescan.
        return (path.relative_to(vault_root).as_posix(), -1, -1, -1)
    return (path.relative_to(vault_root).as_posix(), stat.st_mtime_ns, stat.st_size, stat.st_ino)


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
