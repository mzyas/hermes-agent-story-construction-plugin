"""Confirmed, version-checked chapter writes for the Desktop surface."""

from __future__ import annotations

from dataclasses import dataclass

from .domain import Chapter
from .permissions import SessionScope, StoryPermissionGate
from .repository import StoryRepository, VersionConflictError


@dataclass(frozen=True, slots=True)
class SaveRequest:
    session_id: str
    profile: str
    connection_id: str
    project_id: str
    chapter_id: str
    content: str
    expected_version: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class SaveResult:
    chapter: Chapter


class SaveConflict(RuntimeError):
    """The original changed while a generated draft was awaiting confirmation."""

    def __init__(self, current: Chapter, draft_content: str) -> None:
        super().__init__(f"chapter {current.id!r} changed before save")
        self.current = current
        self.draft_content = draft_content


class StorySaveService:
    def __init__(self, repository: StoryRepository, permissions: StoryPermissionGate) -> None:
        self.repository = repository
        self.permissions = permissions

    def save(self, request: SaveRequest) -> SaveResult:
        _validate_request(request)
        scope = SessionScope(
            session_id=request.session_id,
            source="desktop",
            profile=request.profile,
            connection_id=request.connection_id,
            # Resolve the project from the backend-bound session, not from a
            # client-provided duplicate.  The request ID is still checked by
            # the repository after authorization.
            project_id=None,
        )
        self.permissions.require_write(scope, request.project_id)
        try:
            chapter = self.repository.save_chapter(
                request.project_id,
                request.chapter_id,
                request.content,
                expected_version=request.expected_version,
            )
        except VersionConflictError as exc:
            current = self.repository.get_chapter(request.project_id, request.chapter_id)
            raise SaveConflict(current, request.content) from exc
        return SaveResult(chapter=chapter)


def _validate_request(request: SaveRequest) -> None:
    for field in ("session_id", "profile", "connection_id", "project_id", "chapter_id", "expected_version"):
        if not isinstance(getattr(request, field), str) or not getattr(request, field).strip():
            raise ValueError(f"{field} is required")
    if not isinstance(request.content, str):
        raise ValueError("content must be a string")
    if request.confirmed is not True:
        raise ValueError("explicit save confirmation is required")
