"""OpenRouter vision API client with retry and backoff."""

from __future__ import annotations

import time
from typing import Any

import httpx
from loguru import logger

from config import Settings


class VisionClientError(Exception):
    """Raised when the vision API returns an unrecoverable error."""


class VisionClient:
    """Client for OpenRouter multimodal chat completions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.openrouter_base_url,
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/ai-screen-suffler",
                "X-Title": "AI Screen Suffler",
            },
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def analyze_image(
        self,
        image_base64: str,
        system_prompt: str,
        *,
        mime_type: str = "image/jpeg",
        user_message: str = "Analyze the attached screenshot.",
    ) -> str:
        """Send an image to the vision model and return the assistant reply."""
        payload = self._build_payload(image_base64, system_prompt, mime_type, user_message)
        response_data = self._post_with_retry(payload)
        return self._extract_content(response_data)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> VisionClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _build_payload(
        self,
        image_base64: str,
        system_prompt: str,
        mime_type: str,
        user_message: str,
    ) -> dict[str, Any]:
        return {
            "model": self._settings.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                        },
                    ],
                },
            ],
        }

    def _post_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self._settings.max_retries + 1):
            try:
                logger.info(
                    "Calling OpenRouter (model={}, attempt={}/{})",
                    self._settings.model_name,
                    attempt,
                    self._settings.max_retries,
                )
                response = self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in {401, 403, 404, 422}:
                    logger.error("Non-retryable API error: HTTP {}", status)
                    raise VisionClientError(self._format_http_error(exc)) from exc
                logger.warning("Retryable HTTP error: HTTP {}", status)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning("Network error on attempt {}: {}", attempt, exc)

            if attempt < self._settings.max_retries:
                delay = self._settings.retry_base_delay * (2 ** (attempt - 1))
                logger.info("Retrying in {:.1f}s...", delay)
                time.sleep(delay)

        raise VisionClientError(
            f"Vision API failed after {self._settings.max_retries} attempts"
        ) from last_error

    @staticmethod
    def _extract_content(response_data: dict[str, Any]) -> str:
        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VisionClientError("Unexpected API response structure") from exc

        if not isinstance(content, str) or not content.strip():
            raise VisionClientError("Empty response from vision model")

        return content.strip()

    @staticmethod
    def _format_http_error(exc: httpx.HTTPStatusError) -> str:
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return f"HTTP {exc.response.status_code}: {detail}"
