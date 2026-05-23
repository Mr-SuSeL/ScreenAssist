"""Application entry point — hotkey listener, capture pipeline, UI."""

from __future__ import annotations

import sys
import threading

import keyboard
from loguru import logger

from config import settings
from core.prompt_manager import PromptMode, get_system_prompt
from core.screen_capture import ScreenCaptureError, capture_primary_monitor
from core.vision_engine import VisionClient, VisionClientError
from ui.overlay import OverlayWindow


class Application:
    """Orchestrates UI, hotkey handling, and the vision pipeline."""

    def __init__(self) -> None:
        self._overlay = OverlayWindow()
        self._vision_client = VisionClient(settings)
        self._processing_lock = threading.Lock()
        self._shutdown = threading.Event()

        self._overlay.on_mode_change(self._on_mode_change)

    def run(self) -> None:
        """Start hotkey listener and launch the overlay."""
        self._configure_logging()
        logger.info(
            "Starting ScreenAssist (openrouter={}, gemini={})",
            settings.model_name,
            settings.gemini_model_name,
        )

        hotkey_thread = threading.Thread(
            target=self._register_hotkey,
            name="hotkey-listener",
            daemon=True,
        )
        hotkey_thread.start()

        try:
            self._overlay.run()
        finally:
            self._shutdown.set()
            keyboard.unhook_all_hotkeys()
            self._vision_client.close()
            logger.info("Application shut down cleanly")

    def _register_hotkey(self) -> None:
        keyboard.add_hotkey(settings.hotkey, self._on_hotkey_pressed, suppress=False)
        logger.info("Registered global hotkey: {}", settings.hotkey.upper())
        self._shutdown.wait()

    def _on_hotkey_pressed(self) -> None:
        if not self._processing_lock.acquire(blocking=False):
            logger.warning("Capture already in progress — ignoring hotkey")
            self._overlay.set_status("Busy — analysis already in progress.")
            return

        worker = threading.Thread(
            target=self._run_capture_pipeline,
            name="capture-worker",
            daemon=True,
        )
        worker.start()

    def _run_capture_pipeline(self) -> None:
        try:
            self._overlay.set_status("Capturing...")
            capture = capture_primary_monitor(jpeg_quality=settings.jpeg_quality)

            mode = self._overlay.current_mode
            prompt = get_system_prompt(mode)
            self._overlay.set_status(f"Analyzing ({mode.value})...")

            result = self._vision_client.analyze_image(
                image_base64=capture.base64_data,
                system_prompt=prompt,
            )

            self._overlay.set_response(result)
            self._overlay.set_status(
                f"Done ({capture.width}x{capture.height}). Press F8 again."
            )
            logger.success("Analysis completed for mode={}", mode.value)
        except ScreenCaptureError as exc:
            message = f"Error: Capture failed — {exc}"
            logger.error(message)
            self._overlay.set_status(message)
        except VisionClientError as exc:
            message = f"Error: {exc}"
            logger.error(message)
            self._overlay.set_status(message)
        except Exception:
            logger.exception("Unexpected error during capture pipeline")
            self._overlay.set_status("Error: Unexpected failure — check logs for details.")
        finally:
            self._processing_lock.release()

    @staticmethod
    def _on_mode_change(mode: PromptMode) -> None:
        logger.info("Prompt mode changed to {}", mode.value)

    @staticmethod
    def _configure_logging() -> None:
        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
                "<level>{message}</level>"
            ),
        )


def main() -> None:
    Application().run()


if __name__ == "__main__":
    main()
