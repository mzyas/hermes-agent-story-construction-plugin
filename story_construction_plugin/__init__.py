"""Hermes story-construction plugin registration entry point."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from . import runtime as _runtime
from .permissions import StoryPermissionGate
from .repository import StoryRepository
from .runtime import StoryRuntimeState
from .schemas import TOOL_SCHEMAS
from .session_store import StorySessionRegistry
from .tools import StoryToolService, _error


_SKILLS = (
    ("chapter-drafting", "Draft a chapter from cited project context."),
    ("continuity-check", "Check story continuity against retrieved project facts."),
    ("obsidian-format", "Format a confirmed chapter as Obsidian Markdown."),
)


def register_story_skills(ctx) -> None:
    skill_root = Path(__file__).with_name("skills")
    for name, description in _SKILLS:
        path = skill_root / name / "SKILL.md"
        ctx.register_skill(name, path, description, {"name": name, "description": description})


def register_story_tools(
    ctx: Any,
    repository: StoryRepository,
    permissions: StoryPermissionGate,
    *,
    permissions_provider: Callable[[], StoryPermissionGate] | None = None,
) -> StoryToolService:
    """Register story schemas with their session-scoped handlers."""

    service = StoryToolService(
        repository, permissions, permissions_provider=permissions_provider
    )
    for name, schema in TOOL_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="story",
            schema=schema,
            handler=service.handler(name),
        )
    return service


def register_story_prompt(
    ctx, registry: StorySessionRegistry | LiveStoryRuntime | None = None
) -> None:
    """Use Hermes' session-scoped frozen prompt seam for the main Agent."""

    prompt_registry = registry or StorySessionRegistry()
    ctx.register_system_prompt_section(
        "story-construction.agent",
        prompt_registry.render_system_prompt,
        position="after_memory",
        max_chars=4000,
    )


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _settings(ctx: Any) -> dict[str, object]:
    get_config = getattr(ctx, "get_config", None)
    if not callable(get_config):
        return {}
    return {
        key: get_config(key)
        for key in ("locked_profile", "vault_root", "locked_hermes_home")
    }


def _mark_uncached(check: Callable[[], bool]) -> Callable[[], bool]:
    """Ask Hermes not to cache a config-backed readiness check.

    Without the marker Hermes serves a cached result for about 30 seconds, so a
    session created right after the selection is saved could still miss the
    tools. The helper is host-internal, so its absence only costs that delay.
    """

    try:
        from tools.registry import no_cache_check_fn

        return no_cache_check_fn(check)
    except Exception:
        return check


class LiveStoryRuntime:
    """Resolve the Story runtime from the current settings on every use.

    A plugin loads once per process, but the Story selection can be saved after
    that (first setup, changing the Vault). Tools are therefore registered
    unconditionally and gated by ``check_fn``, which Hermes evaluates whenever a
    session builds its tool list. A ready state is reused until the Hermes home
    or the settings change; a not-ready state holds no Vault, so it is cheap to
    recompute each time.
    """

    def __init__(self, ctx: Any, plugin_root: Path) -> None:
        self._ctx = ctx
        self._plugin_root = plugin_root
        self._lock = RLock()
        self._ready: dict[
            tuple[object, ...], tuple[StoryRuntimeState, StoryToolService]
        ] = {}

        def story_runtime_ready() -> bool:
            try:
                return self.current().ready
            except Exception:
                return False

        # One stable function object: Hermes tracks uncached checks by identity.
        self.check_fn = _mark_uncached(story_runtime_ready)

    def current(self) -> StoryRuntimeState:
        return self._resolve()[0]

    def handler(self, name: str) -> Callable[..., str]:
        def handle(args: Mapping[str, Any] | None = None, **kwargs: Any) -> str:
            try:
                state, service = self._resolve()
            except Exception:
                return _error("runtime_unavailable", "story runtime is not ready")
            if service is None:
                return _error(state.status.code, "story runtime is not ready")
            return service.handle(name, args, **kwargs)

        return handle

    def render_system_prompt(self, session_info: Mapping[str, object]) -> str:
        state = self.current()
        if not state.ready:
            return ""
        return state.sessions.render_system_prompt(session_info)

    def _key(self, settings: Mapping[str, object]) -> tuple[object, ...]:
        try:
            home: object = str(_runtime.canonical_path(_runtime.get_hermes_home()))
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            home = None
        return (
            home,
            settings.get("locked_profile"),
            settings.get("vault_root"),
            settings.get("locked_hermes_home"),
        )

    def _resolve(self) -> tuple[StoryRuntimeState, StoryToolService | None]:
        settings = _settings(self._ctx)
        key = self._key(settings)
        with self._lock:
            hit = self._ready.get(key)
        if hit is not None:
            return hit
        state = _runtime.prepare_story_runtime(self._plugin_root, settings)
        if not state.ready:
            return state, None
        # Each tool call re-reads the durable bindings through this provider;
        # binds and unbinds never need a new service.
        service = StoryToolService(
            state.repository,
            state.permissions,
            permissions_provider=lambda: _runtime.permission_snapshot(state),
        )
        with self._lock:
            if len(self._ready) >= 8:
                self._ready.clear()
            self._ready[key] = (state, service)
        return state, service


def register_live_story_tools(ctx: Any, live: LiveStoryRuntime) -> None:
    """Register every story tool behind the live readiness check."""

    for name, schema in TOOL_SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="story",
            schema=schema,
            handler=live.handler(name),
            check_fn=live.check_fn,
        )


def register_story_backend(ctx) -> LiveStoryRuntime:
    """Register story tools that appear once the runtime is ready."""

    live = LiveStoryRuntime(ctx, _plugin_root())
    live.current()  # publish the initial state for diagnostics
    register_live_story_tools(ctx, live)
    return live


def register(ctx) -> None:
    """Register Skills and the stable, session-scoped Story Agent prompt."""

    register_story_skills(ctx)
    live = register_story_backend(ctx)
    register_story_prompt(ctx, live)
