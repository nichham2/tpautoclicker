"""Full-screen overlay for picking a point or dragging out a region.

It shows a frozen screenshot of the monitor, so you can pick spots on the game
even though the overlay covers it. Results are in screenshot pixels, which are
the same pixels the matcher and the mouse use.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


def ndarray_to_qimage(img: np.ndarray) -> QImage:
    """BGR uint8 -> QImage (copied, so the array can be freed)."""
    rgb = np.ascontiguousarray(img[:, :, ::-1])
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class ScreenPicker(QWidget):
    """mode='point' emits picked(x, y, 0, 0); mode='region' emits picked(x, y, w, h)."""

    picked = Signal(int, int, int, int)
    cancelled = Signal()

    def __init__(self, screenshot: np.ndarray, mode: str = "point", geometry: QRect | None = None,
                 hint: str = "") -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.img = screenshot
        self.pix = QPixmap.fromImage(ndarray_to_qimage(screenshot))
        self.mode = mode
        self.hint = hint or ("Click a spot. Esc to cancel." if mode == "point"
                             else "Drag a box around the button or text. Esc to cancel.")
        self._start: QPoint | None = None
        self._cur = QPoint()
        if geometry is not None:
            self.setGeometry(geometry)

    # widget coords -> screenshot pixel coords
    def _to_px(self, p: QPoint) -> tuple[int, int]:
        sx = self.img.shape[1] / max(1, self.width())
        sy = self.img.shape[0] / max(1, self.height())
        return int(p.x() * sx), int(p.y() * sy)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.cancelled.emit()
            self.close()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.cancelled.emit()
            self.close()
            return
        p = e.position().toPoint()
        if self.mode == "point":
            x, y = self._to_px(p)
            self.picked.emit(x, y, 0, 0)
            self.close()
        else:
            self._start = p
            self._cur = p
            self.update()

    def mouseMoveEvent(self, e):
        self._cur = e.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, e):
        if self.mode != "region" or self._start is None:
            return
        r = QRect(self._start, e.position().toPoint()).normalized()
        self._start = None
        if r.width() < 4 or r.height() < 4:
            self.update()
            return
        x0, y0 = self._to_px(r.topLeft())
        x1, y1 = self._to_px(r.bottomRight())
        self.picked.emit(x0, y0, x1 - x0, y1 - y0)
        self.close()

    def paintEvent(self, _):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 70))
        if self._start is not None:
            r = QRect(self._start, self._cur).normalized()
            src = QRect(*[int(v) for v in (
                r.x() * self.img.shape[1] / self.width(), r.y() * self.img.shape[0] / self.height(),
                r.width() * self.img.shape[1] / self.width(), r.height() * self.img.shape[0] / self.height())])
            p.drawPixmap(r, self.pix, src)  # un-dimmed selection
            p.setPen(QPen(QColor(0, 200, 255), 2))
            p.drawRect(r)
        else:
            p.setPen(QPen(QColor(0, 200, 255, 160), 1))
            p.drawLine(self._cur.x(), 0, self._cur.x(), self.height())
            p.drawLine(0, self._cur.y(), self.width(), self._cur.y())
        # hint banner + live coordinates
        x, y = self._to_px(self._cur)
        text = f"{self.hint}    ({x}, {y})"
        p.setFont(QFont("Segoe UI", 12))
        fm = p.fontMetrics()
        box = QRect(0, 0, fm.horizontalAdvance(text) + 24, fm.height() + 14)
        box.moveCenter(QPoint(self.width() // 2, box.height() // 2 + 12))
        p.fillRect(box, QColor(20, 20, 20, 220))
        p.setPen(QColor(255, 255, 255))
        p.drawText(box, Qt.AlignCenter, text)
        p.end()
