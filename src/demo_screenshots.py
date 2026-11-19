"""Opt-in screenshots of the real windows. Only runs with --demo-screenshots.

Normal launches never import this behaviour. The grabs are QWidget.grab()
of the same widgets the app shows.
"""

import logging
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QGuiApplication, QPen
from PyQt6.QtWidgets import QApplication

log = logging.getLogger("prosnip.demo")
# Screenshot grabs follow the editor shell: toolbar, sidebar and tray.


def demo_output_dir(argv: list[str]) -> Path | None:
    """Return the output folder when the flag is present, else None."""
    if "--demo-screenshots" not in argv:
        return None
    index = argv.index("--demo-screenshots")
    if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
        return Path(argv[index + 1])
    return Path("screenshots")


def capture_demo_screenshots(folder: Path) -> int:
    import faulthandler

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    fault_file = open(folder / "fault.log", "w", encoding="utf-8")
    faulthandler.enable(fault_file, all_threads=True)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    saved: list[Path] = []
    try:
        log.info("demo: main window")
        saved.append(_main_window(folder))
        log.info("demo: editor")
        editor = _editor_window()
        editor.show()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        editor._place_tools()
        editor.assert_tools_left_of_canvas()
        log.info(
            "Tool panel x=%s canvas x=%s panel=%sx%s tools=%s",
            editor._bar.mapTo(editor, editor._bar.rect().topLeft()).y(),
            editor._view.mapTo(editor, editor._view.rect().topLeft()).y(),
            editor._bar.width(),
            editor._bar.height(),
            len(editor._bar._buttons),
        )
        saved.append(_grab(editor, folder / "02-editor.png"))
        saved.append(_colour_menu(editor, folder / "03-colour-dropdown.png"))
        saved.append(_arrow_presets(folder / "06-arrow-presets.png"))
        saved.append(_properties_panel(editor, folder / "07-properties.png"))
        saved.append(_stamp_picker(folder / "08-stamp-picker.png"))
        saved.append(_text_background(folder / "09-text-background.png"))
        saved.append(_image_placeholder(editor, folder / "10-image-placeholder.png"))
        saved.append(_toolbar_tooltip(editor, folder / "11-toolbar-tooltip.png"))
        saved.append(_grab(editor._bar, folder / "12-toolbar.png"))
        saved.append(_picker_loupe(folder / "13-picker-loupe.png"))
        saved.append(_small_editor(folder / "14-editor-small.png"))
        saved.append(_colour_card(folder / "15-colour-card.png"))
        saved.append(_swatches(folder / "16-swatches.png"))
        saved.append(_no_trails(folder / "17-no-trails.png"))
        saved.append(_steps_editor(editor, folder / "18-steps.png"))
        saved.append(_file_menu(editor, folder / "19-file-menu.png"))
        saved.append(_step_properties(editor, folder / "20-step-properties.png"))
        saved.append(_sized_editor(folder / "21-editor-1024.png", 1024, 680, select_step=True))
        saved.append(_colour_popup(folder / "22-colour-popup.png"))
        saved.append(_arrange_menu(folder / "23-arrange-menu.png"))
        saved.append(_sized_editor(folder / "24-editor-1920.png", 1920, 1080, select_step=False))
        saved.append(_shape_options(folder / "25-shape-options.png"))
        saved.append(_transparent_popup(folder / "26-transparent-popup.png"))
        saved.append(_shape_fills(folder / "27-shape-fills.png"))
        saved.append(_editor_theme(folder / "30-editor-1024-light.png", 1024, 680, "light"))
        saved.append(_editor_theme(folder / "31-editor-1024-dark.png", 1024, 680, "dark"))
        saved.append(_editor_theme(folder / "32-editor-1920-light.png", 1920, 1080, "light"))
        saved.append(_editor_theme(folder / "33-editor-1920-dark.png", 1920, 1080, "dark"))
        saved.append(_more_menu(folder / "34-more-menu.png"))
        saved.append(_sidebar_tool(folder / "35-sidebar-arrow.png", "arrow"))
        saved.append(_sidebar_tool(folder / "36-sidebar-callout.png", "callout"))
        saved.append(_sidebar_tool(folder / "39-sidebar-shape.png", "rect"))
        saved.append(_sidebar_tool(folder / "40-sidebar-step.png", "number"))
        saved.append(_recent_tray(folder / "37-recents-tray.png"))
        saved.append(_canvas_demo(folder / "38-canvas-demo.png"))
        _assert_sizes()
        editor.close()
    except Exception:
        log.exception("Demo screenshots failed")
        return 1
    missing = [path.name for path in saved if not path.is_file() or path.stat().st_size < 200]
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
    window.resize(1280, 860)
    window._place_tools()
    window._on_tool_changed("pen")
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
    window._on_tool_changed("pen")
    return window


