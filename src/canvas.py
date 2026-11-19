from PyQt6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsPixmapItem,
    QGraphicsRectItem, QGraphicsItem, QGraphicsItemGroup, QFileDialog, QWidget
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPixmap, QImage,
    QKeyEvent, QPainterPath, QTransform
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QEvent, pyqtSignal

from items import (
    ArrowItem, TextItem, CalloutItem, StampItem,
    RectItem, EllipseItem, ImageOverlayItem, StrokeItem,
    BlurItem, NumberItem, PolygonItem, SpotlightItem,
    apply_shadow, item_is_text_editing,
)
from stamp_picker import StampPickerDialog
from styles import DEFAULT_STYLE


class ProSnipScene(QGraphicsScene):
    crop_requested = pyqtSignal(QRectF)
    tool_used = pyqtSignal(object)  # emits the new item added
    colour_picked = pyqtSignal(QColor)
    numbers_changed = pyqtSignal(int)
    number_edit_requested = pyqtSignal(object)
    style_changed = pyqtSignal()
    image_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor("#3a3a3a")))
        self._tool = "select"
        self._current_item = None
        self._press_pos = QPointF()
        self._undo_stack = []
        self._redo_stack = []
        self._last_stamp = None
        self._crop_rect_item = None

        # Style params
        self._pen_color = QColor(DEFAULT_STYLE.pen_color)
        self._fill_color = QColor(0, 0, 0, 0)
        self._text_color = QColor(DEFAULT_STYLE.text_color)
        self._line_width = DEFAULT_STYLE.line_width
        self._font_size = DEFAULT_STYLE.font_size
        self.arrow_style = "plain"
        self.arrow_start = "none"
        self.arrow_end = "arrow"
        self.item_opacity = 1.0
        self.corner_radius = 0
        self.shadow_enabled = False
        self.shadow_offset = 4
        self.shadow_blur = 8
        self.spotlight_darkness = 140
        self._image_rect_item = None
        self._next_number = 1
        self._clipboard = []
        self._eraser_item = None
        self._poly_points: list[QPointF] = []
        self._poly_preview = None
        self._cut_rect = None

    def set_tool(self, tool: str):
        if tool != "polygon":
            self._cancel_polygon()
        self._tool = tool

    def background_item(self):
        for item in self.items():
            if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0 and item.parentItem() is None:
                return item
        return None

    def set_pen_color(self, color: QColor):
        self._pen_color = QColor(color)

    def set_fill_color(self, color: QColor):
        self._fill_color = QColor(color)

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
        if self.shadow_enabled and not isinstance(item, SpotlightItem):
            item.shadow_enabled = True
            item.shadow_offset = self.shadow_offset
            item.shadow_blur = self.shadow_blur
            apply_shadow(item)
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

    def step_numbers(self) -> list[int]:
        return [
            item.number
            for item in self.items()
            if isinstance(item, NumberItem) and item.parentItem() is None
        ]

    def suggested_next_number(self) -> int:
        numbers = self.step_numbers()
        return (max(numbers) + 1) if numbers else 1

    def set_next_number(self, number: int) -> None:
        self._next_number = max(1, int(number))
        self.numbers_changed.emit(self._next_number)

    def sync_next_number(self) -> None:
        """Next badge is one past the highest number still on the canvas."""
        self.set_next_number(self.suggested_next_number())

    def undo(self):
        if not self._undo_stack:
            return
        entry = self._undo_stack.pop()
        if hasattr(entry, "undo"):
            entry.undo(self)
        else:
            self.removeItem(entry)
        self._redo_stack.append(entry)
        self.sync_next_number()
        self.style_changed.emit()

    def redo(self):
        if not self._redo_stack:
            return
        entry = self._redo_stack.pop()
        if hasattr(entry, "redo"):
            entry.redo(self)
        else:
            self.addItem(entry)
        self._undo_stack.append(entry)
        self.sync_next_number()
        self.style_changed.emit()

    def close_style_edit(self) -> None:
        if self._undo_stack and isinstance(self._undo_stack[-1], _StyleCommand):
            self._undo_stack[-1].open = False

    def edit_style(self, item, mutate) -> None:
        """Apply a colour or opacity change that can be undone as one step."""
        top = self._undo_stack[-1] if self._undo_stack else None
        if isinstance(top, _StyleCommand) and top.item is item and top.open:
            mutate()
            top.after = _style_snapshot(item)
            return
        before = _style_snapshot(item)
        mutate()
        command = _StyleCommand(item, before, _style_snapshot(item))
        self._undo_stack.append(command)
        self._redo_stack.clear()

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

    def _annotations(self):
        found = []
        for item in self.items():
            if item.parentItem() is not None:
                continue
            if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0:
                continue
            found.append(item)
        return found

    def select_all_annotations(self):
        self.clearSelection()
        for item in self._annotations():
            item.setSelected(True)

    def delete_selected(self):
        victims = [
            item for item in self.selectedItems()
            if item.parentItem() is None
            and not (isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0)
        ]
        for item in victims:
            self.removeItem(item)
        if victims:
            self._undo_stack.append(_RemoveCommand(victims))
            self._redo_stack.clear()
        self.sync_next_number()

    def delete_all_annotations(self):
        victims = self._annotations()
        for item in victims:
            self.removeItem(item)
        if victims:
            self._undo_stack.append(_RemoveCommand(victims))
            self._redo_stack.clear()
        self.sync_next_number()

    def bring_to_front(self):
        selected = [item for item in self.selectedItems() if item.parentItem() is None]
        top = max((item.zValue() for item in self.items()), default=0)
        for item in selected:
            top += 1
            item.setZValue(top)

    def send_to_back(self):
        selected = [item for item in self.selectedItems() if item.parentItem() is None]
        floor = 0
        for item in selected:
            floor -= 1
            item.setZValue(floor)

    def renumber_steps(self):
        steps = [item for item in self._annotations() if isinstance(item, NumberItem)]
        steps.sort(key=lambda item: (item.scenePos().y(), item.scenePos().x()))
        for index, item in enumerate(steps, start=1):
            item.set_number(index)
        self.sync_next_number()

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
            item.start_cap = self.arrow_start
            item.end_cap = self.arrow_end
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
            item = self._place(RectItem(QRectF(pos, pos), self._pen_color, self._fill_color, self._line_width))
            item.corner_radius = self.corner_radius
            self._current_item = item
            event.accept()

        elif tool == "polygon":
            self._poly_points.append(QPointF(pos))
            self._update_poly_preview(pos)
            event.accept()

        elif tool == "spotlight":
            item = self._place(SpotlightItem(QRectF(pos, pos), self.spotlight_darkness))
            self._current_item = item
            event.accept()

        elif tool == "cutout":
            self._cut_rect = QGraphicsRectItem(QRectF(pos, pos))
            self._cut_rect.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine))
            self._cut_rect.setBrush(QBrush(QColor(0, 0, 0, 40)))
            self.addItem(self._cut_rect)
            event.accept()

        elif tool == "blur":
            item = BlurItem(QRectF(pos, pos))
            self.addItem(item)
            self._current_item = item
            event.accept()

        elif tool == "number":
            colour = QColor(self._pen_color)
            for existing in self.items():
                if isinstance(existing, NumberItem) and existing.parentItem() is None:
                    colour = QColor(existing.color)
                    break
            item = NumberItem(self._next_number, pos, colour)
            self.addItem(item)
            self._push_undo(item)
            self.sync_next_number()
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

            elif tool in ("rect", "ellipse", "blur", "spotlight"):
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

        elif tool == "polygon" and self._poly_points:
            self._update_poly_preview(pos)

        elif tool == "cutout" and self._cut_rect is not None:
            self._cut_rect.setRect(QRectF(self._press_pos, pos).normalized())

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
            self.erase_to_canvas(stroke)
            return

        if tool == "cutout" and self._cut_rect is not None:
            rect = QRectF(self._cut_rect.rect())
            self.removeItem(self._cut_rect)
            self._cut_rect = None
            self._tool = "select"
            if rect.width() > 4 or rect.height() > 4:
                self.cut_strip(rect)
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

    def mouseDoubleClickEvent(self, event):
        if self._tool == "polygon":
            self.finish_polygon()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _update_poly_preview(self, hover: QPointF):
        if self._poly_preview is None:
            self._poly_preview = QGraphicsRectItem()
            self._poly_preview.setPen(QPen(self._pen_color, 1, Qt.PenStyle.DashLine))
            self._poly_preview.setBrush(QBrush(QColor(self._pen_color.red(), self._pen_color.green(), self._pen_color.blue(), 40)))
            self._poly_preview.setZValue(50)
            self.addItem(self._poly_preview)
        points = list(self._poly_points) + [QPointF(hover)]
        if len(points) < 2:
            return
        left = min(point.x() for point in points)
        top = min(point.y() for point in points)
        right = max(point.x() for point in points)
        bottom = max(point.y() for point in points)
        self._poly_preview.setRect(QRectF(left, top, max(1, right - left), max(1, bottom - top)))

    def _cancel_polygon(self):
        self._poly_points = []
        if self._poly_preview is not None:
            self.removeItem(self._poly_preview)
            self._poly_preview = None

    def finish_polygon(self):
        points = list(self._poly_points)
        self._cancel_polygon()
        if len(points) < 3:
            return None
        origin = points[0]
        local = [QPointF(point.x() - origin.x(), point.y() - origin.y()) for point in points]
        item = self._place(PolygonItem(local, self._pen_color, self._fill_color, self._line_width))
        item.setPos(origin)
        self._push_undo(item)
        return item

    def duplicate_at(self, pos: QPointF):
        """Ctrl+drag: copy the annotation under the cursor and leave the original."""
        item = self._annotation_at(pos)
        if item is None:
            return None
        clone = _clone_item(item)
        if clone is None:
            return None
        clone.setZValue(item.zValue() + 1)
        self.addItem(clone)
        self.clearSelection()
        clone.setSelected(True)
        self._undo_stack.append(_AddCommand([clone]))
        self._redo_stack.clear()
        return clone

    def _annotation_at(self, pos: QPointF):
        for item in self.items(pos):
            while item.parentItem() is not None and not isinstance(item.parentItem(), QGraphicsItemGroup):
                item = item.parentItem()
            if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0:
                continue
            if item.parentItem() is None or isinstance(item.parentItem(), QGraphicsItemGroup):
                if isinstance(item.parentItem(), QGraphicsItemGroup):
                    return item.parentItem()
                return item
        return None

    def erase_to_canvas(self, stroke: StrokeItem):
        """Rub out image pixels and the annotations underneath, back to the canvas."""
        victims = []
        for item in list(self.items()):
            if item is stroke or item.parentItem() is not None:
                continue
            if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0:
                continue
            if stroke.collidesWithItem(item):
                victims.append(item)
        background = self.background_item()
        before = QPixmap(background.pixmap()) if background is not None else None
        scene_before = QRectF(self.sceneRect())
        if background is not None and stroke._points:
            image = background.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32)
            painter = QPainter(image)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.setPen(QPen(
                QColor(0, 0, 0, 255),
                max(8, stroke.line_width),
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            ))
            path = QPainterPath()
            for index, point in enumerate(stroke._points):
                local = background.mapFromScene(stroke.mapToScene(point))
                if index == 0:
                    path.moveTo(local)
                else:
                    path.lineTo(local)
            painter.drawPath(path)
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(QColor(0, 0, 0, 255)))
            radius = max(4.0, stroke.line_width / 2.0)
            for point in stroke._points:
                local = background.mapFromScene(stroke.mapToScene(point))
                painter.drawEllipse(local, radius, radius)
            painter.end()
            background.setPixmap(QPixmap.fromImage(image))
        self.removeItem(stroke)
        for item in victims:
            self.removeItem(item)
        if background is not None and before is not None:
            self._undo_stack.append(_ImageCommand(
                background, before, QPixmap(background.pixmap()), victims, [], scene_before, QRectF(self.sceneRect()),
            ))
            self._redo_stack.clear()
            self.image_changed.emit()
        elif victims:
            self._undo_stack.append(_RemoveCommand(victims))
            self._redo_stack.clear()

    def cut_strip(self, rect: QRectF):
        """Remove a horizontal or vertical band and close the gap."""
        background = self.background_item()
        if background is None:
            return False
        source = background.pixmap().toImage().convertToFormat(QImage.Format.Format_ARGB32)
        width, height = source.width(), source.height()
        band = rect.normalized().intersected(QRectF(0, 0, width, height))
        if band.width() < 2 and band.height() < 2:
            return False
        horizontal = band.width() >= band.height()
        before = QPixmap(background.pixmap())
        scene_before = QRectF(self.sceneRect())
        removed = []
        moves = []
        if horizontal:
            y0 = max(0, int(band.top()))
            y1 = min(height, int(math_ceil(band.bottom())))
            gap = y1 - y0
            if gap < 2 or gap >= height:
                return False
            target = QImage(width, height - gap, QImage.Format.Format_ARGB32)
            target.fill(Qt.GlobalColor.transparent)
            painter = QPainter(target)
            painter.drawImage(0, 0, source, 0, 0, width, y0)
            painter.drawImage(0, y0, source, 0, y1, width, height - y1)
            painter.end()
            self._shift_for_gap(removed, moves, horizontal=True, start=y0, end=y1, gap=gap)
        else:
            x0 = max(0, int(band.left()))
            x1 = min(width, int(math_ceil(band.right())))
            gap = x1 - x0
            if gap < 2 or gap >= width:
                return False
            target = QImage(width - gap, height, QImage.Format.Format_ARGB32)
            target.fill(Qt.GlobalColor.transparent)
            painter = QPainter(target)
            painter.drawImage(0, 0, source, 0, 0, x0, height)
            painter.drawImage(x0, 0, source, x1, 0, width - x1, height)
            painter.end()
            self._shift_for_gap(removed, moves, horizontal=False, start=x0, end=x1, gap=gap)
        background.setPixmap(QPixmap.fromImage(target))
        background.setPos(0, 0)
        self.setSceneRect(QRectF(0, 0, target.width(), target.height()))
        for item in removed:
            self.removeItem(item)
        self._undo_stack.append(_ImageCommand(
            background, before, QPixmap(background.pixmap()), removed, moves,
            scene_before, QRectF(self.sceneRect()),
        ))
        self._redo_stack.clear()
        self.image_changed.emit()
        return True

    def _shift_for_gap(self, removed, moves, horizontal: bool, start: int, end: int, gap: int):
        for item in list(self._annotations()):
            centre = item.sceneBoundingRect().center()
            if horizontal:
                inside = start <= centre.y() <= end
                past = centre.y() > end
                delta = QPointF(0, -gap)
            else:
                inside = start <= centre.x() <= end
                past = centre.x() > end
                delta = QPointF(-gap, 0)
            if inside:
                removed.append(item)
            elif past:
                item.moveBy(delta.x(), delta.y())
                moves.append((item, delta.x(), delta.y()))

    def group_selected(self):
        chosen = [
            item for item in self.selectedItems()
            if item.parentItem() is None and not (isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0)
        ]
        if len(chosen) < 2:
            return None
        group = QGraphicsItemGroup()
        self.addItem(group)
        for item in chosen:
            group.addToGroup(item)
        group.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        group.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.clearSelection()
        group.setSelected(True)
        self._undo_stack.append(_GroupCommand(group, chosen))
        self._redo_stack.clear()
        return group

    def ungroup_selected(self):
        groups = [item for item in self.selectedItems() if isinstance(item, QGraphicsItemGroup)]
        if not groups:
            groups = [
                item.parentItem() for item in self.selectedItems()
                if isinstance(item.parentItem(), QGraphicsItemGroup)
            ]
        undone = []
        for group in groups:
            if group is None or group not in undone:
                children = [child for child in group.childItems() if child.parentItem() is group]
                for child in children:
                    group.removeFromGroup(child)
                self.removeItem(group)
                self._undo_stack.append(_UngroupCommand(group, children))
                undone.append(group)
        if undone:
            self._redo_stack.clear()
        return undone

    def flatten_selected(self):
        background = self.background_item()
        if background is None:
            return False
        selected = [
            item for item in self.selectedItems()
            if item is not background and item.parentItem() is None
        ]
        if not selected:
            selected = [item for item in self._annotations() if item is not background]
        if not selected:
            return False
        before = QPixmap(background.pixmap())
        scene_before = QRectF(self.sceneRect())
        hidden = []
        keep = set(selected)
        for item in self.items():
            if item is background or item in keep:
                continue
            if item.isVisible():
                item.setVisible(False)
                hidden.append(item)
        background.hide()
        layer = QImage(before.width(), before.height(), QImage.Format.Format_ARGB32)
        layer.fill(0)
        painter = QPainter(layer)
        self.render(painter, QRectF(0, 0, before.width(), before.height()), QRectF(0, 0, before.width(), before.height()))
        painter.end()
        background.show()
        for item in hidden:
            item.setVisible(True)
        result = before.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        painter = QPainter(result)
        painter.drawImage(0, 0, layer)
        painter.end()
        background.setPixmap(QPixmap.fromImage(result))
        for item in selected:
            self.removeItem(item)
        self._undo_stack.append(_ImageCommand(
            background, before, QPixmap(background.pixmap()), selected, [],
            scene_before, QRectF(self.sceneRect()),
        ))
        self._redo_stack.clear()
        self.image_changed.emit()
        return True


