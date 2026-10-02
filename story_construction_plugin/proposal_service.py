"""Chapter proposals: the Agent proposes, the person approves, the Agent applies.

Three things keep the Agent from writing anything the person did not see:

* ``propose_*`` only stores a proposal; no chapter file is touched.
* An approval can only be created through the Desktop methods below, which the
  Agent's tools never call.
* ``apply`` takes just a proposal id. It writes what the approval covers (the
  approved edits, or the text the person edited) and nothing else, within 15
  minutes of the approval.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any

from .edits import (
    Edit,
    EditError,
    apply_edits,
    build_previews,
    check_edits,
    clean_body,
    edits_digest,
    normalize_newlines,
    parse_edits,
    text_digest,
)
from .proposal_store import ChapterHistory, ProposalStore
from .repository import NotFoundError, RepositoryError, StoryRepository, VersionConflictError

MAX_TITLE = 120
_STATUS_ERRORS = {
    "pending": ("not_approved", "the user has not approved this proposal yet"),
    "expired": ("approval_expired", "the approval ran out; ask the user to approve again"),
    "applied": ("already_applied", "this proposal was already written"),
    "discarded": ("proposal_closed", "the user discarded this proposal"),
    "superseded": ("proposal_closed", "a newer proposal replaced this one"),
}


class ProposalError(RuntimeError):
    """A proposal request that cannot proceed; ``code`` is stable for callers."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), **self.details}


