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
            "Return the story (fiction) project this chat session is bound to, with its "
            "volumes and chapter metadata (no chapter text); never a code or software "
            "project. Takes no "
            "arguments. Call this first when the user wants to write, continue, "
            "or check the story, to learn the project_id, volume_id, and "
            "chapter_id that the other story.* tools need. An error "
            "session_not_bound means this is an ordinary chat."
        ),
        "parameters": _parameters({}, []),
    },
    "story.propose_edit": {
        "name": "story.propose_edit",
        "description": (
            "Propose changes to the text of an existing chapter, character, "
            "world info entry or note (choose with target_type; default "
            "chapter). This only stores a proposal; call story.apply_edit next "
            "to have the user approve it. Read the record first "
            "(story.get_chapter for a chapter, story.get_record for the others) "
            "and pass its version as base_version. Each edit locates text that "
            "must appear once in the record, copied from what you read; if it "
            "does not match, or matches more than once, the whole proposal is "
            "rejected, so include enough surrounding text. Notes marked as "
            "references are read-only. Every new_text and content must be only "
            "the text that belongs in the record: no greeting, no \"here is\", no "
            "explanation, no closing remark, no code fence, no frontmatter, no "
            "heading that repeats the record's name. Put all conversation in "
            "your chat reply instead. The project comes from this session's "
            "binding."
        ),
        "parameters": _parameters(
            {
                "target_type": {
                    "type": "string",
                    "enum": ["chapter", "character", "world_entry", "note"],
                    "description": "What kind of record to change. Defaults to chapter.",
                },
                "target_id": {
                    "type": "string",
                    "description": (
                        "ID of the record to change, or its exact title/name when the "
                        "name is unique."
                    ),
                },
                "chapter_id": {
                    "type": "string",
                    "description": "Chapter only; the same as target_id. Use target_id instead.",
                },
                "base_version": {
                    "type": "string",
                    "description": "The version string you read for this record.",
                },
                "edits": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "description": (
                        "Edits applied in order; each sees the result of the previous one. "
                        "A rewrite must be the only edit."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": [
                                    "replace", "insert_after", "insert_before",
                                    "append", "prepend", "rewrite",
                                ],
                                "description": (
                                    "replace: swap old_text for new_text (new_text may be empty to "
                                    "delete). insert_after / insert_before: add new_text next to "
                                    "anchor_text. append / prepend: add new_text as a new paragraph "
                                    "at the end / start. rewrite: replace the whole record text with content."
                                ),
                            },
                            "old_text": {"type": "string", "description": "replace only: text to swap out, appearing exactly once."},
                            "anchor_text": {"type": "string", "description": "insert_after / insert_before only: text to insert next to, appearing exactly once."},
                            "new_text": {"type": "string", "description": "The text to write, nothing else."},
                            "content": {"type": "string", "description": "rewrite only: the whole new text, nothing else."},
                        },
                        "required": ["op"],
                        "additionalProperties": False,
                    },
                },
            },
            ["base_version", "edits"],
        ),
    },
    "story.propose_new": {
        "name": "story.propose_new",
        "description": (
            "Propose a new record: a chapter at the end of a volume (the default), "
            "or with target_type a new character, world info entry or note. Check "
            "first with story.list_records that it does not already exist, and "
            "change an existing one with story.propose_edit instead. This only "
            "stores a proposal; call story.apply_edit next to have the user approve it. "
            "A character, world entry or note name already in use (for a note, within "
            "its category) is flagged with a name_in_use warning and gets a number "
            "after it; chapters may share a title. "
            "content must be only the record's text: no greeting, no explanation, "
            "no closing remark, no code fence, no frontmatter, no repeated title. "
            "Put all conversation in your chat reply instead. The project comes "
            "from this session's binding."
        ),
        "parameters": _parameters(
            {
                "target_type": {
                    "type": "string",
                    "enum": ["chapter", "character", "world_entry", "note"],
                    "description": "What kind of record to create. Defaults to chapter.",
                },
                "volume_id": {"type": "string", "description": "Chapter only: ID of the volume that will hold it."},
                "category_id": {"type": "string", "description": "Note only, optional: ID of an existing note category."},
                "title": {
                    "type": "string", "minLength": 1, "maxLength": 120,
                    "description": "Chapter or note title, character name, or world entry title.",
                },
                "content": {"type": "string", "minLength": 1, "description": "The record's text, nothing else."},
            },
            ["title", "content"],
        ),
    },
    "story.propose_rename": {
        "name": "story.propose_rename",
        "description": (
            "Propose a new title or name for an existing chapter, character, world "
            "info entry or note. Only the name changes: the text, id and file stay "
            "the same. A character, world entry or note name already in use (for a "
            "note, within its category) is flagged with a name_in_use warning and "
            "gets a number after it; chapters may share a title. "
            "This only stores a proposal; call story.apply_edit next to have the "
            "user approve it. To change the text as well, use story.propose_edit "
            "separately. Notes marked as references are read-only. The project "
            "comes from this session's binding."
        ),
        "parameters": _parameters(
            {
                "target_type": {
                    "type": "string",
                    "enum": ["chapter", "character", "world_entry", "note"],
                    "description": "What kind of record to rename. Defaults to chapter.",
                },
                "target_id": {
                    "type": "string",
                    "description": "ID of the record, or its exact current title/name when that is unique.",
                },
                "new_title": {
                    "type": "string", "minLength": 1, "maxLength": 120,
                    "description": "The new title or name, nothing else.",
                },
            },
            ["target_id", "new_title"],
        ),
    },
    "story.propose_delete": {
        "name": "story.propose_delete",
        "description": (
            "Propose deleting a character, world info entry or note. The record is "
            "moved to the Vault's trash folder, not erased, and the user can undo "
            "it. This only stores a proposal; call story.apply_edit next to have "
            "the user approve it: deleting always needs the user's approval each "
            "time. Chapters cannot be deleted by the Agent. Notes marked as "
            "references are read-only. If the user only wants a different name, "
            "use story.propose_rename instead. The project comes from this "
            "session's binding."
        ),
        "parameters": _parameters(
            {
                "target_type": {
                    "type": "string",
                    "enum": ["character", "world_entry", "note"],
                    "description": "What kind of record to delete.",
                },
                "target_id": {
                    "type": "string",
                    "description": "ID of the record, or its exact title/name when that is unique.",
                },
            },
            ["target_type", "target_id"],
        ),
    },
    "story.apply_edit": {
        "name": "story.apply_edit",
        "description": (
            "Carry out a proposal (an edit, a new record, a rename or a deletion). Takes only the proposal_id. The user is asked to "
            "approve the change in this chat (or has already approved it in the "
            "Story panel); it writes exactly what they approve and nothing else. "
            "If the call is blocked or declined, nothing was written: tell the user "
            "and do not retry. If it says the proposal expired or is in conflict, "
            "tell the user, then propose again instead of retrying with other content. "
            "For a new record or a rename, it reports the final title or name, which "
            "differs from the proposed one if that name was already taken."
        ),
        "parameters": _parameters(
            {"proposal_id": {"type": "string", "minLength": 1, "description": "The proposal_id returned by the proposal tool you just called."}},
            ["proposal_id"],
        ),
    },
    "story.list_records": {
        "name": "story.list_records",
        "description": (
            "List the characters, world info entries or notes of the project this "
            "session is bound to: ID, title/name, version and length only, not the "
            "text (notes also show their category and whether they are references). "
            "Use it to find what exists before proposing a new record, and to get "
            "IDs. Read one with story.get_record."
        ),
        "parameters": _parameters(
            {
                "target_type": {
                    "type": "string",
                    "enum": ["character", "world_entry", "note"],
                    "description": "Which records to list.",
                },
            },
            ["target_type"],
        ),
    },
    "story.get_record": {
        "name": "story.get_record",
        "description": (
            "Read one character, world info entry or note of the project this "
            "session is bound to, by ID or by its exact title/name when that is "
            "unique. Returns its text and its version, which story.propose_edit "
            "needs as base_version."
        ),
        "parameters": _parameters(
            {
                "target_type": {
                    "type": "string",
                    "enum": ["character", "world_entry", "note"],
                    "description": "Which kind of record to read.",
                },
                "target_id": {"type": "string", "minLength": 1, "description": "The record's ID, or its exact title/name."},
            },
            ["target_type", "target_id"],
        ),
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
