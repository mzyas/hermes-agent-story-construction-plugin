"""Cross-process Story worker probe driven by JSON lines on stdin/stdout.

One process, one role. ``api`` drives the real Dashboard ``dashboard/plugin_api.py``
from the default package copy without calling register; ``agent`` registers the
target Profile's package copy once and serves every later tool call from the
same PID. The protocol has only select/create/bind/unbind/tool/status. Each
input line produces exactly one JSON object on stdout carrying ``pid`` and
``code``. The probe never reads source text and never writes real homes — the
parent test owns every path it touches.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path


def _emit(payload: dict) -> None:
    payload.setdefault("pid", os.getpid())
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _envelope(op: str, payload: dict) -> dict:
    if isinstance(payload, dict) and "ok" in payload:
        ok = bool(payload.get("ok"))
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        code = "ok" if ok else str(error.get("code") or "tool_error")
        return {"op": op, "code": code, "pid": os.getpid(), **payload}
    return {"op": op, "code": "ok", "ok": True, "pid": os.getpid(), **payload}


def _load_plugin_api(plugin_root: Path):
    spec = importlib.util.spec_from_file_location(
        "story_profile_probe_api", plugin_root / "dashboard" / "plugin_api.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("story probe cannot load dashboard/plugin_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _AgentContext:
    """Minimal registration context exposing the target Profile's Story settings."""

    def __init__(self, settings: dict) -> None:
        self.settings = settings
        self.tools: dict[str, dict] = {}
        self.skills: list = []
        self.sections: list = []

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_skill(self, *args) -> None:
        self.skills.append(args)

    def register_system_prompt_section(self, *args, **kwargs) -> None:
        self.sections.append((args, kwargs))

    def register_tool(self, **kwargs) -> None:
        self.tools[kwargs["name"]] = kwargs


def _run_api(api, op: str, request: dict) -> dict:
    if op == "select":
        body = {"profile": request.get("profile")}
        if request.get("vault_root"):
            body["vault_root"] = str(request["vault_root"])
        return {"status": api.update_settings(body)}
    if op == "create":
        body = {
            "profile": request.get("profile"),
            "connection_id": request.get("connection_id") or "local",
            "name": request.get("name"),
        }
        if request.get("slug"):
            body["slug"] = str(request["slug"])
        return api.create_project(body)
    if op == "bind":
        body = {
            "session_id": request.get("session_id"),
            "profile": request.get("profile"),
            "connection_id": request.get("connection_id") or "local",
            "project_id": request.get("project_id"),
        }
        return api.bind_session(body)
    if op == "unbind":
        return api.delete_project_session(
            str(request.get("project_id") or ""),
            str(request.get("session_id") or ""),
            profile=request.get("profile"),
            connection_id=request.get("connection_id") or "local",
        )
    if op == "status":
        return {"status": api.status()}
    raise ValueError(f"unknown api op: {op}")


def _run_agent(agent: _AgentContext, op: str, request: dict) -> dict:
    if op == "tool":
        registered = agent.tools.get("story.get_project")
        if registered is None:
            return {
                "ok": False,
                "error": {
                    "code": "tools_not_registered",
                    "message": "Story tools are not registered",
                },
            }
        raw = registered["handler"](
            {"project_id": str(request.get("project_id") or "")},
            session_id=str(request.get("session_id") or ""),
            source="desktop",
            profile=str(agent.settings.get("locked_profile") or ""),
            connection_id=str(request.get("connection_id") or "local"),
        )
        return json.loads(raw)
    if op == "status":
        return {
            "status": {
                "role": "agent",
                "tools": sorted(agent.tools),
                "sections": [name for (name, *_), _ in agent.sections],
            }
        }
    raise ValueError(f"unknown agent op: {op}")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("api", "agent"):
        _emit({"op": "start", "code": "usage", "ok": False,
               "detail": "usage: story_profile_probe.py <api|agent> [profile]"})
        return 2
    role = argv[1]
    profile_label = argv[2] if len(argv) > 2 else "default"

    from hermes_env import ensure_hermes

    hermes = ensure_hermes()
    if not hermes.available:
        _emit({
            "op": "start",
            "code": "hermes_unavailable",
            "ok": False,
            "detail": "Hermes is not importable (set HERMES_SOURCE or install hermes)",
        })
        return 2

    home = Path(os.environ["HERMES_HOME"]).expanduser().resolve()
    plugin_root = home / "plugins" / "story-construction"

    api = None
    agent = None
    if role == "api":
        api = _load_plugin_api(plugin_root)
    else:
        sys.path.insert(0, str(plugin_root))
        import story_construction_plugin
        from story_construction_plugin.profile_config import _story_settings

        agent = _AgentContext(_story_settings(home))
        story_construction_plugin.register(agent)

    _emit({"op": "ready", "code": "ready", "ok": True,
           "role": role, "profile": profile_label})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _emit({"op": "parse", "code": "invalid_request", "ok": False,
                   "pid": os.getpid(), "detail": str(exc)})
            continue
        op = str(request.get("op") or "")
        try:
            if role == "api":
                payload = _run_api(api, op, request)
            else:
                payload = _run_agent(agent, op, request)
            _emit(_envelope(op, payload))
        except Exception as exc:  # noqa: BLE001  every failure becomes one line
            from fastapi import HTTPException

            if isinstance(exc, HTTPException):
                detail = exc.detail
                if isinstance(detail, dict):
                    code = str(detail.get("code") or f"http_{exc.status_code}")
                    body = {"detail": detail}
                else:
                    code = f"http_{exc.status_code}"
                    body = {"detail": str(detail)}
                _emit({"op": op, "code": code, "ok": False,
                       "pid": os.getpid(), **body})
            else:
                _emit({"op": op, "code": "probe_error", "ok": False,
                       "pid": os.getpid(),
                       "detail": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
