"""Recent captures tray. Files stay in the library folder when a card is removed."""

import json
from pathlib import Path

from PyQt6.QtCore import QByteArray, QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QToolButton, QVBoxLayout, QWidget

CARD_W = 128
THUMB_H = 52
CAPTION_H = 18
CARD_H = 4 + THUMB_H + 2 + CAPTION_H + 6
TRAY_H = 4 + CARD_H + 14 + 4

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
        self.setFixedHeight(TRAY_H)
        self._selected = set()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(0)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        host = QWidget()
        host.setLayout(self._row)
        host.setFixedHeight(CARD_H)
        scroll = QScrollArea()
        scroll.setObjectName("RecentScroll")
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollBar:horizontal { height: 8px; background: transparent; }"
            "QScrollBar::handle:horizontal { background: palette(mid); min-width: 24px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; height: 0; }"
            "QScrollBar:vertical { width: 0; height: 0; }"
        )
        scroll.setWidget(host)
        self._scroll = scroll
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
        width = max(CARD_W, 8 + len(cards[:30]) * (CARD_W + 8))
        self._host.setFixedHeight(CARD_H)
        self._host.setMinimumWidth(width)

    def _card(self, meta_path: Path, meta: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("RecentCard")
        card.setFixedSize(CARD_W, CARD_H)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        thumb = QLabel()
        thumb.setFixedSize(CARD_W - 8, THUMB_H)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = meta.get("path") or ""
        pix = QPixmap(path)
        if not pix.isNull():
            thumb.setPixmap(pix.scaled(
                CARD_W - 8, THUMB_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        layout.addWidget(thumb)
        title = meta.get("title") or meta_path.stem
        caption = QLabel(title)
        caption.setObjectName("RecentCaption")
        caption.setFixedHeight(CAPTION_H)
        caption.setToolTip(title)
        layout.addWidget(caption)
        pin = QToolButton(card)
        pin.setText("•" if not meta.get("pinned") else "●")
        pin.setToolTip("Pin")
        pin.setAutoRaise(True)
        pin.setFixedSize(16, 16)
        pin.setGeometry(4, 4, 16, 16)
        pin.hide()
        pin.clicked.connect(lambda _checked=False, source=meta_path: self._pin(source))
        close = QToolButton(card)
        close.setText("×")
        close.setToolTip("Remove from tray")
        close.setAutoRaise(True)
        close.setFixedSize(16, 16)
        close.setGeometry(CARD_W - 20, 4, 16, 16)
        close.hide()
        close.clicked.connect(lambda _checked=False, source=meta_path: self._hide(source))
        for button in (pin, close):
            button.setStyleSheet(
                "QToolButton { border: none; padding: 0; background: rgba(255,255,255,220); color: #1a1d21; }"
            )
        card.enterEvent = lambda _event, a=pin, b=close: (a.show(), b.show())
        card.leaveEvent = lambda _event, a=pin, b=close: (a.hide(), b.hide())
        card.mousePressEvent = lambda _event, image_path=path: self.opened.emit(image_path)
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
