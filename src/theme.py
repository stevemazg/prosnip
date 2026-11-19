"""One dark theme for every ProSnip-Bob window.

Palette and stylesheet are both set so a control cannot fall back to
black text on a black background.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
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
QPushButton, QComboBox, QListWidget, QPlainTextEdit, QTextEdit {
    background-color: #383838;
    color: #e6e6e6;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 22px;
}
QLineEdit {
    background-color: #383838;
    color: #e6e6e6;
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 2px 6px;
    min-height: 18px;
}
QPushButton:hover, QComboBox:hover {
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
    apply_theme("dark", app)


LIGHT = {
    "window": "#f4f5f6",
    "panel": "#ffffff",
    "raised": "#ffffff",
    "text": "#1a1d21",
    "muted": "#3d4750",
    "accent": "#3730a3",
    "border": "#c5c9cc",
    "workspace": "#f4f5f6",
}
DARK = {
    "window": "#141616",
    "panel": "#2e3334",
    "raised": "#3a4042",
    "text": "#f3f4f6",
    "muted": "#c5cdd1",
    "accent": "#818cf8",
    "border": "#4a5154",
    "workspace": "#1e2122",
}


def colours_for(mode: str) -> dict:
    return DARK if mode == "dark" else LIGHT


def resolved_mode(mode: str) -> str:
    if mode == "system":
        hint = QGuiApplication.styleHints()
        scheme = hint.colorScheme() if hint is not None else None
        if scheme is not None and scheme == Qt.ColorScheme.Dark:
            return "dark"
        return "light"
    return "dark" if mode == "dark" else "light"


def _sheet(colours: dict) -> str:
    return f"""
QWidget {{ background-color: {colours['window']}; color: {colours['text']}; font-size: 13px; }}
QMainWindow, QDialog, QMenuBar, QMenu {{ background-color: {colours['window']}; color: {colours['text']}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background-color: {colours['accent']}; color: #ffffff; }}
QMenu {{ border: 1px solid {colours['border']}; }}
QLabel {{ color: {colours['text']}; background: transparent; }}
QLabel#muted, QLabel#section {{ color: {colours['muted']}; }}
QPushButton, QComboBox, QListWidget, QPlainTextEdit, QTextEdit, QLineEdit {{
    background-color: {colours['panel']}; color: {colours['text']};
    border: 1px solid {colours['border']}; border-radius: 4px; padding: 2px 6px;
}}
QAbstractSpinBox QLineEdit {{ background: transparent; border: none; padding: 0; min-height: 0; color: {colours['text']}; }}
QPushButton:checked {{ background-color: {colours['accent']}; color: #ffffff; border-color: {colours['accent']}; }}
QToolTip {{ background-color: #141414; color: #ffffff; border: 1px solid #ffffff; padding: 6px 8px; }}
"""


def apply_theme(mode: str, app: QApplication | None = None) -> str:
    """Apply light, dark, or system. Returns the resolved mode."""
    app = app or QApplication.instance()
    resolved = resolved_mode(mode)
    colours = colours_for(resolved)
    global WINDOW, PANEL, RAISED, TEXT, MUTED, ACCENT, BORDER
    WINDOW = QColor(colours["window"])
    PANEL = QColor(colours["panel"])
    RAISED = QColor(colours["raised"])
    TEXT = QColor(colours["text"])
    MUTED = QColor(colours["muted"])
    ACCENT = QColor(colours["accent"])
    BORDER = QColor(colours["border"])
    if app is None:
        return resolved
    app.setStyle("Fusion")
    palette = QPalette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        _paint(palette, group)
    app.setPalette(palette)
    app.setStyleSheet(_sheet(colours))
    return resolved
