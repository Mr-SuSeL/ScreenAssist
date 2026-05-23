"""Application path helpers with PyInstaller frozen-bundle support."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    """Return True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def bundle_dir() -> Path:
    """Directory containing bundled read-only assets (_MEIPASS when frozen)."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """Writable application directory (executable dir when frozen, project root otherwise)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    """Resolve a bundled asset path for dev and PyInstaller deployments."""
    return bundle_dir().joinpath(*parts)


def log_file_path() -> Path:
    """Return the path used for file-based logging (pythonw / frozen builds)."""
    logs_dir = app_dir() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir / "screenassist.log"
