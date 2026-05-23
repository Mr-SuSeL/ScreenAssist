"""Windows stealth window helpers for taskbar and Alt+Tab exclusion."""

from __future__ import annotations

import sys
import tkinter as tk


def apply_stealth_window(window: tk.Misc, *, borderless: bool = False, alpha: float = 0.94) -> None:
    """Apply low-profile window styles hiding the overlay from taskbar and Alt+Tab."""
    window.attributes("-topmost", True)

    try:
        window.attributes("-alpha", alpha)
    except tk.TclError:
        pass

    if sys.platform == "win32":
        window.attributes("-toolwindow", True)
        if borderless:
            window.overrideredirect(True)
        window.update_idletasks()
        _hide_from_alt_tab(window)
    elif borderless:
        window.overrideredirect(True)


def _hide_from_alt_tab(window: tk.Misc) -> None:
    """Strip WS_EX_APPWINDOW and set WS_EX_TOOLWINDOW on Windows."""
    import ctypes

    hwnd = _resolve_hwnd(window)
    if hwnd is None:
        return

    gwl_exstyle = -20
    ws_ex_toolwindow = 0x00000080
    ws_ex_appwindow = 0x00040000

    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, gwl_exstyle)
    style |= ws_ex_toolwindow
    style &= ~ws_ex_appwindow
    user32.SetWindowLongW(hwnd, gwl_exstyle, style)


def _resolve_hwnd(window: tk.Misc) -> int | None:
    import ctypes

    try:
        window_id = window.winfo_id()
    except tk.TclError:
        return None

    hwnd = ctypes.windll.user32.GetParent(window_id)
    return hwnd or window_id
