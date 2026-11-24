"""
Per-monitor region capture.

One frameless overlay is placed on each monitor. Capture therefore works
with two or more screens, with monitors to the left of or above the primary
(negative virtual-desktop coordinates), and with mixed scale factors.

The overlay is not shown with showFullScreen(). On Qt that call snaps the
window back to the primary monitor and drops a negative origin.
"""

import logging
import math

from PIL import Image
from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QGuiApplication,
    QImage,
    QKeySequence,
    QBrush,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

# Logical pixels. A smaller drag is a cancelled selection.
MIN_SELECTION = 5


class RegionSelection:
    """A dragged rectangle on one monitor, in that monitor's pixels."""

    def __init__(self, screen, physical_rect: QRect, logical_rect: QRect, screen_geometry: QRect):
        self.screen = screen
        self.physical_rect = QRect(physical_rect)
        self.logical_rect = QRect(logical_rect)
        self.screen_geometry = QRect(screen_geometry)


def map_widget_rect_to_pixmap(
    selection: QRect,
    widget_width: int,
    widget_height: int,
    pixmap_width: int,
    pixmap_height: int,
) -> QRect:
    """Map a widget-local selection onto pixmap pixels.

    ``selection`` is in the overlay's own coordinates, whose origin is the
    top-left of that monitor. A monitor that sits at a negative virtual-desktop
    position still produces a crop that starts at (0, 0) of that monitor's grab.

    The pixmap is the raw grab (physical pixels). The widget is sized in
    logical pixels, so the scale between them is this monitor's device pixel
    ratio, including fractional scales such as 150%. Edges are converted with
    integer floor/ceil so a pixel the user touched is not dropped.
    """
    if (
        widget_width < 1
        or widget_height < 1
        or pixmap_width < 1
        or pixmap_height < 1
    ):
        return QRect()

    selection = selection.normalized().intersected(QRect(0, 0, widget_width, widget_height))
    if selection.width() < 1 or selection.height() < 1:
        return QRect()

    def floor_to(value: int, src: int, dst: int) -> int:
        return (value * dst) // src

    def ceil_to(value: int, src: int, dst: int) -> int:
        if value <= 0:
            return 0
        return (value * dst + src - 1) // src

    left = floor_to(selection.x(), widget_width, pixmap_width)
    top = floor_to(selection.y(), widget_height, pixmap_height)
    right = ceil_to(selection.x() + selection.width(), widget_width, pixmap_width)
    bottom = ceil_to(selection.y() + selection.height(), widget_height, pixmap_height)

    left = max(0, min(left, pixmap_width))
    right = max(left, min(right, pixmap_width))
    top = max(0, min(top, pixmap_height))
    bottom = max(top, min(bottom, pixmap_height))
    if right <= left or bottom <= top:
        return QRect()
    return QRect(left, top, right - left, bottom - top)


def qpixmap_to_pil(pixmap: QPixmap) -> Image.Image:
    """Convert a QPixmap to an owned RGB PIL image."""
    if pixmap.isNull():
        raise ValueError("Cannot convert a null pixmap")
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width = image.width()
    height = image.height()
    if width < 1 or height < 1:
        raise ValueError("Pixmap has no pixels")
    pointer = image.constBits()
    pointer.setsize(image.sizeInBytes())
    pil = Image.frombytes(
        "RGBA",
        (width, height),
        bytes(pointer),
        "raw",
        "RGBA",
        image.bytesPerLine(),
        1,
    )
    return pil.convert("RGB")


def crop_selection(
    pixmap: QPixmap,
    selection: QRect,
    widget_width: int,
    widget_height: int,
) -> QPixmap | None:
    """Copy ``selection`` out of ``pixmap`` in that pixmap's pixel grid."""
    if pixmap.isNull():
        return None
    # copy() and drawPixmap() source rects are device pixels. Drop the device
    # pixel ratio so those calls cannot reinterpret the rect as logical pixels.
    if not math.isclose(pixmap.devicePixelRatio(), 1.0):
        pixmap = pixmap.copy()
        pixmap.setDevicePixelRatio(1.0)
    mapped = map_widget_rect_to_pixmap(
        selection,
        widget_width,
        widget_height,
        pixmap.width(),
        pixmap.height(),
    )
    if mapped.isEmpty():
        return None
    crop = pixmap.copy(mapped)
    if crop.isNull() or crop.width() < 1 or crop.height() < 1:
        return None
    crop.setDevicePixelRatio(1.0)
    return crop


def _same_screen(left, right) -> bool:
    if left is None or right is None:
        return False
    if left is right:
        return True
    return left.name() == right.name() and left.geometry() == right.geometry()


