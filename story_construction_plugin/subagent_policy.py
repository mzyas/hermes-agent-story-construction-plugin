"""Explicit parent/child context envelopes for story analysis workers."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class StoryWorkerContext:
    project_id: str
    chapter_id: str | None
    goal: str
    skill_guidance: str
    source_refs: tuple[str, ...]
    parent_session_id: str | None = None


def render_story_worker_context(request: StoryWorkerContext) -> str:
    if not request.project_id.strip():
        raise ValueError("project_id is required")
    if not request.goal.strip():
        raise ValueError("worker goal is required")
    refs = tuple(_safe_source_ref(ref) for ref in request.source_refs)
    parent = request.parent_session_id or "<not provided>"
    chapter = request.chapter_id or "<project-level>"
    rendered_refs = "\n".join(f"- {ref}" for ref in refs) or "- <none>"
    return (
        "# Story Worker Context\n"
        f"project_id: {request.project_id}\n"
        f"chapter_id: {chapter}\n"
        f"parent_session_id: {parent}\n"
        f"goal: {request.goal.strip()}\n\n"
        "source_refs:\n"
        f"{rendered_refs}\n\n"
        "skill_guidance:\n"
        f"{request.skill_guidance.strip() or '<none>'}\n\n"
        "This is a fresh child context. The worker does not have the parent transcript "
        "or unlisted parent tool results. Read project data only, do not save files, "
        "and return a structured analysis for the parent Agent."
    )


def validate_story_worker_result(
    result: Mapping[str, object], *, project_id: str, chapter_id: str | None
) -> None:
    if not isinstance(result, Mapping):
        raise ValueError("worker result must be a mapping")
    if str(result.get("project_id") or "") != project_id:
        raise ValueError("worker result project_id does not match")
    if chapter_id is not None and str(result.get("chapter_id") or "") != chapter_id:
        raise ValueError("worker result chapter_id does not match")
    if chapter_id is None and result.get("chapter_id") not in (None, ""):
        raise ValueError("worker result chapter_id is outside the requested scope")
    if not isinstance(result.get("summary"), str):
        raise ValueError("worker result summary is required")
    refs = result.get("source_refs")
    if not isinstance(refs, (list, tuple)) or not refs:
        raise ValueError("worker result source_refs are required")
    for ref in refs:
        _safe_source_ref(ref)


def _safe_source_ref(ref: object) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("source_refs must contain non-empty strings")
    value = ref.strip().replace("\\", "/")
    if value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("source_refs must stay within the project")
    return value
