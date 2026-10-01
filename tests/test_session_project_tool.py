"""story.get_session_project resolves the project from the session binding."""

from __future__ import annotations

import json

from story_construction_plugin.permissions import SessionScope, StoryPermissionGate
from story_construction_plugin.prompt_templates import render_story_agent_system_prompt
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
