"""Screen capture utilities using mss."""

from __future__ import annotations

import base64
import io
import sys
from dataclasses import dataclass

import mss
from loguru import logger
from PIL import Image


@dataclass(frozen=True, slots=True)
class MonitorInfo:
    """Detected display metadata for UI selection."""

    index: int
    width: int
    height: int
    left: int
    top: int
    name: str | None = None

    def dropdown_label(self) -> str:
        """Format label as 'Monitor [Index]: [Width]x[Height]' with optional name."""
        label = f"Monitor {self.index}: {self.width}x{self.height}"
        if self.name:
            label += f" — {self.name}"
        return label


@dataclass(frozen=True, slots=True)
class ScreenCapture:
    """JPEG bytes and base64 representation of a captured screen."""

    jpeg_bytes: bytes
    base64_data: str
    width: int
    height: int
    monitor_index: int


class ScreenCaptureError(Exception):
    """Raised when screen capture fails."""


def list_monitors() -> list[MonitorInfo]:
    """Return all mss monitor entries with optional platform display names."""
    with mss.mss() as sct:
        names_by_geometry = _resolve_monitor_names()
        monitors: list[MonitorInfo] = []

        for index, monitor in enumerate(sct.monitors):
            geometry = (
                monitor["left"],
                monitor["top"],
                monitor["width"],
                monitor["height"],
            )
            name = names_by_geometry.get(geometry)
            if index == 0 and name is None:
                name = "All monitors"

            monitors.append(
                MonitorInfo(
                    index=index,
                    width=monitor["width"],
                    height=monitor["height"],
                    left=monitor["left"],
                    top=monitor["top"],
                    name=name,
                )
            )

        return monitors


def log_available_monitors() -> None:
    """Log all detected monitors with their mss indices for configuration."""
    monitors = list_monitors()
    logger.info("Detected {} monitor entries (index 0 = virtual full desktop):", len(monitors))
    for monitor in monitors:
        name_suffix = f" — {monitor.name}" if monitor.name else ""
        logger.info(
            "  [{}] {}x{} at ({}, {}){}",
            monitor.index,
            monitor.width,
            monitor.height,
            monitor.left,
            monitor.top,
            name_suffix,
        )


def capture_monitor(monitor_index: int, jpeg_quality: int = 85) -> ScreenCapture:
    """Capture the given monitor index and return encoded image data."""
    try:
        with mss.mss() as sct:
            if monitor_index < 0 or monitor_index >= len(sct.monitors):
                raise ScreenCaptureError(
                    f"Invalid monitor index {monitor_index}. "
                    f"Available indices: 0-{len(sct.monitors) - 1}"
                )

            monitor = sct.monitors[monitor_index]
            screenshot = sct.grab(monitor)

            image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
            jpeg_bytes = buffer.getvalue()

            base64_data = base64.b64encode(jpeg_bytes).decode("ascii")
            logger.debug(
                "Captured monitor [{}]: {}x{} ({} KB)",
                monitor_index,
                screenshot.width,
                screenshot.height,
                len(jpeg_bytes) // 1024,
            )

            return ScreenCapture(
                jpeg_bytes=jpeg_bytes,
                base64_data=base64_data,
                width=screenshot.width,
                height=screenshot.height,
                monitor_index=monitor_index,
            )
    except ScreenCaptureError:
        raise
    except Exception as exc:
        logger.exception("Screen capture failed for monitor index {}", monitor_index)
        raise ScreenCaptureError("Unable to capture screen") from exc


def _resolve_monitor_names() -> dict[tuple[int, int, int, int], str]:
    """Best-effort display names keyed by (left, top, width, height)."""
    if sys.platform == "win32":
        return _windows_monitor_names()
    return {}


def _windows_monitor_names() -> dict[tuple[int, int, int, int], str]:
    """Enumerate Windows display device names and match them to mss geometry."""
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    user32 = ctypes.windll.user32
    names: list[tuple[tuple[int, int, int, int], str]] = []

    def _callback(_hmonitor, _hdc, _rect_ptr, _lparam) -> bool:
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(_hmonitor, ctypes.byref(info)):
            rect = info.rcMonitor
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            device = info.szDevice.strip()
            friendly = _friendly_windows_device_name(device)
            names.append(((rect.left, rect.top, width, height), friendly))
        return True

    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_callback), 0)
    return dict(names)


def _friendly_windows_device_name(device: str) -> str:
    """Shorten Windows device paths like '\\\\.\\DISPLAY1' when possible."""
    if device.startswith("\\\\.\\"):
        return device.rsplit("\\", maxsplit=1)[-1]
    return device
