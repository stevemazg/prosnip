"""Checks for the multi-monitor crop and the review fixes.

Real monitors are not available here. The geometry tests lock the mapping
that keeps a per-monitor, widget-local selection aligned with the grab,
including a 150% scale factor and a monitor that lives at a negative origin.
"""

import ctypes
import json
import logging
import os
import time
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from PIL import Image

import canvas
import capture
import editor
editor.EditorWindow.prompt_on_close = False
import hotkey
import instance
import items
import main
import main_window
from editor_bar import EditorBar


def setUpModule():
    global _APP
    _APP = QApplication.instance() or QApplication([])
    _APP.setQuitOnLastWindowClosed(False)


def _release_host(host):
    for window in list(host._editors):
        window.close()
    if host._tray is not None:
        host._tray.hide()
    handle = getattr(host, "_hotkey", None)
    if handle is not None:
        handle.unregister()
    if getattr(host, "_main_window", None) is not None:
        host._main_window.allow_close()
        host._main_window.close()
    if hasattr(host, "release_single_instance"):
        host.release_single_instance()
    QApplication.processEvents()


class GeometryTests(unittest.TestCase):
    def test_negative_origin_monitor_uses_widget_local_pixels(self):
        # The secondary monitor lives at (-1920, 0). The overlay selection is
        # widget-local, so the top-left of that monitor is (0, 0) of its grab,
        # not a negative virtual-desktop coordinate.
        mapped = capture.map_widget_rect_to_pixmap(
            QRect(0, 0, 100, 50),
            1920,
            1080,
            1920,
            1080,
        )
        self.assertEqual(mapped, QRect(0, 0, 100, 50))

    def test_fractional_scale_maps_logical_selection_onto_physical_pixels(self):
        # 150% monitor: logical 1920x1080, physical 2880x1620.
        full = capture.map_widget_rect_to_pixmap(
            QRect(0, 0, 1920, 1080),
            1920,
            1080,
            2880,
            1620,
        )
        self.assertEqual(full, QRect(0, 0, 2880, 1620))

        quarter = capture.map_widget_rect_to_pixmap(
            QRect(960, 540, 960, 540),
            1920,
            1080,
            2880,
            1620,
        )
        self.assertEqual(quarter, QRect(1440, 810, 1440, 810))

    def test_selection_outside_the_monitor_is_clipped(self):
        mapped = capture.map_widget_rect_to_pixmap(
            QRect(-50, -20, 80, 40),
            200,
            100,
            200,
            100,
        )
        self.assertEqual(mapped, QRect(0, 0, 30, 20))

    def test_empty_widget_maps_to_nothing(self):
        self.assertTrue(
            capture.map_widget_rect_to_pixmap(QRect(0, 0, 10, 10), 0, 10, 10, 10).isEmpty()
        )

    def test_crop_at_one_and_a_half_scale_keeps_the_selected_pixels(self):
        image = QImage(300, 150, QImage.Format.Format_RGB32)
        image.fill(QColor("blue"))
        image.setPixelColor(0, 0, QColor("green"))
        image.setPixelColor(299, 149, QColor("red"))
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(1.5)

        crop = capture.crop_selection(pixmap, QRect(100, 50, 100, 50), 200, 100)
        self.assertIsNotNone(crop)
        pil = capture.qpixmap_to_pil(crop)
        self.assertEqual(pil.size, (150, 75))
        self.assertEqual(pil.getpixel((149, 74)), (255, 0, 0))
        self.assertNotEqual(pil.getpixel((0, 0)), (0, 255, 0))

    def test_qpixmap_to_pil_respects_row_stride(self):
        image = QImage(3, 2, QImage.Format.Format_RGB32)
        image.fill(QColor("blue"))
        image.setPixelColor(2, 1, QColor("red"))
        pil = capture.qpixmap_to_pil(QPixmap.fromImage(image))
        self.assertEqual(pil.size, (3, 2))
        self.assertEqual(pil.getpixel((2, 1)), (255, 0, 0))
        self.assertEqual(pil.getpixel((0, 0)), (0, 0, 255))


class OverlayTests(unittest.TestCase):
    def _session(self):
        self.results = []
        session = capture.CaptureOverlay(lambda image: self.results.append(image))
        session.show()
        self.addCleanup(self._close_session, session)
        return session

    def _close_session(self, session):
        if session.is_active:
            session.abandon()
        QApplication.processEvents()

    def test_overlay_covers_the_screen_without_fullscreen(self):
        screen = QApplication.primaryScreen()
        session = self._session()
        overlay = session._overlays[0]
        self.assertEqual(overlay.geometry(), screen.geometry())
        self.assertFalse(overlay.isFullScreen())
        self.assertFalse(overlay.windowState() & Qt.WindowState.WindowFullScreen)

    def test_selection_uses_local_position_not_virtual_desktop_position(self):
        session = self._session()
        overlay = session._overlays[0]
        # Global coordinates mimic a monitor whose origin is left of the primary.
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10, 20),
            QPointF(-1905, 80),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(110, 70),
            QPointF(-1805, 130),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(overlay, press)
        QApplication.sendEvent(overlay, release)
        widget_width, widget_height = overlay.width(), overlay.height()
        pixmap_width, pixmap_height = overlay._pixmap.width(), overlay._pixmap.height()
        QTest.qWait(50)

        self.assertEqual(len(self.results), 1)
        image = self.results[0]
        self.assertIsNotNone(image)
        local = QRect(QPoint(10, 20), QPoint(110, 70)).normalized()
        expected = capture.map_widget_rect_to_pixmap(
            local,
            widget_width,
            widget_height,
            pixmap_width,
            pixmap_height,
        )
        self.assertEqual(image.size, (expected.width(), expected.height()))
        self.assertGreaterEqual(image.size[0], capture.MIN_SELECTION)
        self.assertGreaterEqual(image.size[1], capture.MIN_SELECTION)

    def test_escape_cancels(self):
        session = self._session()
        overlay = session._overlays[0]
        overlay.setFocus()
        QTest.keyClick(overlay, Qt.Key.Key_Escape)
        QTest.qWait(50)
        self.assertEqual(self.results, [None])
        self.assertFalse(session.is_active)

    def test_tiny_selection_cancels(self):
        session = self._session()
        overlay = session._overlays[0]
        for point, kind, buttons in (
            (QPointF(30, 30), QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
            (QPointF(32, 32), QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
        ):
            button = (
                Qt.MouseButton.LeftButton
                if kind == QEvent.Type.MouseButtonPress
                else Qt.MouseButton.LeftButton
            )
            event = QMouseEvent(
                kind,
                point,
                point,
                button,
                buttons,
                Qt.KeyboardModifier.NoModifier,
            )
            QApplication.sendEvent(overlay, event)
        QTest.qWait(50)
        self.assertEqual(self.results, [None])


class CropTests(unittest.TestCase):
    def test_clamp_keeps_partial_pixels_inside_the_image(self):
        clamped = editor.clamp_crop_rect(QRectF(0.2, 0.2, 10.6, 10.4), 100, 80)
        self.assertEqual(clamped, QRect(0, 0, 11, 11))

    def test_clamp_of_a_rect_that_misses_the_image_is_empty(self):
        self.assertIsNone(editor.clamp_crop_rect(QRectF(500, 500, 10, 10), 100, 80))
        self.assertIsNone(editor.clamp_crop_rect(QRectF(10, 10, 0, 40), 100, 80))

    def test_editor_clamps_the_crop_and_does_not_shift_child_handles(self):
        window = editor.EditorWindow(Image.new("RGB", (100, 80), "red"))
        self.addCleanup(window.close)
        item = items.RectItem(
            QRectF(10, 10, 30, 30),
            QColor("#e63946"),
            QColor(230, 57, 70, 48),
            2,
        )
        window._scene.addItem(item)

        window._on_crop_requested(QRectF(-10, -5, 30, 25))
        self.assertEqual(window._bg_item.pixmap().size().width(), 20)
        self.assertEqual(window._bg_item.pixmap().size().height(), 20)
        self.assertEqual(window._pil_image.size, (20, 20))
        # The clamped origin is (0, 0), so annotations stay put.
        self.assertEqual(item.pos(), QPointF(0, 0))
        self.assertEqual(item.handles[0].pos(), QPointF(10, 10))

        window._on_crop_requested(QRectF(5, 5, 40, 40))
        self.assertEqual(window._bg_item.pixmap().width(), 15)
        self.assertEqual(window._bg_item.pixmap().height(), 15)
        self.assertEqual(item.pos(), QPointF(-5, -5))
        self.assertEqual(item.handles[0].pos(), QPointF(10, 10))

        untouched = window._bg_item.pixmap().size()
        window._on_crop_requested(QRectF(1000, 1000, 10, 10))
        self.assertEqual(window._bg_item.pixmap().size(), untouched)


class TextEditingTests(unittest.TestCase):
    def _editing_item(self, text="Hello", cursor_at=1):
        window = editor.EditorWindow(Image.new("RGB", (80, 60), "white"))
        self.addCleanup(window.close)
        window.show()
        window._view.setFocus()
        item = items.TextItem(text, QPointF(5, 5), QColor("black"), 14)
        window._scene.addItem(item)
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        window._scene.setFocusItem(item)
        item.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = item.textCursor()
        cursor.setPosition(cursor_at)
        item.setTextCursor(cursor)
        QApplication.processEvents()
        self.assertTrue(window._view.is_text_editing())
        return window, item

    def test_backspace_edits_text_instead_of_deleting_the_item(self):
        window, item = self._editing_item()
        window._view.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier)
        )
        self.assertIs(item.scene(), window._scene)
        self.assertEqual(item.toPlainText(), "ello")

    def test_delete_shortcut_edits_text_instead_of_deleting_the_item(self):
        window, item = self._editing_item()
        window._on_delete_shortcut()
        self.assertIs(item.scene(), window._scene)
        self.assertEqual(item.toPlainText(), "Hllo")

    def test_delete_key_removes_one_character(self):
        window, item = self._editing_item()
        QTest.keyClick(window, Qt.Key.Key_Delete)
        QApplication.processEvents()
        self.assertIs(item.scene(), window._scene)
        self.assertEqual(item.toPlainText(), "Hllo")

    def test_backspace_deletes_the_item_when_text_is_not_being_edited(self):
        window, item = self._editing_item()
        item.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        item.clearFocus()
        window._scene.clearFocus()
        self.assertFalse(window._view.is_text_editing())
        item.setSelected(True)
        window._view.keyPressEvent(
            QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier)
        )
        self.assertIsNone(item.scene())

    def test_shortcut_override_is_accepted_while_editing(self):
        window, _item = self._editing_item()
        event = QKeyEvent(
            QEvent.Type.ShortcutOverride,
            Qt.Key.Key_Delete,
            Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(window._view.viewport(), event)
        self.assertTrue(event.isAccepted())


class LauncherTests(unittest.TestCase):
    def _host(self):
        host = main.ProSnipApp()
        self.addCleanup(_release_host, host)
        self.assertFalse(host.forwarded)
        return host

    def test_startup_shows_the_window_with_version_and_actions(self):
        host = self._host()
        window = host._main_window
        self.assertTrue(window.isVisible())
        self.assertFalse(window.isMinimized())
        self.assertEqual(window.windowTitle(), "ProSnip-Bob")
        labels = [label.text() for label in window.findChildren(main_window.QLabel)]
        self.assertIn("ProSnip-Bob", labels)
        self.assertIn(f"Version {editor.APP_VERSION}", labels)
        script = ROOT / "scripts" / "write_version_info.py"
        exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), {"__name__": "__main__", "__file__": str(script)})
        self.assertIn(editor.APP_VERSION, (ROOT / "version_info.txt").read_text(encoding="utf-8"))
        self.assertEqual(window.new_capture_button.text(), "New Capture")
        self.assertEqual(window.quit_button.text(), "Quit")
        status = window.shortcut_label.text()
        self.assertTrue("this system" in status or "Ctrl+Shift+S" in status or "in use" in status)
        self.assertIn("New Capture", window.shortcut_label.text())

    def test_shortcut_status_text(self):
        self.assertEqual(main_window.shortcut_status_text(None), "Shortcut: Ctrl+Shift+S")
        self.assertEqual(
            main_window.shortcut_status_text(hotkey.TAKEN_MESSAGE),
            "Shortcut unavailable (in use by another app), use New Capture.",
        )

    def test_close_hides_to_the_tray_once(self):
        host = self._host()
        notes = []
        host._notify = lambda message, warning=True: notes.append(message)
        host._main_window.close()
        QApplication.processEvents()
        self.assertFalse(host._main_window.isVisible())
        host._main_window.present()
        host._main_window.close()
        QApplication.processEvents()
        still = [message for message in notes if "still running" in message]
        self.assertEqual(still, [f"{editor.APP_NAME} is still running. Click the tray icon to show it again."])

    def test_tray_click_and_second_launch_restore_the_window(self):
        host = self._host()
        host._main_window.hide()
        self.assertFalse(host._main_window.isVisible())
        host._on_tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertTrue(host._main_window.isVisible())
        host._main_window.hide()
        host._on_tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
        self.assertTrue(host._main_window.isVisible())
        host._main_window.hide()
        self.assertTrue(instance.try_notify_primary())
        QTest.qWait(100)
        self.assertTrue(host._main_window.isVisible())

    def test_capture_hides_the_window_and_restores_it(self):
        host = self._host()
        host._do_capture = lambda: None
        host._show_capture()
        self.assertFalse(host._main_window.isVisible())
        self.assertFalse(host._tray.isVisible())
        host._on_capture_done(None)
        self.assertTrue(host._main_window.isVisible())
        self.assertTrue(host._tray.isVisible())

        host._main_window.hide()
        host._show_capture()
        host._on_capture_done(None)
        self.assertFalse(host._main_window.isVisible())

    def test_quit_unregisters_the_hotkey_and_releases_the_instance(self):
        host = self._host()
        called = []
        host._hotkey.unregister = lambda: called.append("hotkey")
        host._app.quit = lambda: called.append("quit")
        host._quit()
        self.assertIn("hotkey", called)
        self.assertIn("quit", called)
        self.assertIsNone(host._server)

    def test_second_claim_notifies_the_first(self):
        calls = []
        first_primary, first_server, first_peer = instance.claim_primary(
            lambda: calls.append("show"), version="1.5.0.0",
        )
        self.addCleanup(instance.release_server, first_server)
        self.assertTrue(first_primary)
        self.assertIsNone(first_peer)
        second_primary, second_server, second_peer = instance.claim_primary(
            lambda: calls.append("other"), version="1.5.0.0",
        )
        QTest.qWait(200)
        self.assertFalse(second_primary)
        self.assertIsNone(second_server)
        self.assertIsNone(second_peer)
        self.assertEqual(calls, ["show"])


