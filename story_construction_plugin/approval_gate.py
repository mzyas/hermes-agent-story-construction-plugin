"""Approving a proposal inside the chat, with a risk gate.

``story.apply_edit`` is escalated to Hermes' own human-approval prompt by a
``pre_tool_call`` hook, so the person approves in the conversation like any
other tool. Two things keep that from being the only line of defence:

* The hook cannot be trusted to have run (Hermes lets a failing hook through),
  so it leaves a one-time grant that the tool itself requires. No grant, no
  write: the proposal then has to be approved in the Story panel as before.
* A risky change (clearing a record, removing a lot of text) gets its own
  ``rule_key`` per proposal. Choosing "always allow" on a prompt can therefore
  never skip the review of the next risky change.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

APPLY_TOOL = "story.apply_edit"
GRANT_SECONDS = 600

# A change is risky when it removes this much text, in characters or as a share
# of the record (the share only counts above a floor, so short records are not
# flagged for every small edit).
LARGE_REMOVAL_CHARS = 800
LARGE_REMOVAL_SHARE = 0.3
LARGE_REMOVAL_FLOOR = 100

_MAX_LINES = 6
_MAX_LINE_CHARS = 140
_MAX_NEW_TEXT_CHARS = 300
_CJK = re.compile(r"[㐀-鿿]")

_KIND_ZH = {"chapter": "章节", "character": "角色", "world_entry": "世界设定条目", "note": "笔记"}
_KIND_EN = {"chapter": "chapter", "character": "character", "world_entry": "world entry", "note": "note"}


@dataclass(frozen=True, slots=True)
class Risk:
    level: str  # "normal" or "high"
    reasons: tuple[str, ...]
    removed: int
    total: int

    @property
    def high(self) -> bool:
        return self.level == "high"


NORMAL = Risk("normal", (), 0, 0)


def assess_risk(proposal: Mapping[str, Any], base_text: str) -> Risk:
    """How careful the person has to be about this proposal.

    Deleting a record is always high risk. Otherwise only edits to an existing
    record can lose text; a new record or a new name is normal. ``removed``
    counts the characters the diff deletes (a rewrite deletes what it
    replaces), so rewriting most of a record is flagged like deleting it.
    """

    if proposal.get("kind") == "delete":
        return Risk("high", ("deletes_record",), len(base_text), len(base_text))
    if proposal.get("kind") != "edit":
        return NORMAL
    removed = 0
    for preview in proposal.get("previews") or ():
        for region in preview.get("regions") or ():
            for part in region.get("inline") or ():
                if part.get("op") == "delete":
                    removed += len(part.get("text") or "")
    total = len(base_text)
    reasons: list[str] = []
    if not str(proposal.get("result_text") or "").strip():
        reasons.append("clears_record")
    if removed >= LARGE_REMOVAL_CHARS or (
        removed >= LARGE_REMOVAL_FLOOR and total and removed / total >= LARGE_REMOVAL_SHARE
    ):
        reasons.append("large_removal")
    return Risk("high" if reasons else "normal", tuple(reasons), removed, total)


class SessionGrants:
    """Proposals whose approval prompt was just raised by the hook, once each."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._expires: dict[str, float] = {}

    def grant(self, proposal_id: str) -> None:
        with self._lock:
            now = self._clock()
            self._expires = {key: end for key, end in self._expires.items() if end > now}
            self._expires[proposal_id] = now + GRANT_SECONDS

    def revoke(self, proposal_id: str) -> None:
        with self._lock:
            self._expires.pop(proposal_id, None)

    def consume(self, proposal_id: str) -> bool:
        with self._lock:
            end = self._expires.pop(proposal_id, None)
        return end is not None and end > self._clock()


def rule_key(proposal_id: str, risk: Risk) -> str:
    """Normal changes share one key (so "always" can cover them); risky ones never do."""

    return f"story.apply:{proposal_id}" if risk.high else "story.apply"


