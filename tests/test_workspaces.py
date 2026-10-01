"""Workspace folders and Hermes project links for Story projects."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from story_construction_plugin.workspaces import (
    FALLBACK_DIRECTORY,
    WorkspaceError,
    WorkspaceLinkRegistry,
    WorkspaceLinkStoreError,
    ensure_project_folder,
    project_folder_name,
    resolve_workspace_base,
)


def _config(backend: str = "local", cwd: str = "") -> dict:
    return {"terminal": {"backend": backend, "cwd": cwd}}


def test_a_configured_local_workspace_hosts_a_story_subfolder(tmp_path: Path) -> None:
    workspace = tmp_path / "work"
    workspace.mkdir()

    base = resolve_workspace_base(tmp_path / "home", _config(cwd=str(workspace)))

    assert base == workspace.resolve() / "story"


@pytest.mark.parametrize("cwd", ["", ".", "relative/dir", "MISSING"])
def test_an_unusable_workspace_falls_back_to_the_profile_home(tmp_path: Path, cwd: str) -> None:
    if cwd == "MISSING":
        cwd = str(tmp_path / "does-not-exist")

    base = resolve_workspace_base(tmp_path / "home", _config(cwd=cwd))

    assert base == (tmp_path / "home").resolve() / FALLBACK_DIRECTORY


def test_a_container_path_is_not_treated_as_a_host_folder(tmp_path: Path) -> None:
    base = resolve_workspace_base(tmp_path / "home", _config("docker", str(tmp_path)))

    assert base == (tmp_path / "home").resolve() / FALLBACK_DIRECTORY


def test_missing_terminal_config_uses_the_fallback(tmp_path: Path) -> None:
    assert resolve_workspace_base(tmp_path / "home", {}) == (tmp_path / "home").resolve() / FALLBACK_DIRECTORY


def test_an_ssh_terminal_is_refused(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError) as error:
        resolve_workspace_base(tmp_path / "home", _config("ssh", "/home/me"))

    assert error.value.code == "workspace_unsupported_backend"


def test_project_folder_names_cannot_escape_the_base() -> None:
    assert project_folder_name("novel") == "novel"
    assert project_folder_name("我的小说") == "我的小说"
    assert "/" not in project_folder_name("a/b") and "\\" not in project_folder_name("a\\b")
    assert project_folder_name("../escape") == "escape"
    for bad in ("", "...", "  ", "/", ".."):
        with pytest.raises(WorkspaceError):
            project_folder_name(bad)


def test_ensure_creates_once_and_then_reuses_the_folder(tmp_path: Path) -> None:
    base = tmp_path / "base"

    first, created_first = ensure_project_folder(base, "novel")
    (first / "draft.txt").write_text("keep me", encoding="utf-8")
    second, created_second = ensure_project_folder(base, "novel")

    assert first == second == (base / "novel").resolve()
    assert (created_first, created_second) == (True, False)
    assert (second / "draft.txt").read_text(encoding="utf-8") == "keep me"


def test_a_file_in_the_way_is_reported_not_replaced(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "novel").write_text("not a folder", encoding="utf-8")

    with pytest.raises(WorkspaceError) as error:
        ensure_project_folder(base, "novel")

    assert error.value.code == "workspace_unavailable"
    assert (base / "novel").read_text(encoding="utf-8") == "not a folder"


@pytest.fixture
def registry(tmp_path: Path) -> WorkspaceLinkRegistry:
    return WorkspaceLinkRegistry(tmp_path / "plugin-data" / "workspaces.json")


def _link(registry: WorkspaceLinkRegistry, **overrides):
    values = {
        "profile": "writer", "connection_id": "local", "project_id": "novel",
        "hermes_project_id": "p_1", "folder": "/work/novel",
    }
    return registry.link(**{**values, **overrides})


def test_links_are_scoped_by_profile_connection_and_project(registry) -> None:
    _link(registry)
    _link(registry, connection_id="remote", hermes_project_id="p_2")

    got = registry.get(profile="writer", connection_id="local", project_id="novel")
    assert got is not None and got.hermes_project_id == "p_1" and got.archived is False
    assert registry.get(profile="writer", connection_id="remote", project_id="novel").hermes_project_id == "p_2"
    assert registry.get(profile="other", connection_id="local", project_id="novel") is None
    assert registry.get(profile="writer", connection_id="local", project_id="other") is None


def test_relinking_keeps_the_creation_time_and_clears_archived(registry) -> None:
    first = _link(registry)
    registry.mark_archived(profile="writer", connection_id="local", project_id="novel")
    again = _link(registry, hermes_project_id="p_9")

    assert again.created_at == first.created_at
    assert again.hermes_project_id == "p_9" and again.archived is False


def test_archiving_marks_the_link_and_ignores_unknown_projects(registry) -> None:
    _link(registry)

    archived = registry.mark_archived(profile="writer", connection_id="local", project_id="novel")

    assert archived is not None and archived.archived is True
    assert registry.get(profile="writer", connection_id="local", project_id="novel").archived is True
    assert registry.mark_archived(profile="writer", connection_id="local", project_id="none") is None


def test_corrupt_state_is_reported_and_left_untouched(registry) -> None:
    registry.path.parent.mkdir(parents=True)
    registry.path.write_text("{not json", encoding="utf-8")

    with pytest.raises(WorkspaceLinkStoreError):
        registry.get(profile="writer", connection_id="local", project_id="novel")
    with pytest.raises(WorkspaceLinkStoreError):
        _link(registry)
    assert registry.path.read_text(encoding="utf-8") == "{not json"


def test_concurrent_links_all_survive(registry) -> None:
    def add(number: int) -> None:
        _link(registry, project_id=f"novel-{number}", hermes_project_id=f"p_{number}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(24)))

    for number in range(24):
        assert registry.get(profile="writer", connection_id="local", project_id=f"novel-{number}") is not None
