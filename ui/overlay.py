"""CustomTkinter always-on-top overlay window."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from typing import Final

import customtkinter as ctk

from core.prompt_manager import PromptMode, list_modes

StatusCallback = Callable[[str], None]
ModeChangeCallback = Callable[[PromptMode], None]


class OverlayWindow:
    """Floating overlay for status updates and AI responses."""

    _WINDOW_TITLE: Final[str] = "AI Screen Suffler"
    _DEFAULT_GEOMETRY: Final[str] = "520x640"

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title(self._WINDOW_TITLE)
        self._root.geometry(self._DEFAULT_GEOMETRY)
        self._root.attributes("-topmost", True)
        self._root.resizable(True, True)

        self._current_mode = PromptMode.CODE
        self._on_mode_change: ModeChangeCallback | None = None

        self._build_layout()
        self.set_status("Ready — press F8 to capture and analyze.")

    @property
    def root(self) -> ctk.CTk:
        return self._root

    @property
    def current_mode(self) -> PromptMode:
        return self._current_mode

    def on_mode_change(self, callback: ModeChangeCallback) -> None:
        """Register a callback invoked when the user switches prompt mode."""
        self._on_mode_change = callback

    def set_status(self, message: str) -> None:
        """Update the status label (thread-safe)."""
        self._schedule(self._status_label.configure, text=message)

    def set_response(self, text: str) -> None:
        """Replace the response text area content (thread-safe)."""
        def _update() -> None:
            self._response_box.configure(state="normal")
            self._response_box.delete("1.0", tk.END)
            self._response_box.insert("1.0", text)
            self._response_box.configure(state="disabled")

        self._schedule(_update)

    def run(self) -> None:
        """Start the Tkinter main loop."""
        self._root.mainloop()

    def _build_layout(self) -> None:
        container = ctk.CTkFrame(self._root, corner_radius=12)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        header = ctk.CTkLabel(
            container,
            text="AI Screen Suffler",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.pack(anchor="w", pady=(0, 4))

        hint = ctk.CTkLabel(
            container,
            text="F8 — capture screen  •  Esc — hide window",
            font=ctk.CTkFont(size=12),
            text_color="gray70",
        )
        hint.pack(anchor="w", pady=(0, 12))

        mode_frame = ctk.CTkFrame(container, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(mode_frame, text="Mode:", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(0, 8)
        )

        self._mode_var = ctk.StringVar(value=self._current_mode.value)
        self._mode_menu = ctk.CTkOptionMenu(
            mode_frame,
            variable=self._mode_var,
            values=[mode.value for mode in list_modes()],
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

    def _handle_mode_selected(self, value: str) -> None:
        self._current_mode = PromptMode(value)
        if self._on_mode_change is not None:
            self._on_mode_change(self._current_mode)

    def _schedule(self, callback: Callable[..., None], *args: object) -> None:
        """Schedule UI updates on the main thread."""
        self._root.after(0, lambda: callback(*args))
