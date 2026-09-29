"""Translate Vault paths between the Windows and WSL spellings of one drive."""

from __future__ import annotations

import os
import re
from pathlib import Path

_WINDOWS_DRIVE = re.compile(r"^([A-Za-z]):(?:/(.*))?$")
_WSL_DRIVE = re.compile(r"^/mnt/([A-Za-z])(?:/(.*))?$")


def native_vault_path(value: str | Path) -> Path:
    """Resolve a configured Vault path in this process' native spelling.

    ``E:/Vault`` and ``/mnt/e/Vault`` name the same directory; a path written by
    the other side is rewritten so each backend only ever opens paths it can use.
    """

    text = str(value).strip().replace("\\", "/")
    windows = _WINDOWS_DRIVE.match(text)
    wsl = _WSL_DRIVE.match(text)
    if os.name == "nt" and wsl:
        text = f"{wsl[1].upper()}:/{wsl[2] or ''}"
    elif os.name != "nt" and windows:
        text = f"/mnt/{windows[1].lower()}/{windows[2] or ''}"
    return Path(text).expanduser().resolve(strict=False)
