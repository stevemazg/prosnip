from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QToolBar, QPushButton, QFileDialog, QDialog,
    QFormLayout, QSpinBox, QCheckBox, QDialogButtonBox,
    QGraphicsPixmapItem, QApplication, QLabel,
    QMessageBox, QLineEdit, QAbstractSpinBox,
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QEvent, QRect, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QKeySequence,
    QShortcut, QKeyEvent, QGuiApplication,
)

from canvas import ProSnipScene, ProSnipView
from colour import ColourHistory
from layout import fit_editor_frame
from options import ToolOptions
from swatches import SwatchBook
from toolbar import ToolBar
from styles import with_tooltip_style
from theme import apply_dark_theme

import io
import math
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps

APP_NAME = "ProSnip-Bob"
APP_VERSION = "1.7.1.0"


def clamp_crop_rect(rect: QRectF, width: int, height: int) -> QRect | None:
    """Intersect a crop with the image and return whole pixels inside it.

    A drag that starts outside the picture used to be passed straight to
    ``QPixmap.copy`` / ``Image.crop``, which then returned a null or shifted
    image. Partial pixels on the edge are kept.
    """
    if width < 1 or height < 1:
        return None
    clipped = rect.normalized().intersected(QRectF(0, 0, width, height))
    if clipped.isEmpty():
        return None
    left = max(0, math.floor(clipped.left()))
    top = max(0, math.floor(clipped.top()))
    right = min(width, math.ceil(clipped.right()))
    bottom = min(height, math.ceil(clipped.bottom()))
    if right <= left or bottom <= top:
        return None
    return QRect(int(left), int(top), int(right - left), int(bottom - top))


def _crop_pil(image: Image.Image, crop: QRect) -> Image.Image:
    left = max(0, min(crop.left(), image.width))
    top = max(0, min(crop.top(), image.height))
    right = max(left, min(crop.left() + crop.width(), image.width))
    bottom = max(top, min(crop.top() + crop.height(), image.height))
    if right <= left or bottom <= top:
        return image
    return image.crop((left, top, right, bottom))


def pil_to_qpixmap(pil_img: Image.Image) -> QPixmap:
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    data = buf.read()
    qimg = QImage.fromData(data)
    return QPixmap.fromImage(qimg)


