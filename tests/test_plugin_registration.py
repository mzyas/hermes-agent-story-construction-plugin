"""Registration contracts for the standalone story construction package."""

from __future__ import annotations

import importlib
import sys
import types
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_backend_package_exposes_register_entrypoint() -> None:
    module = importlib.import_module("story_construction_plugin")

    assert callable(module.register)


def test_hermes_directory_loader_imports_install_root_entrypoint() -> None:
    namespace = types.ModuleType("hermes_plugins")
    namespace.__path__ = []
    sys.modules.setdefault("hermes_plugins", namespace)
    module_name = "hermes_plugins.story_construction_loader_test"
    spec = importlib.util.spec_from_file_location(
        module_name,
        PACKAGE_ROOT / "__init__.py",
        submodule_search_locations=[str(PACKAGE_ROOT)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = module_name
    module.__path__ = [str(PACKAGE_ROOT)]
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        assert callable(module.register)
    finally:
        sys.modules.pop(module_name, None)


def test_install_root_exposes_hermes_directory_loader_entrypoint() -> None:
    assert (PACKAGE_ROOT / "__init__.py").is_file()


def test_unified_package_declares_agent_and_desktop_halves() -> None:
    plugin_yaml = PACKAGE_ROOT / "plugin.yaml"
    desktop_plugin = PACKAGE_ROOT / "desktop" / "plugin.js"
    dashboard_manifest = PACKAGE_ROOT / "dashboard" / "manifest.json"
    dashboard_api = PACKAGE_ROOT / "dashboard" / "plugin_api.py"

    assert plugin_yaml.is_file()
    assert desktop_plugin.is_file()
    assert dashboard_api.is_file()
    manifest = json.loads(dashboard_manifest.read_text(encoding="utf-8"))
    assert manifest["name"] == "story-construction"
    assert manifest["api"] == "plugin_api.py"
