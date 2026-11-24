"""Writable locations for the log and for settings.

An installed copy is marked by ``installed.txt`` beside the executable.
That copy keeps its log and settings under ``%LOCALAPPDATA%\\ProSnip-Bob``
because Program Files is not writable. A portable folder still prefers
the folder that contains the executable.
"""

import os
import sys
from pathlib import Path

APP_NAME = "ProSnip-Bob"


def installed_copy() -> bool:
    if not getattr(sys, "frozen", False):
        return False
    return (Path(sys.executable).resolve().parent / "installed.txt").is_file()


def user_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME
