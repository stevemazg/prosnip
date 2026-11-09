"""Screen recording.

Frames come from QScreen.grabWindow (one monitor, a dragged region, or the
on-screen area of one top-level window) and are streamed to a bundled ffmpeg
process. Frames are not kept in a list, so a long recording stays bounded.
There is no audio and no global keyboard hook.

The on-screen control is excluded from capture with SetWindowDisplayAffinity
where Windows supports it. The user still sees that control.
"""

import logging
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QRect, QTimer, Qt, pyqtSignal, QObject
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import imageio_ffmpeg

from window_list import list_toplevel_windows, window_capture_rect

log = logging.getLogger(__name__)

WDA_EXCLUDEFROMCAPTURE = 0x00000011
DEFAULT_FPS = 15
QUEUE_LIMIT = 2


def even_size(width: int, height: int) -> tuple[int, int]:
    width = max(2, int(width) - (int(width) % 2))
    height = max(2, int(height) - (int(height) % 2))
    return width, height


def even_rect(rect: QRect) -> QRect:
    width, height = even_size(rect.width(), rect.height())
    return QRect(rect.x(), rect.y(), width, height)


def video_output_path(moment: datetime | None = None) -> Path:
    moment = moment or datetime.now()
    folder = Path.home() / "Videos" / "ProSnip-Bob"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / moment.strftime("ProSnip-Bob_%Y%m%d_%H%M%S.mp4")


def enqueue_frame(frames: queue.Queue, payload: bytes) -> None:
    """Keep at most QUEUE_LIMIT frames. Drop the oldest when the encoder lags."""
    if frames.full():
        try:
            frames.get_nowait()
        except queue.Empty:
            pass
    try:
        frames.put_nowait(payload)
    except queue.Full:
        pass


