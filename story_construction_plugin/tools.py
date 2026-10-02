"""Session-scoped, read-only story retrieval tools."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from functools import partial
from typing import Any, Callable, Mapping

from .edits import EditError
from .permissions import SessionScope, StoryPermissionGate, scope_from_tool_kwargs
from .proposal_service import ProposalError, StoryProposalService
from .proposal_store import ProposalStoreError
from .repository import NotFoundError, RepositoryError, StoryRepository
from .session_store import SessionBindingStoreError


SESSION_PROJECT_TOOL = "story.get_session_project"
PROPOSE_EDIT_TOOL = "story.propose_edit"
PROPOSE_CHAPTER_TOOL = "story.propose_chapter"
APPLY_EDIT_TOOL = "story.apply_edit"
# The project of these tools comes from the session's binding, never from the model.
SESSION_RESOLVED_TOOLS = frozenset(
    {SESSION_PROJECT_TOOL, PROPOSE_EDIT_TOOL, PROPOSE_CHAPTER_TOOL, APPLY_EDIT_TOOL}
)
DEFAULT_SEARCH_LIMIT = 20
MAX_SEARCH_LIMIT = 50


class StoryToolService:
    def __init__(
        self,
        repository: StoryRepository,
        permissions: StoryPermissionGate,
        *,
        permissions_provider: Callable[[], StoryPermissionGate] | None = None,
        proposals_provider: Callable[[], StoryProposalService] | None = None,
    ) -> None:
        self.repository = repository
        self.permissions = permissions
        self._permissions_provider = permissions_provider
        self._proposals_provider = proposals_provider

    def handle(self, name: str, args: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
        payload = dict(args or {})
        project_id = str(payload.get("project_id") or "").strip()
        resolve_from_session = name in SESSION_RESOLVED_TOOLS
        if not project_id and not resolve_from_session:
            return _error("missing_project_id", "project_id is required")
        scope_kwargs = dict(kwargs)
        try:
            gate = (
                self._permissions_provider()
                if self._permissions_provider is not None
                else self.permissions
            )
            scope = _scope_from_gate(gate, **scope_kwargs)
            bound = None
            if resolve_from_session:
                # The binding, not the model, names the project: arguments are
                # ignored so a session can never ask for another project.
                bound = gate.bound_scope(scope.session_id)
                if bound is None:
                    return _error(
                        "session_not_bound",
                        "this session is not bound to a Story project",
                    )
                project_id = bound.project_id
            gate.require_read(scope, project_id)
            data = self._dispatch(name, project_id, payload, bound or scope)
            return _success(project_id, data)
        except SessionBindingStoreError:
            return _error(
                "binding_state_invalid", "persistent Story binding state is invalid"
            )
        except PermissionError as exc:
            return _error(str(getattr(exc, "code", "permission_denied")), str(exc))
        except NotFoundError as exc:
            return _error("not_found", str(exc), project_id=project_id)
        except RepositoryError as exc:
            return _error("repository_error", str(exc), project_id=project_id)
        except (ProposalError, EditError) as exc:
            extra = {k: v for k, v in exc.as_dict().items() if k not in ("code", "message")}
            return _error(exc.code, str(exc), project_id=project_id, **extra)
        except ProposalStoreError:
            return _error(
                "proposal_state_invalid", "persistent Story proposal state is invalid"
            )
        except (KeyError, TypeError, ValueError) as exc:
            return _error("invalid_request", str(exc), project_id=project_id)
        except Exception as exc:  # Tool handlers must return structured failures.
            return _error("internal_error", f"story tool failed: {type(exc).__name__}", project_id=project_id)

    def handler(self, name: str) -> Callable[..., str]:
        return partial(self.handle, name)

    def _dispatch(
        self, name: str, project_id: str, payload: dict[str, Any], scope: SessionScope
    ) -> Any:
        if name in (PROPOSE_EDIT_TOOL, PROPOSE_CHAPTER_TOOL, APPLY_EDIT_TOOL):
            return self._proposal_tool(name, project_id, payload, scope)
        if name == SESSION_PROJECT_TOOL:
            tree = self.repository.get_project(project_id)
            return {
                "project": tree.project,
                "volumes": tree.volumes,
                "chapters": [_chapter_summary(chapter) for chapter in tree.chapters],
            }
        if name == "story.get_project":
            return self.repository.get_project(project_id)
        if name == "story.get_world_info":
            tree = self.repository.get_project(project_id)
            return {"world_info": tree.world_info, "entries": tree.world_info_entries}
        if name == "story.search_world_info":
            return _bounded(
                self.repository.search_world_info(project_id, _query(payload)), payload
            )
        if name == "story.get_character":
            return self.repository.get_character(project_id, _required(payload, "character_id"))
        if name == "story.list_volumes":
            return self.repository.list_volumes(project_id)
        if name == "story.list_chapters":
            chapters = self.repository.list_chapters(project_id, payload.get("volume_id") or None)
            return [_chapter_summary(chapter) for chapter in chapters]
        if name == "story.get_chapter":
            return self.repository.get_chapter(project_id, _required(payload, "chapter_id"))
        if name == "story.search_notes":
            return _bounded(self.repository.search_notes(project_id, _query(payload)), payload)
        if name == "story.search_reference_notes":
            return _bounded(
                self.repository.search_reference_notes(project_id, _query(payload)), payload
            )
        raise ValueError(f"unknown story tool: {name}")


    def _proposal_tool(
        self, name: str, project_id: str, payload: dict[str, Any], scope: SessionScope
    ) -> Any:
        if self._proposals_provider is None:
            raise ProposalError("proposals_unavailable", "chapter proposals are not available")
        service = self._proposals_provider()
        common = {
            "project_id": project_id,
            "profile": scope.profile,
            "connection_id": scope.connection_id,
        }
        if name == APPLY_EDIT_TOOL:
            return service.apply(proposal_id=_required(payload, "proposal_id"), **common)
        common["session_id"] = scope.session_id
        if name == PROPOSE_CHAPTER_TOOL:
            return service.propose_chapter(
                volume_id=_required(payload, "volume_id"),
                title=payload.get("title"),
                content=payload.get("content"),
                **common,
            )
        return service.propose_edit(
            chapter_id=_required(payload, "chapter_id"),
            base_version=payload.get("base_version"),
            raw_edits=payload.get("edits"),
            **common,
        )


def _scope_from_gate(gate: StoryPermissionGate, **kwargs: Any) -> SessionScope:
    """Recover the durable binding identity when the runtime supplied none."""
    scope = scope_from_tool_kwargs(**kwargs)
    if scope.source or scope.profile or scope.connection_id:
        return scope
    bound = gate.bound_scope(scope.session_id)
    return bound if bound is not None else scope


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _query(payload: Mapping[str, Any]) -> str:
    return _required(payload, "query")


def _bounded(rows: Any, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Cap a search result set so one call cannot return every record."""
    raw = payload.get("limit")
    try:
        limit = int(raw) if raw is not None else DEFAULT_SEARCH_LIMIT
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer") from None
    if limit < 1:
        raise ValueError("limit must be at least 1")
    limit = min(limit, MAX_SEARCH_LIMIT)
    rows = tuple(rows)
    return {
        "total": len(rows),
        "returned": min(len(rows), limit),
        "truncated": len(rows) > limit,
        "results": rows[:limit],
    }


def _chapter_summary(chapter: Any) -> dict[str, Any]:
    """Chapter metadata only; chapter text is read through story.get_chapter."""
    return {
        "id": chapter.id,
        "project_id": chapter.project_id,
        "volume_id": chapter.volume_id,
        "title": chapter.title,
        "version": chapter.version,
        "content_length": len(chapter.content),
    }


def _success(project_id: str, data: Any) -> str:
    return json.dumps({"ok": True, "project_id": project_id, "data": _jsonable(data)}, ensure_ascii=False)


def _error(code: str, message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": {"code": code, "message": message}, **extra}, ensure_ascii=False)


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
