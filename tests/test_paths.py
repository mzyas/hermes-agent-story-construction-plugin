from __future__ import annotations

import os
from pathlib import Path

import pytest

from story_construction_plugin.paths import native_vault_path, translate_vault_text


@pytest.mark.parametrize(
    "value, expected",
    [
        ("/mnt/e/My Vault", "E:/My Vault"),
        ("/mnt/E/My Vault", "E:/My Vault"),
        ("/mnt/e", "E:/"),
        ("/mnt/e/", "E:/"),
        ("/mnt/e/Vault/", "E:/Vault/"),
        ("/mnt/e/小说 库", "E:/小说 库"),
        ("  /mnt/e/Vault  ", "E:/Vault"),
    ],
)
def test_wsl_drive_spelling_becomes_windows_drive_spelling(value: str, expected: str) -> None:
    assert translate_vault_text(value, "nt") == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("E:/My Vault", "/mnt/e/My Vault"),
        ("e:/My Vault", "/mnt/e/My Vault"),
        ("E:\\My Vault\\notes", "/mnt/e/My Vault/notes"),
        ("E:", "/mnt/e"),
        ("E:/", "/mnt/e"),
        ("E:/Vault/", "/mnt/e/Vault"),
        ("E:/小说 库", "/mnt/e/小说 库"),
        ("  E:/Vault  ", "/mnt/e/Vault"),
    ],
)
def test_windows_drive_spelling_becomes_wsl_mount_spelling(value: str, expected: str) -> None:
    assert translate_vault_text(value, "posix") == expected


@pytest.mark.parametrize(
    "value",
    ["/mnt/ee/Vault", "/mnt/wsl/Vault", "/mnt/e2/Vault", "/mnt", "/home/me/Vault", "E:Vault"],
)
def test_other_paths_are_not_read_as_wsl_drives_on_windows(value: str) -> None:
    assert translate_vault_text(value, "nt") == value


@pytest.mark.parametrize(
    "value",
    ["/mnt/e/Vault", "/mnt/ee/Vault", "/home/me/Vault", "E:foo", "E:foo\\bar", "vault\\notes", "\\\\server\\share"],
)
def test_other_paths_are_left_unchanged_on_posix(value: str) -> None:
    assert translate_vault_text(value, "posix") == value


def test_windows_native_drive_and_unc_paths_are_left_alone() -> None:
    assert translate_vault_text("E:/Vault", "nt") == "E:/Vault"
    assert translate_vault_text("E:\\Vault\\notes", "nt") == "E:\\Vault\\notes"
    assert translate_vault_text("\\\\server\\share\\Vault", "nt") == "\\\\server\\share\\Vault"


@pytest.mark.skipif(os.name != "nt", reason="Windows spelling of WSL paths")
def test_native_vault_path_opens_wsl_spelling_on_windows() -> None:
    assert native_vault_path("/mnt/e/My Vault") == Path("E:/My Vault")
    assert native_vault_path("/mnt/e") == Path("E:/")


@pytest.mark.skipif(os.name == "nt", reason="WSL spelling of Windows paths")
def test_native_vault_path_opens_windows_spelling_in_wsl() -> None:
    assert native_vault_path("E:/My Vault") == Path("/mnt/e/My Vault")
    assert native_vault_path("E:\\My Vault\\notes") == Path("/mnt/e/My Vault/notes")


def test_native_paths_are_left_alone(tmp_path: Path) -> None:
    assert native_vault_path(str(tmp_path)) == tmp_path.resolve()
    assert native_vault_path(f"  {tmp_path}  ") == tmp_path.resolve()
