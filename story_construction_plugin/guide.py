"""Read-only description of the prompts and skills the Story plugin injects.

The Desktop "Guide" view shows exactly what the Agent is given, so everything
here is derived from the live templates and the packaged skill files rather
than copied into the front end.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .prompt_templates import (
    STORY_AGENT_PROMPT_VERSION,
    STORY_PROMPT_MAX_CHARS,
    STORY_WORKER_PROMPT_VERSION,
    render_story_agent_system_prompt,
    render_story_worker_prompt,
)
from .subagent_policy import StoryWorkerContext

SKILL_NAMESPACE = "story-construction"
_SKILLS_DIR = Path(__file__).resolve().parent / "skills"


def build_story_guide(skills_dir: Path | None = None) -> dict[str, Any]:
    return {
        "prompts": [_main_prompt(), _worker_prompt()],
        "skills": _skills(skills_dir or _SKILLS_DIR),
    }


def _main_prompt() -> dict[str, Any]:
    text = render_story_agent_system_prompt()
    return {
        "id": "global",
        "version": STORY_AGENT_PROMPT_VERSION,
        "text": text,
        "chars": len(text),
        "max_chars": STORY_PROMPT_MAX_CHARS,
    }


def _worker_prompt() -> dict[str, Any]:
    # The real prompt is rendered per task; the template is shown with the
    # task-specific fields left as visible placeholders.
    text = render_story_worker_prompt(
        StoryWorkerContext(
            project_id="<project_id>",
            chapter_id="<chapter_id>",
            goal="<goal>",
            skill_guidance="<skill_guidance>",
            source_refs=("<source_ref>",),
            parent_session_id="<parent_session_id>",
        )
    )
    return {
        "id": "worker",
        "version": STORY_WORKER_PROMPT_VERSION,
        "text": text,
        "chars": len(text),
        "max_chars": None,
    }


def _skills(skills_dir: Path) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        meta = _frontmatter(text)
        folder = skill_file.parent.name
        skills.append(
            {
                "id": folder,
                "name": f"{SKILL_NAMESPACE}:{meta.get('name') or folder}",
                "description": meta.get("description", ""),
                "text": text,
                "chars": len(text),
            }
        )
    return skills


def _frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    meta: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()
    return meta
