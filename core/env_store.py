"""Persist runtime configuration to the .env file."""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from config import Settings

from core.paths import app_dir

ENV_PATH = app_dir() / ".env"


def encode_env_value(value: str) -> str:
    """Encode multiline strings for single-line .env storage."""
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def persist_settings(settings: Settings, env_path: Path = ENV_PATH) -> None:
    """Write user-editable settings to the .env file, preserving other entries."""
    updates = {
        "CAPTURE_MONITOR_INDEX": str(settings.capture_monitor_index),
        "CUSTOM_PROMPT": encode_env_value(settings.custom_prompt),
    }
    _merge_env_file(env_path, updates)
    logger.info("Saved configuration to {}", env_path.resolve())


def _merge_env_file(env_path: Path, updates: dict[str, str]) -> None:
    remaining = dict(updates)
    lines: list[str] = []

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    merged: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            merged.append(line)
            continue

        key, _ = stripped.split("=", 1)
        if key in remaining:
            merged.append(f"{key}={remaining.pop(key)}")
        else:
            merged.append(line)

    for key, value in remaining.items():
        merged.append(f"{key}={value}")

    env_path.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")
