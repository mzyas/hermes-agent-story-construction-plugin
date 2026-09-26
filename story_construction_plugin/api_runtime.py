"""API-owned runtime preparation from the default package and selected Profile.

Preparation resolves the Task 1 writing target on every call and prepares that
target's (package, home) runtime through the same package's ``runtime`` module,
so the Dashboard API never has to discover a Gateway-owned runtime in
``sys.modules``.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

from . import runtime as _runtime_module
from .profile_config import StoryTarget, resolve_story_target
from .runtime import StoryRuntimeState, prepare_story_runtime


def prepare_api_state(
    api_plugin_root: Path, default_home: Path
) -> tuple[ModuleType, StoryRuntimeState]:
    """Resolve the selected writing target and prepare its runtime state."""

    target: StoryTarget = resolve_story_target(api_plugin_root, default_home)
    state = prepare_story_runtime(
        target.plugin_root,
        target.settings,
        current_home=target.home,
    )
    return _runtime_module, state
