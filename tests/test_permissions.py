"""Session and project authorization contracts for story tools."""

from __future__ import annotations

import pytest

from story_construction_plugin.permissions import (
    PermissionDenied,
    ProfileLockMismatch,
    SessionScope,
    StoryPermissionGate,
    scope_from_tool_kwargs,
)


@pytest.fixture
def gate() -> StoryPermissionGate:
    return StoryPermissionGate({"p1": ("default", "local")})


def _bound_scope() -> SessionScope:
    return SessionScope("session-1", "desktop", "default", "local", "p1")


def test_desktop_session_can_read_owned_project(gate: StoryPermissionGate) -> None:
    scope = _bound_scope()
    gate.bind_session(scope, "p1")

    gate.require_read(scope, "p1")


def test_missing_or_cross_project_scope_is_rejected(gate: StoryPermissionGate) -> None:
    scope = _bound_scope()
    gate.bind_session(scope, "p1")

    with pytest.raises(PermissionDenied, match="project_id"):
        gate.require_read(scope, "p2")
    gate.require_read(SessionScope("session-1", "desktop", "default", "local", None), "p1")


def test_unbound_session_is_rejected_even_when_request_names_project(
    gate: StoryPermissionGate,
) -> None:
    scope = SessionScope("unbound", "desktop", "default", "local", "p1")

    with pytest.raises(PermissionDenied, match="binding"):
        gate.require_read(scope, "p1")


def test_profile_or_connection_mismatch_is_rejected(gate: StoryPermissionGate) -> None:
    gate.bind_session(_bound_scope(), "p1")

    with pytest.raises(PermissionDenied, match="profile"):
        gate.require_read(SessionScope("session-1", "desktop", "other", "local", "p1"), "p1")
    with pytest.raises(PermissionDenied, match="connection"):
        gate.require_read(SessionScope("session-1", "desktop", "default", "remote", "p1"), "p1")


def test_rebinding_bound_session_with_mismatched_scope_is_rejected(
    gate: StoryPermissionGate,
) -> None:
    gate.bind_session(_bound_scope(), "p1")

    with pytest.raises(PermissionDenied, match="profile"):
        gate.bind_session(SessionScope("session-1", "desktop", "other", "local", "p1"), "p1")
    with pytest.raises(PermissionDenied, match="connection"):
        gate.bind_session(SessionScope("session-1", "desktop", "default", "remote", "p1"), "p1")
def test_locked_profile_rejects_mismatch_before_session_binding() -> None:
    gate = StoryPermissionGate(
        {"p1": ("writer", "local")},
        locked_profile="writer",
    )
    matching = SessionScope("session-1", "desktop", "writer", "local", "p1")
    mismatched = SessionScope("session-2", "desktop", "other", "local", "p1")

    gate.bind_session(matching, "p1")

    with pytest.raises(PermissionDenied, match="locked profile"):
        gate.bind_session(mismatched, "p1")
    with pytest.raises(PermissionDenied, match="locked profile"):
        gate.require_read(mismatched, "p1")
    with pytest.raises(PermissionDenied, match="locked profile"):
        gate.require_write(mismatched, "p1")


def test_locked_profile_management_accepts_only_matching_profile() -> None:
    gate = StoryPermissionGate(locked_profile="writer")

    gate.require_profile("writer")

    with pytest.raises(ProfileLockMismatch, match="locked profile"):
        gate.require_profile("other")


def test_unbind_session_returns_the_removed_exact_scope() -> None:
    gate = StoryPermissionGate()
    scope = _bound_scope()
    gate.bind_session(scope, "p1")

    removed = gate.unbind_session(scope.session_id)

    assert removed == scope
    assert gate.bound_scope(scope.session_id) is None


def test_non_desktop_session_cannot_write(gate: StoryPermissionGate) -> None:
    scope = SessionScope("session-1", "cli", "default", "local", "p1")
    gate.bind_session(scope, "p1")

    with pytest.raises(PermissionDenied, match="Desktop"):
        gate.require_write(scope, "p1")


def test_tool_kwargs_resolve_the_runtime_session_scope() -> None:
    scope = scope_from_tool_kwargs(
        session_id="s",
        source="desktop",
        profile_name="default",
        connection_id="local",
        project_id="p1",
    )

    assert scope == SessionScope("s", "desktop", "default", "local", "p1")
