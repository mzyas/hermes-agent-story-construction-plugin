"""Session-scoped, read-only story retrieval tools."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from functools import partial
from typing import Any, Callable, Mapping

from .permissions import StoryPermissionGate, scope_from_tool_kwargs
from .repository import NotFoundError, RepositoryError, StoryRepository
from .session_store import SessionBindingStoreError


def _schema(properties: dict[str, dict[str, str]], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_PROJECT = {"project_id": {"type": "string", "description": "Current story project ID."}}
_QUERY = {"query": {"type": "string", "description": "Text to search for."}}

TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "story.get_project": {"name": "story.get_project", "schema": _schema(_PROJECT, ["project_id"])},
    "story.get_world_info": {"name": "story.get_world_info", "schema": _schema(_PROJECT, ["project_id"])},
    "story.search_world_info": {"name": "story.search_world_info", "schema": _schema({**_PROJECT, **_QUERY}, ["project_id", "query"])},
    "story.get_character": {"name": "story.get_character", "schema": _schema({**_PROJECT, "character_id": {"type": "string", "description": "Character ID."}}, ["project_id", "character_id"])},
    "story.list_volumes": {"name": "story.list_volumes", "schema": _schema(_PROJECT, ["project_id"])},
    "story.list_chapters": {"name": "story.list_chapters", "schema": _schema({**_PROJECT, "volume_id": {"type": "string", "description": "Optional volume ID."}}, ["project_id"])},
    "story.get_chapter": {"name": "story.get_chapter", "schema": _schema({**_PROJECT, "chapter_id": {"type": "string", "description": "Chapter ID."}}, ["project_id", "chapter_id"])},
    "story.search_notes": {"name": "story.search_notes", "schema": _schema({**_PROJECT, **_QUERY}, ["project_id", "query"])},
    "story.search_reference_notes": {"name": "story.search_reference_notes", "schema": _schema({**_PROJECT, **_QUERY}, ["project_id", "query"])},
}


class StoryToolService:
    def __init__(
        self,
        repository: StoryRepository,
        permissions: StoryPermissionGate,
        *,
        permissions_provider: Callable[[], StoryPermissionGate] | None = None,
    ) -> None:
        self.repository = repository
        self.permissions = permissions
        self._permissions_provider = permissions_provider

    def handle(self, name: str, args: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
        payload = dict(args or {})
        project_id = str(payload.get("project_id") or "").strip()
        if not project_id:
            return _error("missing_project_id", "project_id is required")
        scope_kwargs = dict(kwargs)
        scope = scope_from_tool_kwargs(**scope_kwargs)
        try:
            gate = (
                self._permissions_provider()
                if self._permissions_provider is not None
                else self.permissions
            )
            gate.require_read(scope, project_id)
            data = self._dispatch(name, project_id, payload)
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
        except (KeyError, TypeError, ValueError) as exc:
            return _error("invalid_request", str(exc), project_id=project_id)
        except Exception as exc:  # Tool handlers must return structured failures.
            return _error("internal_error", f"story tool failed: {type(exc).__name__}", project_id=project_id)

    def handler(self, name: str) -> Callable[..., str]:
        return partial(self.handle, name)

    def _dispatch(self, name: str, project_id: str, payload: dict[str, Any]) -> Any:
        if name == "story.get_project":
            return self.repository.get_project(project_id)
        if name == "story.get_world_info":
            tree = self.repository.get_project(project_id)
            return {"world_info": tree.world_info, "entries": tree.world_info_entries}
        if name == "story.search_world_info":
            return self.repository.search_world_info(project_id, str(payload.get("query") or ""))
        if name == "story.get_character":
            return self.repository.get_character(project_id, _required(payload, "character_id"))
        if name == "story.list_volumes":
            return self.repository.list_volumes(project_id)
        if name == "story.list_chapters":
            return self.repository.list_chapters(project_id, payload.get("volume_id") or None)
        if name == "story.get_chapter":
            return self.repository.get_chapter(project_id, _required(payload, "chapter_id"))
        if name == "story.search_notes":
            return self.repository.search_notes(project_id, str(payload.get("query") or ""))
        if name == "story.search_reference_notes":
            return self.repository.search_reference_notes(project_id, str(payload.get("query") or ""))
        raise ValueError(f"unknown story tool: {name}")


def register_story_tools(
    ctx: Any,
    repository: StoryRepository,
    permissions: StoryPermissionGate,
    *,
    permissions_provider: Callable[[], StoryPermissionGate] | None = None,
) -> StoryToolService:
    service = StoryToolService(
        repository, permissions, permissions_provider=permissions_provider
    )
    for name, definition in TOOL_SCHEMAS.items():
        parameters = definition["schema"]
        ctx.register_tool(
            name=name,
            toolset="story",
            schema={
                "name": name,
                "description": "Scoped story project read.",
                "parameters": parameters,
            },
            handler=service.handler(name),
            description=parameters.get("description", "Scoped story project read."),
        )
    return service


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


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
