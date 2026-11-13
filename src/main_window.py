"""Small window shown when ProSnip-Bob starts."""

import sys

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from colour import ColourHistory

from editor import APP_NAME, APP_VERSION
from hotkey import TAKEN_MESSAGE
from styles import DEFAULT_STYLE, with_tooltip_style


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
        self.setMinimumSize(380, 300)
        self._build()

    def _build(self):
        accent = DEFAULT_STYLE.pen_color.name()
        self.setStyleSheet(with_tooltip_style(
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
        ))

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

        self.settings_button = _large_button("Settings", _gear_icon(), "Settings")
        self.settings_button.clicked.connect(self._open_settings)

        self.shortcut_label = QLabel(shortcut_status_text(None))
        self.shortcut_label.setObjectName("shortcut")
        self.shortcut_label.setWordWrap(True)

        self.picker_shortcut_label = QLabel("Colour picker: Ctrl+Shift+P")
        self.picker_shortcut_label.setObjectName("shortcut")
        self.picker_shortcut_label.setWordWrap(True)

        self.quit_button = _large_button("Quit", _quit_icon(), "Quit")
        self.quit_button.clicked.connect(lambda: self.quit_requested.emit())
        self.new_capture_button.setIcon(_capture_icon())
        self.new_capture_button.setIconSize(QSize(40, 40))
        self.new_capture_button.setMinimumHeight(56)

        layout.addWidget(name)
        layout.addWidget(version)
        layout.addSpacing(8)
        layout.addWidget(self.new_capture_button)
        layout.addWidget(self.settings_button)
        layout.addWidget(self.shortcut_label)
        layout.addWidget(self.picker_shortcut_label)
        layout.addStretch(1)
        layout.addWidget(self.quit_button)

    def _open_settings(self):
        SettingsDialog(self._history if hasattr(self, "_history") else ColourHistory(), self).exec()

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


def _large_button(text: str, icon: QIcon, tooltip: str) -> QPushButton:
    button = QPushButton(text)
    button.setIcon(icon)
    button.setIconSize(QSize(40, 40))
    button.setMinimumHeight(56)
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _capture_icon() -> QIcon:
    return _drawn_icon(lambda painter, size: painter.drawRect(int(size * 0.18), int(size * 0.18), int(size * 0.64), int(size * 0.64)))


def _gear_icon() -> QIcon:
    return _drawn_icon(lambda painter, size: painter.drawEllipse(int(size * 0.22), int(size * 0.22), int(size * 0.56), int(size * 0.56)))


def _quit_icon() -> QIcon:
    return _drawn_icon(lambda painter, size: (
        painter.drawLine(int(size * 0.25), int(size * 0.25), int(size * 0.75), int(size * 0.75)),
        painter.drawLine(int(size * 0.75), int(size * 0.25), int(size * 0.25), int(size * 0.75)),
    ))


def _drawn_icon(draw) -> QIcon:
    pix = QPixmap(80, 80)
    pix.setDevicePixelRatio(2)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#f2f2f2"), 2))
    draw(painter, 40)
    painter.end()
    return QIcon(pix)


class SettingsDialog(QDialog):
    def __init__(self, history: ColourHistory, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self._history = history
        layout = QVBoxLayout(self)
        self._auto = QCheckBox("Copy the snip to the clipboard after a capture")
        self._auto.setChecked(history.auto_copy)
        layout.addWidget(self._auto)
        note = QLabel("Colour picker stays on Ctrl+Shift+P, in the editor toolbar and the tray menu.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        self._history.set_auto_copy(self._auto.isChecked())
        self.accept()
