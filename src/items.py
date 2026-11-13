import math
from enum import IntEnum

from PyQt6.QtWidgets import (
    QGraphicsItem, QGraphicsRectItem, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsPixmapItem, QGraphicsSceneMouseEvent
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath,
    QTextDocument, QTextCursor, QPixmap, QTransform, QPainterPathStroker
)
from PyQt6.QtCore import Qt, QRectF, QPointF, QSizeF


# ---------------------------------------------------------------------------
# Handle position enum
# ---------------------------------------------------------------------------
class HandlePos(IntEnum):
    TL = 0
    T  = 1
    TR = 2
    L  = 3
    R  = 4
    BL = 5
    B  = 6
    BR = 7


HANDLE_SIZE = 8
HANDLE_HALF = HANDLE_SIZE / 2


def item_is_text_editing(item) -> bool:
    """True when ``item`` is a text box currently accepting keyboard edits.

    Stamps are also text items, but they never turn on text interaction, so
    Delete still removes a selected stamp.
    """
    if not isinstance(item, QGraphicsTextItem):
        return False
    flags = item.textInteractionFlags()
    return bool(flags & Qt.TextInteractionFlag.TextEditorInteraction)


def _handle_color():
    pen = QPen(QColor("#000000"), 1)
    brush = QBrush(QColor("#ffffff"))
    return pen, brush


