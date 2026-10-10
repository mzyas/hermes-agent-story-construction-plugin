"""story.get_session_project resolves the project from the session binding."""

from __future__ import annotations

import json

from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.prompt_templates import (
    render_story_agent_system_prompt,
    render_story_subagent_prompt,
)
from story_construction_plugin.schemas import TOOL_SCHEMAS
from story_construction_plugin.tools import StoryToolService

from test_story_tools import FakeRepository

TOOL = "story.get_session_project"


def _service(*, bound: bool = True) -> StoryToolService:
    permissions = StoryPermissionGate({"p1": ("default", "local")})
    if bound:
        permissions.bind_session(SessionScope("s", "desktop", "default", "local", "p1"), "p1")
    return StoryToolService(FakeRepository(), permissions)


def _call(service: StoryToolService, args: dict | None = None, **overrides) -> dict:
    scope = {"session_id": "s", "source": "desktop", "profile": "default", "connection_id": "local"}
    scope.update(overrides)
    return json.loads(service.handle(TOOL, args, **scope))


def test_bound_session_gets_its_project_without_naming_it() -> None:
    response = _call(_service())

    assert response["ok"] is True
    assert response["project_id"] == "p1"
    assert response["data"]["project"]["name"] == "Demo"
    assert [volume["id"] for volume in response["data"]["volumes"]] == ["v1"]
    chapter = response["data"]["chapters"][0]
    assert chapter["id"] == "ch1"
    assert "content" not in chapter  # metadata only, never chapter text


def test_unbound_session_is_reported_as_an_ordinary_chat() -> None:
    response = _call(_service(bound=False))

    assert response["ok"] is False
    assert response["error"]["code"] == "session_not_bound"


def test_arguments_cannot_redirect_the_lookup_to_another_project() -> None:
    response = _call(_service(), {"project_id": "p2"})

    assert response["ok"] is True
    assert response["project_id"] == "p1"


def test_scope_mismatch_is_still_denied() -> None:
    response = _call(_service(), profile="other")

    assert response["ok"] is False
    assert response["error"]["code"] == "permission_denied"


def test_schema_takes_no_arguments() -> None:
    parameters = TOOL_SCHEMAS[TOOL]["parameters"]

    assert parameters["properties"] == {}
    assert parameters["required"] == []
    assert parameters["additionalProperties"] is False


def test_prompt_tells_the_agent_to_judge_intent_and_use_the_tool() -> None:
    rendered = render_story_agent_system_prompt()

    assert TOOL in rendered
    assert "session_not_bound" in rendered
    assert "ordinary conversation" in rendered
    assert "this project" in rendered  # vague project questions go straight to the tool
    assert "project_id:" not in rendered  # the frozen prompt carries no live records


def test_prompt_and_tool_keep_the_story_project_apart_from_code_projects() -> None:
    rendered = render_story_agent_system_prompt()

    assert "not things inside the story" in rendered  # a story about code is still story work
    assert "latest message is about code or software" in rendered
    assert "never story work" not in rendered  # no absolute rule over the ask-when-unclear fallback
    assert "story (fiction) project" in TOOL_SCHEMAS[TOOL]["description"]
    assert "never a code or software project" in TOOL_SCHEMAS[TOOL]["description"]


def test_prompt_makes_the_agent_propose_wait_for_approval_and_keep_text_clean() -> None:
    rendered = render_story_agent_system_prompt()

    for tool in ("story.propose_edit", "story.propose_new", "story.apply_edit"):
        assert tool in rendered
    assert "never say it was saved" in rendered
    assert "Never write files or save chapters yourself" in rendered
    # The format rules moved to a Skill, so the prompt only points to it.
    assert "no greeting" not in rendered and "story-construction:record-format" in rendered


def test_prompt_covers_every_kind_of_record_and_checks_before_creating() -> None:
    rendered = render_story_agent_system_prompt()

    for kind in ("chapter", "character", "world_entry", "note"):
        assert kind in rendered
    assert "story.list_records" in rendered
    assert "does not already exist" in rendered  # list before creating a duplicate
    assert "read-only" in rendered  # reference notes
    # Per-tool detail lives in the tool descriptions, not the prompt.
    assert "name_in_use" in TOOL_SCHEMAS["story.propose_new"]["description"]
    assert "final title" in TOOL_SCHEMAS["story.apply_edit"]["description"]
    assert "name_in_use" in TOOL_SCHEMAS["story.propose_rename"]["description"]


def test_tool_descriptions_keep_the_read_guidance_the_prompt_no_longer_has() -> None:
    edit = TOOL_SCHEMAS["story.propose_edit"]["description"]

    assert "story.get_chapter" in edit and "story.get_record" in edit
    assert "base_version" in edit  # pass the version you read


def test_prompt_keeps_the_agent_brief_and_from_acting_unasked() -> None:
    rendered = render_story_agent_system_prompt()

    # Brevity and no-filler rules come from Hermes' own identity prompt; only the extras stay here.
    assert "## Tone" in rendered and "language of the user's latest message" in rendered
    assert "no emoji" in rendered.lower()
    # Flag continuity or setting conflicts in the reply, without proposing a change unasked.
    assert "say so and suggest an alternative in your reply" in rendered
    assert "A question is answered, not acted on" in rendered
    assert "propose a change only when the user asks" in rendered.lower()


def test_prompt_output_rule_applies_only_to_planning_and_drafting() -> None:
    rendered = render_story_agent_system_prompt()

    assert "When asked to plan or draft a chapter" in rendered
    assert "continuity warnings" in rendered
    assert "still citing sources" in rendered  # plain answers keep the citation rule
    assert "for the current request" not in rendered  # no blanket contract on every reply


def test_unbound_error_and_description_keep_an_ordinary_chat_away_from_story_tools() -> None:
    # An unbound chat has no Story section, so the tool itself draws the line.
    message = _call(_service(bound=False))["error"]["message"]

    assert "ordinary chat" in message and "do not call other story.* tools" in message
    assert "do not search the disk" in message
    assert "do not call other story.* tools" in TOOL_SCHEMAS[TOOL]["description"]


def test_subagent_prompt_is_read_only_and_short() -> None:
    rendered = render_story_subagent_prompt()

    assert rendered.startswith("# StorySubagentPrompt v1")
    assert "You can only read" in rendered
    for tool in ("story.propose_edit", "story.apply_edit", TOOL):
        assert tool in rendered
    assert len(rendered) < 800


def test_prompt_version_names_the_current_protocol() -> None:
    assert render_story_agent_system_prompt().startswith("# StoryConstructionAgentPrompt v11")
