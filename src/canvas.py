from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QGraphicsRectItem, QFileDialog, QWidget
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPixmap, QImage,
    QKeyEvent, QTransform
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QEvent, pyqtSignal

from items import (
    ArrowItem, TextItem, CalloutItem, StampItem,
    RectItem, EllipseItem, ImageOverlayItem, StrokeItem,
    item_is_text_editing,
)
from stamp_picker import StampPickerDialog
from styles import DEFAULT_STYLE


class ProSnipScene(QGraphicsScene):
    crop_requested = pyqtSignal(QRectF)
    tool_used = pyqtSignal(object)  # emits the new item added
    colour_picked = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tool = "select"
        self._current_item = None
        self._press_pos = QPointF()
        self._undo_stack = []
        self._redo_stack = []
        self._last_stamp = None
        self._crop_rect_item = None

        # Style params
        self._pen_color = DEFAULT_STYLE.pen_color
        self._fill_color = DEFAULT_STYLE.fill_color
        self._text_color = DEFAULT_STYLE.text_color
        self._line_width = DEFAULT_STYLE.line_width
        self._font_size = DEFAULT_STYLE.font_size
        self.arrow_style = "plain"
        self.item_opacity = 1.0
        self._image_rect_item = None

    def set_tool(self, tool: str):
        self._tool = tool

    def set_pen_color(self, color: QColor):
        self._pen_color = color

    def set_fill_color(self, color: QColor):
        self._fill_color = color

    def set_text_color(self, color: QColor):
        self._text_color = color

    def set_line_width(self, w: int):
        self._line_width = w

    def set_font_size(self, s: int):
        self._font_size = s

    @property
    def pen_color(self):
        return self._pen_color

    @property
    def line_width(self):
        return self._line_width

    @property
    def font_size(self):
        return self._font_size

    def _place(self, item):
        item.setOpacity(self.item_opacity)
        self.addItem(item)
        return item

    def sample_background(self, pos: QPointF) -> QColor | None:
        for item in self.items():
            if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0:
                local = item.mapFromScene(pos)
                image = item.pixmap().toImage()
                x, y = int(local.x()), int(local.y())
                if 0 <= x < image.width() and 0 <= y < image.height():
                    return image.pixelColor(x, y)
        return None

    def _finish_image_frame(self, frame: QRectF):
        if frame.width() < 8 or frame.height() < 8:
            return
        path, _ = QFileDialog.getOpenFileName(
            None, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.svg)",
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if path.lower().endswith(".svg"):
            pixmap = _svg_pixmap(path, int(frame.width()), int(frame.height()))
        if pixmap.isNull():
            return
        item = ImageOverlayItem(pixmap, frame.topLeft())
        item._set_rect(QRectF(0, 0, max(8, frame.width()), max(8, frame.height())))
        item.setOpacity(self.item_opacity)
        self.addItem(item)
        self._push_undo(item)
        self._tool = "select"

    def set_last_stamp(self, stamp: str):
        self._last_stamp = stamp

    def _push_undo(self, item):
        self._undo_stack.append(item)
        self._redo_stack.clear()
        self.tool_used.emit(item)

    def undo(self):
        if self._undo_stack:
            item = self._undo_stack.pop()
            self.removeItem(item)
            self._redo_stack.append(item)

    def redo(self):
        if self._redo_stack:
            item = self._redo_stack.pop()
            self.addItem(item)
            self._undo_stack.append(item)

    def delete_selected(self):
        for item in self.selectedItems():
            if item in self._undo_stack:
                self._undo_stack.remove(item)
            if item in self._redo_stack:
                self._redo_stack.remove(item)
            self.removeItem(item)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        pos = event.scenePos()
        self._press_pos = pos
        tool = self._tool

        if tool == "select":
            super().mousePressEvent(event)
            return

        if tool == "arrow":
            item = self._place(ArrowItem(
                pos, pos, self._pen_color, max(6, self._line_width), self.arrow_style,
            ))
            self._current_item = item
            event.accept()

        elif tool == "pick":
            colour = self.sample_background(pos)
            if colour is not None and colour.isValid():
                self.set_pen_color(colour)
                self.colour_picked.emit(colour)
            event.accept()

        elif tool in ("pen", "highlight"):
            item = self._place(StrokeItem(
                self._pen_color,
                self._line_width,
                highlighter=(tool == "highlight"),
            ))
            item.add_point(pos)
            self._current_item = item
            event.accept()

        elif tool == "text":
            item = TextItem("Text", pos, self._text_color, self._font_size)
            self.addItem(item)
            self._push_undo(item)
            self._current_item = None
            self._tool = "select"
            event.accept()

        elif tool == "callout":
            item = CalloutItem(pos, self._pen_color, self._fill_color,
                               self._text_color, self._line_width, self._font_size)
            self.addItem(item)
            self._current_item = item
            event.accept()

        elif tool == "stamp":
            stamp = self._last_stamp
            if stamp is None:
                stamp = StampPickerDialog.get_stamp()
                if stamp is None:
                    event.accept()
                    return
                self._last_stamp = stamp
            if stamp.startswith("image:"):
                pixmap = QPixmap(stamp[6:])
                if pixmap.isNull():
                    event.accept()
                    return
                item = ImageOverlayItem(pixmap, pos)
            else:
                item = StampItem(stamp, pos)
            item.setOpacity(self.item_opacity)
            self.addItem(item)
            self._push_undo(item)
            self._current_item = None
            self._tool = "select"
            event.accept()

        elif tool == "rect":
            item = RectItem(QRectF(pos, pos), self._pen_color, self._fill_color, self._line_width)
            self.addItem(item)
            self._current_item = item
            event.accept()

        elif tool == "ellipse":
            item = EllipseItem(QRectF(pos, pos), self._pen_color, self._fill_color, self._line_width)
            self.addItem(item)
            self._current_item = item
            event.accept()

        elif tool == "image":
            self._image_rect_item = QGraphicsRectItem(QRectF(pos, pos))
            self._image_rect_item.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine))
            self._image_rect_item.setBrush(QBrush(QColor(255, 255, 255, 40)))
            self.addItem(self._image_rect_item)
            event.accept()

        elif tool == "crop":
            self._crop_rect_item = QGraphicsRectItem(QRectF(pos, pos))
            pen = QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine)
            self._crop_rect_item.setPen(pen)
            self._crop_rect_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.addItem(self._crop_rect_item)
            event.accept()

        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.scenePos()
        tool = self._tool

        if tool == "select":
            super().mouseMoveEvent(event)
            return

        if self._current_item is not None:
            if tool == "arrow":
                item = self._current_item
                item.prepareGeometryChange()
                item.end = item.mapFromScene(pos)
                item._update_handles()
                item.update()

            elif tool in ("rect", "ellipse"):
                item = self._current_item
                r = QRectF(self._press_pos, pos).normalized()
                item.prepareGeometryChange()
                item._set_rect(r)
                item._update_handles()
                item.update()

            elif tool in ("pen", "highlight"):
                self._current_item.add_point(pos)
                return

            elif tool == "callout":
                item = self._current_item
                r = QRectF(self._press_pos, pos).normalized()
                if r.width() < 40:
                    r.setWidth(40)
                if r.height() < 30:
                    r.setHeight(30)
                item.set_rect(r)

        elif tool == "crop" and self._crop_rect_item is not None:
            r = QRectF(self._press_pos, pos).normalized()
            self._crop_rect_item.setRect(r)

        elif tool == "image" and self._image_rect_item is not None:
            self._image_rect_item.setRect(QRectF(self._press_pos, pos).normalized())

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        pos = event.scenePos()
        tool = self._tool

        if tool == "select":
            super().mouseReleaseEvent(event)
            return

        if self._current_item is not None:
            item = self._current_item
            self._push_undo(item)
            self._current_item = None
            if tool not in ("pen", "highlight"):
                self._tool = "select"
            return

        elif tool == "crop" and self._crop_rect_item is not None:
            r = self._crop_rect_item.rect()
            self.removeItem(self._crop_rect_item)
            self._crop_rect_item = None
            self._tool = "select"
            if r.width() > 4 and r.height() > 4:
                self.crop_requested.emit(r)
            return

        elif tool == "image" and self._image_rect_item is not None:
            frame = self._image_rect_item.rect().normalized()
            self.removeItem(self._image_rect_item)
            self._image_rect_item = None
            self._finish_image_frame(frame)
            return

        super().mouseReleaseEvent(event)


