"""The card shown after a colour is picked from the screen."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QApplication,
)

from colour import format_colour, parse_hex


class ColourCard(QDialog):
    def __init__(self, hex_code: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Colour")
        self._added = False
        parsed = parse_hex(hex_code) or (0, 0, 0)
        self._rgb = parsed
        self.setStyleSheet(
            "QDialog { background: #1e1e1e; color: #f2f2f2; }"
            "QLabel { color: #f7f7f7; font-size: 14px; }"
            "QPushButton { background: #2d2d2d; color: #f7f7f7; border: 1px solid #6a6a6a;"
            " border-radius: 4px; padding: 6px 10px; min-height: 28px; }"
        )
        layout = QVBoxLayout(self)
        swatch = QLabel()
        swatch.setFixedSize(220, 96)
        swatch.setStyleSheet(
            f"background: {format_colour(*parsed)}; border: 1px solid #ffffff; border-radius: 6px;"
        )
        layout.addWidget(swatch, alignment=Qt.AlignmentFlag.AlignHCenter)
        for fmt, title in (("hex", "HEX"), ("rgb", "RGB"), ("hsl", "HSL")):
            row = QHBoxLayout()
            text = format_colour(*parsed, fmt)
            label = QLabel(f"{title}  {text}")
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda _checked=False, value=text: self._copy(value))
            row.addWidget(label, 1)
            row.addWidget(copy)
            layout.addLayout(row)
        add = QPushButton("Add to swatches")
        add.clicked.connect(self._add)
        layout.addWidget(add)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    @property
    def added(self) -> bool:
        return self._added

    def _copy(self, text: str) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _add(self) -> None:
        self._added = True
        self.accept()


def show_colour_card(hex_code: str, parent=None) -> bool:
    """Show the card. Return True when the user adds the colour to swatches."""
    if parse_hex(hex_code) is None:
        return False
    card = ColourCard(hex_code, parent)
    card.exec()
    return card.added
