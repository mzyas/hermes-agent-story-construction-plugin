"""Durable proposals, the approvals that unlock them, and snapshots of what they replaced.

Proposals live in ``plugin-data`` next to the session bindings, never in the
Vault. A proposal only becomes writable through an *approval* the Desktop
creates; the Agent can read a proposal's state but has no way to create one.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Any

from .session_store import _file_lock

_SCHEMA_VERSION = 1
APPROVAL_MINUTES = 15
KEEP_FINISHED_DAYS = 7
MAX_PENDING = 200
SNAPSHOTS_PER_TARGET = 20
OPEN_STATUSES = ("pending", "approved")
FINISHED_STATUSES = ("applied", "discarded", "superseded")


class ProposalStoreError(RuntimeError):
    """Persistent proposal state is unreadable or unwritable."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


class ProposalStore:
    def __init__(self, path: Path, *, now: Callable[[], datetime] = _now) -> None:
        self.path = Path(path)
        self._now = now
        self._lock = RLock()

    # ------------------------------------------------------------- reading
    def get(self, proposal_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._view(next((row for row in self._load() if row["id"] == proposal_id), None))

    def list_for_project(
        self, *, project_id: str, profile: str, connection_id: str, include_finished: bool = False
    ) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                self._view(row)
                for row in self._load()
                if row["project_id"] == project_id
                and row["profile"] == profile
                and row["connection_id"] == connection_id
            ]
        views = [row for row in rows if row is not None]
        if include_finished:
            return views
        return [row for row in views if row["status"] in (*OPEN_STATUSES, "expired")]

    def latest_applied(
        self, *, project_id: str, target_id: str, target_type: str = "chapter"
    ) -> dict[str, Any] | None:
        with self._lock:
            rows = [
                row for row in self._load()
                if row["project_id"] == project_id
                and row["status"] == "applied"
                and row.get("applied")
                and not row["applied"].get("undone_at")
                and target_id in _written_ids(row)
                and _target_type(row) == target_type
            ]
        rows.sort(key=lambda row: row["applied"]["at"])
        return self._view(rows[-1]) if rows else None

    def mark_undone(self, proposal_id: str) -> dict[str, Any] | None:
        def change(row: dict[str, Any]) -> None:
            if row.get("applied"):
                row["applied"]["undone_at"] = _iso(self._now())

        return self.mutate(proposal_id, change)

    def recent_applied(self, *, project_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = [
                row for row in self._load()
                if row["project_id"] == project_id and row["status"] == "applied" and row.get("applied")
            ]
        rows.sort(key=lambda row: row["applied"]["at"], reverse=True)
        return [self._view(row) for row in rows[:limit]]

    # ------------------------------------------------------------- writing
    def create(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        """Store a pending proposal; it supersedes older open ones for the same target."""

        now = self._now()
        row = {
            **proposal,
            "id": secrets.token_hex(6),
            "status": "pending",
            "approval": None,
            "applied": None,
            "created_at": _iso(now),
            "updated_at": _iso(now),
        }
        with self._lock, _file_lock(self.path):
            rows = self._load()
            for other in rows:
                if other["status"] in OPEN_STATUSES and _same_target(other, row):
                    other["status"] = "superseded"
                    other["updated_at"] = row["created_at"]
            rows.append(row)
            self._persist(self._prune(rows, now))
        return self._view(row)

    def mutate(self, proposal_id: str, change: Callable[[dict[str, Any]], None]) -> dict[str, Any] | None:
        """Apply ``change`` to one stored proposal under the file lock."""

        with self._lock, _file_lock(self.path):
            rows = self._load()
            row = next((candidate for candidate in rows if candidate["id"] == proposal_id), None)
            if row is None:
                return None
            change(row)
            row["updated_at"] = _iso(self._now())
            self._persist(rows)
            return self._view(row)

    def approve(self, proposal_id: str, approval: Mapping[str, Any]) -> dict[str, Any] | None:
        now = self._now()

        def change(row: dict[str, Any]) -> None:
            row["status"] = "approved"
            row["approval"] = {
                **approval,
                "approved_at": _iso(now),
                "expires_at": _iso(now + timedelta(minutes=APPROVAL_MINUTES)),
            }

        return self.mutate(proposal_id, change)

    def revoke(self, proposal_id: str) -> dict[str, Any] | None:
        def change(row: dict[str, Any]) -> None:
            if row["status"] == "approved":
                row["status"] = "pending"
                row["approval"] = None

        return self.mutate(proposal_id, change)

    def discard(self, proposal_id: str) -> dict[str, Any] | None:
        def change(row: dict[str, Any]) -> None:
            if row["status"] in OPEN_STATUSES:
                row["status"] = "discarded"
                row["approval"] = None

        return self.mutate(proposal_id, change)

    def mark_applied(self, proposal_id: str, applied: Mapping[str, Any]) -> dict[str, Any] | None:
        now = self._now()

        def change(row: dict[str, Any]) -> None:
            row["status"] = "applied"
            row["applied"] = {**applied, "at": _iso(now)}

        return self.mutate(proposal_id, change)

    def forget_project(self, project_id: str) -> int:
        """Drop every open proposal of a deleted project."""

        count = 0

        with self._lock, _file_lock(self.path):
            rows = self._load()
            for row in rows:
                if row["project_id"] == project_id and row["status"] in OPEN_STATUSES:
                    row["status"] = "discarded"
                    row["approval"] = None
                    count += 1
            if count:
                self._persist(rows)
        return count

    # ------------------------------------------------------------ internals
    def _view(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        """A copy whose status reports an overdue approval as ``expired``."""

        if row is None:
            return None
        view = json.loads(json.dumps(row))
        approval = view.get("approval")
        if view["status"] == "approved" and approval and approval["expires_at"] <= _iso(self._now()):
            view["status"] = "expired"
        return view

    def _prune(self, rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
        cutoff = _iso(now - timedelta(days=KEEP_FINISHED_DAYS))
        kept = [
            row for row in rows
            if row["status"] in OPEN_STATUSES or row["updated_at"] >= cutoff
        ]
        open_rows = [row for row in kept if row["status"] in OPEN_STATUSES]
        if len(open_rows) > MAX_PENDING:
            for row in sorted(open_rows, key=lambda candidate: candidate["created_at"])[: len(open_rows) - MAX_PENDING]:
                row["status"] = "superseded"
        return kept

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("version") != _SCHEMA_VERSION:
                raise ValueError("unsupported version")
            rows = payload["proposals"]
            for row in rows:
                for field in ("id", "project_id", "profile", "connection_id", "status", "created_at", "updated_at"):
                    if not isinstance(row[field], str) or not row[field]:
                        raise ValueError(field)
            return rows
        except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProposalStoreError("persistent Story proposal state is invalid") from exc

    def _persist(self, rows: list[dict[str, Any]]) -> None:
        _write_json(self.path, {"version": _SCHEMA_VERSION, "proposals": rows}, "proposal")


def _target_type(row: Mapping[str, Any]) -> str:
    """Proposals saved before other targets existed have no type: they are chapters."""

    return row.get("target_type") or "chapter"


def _target_id(row: Mapping[str, Any]) -> str | None:
    return row.get("target_id") or row.get("chapter_id")


def _is_new(row: Mapping[str, Any]) -> bool:
    return str(row.get("kind", "")).startswith("new_")


def _written_ids(row: Mapping[str, Any]) -> tuple[str | None, ...]:
    applied = row.get("applied") or {}
    return (_target_id(row), applied.get("target_id"), applied.get("chapter_id"))


def _same_target(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left["project_id"] == right["project_id"]
        and left["profile"] == right["profile"]
        and left["connection_id"] == right["connection_id"]
        and left.get("kind") == right.get("kind")
        and _target_type(left) == _target_type(right)
        and _target_id(left) == _target_id(right)
        and (not _is_new(left) or left.get("title") == right.get("title"))
    )


def _write_json(path: Path, payload: Mapping[str, Any], label: str) -> None:
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, TypeError, ValueError) as exc:
        raise ProposalStoreError(f"persistent Story {label} state is unwritable") from exc
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


# ------------------------------------------------------------------ snapshots
_SAFE = re.compile(r"[^0-9A-Za-z_.\-一-鿿]")


def _segment(value: str) -> str:
    cleaned = _SAFE.sub("-", value).strip(".-")[:80]
    if not cleaned:
        raise ValueError("snapshot name is invalid")
    return cleaned


class ChapterHistory:
    """A record's text as it was just before each write the Agent made."""

    def __init__(self, root: Path, *, keep: int = SNAPSHOTS_PER_TARGET) -> None:
        self.root = Path(root)
        self.keep = keep
        self._lock = RLock()

    def save(self, *, project_id: str, target_id: str, text: str, version: str, proposal_id: str) -> str:
        folder = self._folder(project_id, target_id)
        snapshot_id = f"{_iso(_now()).replace(':', '').replace('+', 'Z')}-{proposal_id}"
        with self._lock:
            _write_json(
                folder / f"{snapshot_id}.json",
                {"id": snapshot_id, "version": version, "proposal_id": proposal_id, "text": text},
                "snapshot",
            )
            files = sorted(folder.glob("*.json"))
            for stale in files[: max(0, len(files) - self.keep)]:
                with suppress(OSError):
                    stale.unlink()
        return snapshot_id

    def load(self, *, project_id: str, target_id: str, snapshot_id: str) -> dict[str, Any] | None:
        path = self._folder(project_id, target_id) / f"{_segment(snapshot_id)}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _folder(self, project_id: str, target_id: str) -> Path:
        return self.root / _segment(project_id) / _segment(target_id)
