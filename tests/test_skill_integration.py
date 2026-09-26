"""Hermes Skill registration contracts for the story plugin."""

from __future__ import annotations

from pathlib import Path

from story_construction_plugin import register_story_skills


class CaptureContext:
    def __init__(self) -> None:
        self.skills = []

    def register_skill(self, name, path, description="", frontmatter=None):
        self.skills.append({
            "name": name,
            "path": Path(path),
            "description": description,
            "frontmatter": dict(frontmatter or {}),
        })


def test_story_skills_register_as_unqualified_local_names() -> None:
    context = CaptureContext()

    register_story_skills(context)

    assert {skill["name"] for skill in context.skills} == {
        "chapter-drafting",
        "continuity-check",
        "obsidian-format",
    }
    assert all(skill["path"].name == "SKILL.md" for skill in context.skills)
    assert all(skill["path"].is_file() for skill in context.skills)
    assert all(":" not in skill["name"] for skill in context.skills)


def test_story_skill_metadata_is_explicit_and_namespaced_by_host() -> None:
    context = CaptureContext()

    register_story_skills(context)

    for skill in context.skills:
        assert skill["frontmatter"]["name"] == skill["name"]
        assert skill["description"]