# ---------------------------------------------------------------------------
# ResizeHandle — child QGraphicsRectItem
# ---------------------------------------------------------------------------
class ResizeHandle(QGraphicsRectItem):
    def __init__(self, pos_index: int, parent_item):
        super().__init__(-HANDLE_HALF, -HANDLE_HALF, HANDLE_SIZE, HANDLE_SIZE, parent_item)
        self.pos_index = pos_index
        self.parent_item = parent_item
        pen, brush = _handle_color()
        self.setPen(pen)
        self.setBrush(brush)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresParentOpacity, True)
        self.setZValue(1000)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_item._start_resize(self.pos_index, event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        self.parent_item._do_resize(self.pos_index, event.scenePos())
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self.parent_item._end_resize()
        event.accept()


# ---------------------------------------------------------------------------
# Mixin: adds 8 resize handles to a rect-based item
# ---------------------------------------------------------------------------
class RotateHandle(QGraphicsEllipseItem):
    """Drag to rotate the parent around its centre."""

    def __init__(self, parent_item):
        super().__init__(-6, -6, 12, 12, parent_item)
        self.parent_item = parent_item
        self.setBrush(QBrush(QColor("#0078d4")))
        self.setPen(QPen(QColor("#ffffff"), 1))
        self.setZValue(1001)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        parent = self.parent_item
        if getattr(parent, "locked", False):
            event.accept()
            return
        origin = parent._get_rect().center() if hasattr(parent, "_get_rect") else parent.boundingRect().center()
        parent.setTransformOriginPoint(origin)
        centre = parent.mapToScene(origin)
        pos = event.scenePos()
        angle = math.degrees(math.atan2(pos.y() - centre.y(), pos.x() - centre.x())) + 90
        parent.prepareGeometryChange()
        parent.setRotation(angle)
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()


class ResizableMixin:
    """Mixin for items that have a rect and support 8-handle resizing."""

    def _init_handles(self):
        self.handles = []
        self._resizing = False
        self._resize_start_pos = None
        self._resize_start_rect = None
        for i in range(8):
            h = ResizeHandle(i, self)
            self.handles.append(h)
        self._update_handles()
        self._show_handles(False)

    def _show_handles(self, visible: bool):
        for h in self.handles:
            h.setVisible(visible)

    def _update_handles(self):
        r = self._get_rect()
        positions = self._handle_positions(r)
        for h, pos in zip(self.handles, positions):
            h.setPos(pos)
        if getattr(self, "_rotate_handle", None) is not None:
            self._rotate_handle.setPos(r.center().x(), r.top() - 22)

    def _init_rotate_handle(self):
        self._rotate_handle = RotateHandle(self)
        self._rotate_handle.setVisible(False)

    def _show_handles(self, visible: bool):
        for h in self.handles:
            h.setVisible(visible and not getattr(self, "locked", False))
        if getattr(self, "_rotate_handle", None) is not None:
            self._rotate_handle.setVisible(visible and not getattr(self, "locked", False))

    def _handle_positions(self, r: QRectF):
        cx = r.center().x()
        cy = r.center().y()
        return [
            QPointF(r.left(),  r.top()),      # TL
            QPointF(cx,        r.top()),       # T
            QPointF(r.right(), r.top()),       # TR
            QPointF(r.left(),  cy),            # L
            QPointF(r.right(), cy),            # R
            QPointF(r.left(),  r.bottom()),    # BL
            QPointF(cx,        r.bottom()),    # B
            QPointF(r.right(), r.bottom()),    # BR
        ]

    def _get_rect(self) -> QRectF:
        raise NotImplementedError

    def _set_rect(self, r: QRectF):
        raise NotImplementedError

    def _start_resize(self, pos_index: int, scene_pos: QPointF):
        self._resizing = True
        self._resize_handle_index = pos_index
        self._resize_start_pos = scene_pos
        self._resize_start_rect = QRectF(self._get_rect())

    def _do_resize(self, pos_index: int, scene_pos: QPointF):
        if not self._resizing:
            return
        delta = scene_pos - self._resize_start_pos
        r = QRectF(self._resize_start_rect)

        if pos_index == HandlePos.TL:
            r.setTopLeft(r.topLeft() + delta)
        elif pos_index == HandlePos.T:
            r.setTop(r.top() + delta.y())
        elif pos_index == HandlePos.TR:
            r.setTopRight(r.topRight() + delta)
        elif pos_index == HandlePos.L:
            r.setLeft(r.left() + delta.x())
        elif pos_index == HandlePos.R:
            r.setRight(r.right() + delta.x())
        elif pos_index == HandlePos.BL:
            r.setBottomLeft(r.bottomLeft() + delta)
        elif pos_index == HandlePos.B:
            r.setBottom(r.bottom() + delta.y())
        elif pos_index == HandlePos.BR:
            r.setBottomRight(r.bottomRight() + delta)

        r = r.normalized()
        if r.width() < 10:
            r.setWidth(10)
        if r.height() < 10:
            r.setHeight(10)
        self.prepareGeometryChange()
        self._set_rect(r)
        self._update_handles()

    def _end_resize(self):
        self._resizing = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._show_handles(bool(value))
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# RectItem
# ---------------------------------------------------------------------------
class RectItem(ResizableMixin, QGraphicsRectItem):
    def __init__(self, rect: QRectF, pen_color: QColor, fill_color: QColor, line_width: int):
        super().__init__(rect)
        self.pen_color = pen_color
        self.fill_color = fill_color
        self.line_width = line_width
        self.stroke_enabled = True
        self._apply_style()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.corner_radius = 0
        self.locked = False
        self._init_handles()
        self._init_rotate_handle()

    def _apply_style(self):
        if self.stroke_enabled and self.line_width > 0:
            self.setPen(QPen(self.pen_color, self.line_width))
        else:
            self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(self.fill_color))

    def boundingRect(self) -> QRectF:
        pad = self.line_width / 2.0 + HANDLE_HALF + 28
        return self.rect().adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.rect().adjusted(-self.line_width, -self.line_width, self.line_width, self.line_width))
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.pen())
        painter.setBrush(self.brush())
        if self.corner_radius > 0:
            painter.drawRoundedRect(self.rect(), self.corner_radius, self.corner_radius)
        else:
            painter.drawRect(self.rect())

    def _get_rect(self) -> QRectF:
        return self.rect()

    def _set_rect(self, r: QRectF):
        self.prepareGeometryChange()
        self.setRect(r)

    def itemChange(self, change, value):
        return ResizableMixin.itemChange(self, change, value)


# ---------------------------------------------------------------------------
# EllipseItem
# ---------------------------------------------------------------------------
class EllipseItem(ResizableMixin, QGraphicsEllipseItem):
    def __init__(self, rect: QRectF, pen_color: QColor, fill_color: QColor, line_width: int):
        super().__init__(rect)
        self.pen_color = pen_color
        self.fill_color = fill_color
        self.line_width = line_width
        self.stroke_enabled = True
        self._apply_style()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.locked = False
        self._init_handles()
        self._init_rotate_handle()

    def _apply_style(self):
        if self.stroke_enabled and self.line_width > 0:
            self.setPen(QPen(self.pen_color, self.line_width))
        else:
            self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(self.fill_color))

    def boundingRect(self) -> QRectF:
        pad = self.line_width / 2.0 + HANDLE_HALF + 28
        return self.rect().adjusted(-pad, -pad, pad, pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.rect().adjusted(-self.line_width, -self.line_width, self.line_width, self.line_width))
        return path

    def _get_rect(self) -> QRectF:
        return self.rect()

    def _set_rect(self, r: QRectF):
        self.prepareGeometryChange()
        self.setRect(r)

    def itemChange(self, change, value):
        return ResizableMixin.itemChange(self, change, value)


