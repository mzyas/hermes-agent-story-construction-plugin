"""Request assembly behavior over consecutive tool-calling requests."""

from __future__ import annotations

from story_construction_plugin.prompt_templates import (
    build_story_request_messages,
    compose_story_system_prompt,
    render_story_agent_system_prompt,
)


def test_consecutive_requests_reuse_stable_system_bytes_and_append_tool_messages() -> None:
    story = render_story_agent_system_prompt()
    stable = compose_story_system_prompt("Hermes base", story)
    history = [{"role": "user", "content": "Use the world book."}]

    first = build_story_request_messages(
        stable_system_prompt=stable,
        history=history,
        current_user_message="project_id: p1\nchapter_id: ch1\nFind relevant rules.",
    )
    history.extend([
        {"role": "assistant", "tool_calls": [{"name": "story.search_world_info"}]},
        {"role": "tool", "name": "story.search_world_info", "content": "Magic costs memory."},
    ])
    second = build_story_request_messages(
        stable_system_prompt=stable,
        history=history,
        current_user_message=(
            "project_id: p1\nchapter_id: ch1\nDraft using the returned rule."
        ),
    )

    assert first[0]["content"] == second[0]["content"]
    assert second[-2]["role"] == "tool"
    assert "Magic costs memory." in second[-2]["content"]
    assert "StoryConstructionAgentPrompt" not in second[-2]["content"]
