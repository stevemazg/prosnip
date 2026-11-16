"""One slim options bar. It never grows, and the colour list is a popup."""

from PyQt6 import sip
from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QWidget,
    QWidgetAction,
    QApplication,
)

from colour import ColourHistory
from items import (
    ARROW_STYLES,
    ArrowItem,
    CalloutItem,
    EllipseItem,
    NumberItem,
    RectItem,
    StrokeItem,
    TextItem,
)
from styles import STYLES, DEFAULT_STYLE
from swatches import SwatchBook

PALETTE = (
    "#e63946", "#e76f51", "#f4a261", "#e9c46a",
    "#2a9d8f", "#2d6a4f", "#1d3557", "#3d8ee6",
    "#ffffff", "#f2f2f2", "#6c757d", "#111111",
)

ARROW_LABELS = {
    "plain": "Plain",
    "dashed": "Dashed",
    "dotted": "Dotted",
    "double": "Double-headed",
    "tapered": "Tapered",
    "curved": "Curved",
}

MENU_STYLE = """
QMenu { background-color: #2b2b2b; color: #e6e6e6; border: 1px solid #4a4a4a; }
QMenu::item { padding: 6px 18px; background: transparent; }
QMenu::item:selected { background-color: #3d8ee6; color: #ffffff; }
QLabel { color: #a0a0a0; background: transparent; }
"""


def _popup(title: str | None = None) -> QMenu:
    menu = QMenu()
    menu.setObjectName("ColourPopup" if title is None else title)
    menu.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
    menu.setStyleSheet(MENU_STYLE)
    return menu


