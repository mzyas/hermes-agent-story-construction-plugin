from __future__ import annotations

import os
from pathlib import Path

import pytest

from story_construction_plugin.paths import native_vault_path


@pytest.mark.skipif(os.name != "nt", reason="Windows spelling of WSL paths")
def test_wsl_drive_path_becomes_windows_drive_path() -> None:
    assert native_vault_path("/mnt/e/My Vault") == Path("E:/My Vault")
    assert native_vault_path("/mnt/e") == Path("E:/")


@pytest.mark.skipif(os.name == "nt", reason="WSL spelling of Windows paths")
def test_windows_drive_path_becomes_wsl_mount_path() -> None:
    assert native_vault_path("E:/My Vault") == Path("/mnt/e/My Vault")
    assert native_vault_path("E:\\My Vault\\notes") == Path("/mnt/e/My Vault/notes")


def test_native_paths_are_left_alone(tmp_path: Path) -> None:
    assert native_vault_path(str(tmp_path)) == tmp_path.resolve()
    assert native_vault_path(f"  {tmp_path}  ") == tmp_path.resolve()
