"""Hermes function schemas exposed to the language model."""

from __future__ import annotations

from typing import Any


def _parameters(
    properties: dict[str, dict[str, str]], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_PROJECT_ID = {
    "project_id": {
        "type": "string",
        "description": "ID of the story project to read.",
    }
}


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
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
                    "description": "Text to match in world-information entry titles or content.",
                },
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
            "Use this to find chapter IDs and titles before retrieving chapter text."
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
                    "description": "Text to match in project note titles or content.",
                },
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
                    "description": "Text to match in reference-note titles or content.",
                },
            },
            ["project_id", "query"],
        ),
    },
}
