"""Dual-pane SFTP file manager — modern layout, distinct from Bitvise."""

import os
import sys
import subprocess
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QMessageBox,
    QHeaderView, QFrame, QSplitter, QToolButton, QStyle, QInputDialog,
    QApplication,
)
from PySide6.QtCore import Qt, QSize, QObject, QThread, Signal
from PySide6.QtGui import QFont, QColor

from sftp_paths import (
    is_windows_sftp_path,
    join_windows_sftp,
    normalize_windows_sftp,
    parent_windows_sftp,
)
from platform_utils import detect_local_os, format_os_display
from security_utils import validate_remote_entry_name, validate_search_pattern
from progress_bars import TransferProgressPanel, _normalize_bytes, _fmt_bytes, ByteProgressTracker


class _RemoteDirWorker(QObject):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, ssh, path):
        super().__init__()
        self.ssh = ssh
        self.path = path

    def run(self):
        entries = self.ssh.list_remote_dir(self.path) if self.ssh else None
        if entries is None:
            self.failed.emit("Lỗi đọc thư mục")
        else:
            self.loaded.emit(entries)


class _FileTransferWorker(QObject):
    """Truyền file SFTP trên thread nền — không chặn UI."""

    progress = Signal(float, float, str)
    finished = Signal(int, int, str)
    failed = Signal(str)

    def __init__(self, ssh, tasks, direction):
        super().__init__()
        self.ssh = ssh
        self.tasks = tasks
        self.direction = direction

    def run(self):
        ok_count = 0
        label = "gửi" if self.direction == "upload" else "nhận"
        try:
            for local_path, remote_path, name, known_size in self.tasks:
                total = self._resolve_total(local_path, remote_path, known_size)

                def _emit(actual, tot, _name=name):
                    self.progress.emit(float(actual), float(tot), _name)

                tracker = ByteProgressTracker(total, _emit)

                if self.direction == "upload":
                    success = self.ssh.upload_file(local_path, remote_path, tracker)
                else:
                    success = self.ssh.download_file(remote_path, local_path, tracker)
                if success:
                    ok_count += 1
            self.finished.emit(ok_count, len(self.tasks), label)
        except Exception as e:
            self.failed.emit(str(e))

    def _resolve_total(self, local_path, remote_path, known_size):
        size = _normalize_bytes(known_size)
        if size > 0:
            return size
        if self.direction == "upload":
            try:
                return float(os.path.getsize(local_path))
            except OSError:
                return 0.0
        return float(self.ssh.get_remote_file_size(remote_path))


def _fmt_size(n):
    return _fmt_bytes(n)


def _list_local_dir(path):
    entries = []
    try:
        for name in os.listdir(path):
            if name.startswith(".") and name not in (".", ".."):
                continue
            full = os.path.join(path, name)
            try:
                st = os.stat(full)
                entries.append({
                    "name": name,
                    "size": st.st_size,
                    "is_dir": os.path.isdir(full),
                    "mtime": st.st_mtime,
                })
            except OSError:
                continue
    except OSError:
        return None
    return entries


