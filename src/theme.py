"""One dark theme for every ProSnip-Bob window.

Palette and stylesheet are both set so a control cannot fall back to
black text on a black background.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication

from pathlib import Path

WINDOW = QColor("#2b2b2b")
PANEL = QColor("#323232")
RAISED = QColor("#383838")
TEXT = QColor("#e6e6e6")
MUTED = QColor("#a0a0a0")
ACCENT = QColor("#4f46e5")
BORDER = QColor("#4a4a4a")
WHITE = QColor("#ffffff")


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
    "tray_fill": "#c7d2fe",
    "tray_text": "#3730a3",
    "indicator": "#3730a3",
}
DARK = {
    "window": "#141616",
    "panel": "#2e3334",
    "raised": "#3a4042",
    "text": "#f3f4f6",
    "muted": "#c5cdd1",
    "accent": "#4f46e5",
    "border": "#4a5154",
    "workspace": "#2b2b2b",
    "tray_fill": "#1e1b4b",
    "tray_text": "#e0e7ff",
    "indicator": "#818cf8",
}


def asset_file(name: str) -> Path:
    """A file shipped beside the source, or inside the frozen application."""
    import sys

    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    else:
        root = Path(__file__).resolve().parent.parent
    return root / "assets" / name


def checkbox_qss(colours: dict) -> str:
    tick = asset_file("checkbox-tick.png").as_posix()
    return f"""
QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 2px solid {colours['text']};
    background: {colours['panel']};
    border-radius: 2px;
}}
QCheckBox::indicator:checked {{
    background: {colours['indicator']};
    border: 2px solid {colours['indicator']};
    image: url("{tick}");
}}
"""


def colours_for(mode: str) -> dict:
    return DARK if mode == "dark" else LIGHT


_ACTIVE = dict(LIGHT)


def active_colours() -> dict:
    return _ACTIVE


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
{checkbox_qss(colours)}
QToolTip {{ background-color: #141414; color: #ffffff; border: 1px solid #ffffff; padding: 6px 8px; }}
QSplitter::handle {{ background-color: {colours['border']}; }}
"""


def apply_theme(mode: str, app: QApplication | None = None) -> str:
    """Apply light, dark, or system. Returns the resolved mode."""
    app = app or QApplication.instance()
    resolved = resolved_mode(mode)
    colours = colours_for(resolved)
    global _ACTIVE
    _ACTIVE = dict(colours)
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
    font = QFont("Segoe UI", 9)
    app.setFont(font)
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
