"""Subprocess commands shared by normal Python and the bundled macOS runtime."""
from __future__ import annotations

import os
import sys

NATIVE_MODULES = {"class": "autosign_cli", "boya": "autoboya", "td": "auto_td.cli", "ygdk": "autobh.ygdk_cli"}


def autobh_command(*arguments: str) -> list[str]:
    prefix = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "autobh"]
    return [*prefix, *arguments]


def native_command(feature: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--native", feature]
    return [sys.executable, "-m", NATIVE_MODULES[feature]]


def subprocess_environment():
    if getattr(sys, "frozen", False):
        return {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    return None
