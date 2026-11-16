"""One dark theme for every ProSnip-Bob window.

Palette and stylesheet are both set so a control cannot fall back to
black text on a black background.
"""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

WINDOW = QColor("#2b2b2b")
PANEL = QColor("#323232")
RAISED = QColor("#383838")
TEXT = QColor("#e6e6e6")
MUTED = QColor("#a0a0a0")
ACCENT = QColor("#3d8ee6")
BORDER = QColor("#4a4a4a")
WHITE = QColor("#ffffff")


DARK_STYLE = """
QWidget {
    background-color: #2b2b2b;
    color: #e6e6e6;
    font-size: 13px;
}
QMainWindow, QDialog, QMenuBar, QMenu, QStatusBar {
    background-color: #2b2b2b;
    color: #e6e6e6;
}
QMenuBar::item:selected, QMenu::item:selected {
    background-color: #3d8ee6;
    color: #ffffff;
}
QMenu {
    border: 1px solid #4a4a4a;
}
QDockWidget {
    color: #e6e6e6;
    titlebar-close-icon: none;
}
QDockWidget::title {
    background: #323232;
    color: #e6e6e6;
    padding: 6px 8px;
    text-align: left;
    border-bottom: 1px solid #4a4a4a;
}
QLabel { color: #e6e6e6; background: transparent; }
QLabel#muted { color: #a0a0a0; }
QPushButton, QComboBox, QSpinBox, QLineEdit, QListWidget, QPlainTextEdit, QTextEdit {
    background-color: #383838;
    color: #e6e6e6;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}
QPushButton:hover, QComboBox:hover, QSpinBox:hover {
    border-color: #3d8ee6;
}
QPushButton:checked {
    background-color: #3d8ee6;
    color: #ffffff;
    border-color: #ffffff;
}
QComboBox QAbstractItemView, QListWidget {
    background-color: #323232;
    color: #e6e6e6;
    selection-background-color: #3d8ee6;
    selection-color: #ffffff;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button { background: #4a4a4a; }
QStatusBar { background: #323232; color: #e6e6e6; }
QStatusBar::item { border: none; }
QToolTip {
    background-color: #141414;
    color: #ffffff;
    border: 1px solid #ffffff;
    padding: 8px 12px;
    font-size: 12pt;
    font-weight: bold;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #2b2b2b;
    border: none;
}
QMessageBox { background: #2b2b2b; }
QMessageBox QLabel { color: #e6e6e6; }
"""


def relative_luminance(colour: QColor) -> float:
    def channel(value: int) -> float:
        s = value / 255.0
        if s <= 0.04045:
            return s / 12.92
        return ((s + 0.055) / 1.055) ** 2.4

    red = channel(colour.red())
    green = channel(colour.green())
    blue = channel(colour.blue())
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(foreground: QColor, background: QColor) -> float:
    lighter = max(relative_luminance(foreground), relative_luminance(background))
    darker = min(relative_luminance(foreground), relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _paint(palette: QPalette, group: QPalette.ColorGroup) -> None:
    palette.setColor(group, QPalette.ColorRole.Window, WINDOW)
    palette.setColor(group, QPalette.ColorRole.WindowText, TEXT if group != QPalette.ColorGroup.Disabled else MUTED)
    palette.setColor(group, QPalette.ColorRole.Base, PANEL)
    palette.setColor(group, QPalette.ColorRole.AlternateBase, RAISED)
    palette.setColor(group, QPalette.ColorRole.Text, TEXT if group != QPalette.ColorGroup.Disabled else MUTED)
    palette.setColor(group, QPalette.ColorRole.Button, RAISED)
    palette.setColor(group, QPalette.ColorRole.ButtonText, TEXT if group != QPalette.ColorGroup.Disabled else MUTED)
    palette.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#141414"))
    palette.setColor(group, QPalette.ColorRole.ToolTipText, WHITE)
    palette.setColor(group, QPalette.ColorRole.Highlight, ACCENT)
    palette.setColor(group, QPalette.ColorRole.HighlightedText, WHITE)
    palette.setColor(group, QPalette.ColorRole.PlaceholderText, MUTED)
    palette.setColor(group, QPalette.ColorRole.Light, BORDER)
    palette.setColor(group, QPalette.ColorRole.Mid, BORDER)
    palette.setColor(group, QPalette.ColorRole.Dark, QColor("#1e1e1e"))


def apply_dark_theme(app: QApplication | None = None) -> None:
    app = app or QApplication.instance()
    if app is None:
        return
    palette = QPalette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        _paint(palette, group)
    app.setPalette(palette)
    current = app.styleSheet() or ""
    if "QDockWidget::title" not in current:
        app.setStyleSheet(current + DARK_STYLE)
