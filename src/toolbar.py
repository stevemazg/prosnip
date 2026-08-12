from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QComboBox,
    QSpinBox, QLabel, QFrame, QColorDialog, QSizePolicy
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush, QFont
from PyQt6.QtCore import pyqtSignal, Qt, QSize

from styles import STYLES, QuickStyle, DEFAULT_STYLE
from stamp_picker import StampPickerDialog


def _make_icon(draw_fn, size=28) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_fn(p, size)
    p.end()
    return QIcon(pix)


def _icon_select(p, s):
    pen = QPen(QColor("#cccccc"), 2)
    p.setPen(pen)
    # Arrow cursor shape
    pts = [
        (4, 4), (4, 22), (9, 17), (12, 24), (14, 23), (11, 16), (18, 16)
    ]
    from PyQt6.QtGui import QPolygon
    from PyQt6.QtCore import QPoint
    poly = QPolygon([QPoint(x, y) for x, y in pts])
    p.setBrush(QBrush(QColor("#cccccc")))
    p.drawPolygon(poly)


def _icon_arrow(p, s):
    pen = QPen(QColor("#e63946"), 2)
    p.setPen(pen)
    p.drawLine(4, s - 4, s - 4, 4)
    p.setBrush(QBrush(QColor("#e63946")))
    p.setPen(Qt.PenStyle.NoPen)
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QPolygon
    tip = QPoint(s - 4, 4)
    poly = QPolygon([tip, QPoint(s - 12, 4), QPoint(s - 4, 12)])
    p.drawPolygon(poly)


