"""Parent-to-child context and result validation contracts."""

from __future__ import annotations

import pytest

from story_construction_plugin.subagent_policy import (
    StoryWorkerContext,
    validate_story_worker_result,
    render_story_worker_context,
)


def _context() -> StoryWorkerContext:
    return StoryWorkerContext(
        project_id="p1",
        chapter_id="ch1",
        goal="Check the protagonist's continuity.",
        skill_guidance="Use retrieved facts only.",
        source_refs=("characters/hero.md", "chapters/ch1.md"),
        parent_session_id="parent-1",
    )


def test_worker_context_is_explicit_and_does_not_claim_parent_history() -> None:
    rendered = render_story_worker_context(_context())

    assert "project_id: p1" in rendered
    assert "chapter_id: ch1" in rendered
    assert "parent_session_id: parent-1" in rendered
    assert "Check the protagonist" in rendered
    assert "characters/hero.md" in rendered
    assert "does not have the parent transcript" in rendered


def test_worker_result_must_match_project_chapter_and_safe_source_refs() -> None:
    valid = {
        "project_id": "p1",
        "chapter_id": "ch1",
        "summary": "Consistent.",
        "source_refs": ["characters/hero.md"],
    }

    validate_story_worker_result(valid, project_id="p1", chapter_id="ch1")

    with pytest.raises(ValueError, match="project_id"):
        validate_story_worker_result({**valid, "project_id": "p2"}, project_id="p1", chapter_id="ch1")
    with pytest.raises(ValueError, match="chapter_id"):
        validate_story_worker_result({**valid, "chapter_id": "ch2"}, project_id="p1", chapter_id="ch1")
    with pytest.raises(ValueError, match="source_refs"):
        validate_story_worker_result({**valid, "source_refs": ["../outside.md"]}, project_id="p1", chapter_id="ch1")


def test_worker_result_requires_scope_fields() -> None:
    with pytest.raises(ValueError, match="project_id"):
        validate_story_worker_result({"summary": "missing"}, project_id="p1", chapter_id=None)
