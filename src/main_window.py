"""Small window shown when ProSnip-Bob starts."""

import sys

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from editor import APP_NAME, APP_VERSION
from hotkey import TAKEN_MESSAGE
from styles import DEFAULT_STYLE


def shortcut_status_text(reason: str | None) -> str:
    """User-facing hotkey line for the main window."""
    if not reason:
        return "Shortcut: Ctrl+Shift+S"
    if reason == TAKEN_MESSAGE:
        return "Shortcut unavailable (in use by another app), use New Capture."
    return "Shortcut unavailable on this system, use New Capture."


def _bring_to_front(window: QWidget) -> None:
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow(int(window.winId()))


class MainWindow(QMainWindow):
    new_capture_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    hidden_to_tray = pyqtSignal()

    def __init__(self, icon: QIcon | None = None):
        super().__init__()
        self._quitting = False
        self.setWindowTitle(APP_NAME)
        if icon is not None:
            self.setWindowIcon(icon)
        self.setMinimumSize(380, 240)
        self._build()

    def _build(self):
        accent = DEFAULT_STYLE.pen_color.name()
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background-color: #2b2b2b;
                color: #f2f2f2;
                font-size: 13px;
            }}
            QLabel#appName {{
                font-size: 22px;
                font-weight: 600;
                color: #ffffff;
            }}
            QLabel#version, QLabel#shortcut {{
                color: #c8c8c8;
            }}
            QPushButton {{
                background: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #eeeeee;
                border-radius: 4px;
                padding: 8px 14px;
                min-height: 22px;
            }}
            QPushButton:hover {{
                background: #3d3d3d;
            }}
            QPushButton#newCapture {{
                background: {accent};
                border-color: {accent};
                color: #ffffff;
                font-weight: 600;
            }}
            QPushButton#newCapture:hover {{
                background: #c62f3b;
            }}
            """
        )

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)

        name = QLabel(APP_NAME)
        name.setObjectName("appName")
        version = QLabel(f"Version {APP_VERSION}")
        version.setObjectName("version")

        self.new_capture_button = QPushButton("New Capture")
        self.new_capture_button.setObjectName("newCapture")
        self.new_capture_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_capture_button.clicked.connect(lambda: self.new_capture_requested.emit())

        self.shortcut_label = QLabel(shortcut_status_text(None))
        self.shortcut_label.setObjectName("shortcut")
        self.shortcut_label.setWordWrap(True)

        self.quit_button = QPushButton("Quit")
        self.quit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quit_button.clicked.connect(lambda: self.quit_requested.emit())

        layout.addWidget(name)
        layout.addWidget(version)
        layout.addSpacing(8)
        layout.addWidget(self.new_capture_button)
        layout.addWidget(self.shortcut_label)
        layout.addStretch(1)
        layout.addWidget(self.quit_button)

    def set_shortcut_status(self, reason: str | None) -> None:
        self.shortcut_label.setText(shortcut_status_text(reason))

    def allow_close(self) -> None:
        self._quitting = True

    def present(self) -> None:
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()
        _bring_to_front(self)

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide()
        self.hidden_to_tray.emit()
