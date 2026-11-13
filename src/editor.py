from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QToolBar, QPushButton, QFileDialog, QDialog,
    QFormLayout, QSpinBox, QCheckBox, QDialogButtonBox,
    QGraphicsPixmapItem, QApplication, QLabel, QSizePolicy,
    QScrollArea, QDockWidget,
)
from PyQt6.QtCore import Qt, QRectF, QEvent, QRect, pyqtSignal
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QKeySequence,
    QShortcut, QKeyEvent, QGuiApplication,
)

from canvas import ProSnipScene, ProSnipView
from colour import ColourHistory
from layout import fit_editor_frame
from properties import PropertiesPanel
from swatches import SwatchBook, SwatchPanel
from toolbar import ToolBar
from styles import QuickStyle, with_tooltip_style

import io
import math
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps

APP_NAME = "ProSnip-Bob"
APP_VERSION = "1.5.1.0"


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

    def __init__(self, pil_image: Image.Image, parent=None):
        super().__init__(parent)
        self._pil_image = pil_image
        self._filename = None
        self._bg_item = None

        self.setWindowTitle(f"{APP_NAME} — Untitled")
        # Wide enough for the top actions, tall enough for two tool columns.
        self.setMinimumSize(1080, 680)
        self.setStyleSheet(with_tooltip_style("background-color: #2b2b2b;"))

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
            400,
            56,
            screen.availableGeometry(),
            screen.devicePixelRatio() or 1.0,
            minimum_w=self.minimumWidth(),
            minimum_h=self.minimumHeight(),
        )
        self.setGeometry(*frame)
        self._place_tools()

    def _setup_ui(self):
        top_bar = QToolBar("Actions")
        top_bar.setMovable(False)
        top_bar.setStyleSheet(with_tooltip_style("""
            QToolBar { background: #1e1e1e; border: none; spacing: 4px; padding: 4px; }
            QPushButton {
                background: #2d2d2d; border: 1px solid #3d3d3d;
                color: #cccccc; border-radius: 4px;
                padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover { background: #3d3d3d; }
        """))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, top_bar)

        def _tb_btn(label, tooltip=""):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(30)
            return btn

        self._btn_save_png = _tb_btn("Save PNG", "Save PNG (Ctrl+S)")
        self._btn_save_jpg = _tb_btn("Save JPG", "Save JPG")
        self._btn_copy = _tb_btn("Copy", "Copy (Ctrl+C)")
        self._btn_resize = _tb_btn("Resize…", "Resize canvas")
        self._btn_rotate = _tb_btn("Rotate", "Rotate image 90°")
        self._btn_flip = _tb_btn("Flip", "Flip image horizontally")
        self._btn_border = _tb_btn("Border", "Add a border")
        self._btn_forward = _tb_btn("Forward", "Bring forward")
        self._btn_back = _tb_btn("Back", "Send back")
        self._btn_lock = _tb_btn("Lock", "Lock or unlock the selection")
        for btn in (
            self._btn_save_png, self._btn_save_jpg, self._btn_copy, self._btn_resize,
            self._btn_rotate, self._btn_flip, self._btn_border,
            self._btn_forward, self._btn_back, self._btn_lock,
        ):
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            top_bar.addWidget(btn)
        self._top_bar = top_bar

        central = QWidget()
        self.setCentralWidget(central)
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._toolbar, 0)
        row.addWidget(self._view, 1)

        self._properties = PropertiesPanel()
        self._properties.bind(self._scene, self._toolbar)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._toolbar.controls_panel)
        right_layout.addWidget(self._properties, 1)
        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._swatch_panel = SwatchPanel(self._swatches, self._apply_swatch)
        self._swatch_panel.setMinimumHeight(200)
        self._properties_dock = self._dock("Properties", right_scroll)
        self._swatch_dock = self._dock("Swatches", self._swatch_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._properties_dock)
        self.splitDockWidget(self._properties_dock, self._swatch_dock, Qt.Orientation.Vertical)
        self._place_tools()

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_properties_dock", None) is None:
            return
        height = max(1, self.height())
        self.resizeDocks(
            [self._properties_dock, self._swatch_dock],
            [int(height * 0.62), int(height * 0.28)],
            Qt.Orientation.Vertical,
        )

    def _place_tools(self):
        top = self._top_bar.height() if getattr(self, "_top_bar", None) is not None else 48
        self._toolbar.arrange(max(240, self.height() - top - 8))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_placing_tools", False) or getattr(self, "_toolbar", None) is None:
            return
        self._placing_tools = True
        try:
            self._place_tools()
        finally:
            self._placing_tools = False

    def _dock(self, title: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setFloating(False)
        return dock

    def _apply_swatch(self, hex_code: str):
        colour = QColor(hex_code)
        self._toolbar.set_pen_colour(colour)
        self._scene.set_pen_color(colour)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._history.display(hex_code))

    def _connect_signals(self):
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.style_changed.connect(self._on_style_changed)
        self._toolbar.pen_color_changed.connect(self._scene.set_pen_color)
        self._scene.colour_picked.connect(self._toolbar.set_pen_colour)
        self._scene.colour_picked.connect(lambda _colour: self._properties.refresh())
        self._toolbar.line_width_changed.connect(self._scene.set_line_width)
        self._toolbar.font_size_changed.connect(self._scene.set_font_size)
        self._toolbar.undo_requested.connect(self._scene.undo)
        self._toolbar.delete_requested.connect(self._scene.delete_selected)
        self._toolbar.stamp_chosen.connect(self._scene.set_last_stamp)
        self._scene.crop_requested.connect(self._on_crop_requested)
        self._btn_save_png.clicked.connect(self._save_png)
        self._btn_save_jpg.clicked.connect(self._save_jpg)
        self._btn_copy.clicked.connect(self._copy_clipboard)
        self._btn_resize.clicked.connect(self._resize_image)
        self._btn_rotate.clicked.connect(self._rotate_image)
        self._btn_flip.clicked.connect(self._flip_image)
        self._btn_border.clicked.connect(self._add_border)
        self._btn_forward.clicked.connect(self._scene.bring_forward)
        self._btn_back.clicked.connect(self._scene.send_back)
        self._btn_lock.clicked.connect(self._scene.toggle_lock)
        self._toolbar.screen_pick_requested.connect(self.screen_pick_requested.emit)

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

    def _on_tool_changed(self, tool: str):
        self._scene.set_tool(tool)
        self._toolbar.set_tool(tool)

    def _on_style_changed(self, style: QuickStyle):
        self._scene.set_pen_color(style.pen_color)
        self._scene.set_fill_color(style.fill_color)
        self._scene.set_text_color(style.text_color)
        self._scene.set_line_width(style.line_width)
        self._scene.set_font_size(style.font_size)

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
