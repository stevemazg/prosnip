"""Ctrl+Shift+S via the Win32 RegisterHotKey API.

This is an ordinary application hotkey, not a low-level keyboard hook.
Other platforms can import the module; registration then explains that the
hotkey is unavailable and tray capture still works.
"""

import ctypes
import logging
import sys
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, Qt
from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

# Win32 constants. MOD_NOREPEAT needs Windows 7 or later.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
HOTKEY_MODIFIERS = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
VK_S = 0x53
WM_HOTKEY = 0x0312
HOTKEY_ID = 1

WINDOWS_MSG_EVENT = "windows_generic_MSG"

TAKEN_MESSAGE = (
    "Could not register Ctrl+Shift+S. It may already be in use. "
    "Use the tray icon to capture."
)
UNAVAILABLE_MESSAGE = (
    "Ctrl+Shift+S is only available on Windows. Use the tray icon to capture."
)

# The layout matches the Windows MSG the process is running under.
# On Windows this is the real Win32 structure.
MSG = wintypes.MSG


def _event_type_text(event_type) -> str:
    if isinstance(event_type, (bytes, bytearray)):
        return event_type.decode("ascii", "replace")
    try:
        return bytes(event_type).decode("ascii", "replace")
    except Exception:
        return str(event_type)


def _message_address(message) -> int | None:
    if message is None:
        return None
    if isinstance(message, int):
        return message
    value = getattr(message, "value", None)
    if isinstance(value, int):
        return value
    try:
        return int(message)
    except (TypeError, ValueError):
        return None


def is_our_hotkey_message(event_type, message, hotkey_id: int = HOTKEY_ID) -> bool:
    """True when a native event is WM_HOTKEY for our id."""
    if _event_type_text(event_type) != WINDOWS_MSG_EVENT:
        return False
    address = _message_address(message)
    if not address:
        return False
    try:
        msg = MSG.from_address(address)
    except (ValueError, OverflowError):
        return False
    return msg.message == WM_HOTKEY and int(msg.wParam) == int(hotkey_id)


class HotkeyEventFilter(QAbstractNativeEventFilter):
    """Receives WM_HOTKEY on the Qt GUI thread and runs the callback there."""

    def __init__(self, hotkey_id: int, on_triggered):
        super().__init__()
        self._hotkey_id = hotkey_id
        self._on_triggered = on_triggered

    def nativeEventFilter(self, eventType, message):
        try:
            if is_our_hotkey_message(eventType, message, self._hotkey_id):
                self._on_triggered()
                return True, 0
        except Exception:
            log.exception("Failed to handle the global hotkey")
        return False, 0


class _HotkeyAnchor(QWidget):
    """Hidden native window that owns the hotkey.

    RegisterHotKey delivers WM_HOTKEY to this HWND, and Qt already runs that
    window's messages on the GUI thread.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        # Force a real HWND without showing the window.
        self.winId()


class GlobalHotkey:
    def __init__(self, on_triggered):
        self._on_triggered = on_triggered
        self._registered = False
        self._anchor: _HotkeyAnchor | None = None
        self._filter: HotkeyEventFilter | None = None
        self._hwnd: int | None = None
        self._app = None

    def register(self, app) -> str | None:
        """Register Ctrl+Shift+S.

        Returns None on success, or a short message suitable for the tray
        when the hotkey could not be registered.
        """
        if self._registered:
            return None
        if sys.platform != "win32":
            return UNAVAILABLE_MESSAGE
        try:
            return self._register_windows(app)
        except Exception:
            log.exception("Failed to register the global hotkey")
            self.unregister()
            return TAKEN_MESSAGE

    def _register_windows(self, app) -> str | None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL

        self._app = app
        self._anchor = _HotkeyAnchor()
        self._hwnd = int(self._anchor.winId())
        self._filter = HotkeyEventFilter(HOTKEY_ID, self._on_triggered)
        app.installNativeEventFilter(self._filter)

        registered = user32.RegisterHotKey(
            self._hwnd,
            HOTKEY_ID,
            HOTKEY_MODIFIERS,
            VK_S,
        )
        if not registered:
            error = ctypes.get_last_error()
            log.error("RegisterHotKey failed (Win32 error %s)", error)
            self.unregister()
            return TAKEN_MESSAGE

        self._registered = True
        log.info("Registered Ctrl+Shift+S (hotkey id %s)", HOTKEY_ID)
        return None

    def unregister(self) -> None:
        if sys.platform == "win32" and self._hwnd:
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
                user32.UnregisterHotKey.restype = wintypes.BOOL
                user32.UnregisterHotKey(self._hwnd, HOTKEY_ID)
            except Exception:
                log.exception("Failed to unregister the global hotkey")
        if self._app is not None and self._filter is not None:
            try:
                self._app.removeNativeEventFilter(self._filter)
            except Exception:
                log.exception("Failed to remove the hotkey event filter")
        self._filter = None
        self._registered = False
        anchor = self._anchor
        self._anchor = None
        self._hwnd = None
        self._app = None
        if anchor is not None:
            anchor.deleteLater()
