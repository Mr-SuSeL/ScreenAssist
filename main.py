"""Application entry point — tray trigger, capture pipeline, stealth UI."""

from __future__ import annotations

import sys
import threading

from loguru import logger

from config import settings
from core.paths import log_file_path
from core.prompt_manager import get_system_prompt
from core.screen_capture import ScreenCaptureError, capture_monitor, log_available_monitors
from core.vision_engine import VisionClient, VisionClientError
from ui.overlay import OverlayWindow
from ui.tray import SystemTray


class Application:
    """Orchestrates stealth UI, tray handling, and the vision pipeline."""

    def __init__(self) -> None:
        self._overlay = OverlayWindow(settings)
        self._vision_client = VisionClient(settings)
        self._processing_lock = threading.Lock()
        self._shutdown = threading.Event()
        self._tray = SystemTray(
            on_analyze=self.trigger_capture,
            on_toggle_overlay=self._overlay.toggle_visibility,
            on_settings=self._overlay.open_settings,
            on_exit=self.shutdown,
        )

        self._overlay.on_mode_change(self._on_mode_change)
        self._overlay.on_shutdown(self.shutdown)

    def run(self) -> None:
        """Start the tray icon and launch the stealth overlay."""
        self._configure_logging()
        logger.info(
            "Starting ScreenAssist (openrouter={}, gemini={})",
            settings.model_name,
            settings.gemini_model_name,
        )
        log_available_monitors()
        logger.info("Capture target: monitor index {}", settings.capture_monitor_index)

        self._tray.start()

        try:
            self._overlay.run()
        finally:
            self._finalize_shutdown()

    def trigger_capture(self) -> None:
        """Start the capture pipeline unless one is already running."""
        if not self._processing_lock.acquire(blocking=False):
            logger.warning("Capture already in progress — ignoring tray trigger")
            self._overlay.set_status("Busy — analysis already in progress.")
            return

        worker = threading.Thread(
            target=self._run_capture_pipeline,
            name="capture-worker",
            daemon=True,
        )
        worker.start()

    def shutdown(self) -> None:
        """Request a graceful application shutdown."""
        if self._shutdown.is_set():
            return

        logger.info("Shutdown requested")
        self._shutdown.set()
        self._tray.stop()
        self._overlay.shutdown()

    def _run_capture_pipeline(self) -> None:
        try:
            self._overlay.show()
            self._overlay.set_status("Capturing...")
            capture = capture_monitor(
                settings.capture_monitor_index,
                jpeg_quality=settings.jpeg_quality,
            )

            mode = self._overlay.current_mode
            prompt = get_system_prompt(mode)
            self._overlay.set_status(f"Analyzing ({mode})...")

            result = self._vision_client.analyze_image(
                image_base64=capture.base64_data,
                system_prompt=prompt,
            )

            self._overlay.set_response(result)
            self._overlay.set_status(
                f"Done ({capture.width}x{capture.height}). Use tray to analyze again."
            )
            logger.success("Analysis completed for mode={}", mode)
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

    def _finalize_shutdown(self) -> None:
        self._shutdown.set()
        self._tray.stop()
        self._vision_client.close()
        logger.info("Application shut down cleanly")

    @staticmethod
    def _on_mode_change(mode: str) -> None:
        logger.info("Prompt mode changed to {}", mode)

    @staticmethod
    def _configure_logging() -> None:
        logger.remove()
        logger.add(
            log_file_path(),
            level="INFO",
            rotation="1 MB",
            retention=3,
            encoding="utf-8",
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
                "{name}:{function} - {message}"
            ),
        )

        stderr = getattr(sys, "stderr", None)
        if stderr is not None and hasattr(stderr, "isatty") and stderr.isatty():
            logger.add(
                stderr,
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
