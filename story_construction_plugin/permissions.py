"""Fail-closed session and project authorization for story tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class PermissionDenied(PermissionError):
    """A story request is outside the session scope granted by the backend."""


class ProfileLockMismatch(PermissionDenied):
    """A request declares a profile other than the runtime's configured profile."""

    code = "profile_lock_mismatch"


@dataclass(frozen=True, slots=True)
class SessionScope:
    session_id: str
    source: str
    profile: str
    connection_id: str
    project_id: str | None


def scope_from_tool_kwargs(**kwargs: object) -> SessionScope:
    return SessionScope(
        session_id=str(kwargs.get("session_id") or "").strip(),
        source=str(kwargs.get("source") or kwargs.get("platform") or "").strip().lower(),
        profile=str(kwargs.get("profile") or kwargs.get("profile_name") or "").strip(),
        connection_id=str(kwargs.get("connection_id") or "").strip(),
        project_id=_optional_text(kwargs.get("project_id")),
    )


class StoryPermissionGate:
    """Validate every request against a backend-known session binding."""

    def __init__(
        self,
        project_owners: Mapping[str, tuple[str, str]] | None = None,
        *,
        locked_profile: str | None = None,
    ) -> None:
        self._project_owners = dict(project_owners or {})
        self._locked_profile = _optional_text(locked_profile)
        self._session_scopes: dict[str, SessionScope] = {}

    def require_profile(self, profile: str) -> None:
        normalized = str(profile or "").strip()
        if not normalized:
            raise PermissionDenied("profile is required")
        if self._locked_profile is not None and normalized != self._locked_profile:
            raise ProfileLockMismatch("session profile does not match the locked profile")

    def bind_session(self, scope: SessionScope, project_id: str) -> None:
        self._require_scope_identity(scope)
        if not project_id:
            raise PermissionDenied("project_id is required")
        current = self._session_scopes.get(scope.session_id)
        if current is not None:
            self._require_same_scope(current, scope)
            if current.project_id != project_id:
                raise PermissionDenied("a story session cannot be rebound to another project")
        self._require_owner(scope, project_id)
        self._session_scopes[scope.session_id] = SessionScope(
            session_id=scope.session_id,
            source=scope.source,
            profile=scope.profile,
            connection_id=scope.connection_id,
            project_id=project_id,
        )

    def unbind_session(self, session_id: str) -> SessionScope | None:
        return self._session_scopes.pop(session_id, None)

    def bound_scope(self, session_id: str) -> SessionScope | None:
        return self._session_scopes.get(session_id)

    def require_bound_scope(
        self,
        scope: SessionScope,
        project_id: str | None = None,
        *,
        allow_unbound: bool = False,
    ) -> SessionScope | None:
        """Require exact session/source/profile/connection identity and optional project."""

        self._require_scope_identity(scope)
        bound = self._session_scopes.get(scope.session_id)
        if bound is None:
            if allow_unbound:
                return None
            raise PermissionDenied("the session has no required project binding")
        self._require_same_scope(bound, scope)
        if scope.project_id is not None and scope.project_id != bound.project_id:
            raise PermissionDenied("requested project_id is outside the session scope")
        if project_id is not None and project_id != bound.project_id:
            raise PermissionDenied("requested project_id is outside the session scope")
        return bound

    def require_read(self, scope: SessionScope, project_id: str) -> None:
        bound = self.require_bound_scope(scope, project_id)
        assert bound is not None
        self._require_owner(bound, project_id)

    def require_write(self, scope: SessionScope, project_id: str) -> None:
        self.require_read(scope, project_id)
        if scope.source != "desktop":
            raise PermissionDenied("chapter writes require a Desktop session")

    def _require_scope_identity(self, scope: SessionScope) -> None:
        if not scope.session_id:
            raise PermissionDenied("session_id is required")
        if not scope.source:
            raise PermissionDenied("source is required")
        self.require_profile(scope.profile)
        if not scope.connection_id:
            raise PermissionDenied("connection_id is required")

    @staticmethod
    def _require_same_scope(bound: SessionScope, request: SessionScope) -> None:
        if bound.source != request.source:
            raise PermissionDenied("session source does not match its story binding")
        if bound.profile != request.profile:
            raise PermissionDenied("session profile does not match its story binding")
        if bound.connection_id != request.connection_id:
            raise PermissionDenied("session connection does not match its story binding")

    def _require_owner(self, scope: SessionScope, project_id: str) -> None:
        if self._project_owners and project_id not in self._project_owners:
            raise PermissionDenied("project is not registered for this story session")
        owner = self._project_owners.get(project_id)
        if owner is None:
            return
        expected_profile, expected_connection = owner
        if scope.profile != expected_profile:
            raise PermissionDenied("session profile does not own the project")
        if scope.connection_id != expected_connection:
            raise PermissionDenied("session connection does not own the project")


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
