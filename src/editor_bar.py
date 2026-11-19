"""Top editor toolbar: navigation, tools, and save. Our own icons."""

from PyQt6.QtCore import QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

DEFAULT_ORDER = ["favourites", "arrow", "text", "callout", "rect", "stamp", "fill", "select"]
MORE_LIVE = ["crop", "pen", "highlight", "number", "eraser", "blur", "ellipse", "image", "screenpick", "pick"]
MORE_LATER = ["selection", "cutout", "magnify", "spotlight"]
LABELS = {
    "favourites": "Favourites",
    "arrow": "Arrow",
    "text": "Text",
    "callout": "Callout",
    "rect": "Shape",
    "stamp": "Stamp",
    "fill": "Fill",
    "select": "Move",
    "crop": "Crop",
    "pen": "Pen",
    "highlight": "Highlighter",
    "number": "Step",
    "eraser": "Eraser",
    "blur": "Blur",
    "ellipse": "Ellipse",
    "image": "Image",
    "screenpick": "Screen colour",
    "pick": "Pick colour",
    "selection": "Selection",
    "cutout": "Cut out",
    "magnify": "Magnify",
    "spotlight": "Spotlight",
}


def _icon(kind: str, colour: str = "#3d4750") -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(colour), 2)
    painter.setPen(pen)
    if kind == "arrow":
        painter.drawLine(6, 26, 24, 8)
        painter.drawLine(24, 8, 16, 10)
        painter.drawLine(24, 8, 22, 16)
    elif kind == "text":
        painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "a")
    elif kind == "callout":
        painter.drawRoundedRect(4, 6, 22, 14, 3, 3)
        painter.drawLine(10, 20, 8, 26)
    elif kind == "rect":
        painter.drawRect(6, 8, 18, 14)
        painter.drawEllipse(12, 12, 12, 12)
    elif kind == "star":
        painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "★")
    else:
        painter.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), kind[:1].upper())
    painter.end()
    return QIcon(pix)


