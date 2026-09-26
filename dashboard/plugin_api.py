"""Dashboard/Desktop REST routes for the prepared Story runtime."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi import APIRouter, HTTPException



_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
router = APIRouter()


@router.get("/status")
def status() -> dict[str, Any]:
    _runtime, state, code = _resolve_runtime_state()
    if state is None:
        return _uninitialized_status(code or "runtime_uninitialized")
    return state.status.as_dict()


@router.put("/settings")
def update_settings(body: dict[str, Any]) -> dict[str, Any]:
    """Select the writing Profile and shared Vault through the scoped transaction.

    The request body never supplies a Hermes home path; the selection is always
    resolved against the API's default home.
    """

    profile = _required_body(body, "profile")
    vault_root = _optional_body(body, "vault_root")
    _backend, profile_config, _api_runtime, _runtime_module = _backend_modules()
    try:
        profile_config.select_story_target(
            _PLUGIN_ROOT, _default_home(), profile, vault_root
        )
    except profile_config.StorySetupError as exc:
        raise HTTPException(
            status_code=_settings_error_status(exc.code),
            detail=_uninitialized_status(exc.code),
        ) from exc
    return status()


@router.get("/projects")
def list_projects(
    session_id: str | None = None,
    profile: str | None = None,
    connection_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    runtime, state = _require_runtime()
    normalized_profile = _required_value(profile, "profile")
    normalized_connection = _required_value(connection_id, "connection_id")
    try:
        if session_id is None:
            state.permissions.require_profile(normalized_profile)
        else:
            scope = _request_scope(
                runtime,
                session_id,
                normalized_profile,
                normalized_connection,
            )
            # An existing binding still has to match the complete request scope.
            state.permissions.require_bound_scope(scope, allow_unbound=True)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    projects = state.repository.list_projects()
    return {"projects": [asdict(project) for project in projects]}


@router.post("/projects")
def create_project(body: dict[str, Any]) -> dict[str, Any]:
    runtime, state = _require_runtime()
    profile = _required_body(body, "profile")
    _required_body(body, "connection_id")
    name = _required_body(body, "name")
    slug = _optional_body(body, "slug")
    try:
        state.permissions.require_profile(profile)
        with _selected_target_guard(state):
            tree = state.repository.create_project(name, slug=slug)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except _component(runtime, "repository").ProjectAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except _component(runtime, "repository").DomainValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"tree": _tree_payload(tree)}


@router.get("/projects/{project_id}")
def get_project_tree(
    project_id: str,
    session_id: str | None = None,
    profile: str | None = None,
    connection_id: str | None = None,
) -> dict[str, Any]:
    runtime, state = _require_runtime()
    scope = _request_scope(runtime, session_id, profile, connection_id, project_id=project_id)
    try:
        state.permissions.require_read(scope, project_id)
        tree = state.repository.get_project(project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except _component(runtime, "repository").NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _tree_payload(tree)


@router.get("/projects/{project_id}/chapters/{chapter_id}")
def get_chapter(
    project_id: str,
    chapter_id: str,
    session_id: str | None = None,
    profile: str | None = None,
    connection_id: str | None = None,
) -> dict[str, Any]:
    runtime, state = _require_runtime()
    scope = _request_scope(runtime, session_id, profile, connection_id, project_id=project_id)
    try:
        state.permissions.require_read(scope, project_id)
        chapter = state.repository.get_chapter(project_id, chapter_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except _component(runtime, "repository").NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"chapter": asdict(chapter)}


@router.post("/sessions/bind")
def bind_session(body: dict[str, Any]) -> dict[str, Any]:
    runtime, state = _require_runtime()
    stored_session_id = _optional_body(body, "stored_session_id")
    if stored_session_id is None:
        stored_session_id = _required_body(body, "session_id")
    runtime_session_id = _optional_body(body, "runtime_session_id")
    profile = _required_body(body, "profile")
    connection_id = _required_body(body, "connection_id")
    project_id = _required_body(body, "project_id")
    title = _optional_body(body, "title")
    permission_module = _component(runtime, "permissions")
    session_ids = _unique_session_ids(stored_session_id, runtime_session_id)
    scopes = [
        permission_module.SessionScope(
            session_id, "desktop", profile, connection_id, project_id
        )
        for session_id in session_ids
    ]
    try:
        for scope in scopes:
            state.permissions.require_bound_scope(scope, allow_unbound=True)
        tree = state.repository.get_project(project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except _component(runtime, "repository").NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    with _selected_target_guard(state):
        # The durable bind is the last fallible mutation: every later request
        # rebuilds its authorization from this file, so no in-memory permission
        # state has to be updated or rolled back here.
        binding = state.sessions.bind(
            stored_session_id=stored_session_id,
            runtime_session_id=runtime_session_id,
            profile=profile,
            connection_id=connection_id,
            source="desktop",
            project_id=tree.project.id,
            project_name=tree.project.name,
            title=title or "",
        )
    return {
        "session": asdict(binding),
        "context": {
            "project": asdict(tree.project),
            "volumes": [asdict(row) for row in tree.volumes],
            "chapters": [_summary(row, "content") for row in tree.chapters],
        },
    }


@router.get("/projects/{project_id}/sessions")
def list_project_sessions(
    project_id: str,
    profile: str | None = None,
    connection_id: str | None = None,
) -> dict[str, Any]:
    runtime, state = _require_runtime()
    normalized_profile = _required_value(profile, "profile")
    normalized_connection = _required_value(connection_id, "connection_id")
    try:
        state.permissions.require_profile(normalized_profile)
        state.repository.get_project(project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except _component(runtime, "repository").NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rows = state.sessions.list_for_project(
        project_id=project_id,
        profile=normalized_profile,
        connection_id=normalized_connection,
    )
    return {"sessions": [asdict(row) for row in rows]}


@router.delete("/projects/{project_id}/sessions/{stored_session_id}")
def delete_project_session(
    project_id: str,
    stored_session_id: str,
    profile: str | None = None,
    connection_id: str | None = None,
) -> dict[str, Any]:
    runtime, state = _require_runtime()
    normalized_stored_id = _required_value(stored_session_id, "stored_session_id")
    normalized_profile = _required_value(profile, "profile")
    normalized_connection = _required_value(connection_id, "connection_id")
    try:
        state.permissions.require_profile(normalized_profile)
        state.repository.get_project(project_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except _component(runtime, "repository").NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    binding = state.sessions.get(
        stored_session_id=normalized_stored_id,
        profile=normalized_profile,
        connection_id=normalized_connection,
    )
    if binding is None or binding.project_id != project_id:
        raise HTTPException(status_code=404, detail="Story session binding was not found")
    with _selected_target_guard(state):
        removed = state.sessions.unbind(
            stored_session_id=normalized_stored_id,
            profile=normalized_profile,
            connection_id=normalized_connection,
        )
        if removed is None:
            raise HTTPException(status_code=404, detail="Story session binding was not found")
    return {"removed": True, "stored_session_id": removed.stored_session_id}


@router.post("/projects/{project_id}/chapters/{chapter_id}/save")
def save_chapter(project_id: str, chapter_id: str, body: dict[str, Any]) -> dict[str, Any]:
    runtime, state = _require_runtime()
    save_module = _component(runtime, "save_service")
    repository_module = _component(runtime, "repository")
    request = save_module.SaveRequest(
        session_id=_required_body(body, "session_id"),
        profile=_required_body(body, "profile"),
        connection_id=_required_body(body, "connection_id"),
        project_id=project_id,
        chapter_id=chapter_id,
        content=body.get("content") if isinstance(body.get("content"), str) else "",
        expected_version=_required_body(body, "expected_version"),
        confirmed=body.get("confirmed") is True,
    )
    service = save_module.StorySaveService(state.repository, state.permissions)
    try:
        with _selected_target_guard(state):
            result = service.save(request)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=_permission_detail(exc)) from exc
    except save_module.SaveConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "version_conflict",
                "current": asdict(exc.current),
                "draft": exc.draft_content,
            },
        ) from exc
    except repository_module.NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"chapter": asdict(result.chapter)}


class _SetupFailure(Exception):
    """Known Story setup failure surfaced with its stable status code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def load_api_backend(plugin_root: Path) -> ModuleType:
    package_dir = plugin_root / 'story_construction_plugin'
    name = 'hermes_story_api_' + sha256(str(plugin_root.resolve()).encode()).hexdigest()[:16]
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(
        name, package_dir / '__init__.py',
        submodule_search_locations=[str(package_dir)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError('Story API package cannot be loaded')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _backend_modules() -> tuple[Any, Any, Any, Any]:
    """Return the API-owned backend package with its profile/api/runtime modules."""

    backend = load_api_backend(_PLUGIN_ROOT)
    profile_config = importlib.import_module(f"{backend.__name__}.profile_config")
    api_runtime = importlib.import_module(f"{backend.__name__}.api_runtime")
    runtime_module = importlib.import_module(f"{backend.__name__}.runtime")
    return backend, profile_config, api_runtime, runtime_module


def _default_home() -> Path:
    from hermes_constants import get_default_hermes_root

    return Path(get_default_hermes_root())


def _prepare_api_runtime() -> tuple[Any, Any]:
    _backend, profile_config, api_runtime, _runtime_module = _backend_modules()
    try:
        return api_runtime.prepare_api_state(_PLUGIN_ROOT, _default_home())
    except profile_config.StorySetupError as exc:
        raise _SetupFailure(exc.code) from exc


def _resolve_runtime_state() -> tuple[Any | None, Any | None, str | None]:
    try:
        runtime, state = _prepare_api_runtime()
    except _SetupFailure as exc:
        return None, None, exc.code
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None, None, "runtime_context_unavailable"
    return runtime, state, None


def _require_runtime() -> tuple[Any, Any]:
    runtime, state, code = _resolve_runtime_state()
    if state is None:
        raise HTTPException(
            status_code=503,
            detail=_uninitialized_status(code or "runtime_uninitialized"),
        )
    if not state.ready or state.repository is None:
        detail = state.status.as_dict()
        detail["message"] = "story runtime is not ready"
        raise HTTPException(status_code=503, detail=detail)
    return runtime, state


@contextmanager
def _selected_target_guard(state: Any):
    """Hold the selected-Profile guard across one API filesystem write."""

    _backend, profile_config, _api_runtime, _runtime_module = _backend_modules()
    try:
        with profile_config.selected_target_guard(
            _default_home(), state.status.locked_profile
        ):
            yield
    except profile_config.StorySetupError as exc:
        raise HTTPException(
            status_code=503, detail=_uninitialized_status(exc.code)
        ) from exc


def _component(runtime: Any, name: str) -> Any:
    package = getattr(runtime, "__package__", "")
    if not package:
        raise HTTPException(
            status_code=503,
            detail=_uninitialized_status("runtime_context_unavailable"),
        )
    return importlib.import_module(f"{package}.{name}")


def _request_scope(
    runtime: Any,
    session_id: str | None,
    profile: str | None,
    connection_id: str | None,
    *,
    project_id: str | None = None,
) -> Any:
    return _component(runtime, "permissions").SessionScope(
        session_id=_required_value(session_id, "session_id"),
        source="desktop",
        profile=_required_value(profile, "profile"),
        connection_id=_required_value(connection_id, "connection_id"),
        project_id=project_id,
    )


def _unique_session_ids(*session_ids: str | None) -> tuple[str, ...]:
    return tuple(dict.fromkeys(session_id for session_id in session_ids if session_id))


def _permission_detail(exc: PermissionError) -> str | dict[str, str]:
    code = getattr(exc, "code", None)
    if code == "profile_lock_mismatch":
        return {"code": code, "message": str(exc)}
    return str(exc)

# PUT /settings alone maps known setup failures onto HTTP semantics while
# keeping detail.code stable: invalid request input -> 422, conflict with the
# existing configuration or selection -> 409, service/target not ready -> 503.
# Every other route keeps its established contracts (the write guard included).
_SETTINGS_INVALID_INPUT_CODES = frozenset(
    {"profile_invalid", "configuration_incomplete"}
)
_SETTINGS_CONFLICT_CODES = frozenset(
    {
        "vault_mismatch",
        "version_mismatch",
        "managed_config",
        "profile_switched",
        "hermes_home_mismatch",
    }
)


def _settings_error_status(code: str) -> int:
    if code in _SETTINGS_INVALID_INPUT_CODES:
        return 422
    if code in _SETTINGS_CONFLICT_CODES:
        return 409
    return 503


def _uninitialized_status(code: str) -> dict[str, Any]:
    return {
        "ready": False,
        "code": code,
        "locked_profile": None,
        "vault_root_configured": False,
        "vault_is_directory": False,
        "home_matches": False,
        "runtime_initialized": False,
    }


def _tree_payload(tree: Any) -> dict[str, Any]:
    return {
        "project": asdict(tree.project),
        "world_info": asdict(tree.world_info) if tree.world_info else None,
        "world_info_entries": [_summary(row, "content") for row in tree.world_info_entries],
        "characters": [_summary(row, "content") for row in tree.characters],
        "categories": [asdict(row) for row in tree.categories],
        "notes": [_summary(row, "content") for row in tree.notes],
        "volumes": [asdict(row) for row in tree.volumes],
        "chapters": [_summary(row, "content") for row in tree.chapters],
    }


def _summary(row: Any, excluded_field: str) -> dict[str, Any]:
    value = asdict(row)
    value.pop(excluded_field, None)
    return value


def _required_body(body: dict[str, Any], field: str) -> str:
    return _required_value(body.get(field), field)


def _optional_body(body: dict[str, Any], field: str) -> str | None:
    value = body.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"{field} must be a string or null")
    return value.strip() or None


def _required_value(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=422, detail=f"{field} is required")
    return value.strip()
