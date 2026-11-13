"""Saved swatches, kept apart from the last 12 picked colours."""

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from colour import format_colour, parse_hex, settings_path, _read_json, _write_json


class SwatchBook:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else settings_path()
        self.items: list[dict] = []
        self.load()

    def load(self) -> None:
        data = _read_json(self.path)
        found = []
        for entry in data.get("swatches", []):
            if isinstance(entry, str):
                parsed = parse_hex(entry)
                name = ""
            elif isinstance(entry, dict):
                parsed = parse_hex(str(entry.get("hex", "")))
                name = str(entry.get("name", "") or "")
            else:
                continue
            if parsed is None:
                continue
            found.append({"name": name, "hex": format_colour(*parsed, "hex")})
        self.items = found

    def save(self) -> None:
        payload = _read_json(self.path)
        payload["swatches"] = [dict(item) for item in self.items]
        _write_json(self.path, payload)

    def add(self, hex_code: str, name: str = "") -> dict | None:
        parsed = parse_hex(hex_code)
        if parsed is None:
            return None
        code = format_colour(*parsed, "hex")
        for item in self.items:
            if item["hex"] == code:
                return item
        item = {"name": name.strip(), "hex": code}
        self.items.append(item)
        self.save()
        return item

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]
            self.save()

    def rename(self, index: int, name: str) -> None:
        if 0 <= index < len(self.items):
            self.items[index]["name"] = name.strip()
            self.save()

    def clear(self) -> None:
        self.items.clear()
        self.save()

    def export_path(self, path: Path) -> None:
        payload = {"swatches": [dict(item) for item in self.items]}
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_path(self, path: Path) -> int:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError):
            return 0
        entries = data.get("swatches", data if isinstance(data, list) else [])
        added = 0
        before = len(self.items)
        for entry in entries:
            if isinstance(entry, str):
                item = self.add(entry)
            elif isinstance(entry, dict):
                item = self.add(str(entry.get("hex", "")), str(entry.get("name", "") or ""))
            else:
                item = None
            if item is not None and len(self.items) > before:
                added += 1
                before = len(self.items)
        return added


def swatch_label(item: dict) -> str:
    name = item.get("name") or ""
    return f"{name}  {item['hex']}" if name else item["hex"]


class SwatchPanel(QWidget):
    """Saved colours. Recent picks stay on the tool column."""

    def __init__(self, book: SwatchBook, on_apply, parent=None):
        super().__init__(parent)
        self._book = book
        self._on_apply = on_apply
        self.setMinimumWidth(220)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Swatches")
        title.setStyleSheet("font-size: 16px; font-weight: 600; color: #ffffff;")
        layout.addWidget(title)
        hint = QLabel("Click to use a colour. Right-click to copy, rename, or remove.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._list = QListWidget()
        self._list.itemClicked.connect(self._apply_current)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self._list, 1)
        row = QHBoxLayout()
        clear = QPushButton("Clear all")
        clear.clicked.connect(self._clear)
        export = QPushButton("Export")
        export.clicked.connect(self._export)
        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import)
        row.addWidget(clear)
        row.addWidget(export)
        row.addWidget(import_btn)
        layout.addLayout(row)
        self.reload()

    def reload(self) -> None:
        self._book.load()
        self._list.clear()
        for item in self._book.items:
            row = QListWidgetItem(swatch_label(item))
            row.setData(Qt.ItemDataRole.UserRole, item["hex"])
            colour = QColor(item["hex"])
            row.setBackground(colour)
            row.setForeground(QColor("#ffffff" if colour.lightness() < 140 else "#111111"))
            self._list.addItem(row)

    def _current_index(self) -> int:
        return self._list.currentRow()

    def _apply_current(self, _item=None) -> None:
        index = self._current_index()
        if index < 0 or index >= len(self._book.items):
            return
        self._on_apply(self._book.items[index]["hex"])

    def _menu(self, pos) -> None:
        index = self._current_index()
        if index < 0:
            return
        menu = QMenu(self)
        for fmt, label in (("hex", "Copy as HEX"), ("rgb", "Copy as RGB"), ("hsl", "Copy as HSL")):
            action = QAction(label, menu)
            action.triggered.connect(lambda _checked=False, kind=fmt: self._copy(kind))
            menu.addAction(action)
        menu.addAction("Rename", self._rename)
        menu.addAction("Remove", lambda: self._remove(index))
        menu.exec(self._list.mapToGlobal(pos))

    def _copy(self, fmt: str) -> None:
        index = self._current_index()
        if index < 0:
            return
        parsed = parse_hex(self._book.items[index]["hex"])
        if parsed is None:
            return
        text = format_colour(*parsed, fmt)
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _rename(self) -> None:
        index = self._current_index()
        if index < 0:
            return
        current = self._book.items[index]["name"]
        name, ok = QInputDialog.getText(self, "Rename swatch", "Name:", text=current)
        if ok:
            self._book.rename(index, name)
            self.reload()

    def _remove(self, index: int) -> None:
        self._book.remove(index)
        self.reload()

    def _clear(self) -> None:
        if not self._book.items:
            return
        answer = QMessageBox.question(
            self,
            "Clear swatches",
            "Remove every saved swatch? Recent picks are kept.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._book.clear()
            self.reload()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export swatches", "swatches.json", "JSON (*.json)")
        if path:
            self._book.export_path(Path(path))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import swatches", "", "JSON (*.json)")
        if path:
            self._book.import_path(Path(path))
            self.reload()
