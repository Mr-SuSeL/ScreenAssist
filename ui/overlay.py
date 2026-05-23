"""CustomTkinter always-on-top stealth overlay window."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Final

import customtkinter as ctk

from config import Settings
from core.prompt_manager import AVAILABLE_MODES, DEFAULT_MODE
from ui.settings_window import SettingsWindow
from ui.stealth import apply_stealth_window

StatusCallback = Callable[[str], None]
ModeChangeCallback = Callable[[str], None]
ShutdownCallback = Callable[[], None]


class OverlayWindow:
    """Floating stealth overlay for status updates and AI responses."""

    _WINDOW_TITLE: Final[str] = "ScreenAssist"
    _DEFAULT_GEOMETRY: Final[str] = "520x640"

    def __init__(self, settings: Settings | None = None) -> None:
        from config import settings as default_settings

        self._settings = settings if settings is not None else default_settings
        self._settings_window: SettingsWindow | None = None
        self._on_mode_change: ModeChangeCallback | None = None
        self._on_shutdown: ShutdownCallback | None = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._master = tk.Tk()
        self._master.withdraw()

        self._root = ctk.CTkToplevel(self._master)
        self._root.title(self._WINDOW_TITLE)
        self._root.geometry(self._DEFAULT_GEOMETRY)
        self._root.resizable(True, True)
        apply_stealth_window(self._root, borderless=True)

        self._current_mode = DEFAULT_MODE

        self._build_layout()
        self.set_status("Ready — use the tray icon to capture and analyze.")

    @property
    def root(self) -> ctk.CTkToplevel:
        return self._root

    @property
    def current_mode(self) -> str:
        return self._current_mode

    def on_mode_change(self, callback: ModeChangeCallback) -> None:
        """Register a callback invoked when the user switches prompt mode."""
        self._on_mode_change = callback

    def on_shutdown(self, callback: ShutdownCallback) -> None:
        """Register a callback invoked when the user requests application exit."""
        self._on_shutdown = callback

    def set_status(self, message: str) -> None:
        """Update the status label (thread-safe)."""
        self._schedule(lambda: self._status_label.configure(text=message))

    def set_response(self, text: str) -> None:
        """Replace the response text area content (thread-safe)."""
        def _update() -> None:
            self._response_box.configure(state="normal")
            self._response_box.delete("1.0", tk.END)
            self._response_box.insert("1.0", text)
            self._response_box.configure(state="disabled")

        self._schedule(_update)

    def show(self) -> None:
        """Show the overlay on the main thread."""
        self._schedule(self._show_window)

    def hide(self) -> None:
        """Hide the overlay on the main thread."""
        self._schedule(self._root.withdraw)

    def toggle_visibility(self) -> None:
        """Toggle overlay visibility on the main thread."""
        self._schedule(self._toggle_visibility)

    def open_settings(self) -> None:
        """Open the settings dialog on the main thread."""
        self._schedule(self._handle_settings)

    def run(self) -> None:
        """Start the Tkinter main loop on the hidden master window."""
        self._master.mainloop()

    def shutdown(self) -> None:
        """Destroy overlay windows and stop the Tkinter loop."""
        def _destroy() -> None:
            if self._settings_window is not None and self._settings_window.is_open():
                self._settings_window.close()
            if self._root.winfo_exists():
                self._root.destroy()
            if self._master.winfo_exists():
                self._master.quit()
                self._master.destroy()

        if threading_main_safe():
            _destroy()
        else:
            self._schedule(_destroy)

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self._root, corner_radius=12)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        header = ctk.CTkLabel(
            container,
            text="ScreenAssist",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.pack(anchor="w", pady=(0, 4))

        hint = ctk.CTkLabel(
            container,
            text="Tray — analyze  •  Esc — hide window",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        hint.pack(anchor="w", pady=(0, 12))

        mode_frame = ctk.CTkFrame(container, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(mode_frame, text="Mode:", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(0, 8)
        )

        self._mode_var = ctk.StringVar(value=self._current_mode)
        self._mode_menu = ctk.CTkOptionMenu(
            mode_frame,
            variable=self._mode_var,
            values=list(AVAILABLE_MODES.keys()),
            command=self._handle_mode_selected,
            width=160,
        )
        self._mode_menu.pack(side="left")

        self._status_label = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#7ec8ff",
            wraplength=460,
            justify="left",
        )
        self._status_label.pack(fill="x", pady=(0, 8))

        footer = ctk.CTkFrame(container, fg_color="transparent")
        footer.pack(side="bottom", fill="x", pady=(12, 0))

        self._exit_button = ctk.CTkButton(
            footer,
            text="Exit",
            command=self._handle_exit,
            width=100,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color="#8b3a3a",
            text_color="#e07070",
            hover_color="#3d2020",
        )
        self._exit_button.pack(side="right")

        self._settings_button = ctk.CTkButton(
            footer,
            text="⚙ Settings",
            command=self._handle_settings,
            width=110,
            height=32,
            fg_color="transparent",
            border_width=1,
            border_color="#4a5568",
            text_color="gray80",
            hover_color="#2a2f3a",
        )
        self._settings_button.pack(side="left")

        self._response_box = ctk.CTkTextbox(
            container,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word",
            activate_scrollbars=True,
        )
        self._response_box.pack(fill="both", expand=True)
        self._response_box.insert("1.0", "Analysis results will appear here.")
        self._response_box.configure(state="disabled")

        self._root.bind("<Escape>", lambda _event: self._root.withdraw())

    def _show_window(self) -> None:
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def _toggle_visibility(self) -> None:
        if self._root.state() == "withdrawn":
            self._show_window()
        else:
            self._root.withdraw()

    def _handle_mode_selected(self, value: str) -> None:
        self._current_mode = value
        if self._on_mode_change is not None:
            self._on_mode_change(self._current_mode)

    def _handle_settings(self) -> None:
        """Open the settings window (single instance)."""
        if self._settings_window is not None and self._settings_window.is_open():
            self._settings_window.focus()
            return

        self._settings_window = SettingsWindow(self._root, self._settings)

    def _handle_exit(self) -> None:
        """Close the overlay and terminate the application."""
        if self._on_shutdown is not None:
            self._on_shutdown()
        else:
            self.shutdown()

    def _schedule(self, callback: Callable[[], None]) -> None:
        """Schedule a zero-argument callback on the Tkinter main thread."""
        if self._master.winfo_exists():
            self._master.after(0, callback)


def threading_main_safe() -> bool:
    """Return True when called from the Tkinter main thread."""
    import threading

    return threading.current_thread() is threading.main_thread()