def approval_message(proposal: Mapping[str, Any], risk: Risk) -> str:
    """What the person is asked to approve: the record, the risk, and the change."""

    title = str(proposal.get("target_title") or proposal.get("chapter_title") or proposal.get("title") or "")
    result = str(proposal.get("result_text") or "")
    new_title = str(proposal.get("new_title") or "")
    # The prompt follows the language of the text being written. Titles alone do
    # not decide it: a project's default titles ("第一章") must not turn the prompt
    # Chinese for an English story. Only a change with no text (rename, delete)
    # falls back to the titles.
    zh = bool(_CJK.search(result if result.strip() else title + new_title))
    kind = str(proposal.get("target_type") or "chapter")
    action = str(proposal.get("kind") or "")
    is_new = action.startswith("new_")
    if action == "rename":
        head = f"重命名{_KIND_ZH.get(kind, kind)}「{title}」→「{new_title}」" if zh else (
            f"Rename {_KIND_EN.get(kind, kind)}: {title} -> {new_title}")
    elif action == "delete":
        head = f"删除{_KIND_ZH.get(kind, kind)}「{title}」" if zh else f"Delete {_KIND_EN.get(kind, kind)}: {title}"
    elif zh:
        head = f"{'新建' if is_new else '修改'}{_KIND_ZH.get(kind, kind)}「{title}」"
    else:
        head = f"{'New' if is_new else 'Edit'} {_KIND_EN.get(kind, kind)}: {title}"
    lines = [head]
    if risk.high:
        lines.append(_risk_line(risk, zh))
    lines.extend(_change_lines(proposal, result, is_new, zh))
    lines.append("完整差异可在 Story 面板查看。" if zh else "The full diff is in the Story panel.")
    return "\n".join(lines)


def _risk_line(risk: Risk, zh: bool) -> str:
    parts = []
    for reason in risk.reasons:
        if reason == "deletes_record":
            parts.append(
                f"会删除这条记录（约 {risk.total} 字，移入回收站，可撤销）" if zh
                else f"deletes the record (about {risk.total} characters; moved to the trash, can be undone)"
            )
        elif reason == "clears_record":
            parts.append("会清空整条记录" if zh else "clears the whole record")
        elif reason == "large_removal":
            share = round(100 * risk.removed / risk.total) if risk.total else 100
            parts.append(
                f"会删掉约 {risk.removed} 字（约 {share}%）" if zh else f"removes about {risk.removed} characters ({share}%)"
            )
    prefix = "高风险：" if zh else "High risk: "
    suffix = "。每次都需要你确认，不能被“总是允许”跳过。" if zh else ". Needs your review every time; \"always allow\" does not cover it."
    return prefix + ("；" if zh else "; ").join(parts) + suffix


def _change_lines(proposal: Mapping[str, Any], result: str, is_new: bool, zh: bool) -> list[str]:
    if proposal.get("kind") in ("rename", "delete"):
        return []
    if is_new:
        shown = _clip(result, _MAX_NEW_TEXT_CHARS)
        return [f"+ {shown}"] if shown else []
    regions = [
        region for preview in proposal.get("previews") or () for region in preview.get("regions") or ()
    ]
    lines: list[str] = []
    shown = 0
    for region in regions:
        pair = []
        if region.get("old"):
            pair.append("- " + _clip(str(region["old"]), _MAX_LINE_CHARS))
        if region.get("new"):
            pair.append("+ " + _clip(str(region["new"]), _MAX_LINE_CHARS))
        if lines and len(lines) + len(pair) > _MAX_LINES:
            break
        lines.extend(pair)
        shown += 1
    if shown < len(regions):
        more = len(regions) - shown
        lines.append(f"…另有 {more} 处改动" if zh else f"… and {more} more changes")
    return lines


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def make_apply_hook(
    resolve: Callable[[str], tuple[Any, Any] | None], grants: SessionGrants
) -> Callable[..., Mapping[str, Any] | None]:
    """The ``pre_tool_call`` hook that sends ``story.apply_edit`` to the person.

    ``resolve(session_id)`` returns ``(proposal_service, bound_scope)`` for a
    bound Story session, or ``None``. Anything unexpected returns ``None`` (no
    directive) and leaves no grant, so the tool then refuses to write.
    """

    def hook(*, tool_name: str = "", args: Mapping[str, Any] | None = None, session_id: str = "", **_ignored: Any):
        if tool_name != APPLY_TOOL:
            return None
        try:
            return _directive(resolve, grants, args or {}, session_id)
        except Exception:
            return None

    return hook


def _directive(
    resolve: Callable[[str], tuple[Any, Any] | None],
    grants: SessionGrants,
    args: Mapping[str, Any],
    session_id: str,
) -> Mapping[str, Any] | None:
    proposal_id = str(args.get("proposal_id") or "").strip()
    resolved = resolve(session_id) if proposal_id and session_id else None
    if resolved is None:
        return None
    service, scope = resolved
    grants.revoke(proposal_id)
    proposal = service.store.get(proposal_id)
    if (
        proposal is None
        or proposal["project_id"] != scope.project_id
        or proposal["profile"] != scope.profile
        or proposal["connection_id"] != scope.connection_id
        # Approved in the Story panel already, or closed: apply_edit decides.
        or proposal["status"] not in ("pending", "expired")
    ):
        return None
    risk = service.assess(project_id=scope.project_id, proposal=proposal)
    grants.grant(proposal_id)
    return {
        "action": "approve",
        "message": approval_message(proposal, risk),
        "rule_key": rule_key(proposal_id, risk),
    }
