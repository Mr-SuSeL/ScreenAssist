"""System tray integration for low-profile capture triggering."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import pystray
from loguru import logger
from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from pystray import Icon


class SystemTray:
    """Background tray icon that triggers capture without global keyboard hooks."""

    def __init__(
        self,
        *,
        on_analyze: Callable[[], None],
        on_toggle_overlay: Callable[[], None],
        on_settings: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self._on_analyze = on_analyze
        self._on_toggle_overlay = on_toggle_overlay
        self._on_settings = on_settings
        self._on_exit = on_exit
        self._icon: Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Launch the tray icon loop on a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._run, name="system-tray", daemon=True)
        self._thread.start()
        logger.info("System tray icon started")

    def stop(self) -> None:
        """Stop the tray icon loop."""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                logger.debug("Tray icon already stopped")

    def _run(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Analyze Screen", self._menu_analyze, default=True),
            pystray.MenuItem("Show / Hide Overlay", self._menu_toggle_overlay),
            pystray.MenuItem("Settings", self._menu_settings),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._menu_exit),
        )
        self._icon = pystray.Icon(
            "desktop-window-manager",
            _create_tray_image(),
            "Desktop Window Manager",
            menu,
        )
        self._icon.run()

    def _menu_analyze(self, _icon: Icon, _item: pystray.MenuItem) -> None:
        logger.debug("Tray analyze action triggered")
        self._on_analyze()

    def _menu_toggle_overlay(self, _icon: Icon, _item: pystray.MenuItem) -> None:
        self._on_toggle_overlay()

    def _menu_settings(self, _icon: Icon, _item: pystray.MenuItem) -> None:
        self._on_settings()

    def _menu_exit(self, _icon: Icon, _item: pystray.MenuItem) -> None:
        self._on_exit()


def _create_tray_image(size: int = 64) -> Image.Image:
    """Build a subtle gray geometric icon resembling a background service."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    body = (120, 124, 132, 255)
    accent = (170, 174, 182, 255)

    padding = size // 8
    draw.rounded_rectangle(
        (padding, padding, size - padding, size - padding),
        radius=size // 6,
        fill=body,
    )
    draw.polygon(
        [
            (size * 0.34, size * 0.38),
            (size * 0.34, size * 0.62),
            (size * 0.68, size * 0.50),
        ],
        fill=accent,
    )
    return image
