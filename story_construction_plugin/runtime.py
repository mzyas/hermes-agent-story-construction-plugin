"""Session-scoped Story runtime state and temporary single-profile lock."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Any

from .permissions import SessionScope, StoryPermissionGate
from .session_store import (
    SessionBindingStoreError,
    StorySessionBinding,
    StorySessionRegistry,
)


@dataclass(frozen=True, slots=True)
class StoryRuntimeStatus:
    code: str
    ready: bool
    locked_profile: str | None
    vault_root_configured: bool
    vault_is_directory: bool
    home_matches: bool
    runtime_initialized: bool = True

    def as_dict(self) -> dict[str, Any]:
        """Return diagnostics without the configured Vault path or its contents."""

        return {
            "ready": self.ready,
            "code": self.code,
            "locked_profile": self.locked_profile,
            "vault_root_configured": self.vault_root_configured,
            "vault_is_directory": self.vault_is_directory,
            "home_matches": self.home_matches,
            "runtime_initialized": self.runtime_initialized,
        }


@dataclass(slots=True)
class StoryRuntimeState:
    plugin_root: Path
    hermes_home: Path
    status: StoryRuntimeStatus
    repository: Any | None = None
    permissions: StoryPermissionGate = field(default_factory=StoryPermissionGate)
    sessions: StorySessionRegistry = field(default_factory=StorySessionRegistry)

    @property
    def ready(self) -> bool:
        return self.status.ready

    def reset(self, status: StoryRuntimeStatus) -> None:
        self.status = status
        self.repository = None
        self.permissions = StoryPermissionGate(locked_profile=status.locked_profile)
        self.sessions = StorySessionRegistry(locked_profile=status.locked_profile)


_RUNTIME_STATES: dict[tuple[str, str], StoryRuntimeState] = {}
_RUNTIME_STATES_LOCK = RLock()


def get_hermes_home() -> Path:
    """Resolve the host's current Hermes home lazily so tests and profiles can bind it."""

    from hermes_constants import get_hermes_home as resolve_hermes_home

    return Path(resolve_hermes_home())


def canonical_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve(strict=False)


def _session_state_path(hermes_home: Path) -> Path:
    return hermes_home / "plugin-data" / "story-construction" / "sessions.json"


def runtime_state_for(plugin_root: str | Path, hermes_home: str | Path) -> StoryRuntimeState | None:
    key = _runtime_key(plugin_root, hermes_home)
    with _RUNTIME_STATES_LOCK:
        return _RUNTIME_STATES.get(key)


