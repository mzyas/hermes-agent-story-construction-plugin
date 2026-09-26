"""Dashboard API behavior stays bound to the prepared single-profile runtime."""

from __future__ import annotations
import importlib
import importlib.util
import json
import shutil
import sys
import threading
import types

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from hermes_env import read_user_config_raw  # lazy real-SDK passthrough

from story_construction_plugin.domain import Chapter, Character, Note, Project, Volume, WorldInfo, WorldInfoEntry
from story_construction_plugin.profile_config import select_story_target

pytestmark = pytest.mark.hermes_integration


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "story-construction"
REAL_PLUGIN_YAML = PACKAGE_ROOT / "plugin.yaml"


class FakeRepository:
    def __init__(self, repository_module) -> None:
        # Raise the backend package's exception classes: the dashboard routes
        # catch those exact class objects, not the real-package copies imported
        # by tests.
        self._repository_module = repository_module
        self.project = Project(id="p1", name="Novel", world_info_id="w1")
        self.chapter = Chapter(
            id="ch1", project_id="p1", volume_id="v1", title="Opening",
            content="full chapter body", source_ref="chapters/ch1.md", version="v1",
        )
        self.created: list[tuple[str, str | None]] = []
        self._created_projects: dict[str, object] = {}

    def create_project(self, name, *, slug=None):
        repository = self._repository_module
        project_id = repository.normalize_project_slug(name, slug)
        if project_id == self.project.id or project_id in self._created_projects:
            raise repository.ProjectAlreadyExistsError(f"project {project_id!r} already exists")
        project, volumes = repository.create_project_with_default_volume(project_id, name.strip())
        tree = repository.ProjectTree(project, None, (), (), (), (), volumes, ())
        self.created.append((name, slug))
        self._created_projects[project_id] = tree
        return tree

    def list_projects(self):
        created = tuple(tree.project for tree in self._created_projects.values())
        return (self.project, *created)

    def get_project(self, project_id):
        if project_id == "p1":
            return self._repository_module.ProjectTree(
                project=self.project,
                world_info=WorldInfo(id="w1", name="World", project_id="p1"),
                world_info_entries=(WorldInfoEntry(id="e1", world_info_id="w1", title="Rule", content="secret"),),
                characters=(Character(id="c1", project_id="p1", name="Hero", content="secret"),),
                categories=(),
                notes=(Note(id="n1", project_id="p1", title="Ref", content="secret"),),
                volumes=(Volume(id="v1", project_id="p1", title="Volume I"),),
                chapters=(self.chapter,),
            )
        try:
            return self._created_projects[project_id]
        except KeyError as exc:
            raise self._repository_module.NotFoundError(f"project {project_id!r} was not found") from exc

    def get_chapter(self, project_id, chapter_id):
        assert (project_id, chapter_id) == ("p1", "ch1")
        return self.chapter

    def save_chapter(self, project_id, chapter_id, content, *, expected_version):
        assert (project_id, chapter_id) == ("p1", "ch1")
        assert expected_version == self.chapter.version
        self.chapter = Chapter("ch1", "p1", "v1", "Opening", content, "chapters/ch1.md", "v2")
        return self.chapter


