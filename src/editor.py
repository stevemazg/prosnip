from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QToolBar, QPushButton, QFileDialog, QDialog,
    QFormLayout, QSpinBox, QCheckBox, QDialogButtonBox,
    QGraphicsPixmapItem, QApplication, QLabel
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QColor, QKeySequence,
    QShortcut
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSize

from canvas import ProSnipScene, ProSnipView
from toolbar import ToolBar
from styles import QuickStyle

import io
from PIL import Image


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
    def __init__(self, pil_image: Image.Image, parent=None):
        super().__init__(parent)
        self._pil_image = pil_image
        self._filename = None
        self._bg_item = None

        self.setWindowTitle("ProSnip — Untitled")
        self.setMinimumSize(900, 600)
        self.setStyleSheet("background-color: #2b2b2b;")

        self._scene = ProSnipScene()
        self._view = ProSnipView(self._scene)
        self._toolbar = ToolBar()

        self._setup_background()
        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

    def _setup_background(self):
        pixmap = pil_to_qpixmap(self._pil_image)
        self._bg_item = QGraphicsPixmapItem(pixmap)
        self._bg_item.setZValue(-100)
        self._scene.addItem(self._bg_item)
        self._scene.setSceneRect(QRectF(pixmap.rect()))

    def _setup_ui(self):
        # Top action toolbar
        top_bar = QToolBar("Actions")
        top_bar.setMovable(False)
        top_bar.setStyleSheet("""
            QToolBar { background: #1e1e1e; border: none; spacing: 4px; padding: 4px; }
            QPushButton {
                background: #2d2d2d; border: 1px solid #3d3d3d;
                color: #cccccc; border-radius: 4px;
                padding: 4px 10px; font-size: 12px;
            }
            QPushButton:hover { background: #3d3d3d; }
        """)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, top_bar)

        def _tb_btn(label, tooltip=""):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(30)
            return btn

        self._btn_save_png = _tb_btn("Save PNG", "Save as PNG (Ctrl+S)")
        self._btn_save_jpg = _tb_btn("Save JPG", "Save as JPG")
        self._btn_copy = _tb_btn("Copy", "Copy to clipboard (Ctrl+C)")
        self._btn_resize = _tb_btn("Resize…", "Resize canvas")

        for btn in [self._btn_save_png, self._btn_save_jpg, self._btn_copy, self._btn_resize]:
            top_bar.addWidget(btn)

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        hlayout = QHBoxLayout(central)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.setSpacing(0)
        hlayout.addWidget(self._toolbar)
        hlayout.addWidget(self._view, 1)

    def _connect_signals(self):
        self._toolbar.tool_changed.connect(self._on_tool_changed)
        self._toolbar.style_changed.connect(self._on_style_changed)
        self._toolbar.pen_color_changed.connect(self._scene.set_pen_color)
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

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self._save_png)
        QShortcut(QKeySequence("Ctrl+Shift+C"), self).activated.connect(self._copy_clipboard)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._scene.undo)
        QShortcut(QKeySequence("Delete"), self).activated.connect(self._scene.delete_selected)
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self._on_tool_changed("select")
        )

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

    def _save_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as PNG", self._filename or "screenshot.png",
            "PNG Images (*.png)"
        )
        if path:
            img = self._render_scene()
            img.save(path, "PNG")
            self._filename = path
            self.setWindowTitle(f"ProSnip — {path}")

    def _save_jpg(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as JPG", self._filename or "screenshot.jpg",
            "JPEG Images (*.jpg *.jpeg)"
        )
        if path:
            img = self._render_scene()
            img.save(path, "JPEG", 95)
            self._filename = path
            self.setWindowTitle(f"ProSnip — {path}")

    def _copy_clipboard(self):
        img = self._render_scene()
        QApplication.clipboard().setImage(img)

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
        # Crop the pixmap
        cropped_px = px.copy(rect.toRect())
        self._bg_item.setPixmap(cropped_px)
        # Shift scene origin
        offset = rect.topLeft()
        self._bg_item.setPos(0, 0)
        self._scene.setSceneRect(QRectF(0, 0, rect.width(), rect.height()))
        # Shift all other items
        for item in self._scene.items():
            if item is self._bg_item:
                continue
            item.moveBy(-offset.x(), -offset.y())
        # Update PIL image
        self._pil_image = self._pil_image.crop((
            int(rect.left()), int(rect.top()),
            int(rect.right()), int(rect.bottom())
        ))