def frame_to_rgb(image: QImage, width: int, height: int) -> bytes:
    scaled = image.scaled(
        width,
        height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled = scaled.convertToFormat(QImage.Format.Format_RGB888)
    row_bytes = width * 3
    stride = scaled.bytesPerLine()
    pointer = scaled.constBits()
    pointer.setsize(scaled.sizeInBytes())
    raw = bytes(pointer)
    if stride == row_bytes:
        return raw[: row_bytes * height]
    out = bytearray(row_bytes * height)
    for y in range(height):
        start = y * stride
        out[y * row_bytes : (y + 1) * row_bytes] = raw[start : start + row_bytes]
    return bytes(out)


def ffmpeg_command(width: int, height: int, fps: int, path: Path) -> list[str]:
    return [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(path),
    ]


def exclude_from_capture(widget: QWidget) -> bool:
    """Keep widget visible to the user but out of Windows screen capture."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL
    ok = user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)
    if not ok:
        log.warning(
            "Could not exclude the recording control from capture (Win32 error %s)",
            ctypes.get_last_error(),
        )
    return bool(ok)


class GrabSource:
    """Repeatedly grab one QScreen, or a physical rectangle of it.

    ``physical_rect`` None means the whole monitor.
    """

    def __init__(self, screen, physical_rect: QRect | None = None):
        self.screen = screen
        self.rect = None if physical_rect is None else even_rect(physical_rect)

    def grab(self) -> QImage | None:
        rect = self.rect
        if rect is None:
            pixmap = self.screen.grabWindow(0)
        else:
            if rect.width() < 2 or rect.height() < 2:
                return None
            pixmap = self.screen.grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        if pixmap.isNull():
            return None
        pixmap.setDevicePixelRatio(1.0)
        return pixmap.toImage()


class WindowGrabSource:
    """Grab the on-screen area of one top-level window, following it if it moves."""

    def __init__(self, hwnd: int):
        self.hwnd = int(hwnd)

    def grab(self) -> QImage | None:
        located = window_capture_rect(self.hwnd)
        if located is None:
            return None
        screen, rect = located
        return GrabSource(screen, rect).grab()


class RecordDialog(QDialog):
    def __init__(self, mode: str = "monitor", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record")
        self.setModal(True)
        self._mode = mode if mode in ("monitor", "region", "window") else "monitor"
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._monitor = QRadioButton("Whole monitor")
        self._region = QRadioButton("Dragged region")
        self._window = QRadioButton("Application window")
        {"monitor": self._monitor, "region": self._region, "window": self._window}[self._mode].setChecked(True)
        layout.addWidget(self._monitor)
        layout.addWidget(self._region)
        layout.addWidget(self._window)

        self._screen_combo = QComboBox()
        from PyQt6.QtGui import QGuiApplication
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            label = screen.name() or "Monitor"
            self._screen_combo.addItem(
                f"{label} ({geo.width()}×{geo.height()})",
                screen,
            )
        form.addRow("Monitor:", self._screen_combo)

        self._window_combo = QComboBox()
        self._windows = list_toplevel_windows()
        if self._windows:
            for hwnd, title in self._windows:
                self._window_combo.addItem(title, hwnd)
        else:
            self._window_combo.addItem("No windows found", 0)
            self._window.setEnabled(sys.platform == "win32" and bool(self._windows))
        form.addRow("Window:", self._window_combo)

        self._fps = QSpinBox()
        self._fps.setRange(15, 30)
        self._fps.setValue(DEFAULT_FPS)
        form.addRow("Frames per second:", self._fps)
        layout.addLayout(form)

        note = QLabel(
            "No sound is recorded. A browser tab cannot be recorded on its own; "
            "choose the browser window. If another window covers it, that covering "
            "window is what is recorded."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Start")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 280)

    def mode(self) -> str:
        if self._region.isChecked():
            return "region"
        if self._window.isChecked():
            return "window"
        return "monitor"

    def fps(self) -> int:
        return int(self._fps.value())

    def screen(self):
        return self._screen_combo.currentData()

    def hwnd(self) -> int:
        value = self._window_combo.currentData()
        return int(value or 0)


class RecordingControl(QWidget):
    pause_toggled = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("ProSnip-Bob recording")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self._paused = False
        self._build()

    def _build(self):
        self.setStyleSheet(
            "QWidget { background: #1e1e1e; color: #f5f5f5; }"
            "QPushButton { background: #2d2d2d; color: #f5f5f5; "
            "border: 1px solid #5a5a5a; border-radius: 4px; padding: 4px 10px; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        self._rec = QLabel("REC")
        self._rec.setStyleSheet("color: #ff4d5a; font-weight: 700;")
        self._time = QLabel("00:00")
        self._pause = QPushButton("Pause")
        self._stop = QPushButton("Stop")
        self._pause.clicked.connect(self.pause_toggled.emit)
        self._stop.clicked.connect(self.stop_requested.emit)
        row.addWidget(self._rec)
        row.addWidget(self._time)
        row.addWidget(self._pause)
        row.addWidget(self._stop)
        self.adjustSize()

    def set_elapsed(self, milliseconds: int) -> None:
        total = max(0, int(milliseconds // 1000))
        self._time.setText(f"{total // 60:02d}:{total % 60:02d}")

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._pause.setText("Resume" if paused else "Pause")
        self._rec.setText("PAUSE" if paused else "REC")

    def place_on_screen(self) -> None:
        from PyQt6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.show()
            return
        area = screen.availableGeometry()
        self.adjustSize()
        self.move(area.right() - self.width() - 16, area.top() + 16)
        self.show()
        self.raise_()
        exclude_from_capture(self)

    def closeEvent(self, event):
        self.stop_requested.emit()
        event.ignore()


class ScreenRecorder(QObject):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, source, path: Path, fps: int = DEFAULT_FPS):
        super().__init__()
        self._source = source
        self.path = Path(path)
        self.fps = max(15, min(30, int(fps)))
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_LIMIT)
        self._proc = None
        self._writer = None
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / self.fps))
        self._timer.timeout.connect(self._on_tick)
        self._clock = QTimer(self)
        self._clock.setInterval(200)
        self._clock.timeout.connect(self._on_clock)
        self._control = RecordingControl()
        self._control.pause_toggled.connect(self.toggle_pause)
        self._control.stop_requested.connect(self.stop)
        self._size = None
        self._paused = False
        self._elapsed = 0
        self._running_since = None
        self._stopping = False
        self._writer_error = None
        self.is_active = False

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._control.place_on_screen()
        self._timer.start()
        self._clock.start()
        self._mark_running()
        self.is_active = True
        log.info("Recording started: %s at %s fps", self.path, self.fps)

    def toggle_pause(self) -> None:
        if not self.is_active:
            return
        if self._paused:
            self._paused = False
            self._mark_running()
            log.info("Recording resumed")
        else:
            self._paused = True
            self._elapsed += self._take_running()
            log.info("Recording paused")
        self._control.set_paused(self._paused)

    def stop(self) -> None:
        if self._stopping:
            return
        self._stopping = True
        self.is_active = False
        self._timer.stop()
        self._clock.stop()
        try:
            self._control.stop_requested.disconnect(self.stop)
        except TypeError:
            pass
        if not self._paused:
            self._elapsed += self._take_running()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                pass
            self._queue.put_nowait(None)
        if self._writer is not None:
            self._writer.join(timeout=20)
        if self._proc is not None:
            try:
                self._proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._control.hide()
        self._control.deleteLater()
        if self._writer_error:
            log.error("Recording failed: %s", self._writer_error)
            self.failed.emit(self._writer_error)
            return
        if self._proc is None:
            message = "Recording stopped before any frames were saved."
            log.error(message)
            self.failed.emit(message)
            return
        if self._proc is not None and self._proc.returncode not in (0, None):
            message = f"The video encoder exited with code {self._proc.returncode}."
            log.error(message)
            self.failed.emit(message)
            return
        log.info("Recording stopped: %s", self.path)
        self.finished.emit(str(self.path))

    def _mark_running(self) -> None:
        self._running_since = datetime.now()

    def _take_running(self) -> int:
        if self._running_since is None:
            return 0
        delta = int((datetime.now() - self._running_since).total_seconds() * 1000)
        self._running_since = None
        return max(0, delta)

    def _on_clock(self) -> None:
        extra = 0 if self._paused or self._running_since is None else self._take_peek()
        self._control.set_elapsed(self._elapsed + extra)

    def _take_peek(self) -> int:
        if self._running_since is None:
            return 0
        return max(0, int((datetime.now() - self._running_since).total_seconds() * 1000))

    def _on_tick(self) -> None:
        if self._writer_error:
            self.stop()
            return
        if self._paused:
            return
        image = self._source.grab()
        if image is None or image.width() < 2 or image.height() < 2:
            self._writer_error = "Screen grab returned no image."
            log.error(self._writer_error)
            self.stop()
            return
        if self._size is None:
            self._size = even_size(image.width(), image.height())
            try:
                self._open_encoder()
            except Exception as exc:
                log.exception("Could not start the video encoder")
                self._writer_error = str(exc) or "Could not start the video encoder."
                self.stop()
                return
        try:
            payload = frame_to_rgb(image, self._size[0], self._size[1])
        except Exception:
            log.exception("Could not convert a recording frame")
            return
        enqueue_frame(self._queue, payload)

    def _open_encoder(self) -> None:
        width, height = self._size
        command = ffmpeg_command(width, height, self.fps, self.path)
        log.info("Encoder: %s", " ".join(command))
        self._proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        self._writer = threading.Thread(target=self._write_frames, daemon=True)
        self._writer.start()

    def _drain_stderr(self) -> None:
        if self._proc is None or self._proc.stderr is None:
            return
        chunks = []
        for line in self._proc.stderr:
            chunks.append(line)
            if sum(len(part) for part in chunks) > 8192:
                chunks = chunks[-20:]
        if chunks:
            log.info("ffmpeg: %s", b"".join(chunks)[-2000:].decode("utf-8", "replace"))

    def _write_frames(self) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        try:
            while True:
                item = self._queue.get()
                if item is None:
                    break
                self._proc.stdin.write(item)
        except Exception as exc:
            self._writer_error = str(exc) or "Could not write a video frame."
            log.exception("Recording writer failed")
        finally:
            try:
                self._proc.stdin.close()
            except Exception:
                pass