# ---------------------------------------------------------------------------
# ArrowItem
# ---------------------------------------------------------------------------
ARROW_STYLES = ("plain", "dashed", "dotted", "double", "tapered", "curved")


class ArrowItem(QGraphicsItem):
    def __init__(self, start: QPointF, end: QPointF, pen_color: QColor, line_width: int, style: str = "plain"):
        super().__init__()
        self.start = QPointF(start)
        self.end = QPointF(end)
        self.pen_color = QColor(pen_color)
        self.line_width = max(1, int(line_width))
        self.style = style if style in ARROW_STYLES else "plain"
        self.stroke_enabled = True
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        # Two handles: TL = start, BR = end
        self.handles = []
        self._resizing = False
        self._resize_handle_index = None
        for i in [HandlePos.TL, HandlePos.BR]:
            h = ResizeHandle(i, self)
            self.handles.append(h)
        self._update_handles()
        self._show_handles(False)

    def _show_handles(self, visible: bool):
        for h in self.handles:
            h.setVisible(visible)

    def _update_handles(self):
        for h in self.handles:
            if h.pos_index == HandlePos.TL:
                h.setPos(self.start)
            else:
                h.setPos(self.end)

    def boundingRect(self) -> QRectF:
        rect = QRectF(self.start, self.end).normalized()
        if self.style == "curved":
            control = self._curve_control()
            rect = rect.united(QRectF(control, control))
        extra = self.line_width + HANDLE_HALF + 28
        return rect.adjusted(-extra, -extra, extra, extra)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def _direction(self, origin: QPointF, target: QPointF):
        dx = target.x() - origin.x()
        dy = target.y() - origin.y()
        length = math.hypot(dx, dy)
        if length < 1:
            return 0.0, 0.0, 0.0
        return dx / length, dy / length, length

    def _curve_control(self) -> QPointF:
        ux, uy, length = self._direction(self.start, self.end)
        if length < 1:
            return QPointF(self.start)
        mid_x = (self.start.x() + self.end.x()) / 2.0
        mid_y = (self.start.y() + self.end.y()) / 2.0
        bend = max(24.0, length * 0.28)
        return QPointF(mid_x - uy * bend, mid_y + ux * bend)

    def _draw_head(self, painter: QPainter, origin: QPointF, tip: QPointF):
        ux, uy, length = self._direction(origin, tip)
        if length < 1:
            return
        head = 10 + self.line_width * 2.4
        px, py = -uy, ux
        base1 = QPointF(tip.x() - ux * head + px * head * 0.42, tip.y() - uy * head + py * head * 0.42)
        base2 = QPointF(tip.x() - ux * head - px * head * 0.42, tip.y() - uy * head - py * head * 0.42)
        path = QPainterPath()
        path.moveTo(tip)
        path.lineTo(base1)
        path.lineTo(base2)
        path.closeSubpath()
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QBrush(self.pen_color))
        painter.drawPath(path)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.stroke_enabled:
            return
        if self.style == "tapered":
            ux, uy, length = self._direction(self.start, self.end)
            if length < 1:
                return
            px, py = -uy, ux
            head_len = min(length * 0.36, 18.0 + self.line_width * 3.0)
            neck = QPointF(self.end.x() - ux * head_len, self.end.y() - uy * head_len)
            tail_half = max(1.25, self.line_width * 0.28)
            neck_half = max(tail_half + 3.0, self.line_width * 0.95)
            head_half = neck_half + max(7.0, self.line_width * 1.2)
            shaft = QPainterPath()
            shaft.moveTo(QPointF(self.start.x() + px * tail_half, self.start.y() + py * tail_half))
            shaft.lineTo(QPointF(neck.x() + px * neck_half, neck.y() + py * neck_half))
            shaft.lineTo(QPointF(neck.x() - px * neck_half, neck.y() - py * neck_half))
            shaft.lineTo(QPointF(self.start.x() - px * tail_half, self.start.y() - py * tail_half))
            shaft.closeSubpath()
            head = QPainterPath()
            head.moveTo(self.end)
            head.lineTo(QPointF(neck.x() + px * head_half, neck.y() + py * head_half))
            head.lineTo(QPointF(neck.x() - px * head_half, neck.y() - py * head_half))
            head.closeSubpath()
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(self.pen_color))
            painter.drawPath(shaft)
            painter.drawPath(head)
            return

        pen = QPen(self.pen_color, self.line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        if self.style == "dashed":
            pen.setStyle(Qt.PenStyle.DashLine)
        elif self.style == "dotted":
            pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if self.style == "curved":
            path = QPainterPath()
            path.moveTo(self.start)
            path.quadTo(self._curve_control(), self.end)
            painter.drawPath(path)
            control = self._curve_control()
            self._draw_head(painter, control, self.end)
        else:
            painter.drawLine(self.start, self.end)
            self._draw_head(painter, self.start, self.end)
            if self.style == "double":
                self._draw_head(painter, self.end, self.start)

    def _start_resize(self, pos_index: int, scene_pos: QPointF):
        self._resizing = True
        self._resize_handle_index = pos_index

    def _do_resize(self, pos_index: int, scene_pos: QPointF):
        if not self._resizing:
            return
        local = self.mapFromScene(scene_pos)
        self.prepareGeometryChange()
        if pos_index == HandlePos.TL:
            self.start = local
        else:
            self.end = local
        self._update_handles()

    def _end_resize(self):
        self._resizing = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._show_handles(bool(value))
        return super().itemChange(change, value)


# ---------------------------------------------------------------------------
# TextItem
# ---------------------------------------------------------------------------
class TextItem(QGraphicsTextItem):
    def __init__(self, text: str, pos: QPointF, text_color: QColor, font_size: int):
        super().__init__(text)
        self.text_color = text_color
        self.font_size = font_size
        font = QFont("Arial", font_size)
        self.setFont(font)
        self.setDefaultTextColor(text_color)
        self.setPos(pos)
        self.bg_color = QColor(0, 0, 0, 0)
        self.outline_enabled = False
        self.outline_color = QColor("#111111")
        self.outline_width = 2
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)

    def mouseDoubleClickEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        super().focusOutEvent(event)

    def set_bold(self, bold: bool) -> None:
        font = self.font()
        font.setBold(bool(bold))
        self.setFont(font)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        # Swallow the key while editing so it cannot bubble out and delete
        # the item the user is typing in.
        if item_is_text_editing(self) and event.key() in (
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
        ):
            event.accept()

    def paint(self, painter: QPainter, option, widget=None):
        painter.save()
        rect = self.boundingRect()
        if self.bg_color.alpha() > 0:
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.setBrush(QBrush(self.bg_color))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        if self.outline_enabled and self.outline_width > 0 and self.toPlainText():
            path = QPainterPath()
            painter.setFont(self.font())
            metrics = painter.fontMetrics()
            y = float(metrics.ascent())
            for line in self.toPlainText().split("\n"):
                path.addText(QPointF(0, y), self.font(), line)
                y += metrics.lineSpacing()
            painter.setPen(QPen(self.outline_color, self.outline_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawPath(path)
        else:
            pen = QPen(QColor(180, 180, 180, 120), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)
        painter.restore()
        super().paint(painter, option, widget)


# ---------------------------------------------------------------------------
# CalloutItem
# ---------------------------------------------------------------------------
class CalloutItem(QGraphicsItem):
    DEFAULT_W = 160
    DEFAULT_H = 80

    def __init__(self, pos: QPointF, pen_color: QColor, fill_color: QColor,
                 text_color: QColor, line_width: int, font_size: int):
        super().__init__()
        self.pen_color = pen_color
        self.fill_color = fill_color
        self.text_color = text_color
        self.line_width = line_width
        self.font_size = font_size
        self.stroke_enabled = True
        self._rect = QRectF(0, 0, self.DEFAULT_W, self.DEFAULT_H)
        self._text = "Callout"
        self._editing = False

        self._doc = QTextDocument()
        self._doc.setPlainText(self._text)
        self._doc.setDefaultFont(QFont("Arial", font_size))
        self._doc.setTextWidth(self._rect.width() - 16)

        self.setPos(pos)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        self.handles = []
        self._resizing = False
        self._resize_handle_index = None
        self._resize_start_pos = None
        self._resize_start_rect = None
        for i in range(8):
            h = ResizeHandle(i, self)
            self.handles.append(h)
        self._update_handles()
        self._show_handles(False)

    def _show_handles(self, visible: bool):
        for h in self.handles:
            h.setVisible(visible)

    def _update_handles(self):
        r = self._rect
        positions = [
            QPointF(r.left(),          r.top()),
            QPointF(r.center().x(),    r.top()),
            QPointF(r.right(),         r.top()),
            QPointF(r.left(),          r.center().y()),
            QPointF(r.right(),         r.center().y()),
            QPointF(r.left(),          r.bottom()),
            QPointF(r.center().x(),    r.bottom()),
            QPointF(r.right(),         r.bottom()),
        ]
        for h, pos in zip(self.handles, positions):
            h.setPos(pos)

    def boundingRect(self) -> QRectF:
        pointer_h = 16
        pad = self.line_width / 2.0 + HANDLE_HALF + 8
        return self._rect.adjusted(-pad, -pad, pad, pointer_h + pad)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._rect
        pointer_h = 16

        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        # Triangular pointer at bottom-left
        ptr_base_x = r.left() + 20
        ptr_tip = QPointF(r.left() + 8, r.bottom() + pointer_h)
        path.moveTo(ptr_base_x, r.bottom())
        path.lineTo(ptr_tip)
        path.lineTo(ptr_base_x + 20, r.bottom())
        path.closeSubpath()

        if self.stroke_enabled and self.line_width > 0:
            pen = QPen(self.pen_color, self.line_width)
        else:
            pen = QPen(Qt.PenStyle.NoPen)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.fill_color))
        painter.drawPath(path)

        # Draw text
        painter.save()
        painter.translate(r.left() + 8, r.top() + 6)
        self._doc.setTextWidth(r.width() - 16)
        text_color = self.text_color
        self._doc.setDefaultStyleSheet(f"body {{ color: {text_color.name()}; }}")
        self._doc.drawContents(painter)
        painter.restore()

    def mouseDoubleClickEvent(self, event):
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            None, "Edit Callout", "Text:", text=self._text
        )
        if ok:
            self._text = text
            self._doc.setPlainText(text)
            self.update()
        event.accept()

    def _start_resize(self, pos_index: int, scene_pos: QPointF):
        self._resizing = True
        self._resize_handle_index = pos_index
        self._resize_start_pos = scene_pos
        self._resize_start_rect = QRectF(self._rect)

    def _do_resize(self, pos_index: int, scene_pos: QPointF):
        if not self._resizing:
            return
        delta = scene_pos - self._resize_start_pos
        r = QRectF(self._resize_start_rect)

        if pos_index == HandlePos.TL:
            r.setTopLeft(r.topLeft() + delta)
        elif pos_index == HandlePos.T:
            r.setTop(r.top() + delta.y())
        elif pos_index == HandlePos.TR:
            r.setTopRight(r.topRight() + delta)
        elif pos_index == HandlePos.L:
            r.setLeft(r.left() + delta.x())
        elif pos_index == HandlePos.R:
            r.setRight(r.right() + delta.x())
        elif pos_index == HandlePos.BL:
            r.setBottomLeft(r.bottomLeft() + delta)
        elif pos_index == HandlePos.B:
            r.setBottom(r.bottom() + delta.y())
        elif pos_index == HandlePos.BR:
            r.setBottomRight(r.bottomRight() + delta)

        r = r.normalized()
        if r.width() < 40:
            r.setWidth(40)
        if r.height() < 30:
            r.setHeight(30)
        self.prepareGeometryChange()
        self._rect = r
        self._update_handles()
        self.update()

    def _end_resize(self):
        self._resizing = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._show_handles(bool(value))
        return super().itemChange(change, value)

    def set_rect(self, r: QRectF):
        self.prepareGeometryChange()
        self._rect = r.normalized()
        self._update_handles()
        self.update()