class StoryProposalService:
    def __init__(
        self, repository: StoryRepository, store: ProposalStore, history: ChapterHistory
    ) -> None:
        self.repository = repository
        self.store = store
        self.history = history

    # ----------------------------------------------------------- the Agent
    def propose_edit(
        self,
        *,
        project_id: str,
        session_id: str,
        profile: str,
        connection_id: str,
        chapter_id: str,
        base_version: str,
        raw_edits: object,
    ) -> dict[str, Any]:
        chapter = self.repository.get_chapter(project_id, chapter_id)
        if not isinstance(base_version, str) or base_version.strip() != chapter.version:
            raise ProposalError(
                "version_changed",
                "the chapter changed since it was read; read it again and propose against the new version",
                current_version=chapter.version,
            )
        edits, warnings = check_edits(parse_edits(raw_edits), title=chapter.title)
        base = normalize_newlines(chapter.content)
        result = apply_edits(base, edits)
        if result == base:
            raise ProposalError("no_change", "these edits would not change the chapter")
        proposal = self.store.create({
            "project_id": project_id,
            "profile": profile,
            "connection_id": connection_id,
            "session_id": session_id,
            "kind": "edit",
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "base_version": chapter.version,
            "edits": [edit.as_dict() for edit in edits],
            "result_text": result,
            "previews": build_previews(base, edits),
            "warnings": [warning.as_dict() for warning in warnings],
        })
        return _agent_summary(proposal)

    def propose_chapter(
        self,
        *,
        project_id: str,
        session_id: str,
        profile: str,
        connection_id: str,
        volume_id: str,
        title: str,
        content: str,
    ) -> dict[str, Any]:
        clean_title = _title(title)
        tree = self.repository.get_project(project_id)
        if volume_id not in {volume.id for volume in tree.volumes}:
            raise NotFoundError(f"volume {volume_id!r} was not found")
        if not isinstance(content, str) or not content.strip():
            raise ProposalError("empty_content", "content must not be empty")
        body, found = clean_body(content, title=clean_title)
        edits = (Edit(op="rewrite", content=body),)
        proposal = self.store.create({
            "project_id": project_id,
            "profile": profile,
            "connection_id": connection_id,
            "session_id": session_id,
            "kind": "new_chapter",
            "chapter_id": None,
            "volume_id": volume_id,
            "title": clean_title,
            "chapter_title": clean_title,
            "base_version": "",
            "edits": [edit.as_dict() for edit in edits],
            "result_text": body,
            "previews": build_previews("", edits),
            "warnings": [warning.as_dict() for warning in found],
        })
        return _agent_summary(proposal)

    def apply(self, *, project_id: str, proposal_id: str, profile: str, connection_id: str) -> dict[str, Any]:
        proposal = self._owned(project_id, proposal_id, profile, connection_id)
        if proposal["status"] != "approved":
            code, message = _STATUS_ERRORS.get(proposal["status"], ("proposal_closed", "this proposal cannot be applied"))
            raise ProposalError(code, message, status=proposal["status"])
        approval = proposal["approval"]
        mode = approval["mode"]
        if mode == "edits":
            selected = [Edit(**edit) for edit in _selected(proposal, approval["selected"])]
            if edits_digest(selected) != approval["digest"]:
                raise ProposalError("approval_mismatch", "the approved content no longer matches this proposal")
        elif mode == "text":
            if text_digest(approval["text"]) != approval["digest"]:
                raise ProposalError("approval_mismatch", "the approved content no longer matches this proposal")
        else:
            raise ProposalError("approval_mismatch", "unknown approval")

        if proposal["kind"] == "new_chapter":
            text = approval["text"] if mode == "text" else apply_edits("", selected)
            chapter = self.repository.create_chapter(
                project_id, proposal["volume_id"], proposal["title"], text
            )
            self.store.mark_applied(proposal_id, {
                "chapter_id": chapter.id, "version_after": chapter.version, "snapshot_id": None,
            })
            return {"status": "applied", "chapter_id": chapter.id, "version": chapter.version}

        chapter = self.repository.get_chapter(project_id, proposal["chapter_id"])
        try:
            if mode == "edits":
                result = apply_edits(chapter.content, selected)
            else:
                if chapter.version != approval["base_version"]:
                    raise ProposalError(
                        "version_changed",
                        "the chapter changed after the user edited the text; ask them to approve again",
                        current_version=chapter.version,
                    )
                result = normalize_newlines(approval["text"])
        except EditError as exc:
            raise _conflict(
                "the chapter changed and an approved edit no longer matches; propose it again", exc
            ) from exc
        snapshot_id = self.history.save(
            project_id=project_id,
            chapter_id=chapter.id,
            text=chapter.content,
            version=chapter.version,
            proposal_id=proposal_id,
        )
        try:
            saved = self.repository.save_chapter(
                project_id, chapter.id, result, expected_version=chapter.version
            )
        except VersionConflictError as exc:
            raise ProposalError(
                "version_changed", "the chapter changed while it was being saved", current_version=""
            ) from exc
        self.store.mark_applied(proposal_id, {
            "chapter_id": chapter.id,
            "version_before": chapter.version,
            "version_after": saved.version,
            "snapshot_id": snapshot_id,
        })
        return {"status": "applied", "chapter_id": chapter.id, "version": saved.version}

    # ---------------------------------------------------------- the Desktop
    def list_open(self, *, project_id: str, profile: str, connection_id: str) -> list[dict[str, Any]]:
        views = []
        for row in self.store.list_for_project(
            project_id=project_id, profile=profile, connection_id=connection_id
        ):
            view = _desktop_view(row)
            # The chapter's version right now, so the Desktop can tell a proposal
            # written against an older text and can approve a hand edit against it.
            view["current_version"] = None
            if row["kind"] == "edit":
                try:
                    view["current_version"] = self.repository.get_chapter(
                        project_id, row["chapter_id"]
                    ).version
                except (NotFoundError, RepositoryError):
                    pass
            views.append(view)
        return views

    def approve(
        self,
        *,
        project_id: str,
        proposal_id: str,
        profile: str,
        connection_id: str,
        selected: Sequence[int] | None = None,
        text: str | None = None,
        base_version: str | None = None,
    ) -> dict[str, Any]:
        proposal = self._owned(project_id, proposal_id, profile, connection_id)
        # An expired approval can be given again.
        if proposal["status"] not in ("pending", "approved", "expired"):
            code, message = _STATUS_ERRORS.get(proposal["status"], ("proposal_closed", "this proposal is closed"))
            raise ProposalError(code, message, status=proposal["status"])
        if text is not None:
            approval = self._approve_text(proposal, project_id, text, base_version)
        else:
            approval = self._approve_edits(proposal, project_id, selected)
        stored = self.store.approve(proposal_id, approval)
        if stored is None:
            raise NotFoundError(f"proposal {proposal_id!r} was not found")
        return _desktop_view(stored)

    def revoke(self, *, project_id: str, proposal_id: str, profile: str, connection_id: str) -> dict[str, Any]:
        self._owned(project_id, proposal_id, profile, connection_id)
        stored = self.store.revoke(proposal_id)
        return _desktop_view(stored)

    def discard(self, *, project_id: str, proposal_id: str, profile: str, connection_id: str) -> dict[str, Any]:
        self._owned(project_id, proposal_id, profile, connection_id)
        stored = self.store.discard(proposal_id)
        return _desktop_view(stored)

    def undo(self, *, project_id: str, chapter_id: str) -> dict[str, Any]:
        applied = self.store.latest_applied(project_id=project_id, chapter_id=chapter_id)
        if applied is None:
            raise ProposalError("nothing_to_undo", "there is no Agent write to undo for this chapter")
        info = applied["applied"]
        if not info.get("snapshot_id"):
            raise ProposalError(
                "undo_unsupported",
                "a chapter the Agent created cannot be undone here; delete it by hand if you do not want it",
            )
        chapter = self.repository.get_chapter(project_id, chapter_id)
        if chapter.version != info["version_after"]:
            raise ProposalError(
                "chapter_changed",
                "the chapter was edited after the Agent's write, so it cannot be undone safely",
                current_version=chapter.version,
            )
        snapshot = self.history.load(
            project_id=project_id, chapter_id=chapter_id, snapshot_id=info.get("snapshot_id") or ""
        )
        if snapshot is None:
            raise ProposalError("snapshot_missing", "the saved copy of the earlier text is gone")
        try:
            restored = self.repository.save_chapter(
                project_id, chapter_id, snapshot["text"], expected_version=chapter.version
            )
        except VersionConflictError as exc:
            raise ProposalError("chapter_changed", "the chapter changed while it was being restored") from exc
        self.store.mark_undone(applied["id"])
        return {"chapter_id": chapter_id, "version": restored.version}

    def writes(self, *, project_id: str) -> list[dict[str, Any]]:
        return [
            {
                "proposal_id": row["id"],
                "chapter_id": row["applied"].get("chapter_id"),
                "chapter_title": row.get("chapter_title"),
                "at": row["applied"]["at"],
                "undone": bool(row["applied"].get("undone_at")),
                "kind": row["kind"],
            }
            for row in self.store.recent_applied(project_id=project_id)
        ]

    # ------------------------------------------------------------ internals
    def _owned(self, project_id: str, proposal_id: str, profile: str, connection_id: str) -> dict[str, Any]:
        proposal = self.store.get(proposal_id) if isinstance(proposal_id, str) else None
        if (
            proposal is None
            or proposal["project_id"] != project_id
            or proposal["profile"] != profile
            or proposal["connection_id"] != connection_id
        ):
            raise NotFoundError(f"proposal {proposal_id!r} was not found")
        return proposal

    def _approve_edits(
        self, proposal: dict[str, Any], project_id: str, selected: Sequence[int] | None
    ) -> dict[str, Any]:
        edits = proposal["edits"]
        chosen = list(range(len(edits))) if selected is None else sorted(set(selected))
        if not chosen or any(not isinstance(i, int) or i < 0 or i >= len(edits) for i in chosen):
            raise ProposalError("invalid_selection", "select at least one of this proposal's edits")
        picked = [Edit(**edits[i]) for i in chosen]
        if proposal["kind"] == "new_chapter":
            base = ""
        else:
            base = self.repository.get_chapter(project_id, proposal["chapter_id"]).content
        try:
            result = apply_edits(base, picked)
        except EditError as exc:
            raise _conflict("an edit no longer matches the chapter", exc) from exc
        if result == normalize_newlines(base):
            raise ProposalError("no_change", "the selected edits would not change the chapter")
        return {"mode": "edits", "selected": chosen, "digest": edits_digest(picked)}

    def _approve_text(
        self, proposal: dict[str, Any], project_id: str, text: str, base_version: str | None
    ) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ProposalError("empty_content", "the text must not be empty")
        try:
            body, _warnings = clean_body(text, title=proposal.get("chapter_title"))
        except EditError as exc:
            raise ProposalError(exc.code, str(exc)) from exc
        if proposal["kind"] == "new_chapter":
            version = ""
        else:
            chapter = self.repository.get_chapter(project_id, proposal["chapter_id"])
            if base_version != chapter.version:
                raise ProposalError(
                    "version_changed",
                    "the chapter changed since the text was edited",
                    current_version=chapter.version,
                )
            if normalize_newlines(chapter.content) == normalize_newlines(body):
                raise ProposalError("no_change", "the text is the same as the chapter")
            version = chapter.version
        return {"mode": "text", "text": body, "base_version": version, "digest": text_digest(body)}