class ToolOptions(QWidget):
    """Fixed-height options for the active tool or the selected item."""

    screen_pick_requested = pyqtSignal()
    pen_color_changed = pyqtSignal(QColor)

    def __init__(self, history: ColourHistory | None = None, swatches: SwatchBook | None = None, parent=None):
        super().__init__(parent)
        self._history = history if history is not None else ColourHistory()
        self._swatches = swatches if swatches is not None else SwatchBook(self._history.path)
        self._scene = None
        self._toolbar = None
        self._updating = False
        self._colour = QColor(DEFAULT_STYLE.pen_color)
        self._colour_menu = None
        self.setObjectName("ToolOptions")
        self.setFixedHeight(36)
        self.setMaximumHeight(40)
        self.setStyleSheet(
            """
            QWidget#ToolOptions { background: #323232; }
            QLabel { color: #a0a0a0; background: transparent; font-size: 12px; }
            QCheckBox { color: #e6e6e6; background: transparent; spacing: 4px; }
            QPushButton#ArrowStyle {
                background: #383838; color: #e6e6e6;
                border: 1px solid #4a4a4a; border-radius: 3px;
                padding: 2px 8px;
            }
            """
        )
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)

        self._colour_btn = QPushButton()
        self._colour_btn.setObjectName("ColourSwatch")
        self._colour_btn.setFixedSize(36, 22)
        self._colour_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._colour_btn.setToolTip("Colour")
        self._colour_btn.clicked.connect(self.open_colour_menu)
        row.addWidget(self._colour_btn)

        self._width_label, self._width = self._pair(row, "Width", 1, 24, DEFAULT_STYLE.line_width, 52)
        self._font_label, self._font = self._pair(row, "Font", 8, 72, DEFAULT_STYLE.font_size, 52)
        self._opacity_label, self._opacity = self._pair(row, "Opacity", 10, 100, 100, 52)
        self._next_label, self._next_spin = self._pair(row, "Next", 1, 999, 1, 56)
        self._step_label, self._step_spin = self._pair(row, "Step", 1, 999, 1, 56)
        self._next_spin.setToolTip("Number placed by the next step badge")
        self._step_spin.setToolTip("Number on the selected step")

        self._outline = QCheckBox("Outline")
        self._outline.setFixedHeight(26)
        row.addWidget(self._outline)

        self._arrow_btn = QPushButton("Arrow")
        self._arrow_btn.setObjectName("ArrowStyle")
        self._arrow_btn.setFixedHeight(26)
        self._arrow_btn.setToolTip("Arrow style")
        self._arrow_btn.clicked.connect(self.open_arrow_menu)
        row.addWidget(self._arrow_btn)
        row.addStretch(1)

        self._width.valueChanged.connect(self._apply_width)
        self._font.valueChanged.connect(self._apply_font)
        self._opacity.valueChanged.connect(self._apply_opacity)
        self._next_spin.valueChanged.connect(self._apply_next)
        self._step_spin.valueChanged.connect(self._apply_step)
        self._outline.toggled.connect(self._apply_outline)
        self._paint_swatch()

    def _pair(self, row, text, low, high, value, width):
        label = QLabel(text)
        label.setFixedHeight(26)
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        spin.setFixedSize(width, 26)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        palette = spin.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor("#383838"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e6e6e6"))
        spin.setPalette(palette)
        edit = spin.lineEdit()
        if edit is not None:
            edit.setPalette(palette)
            edit.setStyleSheet("color: #e6e6e6; background: transparent; border: none; padding: 0; min-height: 0;")
        row.addWidget(label)
        row.addWidget(spin)
        return label, spin

    def bind(self, scene, toolbar):
        self._scene = scene
        self._toolbar = toolbar
        scene.selectionChanged.connect(self.refresh)
        scene.numbers_changed.connect(self.sync_next_display)
        scene.number_edit_requested.connect(self.focus_step_editor)
        scene.colour_picked.connect(self.note_colour)
        self.refresh()

    def sync_next_display(self, value: int):
        self._updating = True
        self._next_spin.setValue(int(value))
        self._updating = False

    def focus_step_editor(self, _item=None):
        self.refresh()
        self._step_spin.setFocus()
        edit = self._step_spin.lineEdit()
        if edit is not None:
            edit.selectAll()

    def note_colour(self, colour: QColor):
        self._colour = QColor(colour)
        self._paint_swatch()
        if self._toolbar is not None:
            self._toolbar.set_pen_colour(colour)

    def refresh(self):
        if self._scene is None or sip.isdeleted(self._scene):
            return
        item = self._selected()
        tool = self._tool()
        self._updating = True
        if self._scene is not None:
            self._width.setValue(self._width_of(item))
            self._font.setValue(self._font_of(item))
            opacity = item.opacity() if item is not None else self._scene.item_opacity
            self._opacity.setValue(int(round(opacity * 100)))
            self._next_spin.setValue(self._scene._next_number)
            if isinstance(item, NumberItem):
                self._step_spin.setValue(item.number)
                self._colour = QColor(item.color)
            elif item is not None:
                self._colour = self._colour_of(item)
            self._outline.setChecked(self._outline_of(item))
        self._paint_swatch()
        self._show_for(tool, item)
        self._updating = False

    def _show_for(self, tool: str, item):
        kind = self._kind(tool, item)
        self._colour_btn.setVisible(kind != "crop")
        self._show(self._width_label, self._width, kind in {"width", "shape", "arrow", "stroke", "callout"})
        self._show(self._font_label, self._font, kind in {"text", "number", "callout"})
        self._show(self._opacity_label, self._opacity, kind not in {"crop", "width"})
        self._show(self._next_label, self._next_spin, tool == "number")
        self._show(self._step_label, self._step_spin, isinstance(item, NumberItem))
        self._outline.setVisible(kind in {"shape", "callout"})
        self._arrow_btn.setVisible(kind == "arrow")

    def _show(self, label, spin, visible: bool):
        label.setVisible(visible)
        spin.setVisible(visible)

    def _kind(self, tool: str, item) -> str:
        if isinstance(item, NumberItem):
            return "number"
        if isinstance(item, TextItem):
            return "text"
        if isinstance(item, CalloutItem):
            return "callout"
        if isinstance(item, (RectItem, EllipseItem)):
            return "shape"
        if isinstance(item, ArrowItem):
            return "arrow"
        if isinstance(item, StrokeItem):
            return "stroke"
        if tool == "number":
            return "number"
        if tool == "text":
            return "text"
        if tool == "callout":
            return "callout"
        if tool in {"rect", "ellipse"}:
            return "shape"
        if tool == "arrow":
            return "arrow"
        if tool in {"pen", "highlight", "blur"}:
            return "stroke"
        if tool == "eraser":
            return "width"
        if tool == "crop":
            return "crop"
        return "basic"

    def _selected(self):
        if self._scene is None:
            return None
        kinds = (RectItem, EllipseItem, ArrowItem, TextItem, CalloutItem, StrokeItem, NumberItem)
        for item in self._scene.selectedItems():
            if isinstance(item, kinds) and item.parentItem() is None:
                return item
        return None

    def _tool(self) -> str:
        if self._scene is None:
            return "select"
        return self._scene._tool

    def _width_of(self, item) -> int:
        if item is not None and hasattr(item, "line_width"):
            return max(1, item.line_width)
        if self._scene is not None:
            return max(1, self._scene.line_width)
        return DEFAULT_STYLE.line_width

    def _font_of(self, item) -> int:
        if item is not None and hasattr(item, "font_size"):
            return item.font_size
        if self._scene is not None:
            return self._scene.font_size
        return DEFAULT_STYLE.font_size

    def _outline_of(self, item) -> bool:
        if item is not None and hasattr(item, "stroke_enabled"):
            return bool(item.stroke_enabled)
        return True

    def _colour_of(self, item) -> QColor:
        if isinstance(item, (RectItem, EllipseItem, CalloutItem)) and hasattr(item, "fill_color"):
            return QColor(item.pen_color)
        if isinstance(item, TextItem):
            return QColor(item.text_color)
        if hasattr(item, "pen_color"):
            return QColor(item.pen_color)
        if hasattr(item, "color"):
            return QColor(item.color)
        return QColor(self._colour)

    def _paint_swatch(self):
        name = self._colour.name()
        self._colour_btn.setStyleSheet(
            f"background: {name}; border: 1px solid #e6e6e6; border-radius: 3px;"
        )
        self._colour_btn.setToolTip(f"Colour {name}")

    def _apply_width(self, value: int):
        if self._updating:
            return
        if self._scene is not None:
            self._scene.set_line_width(value)
        item = self._selected()
        if item is not None and hasattr(item, "line_width"):
            item.line_width = max(1, int(value))
            if hasattr(item, "_apply_style"):
                item._apply_style()
            item.update()

    def _apply_font(self, value: int):
        if self._updating:
            return
        if self._scene is not None:
            self._scene.set_font_size(value)
        item = self._selected()
        if isinstance(item, TextItem):
            item.font_size = int(value)
            font = item.font()
            font.setPointSize(item.font_size)
            item.setFont(font)
            item.update()
        elif item is not None and hasattr(item, "font_size"):
            item.font_size = int(value)
            item.update()

    def _apply_opacity(self, value: int):
        if self._updating or self._scene is None:
            return
        opacity = max(0.1, min(1.0, value / 100.0))
        item = self._selected()
        if item is None:
            self._scene.item_opacity = opacity
            return
        item.setOpacity(opacity)
        item.update()

    def _apply_next(self, value: int):
        if self._updating or self._scene is None:
            return
        self._scene.set_next_number(value)

    def _apply_step(self, value: int):
        if self._updating or self._scene is None:
            return
        item = self._selected()
        if isinstance(item, NumberItem):
            item.set_number(value)
            self._scene.sync_next_number()

    def _apply_outline(self, checked: bool):
        if self._updating:
            return
        item = self._selected()
        if item is None or not hasattr(item, "stroke_enabled"):
            return
        item.stroke_enabled = bool(checked)
        if hasattr(item, "_apply_style"):
            item._apply_style()
        item.update()

    def set_colour(self, colour: QColor, fill: QColor | None = None, text: QColor | None = None):
        self._colour = QColor(colour)
        self._paint_swatch()
        if self._toolbar is not None:
            self._toolbar.set_pen_colour(self._colour)
        if self._scene is not None:
            self._scene.set_pen_color(self._colour)
            self._scene.set_text_color(text or self._colour)
            paint = QColor(fill) if fill is not None else QColor(self._colour)
            if fill is None:
                paint.setAlpha(48)
            self._scene.set_fill_color(paint)
        item = self._selected()
        if item is None:
            self.pen_color_changed.emit(self._colour)
            return
        if isinstance(item, NumberItem):
            item.color = QColor(self._colour)
        elif isinstance(item, TextItem):
            item.text_color = QColor(text or self._colour)
            item.setDefaultTextColor(item.text_color)
        elif isinstance(item, (RectItem, EllipseItem, CalloutItem)):
            item.pen_color = QColor(self._colour)
            paint = QColor(fill) if fill is not None else QColor(self._colour)
            if fill is None:
                paint.setAlpha(48)
            item.fill_color = paint
            if hasattr(item, "_apply_style"):
                item._apply_style()
        elif hasattr(item, "pen_color"):
            colour = QColor(self._colour)
            if isinstance(item, StrokeItem) and item.highlighter:
                colour.setAlpha(96)
            item.pen_color = colour
        item.update()
        self.pen_color_changed.emit(self._colour)

    def apply_named_style(self, name: str):
        style = STYLES.get(name)
        if style is None:
            return
        self._updating = True
        self._width.setValue(style.line_width)
        self._font.setValue(style.font_size)
        self._updating = False
        if self._scene is not None:
            self._scene.set_line_width(style.line_width)
            self._scene.set_font_size(style.font_size)
        self.set_colour(style.pen_color, style.fill_color, style.text_color)

    def open_colour_menu(self):
        menu = self.build_colour_menu()
        origin = self._colour_btn.mapToGlobal(QPoint(0, self._colour_btn.height()))
        menu.popup(origin)
        self._colour_menu = menu
        return menu

    def build_colour_menu(self) -> QMenu:
        menu = _popup()
        host = QWidget()
        host.setStyleSheet("background: #2b2b2b;")
        grid = QGridLayout(host)
        grid.setContentsMargins(8, 8, 8, 4)
        grid.setSpacing(4)
        caption = QLabel("Colours")
        grid.addWidget(caption, 0, 0, 1, 6)
        columns = 6
        for index, name in enumerate(STYLES):
            button = self._swatch_button(STYLES[name].pen_color, name)
            button.clicked.connect(lambda _checked=False, style_name=name: self._pick_style(style_name))
            grid.addWidget(button, 1 + index // columns, index % columns)
        offset = len(STYLES)
        for index, code in enumerate(PALETTE):
            place = offset + index
            button = self._swatch_button(QColor(code), code)
            button.clicked.connect(lambda _checked=False, hex_code=code: self._pick_hex(hex_code))
            grid.addWidget(button, 1 + place // columns, place % columns)
        saved = self._swatches.items
        row = 1 + (offset + len(PALETTE) + columns - 1) // columns
        if saved:
            grid.addWidget(QLabel("Swatches"), row, 0, 1, columns)
            for index, item in enumerate(saved[:12]):
                button = self._swatch_button(QColor(item["hex"]), item.get("name") or item["hex"])
                button.clicked.connect(lambda _checked=False, hex_code=item["hex"]: self._pick_hex(hex_code))
                grid.addWidget(button, row + 1 + index // columns, index % columns)
        action = QWidgetAction(menu)
        action.setDefaultWidget(host)
        menu.addAction(action)
        menu.addAction("Pick colour from screen", self._pick_screen)
        menu.addAction("Pick colour from image", self._pick_image)
        menu.addAction("More colours…", self._more_colours)
        menu.addAction("Save this swatch", self._save_swatch)
        menu.addSeparator()
        menu.addAction("Copy as HEX", lambda: self._copy("hex"))
        menu.addAction("Copy as RGB", lambda: self._copy("rgb"))
        menu.addAction("Copy as HSL", lambda: self._copy("hsl"))
        return menu

    def _swatch_button(self, colour: QColor, tip: str) -> QPushButton:
        button = QPushButton()
        button.setFixedSize(22, 22)
        button.setToolTip(tip)
        button.setStyleSheet(
            f"background: {QColor(colour).name()}; border: 1px solid #e6e6e6; border-radius: 3px;"
        )
        return button

    def _pick_style(self, name: str):
        self._close_menu()
        self.apply_named_style(name)

    def _pick_hex(self, code: str):
        self._close_menu()
        self.set_colour(QColor(code))

    def _pick_screen(self):
        self._close_menu()
        self.screen_pick_requested.emit()

    def _pick_image(self):
        self._close_menu()
        if self._toolbar is not None:
            self._toolbar.set_tool("pick")
            self._toolbar.tool_changed.emit("pick")

    def _more_colours(self):
        self._close_menu()
        colour = QColorDialog.getColor(self._colour, self, "Choose Colour")
        if colour.isValid():
            self.set_colour(colour)

    def _save_swatch(self):
        self._close_menu()
        self._swatches.add(self._colour.name())

    def _copy(self, fmt: str):
        self._close_menu()
        self._history.set_format(fmt)
        text = self._history.display(self._colour.name())
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _close_menu(self):
        if self._colour_menu is not None:
            self._colour_menu.close()

    def open_arrow_menu(self):
        menu = _popup("ArrowMenu")
        current = self._scene.arrow_style if self._scene is not None else "plain"
        item = self._selected()
        if isinstance(item, ArrowItem):
            current = item.style
        for key in ARROW_STYLES:
            label = ARROW_LABELS.get(key, key)
            if key == current:
                label = f"{label}  \u2713"
            menu.addAction(label, lambda style=key: self._set_arrow_style(style))
        menu.popup(self._arrow_btn.mapToGlobal(QPoint(0, self._arrow_btn.height())))
        self._arrow_menu = menu
        return menu

    def _set_arrow_style(self, style: str):
        if self._scene is not None:
            self._scene.arrow_style = style
        item = self._selected()
        if isinstance(item, ArrowItem):
            item.style = style
            item.update()