class EditorBar(QWidget):
    """One toolbar row. Tools that do not fit move into More."""

    tool_changed = pyqtSignal(str)
    capture_requested = pyqtSignal()
    library_requested = pyqtSignal()
    editor_requested = pyqtSignal()
    copy_all_requested = pyqtSignal()
    save_requested = pyqtSignal(str)
    favourites_requested = pyqtSignal()

    def __init__(self, history, parent=None):
        super().__init__(parent)
        self._history = history
        self.setObjectName("EditorToolbar")
        self._labels = history.toolbar_mode != "icons"
        self._order = [item for item in history.toolbar_order.split(",") if item in LABELS] or list(DEFAULT_ORDER)
        self._current = "select"
        self._buttons = {}
        self._more_menu = None
        self._build()
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(4)
        self._row = row
        for name, slot in (
            ("Editor", self.editor_requested.emit),
            ("Library", self.library_requested.emit),
            ("Capture", self.capture_requested.emit),
        ):
            row.addWidget(self._nav(name, slot))
        create = self._nav("Create", None)
        menu = QMenu(create)
        menu.addAction("New image", lambda: self.save_requested.emit("new-image"))
        menu.addAction("New from clipboard", lambda: self.save_requested.emit("new-clipboard"))
        create.setMenu(menu)
        row.addWidget(create)
        row.addStretch(1)
        self._tool_host = QWidget()
        self._tool_row = QHBoxLayout(self._tool_host)
        self._tool_row.setContentsMargins(0, 0, 0, 0)
        self._tool_row.setSpacing(2)
        row.addWidget(self._tool_host, 1)
        self._more = self._nav("More", None)
        self._more.setObjectName("MoreButton")
        self._tool_row.addWidget(self._more)
        copy = self._nav("Copy All", self.copy_all_requested.emit)
        row.addWidget(copy)
        save = QPushButton("Save")
        save.setObjectName("SaveButton")
        save.setFixedHeight(32)
        save.clicked.connect(lambda: self.save_requested.emit("file"))
        menu = QMenu(save)
        self._save_menu = menu
        menu.addAction("File", lambda: self.save_requested.emit("file"))
        menu.addAction("Clipboard", lambda: self.save_requested.emit("clipboard"))
        menu.addAction("Email", lambda: self.save_requested.emit("email"))
        menu.addAction("Program", lambda: self.save_requested.emit("program"))
        menu.addAction("Printer", lambda: self.save_requested.emit("printer"))
        caret = QPushButton("▾")
        caret.setFixedWidth(22)
        caret.setMenu(menu)
        box = QWidget()
        box_row = QHBoxLayout(box)
        box_row.setContentsMargins(0, 0, 0, 0)
        box_row.setSpacing(0)
        box_row.addWidget(save)
        box_row.addWidget(caret)
        row.addWidget(box)
        self._relayout(800)

    def _nav(self, text, slot):
        button = QPushButton(text)
        button.setFlat(True)
        if slot is not None:
            button.clicked.connect(slot)
        return button

    def button(self, tool_id: str) -> QPushButton | None:
        return self._buttons.get(tool_id)

    def set_labels(self, enabled: bool):
        self._labels = bool(enabled)
        self._history.set_toolbar("both" if self._labels else "icons", ",".join(self._order))
        self._relayout(self.width())

    def _relayout(self, width: int):
        while self._tool_row.count():
            item = self._tool_row.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._more:
                widget.setParent(None)
        self._buttons.clear()
        slot = 82 if self._labels else 40
        reserved = 420
        room = max(1, (max(width, 320) - reserved) // slot)
        visible = list(self._order)
        if self._current not in visible and self._current in LABELS:
            visible = visible[:-1] + [self._current] if visible else [self._current]
        shown = visible[:room]
        overflow = visible[room:]
        for tool_id in shown:
            self._tool_row.addWidget(self._tool_button(tool_id))
        self._tool_row.addWidget(self._more)
        self._more_menu = QMenu(self)
        for tool_id in overflow + MORE_LIVE:
            if tool_id in shown:
                continue
            self._more_menu.addAction(LABELS.get(tool_id, tool_id), lambda t=tool_id: self._choose(t))
        self._more_menu.addSeparator()
        for tool_id in MORE_LATER:
            action = self._more_menu.addAction(f"{LABELS[tool_id]} (1.8.1)")
            action.setEnabled(False)
        self._more_menu.addSeparator()
        self._more_menu.addAction("Customise toolbar…", self.customise)
        self._more.setMenu(self._more_menu)
        self.setFixedHeight(60 if self._labels else 40)

    def _tool_button(self, tool_id: str) -> QPushButton:
        button = QPushButton(_icon("star" if tool_id == "favourites" else tool_id), LABELS.get(tool_id, tool_id) if self._labels else "")
        button.setCheckable(tool_id != "favourites")
        button.setChecked(tool_id == self._current)
        button.setToolTip(LABELS.get(tool_id, tool_id))
        button.setIconSize(QSize(20, 20))
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        button.setMinimumWidth(78 if self._labels else 36)
        button.clicked.connect(lambda _checked=False, t=tool_id: self._choose(t))
        self._buttons[tool_id] = button
        return button

    def _choose(self, tool_id: str):
        if tool_id == "favourites":
            self.favourites_requested.emit()
            return
        if tool_id == "fill":
            self.tool_changed.emit("fill")
            self._current = "fill"
            self._relayout(self.width())
            return
        self._current = tool_id
        self.tool_changed.emit(tool_id)
        self._relayout(self.width())

    def set_tool(self, tool_id: str):
        self._current = tool_id
        self._relayout(self.width())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout(event.size().width())

    def _context_menu(self, pos: QPoint):
        menu = QMenu(self)
        icons = menu.addAction("Icon only")
        both = menu.addAction("Icon and text")
        menu.addSeparator()
        menu.addAction("Customise toolbar…", self.customise)
        chosen = menu.exec(self.mapToGlobal(pos))
        if chosen is icons:
            self.set_labels(False)
        elif chosen is both:
            self.set_labels(True)

    def customise(self):
        dialog = CustomiseToolbar(self._order, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._order = dialog.order()
            self._history.set_toolbar("both" if self._labels else "icons", ",".join(self._order))
            self._relayout(self.width())

    @property
    def more_menu(self):
        return self._more_menu


class CustomiseToolbar(QDialog):
    def __init__(self, order, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customise toolbar")
        self._list = QListWidget()
        self._list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        for tool_id in order:
            self._list.addItem(LABELS.get(tool_id, tool_id))
            self._list.item(self._list.count() - 1).setData(Qt.ItemDataRole.UserRole, tool_id)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Drag tools to reorder them. Remove sends a tool into More."))
        layout.addWidget(self._list)
        row = QHBoxLayout()
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove)
        close = QPushButton("Done")
        close.clicked.connect(self.accept)
        row.addWidget(remove)
        row.addWidget(close)
        layout.addLayout(row)

    def _remove(self):
        row = self._list.currentRow()
        if row >= 0:
            self._list.takeItem(row)

    def order(self):
        found = []
        for index in range(self._list.count()):
            tool_id = self._list.item(index).data(Qt.ItemDataRole.UserRole)
            if tool_id:
                found.append(tool_id)
        return found or list(DEFAULT_ORDER)
