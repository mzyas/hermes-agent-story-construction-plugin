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
        "record-format",
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


def test_the_prompt_points_only_to_skills_that_are_registered() -> None:
    import re

    from story_construction_plugin.prompt_templates import render_story_agent_system_prompt

    context = CaptureContext()
    register_story_skills(context)
    registered = {skill["name"] for skill in context.skills}

    named = set(re.findall(r"story-construction:([a-z][a-z-]*)", render_story_agent_system_prompt()))

    assert named == {"record-format"}
    assert named <= registered


def test_the_format_skill_carries_the_rules_the_prompt_no_longer_spells_out() -> None:
    context = CaptureContext()
    register_story_skills(context)
    path = next(skill["path"] for skill in context.skills if skill["name"] == "record-format")
    text = " ".join(path.read_text(encoding="utf-8").split())

    for rule in ("no greeting", "no code fence", "no frontmatter", "repeats the", "replace", "rewrite", "base_version"):
        assert rule in text, rule
    for kind in ("chapter", "character", "world entry", "note"):
        assert kind in text, kind


def test_the_essential_rule_stays_in_the_tool_descriptions_when_the_skill_is_not_read() -> None:
    from story_construction_plugin.schemas import TOOL_SCHEMAS

    for name in ("story.propose_edit", "story.propose_new"):
        description = TOOL_SCHEMAS[name]["description"]
        assert "no greeting" in description and "no code fence" in description, name
