"""Scoped Story profile resolution and config transactions on Hermes homes.

All Hermes SDK imports stay inside adapter functions so a missing or upgraded
Hermes installation fails at the call site, not at plugin import time.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from secrets import token_hex

import yaml

PLUGIN_ID = "story-construction"


class StorySetupError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StoryTarget:
    profile: str
    home: Path
    vault_root: Path
    plugin_root: Path
    settings: Mapping[str, object]


def resolve_story_target(api_plugin_root: Path, default_home: Path) -> StoryTarget:
    """Resolve the configured writing target from the default home's selection."""

    api_root = Path(api_plugin_root)
    default_path = Path(default_home)
    default_settings = _settings_from_raw(_read_raw_config(default_path))
    selected = _setting_text(default_settings, "selected_profile")
    if not selected:
        raise StorySetupError("profile_not_selected")
    canon = _canonical_profile(selected)
    home = _profile_home(canon, default_path)
    _validate_package(api_root, home, canon)
    target_raw = _read_raw_config(home)
    _validate_enabled(target_raw)
    settings = _settings_from_raw(target_raw)

    locked_profile = _setting_text(settings, "locked_profile")
    locked_home = _setting_text(settings, "locked_hermes_home")
    vault_text = _setting_text(settings, "vault_root")
    shared_text = _setting_text(default_settings, "vault_root")
    # The default home's selection is only complete with its shared Vault: a
    # selected_profile without vault_root is a partial record, never writable.
    if not locked_profile or not locked_home or not vault_text or not shared_text:
        raise StorySetupError("configuration_incomplete")
    if locked_profile != canon:
        raise StorySetupError("profile_switched")
    if _home_path(locked_home) != home.resolve():
        raise StorySetupError("hermes_home_mismatch")
    vault = _canonical_vault(vault_text)
    if _vault_path(shared_text) != vault:
        raise StorySetupError("vault_mismatch")
    return StoryTarget(
        profile=canon,
        home=home,
        vault_root=vault,
        plugin_root=api_root,
        settings=dict(settings),
    )


def select_story_target(
    api_plugin_root: Path, default_home: Path, profile: str, vault_root: str | None = None
) -> StoryTarget:
    """Validate one writing target fully, then persist its locks and selection.

    Write ordering: target ``locked_profile``/``locked_hermes_home``/``vault_root``
    first, then the default home's ``selected_profile`` and shared ``vault_root``.
    Any failure before the second write leaves the previous selection intact.
    """

    api_root = Path(api_plugin_root)
    default_path = Path(default_home)
    canon = _canonical_profile(profile)
    home = _profile_home(canon, default_path)
    _validate_package(api_root, home, canon)

    default_raw = _read_raw_config(default_path)
    target_raw = _read_raw_config(home)
    _validate_enabled(target_raw)
    shared_text = _setting_text(_settings_from_raw(default_raw), "vault_root")
    target_text = _setting_text(_settings_from_raw(target_raw), "vault_root")

    if vault_root:
        vault = _canonical_vault(vault_root)
    else:
        base = target_text or shared_text
        if not base:
            raise StorySetupError("configuration_incomplete")
        vault = _canonical_vault(base)
    if target_text and _vault_path(target_text) != vault:
        raise StorySetupError("vault_mismatch")
    if shared_text and _vault_path(shared_text) != vault:
        raise StorySetupError("vault_mismatch")
    _require_writable_vault(vault)

    # Target bindings first: a failure here cannot leave a stale selection behind.
    _write_story_settings(
        home,
        {
            "locked_profile": canon,
            "locked_hermes_home": str(home.resolve()),
            "vault_root": str(vault),
        },
    )
    _write_story_settings(
        default_path,
        {
            "selected_profile": canon,
            "vault_root": str(vault),
        },
    )
    return StoryTarget(
        profile=canon,
        home=home,
        vault_root=vault,
        plugin_root=api_root,
        settings=_story_settings(home),
    )


@contextmanager
def selected_target_guard(default_home: Path, expected_profile: str):
    """Hold the default config file lock across a caller's read-modify-write.

    Re-reads ``selected_profile`` under the same lock ``select_story_target``
    writes with, and keeps that lock for the duration of the caller's mutation
    so a concurrent switch cannot interleave.
    """

    from hermes_cli import config as config_mod
    from hermes_cli.plugins_state import _locked_plugin_state
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    expected = _normalized_profile(expected_profile)
    token = set_hermes_home_override(Path(default_home))
    try:
        path = config_mod.get_config_path()
        with _locked_plugin_state(path), config_mod._CONFIG_LOCK:
            try:
                raw = config_mod.read_user_config_raw() or {}
            except Exception as exc:
                raise StorySetupError("config_invalid") from exc
            current = _setting_text(_settings_from_raw(raw), "selected_profile")
            if current != expected:
                raise StorySetupError("profile_switched")
            yield
    finally:
        reset_hermes_home_override(token)


