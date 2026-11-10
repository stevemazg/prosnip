import logging
import os
import sys
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

import demo_screenshots
from capture import CaptureOverlay
from editor import APP_NAME, APP_VERSION, EditorWindow
from hotkey import GlobalHotkey
from instance import claim_primary, release_server
from main_window import MainWindow
from recorder import GrabSource, RecordDialog, ScreenRecorder, WindowGrabSource, video_output_path

log = logging.getLogger("prosnip")

_logging_ready = False
_reporting_exception = False


def candidate_log_directories() -> list[Path]:
    """Where ``ProSnip-Bob.log`` may be written, most preferred first."""
    directories: list[Path] = []
    if getattr(sys, "frozen", False):
        directories.append(Path(sys.executable).resolve().parent)
    else:
        directories.append(Path.cwd())
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        directories.append(Path(local_app_data) / APP_NAME)
    else:
        directories.append(Path.home() / ".local" / "share" / APP_NAME)
    return directories


def resolve_log_path(directories: list[Path] | None = None) -> Path | None:
    """Return a writable ``<AppName>.log`` path, or None if every candidate fails.

    The first choice is the folder that contains the executable. For a
    PyInstaller onedir build that is the folder with ``ProSnip-Bob.exe``,
    beside ``_internal``, not inside it. When running from source the working
    directory is used. If that folder cannot be written, the fallback is
    ``%LOCALAPPDATA%\\<AppName>``.
    """
    filename = f"{APP_NAME}.log"
    for directory in candidate_log_directories() if directories is None else directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / filename
            with open(path, "a", encoding="utf-8"):
                pass
            return path
        except OSError:
            continue
    return None


def setup_logging(directories: list[Path] | None = None) -> None:
    """Log to the app log file, and to the console only when stderr exists.

    A windowed PyInstaller build sets ``sys.stderr`` to None. Opening a console
    stream in that case crashes before the tray is up.
    """
    global _logging_ready
    if _logging_ready:
        return

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    path = resolve_log_path(directories)
    if path is not None:
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
        log.info("Logging to %s", path)
    else:
        log.warning("No writable log file could be opened")

    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        root.addHandler(console)
    _logging_ready = True


def _excepthook(exc_type, exc, tb):
    """Log an unhandled exception and show it.

    PyQt6 calls ``qFatal`` after an exception escapes a slot or a Python
    reimplementation of a C++ method. In a windowed build that abort used to
    look like the process had vanished. The message box is shown first.
    """
    global _reporting_exception
    if exc_type is None:
        return
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc, tb)
        return

    logging.getLogger("prosnip").error(
        "Unhandled exception",
        exc_info=(exc_type, exc, tb),
    )
    if _reporting_exception:
        return
    app = QApplication.instance()
    if app is None or app.closingDown():
        return
    if QThread.currentThread() is not app.thread():
        return

    _reporting_exception = True
    try:
        QMessageBox.critical(
            None,
            APP_NAME,
            "An unexpected error occurred.\n\n"
            f"{exc_type.__name__}: {exc}\n\n"
            "Details have been written to the log.",
        )
    except Exception:
        logging.getLogger("prosnip").exception("Could not show the error message")
    finally:
        _reporting_exception = False


class ProSnipApplication(QApplication):
    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception:
            sys.excepthook(*sys.exc_info())
            return False


def _make_tray_icon() -> QIcon:
    """Create a simple coloured square as the tray icon."""
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setBrush(QColor("#0078d4"))
    painter.setPen(QPen(Qt.PenStyle.NoPen))
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(QColor("#ffffff"))
    font = QFont("Arial", 14, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "B")
    painter.end()
    return QIcon(pix)


class AppSignals(QObject):
    capture_done = pyqtSignal(object)  # PIL Image or None
    trigger_capture = pyqtSignal()


