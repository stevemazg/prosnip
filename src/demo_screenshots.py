"""Opt-in screenshots of the real windows. Only runs with --demo-screenshots.

Normal launches never import this behaviour. The grabs are QWidget.grab()
of the same widgets the app shows.
"""

import logging
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from PyQt6.QtCore import QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import QApplication

log = logging.getLogger("prosnip.demo")


def demo_output_dir(argv: list[str]) -> Path | None:
    """Return the output folder when the flag is present, else None."""
    if "--demo-screenshots" not in argv:
        return None
    index = argv.index("--demo-screenshots")
    if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
        return Path(argv[index + 1])
    return Path("screenshots")


def capture_demo_screenshots(folder: Path) -> int:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    saved: list[Path] = []
    try:
        saved.append(_main_window(folder))
        editor = _editor_window()
        saved.append(_grab(editor, folder / "02-editor.png"))
        saved.append(_colour_menu(editor, folder / "03-colour-dropdown.png"))
        editor.close()
        saved.append(_record_dialog(folder / "04-record-picker.png"))
        saved.append(_rec_control(folder / "05-rec-control.png"))
    except Exception:
        log.exception("Demo screenshots failed")
        return 1
    missing = [path.name for path in saved if not path.is_file() or path.stat().st_size < 1000]
    if missing:
        log.error("Screenshot files missing or empty: %s", ", ".join(missing))
        return 1
    log.info("Saved demo screenshots: %s", ", ".join(path.name for path in saved))
    return 0


def _grab(widget, path: Path) -> Path:
    app = QApplication.instance()
    widget.show()
    widget.raise_()
    widget.repaint()
    if app is not None:
        app.processEvents()
    widget.repaint()
    pixmap = widget.grab()
    if pixmap.isNull() or pixmap.width() < 40 or pixmap.height() < 40:
        raise RuntimeError(f"Could not grab {widget.windowTitle() or type(widget).__name__}")
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"Could not save {path}")
    log.info("Grabbed %s (%sx%s)", path.name, pixmap.width(), pixmap.height())
    return path


def _main_window(folder: Path) -> Path:
    from main_window import MainWindow

    window = MainWindow()
    window.set_shortcut_status(None)
    window.present()
    window.resize(420, 340)
    return _grab(window, folder / "01-main-window.png")


def _sample_image() -> Image.Image:
    image = Image.new("RGB", (960, 540), "#d7e6f5")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 959, 42), fill="#1d3557")
    draw.rectangle((36, 78, 430, 250), fill="#ffffff", outline="#c5d4e8")
    draw.rectangle((460, 78, 900, 250), fill="#fff7e8", outline="#f4a261")
    draw.rectangle((36, 290, 900, 470), fill="#ffffff", outline="#c5d4e8")
    return image


def _editor_window():
    from editor import EditorWindow
    from items import ArrowItem, StrokeItem, TextItem

    window = EditorWindow(_sample_image())
    window.resize(1100, 720)
    scene = window._scene
    pen = StrokeItem(QColor("#e63946"), 4)
    for point in ((90, 140), (180, 210), (280, 150), (390, 230)):
        pen.add_point(QPointF(*point))
    scene.addItem(pen)
    highlight = StrokeItem(QColor("#f4a261"), 18, highlighter=True)
    for point in ((70, 340), (420, 360)):
        highlight.add_point(QPointF(*point))
    scene.addItem(highlight)
    scene.addItem(ArrowItem(QPointF(500, 120), QPointF(760, 210), QColor("#1d3557"), 3))
    scene.addItem(TextItem("Reviewed", QPointF(520, 240), QColor("#e63946"), 20))
    window._toolbar.set_tool("pen")
    return window


def _colour_menu(editor, path: Path) -> Path:
    combo = editor._toolbar._style_combo
    combo.showPopup()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    view = combo.view()
    popup = view.window()
    if popup is not editor and popup.isVisible() and popup.width() >= 120:
        return _grab(popup, path)
    view.setMinimumWidth(240)
    row = max(24, view.sizeHintForRow(0))
    view.setFixedSize(240, row * combo.count() + 8)
    view.show()
    return _grab(view, path)


def _record_dialog(path: Path) -> Path:
    from recorder import RecordDialog

    dialog = RecordDialog("monitor")
    dialog.resize(480, 320)
    try:
        return _grab(dialog, path)
    finally:
        dialog.close()


def _rec_control(path: Path) -> Path:
    from recorder import GrabSource, ScreenRecorder, video_output_path

    screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No screen is available for the recording control")
    area = screen.geometry()
    source = GrabSource(screen, QRect(0, 0, min(320, area.width()), min(180, area.height())))
    out = video_output_path()
    recorder = ScreenRecorder(source, out, 15)
    try:
        import time

        recorder.start()
        # Grab the live control before a failed capture tick can hide it.
        recorder._timer.stop()
        shot = _grab(recorder._control, path)
        recorder._timer.start()
        app = QApplication.instance()
        if app is not None:
            deadline = time.time() + 1.2
            while time.time() < deadline and recorder.is_active:
                app.processEvents()
                time.sleep(0.05)
        if recorder.is_active:
            recorder.stop()
        return shot
    finally:
        if recorder.is_active:
            recorder.stop()
