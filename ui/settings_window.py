"""Settings dialog for ScreenAssist runtime configuration."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import customtkinter as ctk
from loguru import logger

from core.env_store import persist_settings
from core.screen_capture import MonitorInfo, list_monitors
from ui.stealth import apply_stealth_window

if TYPE_CHECKING:
    from config import Settings


class SettingsWindow:
    """Modal settings panel for monitor selection and .env persistence."""

    def __init__(self, parent: ctk.CTkBaseClass, settings: Settings) -> None:
        self._settings = settings
        self._monitors: list[MonitorInfo] = []
        self._label_to_index: dict[str, int] = {}
        self._loading = False

        self._window = ctk.CTkToplevel(parent)
        self._window.title("ScreenAssist — Settings")
        self._window.geometry("460x220")
        self._window.resizable(False, False)
        self._window.attributes("-topmost", True)
        self._window.transient(parent)
        self._window.grab_set()
        apply_stealth_window(self._window)

        self._build_layout()
        self._load_monitors_async()
        self._window.protocol("WM_DELETE_WINDOW", self._close)

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self._window, corner_radius=12)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            container,
            text="Capture Monitor",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", pady=(0, 4))

        ctk.CTkLabel(
            container,
            text="Select the monitor ScreenAssist captures from the tray action.",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        ).pack(anchor="w", pady=(0, 12))

        self._monitor_var = ctk.StringVar(value="Loading monitors...")
        self._monitor_menu = ctk.CTkOptionMenu(
            container,
            variable=self._monitor_var,
            values=["Loading monitors..."],
            command=self._handle_monitor_selected,
            width=400,
            state="disabled",
        )
        self._monitor_menu.pack(fill="x", pady=(0, 8))

        self._status_label = ctk.CTkLabel(
            container,
            text="Detecting displays...",
            font=ctk.CTkFont(size=12),
            text_color="#7ec8ff",
        )
        self._status_label.pack(anchor="w", pady=(0, 12))

        button_row = ctk.CTkFrame(container, fg_color="transparent")
        button_row.pack(fill="x")

        self._save_button = ctk.CTkButton(
            button_row,
            text="Save",
            command=self._handle_save,
            width=100,
            state="disabled",
        )
        self._save_button.pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            button_row,
            text="Cancel",
            command=self._close,
            width=100,
            fg_color="transparent",
            border_width=1,
        ).pack(side="right")

    def _load_monitors_async(self) -> None:
        if self._loading:
            return

        self._loading = True
        worker = threading.Thread(
            target=self._fetch_monitors,
            name="monitor-discovery",
            daemon=True,
        )
        worker.start()

    def _fetch_monitors(self) -> None:
        try:
            monitors = list_monitors()
            self._schedule(lambda: self._apply_monitors(monitors))
        except Exception as exc:
            logger.exception("Failed to enumerate monitors")
            self._schedule(lambda: self._show_monitor_error(str(exc)))

    def _apply_monitors(self, monitors: list[MonitorInfo]) -> None:
        self._monitors = monitors
        self._label_to_index = {monitor.dropdown_label(): monitor.index for monitor in monitors}

        if not monitors:
            self._monitor_var.set("No monitors detected")
            self._monitor_menu.configure(values=["No monitors detected"], state="disabled")
            self._status_label.configure(text="No displays found.")
            self._loading = False
            return

        labels = [monitor.dropdown_label() for monitor in monitors]
        current_index = self._settings.capture_monitor_index
        selected_label = next(
            (monitor.dropdown_label() for monitor in monitors if monitor.index == current_index),
            labels[0],
        )

        self._monitor_menu.configure(values=labels, state="normal")
        self._monitor_var.set(selected_label)
        self._settings.capture_monitor_index = self._label_to_index[selected_label]
        self._status_label.configure(
            text=f"Active capture target: monitor index {self._settings.capture_monitor_index}"
        )
        self._save_button.configure(state="normal")
        self._loading = False

    def _show_monitor_error(self, message: str) -> None:
        self._monitor_var.set("Monitor detection failed")
        self._monitor_menu.configure(values=["Monitor detection failed"], state="disabled")
        self._status_label.configure(text=f"Error: {message}")
        self._loading = False

    def _handle_monitor_selected(self, label: str) -> None:
        index = self._label_to_index.get(label)
        if index is None:
            return

        self._settings.capture_monitor_index = index
        self._status_label.configure(text=f"Active capture target: monitor index {index}")
        logger.info("Capture monitor changed to index {}", index)

    def _handle_save(self) -> None:
        try:
            persist_settings(self._settings)
            self._status_label.configure(text="Settings saved to .env")
        except OSError as exc:
            logger.error("Failed to save settings: {}", exc)
            self._status_label.configure(text=f"Save failed: {exc}")

    def focus(self) -> None:
        """Bring the settings window to the front if it is open."""
        if self._window.winfo_exists():
            self._window.focus()

    def is_open(self) -> bool:
        """Return True when the settings window is currently visible."""
        return self._window.winfo_exists()

    def close(self) -> None:
        """Close the settings window."""
        self._close()

    def _close(self) -> None:
        if not self._window.winfo_exists():
            return
        self._window.grab_release()
        self._window.destroy()

    def _schedule(self, callback: Callable[[], None]) -> None:
        """Schedule UI updates on the Tkinter main thread."""
        if self._window.winfo_exists():
            self._window.after(0, callback)
