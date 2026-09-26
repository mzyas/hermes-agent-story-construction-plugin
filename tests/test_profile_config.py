"""Behavior tests for Story profile resolution and scoped config transactions."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from hermes_env import read_user_config_raw  # lazy real-SDK passthrough

from story_construction_plugin.profile_config import (
    StorySetupError,
    resolve_story_target,
    select_story_target,
    selected_target_guard,
)

pytestmark = pytest.mark.hermes_integration

PLUGIN_ID = "story-construction"
REAL_PLUGIN_YAML = Path(__file__).resolve().parents[1] / "plugin.yaml"


def _read_bytes(homes) -> tuple[bytes, bytes]:
    default_home, target_home, _, _ = homes
    return (
        (default_home / "config.yaml").read_bytes(),
        (target_home / "config.yaml").read_bytes(),
    )


def _selected_profile(default_home: Path):
    raw = read_user_config_raw(default_home / "config.yaml")
    return (
        raw.get("plugins", {})
        .get("entries", {})
        .get(PLUGIN_ID, {})
        .get("settings", {})
        .get("selected_profile")
    )


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


@pytest.fixture
def homes(tmp_path: Path, monkeypatch):
    default_home = tmp_path / "hermes"
    target_home = default_home / "profiles" / "writer"
    vault = tmp_path / "vault"
    plugin_root = default_home / "plugins" / PLUGIN_ID
    target_plugin_root = target_home / "plugins" / PLUGIN_ID

    default_home.mkdir(parents=True)
    vault.mkdir()
    for folder in (plugin_root, target_plugin_root):
        folder.mkdir(parents=True)
        shutil.copy(REAL_PLUGIN_YAML, folder / "plugin.yaml")

    # The named Profile's config.yaml doubles as its Hermes identity marker.
    (target_home / "config.yaml").write_text(
        "plugins:\n"
        "  enabled:\n"
        f"    - {PLUGIN_ID}\n"
        "agent:\n"
        "  max_turns: 12\n",
        encoding="utf-8",
    )
    (default_home / "config.yaml").write_text(
        "agent:\n  max_turns: 5\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HERMES_HOME", str(default_home))
    monkeypatch.delenv("HERMES_MANAGED", raising=False)
    monkeypatch.delenv("HERMES_MANAGED_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: default_home)
    return default_home, target_home, vault, plugin_root


def test_select_persists_only_story_settings(homes):
    default_home, target_home, vault, plugin_root = homes
    result = select_story_target(plugin_root, default_home, 'writer', str(vault))
    assert (result.profile, result.home, result.vault_root) == ('writer', target_home, vault.resolve())
    default_raw = read_user_config_raw(default_home / 'config.yaml')
    target_raw = read_user_config_raw(target_home / 'config.yaml')
    assert default_raw['plugins']['entries']['story-construction']['settings']['selected_profile'] == 'writer'
    assert target_raw['plugins']['entries']['story-construction']['settings']['locked_hermes_home'] == str(target_home.resolve())
    assert target_raw['agent']['max_turns'] == 12


def test_bad_profile_and_conflicting_vault_do_not_switch(homes):
    default_home, _, vault, plugin_root = homes
    with pytest.raises(StorySetupError) as invalid:
        select_story_target(plugin_root, default_home, '../writer', str(vault))
    assert invalid.value.code == 'profile_invalid'
    with pytest.raises(StorySetupError) as conflict:
        select_story_target(plugin_root, default_home, 'writer', str(vault / 'other'))
    assert conflict.value.code in {'vault_not_directory', 'vault_mismatch'}
    raw = read_user_config_raw(default_home / 'config.yaml')
    assert raw.get('plugins', {}).get('entries', {}).get('story-construction', {}).get('settings', {}).get('selected_profile') is None


def test_select_normalizes_mixed_case_profile(homes):
    default_home, target_home, vault, plugin_root = homes
    result = select_story_target(plugin_root, default_home, "Writer", str(vault))
    assert result.profile == "writer"
    target_raw = read_user_config_raw(target_home / "config.yaml")
    assert target_raw["plugins"]["entries"][PLUGIN_ID]["settings"]["locked_profile"] == "writer"


def test_select_rejects_invalid_and_unknown_profiles(homes):
    default_home, _, vault, plugin_root = homes
    profiles_dir = default_home / "profiles"
    before = sorted(entry.name for entry in profiles_dir.iterdir())
    cases = [
        ("../writer", "profile_invalid"),
        ("test", "profile_invalid"),
        ("", "profile_invalid"),
        ("ghost", "profile_not_found"),
    ]
    for profile, code in cases:
        with pytest.raises(StorySetupError) as exc:
            select_story_target(plugin_root, default_home, profile, str(vault))
        assert exc.value.code == code
    # Malformed and unknown names must not create either directory.
    assert sorted(entry.name for entry in profiles_dir.iterdir()) == before
    assert not (profiles_dir / "ghost").exists()


def _arrange_tombstone(homes, monkeypatch):
    default_home, _, _, _ = homes
    marker = default_home / "profiles" / ".deleted" / "writer"
    marker.parent.mkdir(parents=True)
    marker.write_text("deleted\n", encoding="utf-8")


def _arrange_disabled(homes, monkeypatch):
    _, target_home, _, _ = homes
    _write_yaml(
        target_home / "config.yaml",
        {"plugins": {"enabled": ["other-plugin"]}, "agent": {"max_turns": 12}},
    )


def _arrange_missing_package(homes, monkeypatch):
    _, target_home, _, _ = homes
    shutil.rmtree(target_home / "plugins")


def _arrange_version_mismatch(homes, monkeypatch):
    _, target_home, _, _ = homes
    manifest_path = target_home / "plugins" / PLUGIN_ID / "plugin.yaml"
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["version"] = "999.0.0"
    _write_yaml(manifest_path, data)


def _arrange_malformed_target_yaml(homes, monkeypatch):
    _, target_home, _, _ = homes
    (target_home / "config.yaml").write_text("plugins: [unclosed\n", encoding="utf-8")


def _arrange_malformed_default_yaml(homes, monkeypatch):
    default_home, _, _, _ = homes
    (default_home / "config.yaml").write_text("agent: {unclosed\n", encoding="utf-8")


def _arrange_managed_keys(homes, monkeypatch):
    default_home, _, _, _ = homes
    managed_dir = default_home.parent / "managed"
    managed_dir.mkdir()
    (managed_dir / "config.yaml").write_text(
        "plugins:\n"
        "  entries:\n"
        f"    {PLUGIN_ID}:\n"
        "      settings:\n"
        "        locked_profile: pinned-by-it\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_MANAGED_DIR", str(managed_dir))


def _arrange_managed_system(homes, monkeypatch):
    monkeypatch.setenv("HERMES_MANAGED", "nix")


def _arrange_unwritable_vault(homes, monkeypatch):
    def deny(self, *args, **kwargs):
        raise PermissionError(f"read-only vault: {self}")

    monkeypatch.setattr(Path, "touch", deny)


def _arrange_other_target_vault(homes, monkeypatch):
    default_home, target_home, _, _ = homes
    other = default_home.parent / "other-vault"
    other.mkdir()
    raw = yaml.safe_load((target_home / "config.yaml").read_text(encoding="utf-8"))
    settings = raw.setdefault("plugins", {}).setdefault("entries", {}).setdefault(
        PLUGIN_ID, {}
    ).setdefault("settings", {})
    settings["vault_root"] = str(other)
    _write_yaml(target_home / "config.yaml", raw)


BROKEN_CASES = [
    ("tombstoned", _arrange_tombstone, "profile_not_found"),
    ("disabled", _arrange_disabled, "agent_not_enabled"),
    ("missing_package", _arrange_missing_package, "agent_not_installed"),
    ("version_mismatch", _arrange_version_mismatch, "version_mismatch"),
    ("malformed_target_yaml", _arrange_malformed_target_yaml, "config_invalid"),
    ("malformed_default_yaml", _arrange_malformed_default_yaml, "config_invalid"),
    ("managed_keys", _arrange_managed_keys, "managed_config"),
    ("managed_system", _arrange_managed_system, "managed_config"),
    ("unwritable_vault", _arrange_unwritable_vault, "vault_unwritable"),
    ("other_target_vault", _arrange_other_target_vault, "vault_mismatch"),
]


@pytest.mark.parametrize(
    "name, arrange, code", BROKEN_CASES, ids=[case[0] for case in BROKEN_CASES]
)
def test_select_rejects_broken_target_setups(homes, monkeypatch, name, arrange, code):
    default_home, _, vault, plugin_root = homes
    arrange(homes, monkeypatch)
    before = _read_bytes(homes)
    with pytest.raises(StorySetupError) as exc:
        select_story_target(plugin_root, default_home, "writer", str(vault))
    assert exc.value.code == code
    # Failures leave unrelated YAML and the default selection intact.
    assert _read_bytes(homes) == before
    try:
        assert _selected_profile(default_home) is None
    except Exception:
        # Malformed default YAML: byte equality above already proved it untouched.
        pass


def test_vault_write_check_preserves_preexisting_probe_named_file(homes):
    default_home, _, vault, plugin_root = homes
    user_file = vault / ".story-vault-write-probe"
    user_file.write_text("user data", encoding="utf-8")
    before = user_file.stat()

    select_story_target(plugin_root, default_home, "writer", str(vault))

    # The write check must never touch a file it did not create: same content,
    # same metadata, and no probe litter beside it.
    after = user_file.stat()
    assert user_file.read_text(encoding="utf-8") == "user data"
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_mode == before.st_mode
    assert sorted(entry.name for entry in vault.iterdir()) == [".story-vault-write-probe"]


def test_select_default_profile_reuses_one_home(homes):
    default_home, _, vault, plugin_root = homes
    raw = yaml.safe_load((default_home / "config.yaml").read_text(encoding="utf-8"))
    raw["plugins"] = {"enabled": [PLUGIN_ID]}
    _write_yaml(default_home / "config.yaml", raw)

    result = select_story_target(plugin_root, default_home, "Default", str(vault))

    assert result.profile == "default"
    assert result.home == default_home
    assert not (default_home / "profiles" / "default").exists()
    settings = read_user_config_raw(default_home / "config.yaml")["plugins"]["entries"][
        PLUGIN_ID
    ]["settings"]
    assert settings["selected_profile"] == "default"
    assert settings["locked_profile"] == "default"
    assert settings["locked_hermes_home"] == str(default_home.resolve())
    assert settings["vault_root"] == str(vault.resolve())


def test_resolve_reads_selected_target(homes):
    default_home, target_home, vault, plugin_root = homes
    select_story_target(plugin_root, default_home, "writer", str(vault))
    result = resolve_story_target(plugin_root, default_home)
    assert result.profile == "writer"
    assert result.home == target_home
    assert result.vault_root == vault.resolve()
    assert result.settings["locked_profile"] == "writer"


def test_resolve_requires_shared_vault_root_in_default_config(homes):
    default_home, _, vault, plugin_root = homes
    select_story_target(plugin_root, default_home, "writer", str(vault))
    raw = yaml.safe_load((default_home / "config.yaml").read_text(encoding="utf-8"))
    settings = raw["plugins"]["entries"][PLUGIN_ID]["settings"]
    settings.pop("vault_root")
    assert settings.get("selected_profile") == "writer"
    _write_yaml(default_home / "config.yaml", raw)

    with pytest.raises(StorySetupError) as exc:
        resolve_story_target(plugin_root, default_home)
    assert exc.value.code == "configuration_incomplete"


def test_resolve_without_selection_fails(homes):
    default_home, _, _, plugin_root = homes
    with pytest.raises(StorySetupError) as exc:
        resolve_story_target(plugin_root, default_home)
    assert exc.value.code == "profile_not_selected"


def test_selected_target_guard_runs_and_detects_switch(homes):
    default_home, _, vault, plugin_root = homes
    select_story_target(plugin_root, default_home, "writer", str(vault))
    ran = []
    with selected_target_guard(default_home, "writer"):
        ran.append(True)
    assert ran == [True]
    with pytest.raises(StorySetupError) as exc:
        with selected_target_guard(default_home, "other"):
            ran.append(False)
    assert exc.value.code == "profile_switched"
    assert ran == [True]


def test_hermes_sdk_surface_matches_adapter() -> None:
    """Real SDK imports: fail loudly if a Hermes upgrade moves the adapter's seams."""
    import inspect

    import hermes_constants
    from hermes_cli import config as config_mod
    from hermes_cli import managed_scope, plugins_state, profiles

    for name in (
        "normalize_profile_name",
        "validate_profile_name",
        "profile_exists",
        "get_profile_dir",
    ):
        assert callable(getattr(profiles, name))
    assert callable(hermes_constants.set_hermes_home_override)
    assert callable(hermes_constants.reset_hermes_home_override)
    assert callable(config_mod.read_user_config_raw)
    assert callable(config_mod.save_config)
    assert callable(config_mod.get_config_path)
    assert callable(config_mod.is_managed)
    assert callable(config_mod.load_config_readonly)
    assert hasattr(config_mod, "_CONFIG_LOCK")
    assert callable(managed_scope.is_key_managed)
    assert callable(plugins_state._locked_plugin_state)
    params = inspect.signature(config_mod.save_config).parameters
    assert "preserve_keys" in params and "merge_existing" in params
    assert profiles.normalize_profile_name("Writer") == "writer"
    with pytest.raises(ValueError):
        profiles.validate_profile_name("../writer")
