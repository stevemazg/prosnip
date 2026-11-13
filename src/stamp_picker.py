import json
import os
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QGridLayout, QPushButton, QLabel, QVBoxLayout, QFileDialog, QScrollArea, QWidget
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QPixmap

STAMPS = ["✅", "❌", "⚠️", "👍", "💡", "🔴", "🟡", "🟢", "①", "②", "③", "④", "⑤"]


def stamps_directory() -> Path:
    """Custom stamps live in %APPDATA%\\ProSnip-Bob\\stamps."""
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    folder = root / "ProSnip-Bob" / "stamps"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _manifest_path() -> Path:
    return stamps_directory() / "stamps.json"


def custom_stamp_paths() -> list[Path]:
    path = _manifest_path()
    if not path.is_file():
        return []
    try:
        names = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    found = []
    for name in names:
        candidate = stamps_directory() / name
        if candidate.is_file():
            found.append(candidate)
    return found


def add_custom_stamp(source: str) -> Path | None:
    source_path = Path(source)
    if not source_path.is_file():
        return None
    folder = stamps_directory()
    target = folder / source_path.name
    index = 1
    while target.exists():
        target = folder / f"{source_path.stem}-{index}{source_path.suffix}"
        index += 1
    if source_path.suffix.lower() == ".svg":
        png = target.with_suffix(".png")
        if not _rasterise_svg(source_path, png):
            return None
        target = png
    else:
        shutil.copy2(source_path, target)
    names = [path.name for path in custom_stamp_paths()]
    names.append(target.name)
    _manifest_path().write_text(json.dumps(names), encoding="utf-8")
    return target


def _rasterise_svg(source: Path, target: Path) -> bool:
    try:
        from PyQt6.QtSvg import QSvgRenderer
        from PyQt6.QtGui import QPainter
        from PyQt6.QtCore import Qt as QtCore
    except ImportError:
        return False
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        return False
    pixmap = QPixmap(256, 256)
    pixmap.fill(QtCore.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap.save(str(target), "PNG")


class StampPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Stamp")
        self.setModal(True)
        self.chosen = None
        self._build_ui()

    def _build_ui(self):
        layout = self.layout() or QVBoxLayout(self)
        label = QLabel("Select a stamp:")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 16px; font-weight: 600;")
        layout.addWidget(label)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        host = QWidget()
        grid = QGridLayout(host)
        grid.setSpacing(8)
        cols = 4
        entries: list[tuple[str, QIcon | None]] = [(stamp, None) for stamp in STAMPS]
        for path in custom_stamp_paths():
            entries.append((f"image:{path}", QIcon(str(path))))
        for index, (stamp, icon) in enumerate(entries):
            button = QPushButton()
            button.setFixedSize(96, 96)
            if icon is None:
                font = QFont()
                font.setPointSize(40)
                button.setFont(font)
                button.setText(stamp)
            else:
                button.setIcon(icon)
                button.setIconSize(QSize(72, 72))
            button.clicked.connect(lambda checked, s=stamp: self._select(s))
            grid.addWidget(button, index // cols, index % cols)
        scroller.setWidget(host)
        layout.addWidget(scroller)

        add = QPushButton("Add stamp…")
        add.clicked.connect(self._add_stamp)
        layout.addWidget(add)
        self.resize(460, 420)

    def _add_stamp(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add Stamp", "", "Images (*.png *.jpg *.jpeg *.webp *.svg)"
        )
        if not path:
            return
        if add_custom_stamp(path) is None:
            return
        self._build_ui_reset()

    def _build_ui_reset(self):
        widget = self.layout().takeAt(0)
        while widget is not None:
            if widget.widget() is not None:
                widget.widget().deleteLater()
            widget = self.layout().takeAt(0)
        self._build_ui()

    def _select(self, stamp: str):
        self.chosen = stamp
        self.accept()

    @staticmethod
    def get_stamp(parent=None) -> str | None:
        dlg = StampPickerDialog(parent)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.chosen
        return None
