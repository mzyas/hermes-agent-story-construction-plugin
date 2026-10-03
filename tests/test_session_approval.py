"""Approving a proposal in the chat: the hook, the grant, and the risk gate."""

from __future__ import annotations

import json

import pytest

from story_construction_plugin import approval_gate as gate
from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.tools import StoryToolService

from test_record_proposals import ADD, Env, REPLACE, SCOPE


@pytest.fixture
def env(tmp_path) -> Env:
    return Env(tmp_path)


def _long_text(length: int = 400) -> str:
    return "".join(chr(0x4E00 + i) for i in range(length))


def _scope() -> SessionScope:
    return SessionScope("s1", "desktop", "writer", "local", "novel")


class Chat:
    """A Story session with the approval hook and the tools wired together."""

    def __init__(self, env: Env) -> None:
        self.env = env
        self.grants = gate.SessionGrants()
        self.hook = gate.make_apply_hook(
            lambda session_id: (env.service, _scope()) if session_id == "s1" else None, self.grants
        )
        permissions = StoryPermissionGate({"novel": ("writer", "local")}, locked_profile="writer")
        permissions.bind_session(_scope(), "novel")
        self.tools = StoryToolService(
            env.repository, permissions, proposals_provider=lambda: env.service, grants=self.grants
        )

    def ask(self, proposal_id: str, session_id: str = "s1"):
        """What Hermes gets back from the hook before it runs story.apply_edit."""
        return self.hook(tool_name="story.apply_edit", args={"proposal_id": proposal_id}, session_id=session_id)

    def apply(self, proposal_id: str) -> dict:
        kwargs = {"session_id": "s1", "source": "desktop", "profile": "writer", "connection_id": "local"}
        return json.loads(self.tools.handle("story.apply_edit", {"proposal_id": proposal_id}, **kwargs))


@pytest.fixture
def chat(env) -> Chat:
    return Chat(env)


# ------------------------------------------------------------------ risk
def _proposal(env: Env, target_type: str, edits) -> dict:
    proposal_id = env.propose(target_type, edits)["proposal_id"]
    return env.store.get(proposal_id)


def test_a_small_edit_is_normal(env) -> None:
    proposal = _proposal(env, "character", [REPLACE])

    risk = env.service.assess(project_id="novel", proposal=proposal)

    assert risk.level == "normal" and risk.reasons == () and not risk.high


def test_a_new_record_and_an_addition_are_normal(env) -> None:
    new = env.store.get(env.propose_new("note", "新笔记", "内容。")["proposal_id"])
    added = _proposal(env, "note", [ADD])

    assert env.service.assess(project_id="novel", proposal=new).level == "normal"
    assert env.service.assess(project_id="novel", proposal=added).level == "normal"


def test_removing_most_of_a_record_is_high_risk(env) -> None:
    long = env.repository.create_character("novel", "长篇", _long_text())
    proposal_id = env.service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="character", target_id=long.id,
        base_version=long.version, raw_edits=[{"op": "rewrite", "content": "只剩一句。"}],
    )["proposal_id"]

    risk = env.service.assess(project_id="novel", proposal=env.store.get(proposal_id))

    assert risk.high and risk.reasons == ("large_removal",)
    assert risk.removed >= 300 and risk.total == 400


def test_deleting_the_whole_text_is_high_risk_and_says_so(env) -> None:
    long = env.repository.create_character("novel", "长篇", _long_text(60))
    proposal_id = env.service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="character", target_id=long.id,
        base_version=long.version, raw_edits=[{"op": "replace", "old_text": long.content, "new_text": ""}],
    )["proposal_id"]
    risk = env.service.assess(project_id="novel", proposal=env.store.get(proposal_id))

    # Under the size floor, so emptying it is the only reason.
    assert risk.high and risk.reasons == ("clears_record",)


def test_a_short_record_is_not_flagged_for_a_small_absolute_loss(env) -> None:
    # 5 of 8 characters is most of the record, but under the floor it is not worth a warning.
    proposal = _proposal(env, "character", [{"op": "replace", "old_text": "少年，住在阁", "new_text": "他"}])

    assert env.service.assess(project_id="novel", proposal=proposal).level == "normal"


