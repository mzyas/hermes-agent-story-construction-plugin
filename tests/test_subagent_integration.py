"""Boundary-level parent/child delegation behavior."""

from __future__ import annotations

import json

from story_construction_plugin.permissions import StoryPermissionGate
from story_construction_plugin.subagent_policy import (
    StoryWorkerContext,
    validate_story_worker_result,
    render_story_worker_context,
)
from story_construction_plugin.tools import TOOL_SCHEMAS


def test_parent_continues_after_validated_read_only_worker_result() -> None:
    context = StoryWorkerContext(
        project_id="p1",
        chapter_id="ch1",
        goal="Find continuity risks.",
        skill_guidance="Use cited facts.",
        source_refs=("chapters/ch1.md",),
        parent_session_id="parent-1",
    )
    child_messages = [{"role": "system", "content": render_story_worker_context(context)}]
    child_messages.append({"role": "user", "content": "Analyze the supplied chapter."})
    child_result = {
        "project_id": "p1",
        "chapter_id": "ch1",
        "summary": "No contradiction found.",
        "source_refs": ["chapters/ch1.md"],
    }

    validate_story_worker_result(child_result, project_id="p1", chapter_id="ch1")
    parent_tool_message = {
        "role": "tool",
        "name": "delegate_task",
        "content": json.dumps(child_result),
    }

    assert len(child_messages) == 2
    assert parent_tool_message["role"] == "tool"
    assert "story.save_chapter" not in TOOL_SCHEMAS
    assert "No contradiction" in parent_tool_message["content"]
