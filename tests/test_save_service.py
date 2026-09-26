"""Confirmed chapter saves are scoped, version-checked, and conflict-preserving."""

from __future__ import annotations

import pytest

from story_construction_plugin.domain import Chapter
from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.repository import VersionConflictError
from story_construction_plugin.save_service import SaveConflict, SaveRequest, StorySaveService


class FakeRepository:
    def __init__(self) -> None:
        self.chapter = Chapter("ch1", "p1", "v1", "Opening", "original", "chapters/ch1.md", "v1")
        self.mode = "ok"

    def get_chapter(self, project_id, chapter_id):
        assert (project_id, chapter_id) == ("p1", "ch1")
        return self.chapter

    def save_chapter(self, project_id, chapter_id, content, *, expected_version):
        if self.mode == "conflict":
            self.chapter = Chapter("ch1", "p1", "v1", "Opening", "changed by another editor", "chapters/ch1.md", "v2")
            raise VersionConflictError("stale")
        assert expected_version == "v1"
        self.chapter = Chapter("ch1", "p1", "v1", "Opening", content, "chapters/ch1.md", "v2")
        return self.chapter


def _service(repository):
    permissions = StoryPermissionGate()
    permissions.bind_session(SessionScope("s1", "desktop", "writer", "local", "p1"), "p1")
    return StorySaveService(repository, permissions)


def _request(content="draft"):
    return SaveRequest(
        session_id="s1", profile="writer", connection_id="local", project_id="p1",
        chapter_id="ch1", content=content, expected_version="v1", confirmed=True,
    )


def test_save_requires_explicit_desktop_scope_and_returns_new_version() -> None:
    result = _service(FakeRepository()).save(_request())
    assert result.chapter.content == "draft"
    assert result.chapter.version == "v2"


def test_stale_save_preserves_current_chapter_and_generated_draft() -> None:
    repository = FakeRepository()
    repository.mode = "conflict"

    with pytest.raises(SaveConflict) as error:
        _service(repository).save(_request("generated"))

    assert error.value.current.content == "changed by another editor"
    assert error.value.draft_content == "generated"