class _ScreenOverlay(QWidget):
    """Covers exactly one monitor and shows a frozen grab of it."""

    def __init__(self, session: "CaptureOverlay", screen, pixmap: QPixmap | None = None):
        super().__init__(None)
        self._session = session
        self.screen_ref = screen
        self._start = QPoint()
        self._end = QPoint()
        self._dragging = False

        if pixmap is None:
            pixmap = screen.grabWindow(0)
        if pixmap.isNull():
            raise RuntimeError(f"Screen grab returned nothing for {screen.name() or 'a screen'}")
        # Keep the grabbed pixels addressable 1:1. Width and height stay in
        # device pixels; the ratio is remembered only in the log.
        grabbed_ratio = pixmap.devicePixelRatio() or 1.0
        pixmap.setDevicePixelRatio(1.0)
        self._pixmap = pixmap
        log.info(
            "Grabbed %s geometry=%s screen_dpr=%.2f pixmap_dpr=%.2f pixmap=%dx%d",
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
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self).activated.connect(
            lambda: self._session.finish(None)
        )

    def show_on_screen(self):
        screen = self.screen_ref
        geo = QRect(screen.geometry())
        self.setScreen(screen)
        self.setGeometry(geo)
        # Create the native window, then place it again. A frameless window
        # keeps negative coordinates; showFullScreen() would not.
        self.winId()
        self.show()
        handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(screen)
            handle.setGeometry(geo)
        self.setGeometry(screen.geometry())
        if self.geometry() != screen.geometry():
            log.warning(
                "Overlay on %s is %s; expected %s. Reapplying.",
                screen.name() or "(unnamed)",
                self.geometry(),
                screen.geometry(),
            )
            self.setGeometry(screen.geometry())
        else:
            log.info(
                "Overlay %s placed at %s",
                screen.name() or "(unnamed)",
                self.geometry(),
            )

    def _selection(self) -> QRect:
        rect = QRect(self._start, self._end).normalized()
        return rect.intersected(QRect(0, 0, self.width(), self.height()))

    def _clamp(self, point: QPoint) -> QPoint:
        return QPoint(
            max(0, min(point.x(), max(0, self.width()))),
            max(0, min(point.y(), max(0, self.height()))),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if self._dragging:
            selection = self._selection()
            if not selection.isEmpty():
                source = map_widget_rect_to_pixmap(
                    selection,
                    self.width(),
                    self.height(),
                    self._pixmap.width(),
                    self._pixmap.height(),
                )
                if not source.isEmpty():
                    painter.drawPixmap(selection, self._pixmap, source)
                painter.setPen(QPen(QColor("#ff0000"), 2, Qt.PenStyle.DashLine))
                painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                painter.drawRect(selection.adjusted(0, 0, -1, -1))
        painter.end()

    def _local_point(self, event) -> QPoint:
        # position() is widget-local. globalPosition() would include the
        # monitor's virtual-desktop origin and shift the crop.
        return self._clamp(event.position().toPoint())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = self._local_point(event)
            self._end = self._start
            self._dragging = True
            self.update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self._session.finish(None)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._end = self._local_point(event)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            super().mouseReleaseEvent(event)
            return
        self._dragging = False
        self._end = self._local_point(event)
        selection = self._selection()
        if selection.width() < MIN_SELECTION or selection.height() < MIN_SELECTION:
            self._session.finish(None)
            event.accept()
            return
        try:
            crop = crop_selection(
                self._pixmap,
                selection,
                self.width(),
                self.height(),
            )
            if self._session.kind == "region":
                physical = map_widget_rect_to_pixmap(
                    selection, self.width(), self.height(),
                    self._pixmap.width(), self._pixmap.height(),
                )
                if physical.isEmpty():
                    self._session.finish(None)
                else:
                    self._session.finish(RegionSelection(
                        self.screen_ref,
                        physical,
                        selection,
                        self.screen_ref.geometry(),
                    ))
                event.accept()
                return
            image = qpixmap_to_pil(crop) if crop is not None else None
        except Exception:
            log.exception("Failed to crop the selection")
            image = None
        self._session.finish(image)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._session.finish(None)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        # Alt+F4 on one monitor cancels the whole session. finish() is a
        # no-op if a result was already chosen.
        self._session.finish(None)
        event.accept()


class CaptureOverlay:
    """One capture session across every monitor.

    The callback is invoked once, on the GUI thread, with a PIL image or None
    when the snip is cancelled.
    """

    def __init__(self, callback, screens=None, kind="image"):
        self._callback = callback
        self.kind = kind if kind in ("image", "region") else "image"
        self._finished = False
        self._closed = False
        self._result = None
        self._overlays: list[_ScreenOverlay] = []
        if screens is None:
            screens = list(QGuiApplication.screens())
        if not screens:
            raise RuntimeError("No screens are available to capture")
        for screen in screens:
            try:
                self._overlays.append(_ScreenOverlay(self, screen))
            except Exception:
                log.exception("Could not prepare the overlay for %s", screen.name() or "a screen")
        if not self._overlays:
            raise RuntimeError("No screens could be captured")

    @property
    def is_active(self) -> bool:
        return not self._closed

    def show(self):
        if self._finished or not self._overlays:
            raise RuntimeError("The capture session is no longer active")
        for overlay in self._overlays:
            overlay.show_on_screen()
        target = self._overlay_under_cursor()
        target.raise_()
        target.activateWindow()
        target.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _overlay_under_cursor(self) -> _ScreenOverlay:
        screen = QGuiApplication.screenAt(QCursor.pos())
        for overlay in self._overlays:
            if _same_screen(overlay.screen_ref, screen):
                return overlay
        return self._overlays[0]

    def finish(self, image):
        if self._finished:
            return
        self._finished = True
        self._result = image
        for overlay in self._overlays:
            overlay.hide()
        # Closing the overlay inside its own mouse handler deletes the widget
        # that is still on the stack. Deliver on the next turn.
        QTimer.singleShot(0, self._close_and_deliver)

    def abandon(self):
        """Close without delivering a result. Used when startup fails."""
        if self._closed:
            return
        self._finished = True
        self._closed = True
        self._destroy_overlays()

    def _destroy_overlays(self):
        overlays = list(self._overlays)
        self._overlays.clear()
        for overlay in overlays:
            overlay.hide()
            overlay.close()
            overlay.deleteLater()

    def _close_and_deliver(self):
        if self._closed:
            return
        image = self._result
        self._closed = True
        self._destroy_overlays()
        try:
            self._callback(image)
        except Exception:
            log.exception("Capture callback failed")