class HotkeyTests(unittest.TestCase):
    def test_modifiers_match_the_win32_api(self):
        self.assertEqual(hotkey.MOD_CONTROL, 0x0002)
        self.assertEqual(hotkey.MOD_SHIFT, 0x0004)
        self.assertEqual(hotkey.MOD_NOREPEAT, 0x4000)
        self.assertEqual(
            hotkey.HOTKEY_MODIFIERS,
            hotkey.MOD_CONTROL | hotkey.MOD_SHIFT | hotkey.MOD_NOREPEAT,
        )
        self.assertEqual(hotkey.VK_S, 0x53)
        self.assertEqual(hotkey.VK_P, 0x50)
        self.assertEqual(hotkey.PICK_HOTKEY_ID, 2)
        self.assertNotEqual(hotkey.PICK_HOTKEY_ID, hotkey.HOTKEY_ID)
        self.assertEqual(hotkey.WM_HOTKEY, 0x0312)

    def test_parser_recognises_only_our_hotkey_message(self):
        msg = hotkey.MSG()
        msg.message = hotkey.WM_HOTKEY
        msg.wParam = hotkey.HOTKEY_ID
        address = ctypes.addressof(msg)
        self.assertTrue(
            hotkey.is_our_hotkey_message(b"windows_generic_MSG", address, hotkey.HOTKEY_ID)
        )
        self.assertFalse(
            hotkey.is_our_hotkey_message(b"windows_generic_MSG", address, hotkey.HOTKEY_ID + 1)
        )
        msg.message = 0x0010
        self.assertFalse(
            hotkey.is_our_hotkey_message(b"windows_generic_MSG", address, hotkey.HOTKEY_ID)
        )
        msg.message = hotkey.WM_HOTKEY
        self.assertFalse(
            hotkey.is_our_hotkey_message(b"xcb_generic_event_t", address, hotkey.HOTKEY_ID)
        )

    def test_filter_runs_the_callback_for_our_hotkey(self):
        calls = []
        event_filter = hotkey.HotkeyEventFilter(hotkey.HOTKEY_ID, lambda: calls.append("go"))
        msg = hotkey.MSG()
        msg.message = hotkey.WM_HOTKEY
        msg.wParam = hotkey.HOTKEY_ID
        self.assertEqual(
            event_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg)),
            (True, 0),
        )
        self.assertEqual(calls, ["go"])
        msg.message = 0x000F
        self.assertEqual(
            event_filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(msg)),
            (False, 0),
        )
        self.assertEqual(calls, ["go"])

    def test_register_is_unavailable_off_windows(self):
        if sys.platform == "win32":
            self.skipTest("Windows registers a real hotkey")
        calls = []
        handle = hotkey.GlobalHotkey(lambda: calls.append(1))
        reason = handle.register(QApplication.instance())
        self.addCleanup(handle.unregister)
        self.assertEqual(reason, hotkey.UNAVAILABLE_MESSAGE)
        self.assertIn("Windows", reason)
        self.assertEqual(calls, [])
        handle.unregister()


