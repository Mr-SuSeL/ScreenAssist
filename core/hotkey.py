"""Native Windows global hotkey listener via RegisterHotKey (no low-level hooks)."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from loguru import logger

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_NONE = 0
VK_F8 = 0x77
HOTKEY_ID = 1

HWND_MESSAGE = -3


class NativeHotkeyListener:
    """Register a global hotkey using Win32 RegisterHotKey and a message loop."""

    def __init__(
        self,
        callback: Callable[[], None],
        *,
        virtual_key: int = VK_F8,
        hotkey_id: int = HOTKEY_ID,
    ) -> None:
        self._callback = callback
        self._virtual_key = virtual_key
        self._hotkey_id = hotkey_id
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._hwnd: int | None = None
        self._wnd_proc_ref: object | None = None

    def start(self) -> None:
        """Start the hotkey listener on a background daemon thread."""
        if sys.platform != "win32":
            logger.warning("Native hotkeys are only supported on Windows — skipping")
            return

        if self._thread is not None and self._thread.is_alive():
            return

        self._thread = threading.Thread(
            target=self._run_message_loop,
            name="native-hotkey",
            daemon=True,
        )
        self._thread.start()
        logger.info("Native F8 hotkey listener starting (RegisterHotKey)")

    def stop(self) -> None:
        """Stop the message loop and unregister the global hotkey."""
        if sys.platform != "win32":
            return

        if self._thread_id is not None:
            ctypes = __import__("ctypes")
            user32 = ctypes.windll.user32
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)

        if self._thread is not None:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                logger.warning("Hotkey listener thread did not exit cleanly")

        self._thread = None
        self._thread_id = None
        self._hwnd = None

    def _run_message_loop(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        self._thread_id = kernel32.GetCurrentThreadId()

        WNDPROC = ctypes.WINFUNCTYPE(
            wintypes.LRESULT,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def _window_proc(hwnd: int, msg: int, wparam: int, lparam: int) -> int:
            if msg == WM_HOTKEY and wparam == self._hotkey_id:
                logger.debug("WM_HOTKEY received — triggering capture pipeline")
                try:
                    self._callback()
                except Exception:
                    logger.exception("Hotkey callback failed")
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wnd_proc_ref = WNDPROC(_window_proc)

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HCURSOR),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
            ]

        hinstance = kernel32.GetModuleHandleW(None)
        class_name = "ScreenAssistHotkeyWindow"

        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wnd_proc_ref
        wc.hInstance = hinstance
        wc.lpszClassName = class_name

        if not user32.RegisterClassW(ctypes.byref(wc)):
            error = kernel32.GetLastError()
            if error != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                logger.error("RegisterClassW failed (error={})", error)
                return

        hwnd = user32.CreateWindowExW(
            0,
            class_name,
            "ScreenAssistHotkeySink",
            0,
            0,
            0,
            0,
            0,
            HWND_MESSAGE,
            None,
            hinstance,
            None,
        )
        if not hwnd:
            logger.error("CreateWindowExW failed (error={})", kernel32.GetLastError())
            return

        self._hwnd = hwnd

        if not user32.RegisterHotKey(hwnd, self._hotkey_id, MOD_NONE, self._virtual_key):
            logger.error(
                "RegisterHotKey failed (error={}) — F8 may be in use by another application",
                kernel32.GetLastError(),
            )
            user32.DestroyWindow(hwnd)
            self._hwnd = None
            return

        logger.info("Registered global hotkey F8 (VK=0x{:02X})", self._virtual_key)

        msg = MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            if user32.UnregisterHotKey(hwnd, self._hotkey_id):
                logger.info("Unregistered global hotkey F8")
            else:
                logger.warning(
                    "UnregisterHotKey failed (error={})",
                    kernel32.GetLastError(),
                )
            user32.DestroyWindow(hwnd)
            self._hwnd = None
