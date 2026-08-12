import sys
import threading

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu
)
from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

import keyboard

from capture import CaptureOverlay
from editor import EditorWindow


def _make_tray_icon() -> QIcon:
    """Create a simple coloured square as the tray icon."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setBrush(QColor("#0078d4"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 28, 28, 6, 6)
    p.setPen(QColor("#ffffff"))
    from PyQt6.QtGui import QFont
    font = QFont("Arial", 14, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "S")
    p.end()
    return QIcon(pix)


class AppSignals(QObject):
    capture_done = pyqtSignal(object)  # PIL Image or None
    trigger_capture = pyqtSignal()


class ProSnipApp:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName("ProSnip")

        self._signals = AppSignals()
        self._signals.capture_done.connect(self._on_capture_done)
        self._signals.trigger_capture.connect(self._show_capture)

        self._tray = None
        self._overlay = None
        self._editor = None

        self._setup_tray()
        self._register_hotkey()

    def _setup_tray(self):
        icon = _make_tray_icon()
        self._tray = QSystemTrayIcon(icon, self._app)
        self._tray.setToolTip("ProSnip — Ctrl+Shift+S to capture")

        menu = QMenu()
        action_open = menu.addAction("Open / Capture")
        action_open.triggered.connect(self._show_capture)
        menu.addSeparator()
        action_quit = menu.addAction("Quit ProSnip")
        action_quit.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_capture()

    def _register_hotkey(self):
        def _hotkey_cb():
            # keyboard callback runs in a non-Qt thread — use signal
            self._signals.trigger_capture.emit()

        keyboard.add_hotkey("ctrl+shift+s", _hotkey_cb, suppress=True)

    def _show_capture(self):
        self._tray.hide()
        # Small delay to let tray hide/screen update
        QTimer.singleShot(150, self._do_capture)

    def _do_capture(self):
        self._overlay = CaptureOverlay(callback=self._on_capture_result)
        self._overlay.showFullScreen()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def _on_capture_result(self, pil_image):
        """Called from CaptureOverlay (main thread)."""
        self._signals.capture_done.emit(pil_image)

    def _on_capture_done(self, pil_image):
        if pil_image is None:
            self._tray.show()
            return
        self._editor = EditorWindow(pil_image)
        self._editor.show()
        self._editor.raise_()
        self._editor.activateWindow()
        # Show tray again (editor is open)
        self._tray.show()

    def _quit(self):
        keyboard.unhook_all()
        self._app.quit()

    def run(self):
        sys.exit(self._app.exec())


def main():
    app = ProSnipApp()
    app.run()


if __name__ == "__main__":
    main()
