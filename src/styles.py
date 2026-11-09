from dataclasses import dataclass

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QPainter, QPalette, QPen, QPixmap


@dataclass
class QuickStyle:
    name: str
    pen_color: QColor
    fill_color: QColor
    text_color: QColor
    line_width: int
    font_size: int


STYLES = {
    "Red": QuickStyle("Red", QColor("#e63946"), QColor("#e6394630"), QColor("#e63946"), 2, 14),
    "Blue": QuickStyle("Blue", QColor("#1d3557"), QColor("#1d355730"), QColor("#1d3557"), 2, 14),
    "Green": QuickStyle("Green", QColor("#2d6a4f"), QColor("#2d6a4f30"), QColor("#2d6a4f"), 2, 14),
    "Corporate": QuickStyle("Corporate", QColor("#003049"), QColor("#00304920"), QColor("#003049"), 2, 13),
    "High Contrast": QuickStyle("High Contrast", QColor("#ffffff"), QColor("#00000080"), QColor("#ffffff"), 3, 14),
    "Yellow Highlight": QuickStyle("Yellow Highlight", QColor("#f4a261"), QColor("#f4a26160"), QColor("#000000"), 1, 14),
}
DEFAULT_STYLE = STYLES["Red"]

# Popup and closed combo. Item text stays light so dark swatches
# (Blue, Corporate) are not drawn as dark-on-dark labels.
COMBO_STYLE = """
QComboBox {
    background-color: #2d2d2d;
    color: #f7f7f7;
    border: 1px solid #6a6a6a;
    padding: 2px 4px;
}
QComboBox QAbstractItemView {
    background-color: #2b2b2b;
    color: #f7f7f7;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    outline: 0;
    border: 1px solid #6a6a6a;
}
QComboBox QAbstractItemView::item {
    min-height: 24px;
    padding: 2px 8px;
    color: #f7f7f7;
    background-color: #2b2b2b;
}
QComboBox QAbstractItemView::item:selected {
    background-color: #0078d4;
    color: #ffffff;
}
"""

POPUP_STYLE = """
QAbstractItemView {
    background-color: #2b2b2b;
    color: #f7f7f7;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
    outline: 0;
}
QAbstractItemView::item {
    min-height: 24px;
    padding: 2px 8px;
    color: #f7f7f7;
    background-color: #2b2b2b;
}
QAbstractItemView::item:selected {
    background-color: #0078d4;
    color: #ffffff;
}
"""


def colour_swatch(color: QColor, size: int = 16) -> QPixmap:
    """Filled swatch with a thin light border so it shows on a dark menu."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor("#f2f2f2"), 1))
    painter.setBrush(QBrush(QColor(color)))
    painter.drawRect(1, 1, size - 3, size - 3)
    painter.end()
    return pixmap


def colour_swatch_icon(color: QColor, size: int = 16) -> QIcon:
    return QIcon(colour_swatch(color, size))


def apply_combo_contrast(combo) -> None:
    """Make a style combo readable and wide enough to show the colour name."""
    combo.setStyleSheet(COMBO_STYLE)
    combo.setIconSize(QSize(14, 14))
    view = combo.view()
    view.setMinimumWidth(220)
    view.setStyleSheet(POPUP_STYLE)
    palette = view.palette()
    palette.setColor(QPalette.ColorRole.Base, QColor("#2b2b2b"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0078d4"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    view.setPalette(palette)
