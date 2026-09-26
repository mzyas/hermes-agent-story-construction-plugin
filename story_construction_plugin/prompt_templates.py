"""Stable story-agent prompts and per-request message assembly.

The main prompt is intended to be registered through Hermes' frozen system
prompt section API. It contains one generic protocol; live project identity and
records belong in visible user messages and authorized tool results. Request
assembly deliberately returns a fresh list so prompt templates never become
session-history messages.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from .subagent_policy import StoryWorkerContext, render_story_worker_context


STORY_AGENT_PROMPT_VERSION = "StoryConstructionAgentPrompt v2"
STORY_WORKER_PROMPT_VERSION = "StoryWorkerPrompt v1"


def render_story_agent_system_prompt() -> str:
    return (
        f"# {STORY_AGENT_PROMPT_VERSION}\n"
        "You are the main Story Construction Agent.\n\n"
        "## Stable operating protocol\n"
        "- Obtain the active project, volume, chapter, and goal from the visible user message "
        "and the backend-authorized story.* tool context.\n"
        "- Use story.* tools for Story project facts and cite their source references.\n"
        "- Do not use terminal, shell, Python, or arbitrary filesystem tools to discover, create, "
        "or modify Story Vault files.\n"
        "- Do not write files, save chapters, or mutate project data from the model loop. "
        "A user-confirmed Desktop action performs writes.\n"
        "- Ask the user to confirm the chapter title, narrative goal, and output scope before drafting "
        "when the visible task leaves them open.\n"
        "- Live project records never belong in this frozen system section.\n\n"
        "## Output contract\n"
        "Return planning or a chapter draft for the current request, followed by source references "
        "and continuity warnings."
    )


def render_story_worker_prompt(request: StoryWorkerContext) -> str:
    """Render the isolated read-only prompt for a child Story Worker."""

    return (
        f"# {STORY_WORKER_PROMPT_VERSION}\n"
        "You are a read-only Story Worker delegated by the main Agent.\n"
        "Analyze only the explicit project and chapter scope below. Do not save, "
        "write, or mutate project data. Return a structured analysis with source "
        "references for the parent Agent.\n\n"
        f"{render_story_worker_context(request)}"
    )


def compose_story_system_prompt(
    hermes_system_prompt: str, story_prompt: str
) -> str:
    """Compose the stable Hermes prompt and story section without live data."""

    base = _required(hermes_system_prompt, "hermes_system_prompt")
    story = _required(story_prompt, "story_prompt")
    return f"{base}\n\n{story}"


def build_story_request_messages(
    *,
    stable_system_prompt: str,
    history: Sequence[Mapping[str, object]],
    current_user_message: str,
) -> list[dict[str, object]]:
    """Build a fresh LLM request without mutating or extending Session history.

    The stable system prompt is intentionally present on every returned
    request. Hermes and the model provider can cache its unchanged prefix;
    excluding it would instead change the request contract and cache boundary.
    """

    stable = _required(stable_system_prompt, "stable_system_prompt")
    current = _required(current_user_message, "current_user_message")
    messages: list[dict[str, object]] = [
        {"role": "system", "content": stable},
    ]
    messages.extend(dict(message) for message in history)
    messages.append({"role": "user", "content": current})
    return messages


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()