class AppTests(unittest.TestCase):
    def test_names_and_copy_shortcut_tooltip(self):
        self.assertEqual(editor.APP_NAME, "ProSnip-Bob")
        window = editor.EditorWindow(Image.new("RGB", (10, 10), "white"))
        self.addCleanup(window.close)
        self.assertEqual(window.windowTitle(), "ProSnip-Bob — Untitled")
        self.assertEqual(window._btn_copy.toolTip(), "Copy (Ctrl+C)")
        self.assertEqual(window._btn_save_png.toolTip(), "Save PNG (Ctrl+S)")
        self.assertEqual(window._btn_copy.text(), "Copy")

    def test_second_capture_is_ignored_while_one_is_open(self):
        host = main.ProSnipApp()
        self.addCleanup(_release_host, host)
        hidden = []
        host._tray.hide = lambda: hidden.append("hide")

        host._capture_pending = True
        host._show_capture()
        self.assertEqual(hidden, [])

        host._capture_pending = False

        class _Active:
            is_active = True

        host._session = _Active()
        host._show_capture()
        self.assertEqual(hidden, [])
        self.assertFalse(host._capture_pending)

    def test_three_captures_share_one_editor_and_restore_annotations(self):
        import tempfile

        host = main.ProSnipApp()
        self.addCleanup(_release_host, host)
        previous = os.environ.get("LOCALAPPDATA")
        errors = []
        previous_hook = sys.excepthook

        def _hook(exc_type, exc, tb):
            errors.append(exc)
            previous_hook(exc_type, exc, tb)

        class _Errors(logging.Handler):
            def __init__(self):
                super().__init__(level=logging.ERROR)
                self.records = []

            def emit(self, record):
                self.records.append(record)

        handler = _Errors()
        logging.getLogger("prosnip").addHandler(handler)
        sys.excepthook = _hook
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                red, green, blue = (
                    Image.new("RGB", (48, 32), "red"),
                    Image.new("RGB", (48, 32), "green"),
                    Image.new("RGB", (48, 32), "blue"),
                )
                host._capture_pending = True
                host._on_capture_done(Image.new("RGB", (48, 32), "white"))
                window = host._editors[0]
                before = window._tray.card_count()
                host._capture_pending = True
                host._on_capture_done(red)
                first_path = window._active_path
                mark = items.RectItem(
                    QRectF(4, 4, 12, 12), QColor("#ff0000"), QColor("#ff0000"), 2,
                )
                window._scene.addItem(mark)
                window._scene._push_undo(mark)
                host._capture_pending = True
                host._on_capture_done(green)
                host._capture_pending = True
                host._on_capture_done(blue)
                QApplication.processEvents()
                windows = [
                    widget
                    for widget in QApplication.topLevelWidgets()
                    if isinstance(widget, editor.EditorWindow) and widget.isVisible()
                ]
                self.assertEqual(windows, [window])
                self.assertEqual(len(host._editors), 1)
                self.assertEqual(window._tray.card_count(), before + 3)
                self.assertEqual(window._pil_image.getpixel((1, 1)), (0, 0, 255))
                newest = window._tray._row.itemAt(0).widget()
                self.assertTrue(newest.property("selected"))
                self.assertEqual(newest.property("imagePath"), window._active_path)
                self.assertFalse(any(item is mark for item in window._scene.items()))
                third = window._active_path
                window._open_recent(first_path)
                self.assertEqual(window._pil_image.getpixel((1, 1)), (255, 0, 0))
                self.assertTrue(any(item is mark and item.scene() is window._scene for item in window._scene.items()))
                self.assertTrue(window._scene._undo_stack)
                window._open_recent(third)
                self.assertEqual(window._pil_image.getpixel((1, 1)), (0, 0, 255))
                self.assertFalse(any(item is mark for item in window._scene.items()))
                self.assertEqual(errors, [])
                self.assertEqual(handler.records, [])
        finally:
            sys.excepthook = previous_hook
            logging.getLogger("prosnip").removeHandler(handler)
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_log_path_falls_back_when_the_first_directory_is_not_writable(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked = root / "blocked"
            blocked.write_text("not a directory")
            fallback = root / "fallback"
            path = main.resolve_log_path([blocked, fallback])
            self.assertEqual(path, fallback / "ProSnip-Bob.log")
            self.assertTrue(path.is_file())
            self.assertIsNone(main.resolve_log_path([blocked]))

    def test_console_handler_is_skipped_when_stderr_is_none(self):
        import tempfile

        root_logger = logging.getLogger()
        previous_handlers = list(root_logger.handlers)
        previous_level = root_logger.level
        previous_ready = main._logging_ready
        previous_stderr = sys.stderr
        try:
            for handler in previous_handlers:
                root_logger.removeHandler(handler)
            main._logging_ready = False
            sys.stderr = None
            with tempfile.TemporaryDirectory() as tmp:
                main.setup_logging([Path(tmp)])
                file_handlers = [
                    handler for handler in root_logger.handlers if isinstance(handler, logging.FileHandler)
                ]
                console_handlers = [
                    handler
                    for handler in root_logger.handlers
                    if isinstance(handler, logging.StreamHandler)
                    and not isinstance(handler, logging.FileHandler)
                ]
                self.assertEqual(len(file_handlers), 1)
                self.assertEqual(console_handlers, [])
                self.assertTrue(str(file_handlers[0].baseFilename).endswith("ProSnip-Bob.log"))
                for handler in file_handlers:
                    root_logger.removeHandler(handler)
                    handler.close()
        finally:
            for handler in list(root_logger.handlers):
                root_logger.removeHandler(handler)
                handler.close()
            for handler in previous_handlers:
                root_logger.addHandler(handler)
            root_logger.setLevel(previous_level)
            main._logging_ready = previous_ready
            sys.stderr = previous_stderr

    def test_packaging_files_name_the_bob_executable(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("mss", requirements)
        self.assertNotIn("keyboard", requirements)
        build = (ROOT / "build.bat").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        script = ROOT / "scripts" / "write_version_info.py"
        exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"), {"__name__": "__main__", "__file__": str(script)})
        version = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        command = (
            "pyinstaller --noconfirm --clean --onedir --windowed --noupx "
            "--name ProSnip-Bob --exclude-module tkinter "
            "--version-file version_info.txt --add-data \"LICENSE;.\" "
            "--add-data \"THIRD_PARTY_NOTICES;.\" --add-data \"assets/checkbox-tick.png;assets\" "
            "--icon assets/prosnip-bob.ico src/main.py"
        )
        self.assertIn(command, build)
        self.assertIn(command, workflow)
        self.assertIn(command, readme)
        self.assertIn("/nopause", build)
        self.assertGreaterEqual(build.count("if errorlevel 1"), 2)
        self.assertNotIn("--onefile", build)
        self.assertNotIn("--onefile", workflow)
        self.assertIn("src/editor.py", workflow)
        self.assertIn("APP_VERSION", workflow)
        self.assertIn("steps.version.outputs.name", workflow)
        self.assertIn("ProSnip-Bob-$version-win64", workflow)
        self.assertNotIn("dist/ProSnip-Bob.zip", workflow)
        self.assertNotIn("name: ProSnip-Bob\n", workflow)
        self.assertNotIn("name: ProSnip-Bob ", workflow)
        self.assertIn("prosnip-bob", workflow)
        self.assertIn("python-version: \"3.12\"", workflow)
        self.assertIn("QT_QPA_PLATFORM: offscreen", workflow)
        self.assertIn("colour_picker, main", workflow)
        self.assertNotIn("imageio_ffmpeg", workflow)
        self.assertNotIn("recorder", workflow)
        parts = tuple(int(piece) for piece in editor.APP_VERSION.split("."))
        for text in (
            "Steve Maz",
            "ProSnip-Bob",
            "ProSnip-Bob screen capture and annotation tool",
            editor.APP_VERSION,
            str(parts),
            "ProSnip-Bob.exe",
            "Copyright (C) 2026 Steve Maz",
        ):
            self.assertIn(text, version)
        self.assertIn("unittest tests.test_prosnip_bob", workflow)
        self.assertIn("ISCC", workflow)
        self.assertIn("/VERYSILENT", workflow)
        self.assertIn("/CURRENTUSER", workflow)
        self.assertIn("ProSnip-Bob-${{ steps.version.outputs.version }}-Setup", workflow)
        script = (ROOT / "installer" / "prosnip.iss").read_text(encoding="utf-8")
        for text in (
            "PrivilegesRequiredOverridesAllowed=dialog",
            "AppMutex=ProSnipBobSetup",
            "LicenseFile=..\\LICENSE",
            "THIRD_PARTY_NOTICES",
            "installed.txt",
            "{autopf}\\{#AppName}",
            "desktopicon",
            "startup",
        ):
            self.assertIn(text, script)
        self.assertNotIn("import demo_screenshots", (ROOT / "src" / "main.py").read_text(encoding="utf-8"))

    def test_frozen_log_sits_next_to_the_exe(self):
        import tempfile

        old_executable = sys.executable
        had_frozen = hasattr(sys, "frozen")
        old_frozen = getattr(sys, "frozen", None)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                exe_dir = Path(tmp) / "ProSnip-Bob"
                internal = exe_dir / "_internal"
                internal.mkdir(parents=True)
                exe = exe_dir / "ProSnip-Bob.exe"
                exe.write_bytes(b"")
                sys.frozen = True
                sys.executable = str(exe)
                directories = main.candidate_log_directories()
                self.assertEqual(directories[0], exe_dir.resolve())
                self.assertNotEqual(directories[0], internal.resolve())
        finally:
            sys.executable = old_executable
            if had_frozen:
                sys.frozen = old_frozen
            elif hasattr(sys, "frozen"):
                delattr(sys, "frozen")


class ColourAndPenTests(unittest.TestCase):
    def test_toolbar_buttons_use_tooltips_not_captions(self):
        from colour import ColourHistory
        bar = EditorBar(ColourHistory())
        bar._relayout(1400)
        arrow = bar.button("arrow")
        pen = bar.button("pen")
        if pen is None:
            bar.set_tool("pen")
            pen = bar.button("pen")
        self.assertIsNotNone(arrow)
        self.assertIsNotNone(pen)
        self.assertIn("Arrow", arrow.toolTip())
        self.assertIn("Pen", pen.toolTip())
        self.assertFalse(arrow.icon().isNull())

    def test_style_menu_shows_swatches_and_light_text(self):
        from styles import STYLES, colour_swatch
        from options import ToolOptions

        options = ToolOptions()
        menu = options.build_colour_menu()
        self.assertTrue(menu.windowFlags() & Qt.WindowType.Popup)
        labels = [action.text() for action in menu.actions()]
        self.assertIn("Copy as HEX", labels)
        self.assertIn("Copy as RGB", labels)
        self.assertIn("Copy as HSL", labels)
        self.assertIn("Pick colour from screen", labels)
        self.assertIn("More colours…", labels)
        swatch = colour_swatch(QColor("#e63946"), 16).toImage()
        self.assertEqual(swatch.pixelColor(8, 8).name(), "#e63946")
        self.assertEqual(swatch.pixelColor(1, 1).name(), "#f2f2f2")
        self.assertEqual(len(STYLES), 6)

    def test_selected_style_sets_the_pen_colour(self):
        from styles import STYLES
        from options import ToolOptions

        scene = canvas.ProSnipScene()
        options = ToolOptions()
        options.bind(scene, None)
        options.apply_named_style("Blue")
        self.assertEqual(scene._pen_color.name(), STYLES["Blue"].pen_color.name())

    def test_new_rectangle_has_no_fill_and_transparent_is_in_the_popup(self):
        import tempfile

        from colour import ColourHistory
        from options import ToolOptions, _alpha
        from PyQt6.QtWidgets import QLabel

        class _Event:
            def __init__(self, x, y):
                self._pos = QPointF(x, y)

            def button(self):
                return Qt.MouseButton.LeftButton

            def scenePos(self):
                return self._pos

            def accept(self):
                return None

        with tempfile.TemporaryDirectory() as tmp:
            history = ColourHistory(Path(tmp) / "settings.json")
            options = ToolOptions(history)
            menu = options.build_colour_menu()
            tips = [widget.toolTip() for widget in menu.findChildren(QWidget)]
            labels = [widget.text() for widget in menu.findChildren(QLabel) if hasattr(widget, "text")]
            self.assertIn("Transparent", tips)
            self.assertIn("Transparent", labels)
            scene = canvas.ProSnipScene()
            options.bind(scene, None)
            self.assertEqual(scene._fill_color.alpha(), 0)
            scene.set_tool("rect")
            scene.mousePressEvent(_Event(10, 12))
            scene.mouseReleaseEvent(_Event(90, 70))
            rects = [item for item in scene.items() if isinstance(item, items.RectItem)]
            self.assertEqual(len(rects), 1)
            self.assertEqual(rects[0].fill_color.alpha(), 0)
            self.assertEqual(rects[0].pen_color.name(), "#e63946")
            self.assertEqual(rects[0].pen_color.alpha(), 255)
            rects[0].setSelected(True)
            options.set_fill_colour(QColor("#3d8ee6"))
            self.assertEqual(options._fill_opacity, 30)
            self.assertEqual(rects[0].fill_color.alpha(), _alpha(30))
            self.assertEqual(rects[0].pen_color.alpha(), 255)
            scene.undo()
            self.assertEqual(rects[0].fill_color.alpha(), 0)
            reloaded = ColourHistory(history.path)
            self.assertEqual(reloaded.fill_opacity, 0)
            self.assertEqual(reloaded.border_colour.upper(), "#E63946")

    def test_shape_fills_render_transparent_and_translucent(self):
        from PyQt6.QtWidgets import QGraphicsPixmapItem

        from options import _alpha

        scene = canvas.ProSnipScene()
        scene.setBackgroundBrush(QBrush(Qt.GlobalColor.transparent))
        background = QPixmap(160, 80)
        background.fill(QColor("#00c853"))
        plate = QGraphicsPixmapItem(background)
        plate.setZValue(-100)
        scene.addItem(plate)
        scene.setSceneRect(0, 0, 160, 80)
        scene.addItem(items.RectItem(
            QRectF(8, 8, 60, 60), QColor("#e63946"), QColor(0, 0, 0, 0), 3,
        ))
        scene.addItem(items.RectItem(
            QRectF(90, 8, 60, 60), QColor("#e63946"), QColor(230, 57, 70, _alpha(30)), 3,
        ))
        image = QImage(160, 80, QImage.Format.Format_ARGB32)
        image.fill(QColor("#00c853"))
        painter = QPainter(image)
        scene.render(painter)
        painter.end()
        clear = image.pixelColor(38, 38)
        tinted = image.pixelColor(120, 38)
        self.assertGreater(clear.green(), 180)
        self.assertLess(clear.red(), 40)
        self.assertGreater(tinted.red(), clear.red() + 30)
        self.assertGreater(tinted.green(), 80)

    def test_pen_stroke_can_be_undone_and_redone(self):
        scene = canvas.ProSnipScene()
        scene.set_tool("pen")
        scene.set_pen_color(QColor("#e63946"))
        scene.set_line_width(4)

        class _Event:
            def __init__(self, x, y, release=False):
                self._pos = QPointF(x, y)
                self._release = release

            def button(self):
                return Qt.MouseButton.LeftButton

            def scenePos(self):
                return self._pos

            def accept(self):
                return None

        scene.mousePressEvent(_Event(10, 12))
        scene.mouseMoveEvent(_Event(30, 40))
        scene.mouseMoveEvent(_Event(50, 18))
        scene.mouseReleaseEvent(_Event(55, 22, release=True))
        strokes = [item for item in scene.items() if isinstance(item, items.StrokeItem)]
        self.assertEqual(len(strokes), 1)
        stroke = strokes[0]
        self.assertGreaterEqual(len(stroke._points), 3)
        self.assertFalse(stroke.highlighter)
        self.assertEqual(stroke.line_width, 4)
        self.assertEqual(scene._tool, "pen")
        scene.undo()
        self.assertEqual(
            [item for item in scene.items() if isinstance(item, items.StrokeItem)],
            [],
        )
        scene.redo()
        self.assertEqual(
            len([item for item in scene.items() if isinstance(item, items.StrokeItem)]),
            1,
        )

    def test_highlighter_is_translucent_and_thick(self):
        stroke = items.StrokeItem(QColor("#f4a261"), 2, highlighter=True)
        self.assertTrue(stroke.highlighter)
        self.assertEqual(stroke.line_width, 12)
        self.assertLess(stroke.pen_color.alpha(), 255)
        stroke.add_point(QPointF(0, 0))
        stroke.add_point(QPointF(20, 0))
        self.assertFalse(stroke.boundingRect().isEmpty())


class PaintPathTests(unittest.TestCase):
    def test_every_annotation_paints(self):
        from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem

        scene = canvas.ProSnipScene()
        background = QPixmap(480, 320)
        background.fill(QColor("#d7e6f5"))
        background.setDevicePixelRatio(1.0)
        plate = QGraphicsPixmapItem(background)
        plate.setZValue(-100)
        scene.addItem(plate)
        scene.setSceneRect(0, 0, 480, 320)
        scene.addItem(items.RectItem(QRectF(20, 20, 80, 50), QColor("#e63946"), QColor(230, 57, 70, 60), 3))
        scene.addItem(items.EllipseItem(QRectF(120, 20, 70, 50), QColor("#2d6a4f"), QColor(45, 106, 79, 50), 2))
        for index, style in enumerate(items.ARROW_STYLES):
            scene.addItem(items.ArrowItem(
                QPointF(20, 100 + index * 28),
                QPointF(180, 112 + index * 28),
                QColor("#1d3557"),
                6,
                style,
            ))
        scene.addItem(items.TextItem("Hello", QPointF(220, 40), QColor("#111111"), 16))
        scene.addItem(items.CalloutItem(QPointF(220, 160), QColor("#003049"), QColor(0, 48, 73, 40), QColor("#003049"), 2, 12))
        scene.addItem(items.StampItem("✅", QPointF(360, 40)))
        pen = items.StrokeItem(QColor("#e63946"), 4)
        pen.add_point(QPointF(220, 260))
        pen.add_point(QPointF(300, 280))
        pen.add_point(QPointF(380, 250))
        scene.addItem(pen)
        highlight = items.StrokeItem(QColor("#f4a261"), 8, highlighter=True)
        highlight.add_point(QPointF(220, 300))
        highlight.add_point(QPointF(400, 300))
        scene.addItem(highlight)
        overlay = QPixmap(40, 30)
        overlay.fill(QColor("#ffffff"))
        scene.addItem(items.ImageOverlayItem(overlay, QPointF(400, 200)))
        rubber = QGraphicsRectItem(QRectF(10, 10, 30, 20))
        rubber.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine))
        rubber.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        scene.addItem(rubber)
        image = QImage(480, 320, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        scene.render(painter)
        painter.end()
        self.assertFalse(image.isNull())
        self.assertGreater(image.pixelColor(40, 40).alpha(), 0)
        # Tapered arrow is thin at the tail and has a wide head just before the tip.
        # Index 4 runs from (20, 212) to (180, 224).
        head = image.pixelColor(152, 214)
        tail_off = image.pixelColor(36, 198)
        self.assertLess(abs(head.red() - 0x1D) + abs(head.green() - 0x35) + abs(head.blue() - 0x57), 80)
        self.assertGreater(
            abs(tail_off.red() - 0x1D) + abs(tail_off.green() - 0x35) + abs(tail_off.blue() - 0x57),
            80,
        )

    def test_dark_swatches_have_a_light_outline(self):
        from styles import colour_swatch

        blue = colour_swatch(QColor("#1d3557"), 16).toImage()
        self.assertEqual(blue.pixelColor(2, 2).name(), "#ffffff")
        self.assertEqual(blue.pixelColor(8, 8).name(), "#1d3557")

    def test_custom_stamp_is_stored(self):
        import os
        from stamp_picker import add_custom_stamp, custom_stamp_paths

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["APPDATA"] = tmp
            source = Path(tmp) / "mark.png"
            pixmap = QPixmap(16, 16)
            pixmap.fill(QColor("#e63946"))
            pixmap.save(str(source), "PNG")
            saved = add_custom_stamp(str(source))
            self.assertIsNotNone(saved)
            self.assertTrue(saved.is_file())
            self.assertIn(saved, custom_stamp_paths())
            self.assertEqual(saved.parent, Path(tmp) / "ProSnip-Bob" / "stamps")


class DemoFlagTests(unittest.TestCase):
    def test_flag_is_opt_in(self):
        import demo_screenshots

        self.assertIsNone(demo_screenshots.demo_output_dir(["ProSnip-Bob.exe"]))
        self.assertEqual(
            demo_screenshots.demo_output_dir(["ProSnip-Bob.exe", "--demo-screenshots", "shots"]),
            Path("shots"),
        )


class EditorLayoutTests(unittest.TestCase):
    def test_frame_fits_a_small_snip_and_clamps_a_large_one(self):
        from layout import fit_editor_frame

        class Area:
            def __init__(self, x, y, width, height):
                self._x, self._y, self._w, self._h = x, y, width, height

            def x(self):
                return self._x

            def y(self):
                return self._y

            def width(self):
                return self._w

            def height(self):
                return self._h

        monitor = Area(0, 0, 1280, 800)
        small = fit_editor_frame(400, 300, 280, 150, monitor, 1)
        self.assertEqual((small[2], small[3]), (680, 450))
        huge = fit_editor_frame(4000, 3000, 280, 150, monitor, 1)
        self.assertEqual((huge[2], huge[3]), (1280, 800))
        left = Area(-1920, 0, 1920, 1080)
        placed = fit_editor_frame(800, 600, 100, 100, left, 1.5)
        self.assertGreaterEqual(placed[0], -1920)
        self.assertLessEqual(placed[0] + placed[2], 0)
        self.assertEqual(fit_editor_frame(1500, 900, 0, 0, monitor, 1.5)[2], 1000)
        self.assertEqual(fit_editor_frame(1000, 500, 0, 0, monitor, 1.25)[2], 800)
        wide = fit_editor_frame(200, 120, 400, 56, monitor, 1.5, minimum_w=1080, minimum_h=680)
        self.assertGreaterEqual(wide[2], 1080)
        self.assertGreaterEqual(wide[3], 680)
        self.assertLessEqual(wide[2], 1280)
        from layout import tool_column_layout
        self.assertEqual(tool_column_layout(16, 1000), (2, 32))
        self.assertEqual(tool_column_layout(16, 640), (2, 32))
        columns, button = tool_column_layout(16, 180)
        self.assertEqual(columns, 3)
        self.assertGreaterEqual(button, 24)

    def test_editor_tools_sit_left_of_the_canvas(self):
        from PIL import Image as PILImage

        window = editor.EditorWindow(PILImage.new("RGB", (800, 500), "#d7e6f5"))
        self.addCleanup(window.close)
        window.resize(1200, 800)
        window.show()
        QApplication.processEvents()
        window.assert_compact_layout()
        toolbar = window._bar.mapTo(window, window._bar.rect().topLeft())
        canvas = window._view.mapTo(window, window._view.rect().topLeft())
        sidebar = window._sidebar.mapTo(window, window._sidebar.rect().topLeft())
        self.assertLess(toolbar.y(), canvas.y())
        self.assertGreater(sidebar.x(), canvas.x())

    def test_editor_stays_compact_at_three_sizes(self):
        from PIL import Image as PILImage
        from PyQt6.QtWidgets import QDockWidget

        window = editor.EditorWindow(PILImage.new("RGB", (960, 540), "#d7e6f5"))
        self.addCleanup(window.close)
        window.show()
        for width, height in ((900, 600), (1024, 680), (1920, 1080)):
            window.resize(width, height)
            QApplication.processEvents()
            window.assert_compact_layout()
            self.assertLessEqual(window._bar.height(), 64)
            self.assertEqual(window.findChildren(QDockWidget), [])

    def test_step_numbers_follow_the_badges_on_the_canvas(self):
        scene = canvas.ProSnipScene()
        scene.set_tool("number")

        class _Event:
            def __init__(self, x, y):
                self._pos = QPointF(x, y)

            def button(self):
                return Qt.MouseButton.LeftButton

            def scenePos(self):
                return self._pos

            def accept(self):
                return None

        for x in (10, 40, 70, 100, 130, 160):
            scene.mousePressEvent(_Event(x, 20))
        numbers = sorted(item.number for item in scene.items() if isinstance(item, items.NumberItem))
        self.assertEqual(numbers, [1, 2, 3, 4, 5, 6])
        self.assertEqual(scene._next_number, 7)
        scene.undo()
        numbers = sorted(item.number for item in scene.items() if isinstance(item, items.NumberItem))
        self.assertEqual(numbers, [1, 2, 3, 4, 5])
        self.assertEqual(scene._next_number, 6)
        scene.delete_all_annotations()
        self.assertEqual(scene.step_numbers(), [])
        self.assertEqual(scene._next_number, 1)
        scene.set_next_number(4)
        scene.mousePressEvent(_Event(20, 40))
        self.assertEqual(scene.step_numbers(), [4])
        scene.renumber_steps()
        self.assertEqual(scene.step_numbers(), [1])
        self.assertEqual(scene._next_number, 2)

    def test_text_and_panel_contrast(self):
        from theme import colours_for, contrast_ratio

        for mode in ("light", "dark"):
            colours = colours_for(mode)
            for foreground, background in (
                (colours["text"], colours["window"]),
                (colours["text"], colours["panel"]),
                (colours["muted"], colours["window"]),
                (colours["muted"], colours["panel"]),
                ("#ffffff", colours["accent"]),
                (colours["tray_text"], colours["tray_fill"]),
                (colours["text"], colours["panel"]),
            ):
                self.assertGreaterEqual(
                    contrast_ratio(QColor(foreground), QColor(background)),
                    4.5,
                    f"{foreground} on {background} in {mode}",
                )

    def test_pen_width_is_inside_the_bounding_rect(self):
        rect = items.RectItem(QRectF(10, 10, 80, 40), QColor("#e63946"), QColor(0, 0, 0, 0), 16)
        bounds = rect.boundingRect()
        self.assertLessEqual(bounds.left(), 10 - 8)
        self.assertGreaterEqual(bounds.right(), 90 + 8)
        callout = items.CalloutItem(
            QPointF(0, 0), QColor("#111111"), QColor("#ffffff"), QColor("#111111"), 12, 14,
        )
        self.assertGreater(callout.boundingRect().bottom(), callout._rect.bottom() + 12)

    def test_undo_command_removes_and_restores(self):
        scene = canvas.ProSnipScene()
        scene.set_tool("number")

        class _Event:
            def __init__(self, x, y):
                self._pos = QPointF(x, y)

            def button(self):
                return Qt.MouseButton.LeftButton

            def scenePos(self):
                return self._pos

            def accept(self):
                return None

        scene.mousePressEvent(_Event(20, 20))
        self.assertEqual(len([item for item in scene.items() if isinstance(item, items.NumberItem)]), 1)
        scene.undo()
        self.assertEqual([item for item in scene.items() if isinstance(item, items.NumberItem)], [])
        scene.redo()
        self.assertEqual(len([item for item in scene.items() if isinstance(item, items.NumberItem)]), 1)

    def test_swatches_are_separate_from_recent_picks(self):
        import tempfile
        from colour import ColourHistory
        from swatches import SwatchBook

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            book = SwatchBook(path)
            book.add("#1a2b3c", "Ink")
            self.assertEqual(len(book.items), 1)
            book.rename(0, "Navy")
            self.assertEqual(SwatchBook(path).items[0]["name"], "Navy")
            export = Path(tmp) / "out.json"
            book.export_path(export)
            book.clear()
            self.assertEqual(SwatchBook(path).items, [])
            fresh = SwatchBook(path)
            self.assertEqual(fresh.import_path(export), 1)
            ColourHistory(path).add_rgb(1, 2, 3)
            self.assertEqual(SwatchBook(path).items[0]["hex"], "#1A2B3C")


class ColourFormatTests(unittest.TestCase):
    def test_hex_rgb_and_hsl_edges(self):
        from colour import format_colour, next_format, rgb_to_hsl

        self.assertEqual(format_colour(26, 43, 60), "#1A2B3C")
        self.assertEqual(format_colour(26, 43, 60, "rgb"), "rgb(26, 43, 60)")
        self.assertEqual(format_colour(26, 43, 60, "hsl"), "hsl(210, 40%, 17%)")
        self.assertEqual(rgb_to_hsl(26, 43, 60), (210, 40, 17))
        self.assertEqual(format_colour(0, 0, 0, "hsl"), "hsl(0, 0%, 0%)")
        self.assertEqual(format_colour(255, 255, 255, "hsl"), "hsl(0, 0%, 100%)")
        self.assertEqual(format_colour(255, 0, 0, "hsl"), "hsl(0, 100%, 50%)")
        self.assertEqual(format_colour(0, 255, 0, "hsl"), "hsl(120, 100%, 50%)")
        self.assertEqual(format_colour(0, 0, 255, "hsl"), "hsl(240, 100%, 50%)")
        self.assertEqual(format_colour(128, 128, 128, "hsl"), "hsl(0, 0%, 50%)")
        self.assertEqual(format_colour(-4, 300, 26.2), "#00FF1A")
        self.assertEqual(next_format("hex"), "rgb")
        self.assertEqual(next_format("rgb"), "hsl")
        self.assertEqual(next_format("hsl"), "hex")
        self.assertEqual(next_format("nope"), "rgb")

    def test_zoom_clamps_to_the_loupe_range(self):
        from colour import ZOOM_DEFAULT, clamp_zoom

        self.assertEqual(clamp_zoom(8), 8)
        self.assertEqual(clamp_zoom(1), 2)
        self.assertEqual(clamp_zoom(2), 2)
        self.assertEqual(clamp_zoom(32), 32)
        self.assertEqual(clamp_zoom(100), 32)
        self.assertEqual(clamp_zoom(7.6), 8)
        self.assertEqual(clamp_zoom("nope"), ZOOM_DEFAULT)
        self.assertEqual(clamp_zoom(None), ZOOM_DEFAULT)

    def test_history_persists_the_latest_twelve(self):
        import tempfile

        from colour import HISTORY_LIMIT, ColourHistory, format_colour

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            history = ColourHistory(path)
            self.assertEqual(history.format, "hex")
            self.assertEqual(history.zoom, 8)
            for index in range(HISTORY_LIMIT + 1):
                history.add_rgb(index, 0, 0)
            self.assertEqual(len(history.colours), HISTORY_LIMIT)
            self.assertEqual(history.colours[0], format_colour(HISTORY_LIMIT, 0, 0))
            self.assertNotIn(format_colour(0, 0, 0), history.colours)
            history.add_rgb(HISTORY_LIMIT, 0, 0)
            self.assertEqual(history.colours.count(format_colour(HISTORY_LIMIT, 0, 0)), 1)
            history.set_format("hsl")
            history.set_zoom(40)
            reloaded = ColourHistory(path)
            self.assertEqual(reloaded.format, "hsl")
            self.assertEqual(reloaded.zoom, 32)
            self.assertEqual(reloaded.colours, history.colours)
            self.assertEqual(reloaded.display("#1A2B3C"), "hsl(210, 40%, 17%)")

    def test_loupe_centres_on_the_sampled_pixel(self):
        from colour_picker import loupe_top_left, render_loupe, widget_to_pixel

        source = QImage(30, 20, QImage.Format.Format_ARGB32)
        source.fill(QColor("#1a2b3c"))
        loupe = render_loupe(source, 4, 4, 8)
        centre = loupe.pixelColor(5 * 8 + 3, 5 * 8 + 3)
        self.assertEqual((centre.red(), centre.green(), centre.blue()), (26, 43, 60))
        self.assertEqual(loupe.width(), 11 * 8)
        self.assertEqual(widget_to_pixel(100, 50, 200, 100, 400, 200), (200, 100))
        self.assertEqual(widget_to_pixel(-5, 999, 200, 100, 400, 200), (0, 199))
        self.assertEqual(loupe_top_left(10, 10, 80, 100, 400, 300), (28, 28))
        flipped = loupe_top_left(380, 280, 80, 100, 400, 300)
        self.assertLess(flipped[0], 380)
        self.assertLess(flipped[1], 280)

    def test_toolbar_uses_large_icons_and_names_the_picker(self):
        from colour import ColourHistory
        bar = EditorBar(ColourHistory())
        bar.set_tool("screenpick")
        picker = bar.button("screenpick")
        self.assertIsNotNone(picker)
        self.assertLessEqual(picker.iconSize().width(), 32)
        self.assertGreaterEqual(picker.width(), 28)
        self.assertIn("colour", picker.toolTip().lower())


class Phase181Tests(unittest.TestCase):
    def _plate(self, scene, width=200, height=120, colour="#d7e6f5"):
        from PyQt6.QtWidgets import QGraphicsPixmapItem

        pixmap = QPixmap(width, height)
        pixmap.fill(QColor(colour))
        plate = QGraphicsPixmapItem(pixmap)
        plate.setZValue(-100)
        scene.addItem(plate)
        scene.setSceneRect(0, 0, width, height)
        return plate

    def test_presets_follow_the_active_tool_and_line_up(self):
        from sidebar import PreviewTile

        window = editor.EditorWindow(Image.new("RGB", (640, 360), "#d7e6f5"))
        self.addCleanup(window.close)
        window._on_tool_changed("pen")
        QApplication.processEvents()
        pens = window._sidebar.findChildren(PreviewTile)
        self.assertGreaterEqual(len(pens), 8)
        size = pens[0].size()
        host = window._sidebar._grid_host
        for tile in pens:
            self.assertEqual(tile.size(), size)
            self.assertEqual(tile._tool, "pen")
            pos = tile.mapTo(host, tile.rect().topLeft())
            self.assertGreaterEqual(pos.x(), 0)
            self.assertGreaterEqual(pos.y(), 0)
        window._on_tool_changed("arrow")
        QApplication.processEvents()
        arrows = [tile for tile in window._sidebar.findChildren(PreviewTile) if tile._tool == "arrow"]
        self.assertGreaterEqual(len(arrows), 8)
        self.assertTrue(all(tile._tool == "arrow" for tile in arrows))
        white = next(tile for tile in arrows if tile._name == "White")
        image = white.grab().toImage()
        colours = {
            image.pixelColor(x, y).name()
            for x in range(0, image.width(), 4)
            for y in range(0, image.height(), 4)
        }
        self.assertGreater(len(colours), 2)
        self.assertIn("menu-indicator", window._bar.styleSheet())
        self.assertIn("Create", window._bar.findChild(QWidget, "CreateButton").text())

    def test_recent_tray_fits_the_caption_without_a_vertical_bar(self):
        window = editor.EditorWindow(Image.new("RGB", (320, 180), "#d7e6f5"))
        self.addCleanup(window.close)
        window._tray.remember(Image.new("RGB", (80, 48), "#fff7e8"), "capture-120000")
        scroll = window._tray._scroll
        self.assertEqual(scroll.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.assertLessEqual(window._tray.height(), 130)
        card = window._tray.findChild(QWidget, "RecentCard")
        caption = card.findChild(QWidget, "RecentCaption")
        self.assertIsNotNone(caption)
        self.assertLessEqual(caption.height(), card.height())
        bottom = card.mapTo(window._tray, card.rect().bottomLeft()).y()
        self.assertLess(bottom, window._tray.height())

    def test_shadow_curve_ends_and_rounded_rect(self):
        arrow = items.ArrowItem(QPointF(10, 40), QPointF(120, 20), QColor("#e00000"), 4, "curved")
        arrow.start_cap = "square"
        arrow.end_cap = "dot"
        arrow.shadow_enabled = True
        items.apply_shadow(arrow)
        self.assertIsNotNone(arrow.graphicsEffect())
        rect = items.RectItem(QRectF(0, 0, 80, 40), QColor("#3949ab"), QColor(57, 73, 171, 40), 2)
        rect.corner_radius = 14
        scene = canvas.ProSnipScene()
        scene.addItem(arrow)
        scene.addItem(rect)
        scene.setSceneRect(0, 0, 180, 80)
        image = QImage(180, 80, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        scene.render(painter)
        painter.end()
        painted = image.pixelColor(50, 8)
        self.assertNotEqual(painted.name(), "#ffffff")
        self.assertGreater(painted.blue(), 40)
        items.apply_shadow(arrow)
        arrow.shadow_enabled = False
        items.apply_shadow(arrow)
        self.assertIsNone(arrow.graphicsEffect())

    def test_polygon_spotlight_eraser_cut_group_flatten_and_duplicate(self):
        scene = canvas.ProSnipScene()
        plate = self._plate(scene, 200, 100, "#4488cc")
        scene.set_pen_color(QColor("#e00000"))
        scene.set_fill_color(QColor(224, 0, 0, 80))
        scene.set_tool("polygon")
        scene._poly_points = [QPointF(10, 10), QPointF(40, 12), QPointF(24, 36)]
        polygon = scene.finish_polygon()
        self.assertIsInstance(polygon, items.PolygonItem)
        self.assertEqual(len(polygon.points), 3)

        spot = items.SpotlightItem(QRectF(120, 20, 40, 30), 160)
        scene.addItem(spot)
        self.assertGreater(spot.darkness, 100)
        self.assertLess(spot.shape().boundingRect().width(), 80)

        kept = items.RectItem(QRectF(150, 60, 20, 20), QColor("#111111"), QColor(0, 0, 0, 0), 2)
        scene.addItem(kept)
        stroke = items.StrokeItem(QColor("#ffffff"), 18)
        stroke.add_point(QPointF(20, 20))
        stroke.add_point(QPointF(30, 20))
        scene.addItem(stroke)
        scene.erase_to_canvas(stroke)
        self.assertNotIn(stroke, scene.items())
        cleared = plate.pixmap().toImage().pixelColor(24, 20)
        self.assertLess(cleared.alpha(), 20)

        mover = items.RectItem(QRectF(0, 0, 10, 10), QColor("#111111"), QColor(0, 0, 0, 0), 1)
        mover.setPos(10, 80)
        scene.addItem(mover)
        self.assertTrue(scene.cut_strip(QRectF(0, 40, 200, 16)))
        self.assertLess(plate.pixmap().height(), 100)
        self.assertLess(mover.pos().y(), 80)

        scene.undo()
        self.assertEqual(plate.pixmap().height(), 100)

        left = items.RectItem(QRectF(0, 0, 16, 16), QColor("#111111"), QColor(0, 0, 0, 0), 1)
        right = items.RectItem(QRectF(30, 0, 16, 16), QColor("#111111"), QColor(0, 0, 0, 0), 1)
        scene.addItem(left)
        scene.addItem(right)
        left.setSelected(True)
        right.setSelected(True)
        group = scene.group_selected()
        self.assertIsNotNone(group)
        self.assertIs(left.parentItem(), group)
        scene.ungroup_selected()
        self.assertIsNone(left.parentItem())

        mark = items.RectItem(QRectF(4, 4, 20, 20), QColor("#ff0000"), QColor("#ff0000"), 1)
        scene.addItem(mark)
        mark.setSelected(True)
        self.assertTrue(scene.flatten_selected())
        self.assertNotIn(mark, scene.items())
        flat = plate.pixmap().toImage().pixelColor(10, 10)
        self.assertGreater(flat.red(), 180)
        scene.undo()
        self.assertIn(mark, scene.items())

        copy = scene.duplicate_at(mark.sceneBoundingRect().center())
        self.assertIsNotNone(copy)
        self.assertIsNot(copy, mark)
        self.assertTrue(copy.isSelected())


class Quality182Tests(unittest.TestCase):
    def _editor(self):
        window = editor.EditorWindow(Image.new("RGB", (80, 40), "white"))
        self.addCleanup(window.close)
        window._prompt_on_close = False
        return window

    def test_shortcuts_fire_once(self):
        window = self._editor()
        window.show()
        scene = window._scene
        scene.set_tool("number")
        scene.mousePressEvent(type("E", (), {
            "button": lambda self: Qt.MouseButton.LeftButton,
            "scenePos": lambda self: QPointF(10, 10),
            "accept": lambda self: None,
        })())
        self.assertEqual(len(scene.step_numbers()), 1)
        window._view.setFocus()
        window._view.scale(2, 2)
        QTest.keyClick(window._view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        self.assertEqual(scene.step_numbers(), [])
        QTest.keyClick(window._view, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        self.assertEqual(scene.step_numbers(), [1])
        QTest.keyClick(window._view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        self.assertTrue(any(item.isSelected() for item in scene.items() if isinstance(item, items.NumberItem)))
        window._view.scale(2, 2)
        QTest.keyClick(window._view, Qt.Key.Key_0, Qt.KeyboardModifier.ControlModifier)
        QApplication.processEvents()
        self.assertAlmostEqual(window._view.transform().m11(), 1.0, places=2)

    def test_new_and_open_add_tray_cards(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                window = self._editor()
                window._history.set_canvas_colour("#ffffff")
                before = window._tray.card_count()
                window._new_blank()
                self.assertEqual(window._tray.card_count(), before + 1)
                self.assertEqual(window._pil_image.getpixel((0, 0)), (255, 255, 255))
                image_path = Path(tmp) / "ProSnip" / "opened.png"
                image_path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (20, 20), "blue").save(image_path)
                window._history.last_folder = str(image_path.parent)

                def _open(*_args):
                    return str(image_path), ""

                original_open = editor.QFileDialog.getOpenFileName
                editor.QFileDialog.getOpenFileName = staticmethod(_open)
                try:
                    window._open_image()
                    self.assertEqual(window._tray.card_count(), before + 2)
                    self.assertEqual(window._pil_image.getpixel((0, 0)), (0, 0, 255))
                finally:
                    editor.QFileDialog.getOpenFileName = original_open
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_failed_save_shows_an_error_and_keeps_the_title(self):
        window = self._editor()
        title = window.windowTitle()
        warnings = []
        original_dialog = editor.QFileDialog.getSaveFileName
        original_warning = editor.QMessageBox.warning
        original_save = editor.QImage.save
        editor.QFileDialog.getSaveFileName = staticmethod(lambda *args: ("/tmp/no-such-dir/out.png", ""))
        editor.QMessageBox.warning = staticmethod(lambda *args: warnings.append(args))
        editor.QImage.save = lambda self, *args, **kwargs: False
        try:
            window._save_png()
            self.assertTrue(warnings)
            self.assertEqual(window.windowTitle(), title)
        finally:
            editor.QFileDialog.getSaveFileName = original_dialog
            editor.QMessageBox.warning = original_warning
            editor.QImage.save = original_save

    def test_damaged_tray_json_is_skipped(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                from recents import RecentTray, library_dir
                folder = library_dir()
                (folder / "broken.json").write_text('{"created": "x"}', encoding="utf-8")
                (folder / "list.json").write_text("[1, 2]", encoding="utf-8")
                tray = RecentTray()
                self.addCleanup(tray.deleteLater)
                self.assertEqual(tray.card_count(), 0)
                tray._pin(folder / "broken.json")
                tray._hide(folder / "list.json")
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_image_operations_are_undoable(self):
        window = self._editor()
        scene = window._scene
        mark = items.RectItem(QRectF(10, 4, 12, 8), QColor("#ff0000"), QColor(0, 0, 0, 0), 1)
        scene.addItem(mark)
        before = mark.rect().x()
        window._flip_image()
        self.assertNotEqual(mark.rect().x(), before)
        scene.undo()
        self.assertEqual(window._pil_image.width, 80)
        self.assertAlmostEqual(mark.rect().x(), before, places=3)

    def test_every_item_type_clones(self):
        samples = [
            items.RectItem(QRectF(0, 0, 10, 8), QColor("#111111"), QColor(0, 0, 0, 0), 1),
            items.EllipseItem(QRectF(0, 0, 10, 8), QColor("#111111"), QColor(0, 0, 0, 0), 1),
            items.SpotlightItem(QRectF(0, 0, 10, 8), 80),
            items.ArrowItem(QPointF(0, 0), QPointF(12, 4), QColor("#111111"), 2, "dashed"),
            items.TextItem("Hi", QPointF(1, 1), QColor("#111111"), 12),
            items.CalloutItem(QPointF(0, 0), QColor("#111"), QColor("#fff"), QColor("#111"), 2, 12),
            items.NumberItem(3, QPointF(2, 2), QColor("#e00000")),
            items.StrokeItem(QColor("#111111"), 3),
            items.PolygonItem([QPointF(0, 0), QPointF(4, 0), QPointF(2, 4)], QColor("#111"), QColor(0, 0, 0, 0), 1),
            items.BlurItem(QRectF(0, 0, 8, 8), 4),
            items.StampItem("ok", QPointF(1, 1)),
        ]
        samples[7].add_point(QPointF(0, 0))
        samples[7].add_point(QPointF(6, 2))
        samples[3].start_cap = "dot"
        for item in samples:
            clone = item.clone()
            self.assertIs(type(clone), type(item))
            self.assertIsNot(clone, item)
        self.assertEqual(samples[3].clone().start_cap, "dot")
        self.assertIsInstance(samples[2].clone(), items.SpotlightItem)

    def test_close_autosaves_a_psnip(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                window = editor.EditorWindow(Image.new("RGB", (30, 20), "red"))
                window._prompt_on_close = False
                window._scene.addItem(items.RectItem(QRectF(1, 1, 4, 4), QColor("#010101"), QColor(0, 0, 0, 0), 1))
                path = window._active_path
                window.close()
                from persist import read_psnip
                saved = read_psnip(path)
                self.assertIsNotNone(saved)
                self.assertEqual(saved[0][0].__class__.__name__, "RectItem")
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous


class Quality183Tests(unittest.TestCase):
    def test_close_and_reopen_keeps_every_item_and_the_crop(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                window = editor.EditorWindow(Image.new("RGB", (200, 100), "white"))
                window._prompt_on_close = False
                scene = window._scene
                first = items.RectItem(QRectF(60, 10, 20, 16), QColor("#e00000"), QColor(224, 0, 0, 40), 2)
                second = items.RectItem(QRectF(90, 10, 20, 16), QColor("#3949ab"), QColor(0, 0, 0, 0), 2)
                scene.addItem(first)
                scene.addItem(second)
                first.setSelected(True)
                second.setSelected(True)
                group = scene.group_selected()
                self.assertIsNotNone(group)
                pix = QPixmap(12, 8)
                pix.fill(QColor("#111111"))
                scene.addItem(items.ImageOverlayItem(pix, QPointF(80, 20)))
                scene.addItem(items.EllipseItem(QRectF(80, 40, 18, 12), QColor("#111"), QColor(0, 0, 0, 0), 1))
                scene.addItem(items.ArrowItem(QPointF(80, 70), QPointF(130, 80), QColor("#111"), 2, "curved"))
                scene.addItem(items.TextItem("Note", QPointF(50, 60), QColor("#111"), 12))
                scene.addItem(items.NumberItem(2, QPointF(120, 40), QColor("#e00000")))
                stroke = items.StrokeItem(QColor("#111"), 2)
                stroke.add_point(QPointF(140, 70))
                stroke.add_point(QPointF(170, 80))
                scene.addItem(stroke)
                polygon = items.PolygonItem(
                    [QPointF(0, 0), QPointF(10, 0), QPointF(5, 8)], QColor("#111"), QColor(0, 0, 0, 0), 1,
                )
                polygon.setPos(QPointF(100, 70))
                scene.addItem(polygon)
                scene.addItem(items.SpotlightItem(QRectF(150, 10, 30, 20), 100))
                scene.addItem(items.BlurItem(QRectF(150, 40, 20, 12), 4))
                scene.addItem(items.StampItem("ok", QPointF(150, 70)))
                window._on_crop_requested(QRectF(50, 0, 150, 100))
                self.assertEqual(window._pil_image.size, (150, 100))
                path = window._active_path
                window.autosave_active()
                window.close()
                again = editor.EditorWindow(Image.new("RGB", (20, 20), "black"))
                again._prompt_on_close = False
                again._open_recent(path)
                self.assertEqual(again._pil_image.size, (150, 100))
                kinds = {item.__class__.__name__ for item in again._scene.items()}
                for name in (
                    "QGraphicsItemGroup", "RectItem", "ImageOverlayItem", "EllipseItem", "ArrowItem",
                    "TextItem", "NumberItem", "StrokeItem", "PolygonItem", "SpotlightItem",
                    "BlurItem", "StampItem",
                ):
                    self.assertIn(name, kinds)
                again.close()
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_hide_keeps_files_and_delete_leaves_the_library(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                from recents import RecentTray, library_dir
                tray = RecentTray()
                path = tray.remember(Image.new("RGB", (8, 8), "red"), "keep")
                self.assertTrue(Path(path).is_file())
                meta = Path(path).with_suffix(".json")
                tray._hide(meta)
                self.assertTrue(Path(path).is_file())
                self.assertEqual(tray.card_count(), 0)
                tray.recycle_capture(path)
                self.assertFalse(Path(path).is_file())
                self.assertFalse(meta.is_file())
                self.assertFalse(any(library_dir().glob("keep*")))
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_pinned_capture_survives_retention(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                from recents import library_dir, purge_expired
                folder = library_dir()
                old = time.time() - 10 * 86400
                for name, pinned in (("pinned", True), ("loose", False)):
                    image = folder / f"{name}.png"
                    Image.new("RGB", (4, 4), "red").save(image)
                    (folder / f"{name}.json").write_text(json.dumps({
                        "title": name, "pinned": pinned, "path": str(image), "created": old,
                    }), encoding="utf-8")
                (folder / "escape.json").write_text(json.dumps({
                    "title": "out", "pinned": False, "path": str(Path(tmp) / "outside.png"), "created": old,
                }), encoding="utf-8")
                Path(tmp, "outside.png").write_bytes(b"no")
                purge_expired(1)
                self.assertTrue((folder / "pinned.png").is_file())
                self.assertFalse((folder / "loose.png").is_file())
                self.assertTrue(Path(tmp, "outside.png").is_file())
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_save_clears_the_dirty_flag(self):
        window = editor.EditorWindow(Image.new("RGB", (20, 12), "white"))
        self.addCleanup(window.close)
        window._prompt_on_close = False
        window._dirty = True
        original = editor.QFileDialog.getSaveFileName
        original_save = editor.QImage.save
        editor.QFileDialog.getSaveFileName = staticmethod(lambda *args: ("/tmp/prosnip-save.png", ""))
        editor.QImage.save = lambda self, *args, **kwargs: True
        try:
            self.assertTrue(window._save_png())
            self.assertFalse(window._dirty)
        finally:
            editor.QFileDialog.getSaveFileName = original
            editor.QImage.save = original_save

    def test_autosave_replaces_a_temp_file(self):
        import tempfile

        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                window = editor.EditorWindow(Image.new("RGB", (30, 16), "blue"))
                window._prompt_on_close = False
                window._scene.addItem(items.RectItem(QRectF(1, 1, 4, 4), QColor("#111"), QColor(0, 0, 0, 0), 1))
                window.autosave_active()
                path = Path(window._active_path)
                self.assertTrue(path.is_file())
                self.assertTrue(path.with_suffix(".psnip").is_file())
                self.assertFalse(Path(str(path) + ".tmp").exists())
                self.assertFalse(Path(str(path.with_suffix(".psnip")) + ".tmp").exists())
                window.close()
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_checkbox_indicator_is_visible_in_both_themes(self):
        from PyQt6.QtWidgets import QCheckBox
        from theme import apply_theme, colours_for, contrast_ratio

        for mode in ("light", "dark"):
            colours = colours_for(mode)
            indicator = QColor(colours["indicator"])
            self.assertGreaterEqual(contrast_ratio(indicator, QColor(colours["window"])), 3.0, mode)
            self.assertGreaterEqual(contrast_ratio(indicator, QColor(colours["panel"])), 3.0, mode)
            apply_theme(mode)
            box = QCheckBox("Shadow")
            box.setChecked(True)
            box.resize(120, 28)
            box.show()
            QApplication.processEvents()
            image = box.grab().toImage()
            self.assertTrue(_tick_on_indicator(image, indicator), mode)
            empty = QCheckBox("Curved")
            empty.setChecked(False)
            empty.resize(120, 28)
            empty.show()
            QApplication.processEvents()
            plain = empty.grab().toImage()
            self.assertFalse(_tick_on_indicator(plain, indicator), mode)
            box.deleteLater()
            empty.deleteLater()


def _tick_on_indicator(image: QImage, indicator: QColor) -> bool:
    """A white tick drawn on the indicator fill, not a white panel."""
    width, height = image.width(), image.height()

    def close(colour: QColor, target: QColor, tol: int = 28) -> bool:
        return (
            abs(colour.red() - target.red()) <= tol
            and abs(colour.green() - target.green()) <= tol
            and abs(colour.blue() - target.blue()) <= tol
        )

    for y in range(1, height - 1):
        for x in range(1, width - 1):
            colour = image.pixelColor(x, y)
            if colour.red() < 230 or colour.green() < 230 or colour.blue() < 230:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if close(image.pixelColor(x + dx, y + dy), indicator):
                    return True
    return False


class Quality184Tests(unittest.TestCase):
    def test_footer_follows_the_capture_that_is_open(self):
        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                window = editor.EditorWindow(Image.new("RGB", (150, 100), "white"))
                window._prompt_on_close = False
                small = window._active_path
                window.receive_capture(Image.new("RGB", (640, 480), "blue"), "large")
                self.assertEqual(window._footer_size.text(), "640 × 480 px")
                window._open_recent(small)
                self.assertEqual(window._footer_size.text(), "150 × 100 px")
                window.close()
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_crop_drops_annotations_outside_the_new_picture(self):
        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["LOCALAPPDATA"] = tmp
                window = editor.EditorWindow(Image.new("RGB", (200, 100), "white"))
                window._prompt_on_close = False
                pix = QPixmap(16, 12)
                pix.fill(QColor("#ff00ff"))
                overlay = items.ImageOverlayItem(pix, QPointF(-40, 10))
                window._scene.addItem(overlay)
                window._on_crop_requested(QRectF(20, 0, 120, 80))
                self.assertIsNone(overlay.scene())
                rendered = window._render_scene()
                seen = False
                for y in range(rendered.height()):
                    for x in range(rendered.width()):
                        pixel = rendered.pixelColor(x, y)
                        if pixel.red() > 200 and pixel.blue() > 200 and pixel.green() < 40:
                            seen = True
                self.assertFalse(seen)
                window.autosave_active()
                from persist import read_psnip
                saved = read_psnip(window._active_path)
                self.assertIsNotNone(saved)
                self.assertNotIn("ImageOverlayItem", [item.__class__.__name__ for item in saved[0]])
                window._scene.undo()
                self.assertIs(overlay.scene(), window._scene)
                window.close()
        finally:
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_edits_on_the_undo_stack_mark_the_document_dirty(self):
        window = editor.EditorWindow(Image.new("RGB", (80, 40), "white"))
        self.addCleanup(window.close)
        window._prompt_on_close = False
        rect = items.RectItem(QRectF(4, 4, 20, 12), QColor("#111111"), QColor(0, 0, 0, 0), 1)
        window._scene.addItem(rect)
        window._dirty = False
        window._scene.edit_style(rect, lambda: setattr(rect, "line_width", 6))
        self.assertTrue(window._dirty)
        window._dirty = False
        rect.setSelected(True)
        window._scene.delete_selected()
        self.assertTrue(window._dirty)
        window._dirty = False
        window._scene.undo()
        self.assertTrue(window._dirty)
        window._dirty = False
        window._scene._move_before = {id(rect): (rect, QPointF(rect.pos()))}
        rect.setPos(QPointF(12, 6))
        window._scene._finish_move()
        self.assertTrue(window._dirty)
        window._dirty = False
        window._scene.undo()
        self.assertTrue(window._dirty)

    def test_opacity_zero_and_strokes_round_trip(self):
        from persist import dump_item, load_item

        rect = items.RectItem(QRectF(0, 0, 8, 8), QColor("#111111"), QColor(0, 0, 0, 0), 1)
        rect.setOpacity(0)
        loaded = load_item(dump_item(rect))
        self.assertEqual(loaded.opacity(), 0)
        arrow = items.ArrowItem(QPointF(0, 0), QPointF(10, 4), QColor("#111111"), 2, "plain")
        arrow.stroke_enabled = False
        self.assertFalse(load_item(dump_item(arrow)).stroke_enabled)
        callout = items.CalloutItem(QPointF(0, 0), QColor("#111"), QColor("#fff"), QColor("#111"), 2, 12)
        callout.stroke_enabled = False
        self.assertFalse(load_item(dump_item(callout)).stroke_enabled)

    def test_psnip_hash_rejects_a_mismatched_picture(self):
        import persist

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shot.png"
            image = Image.new("RGB", (12, 8), "red")
            item = items.RectItem(QRectF(1, 1, 4, 4), QColor("#111"), QColor(0, 0, 0, 0), 1)
            order = []
            real = persist.os.replace

            def spy(src, dst):
                order.append(Path(dst).suffix)
                return real(src, dst)

            persist.os.replace = spy
            try:
                persist.write_psnip(str(path), [item], 1, image)
            finally:
                persist.os.replace = real
            self.assertEqual(order, [".psnip", ".png"])
            Image.new("RGB", (12, 8), "blue").save(path)
            with self.assertLogs("prosnip", level="ERROR") as caught:
                self.assertIsNone(persist.read_psnip(str(path)))
            self.assertTrue(any("does not match" in line for line in caught.output))

    def test_failed_recycle_is_logged_and_linux_trash_uses_a_move(self):
        from recents import recycle_file

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gone.png"
            path.write_bytes(b"png")
            recycle_file(path)
            self.assertFalse(path.is_file())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stuck.png"
            path.write_bytes(b"png")
            import recents
            original = recents._windows_recycle if sys.platform == "win32" else recents._trash_move
            if sys.platform == "win32":
                recents._windows_recycle = lambda _path: False
            else:
                recents._trash_move = lambda _path: False
            try:
                with self.assertLogs("prosnip", level="ERROR") as caught:
                    self.assertFalse(recycle_file(path))
            finally:
                if sys.platform == "win32":
                    recents._windows_recycle = original
                else:
                    recents._trash_move = original
            self.assertTrue(any("Could not recycle" in line for line in caught.output))
            self.assertTrue(path.is_file())

    def test_shift_zero_and_alt_zero_fit_the_view(self):
        window = editor.EditorWindow(Image.new("RGB", (400, 300), "white"))
        self.addCleanup(window.close)
        window._prompt_on_close = False
        window.show()
        window._view.setFocus()
        window._view.scale(2, 2)
        window._view.keyPressEvent(QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_ParenRight,
            Qt.KeyboardModifier.ControlModifier,
        ))
        self.assertLess(window._view.transform().m11(), 1.5)
        window._view.scale(3, 3)
        window._view.keyPressEvent(QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_0,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        ))
        self.assertLess(window._view.transform().m11(), 2.0)
        self.assertTrue(any("Ctrl+Alt+0" in action.text() for action in window._view_menu.actions()))


class Quality185Tests(unittest.TestCase):
    def test_tool_defaults_round_trip_for_every_tool(self):
        from colour import ColourHistory
        from tool_defaults import NAMES, builtin

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            history = ColourHistory(path)
            for tool in NAMES:
                values = builtin(tool)
                values["colour"] = "#112233"
                values["width"] = 9
                history.set_tool_default(tool, values)
            again = ColourHistory(path)
            for tool in NAMES:
                saved = again.tool_default(tool)
                self.assertIsNotNone(saved)
                self.assertEqual(saved["colour"], "#112233")
                self.assertEqual(saved["width"], 9)
            again.reset_tool_default("rect")
            self.assertIsNone(ColourHistory(path).tool_default("rect"))
            self.assertEqual(ColourHistory(path).tool_default("pen")["width"], 9)

    def test_corrupt_settings_fall_back_to_built_ins(self):
        from colour import ColourHistory

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"tool_defaults": "nope", "theme": "dark"}', encoding="utf-8")
            with self.assertLogs("prosnip", level="WARNING") as caught:
                history = ColourHistory(path)
            self.assertTrue(any("damaged" in line for line in caught.output))
            self.assertIsNone(history.tool_default("rect"))
            self.assertEqual(history.theme, "dark")
            path.write_text("{", encoding="utf-8")
            with self.assertLogs("prosnip", level="WARNING"):
                blank = ColourHistory(path)
            self.assertEqual(blank.theme, "system")
            self.assertIsNone(blank.tool_default("arrow"))

    def test_a_new_editor_loads_the_saved_tool_default(self):
        previous = os.environ.get("APPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["APPDATA"] = tmp
                window = editor.EditorWindow(Image.new("RGB", (80, 40), "white"))
                window._prompt_on_close = False
                window._on_tool_changed("rect")
                window._options._width.setValue(9)
                window._options.set_border_colour(QColor("#112233"))
                window._options._save_default()
                self.assertIn("Rectangle", window.statusBar().currentMessage())
                self.assertIsNotNone(window._options.findChild(QWidget, "SetDefault"))
                self.assertIsNotNone(window._options.findChild(QWidget, "ResetDefault"))
                window.close()
                again = editor.EditorWindow(Image.new("RGB", (80, 40), "white"))
                again._prompt_on_close = False
                again._on_tool_changed("rect")
                self.assertEqual(again._scene.line_width, 9)
                self.assertEqual(again._scene.pen_color.name().lower(), "#112233")
                again._options._reset_default()
                self.assertEqual(again._scene.line_width, 2)
                again.close()
        finally:
            if previous is None:
                os.environ.pop("APPDATA", None)
            else:
                os.environ["APPDATA"] = previous

    def test_installed_copy_logs_under_local_app_data(self):
        old_executable = sys.executable
        had_frozen = hasattr(sys, "frozen")
        old_frozen = getattr(sys, "frozen", None)
        previous = os.environ.get("LOCALAPPDATA")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                exe_dir = root / "Program Files" / "ProSnip-Bob"
                exe_dir.mkdir(parents=True)
                exe = exe_dir / "ProSnip-Bob.exe"
                exe.write_bytes(b"")
                (exe_dir / "installed.txt").write_text("ProSnip-Bob", encoding="utf-8")
                local = root / "local"
                os.environ["LOCALAPPDATA"] = str(local)
                sys.frozen = True
                sys.executable = str(exe)
                self.assertEqual(main.candidate_log_directories(), [local / "ProSnip-Bob"])
        finally:
            sys.executable = old_executable
            if had_frozen:
                sys.frozen = old_frozen
            elif hasattr(sys, "frozen"):
                delattr(sys, "frozen")
            if previous is None:
                os.environ.pop("LOCALAPPDATA", None)
            else:
                os.environ["LOCALAPPDATA"] = previous

    def test_start_line_records_the_log_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ProSnip-Bob.log"
            original = main.resolve_log_path
            previous = main._log_handle
            main.resolve_log_path = lambda directories=None: path
            try:
                main._mark_session_start()
                text = path.read_text(encoding="utf-8")
                self.assertIn(f"START {editor.APP_VERSION} log={path}", text)
                main._mark_clean_exit()
            finally:
                handle = main._log_handle
                if handle is not None and handle is not previous:
                    handle.close()
                main._log_handle = previous
                main.resolve_log_path = original


if __name__ == "__main__":
    unittest.main()
