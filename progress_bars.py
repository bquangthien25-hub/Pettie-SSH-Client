"""Thanh tiến trình tùy chỉnh — splash xanh lá & thanh truyền file tối giản."""

import time

from PySide6.QtCore import Qt, QTimer, Signal, QRectF
from PySide6.QtGui import QLinearGradient, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)


def _spaced_percent(value: float) -> str:
    """Hiển thị phần trăm theo dung lượng thực — vd. 45%."""
    return f"{max(0, min(100, int(round(value))))}%"


def _normalize_bytes(value) -> float:
    """Chuẩn hóa byte count — tránh overflow 32-bit (>2GB thành số âm)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0.0
    if n < 0:
        n += 1 << 32
    return float(n)


def _fmt_percent(transferred: float, total: float) -> float:
    if total > 0:
        return max(0.0, min(100.0, transferred * 100.0 / total))
    return 0.0


class PillProgressBar(QWidget):
    """Thanh pill bo tròn — fill theo % dung lượng thực tế."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, percent: float):
        self._value = max(0.0, min(100.0, float(percent)))
        self.update()

    def value(self) -> float:
        return self._value

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 8:
            return
        radius = h / 2.0
        track = QRectF(1, 1, w - 2, h - 2)

        p.setPen(QPen(QColor("#fafafa"), 1.5))
        p.setBrush(QColor("#18181b"))
        p.drawRoundedRect(track, radius, radius)

        fill_w = max(0.0, (track.width() - 4) * self._value / 100.0)
        if fill_w > 0:
            fill = QRectF(track.x() + 2, track.y() + 2, fill_w, track.height() - 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#fafafa"))
            p.drawRoundedRect(fill, radius - 2, radius - 2)


class MinimalProgressBar(PillProgressBar):
    """Alias giữ tương thích."""


class GreenSplashProgressBar(QWidget):
    """Thanh xanh lá bóng — splash khi mở app."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self.setFixedHeight(28)
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, percent: float):
        self._value = max(0.0, min(100.0, float(percent)))
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        if w < 20:
            return
        radius = h / 2.0
        track = QRectF(1, 1, w - 2, h - 2)

        p.setPen(QPen(QColor("#6b7280"), 2))
        p.setBrush(QColor("#111827"))
        p.drawRoundedRect(track, radius, radius)

        fill_w = max(0.0, (track.width() - 4) * self._value / 100.0)
        if fill_w <= 0:
            return

        fill = QRectF(track.x() + 2, track.y() + 2, fill_w, track.height() - 4)
        grad = QLinearGradient(fill.left(), 0, fill.right(), 0)
        grad.setColorAt(0.0, QColor("#15803d"))
        grad.setColorAt(0.45, QColor("#4ade80"))
        grad.setColorAt(0.85, QColor("#86efac"))
        grad.setColorAt(1.0, QColor("#bbf7d0"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(fill, radius - 2, radius - 2)

        stripe = QPen(QColor(0, 0, 0, 35), 3)
        p.setPen(stripe)
        x = fill.left() - 20
        while x < fill.right() + 20:
            p.drawLine(int(x), int(fill.top()), int(x + 14), int(fill.bottom()))
            x += 12

        glow_x = fill.right() - 6
        glow = QLinearGradient(glow_x - 18, 0, glow_x + 10, 0)
        glow.setColorAt(0.0, QColor(255, 255, 200, 0))
        glow.setColorAt(0.5, QColor(255, 255, 180, 160))
        glow.setColorAt(1.0, QColor(255, 255, 220, 220))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawRoundedRect(
            QRectF(max(fill.left(), glow_x - 18), fill.top(), 28, fill.height()),
            4, 4,
        )


class TransferProgressPanel(QFrame):
    """Thanh tiến trình cố định phía dưới cửa sổ truyền file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("transferProgressPanel")
        self._started_at = None
        self._last_transferred = 0.0
        self._last_total = 0.0
        self._last_name = ""
        self._tick = QTimer(self)
        self._tick.setInterval(500)
        self._tick.timeout.connect(self._refresh_elapsed)

        self.setStyleSheet("""
            QFrame#transferProgressPanel {
                background-color: #09090b;
                border-top: 1px solid #27272a;
            }
            QLabel#xferPct {
                color: #fafafa;
                font-size: 20px;
                font-weight: 600;
            }
            QLabel#xferDetail {
                color: #71717a;
                font-size: 11px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 10, 24, 12)
        layout.setSpacing(6)

        self.lbl_pct = QLabel("0%")
        self.lbl_pct.setObjectName("xferPct")
        self.lbl_pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_pct)

        self.bar = PillProgressBar()
        layout.addWidget(self.bar)

        self.lbl_detail = QLabel("")
        self.lbl_detail.setObjectName("xferDetail")
        self.lbl_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_detail)

        self.hide()

    def start(self, filename: str, action: str = "Truyền", total_bytes: float = 0):
        self._started_at = time.monotonic()
        self._last_transferred = 0.0
        self._last_total = max(0.0, float(total_bytes))
        self._last_name = filename
        self.lbl_pct.setText("0%")
        self.bar.set_value(0)
        detail = f"{action}: {filename}"
        if self._last_total > 0:
            detail += f"  ·  0 / {_fmt_bytes(self._last_total)}"
        self.lbl_detail.setText(detail)
        self.show()
        self._tick.start()

    def update_progress(self, transferred: float, total: float, name: str):
        transferred = _normalize_bytes(transferred)
        total = _normalize_bytes(total)
        if total <= 0 and self._last_total > 0:
            total = self._last_total
        elif total > 0:
            self._last_total = total

        self._last_transferred = transferred
        self._last_name = name
        pct = _fmt_percent(transferred, total)
        self.bar.set_value(pct)
        self.lbl_pct.setText(_spaced_percent(pct))

        if total > 0:
            size_txt = f"{_fmt_bytes(transferred)} / {_fmt_bytes(total)}"
        else:
            size_txt = _fmt_bytes(transferred)
        elapsed = self._elapsed_text()
        self.lbl_detail.setText(f"{name}  ·  {size_txt}  ·  {elapsed}")

    def elapsed_text(self) -> str:
        return self._elapsed_text()

    def finish(self, message: str):
        self._tick.stop()
        self.bar.set_value(100)
        self.lbl_pct.setText("100%")
        self.lbl_detail.setText(message)
        QTimer.singleShot(1800, self.hide)

    def fail(self, message: str):
        self._tick.stop()
        self.lbl_detail.setText(message)
        QTimer.singleShot(2500, self.hide)

    def _elapsed_text(self) -> str:
        if self._started_at is None:
            return "00:00"
        secs = int(time.monotonic() - self._started_at)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _refresh_elapsed(self):
        if not self._last_name or self._started_at is None:
            return
        if self._last_total > 0:
            size_txt = f"{_fmt_bytes(self._last_transferred)} / {_fmt_bytes(self._last_total)}"
        else:
            size_txt = _fmt_bytes(self._last_transferred)
        self.lbl_detail.setText(
            f"{self._last_name}  ·  {size_txt}  ·  {self._elapsed_text()}"
        )


def _fmt_bytes(n: float) -> str:
    n = max(0.0, _normalize_bytes(n))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class ByteProgressTracker:
    """Theo dõi byte đã truyền — xử lý overflow 32-bit của Paramiko (>2GB, >4GB)."""

    def __init__(self, total_size: float, on_update):
        self.total = max(0.0, float(total_size))
        self.on_update = on_update
        self._prev = 0
        self._base = 0.0

    def __call__(self, raw_transferred, _raw_total):
        chunk = _normalize_bytes(raw_transferred)
        if chunk < self._prev:
            self._base += float(1 << 32)
        self._prev = chunk
        actual = self._base + chunk
        self.on_update(actual, self.total)


class StartupSplashScreen(QWidget):
    """Màn hình splash xanh lá — chạy đến 100% rồi vào app chính."""

    finished = Signal()

    def __init__(self, logo_path=None, parent=None):
        super().__init__(parent, Qt.WindowType.FramelessWindowHint | Qt.WindowType.SplashScreen)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(520, 280)
        self._progress = 0.0
        self._ready = False
        self._logo_path = logo_path

        self.setStyleSheet("background-color: #0a0a0c;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 36, 40, 32)
        layout.setSpacing(16)
        layout.addStretch()

        title = QLabel("Pettie SSH Client")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color: #fafafa; font-size: 22px; font-weight: 700; letter-spacing: 1px;"
        )
        layout.addWidget(title)

        if logo_path:
            from PySide6.QtGui import QPixmap
            from PySide6.QtWidgets import QLabel as _Lbl
            pix = QPixmap(logo_path)
            if not pix.isNull():
                logo = _Lbl()
                logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                logo.setPixmap(
                    pix.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
                layout.addWidget(logo)

        self._bar = GreenSplashProgressBar()
        layout.addWidget(self._bar)

        self.lbl_loading = QLabel("LOADING...")
        self.lbl_loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_loading.setStyleSheet(
            "color: #6ee7b7; font-size: 13px; font-weight: 600; letter-spacing: 4px;"
        )
        layout.addWidget(self.lbl_loading)
        layout.addStretch()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

    def start(self):
        self._progress = 0.0
        self._ready = False
        self._bar.set_value(0)
        self.center_on_screen()
        self.show()
        self._timer.start(18)

    def mark_ready(self):
        self._ready = True

    def center_on_screen(self):
        from PySide6.QtWidgets import QApplication as _QApp
        screen = self.screen() or _QApp.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.x() + (geo.width() - self.width()) // 2,
                geo.y() + (geo.height() - self.height()) // 2,
            )

    def _animate(self):
        if not self._ready:
            if self._progress < 88:
                self._progress = min(88.0, self._progress + 1.35)
        elif self._progress < 100:
            self._progress = min(100.0, self._progress + 3.5)
        else:
            self._timer.stop()
            self.lbl_loading.setText("READY")
            QTimer.singleShot(280, self.finished.emit)
            return

        self._bar.set_value(self._progress)
        self.lbl_loading.setText(f"LOADING... {int(self._progress)}%")
