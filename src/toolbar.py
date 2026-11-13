from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QComboBox,
    QSpinBox, QLabel, QFrame, QColorDialog, QSizePolicy, QApplication,
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QIcon, QPen, QBrush, QFont
from PyQt6.QtCore import pyqtSignal, Qt, QSize

from colour import FORMATS, ColourHistory, parse_hex
from styles import (
    STYLES, QuickStyle, DEFAULT_STYLE,
    apply_combo_contrast, colour_swatch_icon, with_tooltip_style,
)
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
    screen_pick_requested = pyqtSignal()
    format_changed = pyqtSignal(str)

    def __init__(self, parent=None, history: ColourHistory | None = None):
        super().__init__(parent)
        self._current_tool = "select"
        self._tool_buttons = {}
        self._pen_color = DEFAULT_STYLE.pen_color
        self._history = history if history is not None else ColourHistory()
        self._swatch_buttons = []
        self._build_ui()
        self.setMinimumWidth(96)
        self._controls = []
        self.setStyleSheet(with_tooltip_style("""
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
                border-color: #ffffff;
                border-width: 2px;
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
                color: #f2f2f2;
                font-size: 13px;
                font-weight: 600;
            }
            QComboBox, QSpinBox {
                font-size: 13px;
                min-height: 22px;
            }
        """))
        apply_combo_contrast(self._style_combo)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Tool buttons. Icons are 40px and the checked state is the active tool.
        for tool_id, label, icon_fn in TOOL_DEFS:
            btn = QPushButton()
            btn.setCheckable(tool_id != "screenpick")
            btn.setIcon(_make_icon(icon_fn, 40))
            btn.setIconSize(QSize(40, 40))
            btn.setFixedSize(88, 56)
            btn.setToolTip(label)
            btn.clicked.connect(lambda checked, t=tool_id: self._on_tool_clicked(t))
            self._tool_buttons[tool_id] = btn
            layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._tool_buttons["select"].setChecked(True)

        layout.addWidget(_divider())

        # Quick styles
        lbl_style = QLabel("Style")
        lbl_style.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_style)
        self._style_combo = QComboBox()
        self._style_combo.setFixedHeight(26)
        for name, style in STYLES.items():
            self._style_combo.addItem(colour_swatch_icon(style.pen_color), name)
        apply_combo_contrast(self._style_combo)
        self._style_combo.setToolTip(self._style_combo.currentText())
        self._style_combo.currentTextChanged.connect(self._on_style_changed)
        layout.addWidget(self._style_combo)

        lbl_format = QLabel("Code")
        lbl_format.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_format)
        self._format_combo = QComboBox()
        self._format_combo.setFixedHeight(28)
        for key in FORMATS:
            self._format_combo.addItem(key.upper(), key)
        index = self._format_combo.findData(self._history.format)
        if index >= 0:
            self._format_combo.setCurrentIndex(index)
        apply_combo_contrast(self._format_combo)
        self._format_combo.setToolTip("Colour code format")
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        layout.addWidget(self._format_combo)

        self._swatch_row = QWidget()
        self._swatch_layout = QVBoxLayout(self._swatch_row)
        self._swatch_layout.setContentsMargins(0, 0, 0, 0)
        self._swatch_layout.setSpacing(4)
        layout.addWidget(self._swatch_row)
        self.refresh_swatches()

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
        self._lw_spin.setRange(1, 16)
        self._lw_spin.setToolTip("Line and pen thickness (2, 4, 8, 12)")
        self._lw_spin.setValue(DEFAULT_STYLE.line_width)
        self._lw_spin.setFixedHeight(32)
        self._lw_spin.valueChanged.connect(self.line_width_changed.emit)
        layout.addWidget(self._lw_spin)

        # Font size
        lbl_fs = QLabel("Font")
        lbl_fs.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_fs)
        self._fs_spin = QSpinBox()
        self._fs_spin.setRange(8, 48)
        self._fs_spin.setValue(DEFAULT_STYLE.font_size)
        self._fs_spin.setFixedHeight(32)
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

    def _on_format_changed(self, _index: int):
        fmt = self._format_combo.currentData()
        if not fmt:
            return
        self._history.set_format(str(fmt))
        self.refresh_swatches()
        self.format_changed.emit(str(fmt))

    def refresh_swatches(self):
        while self._swatch_layout.count():
            item = self._swatch_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._swatch_buttons = []
        for code in self._history.colours:
            button = QPushButton()
            button.setFixedSize(88, 22)
            button.setToolTip(f"Copy {self._history.display(code)}")
            parsed = parse_hex(code)
            colour = f"#{parsed[0]:02x}{parsed[1]:02x}{parsed[2]:02x}" if parsed else "#000000"
            button.setStyleSheet(
                f"background-color: {colour}; border: 1px solid #ffffff; border-radius: 3px;"
            )
            button.clicked.connect(lambda _checked=False, hex_code=code: self._recopy_swatch(hex_code))
            self._swatch_layout.addWidget(button)
            self._swatch_buttons.append(button)

    def reload_history(self):
        self._history.load()
        index = self._format_combo.findData(self._history.format)
        if index >= 0 and index != self._format_combo.currentIndex():
            self._format_combo.blockSignals(True)
            self._format_combo.setCurrentIndex(index)
            self._format_combo.blockSignals(False)
        self.refresh_swatches()

    def _recopy_swatch(self, hex_code: str):
        text = self._history.display(hex_code)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        parsed = parse_hex(hex_code)
        if parsed is not None:
            self.set_pen_colour(QColor(*parsed))
            self.pen_color_changed.emit(self._pen_color)

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

    def _on_style_changed(self, name: str):
        if name in STYLES:
            style = STYLES[name]
            self._pen_color = style.pen_color
            self._update_color_btn()
            self._lw_spin.setValue(style.line_width)
            self._fs_spin.setValue(style.font_size)
            self._style_combo.setToolTip(name)
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

    def set_pen_colour(self, color: QColor):
        self._pen_color = QColor(color)
        self._update_color_btn()

    def set_tool(self, tool_id: str):
        if tool_id not in self._tool_buttons or tool_id == "screenpick":
            tool_id = self._current_tool
        for tid, btn in self._tool_buttons.items():
            btn.setChecked(tid == tool_id)
        self._current_tool = tool_id
