"""Vision API client with Circuit Breaker and OpenRouter → Gemini fallback."""

from __future__ import annotations

import base64
import threading
import time
from enum import Enum
from typing import Any

import google.generativeai as genai
import httpx
from loguru import logger

from config import Settings


class VisionClientError(Exception):
    """Raised when all vision providers fail or return an unrecoverable error."""


class CircuitState(str, Enum):
    """Circuit breaker states for the primary (OpenRouter) provider."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Tracks OpenRouter health and temporarily skips it after repeated failures."""

    def __init__(self, failure_threshold: int, recovery_timeout: float) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state

    def can_try_primary(self) -> bool:
        """Return True when OpenRouter should be attempted."""
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state in {CircuitState.CLOSED, CircuitState.HALF_OPEN}

    def record_success(self) -> None:
        """Reset breaker after a successful primary call."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.info("Circuit breaker closed — OpenRouter recovered")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None

    def record_failure(self) -> None:
        """Increment failures and open the circuit when threshold is reached."""
        with self._lock:
            self._failure_count += 1
            logger.warning(
                "OpenRouter failure {}/{} (circuit={})",
                self._failure_count,
                self._failure_threshold,
                self._state.value,
            )

            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.error(
                    "Circuit breaker OPEN — skipping OpenRouter for {:.0f}s",
                    self._recovery_timeout,
                )

    def _maybe_transition_to_half_open(self) -> None:
        if self._state != CircuitState.OPEN or self._opened_at is None:
            return

        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self._recovery_timeout:
            self._state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker HALF_OPEN — probing OpenRouter")


class VisionClient:
    """Multimodal vision client: OpenRouter primary, Gemini fallback."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._circuit = CircuitBreaker(
            failure_threshold=settings.circuit_failure_threshold,
            recovery_timeout=settings.circuit_recovery_timeout,
        )
        self._http_client: httpx.Client | None = None
        self._gemini_model: genai.GenerativeModel | None = None

        if settings.openrouter_api_key:
            self._http_client = httpx.Client(
                base_url=settings.openrouter_base_url,
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/screenassist",
                    "X-Title": "ScreenAssist",
                },
                timeout=httpx.Timeout(60.0, connect=10.0),
            )
        else:
            logger.warning("OPENROUTER_API_KEY is not configured — primary provider disabled")

        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
            self._gemini_model = genai.GenerativeModel(settings.gemini_model_name)
        else:
            logger.warning("GEMINI_API_KEY is not configured — fallback provider disabled")

    def analyze_image(
        self,
        image_base64: str,
        system_prompt: str,
        *,
        mime_type: str = "image/jpeg",
        user_message: str = "Analyze the attached screenshot.",
    ) -> str:
        """Analyze a screenshot using OpenRouter with Gemini fallback."""
        primary_error: Exception | None = None

        if self._circuit.can_try_primary() and self._http_client is not None:
            try:
                result = self._analyze_with_openrouter(
                    image_base64,
                    system_prompt,
                    mime_type=mime_type,
                    user_message=user_message,
                )
                self._circuit.record_success()
                return result
            except Exception as exc:
                primary_error = exc
                self._circuit.record_failure()
                logger.warning("OpenRouter failed, failing over to Gemini: {}", exc)
        elif self._http_client is None:
            logger.warning("OpenRouter unavailable — skipping primary provider")
        else:
            logger.warning(
                "Circuit breaker is {} — routing directly to Gemini",
                self._circuit.state.value,
            )

        if self._gemini_model is None:
            if primary_error is not None:
                raise VisionClientError(
                    f"OpenRouter failed and Gemini is not configured: {primary_error}"
                )
            raise VisionClientError(
                "No vision provider configured. Set OPENROUTER_API_KEY and/or GEMINI_API_KEY."
            )

        try:
            result = self._analyze_with_gemini(
                image_base64,
                system_prompt,
                mime_type=mime_type,
                user_message=user_message,
            )
            logger.success("Gemini fallback succeeded")
            return result
        except Exception as fallback_exc:
            if primary_error is not None:
                raise VisionClientError(
                    f"All providers failed. OpenRouter: {primary_error}; Gemini: {fallback_exc}"
                ) from fallback_exc
            raise VisionClientError(f"Gemini fallback failed: {fallback_exc}") from fallback_exc

    def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._http_client is not None:
            self._http_client.close()

    def __enter__(self) -> VisionClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _analyze_with_openrouter(
        self,
        image_base64: str,
        system_prompt: str,
        *,
        mime_type: str,
        user_message: str,
    ) -> str:
        if self._http_client is None:
            raise VisionClientError("OpenRouter is not configured (OPENROUTER_API_KEY missing)")

        payload = self._build_openrouter_payload(
            image_base64,
            system_prompt,
            mime_type,
            user_message,
        )
        response_data = self._post_openrouter_with_retry(payload)
        return self._extract_openrouter_content(response_data)

    def _analyze_with_gemini(
        self,
        image_base64: str,
        system_prompt: str,
        *,
        mime_type: str,
        user_message: str,
    ) -> str:
        if self._gemini_model is None:
            raise VisionClientError("Gemini is not configured (GEMINI_API_KEY missing)")

        image_bytes = base64.b64decode(image_base64)
        logger.info("Calling Gemini (model={})", self._settings.gemini_model_name)

        try:
            response = self._gemini_model.generate_content(
                [
                    f"{system_prompt}\n\n{user_message}",
                    {"mime_type": mime_type, "data": image_bytes},
                ]
            )
        except Exception as exc:
            raise VisionClientError(f"Gemini API error: {exc}") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise VisionClientError("Empty response from Gemini model")

        return text.strip()

    def _build_openrouter_payload(
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

    def _post_openrouter_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self._settings.max_retries + 1):
            try:
                logger.info(
                    "Calling OpenRouter (model={}, attempt={}/{})",
                    self._settings.model_name,
                    attempt,
                    self._settings.max_retries,
                )
                response = self._http_client.post("/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status in {401, 403, 404, 422}:
                    logger.error("Non-retryable OpenRouter error: HTTP {}", status)
                    raise VisionClientError(self._format_http_error(exc)) from exc
                logger.warning("Retryable OpenRouter HTTP error: HTTP {}", status)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning("OpenRouter network error on attempt {}: {}", attempt, exc)

            if attempt < self._settings.max_retries:
                delay = self._settings.retry_base_delay * (2 ** (attempt - 1))
                logger.info("Retrying OpenRouter in {:.1f}s...", delay)
                time.sleep(delay)

        raise VisionClientError(
            f"OpenRouter failed after {self._settings.max_retries} attempts"
        ) from last_error

    @staticmethod
    def _extract_openrouter_content(response_data: dict[str, Any]) -> str:
        try:
            content = response_data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise VisionClientError("Unexpected OpenRouter response structure") from exc

        if not isinstance(content, str) or not content.strip():
            raise VisionClientError("Empty response from OpenRouter model")

        return content.strip()

    @staticmethod
    def _format_http_error(exc: httpx.HTTPStatusError) -> str:
        try:
            detail = exc.response.json()
        except ValueError:
            detail = exc.response.text
        return f"HTTP {exc.response.status_code}: {detail}"
