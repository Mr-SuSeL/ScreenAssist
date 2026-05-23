"""Application configuration loaded from environment variables."""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.paths import app_dir


class Settings(BaseSettings):
    """Validated settings sourced from environment / .env file."""

    openrouter_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    model_name: str = "google/gemini-2.5-flash"
    gemini_model_name: str = "gemini-2.5-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    max_retries: int = 3
    retry_base_delay: float = 1.0

    circuit_failure_threshold: int = 3
    circuit_recovery_timeout: float = 60.0

    jpeg_quality: int = 85
    hotkey: str = "f8"
    capture_monitor_index: int = 1
    custom_prompt: str = "You are a helpful assistant. Provide concise answers."

    model_config = SettingsConfigDict(
        env_file=str(app_dir() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("openrouter_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        """Treat blank .env entries (KEY=) as missing configuration."""
        if value == "":
            return None
        return value

    @field_validator("custom_prompt", mode="before")
    @classmethod
    def _decode_custom_prompt(cls, value: object) -> object:
        """Decode escaped newlines from .env storage."""
        if not isinstance(value, str):
            return value
        return value.replace("\\n", "\n")


settings = Settings()
