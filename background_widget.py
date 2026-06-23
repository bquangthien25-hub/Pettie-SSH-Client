"""Nền ảnh có cache — resize mượt hơn."""

import os

from PySide6.QtWidgets import QWidget, QLabel, QFrame
from ui_theme import get_resource_path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap


def _normalize_asset_path(path):
    """Chuẩn hóa đường dẫn preset assets/ khi chạy bản đóng gói."""
    if not path:
        return path
    if os.path.isfile(path):
        return path
    norm = path.replace("\\", "/")
    if norm.startswith("assets/"):
        resolved = get_resource_path(norm)
        if os.path.isfile(resolved):
            return resolved
    return path


class BackgroundWidget(QWidget):
    def __init__(self, bg_path=None, overlay_alpha=0.62, parent=None):
        super().__init__(parent)
        self._source_path = bg_path
        self._overlay_alpha = overlay_alpha
        self._pixmap_orig = None
        self._cached_size = None
        self._cached_scaled = None

        self._bg_label = QLabel(self)
        self._bg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._overlay = QFrame(self)
        self._overlay.setStyleSheet(
            f"background-color: rgba(9, 9, 11, {overlay_alpha});"
        )

        self._content = QWidget(self)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(80)
        self._resize_timer.timeout.connect(self._apply_bg_scale)

        if bg_path:
            bg_path = _normalize_asset_path(bg_path)
            if os.path.isfile(bg_path):
                self._load_source(bg_path)

    def content_widget(self):
        return self._content

    def set_background(self, path):
        path = _normalize_asset_path(path)
        self._source_path = path
        self._cached_size = None
        self._cached_scaled = None
        if path and os.path.isfile(path):
            self._load_source(path)
        else:
            self._pixmap_orig = None
        self._apply_bg_scale()

    def set_overlay(self, alpha, light=False):
        self._overlay_alpha = alpha
        if light:
            self._overlay.setStyleSheet(
                f"background-color: rgba(255, 255, 255, {alpha});"
            )
        else:
            self._overlay.setStyleSheet(
                f"background-color: rgba(9, 9, 11, {alpha});"
            )

    def _load_source(self, path):
        path = _normalize_asset_path(path)
        pm = QPixmap(path)
        if not pm.isNull():
            self._pixmap_orig = pm

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.rect()
        self._overlay.setGeometry(r)
        self._content.setGeometry(r)
        self._bg_label.lower()
        self._overlay.raise_()
        self._content.raise_()
        self._resize_timer.start()

    def _apply_bg_scale(self):
        r = self.rect()
        if r.width() < 1 or r.height() < 1:
            return

        if self._pixmap_orig and not self._pixmap_orig.isNull():
            key = (r.width(), r.height())
            if self._cached_size != key or self._cached_scaled is None:
                self._cached_scaled = self._pixmap_orig.scaled(
                    r.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._cached_size = key
            scaled = self._cached_scaled
            x = (r.width() - scaled.width()) // 2
            y = (r.height() - scaled.height()) // 2
            self._bg_label.setPixmap(scaled)
            self._bg_label.setGeometry(x, y, scaled.width(), scaled.height())
        else:
            self._bg_label.setGeometry(r)
            self._bg_label.setPixmap(QPixmap())
            self._bg_label.setStyleSheet("background-color: #e2e8f0;")