class ResizeDialog(QDialog):
    def __init__(self, current_w: int, current_h: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resize Image")
        self.setModal(True)
        self._orig_w = current_w
        self._orig_h = current_h
        self._updating = False
        self._build_ui(current_w, current_h)

    def _build_ui(self, w, h):
        layout = QFormLayout(self)

        self._w_spin = QSpinBox()
        self._w_spin.setRange(1, 16000)
        self._w_spin.setValue(w)
        layout.addRow("Width (px):", self._w_spin)

        self._h_spin = QSpinBox()
        self._h_spin.setRange(1, 16000)
        self._h_spin.setValue(h)
        layout.addRow("Height (px):", self._h_spin)

        self._aspect_cb = QCheckBox("Maintain aspect ratio")
        self._aspect_cb.setChecked(True)
        layout.addRow(self._aspect_cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._w_spin.valueChanged.connect(self._on_w_changed)
        self._h_spin.valueChanged.connect(self._on_h_changed)

    def _on_w_changed(self, val):
        if self._updating or not self._aspect_cb.isChecked():
            return
        if self._orig_w <= 0:
            return
        self._updating = True
        self._h_spin.setValue(int(val * self._orig_h / self._orig_w))
        self._updating = False

    def _on_h_changed(self, val):
        if self._updating or not self._aspect_cb.isChecked():
            return
        if self._orig_h <= 0:
            return
        self._updating = True
        self._w_spin.setValue(int(val * self._orig_w / self._orig_h))
        self._updating = False

    def get_size(self):
        return self._w_spin.value(), self._h_spin.value()


class EditorWindow(QMainWindow):
    screen_pick_requested = pyqtSignal()
    new_capture_requested = pyqtSignal()

    def __init__(self, pil_image: Image.Image, parent=None):
        super().__init__(parent)
        self._pil_image = pil_image
        self._filename = None
        self._bg_item = None

        apply_dark_theme()
        self.setWindowTitle(f"{APP_NAME} — Untitled")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(with_tooltip_style("background-color: #2b2b2b;"))
        self._did_fit = False

        self._placing_tools = False
        self._scene = ProSnipScene()
        self._view = ProSnipView(self._scene)
        self._toolbar = ToolBar()

        self._history = ColourHistory()
        self._swatches = SwatchBook(self._history.path)
        self._setup_background()
        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()
        self.fit_to_screen()

    def _setup_background(self):
        pixmap = pil_to_qpixmap(self._pil_image)
        pixmap.setDevicePixelRatio(1.0)
        self._bg_item = QGraphicsPixmapItem(pixmap)
        self._bg_item.setZValue(-100)
        self._scene.addItem(self._bg_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

    def fit_to_screen(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(960, 640)
            return
        frame = fit_editor_frame(
            self._pil_image.width,
            self._pil_image.height,
            120,
            110,
            screen.availableGeometry(),
            screen.devicePixelRatio() or 1.0,
            minimum_w=self.minimumWidth(),
            minimum_h=self.minimumHeight(),
        )
        self.setGeometry(*frame)
        self._place_tools()

    def _setup_ui(self):
        self._build_menus()
        self._options = ToolOptions(self._history, self._swatches)
        self._options.bind(self._scene, self._toolbar)
        options = QToolBar("Tool options")
        options.setObjectName("ToolOptionsBar")
        options.setMovable(False)
        options.setFloatable(False)
        options.setFixedHeight(40)
        options.setMaximumHeight(48)
        options.addWidget(self._options)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, options)
        self._top_bar = options

        central = QWidget()
        central.setObjectName("EditorBody")
        central.setStyleSheet("QWidget#EditorBody { background: #323232; }")
        self.setCentralWidget(central)
        self._tool_host = QWidget()
        self._tool_host.setObjectName("ToolPanel")
        self._tool_host.setStyleSheet("QWidget#ToolPanel { background: #323232; }")
        host = QVBoxLayout(self._tool_host)
        host.setContentsMargins(0, 0, 0, 0)
        host.setSpacing(0)
        host.addWidget(self._toolbar, 0, Qt.AlignmentFlag.AlignTop)
        host.addStretch(1)
        self._view.setObjectName("EditorCanvas")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._tool_host, 0)
        row.addWidget(self._view, 1)
        self._place_tools()
        self._build_status()

    def showEvent(self, event):
        super().showEvent(event)
        self._place_tools()
        if not self._did_fit:
            self._did_fit = True
            self._view.fit_if_larger()

    def _build_menus(self):
        bar = self.menuBar()
        file_menu = bar.addMenu("File")
        self._file_menu = file_menu
        file_menu.addAction("New capture", self.new_capture_requested.emit)
        file_menu.addAction("Open…", self._open_image)
        self._btn_save_png = file_menu.addAction("Save PNG", self._save_png)
        self._btn_save_png.setToolTip("Save PNG (Ctrl+S)")
        file_menu.addAction("Save As JPG", self._save_jpg)
        self._btn_copy = file_menu.addAction("Copy", self._copy_clipboard)
        self._btn_copy.setText("Copy")
        self._btn_copy.setToolTip("Copy (Ctrl+C)")
        file_menu.addAction("Export…", self._save_png)
        file_menu.addSeparator()
        file_menu.addAction("Preferences…", self._preferences)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        edit = bar.addMenu("Edit")
        undo = edit.addAction("Undo")
        undo.setShortcut(QKeySequence.StandardKey.Undo)
        undo.triggered.connect(self._scene.undo)
        redo = edit.addAction("Redo")
        redo.setShortcut(QKeySequence.StandardKey.Redo)
        redo.triggered.connect(self._scene.redo)
        edit.addSeparator()
        edit.addAction("Cut", self._cut)
        edit.addAction("Copy", self._copy_clipboard)
        edit.addAction("Paste", self._scene.paste_clipboard)
        select_all = edit.addAction("Select all")
        select_all.setShortcut(QKeySequence("Ctrl+A"))
        select_all.triggered.connect(self._select_all)
        edit.addAction("Delete", self._on_delete_shortcut)
        edit.addAction("Delete all annotations", self._scene.delete_all_annotations)

        image = bar.addMenu("Image")
        image.addAction("Resize…", self._resize_image)
        image.addAction("Crop", lambda: self._select_tool("crop"))
        image.addAction("Rotate 90°", self._rotate_image)
        image.addAction("Flip horizontally", self._flip_image)
        image.addAction("Border", self._add_border)

        arrange = bar.addMenu("Arrange")
        arrange.addAction("Bring forward", self._scene.bring_forward)
        arrange.addAction("Send backward", self._scene.send_back)
        arrange.addAction("Bring to front", self._scene.bring_to_front)
        arrange.addAction("Send to back", self._scene.send_to_back)
        arrange.addAction("Lock item", self._scene.toggle_lock)
        arrange.addAction("Renumber steps", self._scene.renumber_steps)
        self._arrange_menu = arrange

        view = bar.addMenu("View")
        view.addAction("Zoom in", lambda: self._view.scale(1.15, 1.15))
        view.addAction("Zoom out", lambda: self._view.scale(1 / 1.15, 1 / 1.15))
        fit = view.addAction("Fit")
        fit.setShortcut(QKeySequence("Ctrl+0"))
        fit.triggered.connect(self._view.fit_scene)
        actual = view.addAction("100%")
        actual.setShortcut(QKeySequence("Ctrl+1"))
        actual.triggered.connect(self._view.resetTransform)
        self._view_menu = view

        help_menu = bar.addMenu("Help")
        help_menu.addAction("About ProSnip-Bob", self._about)

    def _build_status(self):
        status = self.statusBar()
        self._status_zoom = QLabel("100%")
        self._status_size = QLabel(f"{self._pil_image.width} × {self._pil_image.height}")
        self._status_pos = QLabel("x —  y —")
        self._status_tool = QLabel("Select")
        for label in (self._status_zoom, self._status_size, self._status_pos, self._status_tool):
            label.setObjectName("muted")
            status.addWidget(label)
        self._view.cursor_moved.connect(self._on_cursor)

    def _on_cursor(self, pos: QPointF):
        self._status_pos.setText(f"x {int(pos.x())}  y {int(pos.y())}")
        zoom = int(round(self._view.transform().m11() * 100))
        self._status_zoom.setText(f"{zoom}%")

    def _preferences(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        layout = QVBoxLayout(dialog)
        auto = QCheckBox("Copy the snip to the clipboard after a capture")
        auto.setChecked(self._history.auto_copy)
        layout.addWidget(auto)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._history.set_auto_copy(auto.isChecked())

    def _select_all(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            focus.selectAll()
            return
        if isinstance(focus, QAbstractSpinBox) and focus.lineEdit() is not None:
            focus.lineEdit().selectAll()
            return
        if self._view.is_text_editing():
            item = self._scene.focusItem()
            if item is not None and hasattr(item, "textCursor"):
                cursor = item.textCursor()
                cursor.select(cursor.SelectionType.Document)
                item.setTextCursor(cursor)
            return
        self._scene.select_all_annotations()

    def _cut(self):
        self._scene.copy_selected()
        self._scene.delete_selected()

    def _open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open image", self._history.last_folder,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        image = Image.open(path).convert("RGB")
        self._replace_pixmap(pil_to_qpixmap(image), image)
        self._history.set_last_folder(str(Path(path).parent))

    def _about(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME}\nVersion {APP_VERSION}\nScreen capture and annotation.",
        )

    def _place_tools(self):
        if getattr(self, "_top_bar", None) is not None:
            self._top_bar.setFixedHeight(40)
        central = self.centralWidget()
        available = central.height() if central is not None and central.height() > 80 else max(240, self.height() - 140)
        self._toolbar.arrange(available)
        if getattr(self, "_tool_host", None) is not None:
            self._tool_host.setFixedWidth(self._toolbar.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_placing_tools", False) or getattr(self, "_toolbar", None) is None:
            return
        self._placing_tools = True
        try:
            self._place_tools()
        finally:
            self._placing_tools = False

    def assert_tools_left_of_canvas(self) -> None:
        """Fail if the tools are not a left-hand column beside the canvas."""
        from PyQt6.QtWidgets import QScrollArea

        panel = self._toolbar
        view = self._view
        origin = panel.mapTo(self, panel.rect().topLeft())
        view_origin = view.mapTo(self, view.rect().topLeft())
        panel_rect = QRect(origin, panel.size())
        view_rect = QRect(view_origin, view.size())
        problems = []
        if panel.width() < 40 or panel.height() < 80:
            problems.append(f"tool panel is too small ({panel.width()}x{panel.height()})")
        if origin.x() >= view_origin.x():
            problems.append(f"tool panel x {origin.x()} is not left of the canvas x {view_origin.x()}")
        if panel_rect.intersects(view_rect):
            problems.append(f"tool panel {panel_rect.getRect()} overlaps the canvas {view_rect.getRect()}")
        if len(panel._tool_buttons) != 16:
            problems.append(f"expected 16 tools, found {len(panel._tool_buttons)}")
        for tool_id, button in panel._tool_buttons.items():
            if not button.isVisible():
                problems.append(f"{tool_id} is not visible")
            ancestor = button.parentWidget()
            while ancestor is not None:
                if isinstance(ancestor, QScrollArea):
                    problems.append(f"{tool_id} is inside a scroll area")
                    break
                ancestor = ancestor.parentWidget()
        if problems:
            raise RuntimeError("Editor tool layout failed: " + "; ".join(problems))

    def assert_compact_layout(self) -> None:
        """Fail when the simplified editor clips, overlaps, or grows a dock."""
        from PyQt6.QtWidgets import QDockWidget, QScrollArea

        problems = []
        if self.findChildren(QDockWidget):
            problems.append("a dock widget is still in the editor")
        options_h = self._top_bar.height() if self._top_bar is not None else 0
        if options_h > 48 or self._options.height() > 48:
            problems.append(
                f"tool options bar is {options_h}px (options widget {self._options.height()}px)"
            )
        window = self.rect()
        if len(self._toolbar._tool_buttons) != 16:
            problems.append(f"expected 16 tools, found {len(self._toolbar._tool_buttons)}")
        for tool_id, button in self._toolbar._tool_buttons.items():
            if not button.isVisible():
                problems.append(f"{tool_id} is hidden")
                continue
            top_left = button.mapTo(self, button.rect().topLeft())
            bottom_right = button.mapTo(self, button.rect().bottomRight())
            if not window.contains(top_left) or not window.contains(bottom_right):
                problems.append(
                    f"{tool_id} sits outside the window at {top_left.x()},{top_left.y()}"
                )
            ancestor = button.parentWidget()
            while ancestor is not None:
                if isinstance(ancestor, QScrollArea):
                    problems.append(f"{tool_id} is inside a scroll area")
                    break
                ancestor = ancestor.parentWidget()

        def area(widget):
            if widget is None or not widget.isVisible() or widget.height() < 8 or widget.width() < 8:
                return None
            return QRect(widget.mapTo(self, widget.rect().topLeft()), widget.size())

        named = [
            ("menu", self.menuBar()),
            ("options", self._top_bar),
            ("tools", self._tool_host),
            ("canvas", self._view),
            ("status", self.statusBar()),
        ]
        rects = [(name, area(widget)) for name, widget in named]
        rects = [(name, rect) for name, rect in rects if rect is not None]
        for index, (name, rect) in enumerate(rects):
            for other, other_rect in rects[index + 1:]:
                hit = rect.intersected(other_rect)
                if hit.width() > 3 and hit.height() > 3:
                    problems.append(f"{name} overlaps {other} by {hit.width()}x{hit.height()}")
        menu = self._options.build_colour_menu()
        layout = self._options.layout()
        if layout is not None:
            for index in range(layout.count()):
                item = layout.itemAt(index)
                if item is not None and item.widget() is menu:
                    problems.append("colour popup is inside the options bar")
        menu.popup(self.mapToGlobal(self.rect().center()))
        app = QApplication.instance()
        if app is not None:
            app.processEvents()
        if menu.window() is self:
            problems.append("colour popup is not a separate window")
        if not (menu.windowFlags() & Qt.WindowType.Popup):
            problems.append("colour popup is not a popup")
        menu.close()
        if self._top_bar.height() > 48:
            problems.append("opening the colour popup grew the options bar")
        try:
            self.assert_tools_left_of_canvas()
        except RuntimeError as exc:
            problems.append(str(exc))
        if problems:
            raise RuntimeError("Editor layout failed: " + "; ".join(problems))

    def _connect_signals(self):
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.pen_color_changed.connect(self._scene.set_pen_color)
        self._scene.colour_picked.connect(self._toolbar.set_pen_colour)
        self._toolbar.stamp_chosen.connect(self._scene.set_last_stamp)
        self._scene.crop_requested.connect(self._on_crop_requested)
        self._toolbar.screen_pick_requested.connect(self.screen_pick_requested.emit)
        self._options.screen_pick_requested.connect(self.screen_pick_requested.emit)
        self._scene.selectionChanged.connect(self._refresh_status_tool)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_png)
        QShortcut(QKeySequence("Ctrl+C"), self).activated.connect(self._copy_clipboard)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self).activated.connect(self._copy_clipboard)
        QShortcut(QKeySequence("Ctrl+V"), self).activated.connect(self._scene.paste_clipboard)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._scene.duplicate_selected)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._scene.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self._scene.redo)
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(self._view.fit_scene)
        QShortcut(QKeySequence("Ctrl+1"), self).activated.connect(self._view.resetTransform)
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(self._select_all)
        for key, tool in (
            ("V", "select"),
            ("A", "arrow"),
            ("T", "text"),
            ("P", "pen"),
            ("H", "highlight"),
            ("R", "rect"),
            ("E", "ellipse"),
            ("B", "blur"),
            ("N", "number"),
            ("C", "crop"),
            ("I", "screenpick"),
            ("X", "eraser"),
        ):
            QShortcut(QKeySequence(key), self).activated.connect(lambda tool=tool: self._select_tool(tool))
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self).activated.connect(self._on_delete_shortcut)
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self._on_tool_changed("select")
        )

    def _on_delete_shortcut(self):
        """Delete the selection, unless a text box is being edited.

        The window-level shortcut runs before the graphics view sees the key.
        While text is being edited, send Delete through to that text box
        instead of removing the item.
        """
        if self._view.is_text_editing():
            self._forward_edit_key(Qt.Key.Key_Delete)
            return
        self._scene.delete_selected()

    def _forward_edit_key(self, key: Qt.Key):
        item = self._scene.focusItem()
        if item is None:
            return
        self._scene.sendEvent(
            item,
            QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier),
        )

    def _select_tool(self, tool: str):
        if self._view.is_text_editing():
            return
        if tool == "screenpick":
            self.screen_pick_requested.emit()
            return
        self._on_tool_changed(tool)
        self._view.set_select_drag(tool == "select")
        self._refresh_status_tool()

    def _on_tool_changed(self, tool: str):
        self._scene.set_tool(tool)
        self._toolbar.set_tool(tool)
        self._options.refresh()
        self._refresh_status_tool()

    def _refresh_status_tool(self):
        if getattr(self, "_status_tool", None) is None:
            return
        names = {
            "select": "Select",
            "arrow": "Arrow",
            "rect": "Rectangle",
            "ellipse": "Ellipse",
            "pen": "Pen",
            "highlight": "Highlighter",
            "blur": "Blur",
            "number": "Numbered step",
            "text": "Text",
            "crop": "Crop",
            "eraser": "Eraser",
            "screenpick": "Colour picker",
        }
        self._status_tool.setText(names.get(self._scene._tool, self._scene._tool))

    def _render_scene(self) -> QImage:
        scene = self._scene
        rect = scene.sceneRect()
        img = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.white)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scene.render(painter, source=rect)
        painter.end()
        return img

    def _default_save_path(self, suffix: str) -> str:
        folder = self._history.last_folder or str(Path.home() / "Pictures")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(Path(folder) / f"ProSnip-Bob_{stamp}{suffix}")

    def _remember_save(self, path: str) -> None:
        self._filename = path
        self._history.set_last_folder(str(Path(path).parent))
        self.setWindowTitle(f"{APP_NAME} — {path}")

    def _save_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as PNG", self._filename or self._default_save_path(".png"),
            "PNG Images (*.png)"
        )
        if path:
            img = self._render_scene()
            img.save(path, "PNG")
            self._remember_save(path)

    def _save_jpg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as JPG", self._filename or self._default_save_path(".jpg"),
            "JPEG Images (*.jpg *.jpeg)"
        )
        if path:
            img = self._render_scene()
            img.save(path, "JPEG", 95)
            self._remember_save(path)

    def _copy_clipboard(self):
        selected = [item for item in self._scene.selectedItems() if item.parentItem() is None]
        if selected:
            self._scene.copy_selected()
            return
        img = self._render_scene()
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setImage(img)

    def _replace_pixmap(self, pixmap: QPixmap, image: Image.Image) -> None:
        pixmap.setDevicePixelRatio(1.0)
        self._bg_item.setPixmap(pixmap)
        self._bg_item.setPos(0, 0)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._pil_image = image
        self._scene.update()

    def _rotate_image(self):
        if self._bg_item is None:
            return
        turned = self._pil_image.transpose(Image.Transpose.ROTATE_90)
        self._replace_pixmap(pil_to_qpixmap(turned), turned)

    def _flip_image(self):
        if self._bg_item is None:
            return
        flipped = ImageOps.mirror(self._pil_image)
        self._replace_pixmap(pil_to_qpixmap(flipped), flipped)

    def _add_border(self):
        if self._bg_item is None:
            return
        bordered = ImageOps.expand(self._pil_image.convert("RGBA"), border=12, fill=(255, 255, 255, 255))
        shadowed = Image.new("RGBA", (bordered.width + 16, bordered.height + 16), (0, 0, 0, 0))
        shade = Image.new("RGBA", bordered.size, (0, 0, 0, 90))
        shadowed.paste(shade, (10, 10), shade)
        shadowed.paste(bordered, (0, 0), bordered)
        self._replace_pixmap(pil_to_qpixmap(shadowed.convert("RGB")), shadowed.convert("RGB"))

    def _resize_image(self):
        if self._bg_item is None:
            return
        px = self._bg_item.pixmap()
        dlg = ResizeDialog(px.width(), px.height(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_w, new_h = dlg.get_size()
            scaled = px.scaled(
                new_w, new_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._bg_item.setPixmap(scaled)
            self._scene.setSceneRect(QRectF(0, 0, new_w, new_h))
            # Update internal PIL image
            self._pil_image = self._pil_image.resize((new_w, new_h), Image.LANCZOS)

    def _on_crop_requested(self, rect: QRectF):
        if self._bg_item is None:
            return
        px = self._bg_item.pixmap()
        crop = clamp_crop_rect(rect, px.width(), px.height())
        if crop is None:
            return
        cropped_px = px.copy(crop)
        if cropped_px.isNull():
            return
        self._bg_item.setPixmap(cropped_px)
        self._bg_item.setPos(0, 0)
        self._scene.setSceneRect(QRectF(0, 0, crop.width(), crop.height()))
        # Child handles live in their parent's coordinates. Moving them as
        # well as the parent shifts them twice.
        for item in self._scene.items():
            if item is self._bg_item or item.parentItem() is not None:
                continue
            item.moveBy(-float(crop.left()), -float(crop.top()))
        self._pil_image = _crop_pil(self._pil_image, crop)