# ---------------------------------------------------------------------------
# StampItem
# ---------------------------------------------------------------------------
class StampItem(QGraphicsTextItem):
    def __init__(self, stamp: str, pos: QPointF):
        super().__init__(stamp)
        font = QFont("Segoe UI Emoji", 36)
        self.setFont(font)
        self.setPos(pos)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)


# ---------------------------------------------------------------------------
# ImageOverlayItem
# ---------------------------------------------------------------------------
class ImageOverlayItem(ResizableMixin, QGraphicsPixmapItem):
    def __init__(self, pixmap: QPixmap, pos: QPointF):
        super().__init__(pixmap)
        self._original_pixmap = pixmap
        self._current_rect = QRectF(0, 0, pixmap.width(), pixmap.height())
        self.setPos(pos)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.stroke_enabled = False
        self.pen_color = QColor("#ffffff")
        self.line_width = 2
        self._init_handles()

    def paint(self, painter: QPainter, option, widget=None):
        super().paint(painter, option, widget)
        if self.stroke_enabled and self.line_width > 0:
            painter.setPen(QPen(self.pen_color, self.line_width))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawRect(self.boundingRect())

    def _get_rect(self) -> QRectF:
        return self._current_rect

    def _set_rect(self, r: QRectF):
        self._current_rect = r
        scaled = self._original_pixmap.scaled(
            int(r.width()), int(r.height()),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self.setPixmap(scaled)

    def itemChange(self, change, value):
        return ResizableMixin.itemChange(self, change, value)


class StrokeItem(QGraphicsItem):
    """One freehand stroke. Points stay in the item's local coordinates."""

    def __init__(self, color: QColor, width: int, highlighter: bool = False):
        super().__init__()
        self.highlighter = highlighter
        self.line_width = max(1, int(width))
        self.pen_color = QColor(color)
        if highlighter:
            self.pen_color.setAlpha(96)
            self.line_width = max(self.line_width, 12)
        self._points: list[QPointF] = []
        self._path = QPainterPath()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def add_point(self, point: QPointF) -> None:
        self.prepareGeometryChange()
        self._points.append(QPointF(point))
        self._rebuild()
        self.update()

    def _rebuild(self) -> None:
        points = self._points
        path = QPainterPath()
        if not points:
            self._path = path
            return
        path.moveTo(points[0])
        if len(points) == 2:
            path.lineTo(points[1])
        elif len(points) > 2:
            for index in range(1, len(points) - 1):
                current = points[index]
                nxt = points[index + 1]
                mid = QPointF(
                    (current.x() + nxt.x()) / 2.0,
                    (current.y() + nxt.y()) / 2.0,
                )
                path.quadTo(current, mid)
            path.lineTo(points[-1])
        self._path = path

    def boundingRect(self) -> QRectF:
        extra = self.line_width / 2.0 + 8.0
        return self._path.boundingRect().adjusted(-extra, -extra, extra, extra)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self.line_width + 8)
        if self._path.isEmpty():
            return self._path
        return stroker.createStroke(self._path)

    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(
            self.pen_color,
            self.line_width,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        if len(self._points) == 1:
            painter.drawPoint(self._points[0])
        elif len(self._points) > 1:
            painter.drawPath(self._path)


class BlurItem(QGraphicsRectItem):
    """Pixelate the picture underneath. Used to redact part of a snip."""

    def __init__(self, rect: QRectF, block: int = 14):
        super().__init__(rect)
        self.block = max(4, int(block))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    def boundingRect(self) -> QRectF:
        return QGraphicsRectItem.boundingRect(self).adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget=None):
        scene = self.scene()
        background = None
        if scene is not None:
            for item in scene.items():
                if isinstance(item, QGraphicsPixmapItem) and item.zValue() < 0:
                    background = item
                    break
        rect = self.rect().normalized()
        block = self.block
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        if background is None:
            painter.setBrush(QBrush(QColor(80, 80, 80)))
            painter.drawRect(rect)
            return
        image = background.pixmap().toImage()
        y = int(rect.top())
        while y < rect.bottom():
            x = int(rect.left())
            while x < rect.right():
                scene_point = self.mapToScene(QPointF(x + block / 2, y + block / 2))
                local = background.mapFromScene(scene_point)
                px = max(0, min(image.width() - 1, int(local.x())))
                py = max(0, min(image.height() - 1, int(local.y())))
                painter.setBrush(QBrush(image.pixelColor(px, py)))
                painter.drawRect(x, y, block, block)
                x += block
            y += block


class NumberItem(QGraphicsItem):
    """A numbered step marker."""

    def __init__(self, number: int, pos: QPointF, color: QColor):
        super().__init__()
        self.number = max(1, int(number))
        self.color = QColor(color)
        self.setPos(pos)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def boundingRect(self) -> QRectF:
        return QRectF(-4, -4, 44, 44)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.setBrush(QBrush(self.color))
        painter.drawEllipse(0, 0, 36, 36)
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont("Arial", 14, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, 36, 36), int(Qt.AlignmentFlag.AlignCenter), str(self.number))
