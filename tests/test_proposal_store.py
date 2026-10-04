"""Durable proposals, their approvals and the chapter snapshots."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from story_construction_plugin.proposal_store import (
    APPROVAL_MINUTES,
    ChapterHistory,
    ProposalStore,
    ProposalStoreError,
)


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> ProposalStore:
    return ProposalStore(tmp_path / "plugin-data" / "proposals.json", now=clock)


def _proposal(**overrides):
    values = {
        "project_id": "novel", "profile": "writer", "connection_id": "local",
        "session_id": "s1", "kind": "edit", "chapter_id": "novel:chapter-1",
        "base_version": "v1", "edits": [], "result_text": "text",
    }
    return {**values, **overrides}


def test_a_new_proposal_is_pending_and_readable_by_scope(store) -> None:
    created = store.create(_proposal())

    assert created["status"] == "pending" and created["approval"] is None
    assert store.get(created["id"])["chapter_id"] == "novel:chapter-1"
    assert [row["id"] for row in store.list_for_project(project_id="novel", profile="writer", connection_id="local")] == [created["id"]]
    assert store.list_for_project(project_id="novel", profile="other", connection_id="local") == []
    assert store.list_for_project(project_id="novel", profile="writer", connection_id="remote") == []
    assert store.list_for_project(project_id="other", profile="writer", connection_id="local") == []
    assert store.get("missing") is None


def test_a_newer_proposal_supersedes_the_open_one_for_the_same_chapter(store) -> None:
    first = store.create(_proposal())
    other_chapter = store.create(_proposal(chapter_id="novel:chapter-2"))
    second = store.create(_proposal())

    assert store.get(first["id"])["status"] == "superseded"
    assert store.get(second["id"])["status"] == "pending"
    assert store.get(other_chapter["id"])["status"] == "pending"
    listed = {row["id"] for row in store.list_for_project(project_id="novel", profile="writer", connection_id="local")}
    assert listed == {second["id"], other_chapter["id"]}


def test_new_chapter_proposals_are_matched_by_title(store) -> None:
    one = store.create(_proposal(kind="new_chapter", chapter_id=None, title="A"))
    two = store.create(_proposal(kind="new_chapter", chapter_id=None, title="B"))
    again = store.create(_proposal(kind="new_chapter", chapter_id=None, title="A"))

    assert store.get(one["id"])["status"] == "superseded"
    assert store.get(two["id"])["status"] == "pending" and store.get(again["id"])["status"] == "pending"


def test_approval_expires_after_fifteen_minutes(store, clock) -> None:
    created = store.create(_proposal())

    approved = store.approve(created["id"], {"digest": "d", "mode": "edits"})

    assert approved["status"] == "approved" and approved["approval"]["digest"] == "d"
    clock.advance(minutes=APPROVAL_MINUTES - 1)
    assert store.get(created["id"])["status"] == "approved"
    clock.advance(minutes=1)
    assert store.get(created["id"])["status"] == "expired"
    assert [row["status"] for row in store.list_for_project(project_id="novel", profile="writer", connection_id="local")] == ["expired"]


def test_discarding_closes_an_open_proposal_only(store) -> None:
    open_one = store.create(_proposal())
    done = store.create(_proposal(chapter_id="novel:chapter-2"))
    store.mark_applied(done["id"], {"version_after": "v2"})

    assert store.discard(open_one["id"])["status"] == "discarded"
    assert store.discard(done["id"])["status"] == "applied"


def test_applied_proposals_record_when_and_what_version(store) -> None:
    created = store.create(_proposal())
    applied = store.mark_applied(created["id"], {"version_after": "v2", "snapshot_id": "snap"})

    assert applied["status"] == "applied" and applied["applied"]["version_after"] == "v2"
    assert store.latest_applied(project_id="novel", target_id="novel:chapter-1")["id"] == created["id"]
    assert store.latest_applied(project_id="novel", target_id="novel:chapter-9") is None
    assert [row["id"] for row in store.recent_applied(project_id="novel")] == [created["id"]]
    assert store.list_for_project(project_id="novel", profile="writer", connection_id="local") == []
    assert len(store.list_for_project(project_id="novel", profile="writer", connection_id="local", include_finished=True)) == 1


def test_latest_applied_picks_the_most_recent_write(store, clock) -> None:
    first = store.create(_proposal())
    store.mark_applied(first["id"], {"version_after": "v2"})
    clock.advance(minutes=5)
    second = store.create(_proposal(base_version="v2"))
    store.mark_applied(second["id"], {"version_after": "v3"})

    assert store.latest_applied(project_id="novel", target_id="novel:chapter-1")["id"] == second["id"]


def test_forgetting_a_project_closes_its_open_proposals(store) -> None:
    open_one = store.create(_proposal())
    other = store.create(_proposal(project_id="other"))

    assert store.forget_project("novel") == 1
    assert store.get(open_one["id"])["status"] == "discarded"
    assert store.get(other["id"])["status"] == "pending"


def test_forgetting_a_project_also_clears_its_write_log(store) -> None:
    written = store.create(_proposal())
    store.mark_applied(written["id"], {"version_after": "v2"})
    other = store.create(_proposal(project_id="other"))
    store.mark_applied(other["id"], {"version_after": "v2"})

    store.forget_project("novel")

    assert store.recent_applied(project_id="novel") == []
    assert [row["id"] for row in store.recent_applied(project_id="other")] == [other["id"]]


def test_forgetting_a_project_removes_its_snapshots_only(tmp_path: Path) -> None:
    history = ChapterHistory(tmp_path / "history")
    gone = history.save(project_id="novel", target_id="novel:chapter-1", text="old", version="v1", proposal_id="p1")
    kept = history.save(project_id="other", target_id="other:chapter-1", text="keep", version="v1", proposal_id="p2")

    history.forget_project("novel")

    assert history.load(project_id="novel", target_id="novel:chapter-1", snapshot_id=gone) is None
    assert history.load(project_id="other", target_id="other:chapter-1", snapshot_id=kept)["text"] == "keep"


def test_finished_proposals_are_pruned_after_a_week(store, clock) -> None:
    old = store.create(_proposal())
    store.discard(old["id"])
    clock.advance(days=8)

    store.create(_proposal(chapter_id="novel:chapter-2"))

    assert store.get(old["id"]) is None


def test_corrupt_state_is_reported_and_left_alone(store) -> None:
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ProposalStoreError):
        store.get("x")
    with pytest.raises(ProposalStoreError):
        store.create(_proposal())
    assert store.path.read_text(encoding="utf-8") == "{broken"


def test_concurrent_creates_all_survive(store) -> None:
    def add(number: int) -> None:
        store.create(_proposal(chapter_id=f"novel:chapter-{number}"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(20)))

    assert len(store.list_for_project(project_id="novel", profile="writer", connection_id="local")) == 20


def test_snapshots_keep_the_text_and_trim_to_the_limit(tmp_path: Path) -> None:
    history = ChapterHistory(tmp_path / "history", keep=3)
    ids = [
        history.save(project_id="novel", target_id="novel:chapter-1", text=f"text {n}", version=f"v{n}", proposal_id=f"p{n}")
        for n in range(5)
    ]

    assert history.load(project_id="novel", target_id="novel:chapter-1", snapshot_id=ids[4])["text"] == "text 4"
    assert history.load(project_id="novel", target_id="novel:chapter-1", snapshot_id=ids[0]) is None
    assert history.load(project_id="novel", target_id="novel:chapter-1", snapshot_id=ids[2])["version"] == "v2"
    assert history.load(project_id="novel", target_id="novel:chapter-2", snapshot_id=ids[4]) is None


def test_snapshot_names_cannot_leave_the_history_folder(tmp_path: Path) -> None:
    history = ChapterHistory(tmp_path / "history")
    history.save(project_id="../x", target_id="..\\y", text="t", version="v", proposal_id="p")

    assert not (tmp_path / "x").exists()
    assert any((tmp_path / "history").rglob("*.json"))
    assert history.load(project_id="novel", target_id="c", snapshot_id="../../escape") is None
