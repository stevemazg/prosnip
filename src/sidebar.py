"""Right-hand Style Presets and tool properties. One place for each setting."""

from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSize
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from editor_bar import LABELS

PRESETS = (
    ("Red", "#e00000", 2, False),
    ("Green", "#2f9e44", 2, False),
    ("Blue", "#3949ab", 2, False),
    ("Yellow", "#c9a227", 2, False),
    ("Black", "#1a1d21", 2, False),
    ("White", "#f7f7f7", 2, False),
    ("Red thick", "#e00000", 5, False),
    ("Green thick", "#2f9e44", 5, False),
    ("Blue thick", "#3949ab", 5, False),
    ("Yellow thick", "#c9a227", 5, False),
    ("Red dashed", "#e00000", 2, True),
    ("Blue dashed", "#3949ab", 2, True),
)


TILE_SIZE = QSize(52, 40)


def _checker(painter: QPainter, rect) -> None:
    """Mid-tone checker so a white stroke and a black stroke both stay visible."""
    cell = 4
    painter.fillRect(rect, QColor("#e7eaee"))
    dark = QColor("#8d949c")
    y = rect.top()
    while y < rect.bottom():
        x = rect.left()
        row = int(y / cell)
        while x < rect.right():
            if (int(x / cell) + row) % 2:
                painter.fillRect(int(x), int(y), cell, cell, dark)
            x += cell
        y += cell


class PreviewTile(QWidget):
    clicked = pyqtSignal()

    def __init__(self, name, colour, width, dashed, tool, parent=None):
        super().__init__(parent)
        self._name = name
        self._colour = QColor(colour)
        self._width = width
        self._dashed = dashed
        self._tool = tool
        self.setObjectName("PresetTile")
        self.setFixedSize(TILE_SIZE)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(self.rect())
        _checker(painter, self.rect())
        painter.setPen(QPen(QColor("#5c656d"), 1))
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        halo = QColor("#1a1d21" if self._colour.lightness() > 150 else "#ffffff")
        self._draw_mark(painter, halo, max(2.2, self._width / 2 + 1.2))
        self._draw_mark(painter, self._colour, max(1.2, self._width / 2))
        painter.end()

    def _draw_mark(self, painter: QPainter, colour: QColor, width: float):
        pen = QPen(colour, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        if self._dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        tool = self._tool
        box = QRectF(10, 10, 32, 18)
        if tool == "pen":
            painter.drawLine(8, 28, 16, 14)
            painter.drawLine(16, 14, 26, 26)
            painter.drawLine(26, 26, 34, 12)
            painter.drawLine(34, 12, 44, 22)
        elif tool == "highlight":
            painter.setPen(QPen(QColor(colour.red(), colour.green(), colour.blue(), 160), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(8, 24, 44, 16)
        elif tool == "ellipse":
            painter.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 70))
            painter.drawEllipse(box)
        elif tool == "rect":
            painter.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 70))
            radius = 6 if self._width >= 5 else 1
            painter.drawRoundedRect(box, radius, radius)
        elif tool == "polygon":
            painter.setBrush(QColor(colour.red(), colour.green(), colour.blue(), 70))
            painter.drawLine(12, 28, 22, 10)
            painter.drawLine(22, 10, 40, 16)
            painter.drawLine(40, 16, 34, 30)
            painter.drawLine(34, 30, 12, 28)
        elif tool == "callout":
            painter.setBrush(colour)
            painter.drawRoundedRect(QRectF(8, 6, 32, 16), 3, 3)
            painter.drawLine(16, 22, 12, 34)
        elif tool == "number":
            painter.setBrush(colour)
            painter.setPen(QPen(colour, 1))
            painter.drawEllipse(QRectF(16, 8, 20, 20))
            painter.setPen(QPen(QColor("#ffffff")))
            painter.drawText(QRectF(16, 8, 20, 20), int(Qt.AlignmentFlag.AlignCenter), "1")
        elif tool == "text":
            painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "Aa")
        elif tool == "arrow":
            painter.drawLine(8, 30, 40, 10)
            painter.drawLine(40, 10, 30, 12)
            painter.drawLine(40, 10, 36, 20)
        elif tool == "blur":
            painter.setBrush(colour)
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.drawRect(10, 12, 8, 8)
            painter.drawRect(22, 18, 8, 8)
            painter.drawRect(34, 12, 8, 8)
        elif tool == "eraser":
            painter.drawLine(8, 20, 20, 20)
            painter.drawLine(32, 20, 44, 20)
        elif tool == "spotlight":
            painter.setBrush(QColor(0, 0, 0, 90))
            painter.setPen(QPen(Qt.PenStyle.NoPen))
            painter.drawRect(self.rect().adjusted(4, 4, -4, -4))
            painter.setBrush(QColor("#e7eaee"))
            painter.drawEllipse(QRectF(18, 12, 16, 16))
        elif tool == "cutout":
            painter.drawRect(QRectF(8, 8, 36, 24))
            painter.drawLine(8, 20, 44, 20)
        elif tool in {"select", "crop"}:
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(box)
        elif tool == "stamp":
            painter.setBrush(colour)
            painter.drawEllipse(QRectF(16, 8, 20, 20))
        else:
            painter.drawLine(10, 28, 42, 12)


