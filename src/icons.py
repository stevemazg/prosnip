"""In-house toolbar icons. Drawn here, not taken from another product."""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def tool_icon(kind: str, colour: str, size: int = 24) -> QIcon:
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.setDevicePixelRatio(scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _draw(painter, kind, size)
    painter.end()
    return QIcon(pixmap)


def _draw(painter: QPainter, kind: str, size: int) -> None:
    s = size
    if kind in {"favourites", "star"}:
        path = QPainterPath()
        path.moveTo(s * 0.50, s * 0.12)
        for x, y in ((0.62, 0.38), (0.90, 0.40), (0.70, 0.60), (0.76, 0.88), (0.50, 0.74), (0.24, 0.88), (0.30, 0.60), (0.10, 0.40), (0.38, 0.38)):
            path.lineTo(s * x, s * y)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "arrow":
        painter.drawLine(QPointF(s * 0.18, s * 0.78), QPointF(s * 0.72, s * 0.24))
        head = QPainterPath()
        head.moveTo(s * 0.86, s * 0.12)
        head.lineTo(s * 0.58, s * 0.22)
        head.lineTo(s * 0.70, s * 0.40)
        head.closeSubpath()
        painter.setBrush(painter.pen().color())
        painter.drawPath(head)
    elif kind == "text":
        painter.drawLine(QPointF(s * 0.22, s * 0.22), QPointF(s * 0.78, s * 0.22))
        painter.drawLine(QPointF(s * 0.50, s * 0.22), QPointF(s * 0.50, s * 0.80))
        painter.drawLine(QPointF(s * 0.34, s * 0.80), QPointF(s * 0.66, s * 0.80))
    elif kind == "callout":
        painter.drawRoundedRect(QRectF(s * 0.12, s * 0.14, s * 0.76, s * 0.48), 3, 3)
        tail = QPainterPath()
        tail.moveTo(s * 0.28, s * 0.62)
        tail.lineTo(s * 0.22, s * 0.86)
        tail.lineTo(s * 0.48, s * 0.62)
        painter.drawPath(tail)
    elif kind == "rect":
        painter.drawRoundedRect(QRectF(s * 0.16, s * 0.22, s * 0.46, s * 0.40), 2, 2)
        painter.drawEllipse(QRectF(s * 0.40, s * 0.38, s * 0.42, s * 0.42))
    elif kind == "stamp":
        painter.drawRoundedRect(QRectF(s * 0.28, s * 0.34, s * 0.44, s * 0.28), 2, 2)
        painter.drawLine(QPointF(s * 0.40, s * 0.34), QPointF(s * 0.40, s * 0.18))
        painter.drawLine(QPointF(s * 0.60, s * 0.34), QPointF(s * 0.60, s * 0.18))
        painter.drawLine(QPointF(s * 0.36, s * 0.18), QPointF(s * 0.64, s * 0.18))
    elif kind == "fill":
        painter.drawRoundedRect(QRectF(s * 0.18, s * 0.42, s * 0.40, s * 0.36), 2, 2)
        painter.drawLine(QPointF(s * 0.48, s * 0.28), QPointF(s * 0.78, s * 0.18))
        painter.drawEllipse(QRectF(s * 0.70, s * 0.12, s * 0.12, s * 0.12))
    elif kind == "select":
        painter.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.50, s * 0.88))
        painter.drawLine(QPointF(s * 0.12, s * 0.50), QPointF(s * 0.88, s * 0.50))
        painter.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.40, s * 0.26))
        painter.drawLine(QPointF(s * 0.50, s * 0.12), QPointF(s * 0.60, s * 0.26))
    elif kind == "editor":
        painter.drawLine(QPointF(s * 0.20, s * 0.78), QPointF(s * 0.62, s * 0.22))
        painter.drawLine(QPointF(s * 0.62, s * 0.22), QPointF(s * 0.78, s * 0.34))
        painter.drawLine(QPointF(s * 0.18, s * 0.82), QPointF(s * 0.36, s * 0.78))
    elif kind == "library":
        for row in range(3):
            for col in range(3):
                painter.drawRect(int(s * (0.16 + col * 0.24)), int(s * (0.16 + row * 0.24)), int(s * 0.16), int(s * 0.16))
    elif kind == "capture":
        painter.drawRoundedRect(QRectF(s * 0.14, s * 0.28, s * 0.72, s * 0.50), 3, 3)
        painter.drawEllipse(QRectF(s * 0.38, s * 0.40, s * 0.24, s * 0.24))
    elif kind == "create":
        painter.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        painter.drawLine(QPointF(s * 0.50, s * 0.32), QPointF(s * 0.50, s * 0.68))
        painter.drawLine(QPointF(s * 0.32, s * 0.50), QPointF(s * 0.68, s * 0.50))
    elif kind == "more":
        painter.drawLine(QPointF(s * 0.22, s * 0.40), QPointF(s * 0.50, s * 0.68))
        painter.drawLine(QPointF(s * 0.50, s * 0.68), QPointF(s * 0.78, s * 0.40))
    elif kind == "pen":
        painter.drawLine(QPointF(s * 0.22, s * 0.78), QPointF(s * 0.72, s * 0.22))
    elif kind == "highlight":
        painter.setPen(QPen(painter.pen().color(), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(s * 0.16, s * 0.62), QPointF(s * 0.84, s * 0.38))
    elif kind == "number":
        painter.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.68, s * 0.68))
        painter.drawText(QRectF(0, 0, s, s), int(Qt.AlignmentFlag.AlignCenter), "1")
    elif kind == "eraser":
        painter.drawRoundedRect(QRectF(s * 0.22, s * 0.30, s * 0.56, s * 0.28), 2, 2)
    elif kind == "blur":
        painter.setBrush(painter.pen().color())
        for i, x in enumerate((0.22, 0.42, 0.62)):
            painter.drawEllipse(QRectF(s * x, s * (0.28 + (i % 2) * 0.12), s * 0.16, s * 0.16))
    elif kind == "ellipse":
        painter.drawEllipse(QRectF(s * 0.16, s * 0.24, s * 0.68, s * 0.50))
    elif kind == "polygon":
        painter.drawLine(QPointF(s * 0.50, s * 0.16), QPointF(s * 0.84, s * 0.40))
        painter.drawLine(QPointF(s * 0.84, s * 0.40), QPointF(s * 0.70, s * 0.82))
        painter.drawLine(QPointF(s * 0.70, s * 0.82), QPointF(s * 0.30, s * 0.82))
        painter.drawLine(QPointF(s * 0.30, s * 0.82), QPointF(s * 0.16, s * 0.40))
        painter.drawLine(QPointF(s * 0.16, s * 0.40), QPointF(s * 0.50, s * 0.16))
    elif kind == "spotlight":
        painter.drawEllipse(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44))
        painter.drawLine(QPointF(s * 0.18, s * 0.18), QPointF(s * 0.30, s * 0.30))
        painter.drawLine(QPointF(s * 0.82, s * 0.18), QPointF(s * 0.70, s * 0.30))
        painter.drawLine(QPointF(s * 0.18, s * 0.82), QPointF(s * 0.30, s * 0.70))
        painter.drawLine(QPointF(s * 0.82, s * 0.82), QPointF(s * 0.70, s * 0.70))
    elif kind == "cutout":
        painter.drawRect(QRectF(s * 0.16, s * 0.20, s * 0.68, s * 0.60))
        painter.drawLine(QPointF(s * 0.16, s * 0.50), QPointF(s * 0.84, s * 0.50))
    elif kind == "image":
        painter.drawRect(QRectF(s * 0.16, s * 0.22, s * 0.68, s * 0.54))
        painter.drawLine(QPointF(s * 0.16, s * 0.60), QPointF(s * 0.40, s * 0.42))
        painter.drawLine(QPointF(s * 0.40, s * 0.42), QPointF(s * 0.84, s * 0.64))
    elif kind == "crop":
        painter.drawLine(QPointF(s * 0.22, s * 0.22), QPointF(s * 0.22, s * 0.42))
        painter.drawLine(QPointF(s * 0.22, s * 0.22), QPointF(s * 0.42, s * 0.22))
        painter.drawLine(QPointF(s * 0.78, s * 0.78), QPointF(s * 0.78, s * 0.58))
        painter.drawLine(QPointF(s * 0.78, s * 0.78), QPointF(s * 0.58, s * 0.78))
    elif kind in {"screenpick", "pick"}:
        painter.drawEllipse(QRectF(s * 0.16, s * 0.16, s * 0.40, s * 0.40))
        painter.drawLine(QPointF(s * 0.48, s * 0.48), QPointF(s * 0.80, s * 0.80))
    else:
        painter.drawEllipse(QRectF(s * 0.28, s * 0.28, s * 0.44, s * 0.44))
