"""Recent captures tray. Files stay in the library folder when a card is removed."""

import json
from pathlib import Path

from PyQt6.QtCore import QByteArray, QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from PIL import Image


def library_dir() -> Path:
    import os

    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    folder = Path(root) / "ProSnip" / "Library"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class RecentTray(QWidget):
    opened = pyqtSignal(str)
    dropped_on_canvas = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RecentTray")
        self.setFixedHeight(124)
        self._selected = set()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        self._row = QHBoxLayout()
        self._row.setSpacing(8)
        host = QWidget()
        host.setLayout(self._row)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(host)
        self._host = host
        outer.addWidget(scroll)
        self.reload()

    def remember(self, image: Image.Image, title: str) -> str:
        folder = library_dir()
        stamp = title or "capture"
        ident = f"{stamp}"
        index = 1
        while (folder / f"{ident}.png").exists():
            index += 1
            ident = f"{title}-{index}"
        path = folder / f"{ident}.png"
        image.save(path, "PNG")
        meta = {"title": title, "pinned": False, "unsaved": True, "path": str(path)}
        (folder / f"{ident}.json").write_text(json.dumps(meta), encoding="utf-8")
        self.reload()
        return str(path)

    def reload(self):
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setObjectName("")
                widget.deleteLater()
        folder = library_dir()
        cards = []
        for meta_path in sorted(folder.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("hidden"):
                continue
            cards.append((bool(meta.get("pinned")), meta_path, meta))
        cards.sort(key=lambda item: (not item[0], item[1].name))
        for _pinned, meta_path, meta in cards[:30]:
            self._row.addWidget(self._card(meta_path, meta))
        self._row.addStretch(0)
        width = 8 + max(1, len(cards[:30])) * 136
        self._host.setMinimumSize(width, 108)

    def _card(self, meta_path: Path, meta: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("RecentCard")
        card.setFixedSize(128, 100)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 2)
        layout.setSpacing(2)
        thumb = QLabel()
        thumb.setFixedSize(120, 64)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = meta.get("path") or ""
        pix = QPixmap(path)
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(120, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(thumb)
        caption = QLabel(meta.get("title") or meta_path.stem)
        caption.setObjectName("muted")
        caption.setFixedHeight(16)
        layout.addWidget(caption)
        pin = QPushButton("•", card)
        pin.setToolTip("Pin")
        pin.setGeometry(4, 4, 18, 18)
        pin.hide()
        pin.clicked.connect(lambda _checked=False, source=meta_path: self._pin(source))
        close = QPushButton("×", card)
        close.setToolTip("Remove from tray")
        close.setGeometry(102, 4, 18, 18)
        close.hide()
        close.clicked.connect(lambda _checked=False, source=meta_path: self._hide(source))
        card.enterEvent = lambda _event, a=pin, b=close: (a.show(), b.show())
        card.leaveEvent = lambda _event, a=pin, b=close: (a.hide(), b.hide())
        card.mousePressEvent = lambda _event, image_path=path: self.opened.emit(image_path)
        if meta.get("pinned"):
            pin.setText("●")
        card.setProperty("imagePath", path)
        return card

    def _hide(self, meta_path: Path):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["hidden"] = True
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.reload()

    def _pin(self, meta_path: Path):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["pinned"] = not bool(meta.get("pinned"))
        meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self.reload()


def _icon(pix: QPixmap):
    from PyQt6.QtGui import QIcon

    return QIcon(pix)
