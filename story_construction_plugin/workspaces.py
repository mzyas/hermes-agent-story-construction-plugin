"""Per-project Hermes workspace folders and the links to Hermes projects.

A Hermes project groups sessions by working directory, so every Story project
gets its own folder under the writing Profile's workspace. The folder is
separate from the Vault: Vault records are only written through tools and the
Desktop UI, while this folder is where a session may keep its own files.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from .session_store import _file_lock


_SCHEMA_VERSION = 1
FALLBACK_DIRECTORY = "story-workspaces"
NESTED_DIRECTORY = "story"
_FOLDER_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')


class WorkspaceError(ValueError):
    """A workspace could not be resolved; ``code`` is stable for API callers."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class WorkspaceLinkStoreError(RuntimeError):
    """Persistent workspace link state is unreadable or unwritable."""


@dataclass(frozen=True, slots=True)
class WorkspaceLink:
    profile: str
    connection_id: str
    project_id: str
    hermes_project_id: str
    folder: str
    archived: bool
    created_at: str
    updated_at: str


def resolve_workspace_base(profile_home: Path, raw_config: Mapping[str, object]) -> Path:
    """Folder that holds one subfolder per Story project.

    The Profile's ``terminal.cwd`` is used when it is an existing absolute
    directory on a local terminal backend; anything else (``.``, a missing
    path, a container path) falls back to a fixed folder in the Profile home.
    An ssh terminal keeps its working directory on another host, which the
    backend cannot create, so it is refused.
    """

    terminal = raw_config.get("terminal") if isinstance(raw_config, Mapping) else None
    terminal = terminal if isinstance(terminal, Mapping) else {}
    backend = str(terminal.get("backend") or "local").strip().lower() or "local"
    if backend == "ssh":
        raise WorkspaceError("workspace_unsupported_backend")
    configured = str(terminal.get("cwd") or "").strip()
    if backend == "local" and configured and configured != ".":
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() and candidate.is_dir():
            return candidate.resolve() / NESTED_DIRECTORY
    return Path(profile_home).resolve() / FALLBACK_DIRECTORY


def project_folder_name(project_id: str) -> str:
    """A single safe path segment derived from a project id."""

    name = unicodedata.normalize("NFKC", str(project_id or ""))
    name = _FOLDER_UNSAFE.sub("-", name).strip(" .-")
    name = name[:80].rstrip(" .-")
    if not name:
        raise WorkspaceError("workspace_name_invalid")
    return name


def ensure_project_folder(base: Path, project_id: str) -> tuple[Path, bool]:
    """Create ``<base>/<project>`` if needed; an existing folder is reused as is."""

    base = Path(base)
    folder = base / project_folder_name(project_id)
    try:
        base.mkdir(parents=True, exist_ok=True)
        resolved_base = base.resolve()
        if folder.resolve().parent != resolved_base:
            raise WorkspaceError("workspace_name_invalid")
        if folder.is_dir():
            return folder.resolve(), False
        folder.mkdir()
    except FileExistsError:
        if not folder.is_dir():
            raise WorkspaceError("workspace_unavailable") from None
        return folder.resolve(), False
    except OSError as exc:
        raise WorkspaceError("workspace_unavailable") from exc
    return folder.resolve(), True


class WorkspaceLinkRegistry:
    """Durable ``(profile, connection, Story project) -> Hermes project`` links."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = RLock()

    def get(self, *, profile: str, connection_id: str, project_id: str) -> WorkspaceLink | None:
        key = _key(profile, connection_id, project_id)
        with self._lock:
            return self._load().get(key)

    def link(
        self,
        *,
        profile: str,
        connection_id: str,
        project_id: str,
        hermes_project_id: str,
        folder: str,
    ) -> WorkspaceLink:
        key = _key(profile, connection_id, project_id)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, _file_lock(self.path):
            rows = self._load()
            previous = rows.get(key)
            link = WorkspaceLink(
                profile=key[0],
                connection_id=key[1],
                project_id=key[2],
                hermes_project_id=_text(hermes_project_id, "hermes_project_id"),
                folder=_text(folder, "folder"),
                archived=False,
                created_at=previous.created_at if previous else now,
                updated_at=now,
            )
            rows[key] = link
            self._persist(rows)
            return link

    def mark_archived(self, *, profile: str, connection_id: str, project_id: str) -> WorkspaceLink | None:
        key = _key(profile, connection_id, project_id)
        with self._lock, _file_lock(self.path):
            rows = self._load()
            previous = rows.get(key)
            if previous is None:
                return None
            archived = WorkspaceLink(
                **{**asdict(previous), "archived": True, "updated_at": datetime.now(timezone.utc).isoformat()}
            )
            rows[key] = archived
            self._persist(rows)
            return archived

    def _load(self) -> dict[tuple[str, str, str], WorkspaceLink]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != _SCHEMA_VERSION:
                raise ValueError("unsupported version")
            rows: dict[tuple[str, str, str], WorkspaceLink] = {}
            for row in payload["links"]:
                link = WorkspaceLink(
                    profile=_text(row["profile"], "profile"),
                    connection_id=_text(row["connection_id"], "connection_id"),
                    project_id=_text(row["project_id"], "project_id"),
                    hermes_project_id=_text(row["hermes_project_id"], "hermes_project_id"),
                    folder=_text(row["folder"], "folder"),
                    archived=bool(row["archived"]),
                    created_at=_text(row["created_at"], "created_at"),
                    updated_at=_text(row["updated_at"], "updated_at"),
                )
                rows[(link.profile, link.connection_id, link.project_id)] = link
            return rows
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise WorkspaceLinkStoreError("persistent Story workspace state is invalid") from exc

    def _persist(self, rows: Mapping[tuple[str, str, str], WorkspaceLink]) -> None:
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": _SCHEMA_VERSION,
                "links": [asdict(link) for _key_, link in sorted(rows.items())],
            }
            with NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
        except (OSError, TypeError, ValueError) as exc:
            raise WorkspaceLinkStoreError("persistent Story workspace state is unwritable") from exc
        finally:
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)


def _key(profile: str, connection_id: str, project_id: str) -> tuple[str, str, str]:
    return (
        _text(profile, "profile"),
        _text(connection_id, "connection_id"),
        _text(project_id, "project_id"),
    )


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()