class ProSnipApp:
    def __init__(self):
        app = QApplication.instance()
        if app is None:
            app = ProSnipApplication(sys.argv)
        self._app = app
        self._app.setQuitOnLastWindowClosed(False)
        self._app.setApplicationName(APP_NAME)
        self._app.setApplicationVersion(APP_VERSION)

        self.forwarded = False
        self._signals = AppSignals()
        self._signals.capture_done.connect(self._on_capture_done)
        self._signals.trigger_capture.connect(self._show_capture)

        self._tray = None
        self._hotkey: GlobalHotkey | None = None
        self._main_window: MainWindow | None = None
        self._server = None
        self._main_has_been_shown = False
        self._restore_main_after_capture = False
        self._announced_tray = False
        self._session: CaptureOverlay | None = None
        self._recording: ScreenRecorder | None = None
        self._record_fps = 15
        self._stop_recording_action = None
        self._capture_pending = False
        self._editors: list[EditorWindow] = []

        is_primary, server = claim_primary(self._show_main_window)
        if not is_primary:
            self.forwarded = True
            return
        self._server = server

        self._setup_tray()
        self._setup_main_window()
        self._show_main_window()
        self._register_hotkey()

    def _capture_in_progress(self) -> bool:
        if self._capture_pending:
            return True
        return self._session is not None and self._session.is_active

    def _setup_tray(self):
        icon = _make_tray_icon()
        self._tray = QSystemTrayIcon(icon, self._app)
        self._tray.setToolTip(APP_NAME)

        menu = QMenu()
        action_show = menu.addAction(f"Show {APP_NAME}")
        action_show.triggered.connect(self._show_main_window)
        record_menu = menu.addMenu("Record")
        record_menu.addAction("Monitor…", lambda: self._open_record_dialog("monitor"))
        record_menu.addAction("Region…", lambda: self._open_record_dialog("region"))
        record_menu.addAction("Window…", lambda: self._open_record_dialog("window"))
        self._stop_recording_action = menu.addAction("Stop recording")
        self._stop_recording_action.triggered.connect(self._stop_recording)
        self._stop_recording_action.setVisible(False)
        menu.addSeparator()
        action_quit = menu.addAction(f"Quit {APP_NAME}")
        action_quit.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _setup_main_window(self):
        icon = self._tray.icon() if self._tray is not None else None
        self._main_window = MainWindow(icon)
        self._main_window.new_capture_requested.connect(self._show_capture)
        self._main_window.record_requested.connect(lambda: self._open_record_dialog("monitor"))
        self._main_window.quit_requested.connect(self._quit)
        self._main_window.hidden_to_tray.connect(self._on_hidden_to_tray)

    def _show_main_window(self, *args):
        if self._main_window is None:
            return
        if self._capture_in_progress():
            self._restore_main_after_capture = True
            log.info("Show requested during capture; the window returns when capture ends")
            return
        was_visible = self._main_window.isVisible()
        self._main_window.present()
        if self._main_has_been_shown and not was_visible:
            log.info("Main window restored")
        else:
            log.info("Main window shown")
        self._main_has_been_shown = True

    def _on_hidden_to_tray(self):
        log.info("Main window hidden to the tray")
        if self._announced_tray:
            return
        self._announced_tray = True
        self._notify(
            f"{APP_NAME} is still running. Click the tray icon to show it again.",
            warning=False,
        )

    def _on_tray_activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_main_window()

    def _register_hotkey(self):
        # WM_HOTKEY is delivered on the GUI thread, so the signal is emitted
        # directly. Tray capture does not depend on this registration.
        self._hotkey = GlobalHotkey(self._signals.trigger_capture.emit)
        reason = self._hotkey.register(self._app)
        if self._main_window is not None:
            self._main_window.set_shortcut_status(reason)
        if reason:
            self._notify(reason)

    def _notify(self, message: str, warning: bool = True):
        log.info("%s", message)
        if self._tray is None:
            return
        if not self._tray.isVisible():
            self._tray.show()
        icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if warning
            else QSystemTrayIcon.MessageIcon.Information
        )
        self._tray.showMessage(APP_NAME, message, icon, 5000)

    def _show_capture(self):
        if self._capture_in_progress():
            log.info("Ignoring a capture request because a capture is already open")
            return
        self._capture_pending = True
        self._restore_main_after_capture = (
            self._main_window is not None and self._main_window.isVisible()
        )
        try:
            self._hide_for_capture()
            QTimer.singleShot(150, self._do_capture)
        except Exception:
            log.exception("Failed to start capture")
            self._capture_pending = False
            self._restore_after_capture()
            self._notify("Could not start the capture. See the log for details.")

    def _hide_for_capture(self):
        if self._main_window is not None and self._main_window.isVisible():
            self._main_window.hide()
            log.info("Main window hidden for capture")
        if self._tray is not None:
            self._tray.hide()

    def _restore_after_capture(self):
        if self._tray is not None and not self._tray.isVisible():
            self._tray.show()
        should_restore = self._restore_main_after_capture
        self._restore_main_after_capture = False
        if should_restore:
            self._show_main_window()

    def _do_capture(self):
        if self._session is not None and self._session.is_active:
            return
        try:
            session = CaptureOverlay(callback=self._on_capture_result)
            self._session = session
            session.show()
        except Exception:
            log.exception("Failed to start capture")
            session = self._session
            self._session = None
            if session is not None:
                session.abandon()
            self._capture_pending = False
            self._restore_after_capture()
            self._notify("Could not start the capture. See the log for details.")

    def _on_capture_result(self, pil_image):
        """Called from CaptureOverlay on the GUI thread."""
        self._signals.capture_done.emit(pil_image)

    def _on_capture_done(self, pil_image):
        self._capture_pending = False
        self._session = None
        self._restore_after_capture()
        if pil_image is None:
            return
        try:
            self._open_editor(pil_image)
        except Exception:
            log.exception("Failed to open the editor")
            self._notify("Could not open the editor. See the log for details.")

    def _open_record_dialog(self, mode: str = "monitor"):
        if self._recording is not None and self._recording.is_active:
            self._notify("A recording is already in progress. Use Stop recording.")
            return
        dialog = RecordDialog(mode, self._main_window)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._record_fps = dialog.fps()
        chosen = dialog.mode()
        if chosen == "region":
            self._start_region_recording()
            return
        if chosen == "window":
            hwnd = dialog.hwnd()
            if hwnd <= 0:
                self._notify("Choose an application window to record. A browser tab cannot be recorded on its own.")
                return
            self._begin_recording(WindowGrabSource(hwnd))
            return
        screen = dialog.screen()
        if screen is None:
            self._notify("No monitor is available to record.")
            return
        self._begin_recording(GrabSource(screen, None))

    def _start_region_recording(self):
        self._restore_main_after_capture = (
            self._main_window is not None and self._main_window.isVisible()
        )
        try:
            self._hide_for_capture()
            self._session = CaptureOverlay(self._on_record_region, kind="region")
            self._session.show()
        except Exception:
            log.exception("Could not start a region recording")
            self._session = None
            self._restore_after_capture()
            self._notify("Could not start the region selection. See the log for details.")

    def _on_record_region(self, region):
        self._session = None
        if self._tray is not None and not self._tray.isVisible():
            self._tray.show()
        if region is None:
            self._restore_after_capture()
            return
        # Keep the main window hidden until recording stops so it is not in the shot.
        self._begin_recording(GrabSource(region.screen, region.physical_rect))

    def _begin_recording(self, source):
        try:
            path = video_output_path()
            recorder = ScreenRecorder(source, path, self._record_fps)
            recorder.finished.connect(self._on_recording_finished)
            recorder.failed.connect(self._on_recording_failed)
            self._recording = recorder
            if self._main_window is not None and self._main_window.isVisible():
                self._restore_main_after_capture = True
                self._main_window.hide()
                log.info("Main window hidden for capture")
            recorder.start()
            self._set_recording_indicator(True)
        except Exception:
            log.exception("Could not start recording")
            self._recording = None
            self._restore_after_capture()
            self._notify("Could not start recording. See the log for details.")

    def _stop_recording(self):
        if self._recording is not None and self._recording.is_active:
            self._recording.stop()

    def _on_recording_finished(self, path: str):
        self._set_recording_indicator(False)
        self._recording = None
        self._restore_after_capture()
        log.info("Recording saved: %s", path)
        self._notify(f"Recording saved to {path}", warning=False)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    def _on_recording_failed(self, message: str):
        self._set_recording_indicator(False)
        self._recording = None
        self._restore_after_capture()
        self._notify(message or "Recording failed. See the log for details.")

    def _set_recording_indicator(self, recording: bool):
        if self._stop_recording_action is not None:
            self._stop_recording_action.setVisible(recording)
        if self._tray is not None:
            self._tray.setToolTip(f"{APP_NAME} — recording" if recording else APP_NAME)

    def _open_editor(self, pil_image):
        editor = EditorWindow(pil_image)
        editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._editors.append(editor)
        editor.destroyed.connect(lambda *_args, ed=editor: self._forget_editor(ed))
        editor.show()
        editor.raise_()
        editor.activateWindow()

    def _forget_editor(self, editor):
        self._editors = [existing for existing in self._editors if existing is not editor]

    def release_single_instance(self):
        release_server(self._server)
        self._server = None

    def _quit(self):
        if self._main_window is not None:
            self._main_window.allow_close()
            self._main_window.close()
        try:
            if self._hotkey is not None:
                self._hotkey.unregister()
        except Exception:
            log.exception("Failed to unregister the hotkey")
        self.release_single_instance()
        self._app.quit()

    def run(self):
        sys.exit(self._app.exec())


def main():
    setup_logging()
    sys.excepthook = _excepthook
    # Pass fractional scales (150%, 125%) through instead of rounding them
    # onto a whole-number factor before any window is created.
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    demo_folder = demo_screenshots.demo_output_dir(sys.argv)
    if demo_folder is not None:
        raise SystemExit(demo_screenshots.capture_demo_screenshots(demo_folder))
    app = ProSnipApp()
    if app.forwarded:
        sys.exit(0)
    app.run()


if __name__ == "__main__":
    main()
