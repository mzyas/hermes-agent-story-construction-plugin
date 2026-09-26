"""Hermes story-construction plugin registration entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runtime import StoryRuntimeState, permission_snapshot, prepare_story_runtime
from .session_store import StorySessionRegistry
from .tools import register_story_tools


_SKILLS = (
    ("chapter-drafting", "Draft a chapter from cited project context."),
    ("continuity-check", "Check story continuity against retrieved project facts."),
    ("obsidian-format", "Format a confirmed chapter as Obsidian Markdown."),
)


def register_story_skills(ctx) -> None:
    skill_root = Path(__file__).with_name("skills")
    for name, description in _SKILLS:
        path = skill_root / name / "SKILL.md"
        ctx.register_skill(name, path, description, {"name": name, "description": description})


def register_story_prompt(ctx, registry: StorySessionRegistry | None = None) -> None:
    """Use Hermes' session-scoped frozen prompt seam for the main Agent."""

    prompt_registry = registry or StorySessionRegistry()
    ctx.register_system_prompt_section(
        "story-construction.agent",
        prompt_registry.render_system_prompt,
        position="after_memory",
        max_chars=4000,
    )


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _settings(ctx: Any) -> dict[str, object]:
    get_config = getattr(ctx, "get_config", None)
    if not callable(get_config):
        return {}
    return {
        key: get_config(key)
        for key in ("locked_profile", "vault_root", "locked_hermes_home")
    }


def register_story_backend(ctx) -> StoryRuntimeState:
    """Prepare one home-bound runtime and register story tools only when ready."""

    state = prepare_story_runtime(_plugin_root(), _settings(ctx))
    if state.ready:
        # Each tool call re-reads the durable bindings through this provider;
        # registration itself never needs to know about later binds or unbinds.
        register_story_tools(
            ctx,
            state.repository,
            state.permissions,
            permissions_provider=lambda: permission_snapshot(state),
        )
    return state


def register(ctx) -> None:
    """Register Skills and the stable, session-scoped Story Agent prompt."""

    register_story_skills(ctx)
    state = register_story_backend(ctx)
    register_story_prompt(ctx, state.sessions)