def _icon_text(p, s):
    p.setPen(QPen(QColor("#cccccc"), 2))
    font = QFont("Arial", 16, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(6, s - 4, "T")


def _icon_callout(p, s):
    p.setPen(QPen(QColor("#cccccc"), 2))
    p.setBrush(QBrush(QColor(100, 100, 100, 80)))
    p.drawRoundedRect(2, 2, s - 8, s - 12, 4, 4)
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QPolygon
    poly = QPolygon([QPoint(4, s - 10), QPoint(10, s - 10), QPoint(6, s - 2)])
    p.setBrush(QBrush(QColor(100, 100, 100, 80)))
    p.drawPolygon(poly)


def _icon_stamp(p, s):
    p.setPen(QPen(QColor("#cccccc"), 1))
    font = QFont("Arial", 14)
    p.setFont(font)
    p.drawText(4, s - 4, "✅")


def _icon_rect(p, s):
    p.setPen(QPen(QColor("#cccccc"), 2))
    p.setBrush(QBrush(QColor(100, 100, 100, 60)))
    p.drawRect(4, 4, s - 8, s - 8)


def _icon_ellipse(p, s):
    p.setPen(QPen(QColor("#cccccc"), 2))
    p.setBrush(QBrush(QColor(100, 100, 100, 60)))
    p.drawEllipse(4, 4, s - 8, s - 8)


def _icon_image(p, s):
    p.setPen(QPen(QColor("#cccccc"), 2))
    p.drawRect(3, 5, s - 6, s - 10)
    p.drawLine(3, s - 8, 9, s - 14)
    p.drawLine(9, s - 14, 14, s - 10)
    p.drawLine(14, s - 10, s - 3, s - 8)


def _icon_crop(p, s):
    p.setPen(QPen(QColor("#cccccc"), 2))
    # L-shape guides
    p.drawLine(8, 2, 8, s - 8)
    p.drawLine(2, s - 8, s - 2, s - 8)
    p.setPen(QPen(QColor("#e63946"), 2, Qt.PenStyle.DashLine))
    p.drawRect(8, 8, s - 12, s - 16)


TOOL_DEFS = [
    ("select",  "Select",       _icon_select),
    ("arrow",   "Arrow",        _icon_arrow),
    ("text",    "Text",         _icon_text),
    ("callout", "Callout",      _icon_callout),
    ("stamp",   "Stamp",        _icon_stamp),
    ("rect",    "Rectangle",    _icon_rect),
    ("ellipse", "Ellipse",      _icon_ellipse),
    ("image",   "Image",        _icon_image),
    ("crop",    "Crop",         _icon_crop),
]


def _divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #555555;")
    return line


class ToolBar(QWidget):
    tool_changed = pyqtSignal(str)
    style_changed = pyqtSignal(object)  # QuickStyle
    pen_color_changed = pyqtSignal(QColor)
    line_width_changed = pyqtSignal(int)
    font_size_changed = pyqtSignal(int)
    undo_requested = pyqtSignal()
    delete_requested = pyqtSignal()
    stamp_chosen = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_tool = "select"
        self._tool_buttons = {}
        self._pen_color = DEFAULT_STYLE.pen_color
        self._build_ui()
        self.setFixedWidth(56)
        self.setStyleSheet("""
            QWidget { background-color: #1e1e1e; }
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                color: #cccccc;
                font-size: 11px;
                padding: 2px;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border-color: #0078d4;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
            }
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #cccccc;
                font-size: 10px;
            }
            QSpinBox {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #cccccc;
                font-size: 10px;
            }
            QLabel {
                color: #888888;
                font-size: 9px;
            }
        """)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(3)

        # Tool buttons
        for tool_id, label, icon_fn in TOOL_DEFS:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setIcon(_make_icon(icon_fn))
            btn.setIconSize(QSize(24, 24))
            btn.setFixedHeight(36)
            btn.setToolTip(label)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
            self._tool_buttons[tool_id] = btn
            layout.addWidget(btn)

        self._tool_buttons["select"].setChecked(True)

        layout.addWidget(_divider())

        # Quick styles
        lbl_style = QLabel("Style")
        lbl_style.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_style)
        self._style_combo = QComboBox()
        self._style_combo.setFixedHeight(24)
        for name in STYLES:
            self._style_combo.addItem(name)
        self._style_combo.currentTextChanged.connect(self._on_style_changed)
        layout.addWidget(self._style_combo)

        # Color picker
        self._color_btn = QPushButton()
        self._color_btn.setFixedHeight(28)
        self._color_btn.setToolTip("Pen colour")
        self._update_color_btn()
        self._color_btn.clicked.connect(self._on_pick_color)
        layout.addWidget(self._color_btn)

        # Line width
        lbl_lw = QLabel("Width")
        lbl_lw.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_lw)
        self._lw_spin = QSpinBox()
        self._lw_spin.setRange(1, 10)
        self._lw_spin.setValue(DEFAULT_STYLE.line_width)
        self._lw_spin.setFixedHeight(24)
        self._lw_spin.valueChanged.connect(self.line_width_changed.emit)
        layout.addWidget(self._lw_spin)

        # Font size
        lbl_fs = QLabel("Font")
        lbl_fs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_fs)
        self._fs_spin = QSpinBox()
        self._fs_spin.setRange(8, 48)
        self._fs_spin.setValue(DEFAULT_STYLE.font_size)
        self._fs_spin.setFixedHeight(24)
        self._fs_spin.valueChanged.connect(self.font_size_changed.emit)
        layout.addWidget(self._fs_spin)

        layout.addWidget(_divider())

        # Undo
        btn_undo = QPushButton("↩")
        btn_undo.setFixedHeight(32)
        btn_undo.setToolTip("Undo (Ctrl+Z)")
        btn_undo.clicked.connect(self.undo_requested.emit)
        layout.addWidget(btn_undo)

        # Delete
        btn_del = QPushButton("🗑")
        btn_del.setFixedHeight(32)
        btn_del.setToolTip("Delete selected (Del)")
        btn_del.clicked.connect(self.delete_requested.emit)
        layout.addWidget(btn_del)

        layout.addStretch()

    def _on_tool_clicked(self, tool_id: str):
        # Uncheck all other tools
        for tid, btn in self._tool_buttons.items():
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

    def _on_style_changed(self, name: str):
        if name in STYLES:
            style = STYLES[name]
            self._pen_color = style.pen_color
            self._update_color_btn()
            self._lw_spin.setValue(style.line_width)
            self._fs_spin.setValue(style.font_size)
            self.style_changed.emit(style)

    def _on_pick_color(self):
        color = QColorDialog.getColor(self._pen_color, self, "Choose Pen Colour")
        if color.isValid():
            self._pen_color = color
            self._update_color_btn()
            self.pen_color_changed.emit(color)

    def _update_color_btn(self):
        pix = QPixmap(32, 16)
        pix.fill(self._pen_color)
        self._color_btn.setIcon(QIcon(pix))
        self._color_btn.setIconSize(QSize(32, 16))
        self._color_btn.setToolTip(f"Pen colour: {self._pen_color.name()}")

    def set_tool(self, tool_id: str):
        for tid, btn in self._tool_buttons.items():
            btn.setChecked(tid == tool_id)
        self._current_tool = tool_id