def _colour_menu(editor, path: Path) -> Path:
    menu = editor._options.open_colour_menu()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    menu.adjustSize()
    try:
        return _grab(menu, path)
    finally:
        menu.close()


def _arrow_presets(path: Path) -> Path:
    from items import ARROW_STYLES, ArrowItem
    from PyQt6.QtWidgets import QGraphicsScene, QGraphicsView

    scene = QGraphicsScene()
    scene.setSceneRect(0, 0, 420, 460)
    scene.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
    y = 36
    for style in ARROW_STYLES:
        item = ArrowItem(QPointF(24, y), QPointF(300, y), QColor("#e63946"), 8, style)
        scene.addItem(item)
        y += 72
    view = QGraphicsView(scene)
    view.setFrameShape(QGraphicsView.Shape.NoFrame)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    view.resize(420, 460)
    return _grab(view, path)


def _properties_panel(editor, path: Path) -> Path:
    strokes = [item for item in editor._scene.items() if item.__class__.__name__ == "StrokeItem"]
    if strokes:
        strokes[0].setSelected(True)
    editor._options.refresh()
    return _grab(editor, path)


def _stamp_picker(path: Path) -> Path:
    from stamp_picker import StampPickerDialog

    dialog = StampPickerDialog()
    try:
        return _grab(dialog, path)
    finally:
        dialog.close()


def _text_background(path: Path) -> Path:
    from editor import EditorWindow
    from items import TextItem

    window = EditorWindow(_sample_image())
    window.resize(900, 520)
    text = TextItem("Label", QPointF(80, 120), QColor("#ffffff"), 28)
    text.bg_color = QColor(29, 53, 87, 220)
    text.outline_enabled = True
    text.outline_color = QColor("#f4a261")
    text.outline_width = 3
    window._scene.addItem(text)
    text.setSelected(True)
    try:
        return _grab(window, path)
    finally:
        window.close()


def _image_placeholder(editor, path: Path) -> Path:
    from PyQt6.QtWidgets import QGraphicsRectItem
    from PyQt6.QtGui import QPen, QBrush

    for item in editor._scene.selectedItems():
        item.setSelected(False)
    frame = QGraphicsRectItem(QRectF(500, 300, 240, 140))
    frame.setPen(QPen(QColor("#e63946"), 3, Qt.PenStyle.DashLine))
    frame.setBrush(QBrush(QColor(230, 57, 70, 50)))
    editor._scene.addItem(frame)
    try:
        return _grab(editor, path)
    finally:
        editor._scene.removeItem(frame)


