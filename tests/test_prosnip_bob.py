"""Checks for the multi-monitor crop and the review fixes.

Real monitors are not available here. The geometry tests lock the mapping
that keeps a per-monitor, widget-local selection aligned with the grab,
including a 150% scale factor and a monitor that lives at a negative origin.
"""

import ctypes
import logging
import os
import queue
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from PIL import Image

import canvas
import capture
import editor
import hotkey
import instance
import items
import main
import main_window
import toolbar


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
        self.assertEqual(editor.APP_VERSION, "1.5.0.0")
        self.assertEqual(window.new_capture_button.text(), "New Capture")
        self.assertEqual(window.quit_button.text(), "Quit")
        self.assertIn("this system", window.shortcut_label.text())
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

    def test_editors_stay_alive_until_they_are_closed(self):
        host = main.ProSnipApp()
        self.addCleanup(_release_host, host)
        image = Image.new("RGB", (30, 20), "blue")
        host._capture_pending = True
        host._on_capture_done(image)
        host._capture_pending = True
        host._on_capture_done(image)
        self.assertEqual(len(host._editors), 2)
        self.assertIsNot(host._editors[0], host._editors[1])
        self.assertTrue(host._editors[0].isVisible())
        self.assertTrue(host._editors[1].isVisible())

        first = host._editors[0]
        first.close()
        QTest.qWait(50)
        self.assertEqual(len(host._editors), 1)
        self.assertIsNot(host._editors[0], first)

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
        version = (ROOT / "version_info.txt").read_text(encoding="utf-8")
        command = (
            "pyinstaller --noconfirm --clean --onedir --windowed --noupx "
            "--name ProSnip-Bob --exclude-module tkinter "
            "--version-file version_info.txt src/main.py"
        )
        self.assertIn(command, build)
        self.assertIn(command, workflow)
        self.assertIn(command, readme)
        self.assertNotIn("--onefile", build)
        self.assertNotIn("--onefile", workflow)
        self.assertIn("src/editor.py", workflow)
        self.assertIn("APP_VERSION", workflow)
        self.assertIn("steps.version.outputs.name", workflow)
        self.assertIn("ProSnip-Bob-$version-win64", workflow)
        self.assertNotIn("dist/ProSnip-Bob.zip", workflow)
        self.assertNotIn("name: ProSnip-Bob", workflow)
        self.assertIn("prosnip-bob", workflow)
        self.assertIn("python-version: \"3.12\"", workflow)
        self.assertIn("QT_QPA_PLATFORM: offscreen", workflow)
        self.assertIn("colour_picker, main", workflow)
        self.assertNotIn("imageio_ffmpeg", workflow)
        self.assertNotIn("recorder", workflow)
        for text in (
            "Steve Maz",
            "ProSnip-Bob",
            "ProSnip-Bob screen capture and annotation tool",
            "1.5.0.0",
            "(1, 5, 0, 0)",
            "ProSnip-Bob.exe",
            "Copyright (C) 2026 Steve Maz",
        ):
            self.assertIn(text, version)

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
        bar = toolbar.ToolBar()
        arrow = bar._tool_buttons["arrow"]
        pen = bar._tool_buttons["pen"]
        self.assertEqual(arrow.text(), "")
        self.assertEqual(pen.text(), "")
        self.assertEqual(arrow.toolTip(), "Arrow (A)")
        self.assertEqual(pen.toolTip(), "Pen (P)")
        self.assertEqual(bar._tool_buttons["highlight"].toolTip(), "Highlighter (H)")
        self.assertIn("QToolTip", bar.styleSheet())
        self.assertIn("font-size: 12pt", bar.styleSheet())
        self.assertIn("color: #ffffff", bar.styleSheet())

    def test_style_menu_shows_swatches_and_light_text(self):
        from PyQt6.QtGui import QPalette
        from styles import STYLES, colour_swatch

        bar = toolbar.ToolBar()
        combo = bar._style_combo
        self.assertEqual(combo.count(), len(STYLES))
        for index in range(combo.count()):
            self.assertFalse(combo.itemIcon(index).isNull())
        swatch = colour_swatch(QColor("#e63946"), 16).toImage()
        self.assertEqual(swatch.pixelColor(8, 8).name(), "#e63946")
        self.assertEqual(swatch.pixelColor(1, 1).name(), "#f2f2f2")
        text = combo.view().palette().color(QPalette.ColorRole.Text)
        self.assertGreater(text.lightness(), 180)
        self.assertGreaterEqual(combo.view().minimumWidth(), 200)

    def test_selected_style_sets_the_pen_colour(self):
        from styles import STYLES

        scene = canvas.ProSnipScene()
        bar = toolbar.ToolBar()
        bar.style_changed.connect(lambda style: scene.set_pen_color(style.pen_color))
        bar._style_combo.setCurrentText("Blue")
        self.assertEqual(scene._pen_color.name(), STYLES["Blue"].pen_color.name())

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
        bar = toolbar.ToolBar()
        picker = bar._tool_buttons["screenpick"]
        self.assertEqual(picker.iconSize(), QSize(40, 40))
        self.assertEqual(picker.toolTip(), "Colour picker (I)")
        self.assertIn("QToolTip", bar.styleSheet())
        self.assertEqual(bar._format_combo.currentData(), "hex")


if __name__ == "__main__":
    unittest.main()
