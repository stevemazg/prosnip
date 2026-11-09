"""Visible top-level windows, for recording one application window.

A browser tab cannot be seen from outside the browser, so callers record
the browser window itself. On Windows the rectangle is in that monitor's
physical pixels, which matches QScreen.grabWindow.
"""

import sys

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QGuiApplication


def list_toplevel_windows() -> list[tuple[int, str]]:
    """Return ``(hwnd, title)`` for visible top-level windows. Empty off Windows."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    dwmapi = None
    try:
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    except OSError:
        dwmapi = None

    found: list[tuple[int, str]] = []

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        if _is_cloaked(dwmapi, hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value.strip()
        if title and title != "ProSnip-Bob recording":
            found.append((int(hwnd), title))
        return True

    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.EnumWindows(enum_proc(_callback), 0)
    return found


def window_capture_rect(hwnd: int):
    """Return ``(QScreen, physical QRect)`` for a window, or None off Windows."""
    if sys.platform != "win32" or not hwnd:
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    rect = wintypes.RECT()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    screen, origin = _screen_for_window(user32, hwnd)
    if screen is None:
        return None
    local = QRect(
        int(rect.left - origin[0]),
        int(rect.top - origin[1]),
        int(rect.right - rect.left),
        int(rect.bottom - rect.top),
    )
    if local.width() < 2 or local.height() < 2:
        return None
    return screen, local


def _is_cloaked(dwmapi, hwnd) -> bool:
    if dwmapi is None:
        return False
    import ctypes
    from ctypes import wintypes

    cloaked = wintypes.DWORD()
    DWMWA_CLOAKED = 14
    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    result = dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_CLOAKED,
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return result == 0 and cloaked.value != 0


def _screen_for_window(user32, hwnd):
    import ctypes
    from ctypes import wintypes

    MONITOR_DEFAULTTONEAREST = 2
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        screen = QGuiApplication.primaryScreen()
        return screen, (0, 0)
    name = info.szDevice
    origin = (int(info.rcMonitor.left), int(info.rcMonitor.top))
    for screen in QGuiApplication.screens():
        if screen.name() == name:
            return screen, origin
    return QGuiApplication.primaryScreen(), origin
