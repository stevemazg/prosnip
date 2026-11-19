"""Recent captures tray. Files stay in the library folder when a card is removed."""

import json
import time
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
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
        self._current = ""
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
        stamp = _safe_name(title or "capture")
        ident = stamp
        index = 1
        while (folder / f"{ident}.png").exists() or (folder / f"{ident}.json").exists():
            index += 1
            ident = f"{stamp}-{index}"
        path = folder / f"{ident}.png"
        image.save(path, "PNG")
        meta = {
            "title": title or ident,
            "pinned": False,
            "unsaved": True,
            "path": str(path),
            "created": time.time(),
        }
        (folder / f"{ident}.json").write_text(json.dumps(meta), encoding="utf-8")
        self._current = str(path)
        self.reload()
        return str(path)

    def card_count(self) -> int:
        total = 0
        for index in range(self._row.count()):
            widget = self._row.itemAt(index).widget()
            if widget is not None and not sip.isdeleted(widget):
                total += 1
        return total

    def reload(self):
        while self._row.count():
            item = self._row.takeAt(0)
            widget = item.widget()
            if widget is None:
                continue
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()
        folder = library_dir()
        cards = []
        for meta_path in folder.glob("*.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if meta.get("hidden"):
                continue
            created = float(meta.get("created") or meta_path.stat().st_mtime)
            cards.append((bool(meta.get("pinned")), created, meta_path, meta))
        cards.sort(key=lambda item: (not item[0], -item[1]))
        shown = cards[:30]
        for _pinned, _created, meta_path, meta in shown:
            self._row.addWidget(self._card(meta_path, meta))
        width = max(CARD_W, 8 + len(shown) * (CARD_W + 8))
        self._host.setFixedHeight(CARD_H)
        self._host.setMinimumWidth(width)
        if self._current:
            self.mark_selected(self._current)

    def mark_selected(self, path: str):
        self._current = path or ""
        chosen = None
        for index in range(self._row.count()):
            card = self._row.itemAt(index).widget()
            if card is None or sip.isdeleted(card):
                continue
            selected = bool(path) and card.property("imagePath") == path
            card.setProperty("selected", selected)
            card.setStyleSheet(
                "QWidget#RecentCard { background-color: #c7d2fe; border: 3px solid #3730a3; }"
                if selected
                else "QWidget#RecentCard { background-color: transparent; border: 3px solid transparent; }"
            )
            if selected:
                chosen = card
        if chosen is not None:
            self._scroll.ensureWidgetVisible(chosen)

    def _card(self, meta_path: Path, meta: dict) -> QWidget:
        card = RecentCard(meta.get("path") or "", meta.get("title") or meta_path.stem, self._host)
        card.setProperty("imagePath", meta.get("path") or "")
        pix = QPixmap(meta.get("path") or "")
        if not pix.isNull():
            card.set_pixmap(pix)
        card.pin_clicked.connect(lambda source=meta_path: self._pin(source))
        card.close_clicked.connect(lambda source=meta_path: self._hide(source))
        card.activated.connect(self.opened.emit)
        if meta.get("pinned"):
            card._pin.setText("●")
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


def _safe_name(title: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in title).strip("-")
    return cleaned or "capture"


class RecentCard(QWidget):
    """One tray thumbnail. Events stay on the widget so a reload cannot call a dead button."""

    activated = pyqtSignal(str)
    pin_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, path: str, title: str, parent=None):
        super().__init__(parent)
        self._path = path
        self.setObjectName("RecentCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedSize(CARD_W, CARD_H)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self._thumb = QLabel()
        self._thumb.setFixedSize(CARD_W - 8, THUMB_H)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._thumb)
        caption = QLabel(title)
        caption.setObjectName("RecentCaption")
        caption.setFixedHeight(CAPTION_H)
        caption.setToolTip(title)
        layout.addWidget(caption)
        self._pin = self._button("•", "Pin", 4)
        self._close = self._button("×", "Remove from tray", CARD_W - 20)
        self._pin.clicked.connect(self.pin_clicked.emit)
        self._close.clicked.connect(self.close_clicked.emit)

    def set_pixmap(self, pix: QPixmap):
        self._thumb.setPixmap(pix.scaled(
            CARD_W - 8, THUMB_H,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))

    def _button(self, text: str, tip: str, x: int) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.setFixedSize(16, 16)
        button.setGeometry(x, 4, 16, 16)
        button.hide()
        button.setStyleSheet(
            "QToolButton { border: none; padding: 0; background: rgba(255,255,255,220); color: #1a1d21; }"
        )
        return button

    def _alive(self, widget) -> bool:
        return widget is not None and not sip.isdeleted(widget)

    def enterEvent(self, event):
        if self._alive(self._pin):
            self._pin.show()
        if self._alive(self._close):
            self._close.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._alive(self._pin):
            self._pin.hide()
        if self._alive(self._close):
            self._close.hide()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._path:
            self.activated.emit(self._path)
        super().mousePressEvent(event)


def _icon(pix: QPixmap):
    from PyQt6.QtGui import QIcon

    return QIcon(pix)