# ---------------------------------------------------------------- grants
def test_a_grant_works_once() -> None:
    grants = gate.SessionGrants()
    grants.grant("p1")

    assert grants.consume("p1") is True
    assert grants.consume("p1") is False
    assert grants.consume("never") is False


def test_a_grant_expires_and_can_be_revoked() -> None:
    now = [100.0]
    grants = gate.SessionGrants(clock=lambda: now[0])
    grants.grant("late")
    grants.grant("gone")
    grants.revoke("gone")
    now[0] += gate.GRANT_SECONDS + 1

    assert grants.consume("late") is False
    assert grants.consume("gone") is False


# --------------------------------------------------------------- the prompt
def test_the_prompt_text_names_the_record_and_shows_the_change(env) -> None:
    proposal = _proposal(env, "character", [REPLACE])

    message = gate.approval_message(proposal, gate.NORMAL)

    assert message.splitlines()[0] == "修改角色「林远」"
    assert "- 少年，住在阁楼。" in message and "+ 青年，住在阁楼。" in message
    assert "Story 面板" in message


def test_the_prompt_for_a_new_record_shows_its_text(env) -> None:
    proposal = env.store.get(env.propose_new("world_entry", "渡口", "城西的老渡口。")["proposal_id"])

    message = gate.approval_message(proposal, gate.NORMAL)

    assert message.splitlines()[0] == "新建世界设定条目「渡口」"
    assert "+ 城西的老渡口。" in message


def test_the_prompt_is_in_english_for_an_english_record(env) -> None:
    proposal = {"kind": "new_record", "target_type": "note", "target_title": "Idea", "result_text": "A bell stops."}

    message = gate.approval_message(proposal, gate.NORMAL)

    assert message.splitlines()[0] == "New note: Idea" and "+ A bell stops." in message


def test_a_risky_prompt_leads_with_the_warning_and_a_long_diff_is_cut(env) -> None:
    regions = [{"old": f"旧{i}", "new": f"新{i}", "inline": []} for i in range(10)]
    proposal = {
        "kind": "edit", "target_type": "chapter", "target_title": "第一章", "result_text": "新",
        "previews": [{"regions": regions}],
    }
    risk = gate.Risk("high", ("large_removal",), 900, 1000)

    message = gate.approval_message(proposal, risk)
    lines = message.splitlines()

    assert lines[1].startswith("高风险：") and "900" in lines[1] and "总是允许" in lines[1]
    assert any(line.startswith("…另有") for line in lines)
    assert len(message) < gate._MAX_LINE_CHARS * 12


def test_normal_changes_share_a_rule_and_risky_ones_never_do() -> None:
    high = gate.Risk("high", ("large_removal",), 1, 1)

    assert gate.rule_key("a", gate.NORMAL) == gate.rule_key("b", gate.NORMAL)
    assert gate.rule_key("a", high) != gate.rule_key("b", high)


# -------------------------------------------------------------------- the hook
def test_the_hook_sends_a_pending_proposal_to_the_approval_prompt(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]

    directive = chat.ask(proposal_id)

    assert directive["action"] == "approve"
    assert directive["message"].startswith("修改角色「林远」")
    assert directive["rule_key"] == "story.apply"
    assert chat.grants.consume(proposal_id) is True


def test_a_risky_proposal_gets_a_rule_of_its_own(chat, env) -> None:
    long = env.repository.create_character("novel", "长篇", _long_text())
    proposal_id = env.service.propose_edit(
        project_id="novel", session_id="s1", **SCOPE, target_type="character", target_id=long.id,
        base_version=long.version, raw_edits=[{"op": "rewrite", "content": "只剩一句。"}],
    )["proposal_id"]

    directive = chat.ask(proposal_id)

    assert directive["rule_key"] == f"story.apply:{proposal_id}"
    assert "高风险" in directive["message"]


@pytest.mark.parametrize("tool", ["story.propose_edit", "story.get_record", "terminal", ""])
def test_the_hook_ignores_every_other_tool(chat, env, tool) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]

    assert chat.hook(tool_name=tool, args={"proposal_id": proposal_id}, session_id="s1") is None
    assert chat.grants.consume(proposal_id) is False


