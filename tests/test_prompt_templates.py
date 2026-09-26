"""Prompt template contracts and stable/dynamic content boundaries."""

from __future__ import annotations

from story_construction_plugin.prompt_templates import (
    STORY_AGENT_PROMPT_VERSION,
    build_story_request_messages,
    compose_story_system_prompt,
    render_story_agent_system_prompt,
    render_story_worker_prompt,
)
from story_construction_plugin.subagent_policy import StoryWorkerContext


def test_main_template_is_generic_and_forbids_direct_vault_tools() -> None:
    rendered = render_story_agent_system_prompt()

    assert STORY_AGENT_PROMPT_VERSION in rendered
    assert "story.*" in rendered
    assert "terminal" in rendered.lower()
    assert "python" in rendered.lower()
    assert "do not write" in rendered.lower()
    assert "project_id:" not in rendered
    assert "project_name:" not in rendered


def test_worker_template_is_separate_and_explicitly_read_only() -> None:
    rendered = render_story_worker_prompt(
        StoryWorkerContext(
            project_id="p1",
            chapter_id="ch1",
            goal="Check continuity",
            skill_guidance="Use cited facts",
            source_refs=("chapters/ch1.md",),
        )
    )

    assert "StoryWorkerPrompt v1" in rendered
    assert "Check continuity" in rendered
    assert "chapters/ch1.md" in rendered
    assert "do not save" in rendered.lower()
    assert "parent transcript" in rendered


def test_request_assembly_keeps_templates_out_of_session_history() -> None:
    story_template = render_story_agent_system_prompt()
    stable_system = compose_story_system_prompt("Hermes base", story_template)
    history = [
        {"role": "user", "content": "Begin the chapter."},
        {"role": "tool", "name": "story.get_character", "content": "Hero"},
    ]

    first = build_story_request_messages(
        stable_system_prompt=stable_system,
        history=history,
        current_user_message="project_id: p1\nchapter_id: ch1\nDraft the opening.",
    )
    second = build_story_request_messages(
        stable_system_prompt=stable_system,
        history=history,
        current_user_message="project_id: p1\nchapter_id: ch2\nDraft the next scene.",
    )

    assert first[0] == second[0]
    assert first[0]["role"] == "system"
    assert first[0]["content"].count("StoryConstructionAgentPrompt") == 1
    assert "project_id: p1" not in first[0]["content"]
    assert "chapter_id: ch1" not in first[0]["content"]
    assert all(
        story_template not in str(message.get("content", ""))
        for message in first[1:]
    )
    assert "project_id: p1" in first[-1]["content"]
    assert "chapter_id: ch1" in first[-1]["content"]
    assert first[-1]["content"] != second[-1]["content"]
    assert first[2]["role"] == "tool"
