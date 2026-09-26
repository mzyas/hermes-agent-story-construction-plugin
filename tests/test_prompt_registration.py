"""Hermes prompt-section registration and profile/session binding contracts."""

from __future__ import annotations

from story_construction_plugin import register_story_prompt
from story_construction_plugin.session_store import StorySessionRegistry


class FakeContext:
    def __init__(self) -> None:
        self.sections = []

    def register_system_prompt_section(self, *args, **kwargs) -> None:
        self.sections.append((args, kwargs))


def test_registered_prompt_keeps_the_existing_section_contract() -> None:
    registry = StorySessionRegistry(locked_profile="writer")
    context = FakeContext()
    register_story_prompt(context, registry)

    args, kwargs = context.sections[0]
    assert args[0] == "story-construction.agent"
    assert kwargs == {"position": "after_memory", "max_chars": 4000}
    assert args[1]({"session_id": "runtime-1", "profile_name": "writer"})


def test_unbound_locked_profile_gets_same_frozen_prompt_after_binding() -> None:
    registry = StorySessionRegistry(locked_profile="writer")
    before = registry.render_system_prompt(
        {"session_id": "runtime-1", "profile_name": "writer"}
    )
    registry.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        project_id="novel",
    )
    after = registry.render_system_prompt(
        {"session_id": "runtime-1", "profile_name": "writer"}
    )

    assert before == after
    assert before
    assert (
        registry.render_system_prompt(
            {"session_id": "other", "profile_name": "reviewer"}
        )
        == ""
    )
    assert registry.render_system_prompt({"session_id": "runtime-1"}) == ""
