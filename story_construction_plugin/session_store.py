"""Profile-scoped persistent Story session bindings."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock


_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class StorySessionBinding:
    stored_session_id: str
    runtime_session_id: str | None
    profile: str
    connection_id: str
    source: str
    project_id: str
    project_name: str | None
    title: str
    created_at: str
    updated_at: str

    @property
    def session_id(self) -> str:
        return self.stored_session_id


class SessionBindingStoreError(RuntimeError):
    """Persistent Story session binding state is unreadable or unwritable."""


class StorySessionRegistry:
    def __init__(
        self,
        path: Path | None = None,
        *,
        locked_profile: str | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else None
        self.locked_profile = (locked_profile or "").strip() or None
        self._bindings: dict[tuple[str, str, str], StorySessionBinding] = {}
        self._lock = RLock()
        self._load()

    def bind(
        self,
        *,
        stored_session_id: str | None = None,
        runtime_session_id: str | None = None,
        session_id: str | None = None,
        profile: str = "default",
        connection_id: str = "local",
        source: str = "desktop",
        project_id: str,
        project_name: str | None = None,
        title: str = "",
    ) -> StorySessionBinding:
        durable_id = _required(
            stored_session_id or session_id or "", "stored_session_id"
        )
        key = (
            _required(profile, "profile"),
            _required(connection_id, "connection_id"),
            durable_id,
        )
        normalized_project_id = _required(project_id, "project_id")
        normalized_runtime_id = (runtime_session_id or "").strip() or None
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._rewrite() as bindings:
            previous = bindings.get(key)
            if previous is not None and previous.project_id != normalized_project_id:
                raise SessionBindingStoreError(
                    "a stored Story session cannot be rebound to another project"
                )
            binding = StorySessionBinding(
                stored_session_id=durable_id,
                runtime_session_id=normalized_runtime_id,
                profile=key[0],
                connection_id=key[1],
                source=_required(source, "source"),
                project_id=normalized_project_id,
                project_name=(project_name or "").strip() or None,
                title=(title or "").strip() or durable_id,
                created_at=previous.created_at if previous else now,
                updated_at=now,
            )
            _reject_conflicting_aliases(bindings, key, binding)
            bindings[key] = binding
            return binding

    def get(
        self,
        *,
        stored_session_id: str | None = None,
        session_id: str | None = None,
        profile: str = "default",
        connection_id: str = "local",
    ) -> StorySessionBinding | None:
        durable_id = _required(
            stored_session_id or session_id or "", "stored_session_id"
        )
        key = (
            _required(profile, "profile"),
            _required(connection_id, "connection_id"),
            durable_id,
        )
        with self._lock:
            return self._load().get(key)

    def list_for_project(
        self,
        *,
        project_id: str,
        profile: str = "default",
        connection_id: str = "local",
    ) -> tuple[StorySessionBinding, ...]:
        normalized_project_id = _required(project_id, "project_id")
        normalized_profile = _required(profile, "profile")
        normalized_connection = _required(connection_id, "connection_id")
        with self._lock:
            bindings = self._load()
            return tuple(
                binding
                for key, binding in sorted(bindings.items())
                if key[0] == normalized_profile
                and key[1] == normalized_connection
                and binding.project_id == normalized_project_id
            )

    def all(self) -> tuple[StorySessionBinding, ...]:
        with self._lock:
            return tuple(
                binding for _, binding in sorted(self._load().items())
            )

    def unbind(
        self,
        *,
        stored_session_id: str | None = None,
        session_id: str | None = None,
        profile: str = "default",
        connection_id: str = "local",
    ) -> StorySessionBinding | None:
        durable_id = _required(
            stored_session_id or session_id or "", "stored_session_id"
        )
        key = (
            _required(profile, "profile"),
            _required(connection_id, "connection_id"),
            durable_id,
        )
        with self._lock, self._rewrite() as bindings:
            removed = bindings.pop(key, None)
            return removed

    def restore_binding(
        self,
        binding: StorySessionBinding | None,
        *,
        stored_session_id: str,
        profile: str,
        connection_id: str,
    ) -> None:
        """Restore one exact snapshot after a coordinated update fails."""

        key = (
            _required(profile, "profile"),
            _required(connection_id, "connection_id"),
            _required(stored_session_id, "stored_session_id"),
        )
        if binding is not None and (
            binding.profile,
            binding.connection_id,
            binding.stored_session_id,
        ) != key:
            raise ValueError("restored Story session binding key does not match")
        with self._lock, self._rewrite() as bindings:
            if binding is None:
                bindings.pop(key, None)
            else:
                _reject_conflicting_aliases(bindings, key, binding)
                bindings[key] = binding

    def render_system_prompt(self, session_info: Mapping[str, object]) -> str:
        """Return one frozen protocol for every session in the locked Profile."""

        from .prompt_templates import render_story_agent_system_prompt

        profile = str(
            session_info.get("profile_name") or session_info.get("profile") or ""
        ).strip()
        if not profile or profile != self.locked_profile:
            return ""
        return render_story_agent_system_prompt()

    def _load(self) -> dict[tuple[str, str, str], StorySessionBinding]:
        """Return the disk-fresh rows; the durable file is the only authority.

        A missing file means no bindings. Malformed or self-conflicting content
        raises without being rewritten, and stale cached rows are discarded.
        """

        if self.path is None:
            return dict(self._bindings)
        if not self.path.exists():
            self._bindings = {}
            return self._bindings
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            bindings = _decode_payload(payload)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            raise SessionBindingStoreError(
                "persistent Story binding state is invalid"
            ) from exc

        rows: dict[tuple[str, str, str], StorySessionBinding] = {}
        for binding in bindings:
            key = (binding.profile, binding.connection_id, binding.stored_session_id)
            if key in rows:
                raise SessionBindingStoreError(
                    "persistent Story binding state contains duplicates"
                )
            try:
                _reject_conflicting_aliases(rows, key, binding)
            except SessionBindingStoreError as exc:
                raise SessionBindingStoreError(
                    "persistent Story binding state is invalid"
                ) from exc
            rows[key] = binding
        self._bindings = rows
        return rows

    @contextmanager
    def _rewrite(self):
        """Reload the durable rows, run one mutation, persist only on success."""

        if self.path is None:
            self._bindings = dict(self._bindings)
            yield self._bindings
            return
        with _file_lock(self.path):
            bindings = self._load()
            yield bindings
            self._persist()

    def _persist(self) -> None:
        if self.path is None:
            return
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": _SCHEMA_VERSION,
                "bindings": [
                    asdict(binding)
                    for _, binding in sorted(self._bindings.items())
                ],
            }
            with NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
        except (OSError, TypeError, ValueError) as exc:
            raise SessionBindingStoreError(
                "persistent Story binding state is unwritable"
            ) from exc
        finally:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)


@contextmanager
def _file_lock(path: Path):
    """Serialize writers across registry instances and processes.

    A sibling ``.sessions.json.lock`` keeps one inode for locking so the
    atomic ``os.replace`` of the bindings file never drops the held lock.
    """

    lock_path = path.parent / f".{path.name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        _lock_handle(handle)
        try:
            yield
        finally:
            _unlock_handle(handle)


def _lock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _unlock_handle(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _reject_conflicting_aliases(
    bindings: Mapping[tuple[str, str, str], StorySessionBinding],
    key: tuple[str, str, str],
    candidate: StorySessionBinding,
) -> None:
    """Reject alias claims the permission gate could not represent.

    An alias (stored id or runtime id) may be shared only by rows that agree on
    the scope identity the gate binds per session id; any other collision fails
    the write without touching the previously committed rows.
    """

    new_aliases = {candidate.stored_session_id}
    if candidate.runtime_session_id:
        new_aliases.add(candidate.runtime_session_id)
    for old_key, old in bindings.items():
        if old_key == key or old.profile != candidate.profile:
            continue
        old_aliases = {old.stored_session_id}
        if old.runtime_session_id:
            old_aliases.add(old.runtime_session_id)
        if not (new_aliases & old_aliases):
            continue
        if (
            old.connection_id != candidate.connection_id
            or old.source != candidate.source
            or old.project_id != candidate.project_id
        ):
            raise SessionBindingStoreError(
                "Story session alias already belongs to another binding"
            )


def _decode_payload(payload: object) -> tuple[StorySessionBinding, ...]:
    if not isinstance(payload, dict):
        raise ValueError("binding state must be an object")
    if payload.get("version") != _SCHEMA_VERSION or not isinstance(
        payload.get("bindings"), list
    ):
        raise ValueError("binding state schema is unsupported")
    return tuple(_decode_binding(row) for row in payload["bindings"])


def _decode_binding(row: object) -> StorySessionBinding:
    if not isinstance(row, dict):
        raise ValueError("binding record must be an object")
    required_fields = {
        "stored_session_id",
        "runtime_session_id",
        "profile",
        "connection_id",
        "source",
        "project_id",
        "project_name",
        "title",
        "created_at",
        "updated_at",
    }
    if set(row) != required_fields:
        raise ValueError("binding record fields are invalid")
    runtime_session_id = _optional_text(
        row["runtime_session_id"], "runtime_session_id"
    )
    project_name = _optional_text(row["project_name"], "project_name")
    return StorySessionBinding(
        stored_session_id=_required_value(
            row["stored_session_id"], "stored_session_id"
        ),
        runtime_session_id=runtime_session_id,
        profile=_required_value(row["profile"], "profile"),
        connection_id=_required_value(row["connection_id"], "connection_id"),
        source=_required_value(row["source"], "source"),
        project_id=_required_value(row["project_id"], "project_id"),
        project_name=project_name,
        title=_required_value(row["title"], "title"),
        created_at=_required_value(row["created_at"], "created_at"),
        updated_at=_required_value(row["updated_at"], "updated_at"),
    )


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_value(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return _required(value, field)


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    return value.strip() or None