def _build_profile_lab(monkeypatch, tmp_path: Path, api_package_root: Path):
    """Temp default home, two named Profiles, one Vault, and real plugin manifests."""
    default_home = tmp_path / "hermes"
    target_home = default_home / "profiles" / "writer"
    other_home = default_home / "profiles" / "other"
    vault = tmp_path / "vault"
    target_plugin_root = target_home / "plugins" / PLUGIN_ID
    other_plugin_root = other_home / "plugins" / PLUGIN_ID

    default_home.mkdir(parents=True)
    vault.mkdir()
    for folder in (target_plugin_root, other_plugin_root):
        folder.mkdir(parents=True)
        shutil.copy(REAL_PLUGIN_YAML, folder / "plugin.yaml")
    for profile_home in (target_home, other_home):
        # The named Profile's config.yaml doubles as its Hermes identity marker.
        (profile_home / "config.yaml").write_text(
            "plugins:\n"
            "  enabled:\n"
            f"    - {PLUGIN_ID}\n",
            encoding="utf-8",
        )
    (default_home / "config.yaml").write_text("agent: {}\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(default_home))
    monkeypatch.delenv("HERMES_MANAGED", raising=False)
    monkeypatch.delenv("HERMES_MANAGED_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: default_home)
    return types.SimpleNamespace(
        default_home=default_home,
        target_home=target_home,
        other_home=other_home,
        vault=vault,
        api_package_root=api_package_root,
        target_plugin_root=target_plugin_root,
        other_plugin_root=other_plugin_root,
    )


def _ready_runtime(monkeypatch, tmp_path: Path):
    from dashboard import plugin_api

    lab = _build_profile_lab(monkeypatch, tmp_path, PACKAGE_ROOT)
    select_story_target(PACKAGE_ROOT, lab.default_home, "writer", str(lab.vault))
    backend = plugin_api.load_api_backend(PACKAGE_ROOT)
    runtime_module = importlib.import_module(f"{backend.__name__}.runtime")
    repository_module = importlib.import_module(f"{backend.__name__}.repository")
    repository = FakeRepository(repository_module)
    monkeypatch.setattr(
        runtime_module, "_default_repository_factory", lambda _: repository
    )
    _runtime, state = plugin_api._require_runtime()
    assert state.ready
    return plugin_api, state, repository


def _scope(session_id="s1", profile="writer", connection_id="local"):
    return {
        "session_id": session_id,
        "profile": profile,
        "connection_id": connection_id,
    }


def _assert_http_error(call, status_code: int, code: str | None = None):
    with pytest.raises(HTTPException) as error:
        call()
    assert error.value.status_code == status_code
    if code is not None:
        assert error.value.detail["code"] == code


def _request_state(plugin_api):
    """Every request prepares its authorization from the durable binding file."""
    _runtime, state = plugin_api._require_runtime()
    return state


def test_uninitialized_runtime_rejects_dashboard_read_and_write(monkeypatch, tmp_path: Path) -> None:
    from dashboard import plugin_api

    home = tmp_path / "uninitialized-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_MANAGED", raising=False)
    monkeypatch.delenv("HERMES_MANAGED_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: home)
    scope = _scope()

    status = plugin_api.status()
    assert status["code"] == "profile_not_selected"
    _assert_http_error(lambda: plugin_api.list_projects(**scope), 503, "profile_not_selected")
    _assert_http_error(
        lambda: plugin_api.save_chapter("p1", "ch1", {**scope, "content": "x", "expected_version": "v1", "confirmed": True}),
        503,
        "profile_not_selected",
    )


def test_dashboard_status_is_ready_without_returning_vault_path(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    status = plugin_api.status()
    assert status["ready"] is True
    assert status["code"] == "ready"
    assert "vault_root" not in status
    assert str(tmp_path / "vault") not in repr(status)


def test_project_discovery_requires_locked_profile_but_not_a_session(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, _, repository = _ready_runtime(monkeypatch, tmp_path)

    projects = plugin_api.list_projects(profile="writer", connection_id="local")

    assert projects == {"projects": [asdict(repository.project)]}


def test_create_project_requires_locked_profile_but_not_a_session(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, repository = _ready_runtime(monkeypatch, tmp_path)

    created = plugin_api.create_project({
        "name": "New Novel", "slug": "new-novel",
        "profile": "writer", "connection_id": "local",
    })

    assert created["tree"]["project"]["id"] == "new-novel"
    assert repository.created == [("New Novel", "new-novel")]


def test_create_project_rejects_locked_profile_mismatch(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.create_project({
            "name": "New Novel", "profile": "other", "connection_id": "local",
        }),
        403,
        "profile_lock_mismatch",
    )


def test_create_project_maps_duplicate_to_conflict(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)
    body = {
        "name": "New Novel", "slug": "new-novel",
        "profile": "writer", "connection_id": "local",
    }
    plugin_api.create_project(body)

    _assert_http_error(lambda: plugin_api.create_project(body), 409)


def test_create_project_maps_invalid_slug_to_unprocessable(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.create_project({
            "name": "New Novel", "slug": "../new-novel",
            "profile": "writer", "connection_id": "local",
        }),
        422,
    )


def test_create_project_rejects_non_string_optional_slug(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.create_project({
            "name": "New Novel", "slug": 7,
            "profile": "writer", "connection_id": "local",
        }),
        422,
    )


def test_project_tree_requires_a_bound_session(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.get_project_tree("p1", **_scope("unbound")),
        403,
    )


def test_dashboard_rejects_locked_profile_mismatch_before_binding(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.bind_session({**_scope(profile="other"), "project_id": "p1"}),
        403,
        "profile_lock_mismatch",
    )

def test_profile_mismatch_is_rejected_for_read_bind_and_save(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)
    plugin_api.bind_session({**_scope(), "project_id": "p1"})

    _assert_http_error(
        lambda: plugin_api.get_project_tree("p1", **_scope(profile="other")),
        403,
    )
    _assert_http_error(
        lambda: plugin_api.bind_session({**_scope(profile="other"), "project_id": "p1"}),
        403,
    )
    _assert_http_error(
        lambda: plugin_api.save_chapter(
            "p1",
            "ch1",
            {**_scope(profile="other"), "content": "x", "expected_version": "v1", "confirmed": True},
        ),
        403,
    )
    _assert_http_error(
        lambda: plugin_api.bind_session({**_scope(connection_id="remote"), "project_id": "p1"}),
        403,
    )
    _assert_http_error(
        lambda: plugin_api.save_chapter(
            "p1",
            "ch1",
            {**_scope(connection_id="remote"), "content": "x", "expected_version": "v1", "confirmed": True},
        ),
        403,
    )

def test_connection_mismatch_is_rejected_for_bound_read(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)
    plugin_api.bind_session({**_scope(), "project_id": "p1"})

    _assert_http_error(
        lambda: plugin_api.get_chapter("p1", "ch1", **_scope(connection_id="remote")),
        403,
    )


def test_bind_persists_stored_identity_and_lists_only_project_scope(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)

    result = plugin_api.bind_session({
        **_scope("stored-1"), "runtime_session_id": "runtime-1",
        "stored_session_id": "stored-1", "project_id": "p1",
        "title": "Story: Novel",
    })
    state.sessions.bind(
        stored_session_id="other-project",
        profile="writer",
        connection_id="local",
        project_id="p2",
    )
    state.sessions.bind(
        stored_session_id="other-connection",
        profile="writer",
        connection_id="remote",
        project_id="p1",
    )
    listed = plugin_api.list_project_sessions(
        "p1", profile="writer", connection_id="local"
    )

    assert result["session"]["stored_session_id"] == "stored-1"
    assert result["context"]["chapters"][0]["id"] == "ch1"
    assert "content" not in result["context"]["chapters"][0]
    assert [row["stored_session_id"] for row in listed["sessions"]] == ["stored-1"]
    assert _request_state(plugin_api).permissions.bound_scope("runtime-1").project_id == "p1"


def test_project_session_list_returns_missing_project(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.list_project_sessions(
            "missing", profile="writer", connection_id="local"
        ),
        404,
    )


def test_delete_stale_binding_does_not_create_replacement(monkeypatch, tmp_path: Path) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    plugin_api.bind_session({
        **_scope("stored-1"), "stored_session_id": "stored-1", "project_id": "p1",
    })
    # Sibling row sharing stored-1 as its runtime alias must survive the delete
    # untouched (same profile and connection so per-request preparation can
    # represent both rows in the permission gate).
    state.sessions.bind(
        stored_session_id="stored-2",
        runtime_session_id="stored-1",
        profile="writer",
        connection_id="local",
        project_id="p1",
    )

    removed = plugin_api.delete_project_session(
        "p1", "stored-1", profile="writer", connection_id="local"
    )

    assert removed == {"removed": True, "stored_session_id": "stored-1"}
    assert [
        row["stored_session_id"]
        for row in plugin_api.list_project_sessions(
            "p1", profile="writer", connection_id="local"
        )["sessions"]
    ] == ["stored-2"]
    assert _request_state(plugin_api).permissions.bound_scope("stored-1") is not None
    _assert_http_error(
        lambda: plugin_api.delete_project_session(
            "p1", "stored-1", profile="writer", connection_id="local"
        ),
        404,
    )


def test_conflicting_stored_id_across_connections_fails_closed(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    plugin_api.bind_session({
        **_scope("stored-1"), "stored_session_id": "stored-1", "project_id": "p1",
    })
    first = state.sessions.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    )
    store_module = importlib.import_module(type(state.sessions).__module__)

    # One session id cannot hold two connection scopes in the permission gate;
    # the store refuses the conflicting row instead of writing a state that
    # preparation cannot represent.
    with pytest.raises(store_module.SessionBindingStoreError):
        state.sessions.bind(
            stored_session_id="stored-1",
            profile="writer",
            connection_id="remote",
            project_id="p1",
        )
    assert (
        state.sessions.get(
            stored_session_id="stored-1",
            profile="writer",
            connection_id="local",
        )
        == first
    )

    # A file that already disagrees (hand-edited) still fails closed per request.
    path = state.sessions.path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["bindings"].append({**asdict(first), "connection_id": "remote"})
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _assert_http_error(
        lambda: plugin_api.delete_project_session(
            "p1", "stored-1", profile="writer", connection_id="local"
        ),
        503,
        "binding_state_invalid",
    )


def test_delete_session_unbinds_stored_and_runtime_ids(monkeypatch, tmp_path: Path) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    plugin_api.bind_session({
        **_scope("stored-1"), "stored_session_id": "stored-1",
        "runtime_session_id": "runtime-1", "project_id": "p1",
    })

    plugin_api.delete_project_session(
        "p1", "stored-1", profile="writer", connection_id="local"
    )

    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("stored-1") is None
    assert permissions.bound_scope("runtime-1") is None


def test_rebinding_then_delete_revokes_superseded_runtime_alias(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    base = {
        "stored_session_id": "stored-1",
        "profile": "writer",
        "connection_id": "local",
        "project_id": "p1",
    }
    plugin_api.bind_session({**base, "runtime_session_id": "runtime-1"})
    plugin_api.bind_session({**base, "runtime_session_id": "runtime-2"})

    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("runtime-1") is None
    assert permissions.bound_scope("runtime-2").project_id == "p1"
    assert plugin_api.get_project_tree("p1", **_scope("runtime-2"))["project"]["id"] == "p1"
    _assert_http_error(
        lambda: plugin_api.get_project_tree("p1", **_scope("runtime-1")),
        403,
    )

    plugin_api.delete_project_session(
        "p1", "stored-1", profile="writer", connection_id="local"
    )

    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("stored-1") is None
    assert permissions.bound_scope("runtime-1") is None
    assert permissions.bound_scope("runtime-2") is None


def test_rebinding_keeps_alias_referenced_by_another_durable_record(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    common = {
        "profile": "writer",
        "connection_id": "local",
        "project_id": "p1",
    }
    plugin_api.bind_session({
        **common,
        "stored_session_id": "stored-1",
        "runtime_session_id": "runtime-old",
    })
    plugin_api.bind_session({
        **common,
        "stored_session_id": "stored-2",
        "runtime_session_id": "runtime-shared",
    })
    plugin_api.bind_session({
        **common,
        "stored_session_id": "stored-1",
        "runtime_session_id": "runtime-shared",
    })

    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("runtime-old") is None
    assert permissions.bound_scope("runtime-shared").project_id == "p1"

    plugin_api.delete_project_session(
        "p1", "stored-1", profile="writer", connection_id="local"
    )

    assert _request_state(plugin_api).permissions.bound_scope(
        "runtime-shared"
    ).project_id == "p1"

    plugin_api.delete_project_session(
        "p1", "stored-2", profile="writer", connection_id="local"
    )

    assert _request_state(plugin_api).permissions.bound_scope("runtime-shared") is None


def test_registry_persist_failure_does_not_leave_permission_aliases(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    # Patch the class: every request re-prepares fresh registry/gate instances.
    store_module = importlib.import_module(type(state.sessions).__module__)

    def fail_persist(self) -> None:
        raise store_module.SessionBindingStoreError("injected persistence failure")

    monkeypatch.setattr(type(state.sessions), "_persist", fail_persist)

    with pytest.raises(store_module.SessionBindingStoreError, match="injected persistence failure"):
        plugin_api.bind_session({
            "stored_session_id": "stored-1",
            "runtime_session_id": "runtime-1",
            "profile": "writer",
            "connection_id": "local",
            "project_id": "p1",
        })

    assert state.sessions.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    ) is None
    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("stored-1") is None
    assert permissions.bound_scope("runtime-1") is None


def test_permission_validation_failure_leaves_registry_unchanged(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    gate_type = type(state.permissions)
    original_require = gate_type.require_bound_scope

    def fail_runtime_alias(self, scope, project_id=None, *, allow_unbound=False):
        if scope.session_id == "runtime-1":
            raise PermissionError("injected permission failure")
        return original_require(self, scope, project_id, allow_unbound=allow_unbound)

    monkeypatch.setattr(gate_type, "require_bound_scope", fail_runtime_alias)

    _assert_http_error(
        lambda: plugin_api.bind_session({
            "stored_session_id": "stored-1",
            "runtime_session_id": "runtime-1",
            "profile": "writer",
            "connection_id": "local",
            "project_id": "p1",
        }),
        403,
    )

    assert state.sessions.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    ) is None
    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("stored-1") is None
    assert permissions.bound_scope("runtime-1") is None


def test_failed_rebind_restores_exact_previous_binding_and_aliases(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    common = {
        "stored_session_id": "stored-1",
        "profile": "writer",
        "connection_id": "local",
        "project_id": "p1",
    }
    plugin_api.bind_session({**common, "runtime_session_id": "runtime-old"})
    previous = state.sessions.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    )
    assert previous is not None
    # Another durable record already owns the requested runtime alias for a
    # different project; the claim must fail before anything is rewritten.
    state.sessions.bind(
        stored_session_id="stored-2",
        runtime_session_id="runtime-new",
        profile="writer",
        connection_id="local",
        project_id="p2",
    )

    _assert_http_error(
        lambda: plugin_api.bind_session({
            **common,
            "runtime_session_id": "runtime-new",
        }),
        403,
    )

    assert state.sessions.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    ) == previous
    permissions = _request_state(plugin_api).permissions
    assert permissions.bound_scope("stored-1").project_id == "p1"
    assert permissions.bound_scope("runtime-old").project_id == "p1"
    assert permissions.bound_scope("runtime-new").project_id == "p2"
    assert permissions.bound_scope("stored-2").project_id == "p2"


def test_new_request_state_sees_bind_and_unbind_immediately(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, _ = _ready_runtime(monkeypatch, tmp_path)
    plugin_api.bind_session({
        **_scope("stored-1"), "stored_session_id": "stored-1", "project_id": "p1",
    })

    # A held registry instance and every later request both reload the file.
    assert (
        state.sessions.get(
            stored_session_id="stored-1",
            profile="writer",
            connection_id="local",
        )
        is not None
    )
    listed = _request_state(plugin_api).sessions.list_for_project(
        project_id="p1", profile="writer", connection_id="local"
    )
    assert [row.stored_session_id for row in listed] == ["stored-1"]

    plugin_api.delete_project_session(
        "p1", "stored-1", profile="writer", connection_id="local"
    )

    assert (
        _request_state(plugin_api).sessions.list_for_project(
            project_id="p1", profile="writer", connection_id="local"
        )
        == ()
    )
    assert (
        state.sessions.get(
            stored_session_id="stored-1",
            profile="writer",
            connection_id="local",
        )
        is None
    )


def test_locked_scope_allows_bind_summary_lazy_read_and_confirmed_save(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, repository = _ready_runtime(monkeypatch, tmp_path)
    scope = _scope()

    projects = plugin_api.list_projects(**scope)
    binding = plugin_api.bind_session({**scope, "project_id": "p1"})
    tree = plugin_api.get_project_tree("p1", **scope)
    chapter = plugin_api.get_chapter("p1", "ch1", **scope)
    saved = plugin_api.save_chapter(
        "p1",
        "ch1",
        {**scope, "content": "confirmed draft", "expected_version": "v1", "confirmed": True},
    )

    assert projects == {"projects": [asdict(repository.project)]}
    assert binding["session"]["stored_session_id"] == scope["session_id"]
    assert binding["session"]["runtime_session_id"] is None
    assert binding["session"]["project_id"] == "p1"
    assert "content" not in tree["chapters"][0]
    assert chapter["chapter"]["content"] == "full chapter body"
    assert saved["chapter"]["content"] == "confirmed draft"


def test_unbound_save_is_rejected(monkeypatch, tmp_path: Path) -> None:
    plugin_api, _, _ = _ready_runtime(monkeypatch, tmp_path)

    _assert_http_error(
        lambda: plugin_api.save_chapter(
            "p1",
            "ch1",
            {**_scope("unbound"), "content": "x", "expected_version": "v1", "confirmed": True},
        ),
        403,
    )


def _load_file_module(name: str, path: Path, package_root: Path | None = None):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
        submodule_search_locations=[str(package_root)] if package_root else None,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    if package_root:
        module.__package__ = name
        module.__path__ = [str(package_root)]
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _settings_node(raw: dict) -> dict:
    node = raw.setdefault("plugins", {}).setdefault("entries", {}).setdefault(
        PLUGIN_ID, {}
    ).setdefault("settings", {})
    return node


@pytest.fixture
def prepared_homes(monkeypatch, tmp_path: Path):
    """Temp API package copy + real default/target config; no Agent pre-registration."""
    copy_root = tmp_path / "api-package"
    (copy_root / "dashboard").mkdir(parents=True)
    shutil.copy(REAL_PLUGIN_YAML, copy_root / "plugin.yaml")
    shutil.copytree(
        PACKAGE_ROOT / "story_construction_plugin",
        copy_root / "story_construction_plugin",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy(
        PACKAGE_ROOT / "dashboard" / "plugin_api.py",
        copy_root / "dashboard" / "plugin_api.py",
    )
    lab = _build_profile_lab(monkeypatch, tmp_path, copy_root)
    select_story_target(copy_root, lab.default_home, "writer", str(lab.vault))
    api_name = f"hermes_dashboard_plugin_story-construction-prepare-{tmp_path.name}"
    lab.dashboard = _load_file_module(api_name, copy_root / "dashboard" / "plugin_api.py")
    lab.backend_name = "hermes_story_api_" + sha256(
        str(copy_root.resolve()).encode()
    ).hexdigest()[:16]
    yield lab
    sys.modules.pop(api_name, None)
    for name in tuple(sys.modules):
        if name == lab.backend_name or name.startswith(f"{lab.backend_name}."):
            sys.modules.pop(name, None)


def test_dashboard_prepares_without_gateway_register(prepared_homes):
    dashboard, vault = prepared_homes.dashboard, prepared_homes.vault
    before = tuple(sys.path)
    assert dashboard.status()['code'] == 'ready'
    response = dashboard.create_project({
        'profile': 'writer', 'connection_id': 'local', 'name': 'Novel', 'slug': 'novel'
    })
    assert response['tree']['project']['id'] == 'novel'
    assert (vault / 'novel').is_dir()
    assert tuple(sys.path) == before


def test_status_reports_specific_missing_agent(prepared_homes):
    shutil.rmtree(prepared_homes.target_plugin_root)
    assert prepared_homes.dashboard.status()['code'] == 'agent_not_installed'
    _assert_http_error(
        lambda: prepared_homes.dashboard.create_project({
            'profile': 'writer', 'connection_id': 'local', 'name': 'Novel'
        }),
        503, 'agent_not_installed',
    )


def _arrange_not_enabled(homes, monkeypatch):
    (homes.target_home / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - other-plugin\n", encoding="utf-8"
    )


def _arrange_version_mismatch(homes, monkeypatch):
    manifest_path = homes.target_plugin_root / "plugin.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["version"] = "999.0.0"
    _write_yaml(manifest_path, data)


def _arrange_missing_settings(homes, monkeypatch):
    (homes.target_home / "config.yaml").write_text(
        "plugins:\n  enabled:\n" f"    - {PLUGIN_ID}\n", encoding="utf-8"
    )


def _arrange_vault_mismatch(homes, monkeypatch):
    other_vault = homes.default_home.parent / "other-vault"
    other_vault.mkdir()
    raw = read_user_config_raw(homes.target_home / "config.yaml")
    _settings_node(raw)["vault_root"] = str(other_vault)
    _write_yaml(homes.target_home / "config.yaml", raw)


def _arrange_invalid_binding_file(homes, monkeypatch):
    path = homes.target_home / "plugin-data" / PLUGIN_ID / "sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")


def _arrange_no_selected_profile(homes, monkeypatch):
    _write_yaml(homes.default_home / "config.yaml", {"agent": {}})


def _arrange_missing_shared_vault(homes, monkeypatch):
    raw = read_user_config_raw(homes.default_home / "config.yaml")
    settings = _settings_node(raw)
    assert settings.pop("vault_root", None) is not None
    assert settings.get("selected_profile") is not None
    _write_yaml(homes.default_home / "config.yaml", raw)


SETUP_CASES = [
    ("not_enabled", _arrange_not_enabled, "agent_not_enabled"),
    ("version_mismatch", _arrange_version_mismatch, "version_mismatch"),
    ("missing_settings", _arrange_missing_settings, "configuration_incomplete"),
    ("missing_shared_vault", _arrange_missing_shared_vault, "configuration_incomplete"),
    ("vault_mismatch", _arrange_vault_mismatch, "vault_mismatch"),
    ("invalid_binding_file", _arrange_invalid_binding_file, "binding_state_invalid"),
    ("no_selected_profile", _arrange_no_selected_profile, "profile_not_selected"),
]


@pytest.mark.parametrize(
    "name, arrange, code", SETUP_CASES, ids=[case[0] for case in SETUP_CASES]
)
def test_status_reports_specific_setup_failures(
    prepared_homes, monkeypatch, name, arrange, code,
):
    arrange(prepared_homes, monkeypatch)
    assert prepared_homes.dashboard.status()["code"] == code
    _assert_http_error(
        lambda: prepared_homes.dashboard.create_project({
            "profile": "writer", "connection_id": "local", "name": "Novel",
        }),
        503, code,
    )


def test_put_settings_updates_config_without_accepting_hermes_home(prepared_homes):
    dashboard = prepared_homes.dashboard
    response = dashboard.update_settings({
        "profile": "other",
        "vault_root": str(prepared_homes.vault),
        "hermes_home": str(prepared_homes.default_home.parent / "evil-home"),
    })

    assert response["ready"] is True
    assert response["locked_profile"] == "other"
    default_raw = read_user_config_raw(prepared_homes.default_home / "config.yaml")
    assert _settings_node(default_raw)["selected_profile"] == "other"
    other_raw = read_user_config_raw(prepared_homes.other_home / "config.yaml")
    other_settings = _settings_node(other_raw)
    assert other_settings["locked_profile"] == "other"
    # The request-supplied hermes_home must be ignored entirely.
    assert other_settings["locked_hermes_home"] == str(
        prepared_homes.other_home.resolve()
    )
    assert other_settings["vault_root"] == str(prepared_homes.vault.resolve())


def _arrange_no_stored_vault(homes, monkeypatch, tmp_path):
    """Both homes forget the shared vault: the next select is a first-time partial."""

    for home in (homes.default_home, homes.target_home):
        raw = read_user_config_raw(home / "config.yaml")
        _settings_node(raw).pop("vault_root", None)
        _write_yaml(home / "config.yaml", raw)


def _arrange_alt_vault(homes, monkeypatch, tmp_path):
    (tmp_path / "other-vault").mkdir()


def _arrange_managed_system(homes, monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED", "nix")


SETTINGS_ERROR_CASES = [
    # PUT /settings error semantics: invalid input -> 422, config or
    # profile-switch conflict -> 409, service/target not ready -> 503.
    ("invalid_profile_name", 422, "profile_invalid", None,
     lambda homes, tmp_path: {"profile": "../writer"}),
    ("first_selection_without_vault", 422, "configuration_incomplete", _arrange_no_stored_vault,
     lambda homes, tmp_path: {"profile": "writer"}),
    ("vault_conflicts_with_selection", 409, "vault_mismatch", _arrange_alt_vault,
     lambda homes, tmp_path: {"profile": "writer", "vault_root": str(tmp_path / "other-vault")}),
    ("installed_versions_conflict", 409, "version_mismatch",
     lambda homes, monkeypatch, tmp_path: _arrange_version_mismatch(homes, monkeypatch),
     lambda homes, tmp_path: {"profile": "writer", "vault_root": str(homes.vault)}),
    ("managed_config_conflict", 409, "managed_config",
     lambda homes, monkeypatch, tmp_path: _arrange_managed_system(homes, monkeypatch),
     lambda homes, tmp_path: {"profile": "writer", "vault_root": str(homes.vault)}),
    ("unknown_profile_not_ready", 503, "profile_not_found", None,
     lambda homes, tmp_path: {"profile": "ghost-profile", "vault_root": str(homes.vault)}),
    ("agent_disabled_not_ready", 503, "agent_not_enabled",
     lambda homes, monkeypatch, tmp_path: _arrange_not_enabled(homes, monkeypatch),
     lambda homes, tmp_path: {"profile": "writer", "vault_root": str(homes.vault)}),
    ("vault_directory_missing", 503, "vault_not_directory", None,
     lambda homes, tmp_path: {"profile": "other", "vault_root": str(tmp_path / "no-such-vault")}),
]


@pytest.mark.parametrize(
    "name, status, code, arrange, body",
    SETTINGS_ERROR_CASES,
    ids=[case[0] for case in SETTINGS_ERROR_CASES],
)
def test_put_settings_maps_setup_errors_to_http_semantics(
    prepared_homes, monkeypatch, tmp_path, name, status, code, arrange, body,
):
    if arrange is not None:
        arrange(prepared_homes, monkeypatch, tmp_path)
    _assert_http_error(
        lambda: prepared_homes.dashboard.update_settings(body(prepared_homes, tmp_path)),
        status, code,
    )


def test_put_settings_failure_keeps_status_as_status_object(prepared_homes, monkeypatch):
    _arrange_version_mismatch(prepared_homes, monkeypatch)
    _assert_http_error(
        lambda: prepared_homes.dashboard.update_settings({
            "profile": "writer", "vault_root": str(prepared_homes.vault),
        }),
        409, "version_mismatch",
    )
    # GET /status keeps returning its status object for the known setup error.
    status = prepared_homes.dashboard.status()
    assert status["code"] == "version_mismatch"
    assert status["ready"] is False


def test_switch_cannot_commit_while_create_holds_guard(prepared_homes, monkeypatch):
    dashboard = prepared_homes.dashboard
    backend = dashboard.load_api_backend(dashboard._PLUGIN_ROOT)
    repository_module = importlib.import_module(f"{backend.__name__}.repository")
    runtime_module = importlib.import_module(f"{backend.__name__}.runtime")
    repository = FakeRepository(repository_module)
    inside = threading.Event()
    release = threading.Event()
    create_project = repository.create_project

    def slow_create(name, *, slug=None):
        inside.set()
        assert release.wait(timeout=10)
        return create_project(name, slug=slug)

    repository.create_project = slow_create
    monkeypatch.setattr(
        runtime_module, "_default_repository_factory", lambda _: repository
    )

    barrier = threading.Barrier(2)
    switch_done = threading.Event()
    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def run_create() -> None:
        try:
            barrier.wait(timeout=10)
            results["create"] = dashboard.create_project({
                "profile": "writer", "connection_id": "local", "name": "Novel", "slug": "novel",
            })
        except BaseException as exc:  # noqa: BLE001  re-raised on the main thread
            errors.append(exc)
        finally:
            release.set()

    def run_switch() -> None:
        try:
            barrier.wait(timeout=10)
            results["switch"] = dashboard.update_settings({"profile": "other"})
        except BaseException as exc:  # noqa: BLE001  re-raised on the main thread
            errors.append(exc)
        finally:
            switch_done.set()

    threads = [threading.Thread(target=run_create), threading.Thread(target=run_switch)]
    try:
        for thread in threads:
            thread.start()
        assert inside.wait(timeout=10)
        # The switch must not be able to commit while the create holds the guard.
        assert not switch_done.wait(timeout=0.5)
        assert "switch" not in results
    finally:
        release.set()
        for thread in threads:
            thread.join(timeout=10)

    assert not errors, errors
    assert "switch" in results
    assert results["create"]["tree"]["project"]["id"] == "novel"
    assert dashboard.status()["locked_profile"] == "other"


def test_guard_rejects_write_when_selection_already_switched(
    monkeypatch, tmp_path: Path,
) -> None:
    plugin_api, state, repository = _ready_runtime(monkeypatch, tmp_path)
    default_home = tmp_path / "hermes"
    vault = tmp_path / "vault"
    gate_type = type(state.permissions)
    require_profile = gate_type.require_profile

    def require_then_switch(self, profile):
        require_profile(self, profile)
        # A switch commits between runtime preparation and the write's guard.
        select_story_target(PACKAGE_ROOT, default_home, "other", str(vault))

    monkeypatch.setattr(gate_type, "require_profile", require_then_switch)

    _assert_http_error(
        lambda: plugin_api.create_project({
            "profile": "writer", "connection_id": "local", "name": "Novel", "slug": "novel",
        }),
        503,
        "profile_switched",
    )
    assert repository.created == []
