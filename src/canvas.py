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
    BlurItem, NumberItem,
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
        self.corner_radius = 0
        self._image_rect_item = None
        self._next_number = 1
        self._clipboard = []
        self._eraser_item = None

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
        if not self._undo_stack:
            return
        entry = self._undo_stack.pop()
        if hasattr(entry, "undo"):
            entry.undo(self)
        else:
            self.removeItem(entry)
        self._redo_stack.append(entry)

    def redo(self):
        if not self._redo_stack:
            return
        entry = self._redo_stack.pop()
        if hasattr(entry, "redo"):
            entry.redo(self)
        else:
            self.addItem(entry)
        self._undo_stack.append(entry)

    def copy_selected(self):
        self._clipboard = [item for item in self.selectedItems() if item.parentItem() is None]

    def paste_clipboard(self):
        clones = []
        for item in self._clipboard:
            clone = _clone_item(item)
            if clone is None:
                continue
            clone.moveBy(16, 16)
            self.addItem(clone)
            clones.append(clone)
        if clones:
            self.clearSelection()
            for clone in clones:
                clone.setSelected(True)
            self._undo_stack.append(_AddCommand(clones))
            self._redo_stack.clear()

    def duplicate_selected(self):
        self.copy_selected()
        self.paste_clipboard()

    def bring_forward(self):
        selected = [item for item in self.selectedItems() if item.parentItem() is None]
        top = max((item.zValue() for item in self.items()), default=0)
        for item in selected:
            top += 1
            item.setZValue(top)

    def send_back(self):
        selected = [item for item in self.selectedItems() if item.parentItem() is None]
        floor = min((item.zValue() for item in self.items() if item.zValue() > -50), default=0)
        for item in selected:
            floor -= 1
            item.setZValue(floor)

    def align_left(self):
        selected = [item for item in self.selectedItems() if item.parentItem() is None]
        if len(selected) < 2:
            return
        edge = min(item.sceneBoundingRect().left() for item in selected)
        for item in selected[1:]:
            rect = item.sceneBoundingRect()
            item.moveBy(edge - rect.left(), 0)

    def toggle_lock(self):
        for item in self.selectedItems():
            locked = not getattr(item, "locked", False)
            item.locked = locked
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not locked)

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
            item.corner_radius = self.corner_radius
            self.addItem(item)
            self._current_item = item
            event.accept()

        elif tool == "blur":
            item = BlurItem(QRectF(pos, pos))
            self.addItem(item)
            self._current_item = item
            event.accept()

        elif tool == "number":
            item = NumberItem(self._next_number, pos, self._pen_color)
            self._next_number += 1
            self.addItem(item)
            self._push_undo(item)
            self._current_item = None
            event.accept()

        elif tool == "eraser":
            self._eraser_item = StrokeItem(QColor(255, 255, 255, 90), max(16, self._line_width))
            self.addItem(self._eraser_item)
            self._eraser_item.add_point(pos)
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

            elif tool in ("rect", "ellipse", "blur"):
                item = self._current_item
                r = QRectF(self._press_pos, pos).normalized()
                item.prepareGeometryChange()
                if hasattr(item, "_set_rect"):
                    item._set_rect(r)
                    item._update_handles()
                else:
                    item.setRect(r)
                item.update()

            elif tool == "eraser" and self._eraser_item is not None:
                self._eraser_item.add_point(pos)
                return

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

        if tool == "eraser" and self._eraser_item is not None:
            stroke = self._eraser_item
            self._eraser_item = None
            victims = []
            for item in list(self.items()):
                if item is stroke or item.parentItem() is not None:
                    continue
                if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0:
                    continue
                if stroke.collidesWithItem(item):
                    victims.append(item)
            self.removeItem(stroke)
            for item in victims:
                self.removeItem(item)
            if victims:
                self._undo_stack.append(_RemoveCommand(victims))
                self._redo_stack.clear()
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
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
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
        if event.key() == Qt.Key.Key_Space and not editing:
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            return
        if (
            not editing
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_0
        ):
            self.fit_scene()
            return
        if (
            not editing
            and event.modifiers() == Qt.KeyboardModifier.ControlModifier
            and event.key() == Qt.Key.Key_1
        ):
            self.resetTransform()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            return
        super().keyReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def fit_scene(self):
        scene = self.scene()
        if scene is not None:
            self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_select_drag(self, enabled: bool):
        mode = (
            QGraphicsView.DragMode.RubberBandDrag
            if enabled
            else QGraphicsView.DragMode.NoDrag
        )
        self.setDragMode(mode)


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


class _AddCommand:
    def __init__(self, items):
        self.items = list(items)

    def undo(self, scene):
        for item in self.items:
            scene.removeItem(item)

    def redo(self, scene):
        for item in self.items:
            scene.addItem(item)


class _RemoveCommand:
    def __init__(self, items):
        self.items = list(items)

    def undo(self, scene):
        for item in self.items:
            scene.addItem(item)

    def redo(self, scene):
        for item in self.items:
            scene.removeItem(item)


def _clone_item(item):
    clone = None
    if isinstance(item, RectItem):
        clone = RectItem(QRectF(item.rect()), item.pen_color, item.fill_color, item.line_width)
        clone.corner_radius = item.corner_radius
    elif isinstance(item, EllipseItem):
        clone = EllipseItem(QRectF(item.rect()), item.pen_color, item.fill_color, item.line_width)
    elif isinstance(item, TextItem):
        clone = TextItem(item.toPlainText(), item.pos(), item.defaultTextColor(), item.font().pointSize() or 14)
        clone.bg_color = QColor(item.bg_color)
        clone.set_bold(item.font().bold())
    elif isinstance(item, NumberItem):
        clone = NumberItem(item.number, item.pos(), item.color)
    elif isinstance(item, BlurItem):
        clone = BlurItem(QRectF(item.rect()), item.block)
    elif isinstance(item, ArrowItem):
        clone = ArrowItem(QPointF(item.start), QPointF(item.end), item.pen_color, item.line_width, item.style)
    elif isinstance(item, StrokeItem):
        clone = StrokeItem(QColor(item.pen_color), item.line_width, item.highlighter)
        for point in item._points:
            clone.add_point(QPointF(point))
    if clone is None:
        return None
    if not isinstance(item, (TextItem, NumberItem)):
        clone.setPos(item.pos())
    clone.setRotation(item.rotation())
    clone.setZValue(item.zValue())
    return clone


def _text_keeps_key(event) -> bool:
    """Keys the text editor must receive instead of a window shortcut."""
    key = event.key()
    mods = event.modifiers()
    if mods == Qt.KeyboardModifier.NoModifier and key in (
        Qt.Key.Key_Delete,
        Qt.Key.Key_Backspace,
        Qt.Key.Key_A,
        Qt.Key.Key_T,
        Qt.Key.Key_P,
        Qt.Key.Key_H,
        Qt.Key.Key_R,
        Qt.Key.Key_E,
        Qt.Key.Key_V,
        Qt.Key.Key_B,
        Qt.Key.Key_N,
        Qt.Key.Key_C,
        Qt.Key.Key_I,
        Qt.Key.Key_X,
    ):
        return True
    if mods == Qt.KeyboardModifier.ControlModifier and key in (
        Qt.Key.Key_Z,
        Qt.Key.Key_Y,
    ):
        return True
    return False
