"""Các cửa sổ tính năng: System Info, Port Forward."""

import threading

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QListWidget,
)
from PySide6.QtCore import Qt, Signal, QObject


DARK = """
    QWidget { background: #09090b; color: #fafafa; font-family: 'Segoe UI', sans-serif; }
    QTextEdit#term, QTextEdit#out {
        background: #0c0c0e; color: #4ade80; border: 1px solid #27272a;
        border-radius: 10px; font-family: Consolas, monospace; font-size: 12px;
    }
    QLineEdit, QComboBox, QSpinBox {
        background: #18181b; border: 1px solid #3f3f46; border-radius: 8px;
        padding: 8px; color: #fafafa;
    }
    QPushButton#go {
        background: #0d9488; color: white; border: none; border-radius: 8px;
        padding: 8px 16px; font-weight: 700;
    }
    QPushButton#go:hover { background: #14b8a6; }
    QLabel#title { font-size: 16px; font-weight: 700; color: #5eead4; }
    QTableWidget { background: #18181b; gridline-color: #27272a; border-radius: 10px; }
    QHeaderView::section { background: #27272a; color: #a1a1aa; border: none; padding: 8px; }
    QListWidget { background: #18181b; border: 1px solid #27272a; border-radius: 10px; }
"""


class _SystemInfoBridge(QObject):
    """Đưa kết quả SSH (thread nền) về UI thread."""
    loaded = Signal(dict)


class SystemInfoWindow(QMainWindow):
    """Dashboard thông tin máy chủ."""

    def __init__(self, ssh_manager, host, parent=None):
        super().__init__(parent)
        self.ssh = ssh_manager
        self._host = host
        self._fetching = False
        self._bridge = _SystemInfoBridge()
        self._bridge.loaded.connect(self._on_info_loaded)
        self.setWindowTitle(f"System Info — {host}")
        self.setMinimumSize(560, 420)
        self.setStyleSheet(DARK)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Remote System Information", objectName="title"))

        self.table = QTableWidget(6, 2)
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.btn_refresh = QPushButton("Làm mới")
        self.btn_refresh.setObjectName("go")
        self.btn_refresh.clicked.connect(lambda: self.refresh(force=True))
        layout.addWidget(self.btn_refresh)
        self.setCentralWidget(w)

        cached = self.ssh.peek_system_info()
        if cached and cached.get("items"):
            self._on_info_loaded(cached)
        else:
            self._show_loading()
            self.refresh(force=True)

    def _show_loading(self):
        labels = ("Hostname", "OS", "CPU", "RAM", "Disk", "Uptime")
        for i, label in enumerate(labels):
            self.table.setItem(i, 0, QTableWidgetItem(label))
            self.table.setItem(i, 1, QTableWidgetItem("Đang tải..."))

    def refresh(self, force=False):
        if self._fetching:
            return
        if force:
            self._show_loading()
        self._fetching = True
        self.btn_refresh.setEnabled(False)

        def work():
            try:
                info = self.ssh.get_system_info(
                    use_cache=not force,
                    force_refresh=force,
                )
            except Exception:
                info = {"hostname": "", "items": []}
            self._bridge.loaded.emit(info)

        threading.Thread(target=work, daemon=True).start()

    def _on_info_loaded(self, info):
        self._fetching = False
        self.setWindowTitle(f"System Info — {info.get('hostname') or self._host}")
        items = info.get("items", [])
        if not items:
            self._show_loading()
            self.table.setItem(0, 1, QTableWidgetItem("Không lấy được dữ liệu"))
        else:
            self.table.setRowCount(len(items))
            for i, row in enumerate(items):
                self.table.setItem(i, 0, QTableWidgetItem(row["label"]))
                self.table.setItem(i, 1, QTableWidgetItem(row["value"]))
        self.btn_refresh.setEnabled(True)


class PortForwardWindow(QMainWindow):
    """Quản lý port forwarding."""

    def __init__(self, ssh_manager, parent=None):
        super().__init__(parent)
        self.ssh = ssh_manager
        self.setWindowTitle("Port Forwarding")
        self.setMinimumSize(500, 380)
        self.setStyleSheet(DARK)

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("SSH Port Forwarding", objectName="title"))

        form = QHBoxLayout()
        form.addWidget(QLabel("Local:"))
        self.spin_local = QSpinBox()
        self.spin_local.setRange(1024, 65535)
        self.spin_local.setValue(8080)
        form.addWidget(self.spin_local)
        form.addWidget(QLabel("→ Remote host:"))
        self.txt_remote_host = QLineEdit("127.0.0.1")
        form.addWidget(self.txt_remote_host)
        form.addWidget(QLabel("Port:"))
        self.spin_remote = QSpinBox()
        self.spin_remote.setRange(1, 65535)
        self.spin_remote.setValue(80)
        form.addWidget(self.spin_remote)
        layout.addLayout(form)

        btn_add = QPushButton("+ Thêm tunnel")
        btn_add.setObjectName("go")
        btn_add.clicked.connect(self.add_tunnel)
        layout.addWidget(btn_add)

        self.list = QListWidget()
        layout.addWidget(self.list)
        self.refresh_list()
        self.setCentralWidget(w)

    def add_tunnel(self):
        h, err = self.ssh.start_local_forward(
            self.spin_local.value(),
            self.txt_remote_host.text().strip(),
            self.spin_remote.value(),
        )
        if err:
            QMessageBox.warning(self, "Lỗi", err)
        else:
            self.refresh_list()

    def refresh_list(self):
        self.list.clear()
        for f in self.ssh.list_forwards():
            self.list.addItem(f"127.0.0.1:{f['port']}  —  {f['label']}")
