"""Properties for the item that is selected, in the style of a small inspector."""

from PyQt6 import sip
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from items import (
    ARROW_STYLES,
    ArrowItem,
    CalloutItem,
    EllipseItem,
    ImageOverlayItem,
    RectItem,
    StampItem,
    StrokeItem,
    TextItem,
)

ARROW_LABELS = {
    "plain": "Plain",
    "dashed": "Dashed",
    "dotted": "Dotted",
    "double": "Double-headed",
    "tapered": "Tapered",
    "curved": "Curved",
}


def _annotations(items):
    kinds = (RectItem, EllipseItem, ArrowItem, TextItem, CalloutItem, StampItem, StrokeItem, ImageOverlayItem)
    return [item for item in items if isinstance(item, kinds)]


class PropertiesPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = None
        self._toolbar = None
        self._updating = False
        self._selected = []
        self.setFixedWidth(250)
        self.setStyleSheet(
            """
            QWidget { background: #1e1e1e; color: #f2f2f2; font-size: 13px; }
            QLabel { color: #f2f2f2; font-size: 13px; }
            QPushButton, QComboBox, QSpinBox {
                background: #2d2d2d; color: #f7f7f7;
                border: 1px solid #6a6a6a; border-radius: 4px;
                padding: 4px; min-height: 24px; font-size: 13px;
            }
            QCheckBox { color: #f2f2f2; font-size: 13px; spacing: 6px; }
            """
        )
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        title = QLabel("Properties")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #ffffff;")
        layout.addWidget(title)
        self._hint = QLabel("Select an item, or set the defaults for the next one.")
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        form = QFormLayout()
        form.setSpacing(8)
        self._colour_btn = QPushButton("Colour")
        self._colour_btn.clicked.connect(self._pick_colour)
        form.addRow("Colour", self._colour_btn)

        self._opacity = QSlider(Qt.Orientation.Horizontal)
        self._opacity.setRange(10, 100)
        self._opacity.setValue(100)
        self._opacity.valueChanged.connect(self._apply)
        form.addRow("Opacity", self._opacity)

        self._stroke_on = QCheckBox("Outline")
        self._stroke_on.stateChanged.connect(self._apply)
        form.addRow("", self._stroke_on)
        self._stroke_btn = QPushButton("Outline colour")
        self._stroke_btn.clicked.connect(self._pick_stroke)
        form.addRow("", self._stroke_btn)
        self._stroke_width = QSpinBox()
        self._stroke_width.setRange(1, 24)
        self._stroke_width.valueChanged.connect(self._apply)
        form.addRow("Outline width", self._stroke_width)

        self._arrow_style = QComboBox()
        for key in ARROW_STYLES:
            self._arrow_style.addItem(ARROW_LABELS[key], key)
        self._arrow_style.currentIndexChanged.connect(self._apply)
        form.addRow("Arrow style", self._arrow_style)

        self._font_size = QSpinBox()
        self._font_size.setRange(8, 72)
        self._font_size.valueChanged.connect(self._apply)
        form.addRow("Font size", self._font_size)

        self._bg_btn = QPushButton("Text background")
        self._bg_btn.clicked.connect(self._pick_background)
        form.addRow("", self._bg_btn)
        layout.addLayout(form)
        self._pick_btn = QPushButton("Pick colour from image")
        self._pick_btn.clicked.connect(self._start_eyedropper)
        layout.addWidget(self._pick_btn)
        layout.addStretch(1)
        self._colour = QColor("#e63946")
        self._stroke = QColor("#e63946")
        self._background = QColor(255, 255, 255, 0)

    def bind(self, scene, toolbar):
        self._scene = scene
        self._toolbar = toolbar
        scene.selectionChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        if self._scene is None or sip.isdeleted(self._scene):
            return
        self._selected = _annotations(self._scene.selectedItems())
        self._updating = True
        if self._selected:
            self._hint.setText("Editing the selected item.")
            item = self._selected[0]
            self._opacity.setValue(int(round(item.opacity() * 100)))
            self._load_item(item)
        else:
            self._hint.setText("Nothing selected. These settings apply to the next item.")
            self._opacity.setValue(int(round(self._scene.item_opacity * 100)))
            self._colour = QColor(self._scene.pen_color)
            self._stroke = QColor(self._scene.pen_color)
            self._stroke_width.setValue(max(6, self._scene.line_width))
            self._stroke_on.setChecked(True)
            index = self._arrow_style.findData(self._scene.arrow_style)
            if index >= 0:
                self._arrow_style.setCurrentIndex(index)
            self._font_size.setValue(self._scene.font_size)
        self._paint_colour_button(self._colour_btn, self._colour)
        self._paint_colour_button(self._stroke_btn, self._stroke)
        self._paint_colour_button(self._bg_btn, self._background)
        self._updating = False

    def _load_item(self, item):
        if isinstance(item, (RectItem, EllipseItem)):
            self._colour = QColor(item.fill_color)
            self._stroke = QColor(item.pen_color)
            self._stroke_on.setChecked(item.stroke_enabled)
            self._stroke_width.setValue(item.line_width)
        elif isinstance(item, ArrowItem):
            self._colour = QColor(item.pen_color)
            self._stroke = QColor(item.pen_color)
            self._stroke_on.setChecked(item.stroke_enabled)
            self._stroke_width.setValue(item.line_width)
            index = self._arrow_style.findData(item.style)
            if index >= 0:
                self._arrow_style.setCurrentIndex(index)
        elif isinstance(item, StrokeItem):
            self._colour = QColor(item.pen_color)
            self._stroke = QColor(item.pen_color)
            self._stroke_width.setValue(item.line_width)
            self._stroke_on.setChecked(True)
        elif isinstance(item, TextItem):
            self._colour = QColor(item.text_color)
            self._stroke = QColor(item.outline_color)
            self._stroke_on.setChecked(item.outline_enabled)
            self._stroke_width.setValue(item.outline_width)
            self._font_size.setValue(item.font_size)
            self._background = QColor(item.bg_color)
        elif isinstance(item, CalloutItem):
            self._colour = QColor(item.fill_color)
            self._stroke = QColor(item.pen_color)
            self._stroke_on.setChecked(item.stroke_enabled)
            self._stroke_width.setValue(item.line_width)
            self._font_size.setValue(item.font_size)
        elif isinstance(item, ImageOverlayItem):
            self._stroke = QColor(item.pen_color)
            self._stroke_on.setChecked(item.stroke_enabled)
            self._stroke_width.setValue(item.line_width)
        elif isinstance(item, StampItem):
            self._stroke_on.setChecked(False)

    def _paint_colour_button(self, button, colour: QColor):
        button.setStyleSheet(
            f"background: {colour.name()}; color: #111111; border: 2px solid #f2f2f2;"
        )

    def _pick_colour(self):
        colour = QColorDialog.getColor(self._colour, self, "Choose Colour", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if colour.isValid():
            self._colour = colour
            self._paint_colour_button(self._colour_btn, colour)
            self._apply()

    def _pick_stroke(self):
        colour = QColorDialog.getColor(self._stroke, self, "Outline Colour")
        if colour.isValid():
            self._stroke = colour
            self._paint_colour_button(self._stroke_btn, colour)
            self._apply()

    def _pick_background(self):
        colour = QColorDialog.getColor(
            self._background, self, "Text Background", QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if colour.isValid():
            self._background = colour
            self._paint_colour_button(self._bg_btn, colour)
            self._apply()

    def _start_eyedropper(self):
        if self._toolbar is not None:
            self._toolbar.set_tool("pick")
            self._toolbar.tool_changed.emit("pick")

    def _apply(self, *_args):
        if self._updating or self._scene is None:
            return
        opacity = self._opacity.value() / 100.0
        style = self._arrow_style.currentData()
        if not self._selected:
            self._scene.set_pen_color(self._colour)
            self._scene.set_line_width(self._stroke_width.value())
            self._scene.set_font_size(self._font_size.value())
            self._scene.arrow_style = style or "plain"
            self._scene.item_opacity = opacity
            if self._toolbar is not None:
                self._toolbar.set_pen_colour(self._colour)
            return
        for item in self._selected:
            item.setOpacity(opacity)
            self._write_item(item, style)
            item.update()

    def _write_item(self, item, arrow_style):
        if isinstance(item, (RectItem, EllipseItem)):
            item.fill_color = QColor(self._colour)
            item.pen_color = QColor(self._stroke)
            item.stroke_enabled = self._stroke_on.isChecked()
            item.line_width = self._stroke_width.value()
            item._apply_style()
        elif isinstance(item, ArrowItem):
            item.pen_color = QColor(self._colour)
            item.stroke_enabled = self._stroke_on.isChecked()
            item.line_width = max(1, self._stroke_width.value())
            if arrow_style:
                item.style = arrow_style
            item.update()
        elif isinstance(item, StrokeItem):
            colour = QColor(self._colour)
            if item.highlighter:
                colour.setAlpha(96)
            item.pen_color = colour
            item.line_width = max(1, self._stroke_width.value())
            item.update()
        elif isinstance(item, TextItem):
            item.text_color = QColor(self._colour)
            item.setDefaultTextColor(item.text_color)
            item.font_size = self._font_size.value()
            item.setFont(item.font())
            font = item.font()
            font.setPointSize(item.font_size)
            item.setFont(font)
            item.outline_enabled = self._stroke_on.isChecked()
            item.outline_color = QColor(self._stroke)
            item.outline_width = self._stroke_width.value()
            item.bg_color = QColor(self._background)
            item.update()
        elif isinstance(item, CalloutItem):
            item.fill_color = QColor(self._colour)
            item.pen_color = QColor(self._stroke)
            item.text_color = QColor(self._colour)
            item.stroke_enabled = self._stroke_on.isChecked()
            item.line_width = self._stroke_width.value()
            item.font_size = self._font_size.value()
            item.update()
        elif isinstance(item, ImageOverlayItem):
            item.pen_color = QColor(self._stroke)
            item.stroke_enabled = self._stroke_on.isChecked()
            item.line_width = self._stroke_width.value()
            item.update()
