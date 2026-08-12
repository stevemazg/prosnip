from dataclasses import dataclass
from PyQt6.QtGui import QColor


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