def _normalized_profile(profile: str) -> str:
    from hermes_cli import profiles as hermes_profiles

    try:
        canon = hermes_profiles.normalize_profile_name(profile)
        hermes_profiles.validate_profile_name(canon)
    except ValueError as exc:
        raise StorySetupError("profile_invalid") from exc
    return canon


def _canonical_profile(profile: str) -> str:
    from hermes_cli import profiles as hermes_profiles

    canon = _normalized_profile(profile)
    if not hermes_profiles.profile_exists(canon):
        raise StorySetupError("profile_not_found")
    return canon


def _profile_home(canon: str, default_home: Path) -> Path:
    if canon == "default":
        # The default Profile reuses its one home/install, never a second copy.
        return default_home
    from hermes_cli import profiles as hermes_profiles

    return Path(hermes_profiles.get_profile_dir(canon))


def _read_raw_config(home: Path) -> dict:
    from hermes_cli import config as config_mod

    try:
        return config_mod.read_user_config_raw(home / "config.yaml") or {}
    except Exception as exc:
        raise StorySetupError("config_invalid") from exc


def _read_manifest(path: Path) -> dict:
    if not path.is_file():
        raise StorySetupError("agent_not_installed")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise StorySetupError("config_invalid") from exc
    if not isinstance(data, dict):
        raise StorySetupError("config_invalid")
    return data


def _validate_package(api_root: Path, home: Path, canon: str) -> None:
    api_manifest = _read_manifest(api_root / "plugin.yaml")
    if canon == "default":
        target_manifest_path = api_root / "plugin.yaml"
    else:
        target_manifest_path = home / "plugins" / PLUGIN_ID / "plugin.yaml"
    target_manifest = _read_manifest(target_manifest_path)
    if api_manifest.get("name") != PLUGIN_ID or target_manifest.get("name") != PLUGIN_ID:
        raise StorySetupError("agent_name_mismatch")
    if str(api_manifest.get("version") or "") != str(target_manifest.get("version") or ""):
        raise StorySetupError("version_mismatch")


def _validate_enabled(raw: Mapping[str, object]) -> None:
    plugins = raw.get("plugins") if isinstance(raw.get("plugins"), Mapping) else {}
    enabled = plugins.get("enabled") if isinstance(plugins.get("enabled"), list) else None
    disabled = plugins.get("disabled") if isinstance(plugins.get("disabled"), list) else []
    if not enabled or PLUGIN_ID not in enabled or PLUGIN_ID in disabled:
        raise StorySetupError("agent_not_enabled")


def _settings_from_raw(raw: Mapping[str, object]) -> dict[str, object]:
    node: object = raw
    for key in ("plugins", "entries", PLUGIN_ID, "settings"):
        if not isinstance(node, Mapping) or key not in node:
            return {}
        node = node[key]
    return dict(node) if isinstance(node, Mapping) else {}


def _setting_text(settings: Mapping[str, object], key: str) -> str | None:
    value = settings.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _home_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _vault_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _canonical_vault(value: str) -> Path:
    vault = _vault_path(value)
    if not vault.is_dir():
        raise StorySetupError("vault_not_directory")
    return vault


def _require_writable_vault(vault: Path) -> None:
    """Prove writability with one exclusive-create probe only this call removes.

    A pre-existing file with any name is never touched, truncated, or deleted.
    """

    probe = vault / f".story-vault-write-probe-{token_hex(8)}"
    created = False
    try:
        probe.touch(exist_ok=False)
        created = True
    except OSError as exc:
        raise StorySetupError("vault_unwritable") from exc
    finally:
        if created:
            with suppress(OSError):
                probe.unlink(missing_ok=True)


def _story_settings(home: Path) -> dict[str, object]:
    from hermes_cli.config import load_config_readonly
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(home)
    try:
        raw = load_config_readonly() or {}
        return dict(_settings_from_raw(raw))
    finally:
        reset_hermes_home_override(token)


def _write_story_settings(home: Path, changes: Mapping[str, object]) -> None:
    from hermes_cli import config as config_mod
    from hermes_cli import managed_scope
    from hermes_cli.plugins_state import _locked_plugin_state
    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(home)
    try:
        path = config_mod.get_config_path()
        if config_mod.is_managed() or any(
            managed_scope.is_key_managed(f"plugins.entries.{PLUGIN_ID}.settings.{key}")
            for key in changes
        ):
            raise StorySetupError("managed_config")
        with _locked_plugin_state(path), config_mod._CONFIG_LOCK:
            config_mod.read_user_config_raw()
            partial = {"plugins": {"entries": {PLUGIN_ID: {"settings": dict(changes)}}}}
            preserve = {
                ("plugins", "entries", PLUGIN_ID, "settings", key) for key in changes
            }
            try:
                config_mod.save_config(partial, preserve_keys=preserve, merge_existing=True)
            except StorySetupError:
                raise
            except RuntimeError as exc:
                raise StorySetupError("config_invalid") from exc
            except OSError as exc:
                raise StorySetupError("config_write_failed") from exc
    finally:
        reset_hermes_home_override(token)
