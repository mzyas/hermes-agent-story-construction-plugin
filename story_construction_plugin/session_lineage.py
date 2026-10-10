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
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


logger = logging.getLogger(__name__)

# A parent link is (parent_session_id, reached_through_a_subagent). A lookup
# returns every link it found walking up from one session, keyed by child id.
ParentLink = tuple[str, bool]
AncestryLookup = Callable[[str], Mapping[str, ParentLink]]

# Real compression chains run about 180 deep; Hermes caps its own walk at 1000
# for the same reason (hermes_state_compression._CHAIN_CAP).
_MAX_HOPS = 1000
_MAX_REMEMBERED = 4096


@dataclass(frozen=True, slots=True)
class ResolvedSession:
    session_id: str
    delegated: bool


class SessionLineage:
    """Walk compression and subagent links from a session id to a bound one."""

    def __init__(self, ancestry_lookup: AncestryLookup | None = None) -> None:
        self._lookup = ancestry_lookup
        self._lock = Lock()
        # Hermes announces a subagent before its first turn; its row may not exist yet.
        self._subagent_parents: dict[str, str] = {}
        # Found links are kept for the life of the process. Hermes clears a
        # parent link only when it deletes or prunes the parent; a session that
        # outlives a deleted bound parent keeps resolving to it until a restart.
        self._known_parents: dict[str, ParentLink] = {}

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

    def _parent(self, session_id: str) -> ParentLink | None:
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
            links = self._lookup(session_id)
        except Exception:
            logger.debug("Story session lineage lookup failed for %s", session_id, exc_info=True)
            return None
        with self._lock:
            for child, link in links.items():
                _remember(self._known_parents, child, link)
        return links.get(session_id)


def state_db_ancestry(hermes_home: Path, session_id: str) -> dict[str, ParentLink]:
    """Every parent link above ``session_id`` in the Hermes session database.

    One database handle serves the whole walk and each row is read once.
    """

    db_path = Path(hermes_home) / "state.db"
    if not db_path.is_file():
        return {}
    from hermes_state_registry import acquire, release_or_close

    db = acquire(db_path)
    try:
        return ancestry(db, session_id)
    finally:
        release_or_close(db)


def ancestry(db: Any, session_id: str) -> dict[str, ParentLink]:
    links: dict[str, ParentLink] = {}
    row = db.get_session(session_id)
    while row and len(links) < _MAX_HOPS:
        child = str(row.get("id") or "")
        found = _row_link(db, row)
        if not child or found is None:
            break
        parent, via_subagent, parent_row = found
        if parent in links or parent == session_id:
            break
        links[child] = (parent, via_subagent)
        row = parent_row
    return links


def parent_link(db: Any, session_id: str) -> ParentLink | None:
    """The compression parent or delegating session of one session row.

    Branches, ``/new`` resets and tool children start a conversation of their
    own, so they have no link.
    """

    row = db.get_session(session_id)
    found = _row_link(db, row) if row else None
    return None if found is None else found[:2]


def _row_link(db: Any, row: Mapping[str, Any]) -> tuple[str, bool, Any] | None:
    parent = str(row.get("parent_session_id") or "").strip()
    if not parent:
        return None
    config = _model_config(row)
    if config.get("_delegate_from") == parent:
        return parent, True, db.get_session(parent)
    if _starts_own_conversation(row, config, parent):
        return None
    parent_row = db.get_session(parent)
    if parent_row and parent_row.get("end_reason") == "compression":
        return parent, False, parent_row
    return None


def _starts_own_conversation(row: Mapping[str, Any], config: Mapping[str, Any], parent: str) -> bool:
    # Mirrors Hermes' _is_explicit_fork_child_row(include_reset=True): a tool
    # child, or a branch, delegate or reset marker pointing at this parent.
    if row.get("source") == "tool":
        return True
    markers = (config.get("_branched_from"), config.get("_delegate_from"), config.get("_reset_from"))
    return parent in markers


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