def prepare_story_runtime(
    plugin_root: str | Path,
    settings: Mapping[str, object] | None,
    *,
    current_home: str | Path | None = None,
    repository_factory: Callable[[Path], Any] | None = None,
) -> StoryRuntimeState:
    """Validate one process-bound Story configuration and prepare its keyed state."""

    plugin_path = canonical_path(plugin_root)
    home_error = False
    try:
        current_path = canonical_path(current_home if current_home is not None else get_hermes_home())
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        current_path = plugin_path / ".runtime-home-unavailable"
        home_error = True

    key = (str(plugin_path), str(current_path))
    # One private state per call: a request in flight keeps the objects it was
    # given even when a concurrent request rebuilds the same (package, home).
    state = StoryRuntimeState(
        plugin_root=plugin_path,
        hermes_home=current_path,
        status=StoryRuntimeStatus(
            code="runtime_uninitialized",
            ready=False,
            locked_profile=None,
            vault_root_configured=False,
            vault_is_directory=False,
            home_matches=False,
        ),
    )

    raw_settings = settings if isinstance(settings, Mapping) else {}
    locked_profile = _setting_text(raw_settings, "locked_profile")
    vault_text = _setting_text(raw_settings, "vault_root")
    locked_home_text = _setting_text(raw_settings, "locked_hermes_home")
    vault_path: Path | None = None
    vault_is_directory = False
    if vault_text:
        try:
            vault_path = canonical_path(vault_text)
            vault_is_directory = vault_path.is_dir()
        except (OSError, TypeError, ValueError):
            vault_path = None

    base = {
        "locked_profile": locked_profile,
        "vault_root_configured": bool(vault_text),
        "vault_is_directory": vault_is_directory,
        "home_matches": False,
    }
    if not locked_profile or not vault_text or not locked_home_text:
        state.reset(StoryRuntimeStatus(code="configuration_incomplete", ready=False, **base))
        return _publish_state(key, state)
    if home_error:
        state.reset(StoryRuntimeStatus(code="runtime_home_unavailable", ready=False, **base))
        return _publish_state(key, state)

    try:
        locked_home = canonical_path(locked_home_text)
    except (OSError, TypeError, ValueError):
        state.reset(StoryRuntimeStatus(code="configuration_incomplete", ready=False, **base))
        return _publish_state(key, state)
    if locked_home != current_path:
        state.reset(StoryRuntimeStatus(code="hermes_home_mismatch", ready=False, **base))
        return _publish_state(key, state)
    base["home_matches"] = True
    if vault_path is None or not vault_is_directory:
        state.reset(StoryRuntimeStatus(code="vault_not_directory", ready=False, **base))
        return _publish_state(key, state)

    try:
        factory = repository_factory or _default_repository_factory
        repository = factory(vault_path)
    except Exception:
        state.reset(StoryRuntimeStatus(code="vault_unavailable", ready=False, **base))
        return _publish_state(key, state)

    try:
        sessions = StorySessionRegistry(
            _session_state_path(current_path),
            locked_profile=locked_profile,
        )
        permissions = _restore_gate(sessions, locked_profile)
    except SessionBindingStoreError:
        state.reset(
            StoryRuntimeStatus(code="binding_state_invalid", ready=False, **base)
        )
        return _publish_state(key, state)

    state.status = StoryRuntimeStatus(code="ready", ready=True, **base)
    state.repository = repository
    state.permissions = permissions
    state.sessions = sessions
    return _publish_state(key, state)


def permission_snapshot(state: StoryRuntimeState) -> StoryPermissionGate:
    """Build one gate from the durable bindings as they exist right now.

    Every call re-reads the binding file through a fresh registry, so a bind or
    unbind committed by any other registry instance or process is visible to the
    next tool call without re-registering anything. Malformed or conflicting
    binding state raises ``SessionBindingStoreError``; callers must never fall
    back to ``state.permissions``.
    """

    locked_profile = state.status.locked_profile
    sessions = StorySessionRegistry(
        _session_state_path(state.hermes_home),
        locked_profile=locked_profile,
    )
    return _restore_gate(sessions, locked_profile)


def _restore_gate(
    sessions: StorySessionRegistry, locked_profile: str | None
) -> StoryPermissionGate:
    """Bind every locked-profile row into one new gate, failing closed."""

    permissions = StoryPermissionGate(locked_profile=locked_profile)
    try:
        for binding in sessions.all():
            if binding.profile != locked_profile:
                continue
            for session_id in (binding.stored_session_id, binding.runtime_session_id):
                if session_id is None:
                    continue
                permissions.bind_session(
                    SessionScope(
                        session_id=session_id,
                        source=binding.source,
                        profile=binding.profile,
                        connection_id=binding.connection_id,
                        project_id=binding.project_id,
                    ),
                    binding.project_id,
                )
    except SessionBindingStoreError:
        raise
    except PermissionError as exc:
        # Conflicting alias claims are indistinguishable from corrupt durable
        # state: translate them into one stable store error vocabulary.
        raise SessionBindingStoreError(
            "persistent Story binding state is invalid"
        ) from exc
    return permissions


def _publish_state(key: tuple[str, str], state: StoryRuntimeState) -> StoryRuntimeState:
    """Record the latest prepared state for ``runtime_state_for`` and return it.

    Published states are never mutated afterwards, so callers that hold a
    returned state keep a consistent (repository, permissions, sessions) set.
    """

    with _RUNTIME_STATES_LOCK:
        _RUNTIME_STATES[key] = state
    return state


def _default_repository_factory(vault_path: Path) -> Any:
    from .obsidian_repository import ObsidianProjectRepository

    return ObsidianProjectRepository(vault_path)


def _runtime_key(plugin_root: str | Path, hermes_home: str | Path) -> tuple[str, str]:
    return str(canonical_path(plugin_root)), str(canonical_path(hermes_home))


def _setting_text(settings: Mapping[str, object], key: str) -> str | None:
    value = settings.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
