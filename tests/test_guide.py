"""The read-only guide shows the live prompts and packaged skills."""

from __future__ import annotations

from pathlib import Path

from story_construction_plugin import _SKILLS
from story_construction_plugin.guide import build_story_guide
from story_construction_plugin.prompt_templates import (
    STORY_PROMPT_MAX_CHARS,
    render_story_agent_system_prompt,
)


def test_guide_lists_main_and_worker_prompts_with_versions_and_limits() -> None:
    guide = build_story_guide()
    prompts = {item["id"]: item for item in guide["prompts"]}

    main = prompts["global"]
    assert main["text"] == render_story_agent_system_prompt()
    assert main["chars"] == len(main["text"])
    assert main["max_chars"] == STORY_PROMPT_MAX_CHARS
    assert main["version"] in main["text"]
    assert main["injected"] is True

    worker = prompts["worker"]
    assert worker["version"] in worker["text"]
    assert "<goal>" in worker["text"]
    assert worker["max_chars"] is None
    assert worker["injected"] is False


def test_guide_lists_every_packaged_skill_with_namespaced_name() -> None:
    skills = {item["id"]: item for item in build_story_guide()["skills"]}

    assert {"chapter-drafting", "continuity-check", "obsidian-format", "record-format"} <= set(skills)
    drafting = skills["chapter-drafting"]
    assert drafting["name"] == "story-construction:chapter-drafting"
    assert drafting["description"]
    assert drafting["text"].startswith("---")


def test_guide_skill_without_frontmatter_falls_back_to_folder_name(tmp_path: Path) -> None:
    skill = tmp_path / "plain" / "SKILL.md"
    skill.parent.mkdir()
    skill.write_text("# Plain\nbody", encoding="utf-8")

    (entry,) = build_story_guide(tmp_path)["skills"]

    assert entry["name"] == "story-construction:plain"
    assert entry["description"] == ""


def test_guide_skills_match_what_is_registered_with_hermes() -> None:
    skills = {item["id"]: item for item in build_story_guide()["skills"]}

    assert set(skills) == {name for name, _description in _SKILLS}
    for name, description in _SKILLS:
        assert skills[name]["description"] == description
