from pathlib import Path
import threading

import pytest

from story_construction_plugin.session_store import (
    SessionBindingStoreError,
    StorySessionRegistry,
)


def _bind(
    registry: StorySessionRegistry,
    *,
    profile: str = "writer",
    connection: str = "local",
):
    return registry.bind(
        stored_session_id="stored-1",
        runtime_session_id="runtime-1",
        profile=profile,
        connection_id=connection,
        source="desktop",
        project_id="novel",
        project_name="Novel",
        title="Story: Novel",
    )


def test_binding_survives_registry_recreation(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    _bind(StorySessionRegistry(path, locked_profile="writer"))

    restored = StorySessionRegistry(path, locked_profile="writer")

    assert restored.get(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    ).project_id == "novel"
    assert [
        row.stored_session_id
        for row in restored.list_for_project(
            project_id="novel",
            profile="writer",
            connection_id="local",
        )
    ] == ["stored-1"]


def test_bindings_are_isolated_a_b_a(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    registry = StorySessionRegistry(path)
    _bind(registry, profile="writer-a", connection="local")
    _bind(registry, profile="writer-b", connection="remote")

    assert len(
        registry.list_for_project(
            project_id="novel",
            profile="writer-a",
            connection_id="local",
        )
    ) == 1
    assert len(
        registry.list_for_project(
            project_id="novel",
            profile="writer-b",
            connection_id="remote",
        )
    ) == 1
    assert len(
        registry.list_for_project(
            project_id="novel",
            profile="writer-a",
            connection_id="local",
        )
    ) == 1
    assert (
        registry.list_for_project(
            project_id="novel",
            profile="writer-a",
            connection_id="remote",
        )
        == ()
    )


def test_corrupt_binding_file_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(SessionBindingStoreError, match="binding state"):
        StorySessionRegistry(path, locked_profile="writer")


def test_unbind_removes_only_exact_scope(tmp_path: Path) -> None:
    registry = StorySessionRegistry(tmp_path / "sessions.json")
    _bind(registry, profile="writer", connection="local")

    removed = registry.unbind(
        stored_session_id="stored-1",
        profile="writer",
        connection_id="local",
    )

    assert removed is not None
    assert registry.all() == ()


def test_two_instances_keep_both_confirmed_bindings(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    left = StorySessionRegistry(path, locked_profile="writer")
    right = StorySessionRegistry(path, locked_profile="writer")
    left.bind(
        stored_session_id="s1",
        runtime_session_id="r1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    right.bind(
        stored_session_id="s2",
        runtime_session_id="r2",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p2",
    )

    assert {row.stored_session_id for row in left.all()} == {"s1", "s2"}


def test_removed_file_cannot_leave_stale_binding(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    registry = StorySessionRegistry(path, locked_profile="writer")
    registry.bind(
        stored_session_id="s1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p1",
    )
    path.unlink()

    assert registry.all() == ()


def test_alias_claim_conflict_rejects_and_keeps_first_row(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    registry = StorySessionRegistry(path, locked_profile="writer")
    _bind(registry)
    before = path.read_bytes()

    with pytest.raises(SessionBindingStoreError, match="alias"):
        registry.bind(
            stored_session_id="stored-2",
            runtime_session_id="runtime-1",
            profile="writer",
            connection_id="local",
            source="desktop",
            project_id="other",
        )

    # The refused claim must not touch the previously committed row.
    assert path.read_bytes() == before
    assert (
        registry.get(
            stored_session_id="stored-1",
            profile="writer",
            connection_id="local",
        ).project_id
        == "novel"
    )


def test_alias_may_be_shared_by_compatible_rows(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    registry = StorySessionRegistry(path, locked_profile="writer")
    _bind(registry)

    registry.bind(
        stored_session_id="stored-2",
        runtime_session_id="runtime-1",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="novel",
    )

    assert {row.stored_session_id for row in registry.all()} == {
        "stored-1",
        "stored-2",
    }


def test_corrupt_file_is_never_rewritten_by_mutations(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    registry = StorySessionRegistry(path, locked_profile="writer")
    _bind(registry)
    broken = b"{broken"
    path.write_bytes(broken)

    with pytest.raises(SessionBindingStoreError):
        registry.bind(
            stored_session_id="stored-2",
            profile="writer",
            connection_id="local",
            source="desktop",
            project_id="novel",
        )
    with pytest.raises(SessionBindingStoreError):
        registry.unbind(
            stored_session_id="stored-1",
            profile="writer",
            connection_id="local",
        )

    assert path.read_bytes() == broken


def test_threaded_binds_of_different_ids_keep_both(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        try:
            registry = StorySessionRegistry(path, locked_profile="writer")
            registry.bind(
                stored_session_id=f"s{index}",
                runtime_session_id=f"r{index}",
                profile="writer",
                connection_id="local",
                source="desktop",
                project_id=f"p{index}",
            )
        except BaseException as exc:  # noqa: BLE001  re-raised on the main thread
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    final = StorySessionRegistry(path, locked_profile="writer")
    assert {row.stored_session_id for row in final.all()} == {
        f"s{i}" for i in range(8)
    }


def test_threaded_same_alias_for_different_projects_keeps_one_winner(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sessions.json"
    StorySessionRegistry(path, locked_profile="writer").bind(
        stored_session_id="kept",
        runtime_session_id="kept-r",
        profile="writer",
        connection_id="local",
        source="desktop",
        project_id="p0",
    )
    wins: list[str] = []
    rejects: list[str] = []
    barrier = threading.Barrier(2)

    def worker(stored_id: str, project_id: str) -> None:
        registry = StorySessionRegistry(path, locked_profile="writer")
        barrier.wait(timeout=10)
        try:
            registry.bind(
                stored_session_id=stored_id,
                runtime_session_id="shared-r",
                profile="writer",
                connection_id="local",
                source="desktop",
                project_id=project_id,
            )
            wins.append(stored_id)
        except SessionBindingStoreError:
            rejects.append(stored_id)

    threads = [
        threading.Thread(target=worker, args=("s1", "p1")),
        threading.Thread(target=worker, args=("s2", "p2")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert len(wins) == 1, (wins, rejects)
    assert len(rejects) == 1, (wins, rejects)
    rows = {
        row.stored_session_id: row
        for row in StorySessionRegistry(path, locked_profile="writer").all()
    }
    # The rejected claim loses; every already-committed binding survives.
    assert set(rows) == {"kept", wins[0]}
    assert rows["kept"].project_id == "p0"
    assert rows[wins[0]].project_id in {"p1", "p2"}
