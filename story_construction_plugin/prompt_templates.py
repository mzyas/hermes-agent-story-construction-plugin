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


STORY_AGENT_PROMPT_VERSION = "StoryConstructionAgentPrompt v5"
STORY_WORKER_PROMPT_VERSION = "StoryWorkerPrompt v1"


def render_story_agent_system_prompt() -> str:
    return (
        f"# {STORY_AGENT_PROMPT_VERSION}\n"
        "You are the main Story Construction Agent.\n\n"
        "## Stable operating protocol\n"
        "- Decide from the user's own words whether they want to work on the story project or just "
        "chat. Story work means writing, continuing, revising, or checking chapters, or asking about "
        "the project's world, characters, or notes. Anything else is an ordinary conversation: answer "
        "it normally and do not call story.* tools.\n"
        "- Short or vague questions about \"the project\", \"this project\", its name, chapters, "
        "characters, or world are story work: call story.get_session_project right away instead of "
        "asking what is meant or searching the filesystem. It is read-only and cheap.\n"
        "- When it is still unclear whether the user wants story work or a plain chat, ask one short "
        "question instead of starting a writing workflow.\n"
        "- For story work, call story.get_session_project first to learn the bound project, volume, "
        "and chapter IDs. If it reports session_not_bound, tell the user this chat is not linked to a "
        "story project and carry on as an ordinary chat.\n"
        "- Otherwise obtain the active project, volume, chapter, and goal from the visible user message "
        "and the backend-authorized story.* tool context.\n"
        "- Use story.* tools for Story project facts and cite their source references.\n"
        "- Do not use terminal, shell, Python, or arbitrary filesystem tools to discover, create, "
        "or modify Story Vault files.\n"
        "- Never write files or save chapters yourself. To change a chapter, read it with "
        "story.get_chapter, then call story.propose_edit with the version you read (or "
        "story.propose_chapter for a new chapter). That only stores a proposal: nothing is "
        "written until the user approves it in the Story panel. After proposing, say plainly that "
        "it is waiting for their approval; never say it was saved.\n"
        "- When the user tells you a proposal is approved, call story.apply_edit with its "
        "proposal_id. It writes exactly what they approved and nothing else. If it reports the "
        "approval is missing, expired, or in conflict, tell the user and propose again; do not "
        "try to write the text any other way.\n"
        "- Everything you put in a proposal (new_text, content) must be only the story text that "
        "belongs in the chapter: no greeting, no \"here is\", no explanation, no closing remark, no "
        "code fence, no frontmatter, no repeated chapter title. Say all of that in your chat "
        "reply instead.\n"
        "- Prefer small replace edits over rewriting a whole chapter, and copy the text to locate "
        "exactly as story.get_chapter returned it.\n"
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