class FilePane(QFrame):
    """Một cột file browser (local hoặc remote)."""

    def __init__(self, title, accent, pane_id, pane_os="linux", ssh=None, parent=None):
        super().__init__(parent)
        self.pane_id = pane_id  # "local" | "remote"
        self.accent = accent
        self.pane_os = pane_os
        self.remote_os = pane_os
        self.ssh = ssh
        self._history = []
        self.setObjectName("filePane")

        if pane_id == "local":
            self.current_path = os.path.expanduser("~")
            if sys.platform.startswith("win"):
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                if os.path.isdir(desktop):
                    self.current_path = desktop
        else:
            self.current_path = self._initial_remote_path(ssh, pane_os)

        self._load_thread = None
        self._load_worker = None

        self.setStyleSheet(f"""
            QFrame#filePane {{
                background-color: #18181b;
                border: 1px solid #27272a;
                border-radius: 16px;
            }}
            QLabel#paneTitle {{
                color: {accent};
                font-size: 13px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            QLabel#panePath {{
                color: #71717a;
                font-size: 11px;
            }}
            QLineEdit#pathInput {{
                background-color: #09090b;
                color: #fafafa;
                border: 1px solid #3f3f46;
                border-radius: 10px;
                padding: 8px 12px;
                font-family: 'Cascadia Code', Consolas, monospace;
                font-size: 12px;
            }}
            QLineEdit#pathInput:focus {{ border-color: {accent}; }}
            QLineEdit#filterInput {{
                background-color: #27272a;
                color: #a1a1aa;
                border: none;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QToolButton#navBtn {{
                background-color: #27272a;
                color: #e4e4e7;
                border: none;
                border-radius: 8px;
                padding: 6px;
            }}
            QToolButton#navBtn:hover {{
                background-color: {accent};
                color: #09090b;
            }}
            QTreeWidget {{
                background-color: #09090b;
                alternate-background-color: #18181b;
                color: #fafafa;
                border: none;
                border-radius: 12px;
                outline: none;
                font-size: 12px;
            }}
            QTreeWidget::item {{ padding: 5px 2px; border-radius: 4px; }}
            QTreeWidget::item:selected {{
                background-color: {accent};
                color: #09090b;
            }}
            QTreeWidget::item:hover:!selected {{ background-color: #27272a; }}
            QHeaderView::section {{
                background-color: #18181b;
                color: #71717a;
                border: none;
                border-bottom: 1px solid #3f3f46;
                padding: 8px 6px;
                font-weight: 600;
                font-size: 11px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        self.lbl_title = QLabel(title.upper())
        self.lbl_title.setObjectName("paneTitle")
        hdr.addWidget(self.lbl_title)
        hdr.addStretch()
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("panePath")
        hdr.addWidget(self.lbl_count)
        layout.addLayout(hdr)

        nav = QHBoxLayout()
        nav.setSpacing(6)
        style = self.style()
        nav_items = [
            ("Lên", self.go_up, QStyle.StandardPixmap.SP_ArrowUp),
            ("Lùi", self.go_back, QStyle.StandardPixmap.SP_ArrowBack),
            ("Home", self.go_home, QStyle.StandardPixmap.SP_DirHomeIcon),
            ("Làm mới", self.refresh, QStyle.StandardPixmap.SP_BrowserReload),
        ]
        if pane_id == "remote":
            nav_items.insert(
                3,
                ("Ổ đĩa", self.go_drives, QStyle.StandardPixmap.SP_DriveHDIcon),
            )
        for tip, slot, icon in nav_items:
            btn = QToolButton()
            btn.setObjectName("navBtn")
            btn.setIcon(style.standardIcon(icon))
            btn.setToolTip(tip)
            btn.setFixedSize(32, 32)
            btn.clicked.connect(slot)
            nav.addWidget(btn)

        if pane_id == "local":
            btn_explorer = QToolButton()
            btn_explorer.setObjectName("navBtn")
            btn_explorer.setText("📂")
            btn_explorer.setToolTip("Mở Explorer / File manager hệ thống")
            btn_explorer.setFixedSize(32, 32)
            btn_explorer.clicked.connect(self.open_native_explorer)
            nav.addWidget(btn_explorer)

        nav.addStretch()
        self.filter_box = QLineEdit()
        self.filter_box.setObjectName("filterInput")
        self.filter_box.setPlaceholderText("Lọc tên file...")
        self.filter_box.setFixedWidth(140)
        self.filter_box.textChanged.connect(self._apply_filter)
        nav.addWidget(self.filter_box)
        layout.addLayout(nav)

        self.path_input = QLineEdit()
        self.path_input.setObjectName("pathInput")
        self.path_input.returnPressed.connect(self._navigate_from_bar)
        layout.addWidget(self.path_input)

        self.tree = QTreeWidget()
        self.tree.setAlternatingRowColors(True)
        self.tree.setHeaderLabels(["Tên", "Kích thước", "Sửa đổi"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.tree)

    @staticmethod
    def _initial_remote_path(ssh, remote_os):
        if not ssh:
            return "/"
        cached = getattr(ssh, "_remote_home_cache", None)
        if cached:
            return cached
        try:
            if ssh.sftp_client:
                path = ssh.sftp_client.normalize(".")
                if path:
                    if remote_os == "windows" or is_windows_sftp_path(path):
                        path = normalize_windows_sftp(path)
                    ssh._remote_home_cache = path
                    return path
        except Exception:
            pass
        return "/C:/" if remote_os == "windows" else "/"

    def _is_win_remote(self):
        if self.pane_id != "remote":
            return False
        if self.pane_os == "windows":
            return True
        return is_windows_sftp_path(self.current_path)

    def _normalize_path(self, path):
        if self.pane_id == "local":
            return os.path.normpath(path) if path else os.path.expanduser("~")
        if self._is_win_remote() or is_windows_sftp_path(path):
            return normalize_windows_sftp(path)
        p = (path or "/").replace("\\", "/")
        return p if p.startswith("/") else f"/{p}"

    def _join(self, base, name):
        if self._is_win_remote() or is_windows_sftp_path(base):
            return join_windows_sftp(base, name)
        if self.pane_id == "local":
            return os.path.join(base, name)
        base = base.rstrip("/")
        return f"{base}/{name}" if base and base != "/" else f"/{name}"

    def _parent_path(self, path):
        if self.pane_id == "local":
            parent = os.path.dirname(path)
            return parent if parent else path
        if self._is_win_remote() or is_windows_sftp_path(path):
            return parent_windows_sftp(path)
        if path in ("/", ""):
            return "/"
        parent = os.path.dirname(path.rstrip("/"))
        return parent if parent else "/"

    def go_home(self):
        if self.pane_id == "local":
            self._go_to(os.path.expanduser("~"))
        elif self.ssh:
            self._go_to(self._normalize_path(self.ssh.get_remote_home(fast_only=True)))

    def go_drives(self):
        """Windows SFTP: về / để xem C:, D:, ..."""
        if self.pane_id == "remote" and self._is_win_remote():
            self._go_to("/")

    def go_back(self):
        if self._history:
            self._go_to(self._history.pop(), push_history=False)

    def go_up(self):
        parent = self._parent_path(self.current_path)
        if parent != self.current_path:
            self._go_to(parent)

    def _go_to(self, path, push_history=True):
        path = self._normalize_path(path)
        if push_history and self.current_path != path:
            self._history.append(self.current_path)
        self.current_path = path
        self.path_input.setText(path)
        self.refresh()

    def _navigate_from_bar(self):
        path = self.path_input.text().strip()
        if path:
            self._go_to(path)

    def _apply_filter(self, text):
        text = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.data(0, Qt.ItemDataRole.UserRole)
            if name and name.get("is_parent"):
                item.setHidden(False)
                continue
            item.setHidden(bool(text) and text not in item.text(0).lower())

    def refresh(self):
        if self.pane_id == "remote":
            self._refresh_remote_async()
            return
        self._render_entries(_list_local_dir(self.current_path))

    def _refresh_remote_async(self):
        self._stop_load_thread()
        self.path_input.setText(self.current_path)
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        self.lbl_count.setText("Đang tải...")
        self.tree.setUpdatesEnabled(True)

        self._load_thread = QThread()
        self._load_worker = _RemoteDirWorker(self.ssh, self.current_path)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.loaded.connect(self._on_remote_loaded)
        self._load_worker.failed.connect(self._on_remote_failed)
        self._load_worker.loaded.connect(self._load_thread.quit)
        self._load_worker.failed.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._clear_load_thread)
        self._load_thread.start()

    def _stop_load_thread(self):
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(200)

    def _clear_load_thread(self):
        self._load_thread = None
        self._load_worker = None

    def _on_remote_loaded(self, entries):
        self._render_entries(entries)

    def _on_remote_failed(self, _msg):
        self.lbl_count.setText("Lỗi đọc thư mục")
        self.tree.setUpdatesEnabled(True)

    def _render_entries(self, entries):
        self.path_input.setText(self.current_path)
        self.tree.setUpdatesEnabled(False)
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        self._all_entries = []

        if entries is None:
            self.lbl_count.setText("Lỗi đọc thư mục")
            self.tree.setUpdatesEnabled(True)
            return

        parent = self._parent_path(self.current_path)
        if parent != self.current_path:
            up = QTreeWidgetItem(["  ⬆  ..", "", ""])
            up.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": True, "name": "..", "is_parent": True})
            up.setForeground(0, QColor("#71717a"))
            self.tree.addTopLevelItem(up)

        dirs = sorted([e for e in entries if e["is_dir"]], key=lambda x: x["name"].lower())
        files = sorted([e for e in entries if not e["is_dir"]], key=lambda x: x["name"].lower())

        for entry in dirs + files:
            mtime = ""
            if entry.get("mtime"):
                mtime = datetime.fromtimestamp(entry["mtime"]).strftime("%d/%m/%Y %H:%M")
            size = "" if entry["is_dir"] else _fmt_size(entry["size"])
            prefix = "📁 " if entry["is_dir"] else "📄 "
            item = QTreeWidgetItem([prefix + entry["name"], size, mtime])
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            if entry["is_dir"]:
                item.setForeground(0, QColor(self.accent))
            self.tree.addTopLevelItem(item)
            self._all_entries.append(entry)

        self.lbl_count.setText(f"{len(entries)} mục")
        self.tree.setUpdatesEnabled(True)
        self.tree.setSortingEnabled(True)
        self._apply_filter(self.filter_box.text())

    def _on_double_click(self, item, _col):
        entry = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry:
            return
        if entry.get("is_parent"):
            self.go_up()
            return
        if entry["is_dir"]:
            self._go_to(self._join(self.current_path, entry["name"]))

    def selected_entries(self):
        result = []
        for item in self.tree.selectedItems():
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            if entry and not entry.get("is_parent"):
                result.append(entry)
        return result

    def open_native_explorer(self):
        path = self.current_path
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không mở được file manager: {e}")


class SftpFileManagerWindow(QMainWindow):
    """Cửa sổ dual-pane: Local | Transfer | Remote."""

    STYLESHEET = """
        QMainWindow { background-color: #09090b; }
        QFrame#topBar {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #0c4a6e, stop:0.5 #4c1d95, stop:1 #831843);
            border-radius: 0;
        }
        QLabel#winTitle { color: white; font-size: 18px; font-weight: 700; }
        QLabel#winSub { color: rgba(255,255,255,0.65); font-size: 12px; }
        QFrame#transferCol {
            background-color: #18181b;
            border: 1px solid #27272a;
            border-radius: 16px;
        }
        QPushButton#xferBtn {
            background-color: #27272a;
            color: #fafafa;
            border: none;
            border-radius: 12px;
            padding: 14px 8px;
            font-weight: 700;
            font-size: 11px;
            min-width: 72px;
        }
        QPushButton#xferBtn:hover { background-color: #14b8a6; color: #042f2e; }
        QPushButton#xferBtnDl:hover { background-color: #a78bfa; color: #2e1065; }
        QStatusBar {
            background-color: #18181b;
            color: #71717a;
            border-top: 1px solid #27272a;
            font-size: 12px;
        }
    """

    def __init__(self, ssh_manager, host, user, remote_os="unknown", parent=None):
        super().__init__(parent)
        self.ssh = ssh_manager
        self.host = host
        self.user = user
        self.remote_os = remote_os
        self.local_os = detect_local_os()

        self.setWindowTitle(f"Pettie Transfer — {user}@{host}")
        self.setMinimumSize(1100, 620)
        self.resize(1280, 700)
        self.setStyleSheet(self.STYLESHEET)
        self._transfer_thread = None
        self._transfer_worker = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QFrame()
        top.setObjectName("topBar")
        top.setFixedHeight(64)
        th = QHBoxLayout(top)
        th.setContentsMargins(24, 0, 24, 0)
        col = QVBoxLayout()
        t = QLabel("Pettie Transfer")
        t.setObjectName("winTitle")
        sub = QLabel(
            f"{self.user}@{self.host}  ·  "
            f"Máy bạn: {format_os_display(self.local_os, role='local')}  ·  "
            f"Máy chủ: {format_os_display(self.remote_os)}"
        )
        sub.setObjectName("winSub")
        col.addWidget(t)
        col.addWidget(sub)
        th.addLayout(col)
        th.addStretch()

        btn_search = QPushButton("🔍 Tìm file")
        btn_search.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.15); color: white;"
            "border: none; border-radius: 8px; padding: 8px 14px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(255,255,255,0.3); }"
        )
        btn_search.clicked.connect(self.search_remote)
        btn_rename = QPushButton("✏ Đổi tên")
        btn_rename.setStyleSheet(btn_search.styleSheet())
        btn_rename.clicked.connect(self.rename_remote)
        th.addWidget(btn_search)
        th.addWidget(btn_rename)
        layout.addWidget(top)

        body = QWidget()
        body.setStyleSheet("background-color: #09090b;")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(16, 16, 16, 16)
        bl.setSpacing(12)

        self.local_pane = FilePane(
            "Máy của bạn", "#2dd4bf", "local", self.local_os, parent=self
        )
        self.remote_pane = FilePane(
            "Máy chủ", "#c084fc", "remote", self.remote_os, self.ssh, parent=self
        )

        transfer = QFrame()
        transfer.setObjectName("transferCol")
        transfer.setFixedWidth(96)
        tv = QVBoxLayout(transfer)
        tv.setContentsMargins(10, 20, 10, 20)
        tv.setSpacing(12)
        tv.addStretch()

        self.btn_upload = QPushButton("▶\nGửi")
        self.btn_upload.setObjectName("xferBtn")
        self.btn_upload.setToolTip("Upload file đã chọn — Local → Remote")
        self.btn_upload.clicked.connect(self.transfer_upload)

        self.btn_download = QPushButton("◀\nNhận")
        self.btn_download.setObjectName("xferBtn")
        self.btn_download.setProperty("class", "xferBtnDl")
        self.btn_download.setStyleSheet(
            "QPushButton:hover { background-color: #a78bfa; color: #2e1065; }"
        )
        self.btn_download.setToolTip("Download file đã chọn — Remote → Local")
        self.btn_download.clicked.connect(self.transfer_download)

        btn_mkdir_r = QPushButton("+\nRemote")
        btn_mkdir_r.setObjectName("xferBtn")
        btn_mkdir_r.setToolTip("Tạo thư mục trên máy chủ")
        btn_mkdir_r.clicked.connect(self.create_remote_folder)

        btn_del_r = QPushButton("✕\nXóa")
        btn_del_r.setObjectName("xferBtn")
        btn_del_r.setToolTip("Xóa trên máy chủ")
        btn_del_r.clicked.connect(self.delete_remote)

        for b in (self.btn_upload, self.btn_download, btn_mkdir_r, btn_del_r):
            tv.addWidget(b)
        tv.addStretch()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.local_pane)
        splitter.addWidget(transfer)
        splitter.addWidget(self.remote_pane)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([500, 96, 500])
        splitter.setStyleSheet("""
            QSplitter::handle { background-color: #27272a; width: 4px; border-radius: 2px; }
            QSplitter::handle:hover { background-color: #14b8a6; }
        """)

        bl.addWidget(splitter)
        layout.addWidget(body, stretch=1)

        self.transfer_panel = TransferProgressPanel()
        layout.addWidget(self.transfer_panel)

        self.setCentralWidget(central)
        self.status = self.statusBar()
        self.status.showMessage("Sẵn sàng · Chọn file và dùng nút Gửi / Nhận")

        self.show()
        QApplication.processEvents()
        self.local_pane.refresh()
        self.remote_pane.refresh()

    def _set_transfer_busy(self, busy):
        for btn in (self.btn_upload, self.btn_download):
            btn.setEnabled(not busy)

    def _start_transfer(self, tasks, direction):
        if self._transfer_thread and self._transfer_thread.isRunning():
            QMessageBox.information(
                self, "Truyền file",
                "Đang truyền file khác — vui lòng đợi hoàn tất.",
            )
            return
        if not tasks:
            return

        self._set_transfer_busy(True)
        first_name = tasks[0][2]
        first_size = tasks[0][3] if len(tasks[0]) > 3 else 0
        action = "Gửi" if direction == "upload" else "Nhận"
        self.transfer_panel.start(first_name, action=action, total_bytes=first_size)

        self._transfer_thread = QThread()
        self._transfer_worker = _FileTransferWorker(self.ssh, tasks, direction)
        self._transfer_worker.moveToThread(self._transfer_thread)
        self._transfer_thread.started.connect(self._transfer_worker.run)
        self._transfer_worker.progress.connect(self._on_transfer_progress)
        self._transfer_worker.finished.connect(self._on_transfer_finished)
        self._transfer_worker.failed.connect(self._on_transfer_failed)
        self._transfer_worker.finished.connect(self._transfer_thread.quit)
        self._transfer_worker.failed.connect(self._transfer_thread.quit)
        self._transfer_thread.finished.connect(self._clear_transfer_thread)
        self._transfer_thread.start()

    def _on_transfer_progress(self, transferred, total, name):
        self.transfer_panel.update_progress(transferred, total, name)
        t = _normalize_bytes(transferred)
        tot = _normalize_bytes(total)
        self.status.showMessage(
            f"{name}: {_fmt_size(t)}"
            + (f" / {_fmt_size(tot)}" if tot > 0 else ""),
        )

    def _on_transfer_finished(self, ok_count, total, label):
        self._set_transfer_busy(False)
        if label == "gửi":
            self.remote_pane.refresh()
        else:
            self.local_pane.refresh()
        msg = f"Đã {label} {ok_count}/{total} file · {self.transfer_panel.elapsed_text()}"
        self.transfer_panel.finish(msg)
        self.status.showMessage(f"Đã {label} {ok_count}/{total} file.")

    def _on_transfer_failed(self, message):
        self._set_transfer_busy(False)
        self.transfer_panel.fail(f"Truyền file thất bại: {message}")
        self.status.showMessage("Truyền file thất bại.")
        QMessageBox.warning(self, "Lỗi truyền file", message)

    def _clear_transfer_thread(self):
        self._transfer_thread = None
        self._transfer_worker = None

    def transfer_upload(self):
        entries = self.local_pane.selected_entries()
        files = [e for e in entries if not e["is_dir"]]
        if not files:
            QMessageBox.information(self, "Upload", "Chọn file ở cột trái — Máy của bạn.")
            return
        dest = self.remote_pane.current_path
        tasks = []
        for entry in files:
            local = self.local_pane._join(self.local_pane.current_path, entry["name"])
            remote = self.remote_pane._join(dest, entry["name"])
            tasks.append((local, remote, entry["name"], entry.get("size", 0)))
        self._start_transfer(tasks, "upload")

    def transfer_download(self):
        entries = self.remote_pane.selected_entries()
        files = [e for e in entries if not e["is_dir"]]
        if not files:
            QMessageBox.information(self, "Download", "Chọn file ở cột phải — Máy chủ.")
            return
        dest = self.local_pane.current_path
        tasks = []
        for entry in files:
            remote = self.remote_pane._join(self.remote_pane.current_path, entry["name"])
            local = self.local_pane._join(dest, entry["name"])
            tasks.append((local, remote, entry["name"], entry.get("size", 0)))
        self._start_transfer(tasks, "download")

    def create_remote_folder(self):
        name, ok = QInputDialog.getText(self, "Thư mục mới", "Tên thư mục trên máy chủ:")
        if not ok or not name.strip():
            return
        remote = self.remote_pane._join(self.remote_pane.current_path, name.strip())
        if self.ssh.mkdir(remote):
            self.remote_pane.refresh()
        else:
            QMessageBox.warning(self, "Lỗi", "Không tạo được thư mục.")

    def delete_remote(self):
        entries = self.remote_pane.selected_entries()
        if not entries:
            QMessageBox.information(self, "Xóa", "Chọn mục trên máy chủ để xóa.")
            return
        reply = QMessageBox.question(
            self, "Xác nhận", f"Xóa {len(entries)} mục trên máy chủ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for entry in entries:
            remote = self.remote_pane._join(self.remote_pane.current_path, entry["name"])
            if entry["is_dir"]:
                self.ssh.remove_dir(remote)
            else:
                self.ssh.remove_file(remote)
        self.remote_pane.refresh()

    def search_remote(self):
        pattern, ok = QInputDialog.getText(
            self, "Tìm file", "Tên file/thư mục chứa chuỗi:",
        )
        if not ok or not pattern.strip():
            return
        try:
            pattern = validate_search_pattern(pattern)
        except ValueError as e:
            QMessageBox.warning(self, "Tìm file", str(e))
            return
        self.status.showMessage(f"Đang tìm '{pattern}'...")
        QApplication.processEvents()
        results = self.ssh.search_remote_files(
            self.remote_pane.current_path, pattern, max_results=100
        )
        if not results:
            QMessageBox.information(self, "Tìm kiếm", "Không thấy kết quả.")
            return
        lines = "\n".join(
            f"{'📁' if r['is_dir'] else '📄'} {r['path']}" for r in results[:30]
        )
        if len(results) > 30:
            lines += f"\n... và {len(results) - 30} kết quả nữa"
        QMessageBox.information(self, "Tìm thấy", f"{len(results)} mục:\n\n{lines}")

    def rename_remote(self):
        entries = self.remote_pane.selected_entries()
        if len(entries) != 1:
            QMessageBox.information(self, "Đổi tên", "Chọn đúng một mục trên máy chủ.")
            return
        entry = entries[0]
        new_name, ok = QInputDialog.getText(
            self, "Đổi tên", "Tên mới:", text=entry["name"],
        )
        if not ok or not new_name.strip() or new_name == entry["name"]:
            return
        try:
            new_name = validate_remote_entry_name(new_name)
        except ValueError as e:
            QMessageBox.warning(self, "Đổi tên", str(e))
            return
        old = self.remote_pane._join(self.remote_pane.current_path, entry["name"])
        new = self.remote_pane._join(self.remote_pane.current_path, new_name)
        if self.ssh.rename_remote(old, new):
            self.remote_pane.refresh()
            self.status.showMessage(f"Đã đổi tên → {new_name}")
        else:
            QMessageBox.warning(self, "Lỗi", "Không đổi tên được.")
