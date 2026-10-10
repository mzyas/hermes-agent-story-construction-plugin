"""Find the Story session that a Hermes session id belongs to.

A binding names the session the person started from the Story page. Hermes
gives that conversation a new id each time it compresses it, and a subagent
delegated from it runs under an id of its own. Both still belong to the bound
session, so tools and approvals follow the chain back to the bound id instead
of trusting the id alone. Delegated subagents are reported as such so writes
can be kept to the main Agent.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


# A parent link is (parent_session_id, reached_through_a_subagent).
ParentLookup = Callable[[str], "tuple[str, bool] | None"]

_MAX_HOPS = 32
_MAX_REMEMBERED = 2048


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    session_id: str
    delegated: bool


class SessionLineage:
    """Walk compression and subagent links from a session id to a bound one."""

    def __init__(self, parent_lookup: ParentLookup | None = None) -> None:
        self._lookup = parent_lookup
        self._lock = Lock()
        # Hermes announces a subagent before its first turn; its row may not exist yet.
        self._subagent_parents: dict[str, str] = {}
        # A row's parent never changes, so a found link is kept.
        self._known_parents: dict[str, tuple[str, bool]] = {}

    def note_subagent(
        self, *, parent_session_id: Any = "", child_session_id: Any = "", **_ignored: Any
    ) -> None:
        """The ``subagent_start`` hook: remember which session a subagent came from."""

        child = str(child_session_id or "").strip()
        parent = str(parent_session_id or "").strip()
        if not child or not parent or child == parent:
            return
        with self._lock:
            _remember(self._subagent_parents, child, parent)

    def resolve(
        self, session_id: str, is_bound: Callable[[str], bool]
    ) -> ResolvedSession | None:
        """The bound session ``session_id`` belongs to, or None for an ordinary chat."""

        current = str(session_id or "").strip()
        if not current:
            return None
        delegated = False
        seen: set[str] = set()
        for _ in range(_MAX_HOPS):
            if is_bound(current):
                return ResolvedSession(current, delegated)
            seen.add(current)
            link = self._parent(current)
            if link is None or link[0] in seen:
                return None
            current, via_subagent = link
            delegated = delegated or via_subagent
        return None

    def _parent(self, session_id: str) -> tuple[str, bool] | None:
        with self._lock:
            parent = self._subagent_parents.get(session_id)
            if parent is not None:
                return parent, True
            known = self._known_parents.get(session_id)
        if known is not None:
            return known
        if self._lookup is None:
            return None
        try:
            link = self._lookup(session_id)
        except Exception:
            return None
        if link is not None:
            with self._lock:
                _remember(self._known_parents, session_id, link)
        return link


def state_db_parent(hermes_home: Path, session_id: str) -> tuple[str, bool] | None:
    """Read one parent link from the Hermes session database of ``hermes_home``."""

    db_path = Path(hermes_home) / "state.db"
    if not db_path.is_file():
        return None
    from hermes_state_registry import acquire, release

    db = acquire(db_path)
    try:
        return parent_link(db, session_id)
    finally:
        release(db)


def parent_link(db: Any, session_id: str) -> tuple[str, bool] | None:
    """The compression parent or delegating session of one session row.

    Branches, ``/new`` resets and tool children start a conversation of their
    own, so they have no link.
    """

    row = db.get_session(session_id)
    if not row:
        return None
    parent = str(row.get("parent_session_id") or "").strip()
    if not parent:
        return None
    config = _model_config(row)
    if config.get("_delegate_from") == parent:
        return parent, True
    if config.get("_reset_from") == parent or db.is_explicit_fork_child(session_id):
        return None
    parent_row = db.get_session(parent)
    if parent_row and parent_row.get("end_reason") == "compression":
        return parent, False
    return None


def _model_config(row: Any) -> dict[str, Any]:
    config = row.get("model_config")
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError:
            return {}
    return config if isinstance(config, dict) else {}


def _remember(table: dict[str, Any], key: str, value: Any) -> None:
    table.pop(key, None)
    table[key] = value
    while len(table) > _MAX_REMEMBERED:
        table.pop(next(iter(table)))
