"""Hermes function schemas exposed to the language model."""

from __future__ import annotations

from typing import Any


def _parameters(
    properties: dict[str, dict[str, Any]], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_LIMIT = {
    "limit": {
        "type": "integer",
        "minimum": 1,
        "maximum": 50,
        "description": "Maximum number of matches to return (default 20, at most 50).",
    }
}


_PROJECT_ID = {
    "project_id": {
        "type": "string",
        "description": "ID of the story project to read.",
    }
}


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "story.get_session_project": {
        "name": "story.get_session_project",
        "description": (
            "Return the story project this chat session is bound to, with its "
            "volumes and chapter metadata (no chapter text). Takes no "
            "arguments. Call this first when the user wants to write, continue, "
            "or check the story, to learn the project_id, volume_id, and "
            "chapter_id that the other story.* tools need. An error "
            "session_not_bound means this is an ordinary chat."
        ),
        "parameters": _parameters({}, []),
    },
    "story.get_project": {
        "name": "story.get_project",
        "description": (
            "Read a story project's metadata and indexed records, including its "
            "world information, characters, notes, volumes, and chapters. Use "
            "this for a project overview or to find IDs before retrieving a "
            "specific record."
        ),
        "parameters": _parameters(_PROJECT_ID, ["project_id"]),
    },
    "story.get_world_info": {
        "name": "story.get_world_info",
        "description": (
            "Read a story project's world information and structured lore "
            "entries. Use this to review the setting or lore as a whole."
        ),
        "parameters": _parameters(_PROJECT_ID, ["project_id"]),
    },
    "story.search_world_info": {
        "name": "story.search_world_info",
        "description": (
            "Find world-information entries whose title or content matches a "
            "topic, name, place, or rule. Use this for a targeted lore lookup."
        ),
        "parameters": _parameters(
            {
                **_PROJECT_ID,
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Non-empty text to match in world-information entry titles or content.",
                },
                **_LIMIT,
            },
            ["project_id", "query"],
        ),
    },
    "story.get_character": {
        "name": "story.get_character",
        "description": (
            "Read one character record by ID. Use this to retrieve established "
            "character facts before drafting or checking a scene."
        ),
        "parameters": _parameters(
            {
                **_PROJECT_ID,
                "character_id": {
                    "type": "string",
                    "description": "ID of the character record to retrieve.",
                },
            },
            ["project_id", "character_id"],
        ),
    },
    "story.list_volumes": {
        "name": "story.list_volumes",
        "description": (
            "List a story project's volumes and their IDs. Use this to navigate "
            "the project or locate a volume before listing its chapters."
        ),
        "parameters": _parameters(_PROJECT_ID, ["project_id"]),
    },
    "story.list_chapters": {
        "name": "story.list_chapters",
        "description": (
            "List a story project's chapters, optionally limited to one volume. "
            "Returns metadata only (ID, title, volume, length), not chapter text; use "
            "story.get_chapter to read one chapter."
        ),
        "parameters": _parameters(
            {
                **_PROJECT_ID,
                "volume_id": {
                    "type": "string",
                    "description": "Optional volume ID used to limit the chapter list.",
                },
            },
            ["project_id"],
        ),
    },
    "story.get_chapter": {
        "name": "story.get_chapter",
        "description": (
            "Read one chapter's stored content by chapter ID. Use this to "
            "continue, summarize, or check a specific chapter for continuity."
        ),
        "parameters": _parameters(
            {
                **_PROJECT_ID,
                "chapter_id": {
                    "type": "string",
                    "description": "ID of the chapter record to retrieve.",
                },
            },
            ["project_id", "chapter_id"],
        ),
    },
    "story.search_notes": {
        "name": "story.search_notes",
        "description": (
            "Search project notes by matching their titles or content. Use this "
            "for a targeted search across the project's notes."
        ),
        "parameters": _parameters(
            {
                **_PROJECT_ID,
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Non-empty text to match in project note titles or content.",
                },
                **_LIMIT,
            },
            ["project_id", "query"],
        ),
    },
    "story.search_reference_notes": {
        "name": "story.search_reference_notes",
        "description": (
            "Search only notes marked as references, matching their titles or "
            "content. Use this to find research notes relevant to a story fact."
        ),
        "parameters": _parameters(
            {
                **_PROJECT_ID,
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Non-empty text to match in reference-note titles or content.",
                },
                **_LIMIT,
            },
            ["project_id", "query"],
        ),
    },
}
