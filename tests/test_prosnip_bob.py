"""Checks for the multi-monitor crop and the review fixes.

Real monitors are not available here. The geometry tests lock the mapping
that keeps a per-monitor, widget-local selection aligned with the grab,
including a 150% scale factor and a monitor that lives at a negative origin.
"""

import ctypes
import logging
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPixmap
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from PIL import Image

import capture
import editor
import hotkey
import items
import main


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
        self.assertEqual(window._btn_copy.toolTip(), "Copy to clipboard (Ctrl+Shift+C)")

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
        self.assertIn("dist/ProSnip-Bob.zip", workflow)
        self.assertIn("name: ProSnip-Bob", workflow)
        self.assertIn("prosnip-bob", workflow)
        self.assertIn("python-version: \"3.12\"", workflow)
        self.assertIn("QT_QPA_PLATFORM: offscreen", workflow)
        self.assertIn("hotkey, main", workflow)
        for text in (
            "Steve Maz",
            "ProSnip-Bob",
            "ProSnip-Bob screen capture and annotation tool",
            "1.1.0.0",
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


if __name__ == "__main__":
    unittest.main()
