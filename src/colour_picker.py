"""Full-screen colour picker across every monitor.

One frameless overlay is placed on each screen, the same way a snip is.
showFullScreen() is not used: it snaps a window back to the primary monitor.
The grab is kept in device pixels so the loupe and the arrow keys can land
on a single physical pixel at any scale factor.
"""

import logging

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from colour import (
    ZOOM_DEFAULT,
    ColourHistory,
    clamp_zoom,
    format_colour,
    next_format,
    parse_hex,
)

log = logging.getLogger(__name__)

LOUPE_CELLS = 11
LOUPE_HALF = LOUPE_CELLS // 2


def widget_to_pixel(x: int, y: int, widget_w: int, widget_h: int, image_w: int, image_h: int):
    """Map a point in overlay coordinates onto a device pixel of the grab."""
    if widget_w < 1 or widget_h < 1 or image_w < 1 or image_h < 1:
        return 0, 0
    px = (int(x) * image_w) // widget_w
    py = (int(y) * image_h) // widget_h
    return max(0, min(image_w - 1, px)), max(0, min(image_h - 1, py))


def loupe_top_left(
    cursor_x: int,
    cursor_y: int,
    block_w: int,
    block_h: int,
    widget_w: int,
    widget_h: int,
    gap: int = 18,
) -> tuple[int, int]:
    """Place the loupe beside the cursor, flipping at the screen edge."""
    x = cursor_x + gap
    y = cursor_y + gap
    if x + block_w > widget_w:
        x = cursor_x - gap - block_w
    if y + block_h > widget_h:
        y = cursor_y - gap - block_h
    return max(0, x), max(0, y)