def _toolbar_tooltip(editor, path: Path) -> Path:
    from PyQt6.QtWidgets import QToolTip

    button = editor._bar.button("arrow")
    if button is None:
        editor._on_tool_changed("arrow")
        button = editor._bar.button("arrow")
    editor.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    anchor = button.mapToGlobal(QPoint(button.width() // 2, button.height() // 2))
    QToolTip.showText(anchor, button.toolTip(), button, button.rect(), 30000)
    if app is not None:
        app.processEvents()
    tip = None
    for widget in QApplication.topLevelWidgets():
        if widget.isVisible() and widget.windowType() == Qt.WindowType.ToolTip:
            tip = widget
            break
    if tip is None:
        raise RuntimeError("The Arrow tooltip did not appear")
    grabbed = _grab(tip, path)
    if tip.height() > 160:
        raise RuntimeError(f"Tooltip grab is the wrong window ({tip.width()}x{tip.height()})")
    return grabbed


def _picker_loupe(path: Path) -> Path:
    from PyQt6.QtGui import QImage, QPainter, QPixmap

    from colour import ColourHistory
    from colour_picker import _PickerOverlay

    image = QImage(240, 160, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1a2b3c"))
    painter = QPainter(image)
    painter.fillRect(80, 40, 80, 80, QColor("#e63946"))
    painter.fillRect(120, 70, 40, 40, QColor("#f4a261"))
    painter.end()
    if QApplication.instance() is None:
        QApplication([])
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("No screen is available for the colour picker grab")

    class _Preview:
        def __init__(self):
            self.history = ColourHistory(path=path.with_suffix(".json"))
            self.history.format = "hex"
            self.history.zoom = 8
            self.history.colours = ["#E63946", "#1A2B3C", "#F4A261", "#1D3557"]

        def set_zoom(self, zoom):
            self.history.zoom = zoom

        def cycle_format(self):
            return None

        def finish(self, _hex_code):
            return None

    overlay = _PickerOverlay(_Preview(), screen, QPixmap.fromImage(image))
    overlay.resize(720, 460)
    overlay.set_sample_pixel(100, 80)
    try:
        return _grab(overlay, path)
    finally:
        overlay.close()


def _steps_editor(editor, path: Path) -> Path:
    from items import NumberItem

    for number, pos in ((1, (70, 90)), (2, (180, 160)), (3, (300, 220))):
        editor._scene.addItem(NumberItem(number, QPointF(*pos), QColor("#e63946")))
    editor._scene.sync_next_number()
    editor._refresh_status_tool()
    return _grab(editor, path)


def _file_menu(editor, path: Path) -> Path:
    menu = editor._file_menu
    menu.popup(editor.mapToGlobal(QPoint(8, editor.menuBar().height() + 4)))
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    try:
        return _grab(menu, path)
    finally:
        menu.close()


def _step_properties(editor, path: Path) -> Path:
    from items import NumberItem

    step = next(item for item in editor._scene.items() if isinstance(item, NumberItem))
    step.setSelected(True)
    editor._options.refresh()
    return _grab(editor, path)


def _present(window, width: int, height: int):
    window.resize(width, height)
    window.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    window._place_tools()
    window._view.fit_if_larger()
    if app is not None:
        app.processEvents()
    window.assert_compact_layout()


def _sized_editor(path: Path, width: int, height: int, select_step: bool) -> Path:
    from items import NumberItem

    window = _editor_window()
    for number, pos in ((1, (70, 90)), (2, (180, 160)), (3, (300, 220))):
        window._scene.addItem(NumberItem(number, QPointF(*pos), QColor("#e63946")))
    window._scene.sync_next_number()
    _present(window, width, height)
    if select_step:
        step = next(item for item in window._scene.items() if isinstance(item, NumberItem))
        step.setSelected(True)
        window._options.refresh()
    try:
        return _grab(window, path)
    finally:
        window.close()


def _colour_popup(path: Path) -> Path:
    window = _editor_window()
    _present(window, 1024, 680)
    menu = window._options.open_colour_menu()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    menu.adjustSize()
    try:
        return _grab(menu, path)
    finally:
        menu.close()
        window.close()


def _arrange_menu(path: Path) -> Path:
    window = _editor_window()
    _present(window, 1024, 680)
    menu = window._arrange_menu
    menu.popup(window.mapToGlobal(QPoint(180, window.menuBar().height() + 4)))
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    try:
        return _grab(menu, path)
    finally:
        menu.close()
        window.close()


def _shape_options(path: Path) -> Path:
    window = _editor_window()
    _present(window, 1024, 680)
    window._options.set_border_colour(QColor("#e63946"))
    window._options.set_fill_colour(QColor("#e63946"), transparent=True)
    window._on_tool_changed("rect")
    window._options.refresh()
    try:
        return _grab(window, path)
    finally:
        window.close()


def _transparent_popup(path: Path) -> Path:
    window = _editor_window()
    _present(window, 1024, 680)
    window._options.set_border_colour(QColor("#e63946"))
    window._options.set_fill_colour(QColor("#e63946"), transparent=True)
    window._on_tool_changed("rect")
    menu = window._options.open_colour_menu("fill")
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    menu.adjustSize()
    try:
        return _grab(menu, path)
    finally:
        menu.close()
        window.close()


def _shape_fills(path: Path) -> Path:
    from items import RectItem
    from options import _alpha

    window = _editor_window()
    _present(window, 1024, 680)
    window._scene.addItem(RectItem(
        QRectF(70, 110, 220, 130), QColor("#e63946"), QColor(0, 0, 0, 0), 4,
    ))
    window._scene.addItem(RectItem(
        QRectF(340, 110, 220, 130), QColor("#e63946"), QColor(230, 57, 70, _alpha(30)), 4,
    ))
    window._on_tool_changed("select")
    try:
        return _grab(window, path)
    finally:
        window.close()


def _editor_theme(path: Path, width: int, height: int, mode: str) -> Path:
    from theme import apply_theme

    window = _editor_window()
    window._theme = apply_theme(mode)
    window._apply_workspace()
    _present(window, width, height)
    try:
        return _grab(window, path)
    finally:
        window.close()


def _more_menu(path: Path) -> Path:
    window = _editor_window()
    _present(window, 1024, 680)
    menu = window._bar.more_menu
    menu.popup(window._bar._more.mapToGlobal(QPoint(0, window._bar._more.height())))
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    try:
        return _grab(menu, path)
    finally:
        menu.close()
        window.close()


def _sidebar_tool(path: Path, tool: str) -> Path:
    window = _editor_window()
    _present(window, 1024, 680)
    window._on_tool_changed(tool)
    try:
        return _grab(window._sidebar, path)
    finally:
        window.close()


def _recent_tray(path: Path) -> Path:
    from PIL import Image as PILImage

    window = _editor_window()
    _present(window, 1024, 680)
    for name, colour in (("one", "#d7e6f5"), ("two", "#fff7e8"), ("three", "#e8f5e9")):
        window._tray.remember(PILImage.new("RGB", (320, 180), colour), name)
    try:
        return _grab(window, path)
    finally:
        window.close()


def _canvas_demo(path: Path) -> Path:
    from items import ArrowItem, CalloutItem, NumberItem, StrokeItem

    window = _editor_window()
    _present(window, 1024, 680)
    window._scene.addItem(ArrowItem(QPointF(80, 120), QPointF(280, 180), QColor("#e00000"), 4))
    window._scene.addItem(CalloutItem(QPointF(320, 100), QColor("#3949ab"), QColor(255, 255, 255, 230), QColor("#1a1d21"), 2, 16))
    window._scene.addItem(NumberItem(1, QPointF(120, 220), QColor("#e00000")))
    window._scene.addItem(NumberItem(2, QPointF(200, 260), QColor("#e00000")))
    blur = StrokeItem(QColor("#f4a261"), 18, highlighter=True)
    blur.add_point(QPointF(80, 320))
    blur.add_point(QPointF(360, 340))
    window._scene.addItem(blur)
    try:
        return _grab(window, path)
    finally:
        window.close()


def _assert_sizes() -> None:
    window = _editor_window()
    try:
        for width, height in ((900, 600), (1024, 680), (1920, 1080)):
            _present(window, width, height)
            log.info("Layout %sx%s toolbar=%s sidebar=%s", width, height, window._bar.height(), window._sidebar.width())
    finally:
        window.close()


def _small_editor(path: Path) -> Path:
    from editor import EditorWindow

    window = EditorWindow(Image.new("RGB", (240, 140), "#d7e6f5"))
    _present(window, 900, 600)
    try:
        return _grab(window, path)
    finally:
        window.close()


def _colour_card(path: Path) -> Path:
    from colour_card import ColourCard

    card = ColourCard("#1A2B3C")
    try:
        return _grab(card, path)
    finally:
        card.close()


def _swatches(path: Path) -> Path:
    from swatches import SwatchBook, SwatchPanel

    book = SwatchBook(path.with_suffix(".json"))
    book.add("#E63946", "Red")
    book.add("#1A2B3C", "Ink")
    book.add("#F4A261", "Sand")
    panel = SwatchPanel(book, lambda _hex: None)
    panel.resize(280, 360)
    try:
        return _grab(panel, path)
    finally:
        panel.close()


def _no_trails(path: Path) -> Path:
    from editor import EditorWindow
    from items import CalloutItem

    window = EditorWindow(Image.new("RGB", (640, 360), "#1e1e1e"))
    callout = CalloutItem(QPointF(40, 40), QColor("#e63946"), QColor("#ffffff"), QColor("#111111"), 6, 16)
    window._scene.addItem(callout)
    for step in range(12):
        callout.setPos(80 + step * 18, 70 + step * 6)
        window._scene.update()
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
    try:
        return _grab(window._view, path)
    finally:
        window.close()