def math_ceil(value: float) -> int:
    return int(value) if value == int(value) else int(value) + 1


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
    cursor_moved = pyqtSignal(QPointF)

    def __init__(self, scene: ProSnipScene, parent=None):
        super().__init__(scene, parent)
        self.setViewport(_CanvasViewport(self))
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor("#3a3a3a")))
        self.setStyleSheet("background-color: #3a3a3a; border: none;")

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
        if (
            not editing
            and scene is not None
            and scene._tool == "polygon"
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        ):
            scene.finish_polygon()
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

    def mousePressEvent(self, event):
        scene = self.scene()
        if (
            isinstance(scene, ProSnipScene)
            and scene._tool == "select"
            and event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            scene.duplicate_at(self.mapToScene(event.position().toPoint()))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.cursor_moved.emit(self.mapToScene(event.position().toPoint()))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            self.cursor_moved.emit(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        super().wheelEvent(event)

    def fit_scene(self):
        scene = self.scene()
        if scene is not None:
            self.fitInView(scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def fit_if_larger(self):
        """Scale the picture down so it is on screen. Leave a smaller one at 100%."""
        scene = self.scene()
        if scene is None:
            return
        rect = scene.sceneRect()
        view = self.viewport().size()
        if view.width() < 20 or view.height() < 20:
            return
        if rect.width() > view.width() - 48 or rect.height() > view.height() - 48:
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
            self.scale(0.92, 0.92)

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


class _StyleCommand:
    def __init__(self, item, before, after):
        self.item = item
        self.before = before
        self.after = after
        self.open = True

    def undo(self, scene):
        self.open = False
        _restore_style(self.item, self.before)

    def redo(self, scene):
        _restore_style(self.item, self.after)


def _style_snapshot(item) -> dict:
    fill = getattr(item, "fill_color", None)
    pen = getattr(item, "pen_color", None)
    return {
        "pen": QColor(pen) if pen is not None else None,
        "fill": QColor(fill) if fill is not None else None,
        "width": getattr(item, "line_width", None),
        "stroke": getattr(item, "stroke_enabled", None),
        "opacity": item.opacity(),
        "shadow": bool(getattr(item, "shadow_enabled", False)),
        "shadow_offset": getattr(item, "shadow_offset", None),
        "shadow_blur": getattr(item, "shadow_blur", None),
        "corner": getattr(item, "corner_radius", None),
        "style": getattr(item, "style", None),
        "start_cap": getattr(item, "start_cap", None),
        "end_cap": getattr(item, "end_cap", None),
        "darkness": getattr(item, "darkness", None),
    }


def _restore_style(item, snap: dict) -> None:
    if snap["pen"] is not None and hasattr(item, "pen_color"):
        item.pen_color = QColor(snap["pen"])
    if snap["fill"] is not None and hasattr(item, "fill_color"):
        item.fill_color = QColor(snap["fill"])
    if snap["width"] is not None and hasattr(item, "line_width"):
        item.line_width = snap["width"]
    if snap["stroke"] is not None and hasattr(item, "stroke_enabled"):
        item.stroke_enabled = snap["stroke"]
    if snap.get("corner") is not None and hasattr(item, "corner_radius"):
        item.corner_radius = snap["corner"]
    if snap.get("style") is not None and hasattr(item, "style"):
        item.style = snap["style"]
    if snap.get("start_cap") is not None and hasattr(item, "start_cap"):
        item.start_cap = snap["start_cap"]
    if snap.get("end_cap") is not None and hasattr(item, "end_cap"):
        item.end_cap = snap["end_cap"]
    if snap.get("darkness") is not None and hasattr(item, "darkness"):
        item.darkness = snap["darkness"]
    if "shadow" in snap:
        item.shadow_enabled = bool(snap["shadow"])
    if snap.get("shadow_offset") is not None:
        item.shadow_offset = snap["shadow_offset"]
    if snap.get("shadow_blur") is not None:
        item.shadow_blur = snap["shadow_blur"]
    item.setOpacity(snap["opacity"])
    if hasattr(item, "_apply_style"):
        item._apply_style()
    apply_shadow(item)
    item.update()


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


class _ImageCommand:
    """Pixmap edit plus any annotations removed or shifted to close a gap."""

    def __init__(self, item, before, after, removed, moves, scene_before, scene_after):
        self.item = item
        self.before = before
        self.after = after
        self.removed = list(removed)
        self.moves = list(moves)
        self.scene_before = scene_before
        self.scene_after = scene_after

    def undo(self, scene):
        self.item.setPixmap(self.before)
        scene.setSceneRect(self.scene_before)
        for item, dx, dy in self.moves:
            item.moveBy(-dx, -dy)
        for item in self.removed:
            scene.addItem(item)
        scene.image_changed.emit()

    def redo(self, scene):
        self.item.setPixmap(self.after)
        scene.setSceneRect(self.scene_after)
        for item, dx, dy in self.moves:
            item.moveBy(dx, dy)
        for item in self.removed:
            scene.removeItem(item)
        scene.image_changed.emit()


class _GroupCommand:
    def __init__(self, group, items):
        self.group = group
        self.items = list(items)

    def undo(self, scene):
        for item in self.items:
            self.group.removeFromGroup(item)
        scene.removeItem(self.group)

    def redo(self, scene):
        scene.addItem(self.group)
        for item in self.items:
            self.group.addToGroup(item)


class _UngroupCommand:
    def __init__(self, group, items):
        self.group = group
        self.items = list(items)

    def undo(self, scene):
        scene.addItem(self.group)
        for item in self.items:
            self.group.addToGroup(item)

    def redo(self, scene):
        for item in list(self.group.childItems()):
            self.group.removeFromGroup(item)
        scene.removeItem(self.group)


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
        clone.start_cap = item.start_cap
        clone.end_cap = item.end_cap
    elif isinstance(item, PolygonItem):
        clone = PolygonItem(item.points, item.pen_color, item.fill_color, item.line_width)
    elif isinstance(item, SpotlightItem):
        clone = SpotlightItem(QRectF(item.rect()), item.darkness)
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
    clone.shadow_enabled = bool(getattr(item, "shadow_enabled", False))
    clone.shadow_offset = getattr(item, "shadow_offset", 4)
    clone.shadow_blur = getattr(item, "shadow_blur", 8)
    apply_shadow(clone)
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