def test_the_hook_leaves_unbound_unknown_and_foreign_proposals_alone(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]

    assert chat.ask(proposal_id, session_id="other") is None
    assert chat.ask("missing") is None
    assert chat.hook(tool_name="story.apply_edit", args={}, session_id="s1") is None
    env.store.mutate(proposal_id, lambda row: row.update(profile="someone-else"))
    assert chat.ask(proposal_id) is None
    assert chat.grants.consume(proposal_id) is False


def test_a_proposal_already_approved_in_the_panel_is_not_asked_again(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    env.approve(proposal_id)

    assert chat.ask(proposal_id) is None
    assert chat.apply(proposal_id)["data"]["status"] == "applied"


def test_a_failing_hook_returns_nothing_instead_of_raising(env) -> None:
    def broken(_session_id):
        raise RuntimeError("binding file unreadable")

    hook = gate.make_apply_hook(broken, gate.SessionGrants())

    assert hook(tool_name="story.apply_edit", args={"proposal_id": "x"}, session_id="s1") is None


# ------------------------------------------------------------ the tool's side
def test_without_the_hook_the_tool_refuses_to_write(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]

    result = chat.apply(proposal_id)

    assert result["ok"] is False and result["error"]["code"] == "not_approved"
    assert env.doc("character").content == "少年，住在阁楼。"


def test_after_the_person_accepts_in_the_chat_the_tool_writes_exactly_that(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    assert chat.ask(proposal_id)["action"] == "approve"

    result = chat.apply(proposal_id)

    assert result["ok"] is True and result["data"]["status"] == "applied"
    assert env.doc("character").content == "青年，住在阁楼。"
    assert env.store.get(proposal_id)["approval"]["via"] == "chat"


def test_one_acceptance_covers_one_write(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    chat.ask(proposal_id)
    chat.apply(proposal_id)

    again = chat.apply(proposal_id)

    assert again["ok"] is False and again["error"]["code"] == "already_applied"


def test_declining_leaves_nothing_written_and_a_later_call_needs_a_new_prompt(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    chat.ask(proposal_id)  # the person then declines: Hermes blocks the call, the tool never runs
    chat.ask(proposal_id)  # the next attempt raises a fresh prompt and replaces the grant
    chat.grants.revoke(proposal_id)  # as if that hook run had not happened

    assert chat.apply(proposal_id)["error"]["code"] == "not_approved"
    assert env.doc("character").content == "少年，住在阁楼。"


def test_an_expired_approval_can_be_given_again_in_the_chat(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    env.approve(proposal_id)
    env.store.mutate(proposal_id, lambda row: row.update(status="expired"))
    assert chat.ask(proposal_id)["action"] == "approve"

    assert chat.apply(proposal_id)["data"]["status"] == "applied"


def test_a_new_record_is_created_after_the_chat_approval(chat, env) -> None:
    proposal_id = env.propose_new("note", "新点子", "钟声停了。")["proposal_id"]
    chat.ask(proposal_id)

    result = chat.apply(proposal_id)

    assert result["data"]["status"] == "applied" and result["data"]["title"] == "新点子"
    assert any(note.title == "新点子" for note in env.repository.get_project("novel").notes)


def test_the_text_that_changed_after_the_prompt_is_not_written_blindly(chat, env) -> None:
    proposal_id = env.propose("character", [REPLACE])["proposal_id"]
    chat.ask(proposal_id)
    character = env.doc("character")
    env.repository.save_character("novel", character.id, "完全不同的描述。", expected_version=character.version)

    result = chat.apply(proposal_id)

    assert result["ok"] is False
    assert env.doc("character").content == "完全不同的描述。"


# ----------------------------------------------------------------- registration
def test_the_plugin_registers_the_approval_hook_with_its_tools() -> None:
    from story_construction_plugin import register_story_backend

    class Ctx:
        def __init__(self) -> None:
            self.hooks = []

        def register_tool(self, **_kwargs) -> None:
            pass

        def register_hook(self, name, callback) -> None:
            self.hooks.append(name)

    ctx = Ctx()
    register_story_backend(ctx)

    assert ctx.hooks == ["pre_tool_call"]


def test_a_host_without_hooks_still_registers_the_tools() -> None:
    from story_construction_plugin import register_story_backend

    class Ctx:
        def register_tool(self, **_kwargs) -> None:
            pass

    assert register_story_backend(Ctx()) is not None