class SideBar(QWidget):
    preset_chosen = pyqtSignal(QColor)
    select_all_requested = pyqtSignal()

    def __init__(self, options, history, parent=None):
        super().__init__(parent)
        self.setObjectName("SideBar")
        self.setFixedWidth(260)
        self._options = options
        self._history = history
        self._favourites = set()
        self._custom = []
        self._show_favourites = False
        self._effects = False
        self._tool = "arrow"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        self._header = QLabel("Style Presets")
        self._header.setObjectName("section")
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._header)
        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme"))
        self._theme = QComboBox()
        self._theme.setObjectName("PresetTheme")
        self._theme.addItems(["Starter", "Mono"])
        self._theme.currentTextChanged.connect(lambda _text: self._rebuild())
        theme_row.addWidget(self._theme, 1)
        add = QPushButton("+")
        add.setFixedWidth(28)
        add.setToolTip("Save the current colour as a preset")
        add.clicked.connect(self._save_current)
        theme_row.addWidget(add)
        wrap = QWidget()
        wrap.setLayout(theme_row)
        layout.addWidget(wrap)
        self._grid_host = QWidget()
        self._grid_host.setObjectName("PresetGrid")
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(8, 6, 8, 8)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(6)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._grid_host)
        self._props_header = QLabel("Tool properties")
        self._props_header.setObjectName("section")
        self._props_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._props_header)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(options)
        self._scroll = scroll
        layout.addWidget(scroll, 1)
        self._effects_page = QLabel("Effects are coming in 1.9.")
        self._effects_page.setWordWrap(True)
        self._effects_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._effects_page.hide()
        layout.addWidget(self._effects_page)
        footer = QWidget()
        footer.setObjectName("SidebarFooter")
        footer.setAutoFillBackground(True)
        foot = QVBoxLayout(footer)
        foot.setContentsMargins(8, 4, 8, 4)
        foot.setSpacing(4)
        self._count = QLabel("")
        self._count.setObjectName("muted")
        foot.addWidget(self._count)
        select = QPushButton("Select all")
        select.setObjectName("SelectAllTool")
        select.clicked.connect(self.select_all_requested.emit)
        foot.addWidget(select)
        layout.addWidget(footer)
        self._select = select
        self._rebuild()

    def set_tool_name(self, name: str, count: int):
        self._tool = name
        label = LABELS.get(name, name)
        self._select.setText(f"Select all ({label})")
        self._count.setText(f"{count} objects selected" if count else "")
        self._rebuild()

    def show_favourites(self, enabled: bool):
        self._show_favourites = enabled
        self._header.setText("Favourites" if enabled else "Style Presets")
        self._rebuild()

    def show_effects(self, enabled: bool):
        self._effects = enabled
        self._scroll.setVisible(not enabled)
        self._props_header.setVisible(not enabled)
        self._effects_page.setVisible(enabled)
        self._grid_host.setVisible(not enabled)
        self._header.setVisible(not enabled)

    def _palette(self):
        if self._theme.currentText() == "Mono":
            return [tile for tile in PRESETS if tile[0] in {"Black", "White", "Red thick", "Blue thick"}] + [
                ("Slate", "#3d4750", 2, False),
                ("Silver", "#6b7280", 2, False),
                ("Slate thick", "#3d4750", 5, False),
                ("Silver dashed", "#6b7280", 2, True),
            ]
        return list(PRESETS)

    def _rebuild(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        tiles = list(self._palette()) + [(name, colour, 2, False) for name, colour in self._custom]
        if self._show_favourites:
            tiles = [tile for tile in tiles if tile[0] in self._favourites]
        for index, tile in enumerate(tiles):
            name, colour, width, dashed = tile
            button = PreviewTile(name, colour, width, dashed, self._tool)
            button.clicked.connect(lambda _checked=False, value=colour: self.preset_chosen.emit(QColor(value)))
            button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda pos, tile_name=name, source=button: self._tile_menu(source, tile_name, pos)
            )
            star = "★ " if name in self._favourites else ""
            button.setToolTip(f"{star}{name}")
            self._grid.addWidget(button, index // 4, index % 4, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def _save_current(self):
        colour = self._options._colour.name()
        name = f"Custom {len(self._custom) + 1}"
        self._custom.append((name, colour))
        self._rebuild()

    def _tile_menu(self, button, name, pos):
        menu = QMenu(button)
        menu.addAction("Add to favourites", lambda: self._favourite(name, True))
        menu.addAction("Remove from favourites", lambda: self._favourite(name, False))
        if name.startswith("Custom"):
            menu.addAction("Delete preset", lambda: self._delete(name))
        menu.exec(button.mapToGlobal(pos))

    def _favourite(self, name, enabled):
        if enabled:
            self._favourites.add(name)
        else:
            self._favourites.discard(name)
        self._rebuild()

    def _delete(self, name):
        self._custom = [tile for tile in self._custom if tile[0] != name]
        self._favourites.discard(name)
        self._rebuild()
