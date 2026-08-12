from PyQt6.QtWidgets import (
    QDialog, QGridLayout, QPushButton, QLabel, QVBoxLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

STAMPS = ["✅", "❌", "⚠️", "👍", "💡", "🔴", "🟡", "🟢", "①", "②", "③", "④", "⑤"]


class StampPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Stamp")
        self.setModal(True)
        self.chosen = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        label = QLabel("Select a stamp:")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        grid = QGridLayout()
        cols = 5
        for i, stamp in enumerate(STAMPS):
            btn = QPushButton(stamp)
            btn.setFixedSize(52, 52)
            font = QFont()
            font.setPointSize(22)
            btn.setFont(font)
            btn.clicked.connect(lambda checked, s=stamp: self._select(s))
            grid.addWidget(btn, i // cols, i % cols)

        layout.addLayout(grid)
        self.setFixedSize(300, 180)

    def _select(self, stamp: str):
        self.chosen = stamp
        self.accept()

    @staticmethod
    def get_stamp(parent=None) -> str | None:
        dlg = StampPickerDialog(parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.chosen
        return None
