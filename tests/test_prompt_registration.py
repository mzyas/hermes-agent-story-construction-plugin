"""Hermes prompt-section registration and which sessions get the Story section."""

from __future__ import annotations

from story_construction_plugin import register_story_prompt
from story_construction_plugin.prompt_templates import (
    STORY_AGENT_PROMPT_VERSION,
    STORY_SUBAGENT_PROMPT_VERSION,
)
from story_construction_plugin.session_lineage import SessionLineage
from story_construction_plugin.session_store import StorySessionRegistry


class FakeContext:
    def __init__(self) -> None:
        self.sections = []

    def register_system_prompt_section(self, *args, **kwargs) -> None:
        self.sections.append((args, kwargs))


def _bound_registry(tmp_path=None) -> StorySessionRegistry:
    path = tmp_path / "sessions.json" if tmp_path is not None else None
    registry = StorySessionRegistry(path, locked_profile="writer")
    registry.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        project_id="novel",
    )
    return registry


def _render(registry, session_id: str, lineage: SessionLineage | None = None, **info) -> str:
    return registry.render_system_prompt(
        {"session_id": session_id, "profile_name": "writer", **info}, lineage
    )


def test_registered_prompt_keeps_the_existing_section_contract() -> None:
    registry = _bound_registry()
    context = FakeContext()
    register_story_prompt(context, registry)

    args, kwargs = context.sections[0]
    assert args[0] == "story-construction.agent"
    assert kwargs == {"position": "after_memory", "max_chars": 4000}
    assert args[1]({"session_id": "runtime-1", "profile_name": "writer"})


def test_only_a_bound_session_gets_the_story_protocol() -> None:
    registry = _bound_registry()

    for session_id in ("stored-1", "runtime-1"):
        assert _render(registry, session_id).startswith(f"# {STORY_AGENT_PROMPT_VERSION}")
    # An ordinary chat in the Story Profile gets no Story section at all.
    assert _render(registry, "chat") == ""
    assert _render(registry, "") == ""
    # Other Profiles never get it, bound or not.
    assert registry.render_system_prompt({"session_id": "runtime-1", "profile_name": "reviewer"}) == ""
    assert registry.render_system_prompt({"session_id": "runtime-1"}) == ""


def test_a_session_rendered_before_its_binding_stays_without_it() -> None:
    # Hermes freezes the first render, so a chat must be bound before it starts:
    # "New writing session" binds first, and late binding is refused.
    registry = StorySessionRegistry(locked_profile="writer")
    before = _render(registry, "runtime-1")
    registry.bind(
        stored_session_id="stored-1", runtime_session_id="runtime-1",
        profile="writer", connection_id="local", project_id="novel",
    )

    assert before == ""
    assert _render(registry, "runtime-1").startswith(f"# {STORY_AGENT_PROMPT_VERSION}")


def test_a_compressed_session_keeps_the_protocol() -> None:
    lineage = SessionLineage(
        {"c2": ("c1", False), "c1": ("stored-1", False)}.get
    )

    assert _render(_bound_registry(), "c2", lineage).startswith(f"# {STORY_AGENT_PROMPT_VERSION}")


def test_a_subagent_of_a_bound_session_gets_the_read_only_section() -> None:
    lineage = SessionLineage()
    lineage.note_subagent(parent_session_id="runtime-1", child_session_id="sub")
    lineage.note_subagent(parent_session_id="chat", child_session_id="chat-sub")
    registry = _bound_registry()

    rendered = _render(registry, "sub", lineage, platform="subagent")

    assert rendered.startswith(f"# {STORY_SUBAGENT_PROMPT_VERSION}")
    assert "You can only read" in rendered
    assert _render(registry, "chat-sub", lineage, platform="subagent") == ""


def test_when_the_binding_cannot_be_read_the_full_protocol_is_safer(tmp_path) -> None:
    def broken(_session_id):
        raise OSError("state.db is locked")

    registry = _bound_registry(tmp_path)
    assert _render(registry, "chat", SessionLineage(broken)).startswith(
        f"# {STORY_AGENT_PROMPT_VERSION}"
    )
    (tmp_path / "sessions.json").write_text("{not json", encoding="utf-8")
    assert _render(registry, "chat").startswith(f"# {STORY_AGENT_PROMPT_VERSION}")