class _CanvasViewport(QWidget):
    """Accepts Delete and Backspace while a text box is being edited.

    Those keys are also window shortcuts. The shortcut map delivers
    ShortcutOverride to the focus widget first, which is this viewport.
    Accepting it lets the text box receive the key.
    """

    def __init__(self, view: "ProSnipView"):
        super().__init__(view)
        self._view = view

    def event(self, event):
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and self._view.is_text_editing()
            and _text_keeps_key(event)
        ):
            event.accept()
            return True
        return super().event(event)


class ProSnipView(QGraphicsView):
    def __init__(self, scene: ProSnipScene, parent=None):
        super().__init__(scene, parent)
        self.setViewport(_CanvasViewport(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setStyleSheet("background-color: #2b2b2b; border: none;")

    def is_text_editing(self) -> bool:
        scene = self.scene()
        if scene is None:
            return False
        return item_is_text_editing(scene.focusItem())

    def event(self, event):
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and self.is_text_editing()
            and _text_keeps_key(event)
        ):
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        scene = self.scene()
        editing = self.is_text_editing()
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if editing:
                super().keyPressEvent(event)
            else:
                scene.delete_selected()
            return
        if (
            not editing
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Z
        ):
            scene.undo()
            return
        if (
            not editing
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_Y
        ):
            scene.redo()
            return
        super().keyPressEvent(event)


def _svg_pixmap(path: str, width: int, height: int) -> QPixmap:
    try:
        from PyQt6.QtSvg import QSvgRenderer
    except ImportError:
        return QPixmap()
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return QPixmap()
    pixmap = QPixmap(max(8, width), max(8, height))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def _text_keeps_key(event) -> bool:
    """Keys the text editor must receive instead of a window shortcut."""
    key = event.key()
    mods = event.modifiers()
    if mods == Qt.KeyboardModifier.NoModifier and key in (
        Qt.Key.Key_Delete,
        Qt.Key.Key_Backspace,
        Qt.Key.Key_P,
        Qt.Key.Key_H,
    ):
        return True
    if mods == Qt.KeyboardModifier.ControlModifier and key in (
        Qt.Key.Key_Z,
        Qt.Key.Key_Y,
    ):
        return True
    return False