def _conflict(message: str, cause: EditError) -> ProposalError:
    extra = {key: value for key, value in cause.as_dict().items() if key not in ("code", "message")}
    return ProposalError("conflict", message, reason=cause.code, **extra)


def _selected(proposal: dict[str, Any], indexes: Sequence[int]) -> list[dict[str, str]]:
    edits = proposal["edits"]
    return [edits[i] for i in indexes if isinstance(i, int) and 0 <= i < len(edits)]


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise ProposalError("invalid_title", "title must be a string")
    title = unicodedata.normalize("NFKC", value).strip()
    if not title or len(title) > MAX_TITLE or any(ord(ch) < 32 for ch in title):
        raise ProposalError("invalid_title", f"title must be 1-{MAX_TITLE} characters without control characters")
    return title


def _agent_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": proposal["id"],
        "status": proposal["status"],
        "kind": proposal["kind"],
        "chapter_id": proposal.get("chapter_id"),
        "edits": len(proposal["edits"]),
        "warnings": proposal["warnings"],
        "next": (
            "Nothing is written yet. Tell the user to review this proposal in the Story "
            "panel and approve it. After they say it is approved, call story.apply_edit "
            "with this proposal_id."
        ),
    }


def _desktop_view(proposal: dict[str, Any] | None) -> dict[str, Any]:
    if proposal is None:
        raise NotFoundError("proposal was not found")
    approval = proposal.get("approval")
    return {
        "id": proposal["id"],
        "status": proposal["status"],
        "kind": proposal["kind"],
        "chapter_id": proposal.get("chapter_id"),
        "volume_id": proposal.get("volume_id"),
        "title": proposal.get("title"),
        "chapter_title": proposal.get("chapter_title"),
        "base_version": proposal["base_version"],
        "edits": proposal["edits"],
        "previews": proposal["previews"],
        "warnings": proposal["warnings"],
        "result_text": proposal["result_text"],
        "created_at": proposal["created_at"],
        "approval": (
            {
                "mode": approval["mode"],
                "selected": approval.get("selected"),
                "approved_at": approval["approved_at"],
                "expires_at": approval["expires_at"],
            }
            if approval
            else None
        ),
    }
