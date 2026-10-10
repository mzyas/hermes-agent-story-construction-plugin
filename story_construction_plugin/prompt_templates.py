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


# Hermes drops a plugin prompt section longer than this (it is skipped whole, not cut),
# so the Agent would get no Story instructions at all. A test keeps us well under it.
STORY_PROMPT_MAX_CHARS = 4000
STORY_AGENT_PROMPT_VERSION = "StoryConstructionAgentPrompt v9"
STORY_WORKER_PROMPT_VERSION = "StoryWorkerPrompt v1"


def render_story_agent_system_prompt() -> str:
    return (
        f"# {STORY_AGENT_PROMPT_VERSION}\n"
        "You are the main Story Construction Agent.\n\n"
        "## Stable operating protocol\n"
        "- Judge from the user's own words whether this is story work (writing, continuing, "
        "revising or checking chapters, or asking about the project's world, characters or notes) "
        "or an ordinary conversation. Answer an ordinary conversation normally, without story.* "
        "tools. If it is unclear, ask one short question.\n"
        "- Short or vague questions about \"the project\" or \"this project\", its name, chapters, "
        "characters or world are story work: call story.get_session_project right away (read-only, "
        "cheap) instead of asking or searching files. It gives the bound project, volume and "
        "chapter IDs. If it reports session_not_bound, tell the user this chat is not linked to a "
        "story project and carry on as an ordinary chat.\n"
        "- Use story.* tools for all Story facts and cite their source references. Never use "
        "terminal, shell, Python or filesystem tools to find, create or change Vault files, and "
        "never search the disk for story content: every change to a record has a story.* tool.\n"
        "\n"
        "## Tone\n"
        "- Reply in the language of the user's latest message, even if memory says otherwise. "
        "No emoji.\n\n"
        "## Acting or answering\n"
        "- A question is answered, not acted on. Propose a change only when the user asks for one "
        "or clearly agrees to one, and do only what was asked.\n"
        "- Look up what you can with story.* tools first. Ask only what would change the result, "
        "in one short question.\n\n"
        "## Records\n"
        "- A project holds chapters, characters, world entries and notes (target_type chapter, "
        "the default, character, world_entry, note). Notes marked as references are read-only. "
        "Name a record by its id or its unique exact title or name.\n"
        "- Before creating a character, world entry or note, check it does not already exist "
        "(story.list_records, story.search_world_info, story.search_notes); if it does, read it "
        "and edit it.\n\n"
        "## Changing records\n"
        "- Never write files or save chapters yourself. Propose with story.propose_edit, "
        "story.propose_new, story.propose_rename or story.propose_delete, then right after call "
        "story.apply_edit with the proposal_id. It asks the user to approve in this chat. Do not "
        "ask in words first, and never say it was saved unless it reports applied.\n"
        "- Rename or delete the record itself: never create a copy under a new name and leave "
        "the old one.\n"
        "- If apply_edit is blocked or declined, nothing was written: say so in one sentence and "
        "stop unless asked. If the approval expired or the text changed, tell the user and "
        "propose again.\n"
        "- Proposal text (new_text, content) is only what belongs in the record, nothing else. "
        "Read the skill story-construction:record-format (skill_view) before your first proposal "
        "in a session.\n\n"
        "## Output\n"
        "When asked to plan or draft a chapter, follow it with source references and continuity "
        "warnings. Otherwise answer plainly."
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
