"""Every tool name the plugin mentions is a tool it really registers."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from story_construction_plugin.prompt_templates import render_story_agent_system_prompt
from story_construction_plugin.schemas import TOOL_SCHEMAS

ROOT = Path(__file__).resolve().parents[1]
TOOL_NAME = re.compile(r"story\.[a-z_]+")


def test_the_manifest_lists_exactly_the_registered_tools() -> None:
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))

    assert sorted(manifest["provides_tools"]) == sorted(TOOL_SCHEMAS)


def test_the_new_record_tool_has_a_name_that_fits_every_kind_of_record() -> None:
    assert "story.propose_new" in TOOL_SCHEMAS
    assert "story.propose_chapter" not in TOOL_SCHEMAS
    assert TOOL_SCHEMAS["story.propose_new"]["name"] == "story.propose_new"


def test_the_prompt_only_names_tools_that_exist() -> None:
    mentioned = set(TOOL_NAME.findall(render_story_agent_system_prompt()))

    assert mentioned, "the prompt should name the story tools"
    assert mentioned <= set(TOOL_SCHEMAS), sorted(mentioned - set(TOOL_SCHEMAS))
    # The tools the protocol depends on are all spelled out.
    assert {"story.propose_edit", "story.propose_new", "story.apply_edit"} <= mentioned


def test_tool_descriptions_only_point_to_tools_that_exist() -> None:
    for name, schema in TOOL_SCHEMAS.items():
        text = schema["description"] + " ".join(
            str(prop.get("description", "")) for prop in schema["parameters"]["properties"].values()
        )
        unknown = set(TOOL_NAME.findall(text)) - set(TOOL_SCHEMAS)
        assert not unknown, (name, sorted(unknown))


def test_the_readme_only_names_tools_that_exist() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Skip route-like text such as `story.construction`; only underscore names are tools.
    mentioned = {name for name in TOOL_NAME.findall(readme) if "_" in name}

    assert mentioned <= set(TOOL_SCHEMAS), sorted(mentioned - set(TOOL_SCHEMAS))


def test_every_required_argument_is_a_declared_property() -> None:
    for name, schema in TOOL_SCHEMAS.items():
        parameters = schema["parameters"]
        declared = set(parameters["properties"])
        assert set(parameters["required"]) <= declared, (name, sorted(set(parameters["required"]) - declared))
        assert parameters["additionalProperties"] is False


def test_the_record_tools_offer_the_same_kinds_of_record_the_service_accepts() -> None:
    from story_construction_plugin.proposal_service import TARGET_TYPES

    for name in ("story.propose_edit", "story.propose_new"):
        assert TOOL_SCHEMAS[name]["parameters"]["properties"]["target_type"]["enum"] == list(TARGET_TYPES)
    for name in ("story.list_records", "story.get_record"):
        offered = TOOL_SCHEMAS[name]["parameters"]["properties"]["target_type"]["enum"]
        assert offered == [kind for kind in TARGET_TYPES if kind != "chapter"]


def test_chapters_stay_the_default_so_older_calls_keep_working() -> None:
    edit = TOOL_SCHEMAS["story.propose_edit"]["parameters"]
    new = TOOL_SCHEMAS["story.propose_new"]["parameters"]

    assert "target_type" not in edit["required"] and "target_type" not in new["required"]
    assert "chapter_id" in edit["properties"]
