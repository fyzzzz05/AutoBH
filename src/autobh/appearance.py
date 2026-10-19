"""Local UI preferences, independent of accounts and background workers."""
from pathlib import Path

from .storage import atomic_json, file_lock, read_json

MODES = ("system", "light", "dark")


def read_appearance(root: Path) -> str:
    try:
        settings = read_json(root / "preferences.json", {})
        mode = settings.get("appearance") if isinstance(settings, dict) else None
        return mode if mode in MODES else "system"
    except (OSError, ValueError):
        return "system"


def save_appearance(root: Path, mode: str) -> None:
    if not isinstance(mode, str) or mode not in MODES:
        raise ValueError("外观仅支持系统、浅色或深色")
    with file_lock(root / "preferences.lock"):
        try:
            settings = read_json(root / "preferences.json", {})
        except ValueError:
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        settings["appearance"] = mode
        atomic_json(root / "preferences.json", settings)
