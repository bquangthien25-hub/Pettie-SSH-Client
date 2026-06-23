"""Thanh sóng nhạc (equalizer) trang trí."""

import random

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QLinearGradient
from PySide6.QtWidgets import QWidget, QSizePolicy


class MusicBarsWidget(QWidget):
    """Dải cột nhảy ngẫu nhiên giống visualizer nhạc."""

    def __init__(self, bar_count=20, accent="#2dd4bf", parent=None):
        super().__init__(parent)
        self._bar_count = max(8, bar_count)
        self._accent = QColor(accent)
        self._heights = [0.25] * self._bar_count
        self._targets = [0.25] * self._bar_count
        self.setFixedHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(70)

    def set_accent(self, color):
        self._accent = QColor(color)
        self.update()

    def _tick(self):
        for i in range(self._bar_count):
            if random.random() < 0.28:
                self._targets[i] = random.uniform(0.12, 1.0)
            self._heights[i] += (self._targets[i] - self._heights[i]) * 0.24
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return
        gap = 3
        bar_w = max(4, (w - gap * (self._bar_count + 1)) // self._bar_count)
        x = gap
        for frac in self._heights:
            bh = max(4, int(h * frac * 0.95))
            y = h - bh
            grad = QLinearGradient(0, y, 0, h)
            top = self._accent.lighter(140)
            grad.setColorAt(0, top)
            grad.setColorAt(1, self._accent)
            p.setBrush(grad)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(int(x), y, bar_w, bh, 3, 3)
            x += bar_w + gap

    def hideEvent(self, event):
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        if not self._timer.isActive():
            self._timer.start(70)
        super().showEvent(event)