def render_loupe(source: QImage, x: int, y: int, zoom: int) -> QImage:
    """Pixel grid centred on (x, y), with a white crosshair on that cell."""
    zoom = clamp_zoom(zoom)
    size = LOUPE_CELLS * zoom
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(QColor("#1a1a1a"))
    painter = QPainter(image)
    for row in range(LOUPE_CELLS):
        for col in range(LOUPE_CELLS):
            sx = x + col - LOUPE_HALF
            sy = y + row - LOUPE_HALF
            if source is not None and 0 <= sx < source.width() and 0 <= sy < source.height():
                colour = source.pixelColor(sx, sy)
            else:
                colour = QColor("#2a2a2a")
            painter.fillRect(col * zoom, row * zoom, zoom, zoom, colour)
    painter.setPen(QPen(QColor(255, 255, 255, 110), 1))
    for index in range(LOUPE_CELLS + 1):
        painter.drawLine(index * zoom, 0, index * zoom, size)
        painter.drawLine(0, index * zoom, size, index * zoom)
    origin = LOUPE_HALF * zoom
    painter.setPen(QPen(QColor("#ffffff"), max(2, zoom // 8)))
    painter.drawRect(origin, origin, max(1, zoom - 1), max(1, zoom - 1))
    painter.end()
    return image


class _Toast(QWidget):
    def __init__(self, text: str):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        label = QLabel(text, self)
        label.setStyleSheet(
            "background-color: #141414; color: #ffffff; border: 1px solid #ffffff;"
            "padding: 8px 12px; font-size: 12pt; font-weight: 600;"
        )
        label.adjustSize()
        self.resize(label.size())


_TOASTS: list[_Toast] = []


def show_toast(text: str, global_pos: QPoint) -> None:
    toast = _Toast(text)
    toast.move(global_pos.x() + 24, global_pos.y() + 24)
    toast.show()
    _TOASTS.append(toast)

    def _close():
        toast.close()
        toast.deleteLater()
        if toast in _TOASTS:
            _TOASTS.remove(toast)

    QTimer.singleShot(1400, _close)


class _PickerOverlay(QWidget):
    def __init__(self, session: "ColourPicker", screen, pixmap):
        super().__init__(None)
        self._session = session
        self.screen_ref = screen
        grabbed_ratio = pixmap.devicePixelRatio() or 1.0
        pixmap.setDevicePixelRatio(1.0)
        self._pixmap = pixmap
        self._image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        self._cursor = QPoint(self.width() // 2, self.height() // 2)
        self._pixel = (0, 0)
        self._swatches: list[tuple[QRect, str]] = []
        log.info(
            "Picker grabbed %s geometry=%s screen_dpr=%.2f pixmap_dpr=%.2f pixmap=%dx%d",
            screen.name() or "(unnamed)",
            screen.geometry(),
            screen.devicePixelRatio() or 1.0,
            grabbed_ratio,
            pixmap.width(),
            pixmap.height(),
        )
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def show_on_screen(self):
        screen = self.screen_ref
        geo = QRect(screen.geometry())
        self.setScreen(screen)
        self.setGeometry(geo)
        self.winId()
        self.show()
        handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(screen)
            handle.setGeometry(geo)
        self.setGeometry(screen.geometry())
        self._move_to_widget_point(QPoint(self.width() // 2, self.height() // 2))

    def set_sample_pixel(self, x: int, y: int):
        """Used by the demo grab, which does not move the real cursor."""
        self._pixel = (
            max(0, min(self._image.width() - 1, int(x))),
            max(0, min(self._image.height() - 1, int(y))),
        )
        if self.width() > 0 and self._image.width() > 0:
            self._cursor = QPoint(
                (self._pixel[0] * self.width()) // self._image.width(),
                (self._pixel[1] * self.height()) // self._image.height(),
            )
        self.update()

    def _move_to_widget_point(self, point: QPoint):
        point = QPoint(
            max(0, min(point.x(), max(0, self.width() - 1))),
            max(0, min(point.y(), max(0, self.height() - 1))),
        )
        self._cursor = point
        self._pixel = widget_to_pixel(
            point.x(), point.y(), self.width(), self.height(),
            self._image.width(), self._image.height(),
        )
        self.update()

    def _sample(self):
        if self._image.isNull():
            return 0, 0, 0
        colour = self._image.pixelColor(*self._pixel)
        return colour.red(), colour.green(), colour.blue()

    def _code_for(self, red, green, blue) -> str:
        return format_colour(red, green, blue, self._session.history.format)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        red, green, blue = self._sample()
        code = self._code_for(red, green, blue)
        zoom = self._session.history.zoom
        loupe = render_loupe(self._image, self._pixel[0], self._pixel[1], zoom)
        info_h = 44
        block_w = max(loupe.width(), 260)
        block_h = loupe.height() + info_h
        left, top = loupe_top_left(
            self._cursor.x(), self._cursor.y(), block_w, block_h, self.width(), self.height(),
        )
        painter.drawImage(left + (block_w - loupe.width()) // 2, top, loupe)
        info = QRect(left, top + loupe.height(), block_w, info_h)
        painter.fillRect(info, QColor("#141414"))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawRect(info)
        swatch = QRect(info.left() + 8, info.top() + 8, 28, 28)
        painter.fillRect(swatch, QColor(red, green, blue))
        painter.setPen(QPen(QColor("#ffffff"), 1))
        painter.drawRect(swatch)
        painter.setPen(QPen(QColor("#ffffff")))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            swatch.right() + 10, info.top(), info.width() - 48, info.height(),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            code,
        )
        self._paint_hud(painter)
        self._paint_swatches(painter)
        painter.end()

    def _paint_hud(self, painter: QPainter):
        zoom = self._session.history.zoom
        label = (
            f"{self._session.history.format.upper()}  ·  {zoom}×  ·  "
            "Tab or F changes format  ·  Esc cancels  ·  Enter picks"
        )
        rect = QRect(12, 12, min(self.width() - 24, 760), 32)
        painter.fillRect(rect, QColor(20, 20, 20, 220))
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(rect.adjusted(10, 0, -10, 0), int(Qt.AlignmentFlag.AlignVCenter), label)

    def _paint_swatches(self, painter: QPainter):
        self._swatches = []
        colours = self._session.history.colours
        if not colours:
            return
        size = 28
        gap = 6
        width = len(colours) * (size + gap) + gap
        left = max(8, (self.width() - width) // 2)
        top = max(8, self.height() - size - 16)
        for index, code in enumerate(colours):
            rect = QRect(left + index * (size + gap), top, size, size)
            parsed = parse_hex(code)
            colour = QColor(*parsed) if parsed else QColor("#000000")
            painter.fillRect(rect, colour)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.drawRect(rect)
            self._swatches.append((rect, code))

    def _swatch_at(self, point: QPoint) -> str | None:
        for rect, code in self._swatches:
            if rect.contains(point):
                return code
        return None

    def _copy(self, red: int, green: int, blue: int, stay: bool):
        text = self._code_for(red, green, blue)
        self._session.history.add_rgb(red, green, blue)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        show_toast(f"Copied {text}", self.mapToGlobal(self._cursor))
        log.info("Copied %s", text)
        self.update()
        if not stay:
            self._session.finish(format_colour(red, green, blue, "hex"))

    def _copy_current(self, stay: bool):
        self._copy(*self._sample(), stay)

    def wheelEvent(self, event):
        step = 1 if event.angleDelta().y() > 0 else -1
        self._session.set_zoom(self._session.history.zoom + step)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        self._move_to_widget_point(event.position().toPoint())
        event.accept()

    def mousePressEvent(self, event):
        self._move_to_widget_point(event.position().toPoint())
        swatch = self._swatch_at(event.position().toPoint())
        if swatch is not None:
            parsed = parse_hex(swatch)
            if parsed is not None:
                self._copy(*parsed, True)
            event.accept()
            return
        stay = (
            event.button() == Qt.MouseButton.RightButton
            or bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        )
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self._copy_current(stay)
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self._session.finish(None)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._copy_current(False)
            event.accept()
            return
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_F):
            self._session.cycle_format()
            self.update()
            event.accept()
            return
        if mods & Qt.KeyboardModifier.ControlModifier and key in (
            Qt.Key.Key_Minus,
            Qt.Key.Key_Underscore,
        ):
            self._session.set_zoom(self._session.history.zoom - 1)
            self.update()
            event.accept()
            return
        if mods & Qt.KeyboardModifier.ControlModifier and key in (
            Qt.Key.Key_Plus,
            Qt.Key.Key_Equal,
        ):
            self._session.set_zoom(self._session.history.zoom + 1)
            self.update()
            event.accept()
            return
        nudge = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }.get(key)
        if nudge is not None:
            self._nudge(*nudge)
            event.accept()
            return
        super().keyPressEvent(event)

    def _nudge(self, dx: int, dy: int):
        px = max(0, min(self._image.width() - 1, self._pixel[0] + dx))
        py = max(0, min(self._image.height() - 1, self._pixel[1] + dy))
        self._pixel = (px, py)
        if self._image.width() > 0 and self.width() > 0:
            local = QPoint(
                min(self.width() - 1, ((px * self.width()) + self._image.width() // 2) // self._image.width()),
                min(self.height() - 1, ((py * self.height()) + self._image.height() // 2) // self._image.height()),
            )
            self._cursor = local
            QCursor.setPos(self.mapToGlobal(local))
        self.update()

    def closeEvent(self, event):
        self._session.finish(None)
        event.accept()


class ColourPicker:
    """One picker session across every monitor. The callback receives a HEX code or None."""

    def __init__(self, callback, screens=None, history: ColourHistory | None = None, pixmaps=None):
        self._callback = callback
        self.history = history if history is not None else ColourHistory()
        self.history.zoom = clamp_zoom(self.history.zoom or ZOOM_DEFAULT)
        self._finished = False
        self._closed = False
        self._result = None
        self._overlays: list[_PickerOverlay] = []
        if screens is None:
            screens = list(QGuiApplication.screens())
        if not screens:
            raise RuntimeError("No screens are available to pick a colour")
        pixmaps = list(pixmaps or [])
        for index, screen in enumerate(screens):
            try:
                pixmap = pixmaps[index] if index < len(pixmaps) else screen.grabWindow(0)
                if pixmap is None or pixmap.isNull():
                    raise RuntimeError("empty grab")
                self._overlays.append(_PickerOverlay(self, screen, pixmap))
            except Exception:
                log.exception("Could not prepare the colour picker for %s", getattr(screen, "name", lambda: "a screen")())
        if not self._overlays:
            raise RuntimeError("No screens could be captured for the colour picker")

    @property
    def is_active(self) -> bool:
        return not self._closed

    def set_zoom(self, zoom: int):
        self.history.set_zoom(zoom)
        for overlay in self._overlays:
            overlay.update()

    def cycle_format(self):
        self.history.set_format(next_format(self.history.format))
        for overlay in self._overlays:
            overlay.update()

    def show(self):
        if self._finished or not self._overlays:
            raise RuntimeError("The colour picker is no longer active")
        for overlay in self._overlays:
            overlay.show_on_screen()
        target = self._overlay_under_cursor()
        target.raise_()
        target.activateWindow()
        target.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _overlay_under_cursor(self) -> _PickerOverlay:
        screen = QGuiApplication.screenAt(QCursor.pos())
        for overlay in self._overlays:
            if overlay.screen_ref is screen:
                return overlay
        return self._overlays[0]

    def finish(self, hex_code):
        if self._finished:
            return
        self._finished = True
        self._result = hex_code
        for overlay in self._overlays:
            overlay.hide()
        QTimer.singleShot(0, self._close_and_deliver)

    def abandon(self):
        if self._closed:
            return
        self._finished = True
        self._closed = True
        self._destroy()

    def _destroy(self):
        overlays = list(self._overlays)
        self._overlays.clear()
        for overlay in overlays:
            overlay.hide()
            overlay.close()
            overlay.deleteLater()

    def _close_and_deliver(self):
        if self._closed:
            return
        result = self._result
        self._closed = True
        self._destroy()
        try:
            self._callback(result)
        except Exception:
            log.exception("Colour picker callback failed")
