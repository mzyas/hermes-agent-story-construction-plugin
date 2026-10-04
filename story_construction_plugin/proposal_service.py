"""Proposals: the Agent proposes, the person approves, the Agent applies.

A proposal targets one record: a chapter, a character, a world info entry or a
note. Three things keep the Agent from writing anything the person did not see:

* ``propose_*`` only stores a proposal; no file is touched.
* An approval can only be created through the Desktop methods below, which the
  Agent's tools never call.
* ``apply`` takes just a proposal id. It writes what the approval covers (the
  approved edits, or the text the person edited) and nothing else, within 15
  minutes of the approval.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .approval_gate import Risk, assess_risk
from .edits import (
    BodyWarning,
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
# Proposals that act on a whole record instead of its text.
ACTION_KINDS = ("rename", "delete")
TARGET_TYPES = ("chapter", "character", "world_entry", "note")
_LABELS = {
    "chapter": "chapter",
    "character": "character",
    "world_entry": "world entry",
    "note": "note",
}
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


@dataclass(frozen=True, slots=True)
class _Doc:
    """The part of any record a proposal needs: its text and where it stands."""

    id: str
    title: str
    content: str
    version: str
    read_only: bool = False


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
        base_version: str,
        raw_edits: object,
        target_type: str = "chapter",
        target_id: str | None = None,
        chapter_id: str | None = None,
    ) -> dict[str, Any]:
        target_type = _target_type(target_type)
        label = _LABELS[target_type]
        doc = self._doc(
            project_id, target_type, self.resolve_target(project_id, target_type, target_id or chapter_id)
        )
        if doc.read_only:
            raise ProposalError(
                "read_only", f"this {label} is a reference and cannot be changed by the Agent"
            )
        if not isinstance(base_version, str) or base_version.strip() != doc.version:
            raise ProposalError(
                "version_changed",
                f"the {label} changed since it was read; read it again and propose against the new version",
                current_version=doc.version,
            )
        edits, warnings = check_edits(parse_edits(raw_edits), title=doc.title)
        base = normalize_newlines(doc.content)
        result = apply_edits(base, edits)
        if result == base:
            raise ProposalError("no_change", f"these edits would not change the {label}")
        proposal = self.store.create({
            "project_id": project_id,
            "profile": profile,
            "connection_id": connection_id,
            "session_id": session_id,
            "kind": "edit",
            **_identity(target_type, doc.id, doc.title),
            "base_version": doc.version,
            "edits": [edit.as_dict() for edit in edits],
            "result_text": result,
            "previews": build_previews(base, edits),
            "warnings": [warning.as_dict() for warning in warnings],
        })
        return _agent_summary(proposal)

    def propose_new(
        self,
        *,
        project_id: str,
        session_id: str,
        profile: str,
        connection_id: str,
        title: str,
        content: str,
        target_type: str = "chapter",
        volume_id: str | None = None,
        category_id: str | None = None,
    ) -> dict[str, Any]:
        target_type = _target_type(target_type)
        clean_title = _title(title)
        tree = self.repository.get_project(project_id)
        extra: dict[str, Any] = {}
        warnings: list[BodyWarning] = []
        if target_type == "chapter":
            if not volume_id:
                raise ProposalError("invalid_request", "volume_id is required for a new chapter")
            if volume_id not in {volume.id for volume in tree.volumes}:
                raise NotFoundError(f"volume {volume_id!r} was not found")
            extra["volume_id"] = volume_id
        elif target_type == "world_entry" and tree.world_info is None:
            raise ProposalError("no_world_info", "this project has no world info to add an entry to")
        elif target_type == "note" and category_id:
            if category_id not in {category.id for category in tree.categories}:
                raise NotFoundError(f"note category {category_id!r} was not found")
            extra["category_id"] = category_id
        if not isinstance(content, str) or not content.strip():
            raise ProposalError("empty_content", "content must not be empty")
        body, found = clean_body(content, title=clean_title)
        warnings.extend(found)
        taken = _taken_titles(tree, target_type, category_id)
        if clean_title.casefold() in taken:
            # Several chapters may share a title; any other record should not.
            if target_type != "chapter":
                warnings.append(BodyWarning(edit=0, kind="name_in_use", text=taken[clean_title.casefold()]))
        edits = (Edit(op="rewrite", content=body),)
        proposal = self.store.create({
            "project_id": project_id,
            "profile": profile,
            "connection_id": connection_id,
            "session_id": session_id,
            "kind": "new_chapter" if target_type == "chapter" else "new_record",
            **_identity(target_type, None, clean_title),
            **extra,
            "title": clean_title,
            "base_version": "",
            "edits": [edit.as_dict() for edit in edits],
            "result_text": body,
            "previews": build_previews("", edits),
            "warnings": [warning.as_dict() for warning in warnings],
        })
        return _agent_summary(proposal)

    def propose_rename(
        self,
        *,
        project_id: str,
        session_id: str,
        profile: str,
        connection_id: str,
        target_type: str,
        target_id: str,
        new_title: str,
    ) -> dict[str, Any]:
        target_type = _target_type(target_type)
        label = _LABELS[target_type]
        doc = self._doc(project_id, target_type, self.resolve_target(project_id, target_type, target_id))
        if doc.read_only:
            raise ProposalError("read_only", f"this {label} is a reference and cannot be changed by the Agent")
        title = _title(new_title)
        if title == doc.title:
            raise ProposalError("no_change", f"the {label} already has this name")
        warnings: list[BodyWarning] = []
        if target_type != "chapter":
            tree = self.repository.get_project(project_id)
            category = next((n.category_id for n in tree.notes if n.id == doc.id), None) if target_type == "note" else None
            taken = _taken_titles(tree, target_type, category)
            taken.pop(doc.title.casefold(), None)
            if title.casefold() in taken:
                warnings.append(BodyWarning(edit=0, kind="name_in_use", text=taken[title.casefold()]))
        proposal = self.store.create({
            "project_id": project_id,
            "profile": profile,
            "connection_id": connection_id,
            "session_id": session_id,
            "kind": "rename",
            **_identity(target_type, doc.id, doc.title),
            "new_title": title,
            "base_version": doc.version,
            "edits": [],
            "result_text": "",
            "previews": [],
            "warnings": [warning.as_dict() for warning in warnings],
        })
        return _agent_summary(proposal)

    def propose_delete(
        self,
        *,
        project_id: str,
        session_id: str,
        profile: str,
        connection_id: str,
        target_type: str,
        target_id: str,
    ) -> dict[str, Any]:
        target_type = _target_type(target_type)
        label = _LABELS[target_type]
        if target_type == "chapter":
            raise ProposalError("unsupported", "the Agent cannot delete chapters; ask the user to do it")
        doc = self._doc(project_id, target_type, self.resolve_target(project_id, target_type, target_id))
        if doc.read_only:
            raise ProposalError("read_only", f"this {label} is a reference and cannot be changed by the Agent")
        proposal = self.store.create({
            "project_id": project_id,
            "profile": profile,
            "connection_id": connection_id,
            "session_id": session_id,
            "kind": "delete",
            **_identity(target_type, doc.id, doc.title),
            "base_version": doc.version,
            "edits": [],
            "result_text": "",
            "previews": [],
            "warnings": [],
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
        return self.propose_new(
            project_id=project_id, session_id=session_id, profile=profile,
            connection_id=connection_id, title=title, content=content,
            target_type="chapter", volume_id=volume_id,
        )

    def apply(self, *, project_id: str, proposal_id: str, profile: str, connection_id: str) -> dict[str, Any]:
        proposal = self._owned(project_id, proposal_id, profile, connection_id)
        if proposal["status"] != "approved":
            code, message = _STATUS_ERRORS.get(proposal["status"], ("proposal_closed", "this proposal cannot be applied"))
            raise ProposalError(code, message, status=proposal["status"])
        if proposal["kind"] in ACTION_KINDS:
            return self._apply_action(project_id, proposal_id, proposal)
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

        target_type = _proposal_type(proposal)
        label = _LABELS[target_type]
        if _is_new(proposal):
            text = approval["text"] if mode == "text" else apply_edits("", selected)
            created = self._create(project_id, target_type, proposal, text)
            self.store.mark_applied(proposal_id, {
                **_written(target_type, created.id),
                "title": created.title,
                "version_after": created.version,
                "snapshot_id": None,
            })
            return {"status": "applied", "title": created.title, "version": created.version,
                    **_written(target_type, created.id)}

        doc = self._doc(project_id, target_type, proposal["target_id"])
        if doc.read_only:
            raise ProposalError("read_only", f"this {label} is a reference and cannot be changed by the Agent")
        try:
            if mode == "edits":
                result = apply_edits(doc.content, selected)
            else:
                if doc.version != approval["base_version"]:
                    raise ProposalError(
                        "version_changed",
                        f"the {label} changed after the user edited the text; ask them to approve again",
                        current_version=doc.version,
                    )
                result = normalize_newlines(approval["text"])
        except EditError as exc:
            raise _conflict(
                f"the {label} changed and an approved edit no longer matches; propose it again", exc
            ) from exc
        snapshot_id = self.history.save(
            project_id=project_id,
            target_id=_history_key(target_type, doc.id),
            text=doc.content,
            version=doc.version,
            proposal_id=proposal_id,
        )
        try:
            saved = self._save(project_id, target_type, doc.id, result, doc.version)
        except VersionConflictError as exc:
            raise ProposalError(
                "version_changed", f"the {label} changed while it was being saved", current_version=""
            ) from exc
        self.store.mark_applied(proposal_id, {
            **_written(target_type, doc.id),
            "version_before": doc.version,
            "version_after": saved.version,
            "snapshot_id": snapshot_id,
        })
        return {"status": "applied", "version": saved.version, **_written(target_type, doc.id)}

    # ---------------------------------------------------------- the Desktop
    def list_open(self, *, project_id: str, profile: str, connection_id: str) -> list[dict[str, Any]]:
        views = []
        for row in self.store.list_for_project(
            project_id=project_id, profile=profile, connection_id=connection_id
        ):
            view = _desktop_view(row)
            # The record's version right now, so the Desktop can tell a proposal
            # written against an older text and can approve a hand edit against it.
            view["current_version"] = None
            if row["kind"] == "edit" or row["kind"] in ACTION_KINDS:
                try:
                    view["current_version"] = self._doc(
                        project_id, _proposal_type(row), row.get("target_id") or row["chapter_id"]
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
        via: str | None = None,
    ) -> dict[str, Any]:
        proposal = self._owned(project_id, proposal_id, profile, connection_id)
        # An expired approval can be given again.
        if proposal["status"] not in ("pending", "approved", "expired"):
            code, message = _STATUS_ERRORS.get(proposal["status"], ("proposal_closed", "this proposal is closed"))
            raise ProposalError(code, message, status=proposal["status"])
        if proposal["kind"] in ACTION_KINDS:
            if text is not None or selected is not None:
                raise ProposalError("invalid_request", "this proposal has no edits to choose or change; approve or discard it")
            approval = self._approve_action(proposal, project_id)
        elif text is not None:
            approval = self._approve_text(proposal, project_id, text, base_version)
        else:
            approval = self._approve_edits(proposal, project_id, selected)
        if via:
            approval = {**approval, "via": via}
        stored = self.store.approve(proposal_id, approval)
        if stored is None:
            raise NotFoundError(f"proposal {proposal_id!r} was not found")
        return _desktop_view(stored)

    def assess(self, *, project_id: str, proposal: dict[str, Any]) -> Risk:
        """How risky applying this proposal is, against the record as it is now."""

        base = ""
        if proposal["kind"] in ("edit", "delete"):
            base = normalize_newlines(
                self._doc(project_id, _proposal_type(proposal), proposal["target_id"]).content
            )
        return assess_risk(proposal, base)

    def discard(self, *, project_id: str, proposal_id: str, profile: str, connection_id: str) -> dict[str, Any]:
        self._owned(project_id, proposal_id, profile, connection_id)
        stored = self.store.discard(proposal_id)
        return _desktop_view(stored)

    def undo(
        self,
        *,
        project_id: str,
        target_id: str | None = None,
        target_type: str = "chapter",
        chapter_id: str | None = None,
    ) -> dict[str, Any]:
        target_type = _target_type(target_type)
        label = _LABELS[target_type]
        target_id = target_id or chapter_id or ""
        applied = self.store.latest_applied(project_id=project_id, target_id=target_id, target_type=target_type)
        if applied is None:
            raise ProposalError("nothing_to_undo", f"there is no Agent write to undo for this {label}")
        info = applied["applied"]
        if applied["kind"] in ACTION_KINDS:
            return self._undo_action(project_id, target_type, target_id, applied)
        if not info.get("snapshot_id"):
            raise ProposalError(
                "undo_unsupported",
                f"a {label} the Agent created cannot be undone here; delete it by hand if you do not want it",
            )
        doc = self._doc(project_id, target_type, target_id)
        if doc.version != info["version_after"]:
            raise ProposalError(
                "chapter_changed",
                f"the {label} was edited after the Agent's write, so it cannot be undone safely",
                current_version=doc.version,
            )
        snapshot = self.history.load(
            project_id=project_id,
            target_id=_history_key(target_type, target_id),
            snapshot_id=info.get("snapshot_id") or "",
        )
        if snapshot is None:
            raise ProposalError("snapshot_missing", "the saved copy of the earlier text is gone")
        try:
            restored = self._save(project_id, target_type, target_id, snapshot["text"], doc.version)
        except VersionConflictError as exc:
            raise ProposalError("chapter_changed", f"the {label} changed while it was being restored") from exc
        self.store.mark_undone(applied["id"])
        return {"target_type": target_type, "target_id": target_id, "chapter_id": target_id if target_type == "chapter" else None, "version": restored.version}

    def writes(self, *, project_id: str) -> list[dict[str, Any]]:
        rows = []
        for row in self.store.recent_applied(project_id=project_id):
            target_type = _proposal_type(row)
            applied = row["applied"]
            target_id = applied.get("target_id") or applied.get("chapter_id")
            rows.append({
                "proposal_id": row["id"],
                "target_type": target_type,
                "target_id": target_id,
                "target_title": applied.get("title") or row.get("target_title") or row.get("chapter_title") or row.get("title"),
                "chapter_id": applied.get("chapter_id"),
                "chapter_title": row.get("chapter_title"),
                "at": applied["at"],
                "undone": bool(applied.get("undone_at")),
                "kind": row["kind"],
            })
        return rows

    # ------------------------------------------------------------- targets
    def resolve_target(self, project_id: str, target_type: str, ref: object) -> str:
        return resolve_target(self.repository, project_id, target_type, ref)

    def _doc(self, project_id: str, target_type: str, target_id: str) -> _Doc:
        repo = self.repository
        if target_type == "character":
            row = repo.get_character(project_id, target_id)
            return _Doc(row.id, row.name, row.content, row.version)
        if target_type == "world_entry":
            row = repo.get_world_entry(project_id, target_id)
            return _Doc(row.id, row.title, row.content, row.version)
        if target_type == "note":
            row = repo.get_note(project_id, target_id)
            return _Doc(row.id, row.title, row.content, row.version, read_only=row.reference)
        row = repo.get_chapter(project_id, target_id)
        return _Doc(row.id, row.title, row.content, row.version)

    def _save(self, project_id: str, target_type: str, target_id: str, text: str, expected: str) -> _Doc:
        repo = self.repository
        if target_type == "character":
            row = repo.save_character(project_id, target_id, text, expected_version=expected)
            return _Doc(row.id, row.name, row.content, row.version)
        if target_type == "world_entry":
            row = repo.save_world_entry(project_id, target_id, text, expected_version=expected)
            return _Doc(row.id, row.title, row.content, row.version)
        if target_type == "note":
            row = repo.save_note(project_id, target_id, text, expected_version=expected)
            return _Doc(row.id, row.title, row.content, row.version, read_only=row.reference)
        row = repo.save_chapter(project_id, target_id, text, expected_version=expected)
        return _Doc(row.id, row.title, row.content, row.version)

    def _create(self, project_id: str, target_type: str, proposal: dict[str, Any], text: str) -> _Doc:
        repo = self.repository
        title = proposal["title"]
        if target_type == "character":
            row = repo.create_character(project_id, title, text)
            return _Doc(row.id, row.name, row.content, row.version)
        if target_type == "world_entry":
            row = repo.create_world_entry(project_id, title, text)
            return _Doc(row.id, row.title, row.content, row.version)
        if target_type == "note":
            row = repo.create_note(project_id, title, text, proposal.get("category_id"))
            return _Doc(row.id, row.title, row.content, row.version)
        row = repo.create_chapter(project_id, proposal["volume_id"], title, text)
        return _Doc(row.id, row.title, row.content, row.version)

    # ----------------------------------------------- renaming and deleting
    def _approve_action(self, proposal: dict[str, Any], project_id: str) -> dict[str, Any]:
        target_type = _proposal_type(proposal)
        label = _LABELS[target_type]
        doc = self._doc(project_id, target_type, proposal["target_id"])
        if doc.read_only:
            raise ProposalError("read_only", f"this {label} is a reference and cannot be changed by the Agent")
        if doc.version != proposal["base_version"]:
            raise ProposalError(
                "version_changed",
                f"the {label} changed after this was proposed; ask the Agent to propose it again",
                current_version=doc.version,
            )
        return {"mode": "action", "digest": _action_digest(proposal)}

    def _apply_action(self, project_id: str, proposal_id: str, proposal: dict[str, Any]) -> dict[str, Any]:
        approval = proposal["approval"]
        if approval.get("mode") != "action" or approval.get("digest") != _action_digest(proposal):
            raise ProposalError("approval_mismatch", "the approved content no longer matches this proposal")
        target_type = _proposal_type(proposal)
        label = _LABELS[target_type]
        doc = self._doc(project_id, target_type, proposal["target_id"])
        if doc.read_only:
            raise ProposalError("read_only", f"this {label} is a reference and cannot be changed by the Agent")
        if doc.version != proposal["base_version"]:
            raise ProposalError(
                "version_changed",
                f"the {label} changed after this was proposed; ask the Agent to propose it again",
                current_version=doc.version,
            )
        try:
            if proposal["kind"] == "rename":
                self.repository.rename_record(
                    project_id, target_type, doc.id, proposal["new_title"], expected_version=doc.version
                )
                after = self._doc(project_id, target_type, doc.id)
                self.store.mark_applied(proposal_id, {
                    **_written(target_type, doc.id),
                    "title": after.title,
                    "old_title": doc.title,
                    "version_before": doc.version,
                    "version_after": after.version,
                    "snapshot_id": None,
                })
                return {"status": "applied", "title": after.title, "version": after.version,
                        **_written(target_type, doc.id)}
            trash_ref, source_ref = self.repository.trash_record(
                project_id, target_type, doc.id, expected_version=doc.version
            )
        except VersionConflictError as exc:
            raise ProposalError(
                "version_changed", f"the {label} changed while it was being saved", current_version=""
            ) from exc
        self.store.mark_applied(proposal_id, {
            **_written(target_type, doc.id),
            "title": doc.title,
            "trash_ref": trash_ref,
            "source_ref": source_ref,
            "version_before": doc.version,
            "snapshot_id": None,
        })
        return {"status": "applied", "deleted": True, "title": doc.title, **_written(target_type, doc.id)}

    def _undo_action(
        self, project_id: str, target_type: str, target_id: str, applied: dict[str, Any]
    ) -> dict[str, Any]:
        label = _LABELS[target_type]
        info = applied["applied"]
        if applied["kind"] == "rename":
            doc = self._doc(project_id, target_type, target_id)
            if doc.version != info["version_after"]:
                raise ProposalError(
                    "chapter_changed",
                    f"the {label} was edited after the Agent's write, so it cannot be undone safely",
                    current_version=doc.version,
                )
            try:
                self.repository.rename_record(
                    project_id, target_type, target_id, info["old_title"], expected_version=doc.version
                )
            except VersionConflictError as exc:
                raise ProposalError("chapter_changed", f"the {label} changed while it was being restored") from exc
        else:
            try:
                self.repository.restore_record(project_id, info["trash_ref"], info["source_ref"])
            except RepositoryError as exc:
                raise ProposalError("restore_failed", f"the {label} could not be put back: {exc}") from exc
        version = self._doc(project_id, target_type, target_id).version
        self.store.mark_undone(applied["id"])
        return {
            "target_type": target_type,
            "target_id": target_id,
            "chapter_id": target_id if target_type == "chapter" else None,
            "version": version,
        }

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
        label = _LABELS[_proposal_type(proposal)]
        if _is_new(proposal):
            base = ""
        else:
            base = self._doc(project_id, _proposal_type(proposal), proposal["target_id"]).content
        try:
            result = apply_edits(base, picked)
        except EditError as exc:
            raise _conflict(f"an edit no longer matches the {label}", exc) from exc
        if result == normalize_newlines(base):
            raise ProposalError("no_change", f"the selected edits would not change the {label}")
        return {"mode": "edits", "selected": chosen, "digest": edits_digest(picked)}

    def _approve_text(
        self, proposal: dict[str, Any], project_id: str, text: str, base_version: str | None
    ) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ProposalError("empty_content", "the text must not be empty")
        label = _LABELS[_proposal_type(proposal)]
        try:
            body, _warnings = clean_body(text, title=proposal.get("target_title") or proposal.get("chapter_title"))
        except EditError as exc:
            raise ProposalError(exc.code, str(exc)) from exc
        if _is_new(proposal):
            version = ""
        else:
            doc = self._doc(project_id, _proposal_type(proposal), proposal["target_id"])
            if base_version != doc.version:
                raise ProposalError(
                    "version_changed",
                    f"the {label} changed since the text was edited",
                    current_version=doc.version,
                )
            if normalize_newlines(doc.content) == normalize_newlines(body):
                raise ProposalError("no_change", f"the text is the same as the {label}")
            version = doc.version
        return {"mode": "text", "text": body, "base_version": version, "digest": text_digest(body)}


def resolve_target(repository: StoryRepository, project_id: str, target_type: str, ref: object) -> str:
    """The id a name or id points at; a name shared by several records is refused."""

    target_type = _target_type(target_type)
    label = _LABELS[target_type]
    text = ref.strip() if isinstance(ref, str) else ""
    if not text:
        raise ProposalError("invalid_request", f"the {label} id or name is required")
    rows = _rows(repository.get_project(project_id), target_type)
    if any(row_id == text for row_id, _title_text in rows):
        return text
    matches = [(row_id, name) for row_id, name in rows if name.casefold() == text.casefold()]
    if len(matches) == 1:
        return matches[0][0]
    if matches:
        raise ProposalError(
            "ambiguous_target",
            f"several {label}s are named {text!r}; use one of the ids",
            candidates=[{"id": row_id, "title": name} for row_id, name in matches],
        )
    raise NotFoundError(f"{label} {text!r} was not found")


def record_summaries(repository: StoryRepository, project_id: str, target_type: str) -> list[dict[str, Any]]:
    """Id, title, version and length of every record of one kind; never the text."""

    tree = repository.get_project(project_id)
    if target_type == "character":
        return [
            {"id": row.id, "title": row.name, "version": row.version, "content_length": len(row.content)}
            for row in tree.characters
        ]
    if target_type == "world_entry":
        return [
            {"id": row.id, "title": row.title, "version": row.version, "content_length": len(row.content)}
            for row in tree.world_info_entries
        ]
    if target_type == "note":
        return [
            {
                "id": row.id, "title": row.title, "version": row.version,
                "content_length": len(row.content), "category_id": row.category_id,
                "reference": row.reference,
            }
            for row in tree.notes
        ]
    raise ProposalError("invalid_target_type", "target_type must be one of character, world_entry, note")


def read_record(repository: StoryRepository, project_id: str, target_type: str, ref: object) -> Any:
    target_type = _target_type(target_type)
    target_id = resolve_target(repository, project_id, target_type, ref)
    if target_type == "character":
        return repository.get_character(project_id, target_id)
    if target_type == "world_entry":
        return repository.get_world_entry(project_id, target_id)
    if target_type == "note":
        return repository.get_note(project_id, target_id)
    raise ProposalError("invalid_target_type", "target_type must be one of character, world_entry, note")


def _conflict(message: str, cause: EditError) -> ProposalError:
    extra = {key: value for key, value in cause.as_dict().items() if key not in ("code", "message")}
    return ProposalError("conflict", message, reason=cause.code, **extra)


def _selected(proposal: dict[str, Any], indexes: Sequence[int]) -> list[dict[str, str]]:
    edits = proposal["edits"]
    return [edits[i] for i in indexes if isinstance(i, int) and 0 <= i < len(edits)]


def _action_digest(proposal: dict[str, Any]) -> str:
    """What an approval of a rename or delete covers: that action on that record version."""

    return text_digest("|".join(str(proposal.get(key) or "") for key in (
        "kind", "target_type", "target_id", "base_version", "new_title",
    )))


def _title(value: object) -> str:
    if not isinstance(value, str):
        raise ProposalError("invalid_title", "title must be a string")
    title = unicodedata.normalize("NFKC", value).strip()
    if not title or len(title) > MAX_TITLE or any(ord(ch) < 32 for ch in title):
        raise ProposalError("invalid_title", f"title must be 1-{MAX_TITLE} characters without control characters")
    return title


def _target_type(value: object) -> str:
    if value is None or value == "":
        return "chapter"
    if value not in TARGET_TYPES:
        raise ProposalError(
            "invalid_target_type", f"target_type must be one of {', '.join(TARGET_TYPES)}"
        )
    return str(value)


def _proposal_type(proposal: dict[str, Any]) -> str:
    """Proposals saved before other targets existed have no type: they are chapters."""

    return proposal.get("target_type") or "chapter"


def _is_new(proposal: dict[str, Any]) -> bool:
    return str(proposal.get("kind", "")).startswith("new_")


def _identity(target_type: str, target_id: str | None, title: str) -> dict[str, Any]:
    """The fields that say what a proposal is about. Chapters keep their older
    ``chapter_*`` names too, which the Desktop already reads."""

    fields: dict[str, Any] = {"target_type": target_type, "target_id": target_id, "target_title": title}
    if target_type == "chapter":
        fields.update({"chapter_id": target_id, "chapter_title": title})
    return fields


def _history_key(target_type: str, target_id: str) -> str:
    """Chapters keep the bare id their snapshots were always saved under."""

    return target_id if target_type == "chapter" else f"{target_type}.{target_id}"


def _written(target_type: str, target_id: str) -> dict[str, Any]:
    fields: dict[str, Any] = {"target_type": target_type, "target_id": target_id}
    if target_type == "chapter":
        fields["chapter_id"] = target_id
    return fields


def _rows(tree: Any, target_type: str) -> list[tuple[str, str]]:
    if target_type == "character":
        return [(row.id, row.name) for row in tree.characters]
    if target_type == "world_entry":
        return [(row.id, row.title) for row in tree.world_info_entries]
    if target_type == "note":
        return [(row.id, row.title) for row in tree.notes]
    return [(row.id, row.title) for row in tree.chapters]


def _taken_titles(tree: Any, target_type: str, category_id: str | None) -> dict[str, str]:
    """Casefolded name -> id of the records a new one would sit beside."""

    if target_type == "note":
        rows = [(row.id, row.title) for row in tree.notes if row.category_id == (category_id or None)]
    else:
        rows = _rows(tree, target_type)
    return {name.casefold(): row_id for row_id, name in rows}


def _agent_summary(proposal: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": proposal["id"],
        "status": proposal["status"],
        "kind": proposal["kind"],
        "target_type": _proposal_type(proposal),
        "target_id": proposal.get("target_id"),
        "chapter_id": proposal.get("chapter_id"),
        "edits": len(proposal["edits"]),
        "warnings": proposal["warnings"],
        "next": (
            "Nothing is written yet. Call story.apply_edit with this proposal_id: it asks "
            "the user to approve the change in this chat and writes it only if they do. "
            "If it is declined, nothing is written."
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
        "target_type": _proposal_type(proposal),
        "target_id": proposal.get("target_id") or proposal.get("chapter_id"),
        "target_title": proposal.get("target_title") or proposal.get("chapter_title") or proposal.get("title"),
        "chapter_id": proposal.get("chapter_id"),
        "volume_id": proposal.get("volume_id"),
        "category_id": proposal.get("category_id"),
        "title": proposal.get("title"),
        "new_title": proposal.get("new_title"),
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
