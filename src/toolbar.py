from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGridLayout, QPushButton, QSizePolicy,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush, QFont
from PyQt6.QtCore import pyqtSignal, Qt, QSize

from layout import tool_column_layout
from styles import with_tooltip_style
from stamp_picker import StampPickerDialog


def _make_icon(draw_fn, size=40) -> QIcon:
    """Draw at 2× so the icon stays sharp on a high-DPI screen."""
    scale = 2
    pix = QPixmap(size * scale, size * scale)
    pix.setDevicePixelRatio(scale)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(painter, size)
    painter.end()
    return QIcon(pix)


def _pt(s, x, y):
    from PyQt6.QtCore import QPoint
    return QPoint(int(s * x), int(s * y))


def _icon_select(p, s):
    from PyQt6.QtGui import QPolygon
    p.setPen(QPen(QColor("#f2f2f2"), max(1.6, s * 0.05)))
    p.setBrush(QBrush(QColor("#f2f2f2")))
    p.drawPolygon(QPolygon([
        _pt(s, 0.16, 0.12), _pt(s, 0.16, 0.78), _pt(s, 0.34, 0.60),
        _pt(s, 0.46, 0.88), _pt(s, 0.56, 0.84), _pt(s, 0.44, 0.56),
        _pt(s, 0.70, 0.56),
    ]))


def _icon_arrow(p, s):
    from PyQt6.QtGui import QPolygon
    p.setPen(QPen(QColor("#e63946"), max(2.0, s * 0.07), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(_pt(s, 0.16, 0.84), _pt(s, 0.72, 0.28))
    p.setPen(QPen(Qt.PenStyle.NoPen))
    p.setBrush(QBrush(QColor("#e63946")))
    p.drawPolygon(QPolygon([
        _pt(s, 0.86, 0.14), _pt(s, 0.58, 0.22), _pt(s, 0.70, 0.42),
    ]))


def _icon_text(p, s):
    p.setPen(QPen(QColor("#f2f2f2")))
    font = QFont("Arial", max(10, int(s * 0.55)), QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(0, 0, s, s, int(Qt.AlignmentFlag.AlignCenter), "T")


def _icon_callout(p, s):
    from PyQt6.QtGui import QPolygon
    p.setPen(QPen(QColor("#f2f2f2"), max(1.6, s * 0.05)))
    p.setBrush(QBrush(QColor(242, 242, 242, 40)))
    p.drawRoundedRect(int(s * 0.12), int(s * 0.12), int(s * 0.76), int(s * 0.52), 4, 4)
    p.drawPolygon(QPolygon([
        _pt(s, 0.22, 0.64), _pt(s, 0.42, 0.64), _pt(s, 0.24, 0.88),
    ]))


def _icon_stamp(p, s):
    p.setPen(QPen(QColor("#2d6a4f"), max(2.0, s * 0.08), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawLine(_pt(s, 0.22, 0.52), _pt(s, 0.42, 0.74))
    p.drawLine(_pt(s, 0.42, 0.74), _pt(s, 0.80, 0.28))


def _icon_rect(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.8, s * 0.06)))
    p.setBrush(QBrush(QColor(242, 242, 242, 36)))
    margin = int(s * 0.16)
    p.drawRect(margin, margin, s - margin * 2, s - margin * 2)


def _icon_ellipse(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.8, s * 0.06)))
    p.setBrush(QBrush(QColor(242, 242, 242, 36)))
    margin = int(s * 0.16)
    p.drawEllipse(margin, margin, s - margin * 2, s - margin * 2)


def _icon_image(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.6, s * 0.05)))
    p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    p.drawRect(int(s * 0.12), int(s * 0.18), int(s * 0.76), int(s * 0.64))
    p.drawLine(_pt(s, 0.12, 0.70), _pt(s, 0.36, 0.46))
    p.drawLine(_pt(s, 0.36, 0.46), _pt(s, 0.52, 0.60))
    p.drawLine(_pt(s, 0.52, 0.60), _pt(s, 0.88, 0.32))


def _icon_pen(p, s):
    pen = QPen(QColor("#e63946"), max(2.0, s * 0.07), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawLine(_pt(s, 0.18, 0.82), _pt(s, 0.72, 0.28))
    p.drawLine(_pt(s, 0.72, 0.28), _pt(s, 0.84, 0.18))


def _icon_highlight(p, s):
    pen = QPen(QColor(244, 162, 97, 220), max(6.0, s * 0.22), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(_pt(s, 0.14, 0.62), _pt(s, 0.86, 0.40))


def _icon_pick(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.8, s * 0.06)))
    p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    p.drawEllipse(int(s * 0.14), int(s * 0.14), int(s * 0.48), int(s * 0.48))
    p.drawLine(_pt(s, 0.56, 0.56), _pt(s, 0.84, 0.84))


def _icon_dropper(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.8, s * 0.06), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawLine(_pt(s, 0.62, 0.16), _pt(s, 0.30, 0.62))
    p.setBrush(QBrush(QColor("#e63946")))
    p.setPen(QPen(QColor("#f2f2f2"), max(1.4, s * 0.04)))
    p.drawEllipse(int(s * 0.16), int(s * 0.62), int(s * 0.28), int(s * 0.22))


def _icon_crop(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.8, s * 0.06)))
    p.drawLine(_pt(s, 0.28, 0.10), _pt(s, 0.28, 0.78))
    p.drawLine(_pt(s, 0.10, 0.78), _pt(s, 0.90, 0.78))
    p.setPen(QPen(QColor("#e63946"), max(1.6, s * 0.05), Qt.PenStyle.DashLine))
    p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    p.drawRect(int(s * 0.28), int(s * 0.22), int(s * 0.52), int(s * 0.46))


