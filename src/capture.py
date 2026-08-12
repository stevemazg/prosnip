from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPen, QImage
from PyQt6.QtCore import Qt, QRect, QPoint

import mss
import mss.tools
from PIL import Image
import io


class CaptureOverlay(QWidget):
    """Full-screen transparent overlay for region capture."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._start = QPoint()
        self._end = QPoint()
        self._dragging = False
        self._screenshot_pil = None
        self._background_pixmap = None

        self._setup_window()
        self._take_screenshot()

    def _setup_window(self):
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Cover all screens
        app = QApplication.instance()
        total_rect = app.primaryScreen().virtualGeometry()
        for screen in app.screens():
            total_rect = total_rect.united(screen.geometry())
        self.setGeometry(total_rect)

    def _take_screenshot(self):
        with mss.mss() as sct:
            # Capture all monitors combined
            monitor = sct.monitors[0]  # index 0 = all monitors combined
            shot = sct.grab(monitor)
            w, h = shot.width, shot.height
            raw = bytes(shot.raw)
            pil_img = Image.frombytes("RGB", (w, h), raw, "raw", "BGRX")
            self._screenshot_pil = pil_img

        # Convert to QPixmap for background
        buf = io.BytesIO()
        self._screenshot_pil.save(buf, format="PNG")
        buf.seek(0)
        data = buf.read()
        qimg = QImage.fromData(data)
        self._background_pixmap = QPixmap.fromImage(qimg)

    def paintEvent(self, event):
        painter = QPainter(self)

        # Draw screenshot as background
        if self._background_pixmap:
            painter.drawPixmap(0, 0, self._background_pixmap)

        # Dark overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        # Draw selection rectangle
        if self._dragging:
            sel = self._selection_rect()
            if not sel.isNull():
                # Reveal the screenshot within selection (remove dark overlay)
                if self._background_pixmap:
                    painter.drawPixmap(sel, self._background_pixmap, sel)
                # Red dashed border
                pen = QPen(QColor("#ff0000"), 2, Qt.PenStyle.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(sel)

        painter.end()

    def _selection_rect(self) -> QRect:
        return QRect(self._start, self._end).normalized()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start = event.position().toPoint()
            self._end = self._start
            self._dragging = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._end = event.position().toPoint()
            sel = self._selection_rect()
            if sel.width() > 4 and sel.height() > 4 and self._screenshot_pil:
                cropped = self._screenshot_pil.crop((
                    sel.left(), sel.top(), sel.right(), sel.bottom()
                ))
                self.hide()
                self._callback(cropped)
            else:
                self.hide()
                self._callback(None)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self._callback(None)
        else:
            super().keyPressEvent(event)
