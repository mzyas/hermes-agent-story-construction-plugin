"""Translate Vault paths between the Windows and WSL spellings of one drive."""

from __future__ import annotations

import os
import re
from pathlib import Path

# ``E:`` or ``E:/...`` (after backslashes are read as separators). ``E:foo`` is a
# drive-relative path with no fixed location, so it is deliberately not matched.
_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):(?:/(.*))?$")
# ``/mnt/e`` or ``/mnt/e/...``; ``/mnt/ee`` and ``/mnt/wsl`` are not drives.
_WSL_DRIVE = re.compile(r"^/mnt/([A-Za-z])(?:/(.*))?$")


def translate_vault_text(value: str, os_name: str) -> str:
    """Rewrite a drive-letter Vault path into the spelling used by ``os_name``.

    ``E:/Vault`` and ``/mnt/e/Vault`` name the same directory. Only paths written
    in the other side's drive spelling are rewritten; every other path, including
    a native POSIX path that contains a backslash, is returned unchanged.
    """

    text = value.strip()
    if os_name == "nt":
        wsl = _WSL_DRIVE.match(text)
        if wsl:
            return f"{wsl[1].upper()}:/{wsl[2] or ''}"
        return text
    windows = _WINDOWS_DRIVE.match(text.replace("\\", "/"))
    if windows:
        return f"/mnt/{windows[1].lower()}/{windows[2] or ''}".rstrip("/")
    return text


def native_vault_path(value: str | Path) -> Path:
    """Resolve a configured Vault path in this process' native spelling."""

    text = translate_vault_text(str(value), os.name)
    return Path(text).expanduser().resolve(strict=False)