def _icon_blur(p, s):
    p.setPen(QPen(Qt.PenStyle.NoPen))
    p.setBrush(QBrush(QColor("#9aa0a6")))
    block = max(4, int(s * 0.22))
    for row in range(3):
        for col in range(3):
            shade = 90 + ((row + col) % 2) * 50
            p.setBrush(QBrush(QColor(shade, shade, shade)))
            p.drawRect(int(s * 0.12) + col * block, int(s * 0.12) + row * block, block - 1, block - 1)


def _icon_number(p, s):
    p.setPen(QPen(QColor("#ffffff"), max(1.5, s * 0.05)))
    p.setBrush(QBrush(QColor("#e63946")))
    p.drawEllipse(int(s * 0.12), int(s * 0.12), int(s * 0.76), int(s * 0.76))
    p.setPen(QPen(QColor("#ffffff")))
    font = QFont("Arial", max(10, int(s * 0.42)), QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(0, 0, s, s, int(Qt.AlignmentFlag.AlignCenter), "1")


def _icon_eraser(p, s):
    p.setPen(QPen(QColor("#f2f2f2"), max(1.6, s * 0.05)))
    p.setBrush(QBrush(QColor("#f4a261")))
    p.drawRoundedRect(int(s * 0.18), int(s * 0.28), int(s * 0.64), int(s * 0.36), 3, 3)
    p.drawRect(int(s * 0.18), int(s * 0.48), int(s * 0.64), int(s * 0.16))


TOOL_DEFS = [
    ("select", "Select (V)", _icon_select),
    ("arrow", "Arrow (A)", _icon_arrow),
    ("rect", "Rectangle (R)", _icon_rect),
    ("ellipse", "Ellipse (E)", _icon_ellipse),
    ("pen", "Pen (P)", _icon_pen),
    ("highlight", "Highlighter (H)", _icon_highlight),
    ("blur", "Blur (B)", _icon_blur),
    ("number", "Number (N)", _icon_number),
    ("text", "Text (T)", _icon_text),
    ("crop", "Crop (C)", _icon_crop),
    ("eraser", "Eraser", _icon_eraser),
    ("screenpick", "Colour picker (I)", _icon_dropper),
    ("callout", "Callout", _icon_callout),
    ("stamp", "Stamp", _icon_stamp),
    ("image", "Image", _icon_image),
    ("pick", "Pick colour from image", _icon_pick),
]


class ToolBar(QWidget):
    tool_changed = pyqtSignal(str)
    pen_color_changed = pyqtSignal(QColor)
    stamp_chosen = pyqtSignal(str)
    screen_pick_requested = pyqtSignal()

    def __init__(self, parent=None, history=None):
        super().__init__(parent)
        self._current_tool = "select"
        self._tool_buttons = {}
        self._pen_color = QColor("#e63946")
        self._history = history
        self._build_ui()
        self.arrange(1200)
        self.setStyleSheet(with_tooltip_style("""
            QWidget { background-color: #323232; }
            QPushButton {
                background-color: #383838;
                border: 1px solid #4a4a4a;
                border-radius: 4px;
                color: #e6e6e6;
                padding: 2px;
            }
            QPushButton:checked {
                background-color: #3d8ee6;
                border-color: #ffffff;
                border-width: 2px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
        """))

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        layout.addLayout(self._grid)

        for tool_id, label, icon_fn in TOOL_DEFS:
            btn = QPushButton()
            btn.setCheckable(tool_id != "screenpick")
            btn.setIcon(_make_icon(icon_fn, 32))
            btn.setIconSize(QSize(22, 22))
            btn.setFixedSize(32, 32)
            btn.setToolTip(label)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
            self._tool_buttons[tool_id] = btn
        self._tool_buttons["select"].setChecked(True)

    def arrange(self, available_height: int) -> None:
        """Lay every tool out in two columns, or three when the window is short."""
        count = len(TOOL_DEFS)
        columns, button = tool_column_layout(count, available_height)
        icon = max(18, button - 10)
        rows = (count + columns - 1) // columns
        while self._grid.count():
            self._grid.takeAt(0)
        for index, (tool_id, _label, _icon) in enumerate(TOOL_DEFS):
            btn = self._tool_buttons[tool_id]
            btn.setFixedSize(button, button)
            btn.setIconSize(QSize(icon, icon))
            row = index % rows
            column = index // rows
            self._grid.addWidget(btn, row, column)
        width = 8 + columns * button + max(0, columns - 1) * 4
        height = 8 + rows * button + max(0, rows - 1) * 4
        self.setFixedSize(width, height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _on_tool_clicked(self, tool_id: str):
        if tool_id == "screenpick":
            self.screen_pick_requested.emit()
            self.set_tool(self._current_tool)
            return
        # Uncheck all other tools
        for tid, btn in self._tool_buttons.items():
            if tid == "screenpick":
                continue
            btn.setChecked(tid == tool_id)
        self._current_tool = tool_id

        if tool_id == "stamp":
            stamp = StampPickerDialog.get_stamp(self)
            if stamp:
                self.stamp_chosen.emit(stamp)
                self.tool_changed.emit("stamp")
            else:
                # Revert to select
                self._on_tool_clicked("select")
            return

        self.tool_changed.emit(tool_id)

    def set_pen_colour(self, color: QColor):
        self._pen_color = QColor(color)

    def set_tool(self, tool_id: str):
        if tool_id not in self._tool_buttons or tool_id == "screenpick":
            tool_id = self._current_tool
        for tid, btn in self._tool_buttons.items():
            btn.setChecked(tid == tool_id)
        self._current_tool = tool_id
