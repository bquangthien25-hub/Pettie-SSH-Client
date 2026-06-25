import sys
import os
import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QHBoxLayout, QMessageBox, QTextEdit, QComboBox, QCheckBox, QGridLayout,
    QFrame, QStackedWidget, QScrollArea, QListWidget, QFileDialog,
    QInputDialog, QSizePolicy, QGroupBox, QDialog, QProgressDialog, QToolButton,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, Slot, QMetaObject, Q_ARG, Q_RETURN_ARG, QTimer, QSize, QEvent
from PySide6.QtGui import QGuiApplication, QPixmap, QIcon

from background_widget import BackgroundWidget
from music_bars_widget import MusicBarsWidget
from windows_startup import is_startup_enabled, set_startup_enabled
from ui_theme import APP_LOGO, OASIS_LOGO, resolve_background, list_available_backgrounds
from progress_bars import StartupSplashScreen
from themes import (
    THEME_IDS, PALETTES, build_stylesheet, login_button_style, combo_popup_stylesheet,
)
from visual_styles import VISUAL_STYLE_IDS
from ui_icons import themed_icon, NAV_ICON_IDS

from ssh_backend import SSHManager
from file_manager_window import SftpFileManagerWindow
from remote_desktop import (
    RemoteDesktopDialog, connect_direct_rdp, RDP_PORT,
    linux_rdp_client_available, linux_rdp_status_message,
    ensure_linux_freerdp_installed,
)
from feature_windows import (
    SystemInfoWindow, PortForwardWindow,
)
from profile_store import (
    list_profiles, save_profile, delete_profile,
    get_settings, save_settings, clear_connection_history,
    get_config, save_config, update_profile_fields, refresh_all_profile_dns,
    get_default_dns_host,
)
from dns_utils import prepare_connect_host, refresh_profile_entry, is_hostname
from security_utils import (
    ssh_argv,
    validate_ssh_host,
    validate_ssh_user,
    validate_ssh_port,
    validate_ssh_key_path,
    validate_windows_logon,
)
from host_key_store import (
    peek_host_key_status,
    verify_host_key_live,
    trust_host_key,
)
from platform_utils import detect_local_os, format_os_display, local_os_display_name, launch_system_terminal
from ngonngu import init_language, set_language, get_language, tr, LANG_VI, LANG_EN


class _ConnectUiBridge(QObject):
    """Hộp thoại host key trên UI thread (gọi từ worker)."""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self._parent_window = parent_window

    @Slot(str, int, str, result=bool)
    def ask_trust_host_key(self, host, port, fingerprint):
        reply = QMessageBox.question(
            self._parent_window,
            tr("dlg_trust_host_title"),
            tr("dlg_trust_host_body", host=host, port=port, fingerprint=fingerprint),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes


class _SSHConnectWorker(QThread):
    """Kết nối SSH nền — tránh đơ giao diện khi IP sai hoặc timeout."""

    connect_result = Signal(bool, str)

    def __init__(self, manager, host, port, user, password, key_path, ui_bridge):
        super().__init__()
        self._manager = manager
        self._host = host
        self._port = int(port)
        self._user = user
        self._password = password
        self._key_path = key_path
        self._ui_bridge = ui_bridge

    def _ensure_host_key_trusted(self):
        disk_status, _, _, _ = peek_host_key_status(self._host, self._port)
        if disk_status == "trusted":
            return True, ""
        try:
            status, fp, old_fp, key = verify_host_key_live(
                self._host, self._port, timeout=4,
            )
        except OSError as e:
            return False, f"Không kết nối được tới {self._host}:{self._port} ({e})"
        except Exception as e:
            return False, f"Không đọc được host key SSH: {e}"

        if status == "changed":
            return False, (
                f"Host key của {self._host}:{self._port} đã thay đổi — có thể bị MITM.\n\n"
                f"Cũ: SHA256:{old_fp}\nMới: SHA256:{fp}\n\n"
                "Xóa mục tương ứng trong ~/.pettie-ssh/known_hosts nếu máy chủ vừa cài lại."
            )
        if status == "trusted":
            return True, ""

        approved = QMetaObject.invokeMethod(
            self._ui_bridge,
            "ask_trust_host_key",
            Qt.ConnectionType.BlockingQueuedConnection,
            Q_RETURN_ARG(bool),
            Q_ARG(str, self._host),
            Q_ARG(int, self._port),
            Q_ARG(str, fp),
        )
        if approved is None:
            return False, "Không hiển thị được hộp thoại host key."
        if not approved:
            return False, "Đã hủy — chưa tin cậy host key."
        trust_host_key(self._host, self._port, key)
        return True, ""

    def run(self):
        try:
            ok_hk, hk_err = self._ensure_host_key_trusted()
            if not ok_hk:
                self.connect_result.emit(False, hk_err)
                return

            success, err = self._manager.connect(
                self._host,
                self._user,
                self._password,
                port=self._port,
                key_path=self._key_path,
                timeout=8,
            )
            if success:
                self.connect_result.emit(True, "")
            else:
                self.connect_result.emit(
                    False, err or f"Không kết nối được tới {self._host}.",
                )
        except Exception as e:
            self.connect_result.emit(
                False, f"Không kết nối được tới {self._host}: {e}",
            )
        finally:
            self._password = None


class _FreerdpInstallWorker(QThread):
    """Cài xfreerdp trên Linux (apt/dnf/pacman) — chạy nền."""

    install_result = Signal(bool, str)

    def run(self):
        ok, msg = ensure_linux_freerdp_installed()
        self.install_result.emit(ok, msg)


class PettieSSHClient(QWidget):
    def __init__(self):
        super().__init__()
        self.ssh_manager = SSHManager()
        self.ssh_manager.set_os_ready_callback(self._on_remote_os_ready)
        self._local_os = detect_local_os()
        self.is_logged_in = False
        self._fm_window = None
        self._child_windows = []
        self._session_history = []
        self._connect_worker = None
        self._freerdp_install_worker = None
        self._connect_progress = None
        self._pending_connect = None
        self._connect_ui_bridge = _ConnectUiBridge(self)
        self._settings = get_settings()
        init_language(self._settings.get("language", LANG_VI))
        self._field_label_keys = []
        self._tool_defs_keys = []
        self._bg_thumb_buttons = {}
        self._custom_bg_path = None
        self._selected_bg_id = "sakura_sky"
        self._connect_form = {
            "host": "", "dns": "", "port": "", "user": "", "pass": "", "key": "",
        }
        self._form_syncing = False
        self.init_ui()
        self._load_settings_to_ui()
        self._sync_startup_with_settings()
        self.apply_appearance()
        self._init_connect_form_empty()
        self._refresh_profiles()
        self._refresh_dns_profiles(silent=True)
        self._dns_refresh_timer = QTimer(self)
        self._dns_refresh_timer.timeout.connect(self._on_dns_refresh_tick)
        self._dns_refresh_timer.start(120_000)

    def _enter_workspace_after_connect(self):
        self.btn_action.setText(tr("btn_disconnect"))
        self.btn_action.setStyleSheet(self._btn_logout_style)
        self._set_connected_ui(True)
        self._switch_page(1)

    def _disconnect_session(self):
        self.ssh_manager.disconnect()
        self.is_logged_in = False
        self._set_connected_ui(False)
        if self._fm_window:
            self._fm_window.close()
            self._fm_window = None
        for w in self._child_windows:
            try:
                w.close()
            except Exception:
                pass
        self._child_windows.clear()
        self.log_info("Session closed by user request.")
        self._update_connect_button_label()
        self.btn_action.setStyleSheet(self._btn_login_style)
        self._switch_page(0)

    def init_ui(self):
        self.setWindowTitle("Pettie SSH Client 2.5")
        self.setMinimumSize(1080, 740)

        self._bg = BackgroundWidget(None, overlay_alpha=0.45)
        root = self._bg.content_widget()
        root.setObjectName("mainRoot")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Navigation rail ---
        nav = QFrame()
        nav.setObjectName("navRail")
        nav.setFixedWidth(88)
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(8, 20, 8, 20)
        nv.setSpacing(6)

        logo = QLabel()
        logo.setObjectName("brandLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.isfile(APP_LOGO):
            px = QPixmap(APP_LOGO).scaled(
                56, 56,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(px)
        else:
            logo.setText("⚡")
            logo.setStyleSheet("font-size: 28px;")
        nv.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
        nm = QLabel("Pettie")
        nm.setObjectName("brandName")
        nm.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nv.addWidget(nm)
        ver = QLabel("v2.5")
        ver.setObjectName("brandVer")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nv.addWidget(ver)
        nv.addSpacing(20)

        self._nav_btns = []
        self._nav_icon_ids = list(NAV_ICON_IDS)
        self.stack = QStackedWidget()
        self._nav_label_keys = ["nav_connect", "nav_tools", "nav_settings", "nav_about"]
        for i, _key in enumerate(self._nav_label_keys):
            b = QToolButton()
            b.setObjectName("navBtn")
            b.setText(tr(_key))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(26, 26))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setMinimumHeight(72)
            b.clicked.connect(lambda checked, idx=i: self._switch_page(idx))
            nv.addWidget(b)
            self._nav_btns.append(b)
        self._nav_btns[0].setChecked(True)

        nv.addStretch()
        self.lbl_status = QLabel(tr("status_offline"))
        self.lbl_status.setObjectName("statusDot")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #71717a;")
        nv.addWidget(self.lbl_status)
        outer.addWidget(nav)

        # --- Main column ---
        main_col = QVBoxLayout()
        main_col.setContentsMargins(24, 24, 24, 20)
        main_col.setSpacing(16)

        # Page: Connect
        page_connect = QWidget()
        pc = QVBoxLayout(page_connect)
        card = QFrame()
        card.setObjectName("contentCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(32, 28, 32, 28)
        cl.setSpacing(18)
        self.lbl_connect_title = QLabel()
        self.lbl_connect_title.setObjectName("cardTitle")
        self.lbl_connect_desc = QLabel()
        self.lbl_connect_desc.setObjectName("cardDesc")
        cl.addWidget(self.lbl_connect_title)
        cl.addWidget(self.lbl_connect_desc)

        grid = QGridLayout()
        grid.setSpacing(14)
        grid.setColumnStretch(1, 1)
        grid.addWidget(self._fl("field_host"), 0, 0)
        self.txt_host = QLineEdit()
        grid.addWidget(self.txt_host, 0, 1, 1, 3)
        grid.addWidget(self._fl("field_dns_host"), 1, 0)
        self.txt_dns = QLineEdit()
        grid.addWidget(self.txt_dns, 1, 1, 1, 3)
        grid.addWidget(self._fl("field_port"), 2, 0)
        self.txt_port = QLineEdit()
        self.txt_port.setMaxLength(5)
        self.txt_port.setClearButtonEnabled(False)
        self.txt_port.setFixedWidth(120)
        self.txt_port.setMinimumHeight(36)
        grid.addWidget(self.txt_port, 2, 1, 1, 3)
        grid.addWidget(self._fl("field_username"), 3, 0)
        self.txt_user = QLineEdit()
        grid.addWidget(self.txt_user, 3, 1, 1, 3)
        grid.addWidget(self._fl("field_password"), 4, 0)
        self.txt_pass = QLineEdit()
        self.txt_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_pass.setClearButtonEnabled(False)
        self.chk_hide_pass = QCheckBox()
        self.chk_hide_pass.setChecked(True)
        self.chk_hide_pass.toggled.connect(self._toggle_pass_visibility)
        pass_row = QHBoxLayout()
        pass_row.setContentsMargins(0, 0, 0, 0)
        pass_row.addWidget(self.txt_pass, stretch=1)
        pass_row.addWidget(self.chk_hide_pass)
        pass_wrap = QWidget()
        pass_wrap.setLayout(pass_row)
        grid.addWidget(pass_wrap, 4, 1, 1, 3)
        grid.addWidget(self._fl("field_ssh_key"), 5, 0)
        self.txt_key = QLineEdit()
        btn_key = QPushButton("...")
        btn_key.setFixedWidth(36)
        btn_key.clicked.connect(self._browse_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.txt_key)
        key_row.addWidget(btn_key)
        grid.addLayout(key_row, 5, 1, 1, 3)
        cl.addLayout(grid)

        prof_row = QHBoxLayout()
        prof_row.addWidget(self._fl("field_profile"))
        self.combo_profile = QComboBox()
        self.combo_profile.setMinimumWidth(200)
        self.combo_profile.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if hasattr(self.combo_profile, "setWheelEnabled"):
            self.combo_profile.setWheelEnabled(False)
        self.combo_profile.activated.connect(self._on_profile_activated)
        prof_row.addWidget(self.combo_profile, stretch=1)
        self.btn_save_prof = QPushButton()
        self.btn_save_prof.clicked.connect(self._save_current_profile)
        self.btn_del_prof = QPushButton()
        self.btn_del_prof.clicked.connect(self._delete_current_profile)
        self.btn_ping = QPushButton()
        self.btn_ping.clicked.connect(self.ping_host)
        for b in (self.btn_save_prof, self.btn_del_prof, self.btn_ping):
            b.setStyleSheet(
                "QPushButton { background:#27272a; color:#e4e4e7; border:none;"
                "border-radius:8px; padding:8px 12px; }"
                "QPushButton:hover { background:#3f3f46; }"
            )
        prof_row.addWidget(self.btn_save_prof)
        prof_row.addWidget(self.btn_del_prof)
        prof_row.addWidget(self.btn_ping)
        cl.addLayout(prof_row)

        row_btn = QHBoxLayout()
        self._btn_login_style = """
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0d9488, stop:1 #0891b2);
                color: white; font-weight: 700; border: none;
                border-radius: 12px; padding: 12px 32px; font-size: 14px;
            }
            QPushButton:hover { background-color: #14b8a6; }
        """
        self._btn_logout_style = """
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #e11d48, stop:1 #be123c);
                color: white; font-weight: 700; border: none;
                border-radius: 12px; padding: 12px 32px;
            }
            QPushButton:hover { background-color: #fb7185; }
        """
        self.btn_action = QPushButton()
        self.btn_action.setStyleSheet(self._btn_login_style)
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.clicked.connect(self.handle_action)
        row_btn.addWidget(self.btn_action)
        self._setup_connect_form_state()
        for field in (
            self.txt_host, self.txt_dns, self.txt_user, self.txt_pass,
        ):
            field.returnPressed.connect(self._submit_connect_form)
        row_btn.addStretch()
        self.btn_exit = QPushButton()
        self.btn_exit.setStyleSheet(
            "QPushButton { background:#27272a; color:#a1a1aa; border:none;"
            "border-radius:12px; padding:12px 24px; }"
            "QPushButton:hover { background:#3f3f46; color:#fafafa; }"
        )
        self.btn_exit.clicked.connect(self.close)
        row_btn.addWidget(self.btn_exit)
        cl.addLayout(row_btn)
        pc.addWidget(card)
        pc.addStretch()
        self.stack.addWidget(page_connect)

        # Page: Workspace (tools grid)
        page_ws = QWidget()
        pw = QVBoxLayout(page_ws)
        self.lbl_workspace_title = QLabel()
        self.lbl_workspace_title.setObjectName("cardTitle")
        self.lbl_session = QLabel()
        self.lbl_session.setObjectName("cardDesc")
        pw.addWidget(self.lbl_workspace_title)
        pw.addWidget(self.lbl_session)

        tools_grid = QGridLayout()
        tools_grid.setSpacing(12)
        self._tool_buttons = []
        self._tool_defs_keys = [
            ("💻", "tool_terminal", "tool_terminal_hint", self.open_terminal_action),
            ("📂", "tool_sftp", "tool_sftp_desc", self.open_sftp_action),
            ("🖼", "tool_rdp", "tool_rdp_desc", self.open_remote_desktop),
            ("📊", "tool_sysinfo", "tool_sysinfo_desc", self.open_system_info),
            ("🔀", "tool_portfwd", "tool_portfwd_desc", self.open_port_forward),
            ("🔑", "tool_hostkey", "tool_hostkey_desc", self.show_fingerprint),
        ]
        for i, (icon, title_key, desc_key, slot) in enumerate(self._tool_defs_keys):
            btn = QPushButton()
            btn.setProperty("tool_icon", icon)
            btn.setProperty("title_key", title_key)
            btn.setProperty("desc_key", desc_key)
            btn.setObjectName("toolCard")
            btn.setMinimumHeight(110)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setEnabled(False)
            btn.clicked.connect(slot)
            tools_grid.addWidget(btn, i // 3, i % 3)
            self._tool_buttons.append(btn)
        pw.addLayout(tools_grid)
        pw.addStretch()
        self.stack.addWidget(page_ws)

        # Page: Settings
        page_set = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        sw = QWidget()
        sl = QVBoxLayout(sw)
        sc = QFrame()
        sc.setObjectName("contentCard")
        scl = QVBoxLayout(sc)
        scl.setContentsMargins(28, 24, 28, 24)
        self.lbl_settings_title = QLabel()
        self.lbl_settings_title.setObjectName("cardTitle")
        scl.addWidget(self.lbl_settings_title)

        self.lbl_sec_general = QLabel()
        self.lbl_sec_general.setObjectName("settingsSection")
        scl.addWidget(self.lbl_sec_general)

        row_lang = QHBoxLayout()
        row_lang.addWidget(self._fl("field_language"))
        self.combo_language = QComboBox()
        self.combo_language.addItem(tr("lang_vi"), LANG_VI)
        self.combo_language.addItem(tr("lang_en"), LANG_EN)
        self.combo_language.currentIndexChanged.connect(self._on_language_changed)
        row_lang.addWidget(self.combo_language, stretch=1)
        scl.addLayout(row_lang)

        self.lbl_sec_ui = QLabel()
        self.lbl_sec_ui.setObjectName("settingsSection")
        scl.addWidget(self.lbl_sec_ui)

        row_mode = QHBoxLayout()
        row_mode.addWidget(self._fl("field_color_mode"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem(tr("color_dark"), "dark")
        self.combo_mode.addItem(tr("color_light"), "light")
        self.combo_mode.currentIndexChanged.connect(self._on_appearance_changed)
        row_mode.addWidget(self.combo_mode, stretch=1)
        scl.addLayout(row_mode)

        row_theme = QHBoxLayout()
        row_theme.addWidget(self._fl("field_theme"))
        self.combo_theme = QComboBox()
        for tid, tname in THEME_IDS:
            self.combo_theme.addItem(tname, tid)
        self.combo_theme.currentIndexChanged.connect(self._on_appearance_changed)
        row_theme.addWidget(self.combo_theme, stretch=1)
        scl.addLayout(row_theme)

        row_visual = QHBoxLayout()
        row_visual.addWidget(self._fl("field_visual"))
        self.combo_visual = QComboBox()
        for sid, sname in VISUAL_STYLE_IDS:
            self.combo_visual.addItem(sname, sid)
        self.combo_visual.currentIndexChanged.connect(self._on_appearance_changed)
        row_visual.addWidget(self.combo_visual, stretch=1)
        scl.addLayout(row_visual)

        self.chk_transparent = QCheckBox()
        self.chk_transparent.stateChanged.connect(self._on_appearance_changed)
        scl.addWidget(self.chk_transparent)

        self.lbl_sec_bg = QLabel()
        self.lbl_sec_bg.setObjectName("settingsSection")
        scl.addWidget(self.lbl_sec_bg)
        self.bg_grid_widget = QWidget()
        self.bg_grid = QGridLayout(self.bg_grid_widget)
        self.bg_grid.setSpacing(10)
        scl.addWidget(self.bg_grid_widget)

        self.btn_custom_bg = QPushButton()
        self.btn_custom_bg.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_custom_bg.clicked.connect(self._pick_custom_background)
        scl.addWidget(self.btn_custom_bg)

        self.lbl_custom_bg = QLabel()
        self.lbl_custom_bg.setObjectName("settingsHint")
        self.lbl_custom_bg.setWordWrap(True)
        scl.addWidget(self.lbl_custom_bg)

        self.lbl_sec_perf = QLabel()
        self.lbl_sec_perf.setObjectName("settingsSection")
        scl.addWidget(self.lbl_sec_perf)
        self.chk_fast_ui = QCheckBox()
        self.chk_fast_ui.setChecked(True)
        self.chk_fast_ui.stateChanged.connect(self._on_appearance_changed)
        scl.addWidget(self.chk_fast_ui)

        self.chk_auto_term = QCheckBox()
        self.chk_auto_fm = QCheckBox()
        self.chk_auto_rdp = QCheckBox()
        scl.addWidget(self.chk_auto_term)
        scl.addWidget(self.chk_auto_fm)
        scl.addWidget(self.chk_auto_rdp)

        self.chk_startup_win = QCheckBox()
        self.chk_startup_win.setEnabled(sys.platform.startswith("win"))
        self.chk_startup_win.stateChanged.connect(self._on_startup_windows_changed)
        scl.addWidget(self.chk_startup_win)

        self.lbl_history_title = QLabel()
        scl.addWidget(self.lbl_history_title)
        self.list_history = QListWidget()
        self.list_history.setMaximumHeight(120)
        self.list_history.itemDoubleClicked.connect(self._load_from_history)
        scl.addWidget(self.list_history)

        self.btn_export_log = QPushButton()
        self.btn_export_log.clicked.connect(self.export_log)
        self.btn_copy_log = QPushButton()
        self.btn_copy_log.clicked.connect(self.copy_log)
        scl.addWidget(self.btn_export_log)
        scl.addWidget(self.btn_copy_log)
        scl.addStretch()
        self._refresh_history_list()
        sl.addWidget(sc)
        sl.addStretch()
        scroll.setWidget(sw)
        ps = QVBoxLayout(page_set)
        ps.addWidget(scroll)
        self.stack.addWidget(page_set)

        # Page: About — layout kiểu Bitvise (group box + liên kết)
        page_about = QWidget()
        pa_outer = QVBoxLayout(page_about)
        pa_outer.setContentsMargins(0, 0, 0, 0)
        scroll_about = QScrollArea()
        scroll_about.setWidgetResizable(True)
        scroll_about.setFrameShape(QFrame.Shape.NoFrame)
        scroll_about.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        scroll_inner = QWidget()
        pa = QVBoxLayout(scroll_inner)
        pa.setContentsMargins(16, 12, 16, 16)
        pa.setAlignment(Qt.AlignmentFlag.AlignTop)

        panel = QFrame()
        panel.setObjectName("aboutBitvisePanel")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 14, 16, 14)
        pl.setSpacing(8)
        pl.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.lbl_about_headline = QLabel()
        self.lbl_about_headline.setObjectName("aboutHeadline")
        self.lbl_about_headline.setWordWrap(True)
        self.lbl_about_headline.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        pl.addWidget(self.lbl_about_headline)

        self.lbl_about_version_status = self._about_rich_label("")
        pl.addWidget(self.lbl_about_version_status)

        self._gb_app, gl_app = self._make_about_group("")
        self.lbl_about_app_desc = self._about_body_label("")
        gl_app.addWidget(self.lbl_about_app_desc)
        if os.path.isfile(APP_LOGO):
            app_px = QPixmap(APP_LOGO).scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            app_icon = QLabel()
            app_icon.setPixmap(app_px)
            app_icon.setFixedSize(app_px.size())
            row_icon = QHBoxLayout()
            row_icon.setContentsMargins(0, 4, 0, 0)
            row_icon.setSpacing(10)
            row_icon.setAlignment(Qt.AlignmentFlag.AlignLeft)
            row_icon.addWidget(app_icon, alignment=Qt.AlignmentFlag.AlignVCenter)
            self.lbl_about_version_build = self._about_body_label("")
            row_icon.addWidget(
                self.lbl_about_version_build, alignment=Qt.AlignmentFlag.AlignVCenter
            )
            row_icon.addStretch()
            gl_app.addLayout(row_icon)
        else:
            self.lbl_about_version_build = None
        pl.addWidget(self._gb_app)

        self._gb_feat, gl_feat = self._make_about_group("")
        self.lbl_about_features = self._about_body_label("")
        gl_feat.addWidget(self.lbl_about_features)
        pl.addWidget(self._gb_feat)

        self._gb_dev, gl_dev = self._make_about_group("")
        if os.path.isfile(OASIS_LOGO):
            src = QPixmap(OASIS_LOGO)
            scaled = src.scaledToWidth(
                260, Qt.TransformationMode.SmoothTransformation
            )
            oasis_logo = QLabel()
            oasis_logo.setObjectName("aboutOasisLogo")
            oasis_logo.setPixmap(scaled)
            oasis_logo.setFixedSize(scaled.size())
            oasis_logo.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            gl_dev.addWidget(
                oasis_logo, alignment=Qt.AlignmentFlag.AlignLeft
            )
        self.lbl_about_dev_credit = self._about_body_label("")
        gl_dev.addWidget(self.lbl_about_dev_credit)
        self.lbl_about_dev_oasis = self._about_body_label("")
        gl_dev.addWidget(self.lbl_about_dev_oasis)
        pl.addWidget(self._gb_dev)

        self._gb_contact, gl_contact = self._make_about_group("")
        self.lbl_about_contact_hint = self._about_body_label("")
        gl_contact.addWidget(self.lbl_about_contact_hint)
        gl_contact.addWidget(self._about_link_label(
            "bquangthien25@gmail.com", "mailto:bquangthien25@gmail.com"
        ))
        acc = PALETTES.get(
            self._settings.get("theme_id", "teal"), PALETTES["teal"]
        )["accent"]
        self._about_music_bars = MusicBarsWidget(22, accent=acc, parent=self)
        gl_contact.addWidget(self._about_music_bars)
        pl.addWidget(self._gb_contact)

        pa.addWidget(panel, alignment=Qt.AlignmentFlag.AlignTop)
        scroll_about.setWidget(scroll_inner)
        pa_outer.addWidget(scroll_about)
        self.stack.addWidget(page_about)

        main_col.addWidget(self.stack, stretch=1)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(160)
        main_col.addWidget(self.txt_log)
        outer.addLayout(main_col, stretch=1)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.addWidget(self._bg)

        if os.path.isfile(APP_LOGO):
            self.setWindowIcon(QIcon(APP_LOGO))

        self._retranslate_ui()
        self.log_info(tr("log_ready"))
        self.log_info(tr("log_ready_connect"))
        if sys.platform.startswith("linux"):
            rdp_msg = linux_rdp_status_message()
            if rdp_msg:
                self.log_info(rdp_msg)
            QTimer.singleShot(800, self._maybe_install_freerdp_on_linux)

    def _fl(self, key):
        lb = QLabel()
        lb.setObjectName("fieldLabel")
        self._field_label_keys.append((lb, key))
        return lb

    def _setup_connect_form_state(self):
        """Giá trị form lưu RAM; khi rời ô phải chụp text ngay (không cần bấm Space)."""
        self._connect_field_map = {
            "host": self.txt_host,
            "dns": self.txt_dns,
            "port": self.txt_port,
            "user": self.txt_user,
            "pass": self.txt_pass,
            "key": self.txt_key,
        }
        for key, widget in self._connect_field_map.items():
            widget.textChanged.connect(
                lambda _text, k=key, w=widget: self._capture_connect_field(k, w),
            )
            widget.editingFinished.connect(
                lambda k=key, w=widget: self._capture_connect_field(k, w),
            )

        class _ConnectFieldGuard(QObject):
            def __init__(self, window):
                super().__init__(window)
                self._win = window

            def eventFilter(self, obj, event):
                win = self._win
                if obj not in win._connect_field_map.values():
                    return False
                if event.type() == QEvent.Type.FocusOut:
                    win._capture_connect_field_by_widget(obj)
                elif event.type() == QEvent.Type.KeyPress:
                    QTimer.singleShot(0, lambda w=obj: win._capture_connect_field_by_widget(w))
                return False

        guard = _ConnectFieldGuard(self)
        self._connect_field_guard = guard
        for widget in self._connect_field_map.values():
            widget.installEventFilter(guard)

        app = QApplication.instance()
        if app and not getattr(self, "_focus_hooked", False):
            app.focusChanged.connect(self._on_connect_focus_changed)
            self._focus_hooked = True

        self._restore_connect_form_fields()

    def _capture_connect_field_by_widget(self, widget):
        for key, w in self._connect_field_map.items():
            if w is widget:
                self._capture_connect_field(key, w)
                return

    def _toggle_pass_visibility(self, hide):
        """Mặc định ẩn mật khẩu; bỏ tick «Ẩn MK» để hiện chữ."""
        self.txt_pass.setEchoMode(
            QLineEdit.EchoMode.Password if hide else QLineEdit.EchoMode.Normal,
        )
        self._schedule_restore_connect_form()

    def _capture_connect_field(self, key, widget):
        if self._form_syncing:
            return
        self._connect_form[key] = widget.text()
        if key == "port":
            self._update_connect_button_label()

    def _on_connect_focus_changed(self, old, _new):
        fields = set(self._connect_field_map.values())
        if old in fields:
            self._capture_connect_field_by_widget(old)
        if old in fields or _new in fields:
            self._schedule_restore_connect_form()

    def _schedule_restore_connect_form(self):
        for ms in (0, 40):
            QTimer.singleShot(ms, self._restore_connect_form_fields)

    def _restore_connect_form_fields(self):
        """Khôi phục ô bị Qt xóa trắng; không ghi đè ô user đang gõ."""
        self._form_syncing = True
        try:
            for key, widget in self._connect_field_map.items():
                cached = self._connect_form.get(key, "")
                live = widget.text()
                if not live and cached:
                    widget.setText(cached)
                elif live != cached:
                    self._connect_form[key] = live
            self._update_connect_button_label()
        finally:
            self._form_syncing = False

    def _flush_connect_form_from_widgets(self):
        """Gọi trước Ping / Lưu profile / Kết nối — lấy cả ô đang focus (chưa bấm Space)."""
        focused = QApplication.focusWidget()
        if focused in self._connect_field_map.values():
            self._capture_connect_field_by_widget(focused)
        for key, widget in self._connect_field_map.items():
            self._connect_form[key] = widget.text()

    def _get_password(self):
        self._flush_connect_form_from_widgets()
        return self._connect_form.get("pass", "")

    def _init_connect_form_empty(self):
        """Form trống khi mở app — không điền sẵn IP/domain/port."""
        self._connect_form = {
            "host": "", "dns": "", "port": "", "user": "", "pass": "", "key": "",
        }
        clear_connection_history()
        self._session_history.clear()
        if hasattr(self, "_connect_field_map"):
            for widget in self._connect_field_map.values():
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)
            self._restore_connect_form_fields()
        self._update_connect_button_label()
        if hasattr(self, "list_history"):
            self._refresh_history_list()

    def _maybe_install_freerdp_on_linux(self):
        """Linux: hỏi cài xfreerdp nếu chưa có (bundled hoặc hệ thống)."""
        if not sys.platform.startswith("linux"):
            return
        if linux_rdp_client_available():
            return
        if self._freerdp_install_worker and self._freerdp_install_worker.isRunning():
            return
        reply = QMessageBox.question(
            self,
            tr("freerdp_install_title"),
            tr("freerdp_install_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.log_info(tr("freerdp_install_skipped"))
            return
        self._run_freerdp_install()

    def _run_freerdp_install(self):
        if self._freerdp_install_worker and self._freerdp_install_worker.isRunning():
            return
        progress = QProgressDialog(
            tr("freerdp_install_progress"),
            None,
            0,
            0,
            self,
        )
        progress.setWindowTitle(tr("freerdp_install_title"))
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setCancelButton(None)
        progress.show()
        QApplication.processEvents()
        self._freerdp_install_progress = progress

        worker = _FreerdpInstallWorker()
        worker.install_result.connect(
            self._on_freerdp_install_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(worker.deleteLater)
        self._freerdp_install_worker = worker
        worker.start()

    def _on_freerdp_install_finished(self, ok, message):
        if self._freerdp_install_progress:
            self._freerdp_install_progress.close()
            self._freerdp_install_progress = None
        if self._freerdp_install_worker and not self._freerdp_install_worker.isRunning():
            self._freerdp_install_worker = None
        if ok:
            self.log_info(message or tr("freerdp_install_ok"))
            if linux_rdp_client_available():
                self.log_info(linux_rdp_status_message())
            else:
                QMessageBox.information(
                    self, tr("freerdp_install_title"), tr("freerdp_install_ok"),
                )
        else:
            self.log_info(tr("freerdp_install_fail", msg=message))
            QMessageBox.warning(
                self,
                tr("freerdp_install_title"),
                tr("freerdp_install_fail", msg=message),
            )

    def _ensure_freerdp_for_rdp(self) -> bool:
        """Đảm bảo có xfreerdp trước khi mở Remote Desktop (Linux)."""
        if not sys.platform.startswith("linux"):
            return True
        if linux_rdp_client_available():
            return True
        reply = QMessageBox.question(
            self,
            tr("freerdp_install_title"),
            tr("freerdp_install_rdp_body"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False
        ok, msg = ensure_linux_freerdp_installed()
        if ok and linux_rdp_client_available():
            self.log_info(msg)
            return True
        QMessageBox.warning(
            self,
            tr("freerdp_install_title"),
            tr("freerdp_install_fail", msg=msg),
        )
        return False

    def _default_connect_port(self):
        """Windows: mặc định RDP (3389) — giống Remote Desktop Connection."""
        if sys.platform.startswith("win"):
            return RDP_PORT
        return 22

    def _effective_connect_port(self, port_text=""):
        port_text = (port_text or self._connect_form.get("port", "")).strip()
        try:
            return int(port_text) if port_text else self._default_connect_port()
        except ValueError:
            return self._default_connect_port()

    def _is_rdp_mode(self):
        return self._effective_connect_port() == RDP_PORT

    def _submit_connect_form(self):
        if not self.is_logged_in:
            self.handle_action()

    def _prepare_connect_target(self, require_host=True, require_resolve=True):
        """Resolve DNS/DDNS trước khi ping / SSH / RDP."""
        self._flush_connect_form_from_widgets()
        host = self._connect_form.get("host", "").strip()
        dns_host = self._connect_form.get("dns", "").strip()
        if not host and not dns_host:
            if require_host:
                return None, tr("warn_enter_host")
            return None, ""
        info = prepare_connect_host(
            host, dns_host,
            require_resolve=require_resolve,
            default_dns=get_default_dns_host(),
        )
        if info.get("error"):
            return None, info["error"]
        connect_host = info["connect_host"]
        if info.get("resolved_ip"):
            # Chỉ cập nhật IP trong RAM khi user đã nhập host hoặc dns
            if host or dns_host:
                self._connect_form["host"] = info["resolved_ip"]
            if info.get("dns_host") and dns_host:
                self._connect_form["dns"] = info["dns_host"]
            if host or dns_host:
                self._restore_connect_form_fields()
        if info.get("changed"):
            self.log_info(
                tr(
                    "log_dns_updated",
                    dns=info["dns_host"],
                    ip=info["resolved_ip"],
                )
            )
        return info, ""

    def _current_profile_name(self):
        p = self.combo_profile.currentData() if hasattr(self, "combo_profile") else None
        return (p or {}).get("name", "")

    def _persist_dns_to_profile(self, info):
        name = self._current_profile_name()
        if not name or not info:
            return
        fields = {}
        if info.get("dns_host"):
            fields["dns_host"] = info["dns_host"]
        if info.get("resolved_ip"):
            fields["host"] = info["resolved_ip"]
        if fields:
            update_profile_fields(name, **fields)

    def _apply_remote_dns_to_form(self, remote_dns):
        remote_dns = (remote_dns or "").strip()
        if not remote_dns:
            return
        self._connect_form["dns"] = remote_dns
        info, _ = self._prepare_connect_target(require_host=False)
        if info and info.get("resolved_ip"):
            self._restore_connect_form_fields()
            self.log_info(
                tr("log_dns_sync_server", dns=remote_dns, ip=info["resolved_ip"])
            )
            self._persist_dns_to_profile(info)

    def _sync_dns_from_server(self):
        try:
            remote_dns = self.ssh_manager.fetch_remote_dns_host()
        except Exception:
            remote_dns = ""
        if remote_dns:
            self._apply_remote_dns_to_form(remote_dns)

    def _refresh_dns_profiles(self, silent=False):
        updated = refresh_all_profile_dns(refresh_profile_entry)
        if not updated:
            return
        self._refresh_profiles()
        current = self._current_profile_name()
        if current in updated:
            self._load_profile()
            if not silent:
                self.log_info(tr("log_dns_profiles_refreshed", count=len(updated)))

    def _on_dns_refresh_tick(self):
        if self.is_logged_in:
            return
        self._refresh_dns_profiles(silent=True)
        dns_host = self._connect_form.get("dns", "").strip()
        if not dns_host:
            return
        old_ip = self._connect_form.get("host", "").strip()
        info, _ = self._prepare_connect_target(require_host=False)
        if info and info.get("changed"):
            self.log_info(
                tr(
                    "log_dns_updated",
                    dns=info["dns_host"],
                    ip=info["resolved_ip"],
                )
            )
        elif info and info.get("resolved_ip") and info["resolved_ip"] != old_ip:
            self._restore_connect_form_fields()

    def _retranslate_ui(self):
        """Cập nhật toàn bộ chuỗi UI theo ngôn ngữ hiện tại."""
        for i, btn in enumerate(self._nav_btns):
            if i < len(self._nav_label_keys):
                btn.setText(tr(self._nav_label_keys[i]))

        self.lbl_connect_title.setText(tr("connect_setup"))
        self.lbl_connect_desc.setText(tr("welcome_msg"))
        self.txt_host.setPlaceholderText(tr("placeholder_host"))
        if hasattr(self, "txt_dns"):
            self.txt_dns.setPlaceholderText(tr("placeholder_dns"))
        self.txt_port.setPlaceholderText(tr("placeholder_port"))
        self.txt_user.setPlaceholderText(tr("placeholder_user"))
        self.txt_pass.setPlaceholderText(tr("placeholder_pass"))
        if hasattr(self, "chk_hide_pass"):
            self.chk_hide_pass.setText(tr("chk_hide_pass"))
        self.txt_key.setPlaceholderText(tr("placeholder_key"))
        self.btn_save_prof.setText(tr("btn_save_profile"))
        self.btn_del_prof.setText(tr("btn_delete"))
        self.btn_ping.setText(tr("btn_ping_host"))
        self.btn_exit.setText(tr("btn_exit"))
        if self.is_logged_in:
            self.btn_action.setText(tr("btn_disconnect"))
        else:
            self._update_connect_button_label()

        for lb, key in self._field_label_keys:
            lb.setText(tr(key))

        self.lbl_workspace_title.setText(tr("workspace_title"))
        term_hint_key = (
            "tool_terminal_hint_win"
            if self._local_os == "windows"
            else "tool_terminal_hint_linux"
        )
        for btn in self._tool_buttons:
            icon = btn.property("tool_icon") or ""
            title_key = btn.property("title_key") or ""
            desc_key = btn.property("desc_key") or ""
            desc = tr(desc_key)
            if desc_key == "tool_terminal_hint":
                desc = tr(term_hint_key)
            btn.setText(f"{icon}  {tr(title_key)}\n\n{desc}")

        self.lbl_settings_title.setText(tr("settings_title"))
        self.lbl_sec_general.setText(tr("section_general"))
        self.lbl_sec_ui.setText(tr("section_ui"))
        self.lbl_sec_bg.setText(tr("section_background"))
        self.lbl_sec_perf.setText(tr("section_perf"))
        self.lbl_history_title.setText(tr("history_title"))
        self.btn_custom_bg.setText(tr("btn_custom_bg"))
        self.btn_export_log.setText(tr("btn_export_log"))
        self.btn_copy_log.setText(tr("btn_copy_log"))

        self.chk_transparent.setText(tr("chk_transparent"))
        self.chk_transparent.setToolTip(tr("chk_transparent_tip"))
        self.chk_fast_ui.setText(tr("chk_smooth"))
        self.chk_auto_term.setText(tr("chk_auto_term"))
        self.chk_auto_fm.setText(tr("chk_auto_fm"))
        self.chk_auto_rdp.setText(tr("chk_auto_rdp"))
        self.chk_startup_win.setText(tr("chk_startup_win"))
        if not sys.platform.startswith("win"):
            self.chk_startup_win.setToolTip(tr("chk_startup_win_tip"))
        self.combo_visual.setToolTip(tr("visual_tooltip"))

        lang = get_language()
        self.combo_language.blockSignals(True)
        idx = 0 if lang == LANG_VI else 1
        self.combo_language.clear()
        self.combo_language.addItem(tr("lang_vi"), LANG_VI)
        self.combo_language.addItem(tr("lang_en"), LANG_EN)
        self.combo_language.setCurrentIndex(idx)
        self.combo_language.blockSignals(False)

        mode_idx = self.combo_mode.currentIndex()
        self.combo_mode.blockSignals(True)
        self.combo_mode.clear()
        self.combo_mode.addItem(tr("color_dark"), "dark")
        self.combo_mode.addItem(tr("color_light"), "light")
        self.combo_mode.setCurrentIndex(max(0, mode_idx))
        self.combo_mode.blockSignals(False)

        if not self.is_logged_in:
            self.lbl_status.setText(tr("status_offline"))
        elif self.lbl_status.text().startswith("●") and "…" in self.lbl_status.text():
            self.lbl_status.setText(tr("status_connecting"))
        elif self.is_logged_in:
            self.lbl_status.setText(tr("status_online"))

        self._refresh_session_label()
        self._update_custom_bg_label()

        empty = self.combo_profile.itemText(0) if self.combo_profile.count() else ""
        if self.combo_profile.count() and (
            empty.startswith("—") or empty.startswith("-")
        ):
            self.combo_profile.blockSignals(True)
            self.combo_profile.setItemText(0, tr("combo_profile_empty"))
            self.combo_profile.blockSignals(False)

        self.lbl_about_headline.setText(tr("about_headline"))
        self.lbl_about_version_status.setText(tr("about_version_status"))
        self._gb_app.setTitle(tr("about_group_app"))
        self.lbl_about_app_desc.setText(tr("about_app_desc"))
        if self.lbl_about_version_build is not None:
            self.lbl_about_version_build.setText(tr("about_version_build"))
        self._gb_feat.setTitle(tr("about_group_features"))
        self.lbl_about_features.setText(tr("about_features_desc"))
        self._gb_dev.setTitle(tr("about_group_dev"))
        self.lbl_about_dev_credit.setText(tr("about_dev_credit"))
        self.lbl_about_dev_oasis.setText(tr("about_dev_oasis"))
        self._gb_contact.setTitle(tr("about_group_contact"))
        self.lbl_about_contact_hint.setText(tr("about_contact_hint"))

    def _on_language_changed(self):
        lang = self.combo_language.currentData()
        if lang not in (LANG_VI, LANG_EN) or lang == get_language():
            return
        set_language(lang)
        save_settings({"language": lang})
        self._settings["language"] = lang
        self._retranslate_ui()
        name = tr("lang_vi") if lang == LANG_VI else tr("lang_en")
        self.log_info(tr("language_changed", lang=name))

    def _make_about_group(self, title):
        gb = QGroupBox(title)
        gb.setObjectName("aboutGroup")
        gb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lay = QVBoxLayout(gb)
        lay.setContentsMargins(12, 18, 12, 12)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        return gb, lay

    def _about_body_label(self, text):
        lb = QLabel(text)
        lb.setObjectName("aboutBody")
        lb.setWordWrap(True)
        lb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lb.setContentsMargins(0, 0, 0, 0)
        if "<" in text:
            lb.setTextFormat(Qt.TextFormat.RichText)
        return lb

    def _about_rich_label(self, html):
        lb = QLabel(html)
        lb.setObjectName("aboutBody")
        lb.setWordWrap(True)
        lb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.setTextFormat(Qt.TextFormat.RichText)
        lb.setOpenExternalLinks(True)
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        return lb

    def _about_link_label(self, text, href):
        lb = QLabel(f'<a href="{href}">{text}</a>')
        lb.setObjectName("aboutLink")
        lb.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.setOpenExternalLinks(True)
        lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        return lb

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, b in enumerate(self._nav_btns):
            b.setChecked(i == index)
        self._refresh_nav_icons()

    def closeEvent(self, event):
        if self._connect_worker and self._connect_worker.isRunning():
            self._connect_worker.wait(4000)
            if self._connect_worker.isRunning():
                self._connect_worker.terminate()
                self._connect_worker.wait(1000)
        self._end_connect_progress()
        self._wipe_sensitive_data()
        super().closeEvent(event)

    def _session_host(self):
        return self.ssh_manager.get_session_host() or self.txt_host.text().strip()

    def _session_user(self):
        return self.ssh_manager.get_session_user() or self.txt_user.text().strip()

    def _wipe_sensitive_data(self):
        """Xóa mọi thông tin nhạy cảm khi thoát — không lưu IP/user/pass."""
        if getattr(self, "_secrets_wiped", False):
            return
        self._secrets_wiped = True
        if self.is_logged_in:
            self.ssh_manager.disconnect()
            self.is_logged_in = False
        if self._fm_window:
            try:
                self._fm_window.close()
            except Exception:
                pass
            self._fm_window = None
        for w in list(self._child_windows):
            try:
                w.close()
            except Exception:
                pass
        self._child_windows.clear()

        self.txt_host.clear()
        self.txt_dns.clear()
        self.txt_user.clear()
        self.txt_pass.clear()
        self.txt_key.clear()
        self.txt_port.clear()
        self._connect_form = {
            "host": "", "dns": "", "port": "", "user": "", "pass": "", "key": "",
        }

        if hasattr(self, "txt_log"):
            self.txt_log.clear()
        if hasattr(self, "list_history"):
            self.list_history.clear()
        self._session_history.clear()
        clear_connection_history()

        if hasattr(self, "combo_profile") and self.combo_profile.count():
            self.combo_profile.blockSignals(True)
            self.combo_profile.setCurrentIndex(0)
            self.combo_profile.blockSignals(False)

    def _session_status_text(self, remote_os=None):
        """Dòng trạng thái: máy bạn (local) + máy chủ (remote)."""
        if not self.is_logged_in:
            return tr("session_login_hint")
        host = self._session_host()
        user = self._session_user()
        local_label = format_os_display(self._local_os, role="local")
        raw = remote_os if remote_os is not None else self.ssh_manager.remote_os
        remote_label = format_os_display(raw) if raw else tr("session_detecting")
        return tr(
            "session_connected_fmt",
            user=user,
            host=host,
            local=local_label,
            remote=remote_label,
        )

    def _on_remote_os_ready(self, os_name):
        """Thread nền gọi — cập nhật nhãn OS trên UI thread."""
        QTimer.singleShot(0, lambda: self._refresh_session_label(os_name))

    def _refresh_session_label(self, remote_os=None):
        if self.is_logged_in:
            self.lbl_session.setText(self._session_status_text(remote_os))
        else:
            local_label = format_os_display(self._local_os, role="local")
            self.lbl_session.setText(
                tr("session_not_connected_local", local=local_label)
            )

    def _set_connected_ui(self, connected):
        if connected:
            self.lbl_status.setText(tr("status_online"))
            self.lbl_status.setStyleSheet(
                "color: #34d399; background-color: #052e16;"
                " border-radius: 12px; padding: 6px;"
            )
            self.lbl_session.setText(self._session_status_text())
            for b in self._tool_buttons:
                b.setEnabled(True)
        else:
            self.lbl_status.setText(tr("status_offline"))
            self.lbl_status.setStyleSheet("color: #71717a;")
            local_label = format_os_display(self._local_os, role="local")
            self.lbl_session.setText(
                tr("session_not_connected_local", local=local_label)
            )
            for b in self._tool_buttons:
                is_rdp = b.property("title_key") == "tool_rdp"
                b.setEnabled(is_rdp)

    def _load_settings_to_ui(self):
        s = self._settings
        lang = s.get("language", LANG_VI)
        set_language(lang)
        if hasattr(self, "combo_language"):
            self.combo_language.blockSignals(True)
            self.combo_language.setCurrentIndex(0 if lang == LANG_VI else 1)
            self.combo_language.blockSignals(False)
            self._retranslate_ui()
        self.chk_auto_term.setChecked(s.get("auto_terminal", False))
        self.chk_auto_fm.setChecked(s.get("auto_file_manager", False))
        self.chk_auto_rdp.setChecked(s.get("auto_rdp", False))
        if hasattr(self, "chk_startup_win"):
            self.chk_startup_win.blockSignals(True)
            self.chk_startup_win.setChecked(
                is_startup_enabled() if sys.platform.startswith("win")
                else s.get("start_with_windows", False)
            )
            self.chk_startup_win.blockSignals(False)
        self.chk_transparent.setChecked(s.get("transparent_ui", False))
        mode = s.get("color_mode", "dark")
        self.combo_mode.setCurrentIndex(1 if mode == "light" else 0)
        tid = s.get("theme_id", "teal")
        for i in range(self.combo_theme.count()):
            if self.combo_theme.itemData(i) == tid:
                self.combo_theme.setCurrentIndex(i)
                break
        vid = s.get("visual_style", "classic")
        for i in range(self.combo_visual.count()):
            if self.combo_visual.itemData(i) == vid:
                self.combo_visual.setCurrentIndex(i)
                break
        custom = get_config().get("custom_background_path", "")
        if custom and os.path.exists(custom):
            self._custom_bg_path = custom
            self._selected_bg_id = "__custom__"
        else:
            self._custom_bg_path = None
            if custom:
                save_config({"custom_background_path": ""})
            self._selected_bg_id = s.get("background_id", "sakura_sky")
        self._rebuild_bg_thumbnails()
        self._update_custom_bg_label()

    def _save_settings_from_ui(self):
        bg_id = getattr(self, "_selected_bg_id", "sakura_sky")
        payload = {
            "auto_terminal": self.chk_auto_term.isChecked(),
            "auto_file_manager": self.chk_auto_fm.isChecked(),
            "auto_rdp": self.chk_auto_rdp.isChecked(),
            "color_mode": self.combo_mode.currentData(),
            "theme_id": self.combo_theme.currentData(),
            "visual_style": self.combo_visual.currentData(),
            "fast_ui": self.chk_fast_ui.isChecked(),
            "transparent_ui": self.chk_transparent.isChecked(),
            "start_with_windows": (
                self.chk_startup_win.isChecked()
                if hasattr(self, "chk_startup_win")
                else self._settings.get("start_with_windows", False)
            ),
            "language": (
                self.combo_language.currentData()
                if hasattr(self, "combo_language")
                else self._settings.get("language", LANG_VI)
            ),
        }
        if bg_id != "__custom__":
            payload["background_id"] = bg_id
        save_settings(payload)

    def _sync_startup_with_settings(self):
        if not sys.platform.startswith("win") or not hasattr(self, "chk_startup_win"):
            return
        want = self._settings.get("start_with_windows", False)
        have = is_startup_enabled()
        if want != have:
            set_startup_enabled(want)

    def _on_startup_windows_changed(self):
        if not sys.platform.startswith("win"):
            return
        enabled = self.chk_startup_win.isChecked()
        ok, err = set_startup_enabled(enabled)
        if not ok:
            self.chk_startup_win.blockSignals(True)
            self.chk_startup_win.setChecked(not enabled)
            self.chk_startup_win.blockSignals(False)
            QMessageBox.warning(
                self, tr("startup_win_title"), err or tr("startup_win_fail"),
            )
            return
        save_settings({"start_with_windows": enabled})
        self._settings["start_with_windows"] = enabled
        self.log_info(
            "Đã bật khởi động cùng Windows."
            if enabled
            else "Đã tắt khởi động cùng Windows."
        )

    def _on_appearance_changed(self):
        was_transparent = self._settings.get("transparent_ui", False)
        self.apply_appearance()
        self._save_settings_from_ui()
        now_transparent = self.chk_transparent.isChecked()
        if was_transparent != now_transparent:
            state = "bật" if now_transparent else "tắt"
            self.log_info(f"Đã {state} nền trong suốt toàn app.")

    def _rebuild_bg_thumbnails(self):
        while self.bg_grid.count():
            item = self.bg_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._bg_thumb_buttons.clear()
        selected = getattr(self, "_selected_bg_id", "sakura_sky")
        for i, bg in enumerate(list_available_backgrounds()):
            btn = QPushButton()
            btn.setObjectName("bgThumb")
            btn.setCheckable(True)
            btn.setFixedSize(120, 72)
            btn.setToolTip(bg["name"])
            btn.setProperty("bg_id", bg["id"])
            pm = QPixmap(bg["path"]).scaled(
                116, 68,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            btn.setIcon(QIcon(pm))
            btn.setIconSize(pm.size())
            btn.setChecked(
                bg["id"] == selected and selected != "__custom__"
            )
            btn.clicked.connect(lambda checked, bid=bg["id"]: self._select_background(bid))
            self.bg_grid.addWidget(btn, i // 4, i % 4)
            self._bg_thumb_buttons[bg["id"]] = btn

    def _update_custom_bg_label(self):
        if not hasattr(self, "lbl_custom_bg"):
            return
        path = getattr(self, "_custom_bg_path", None)
        if path and os.path.exists(path):
            self.lbl_custom_bg.setText(
                tr("custom_bg_using", name=os.path.basename(path))
            )
        else:
            self.lbl_custom_bg.setText("")

    def _pick_custom_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("pick_bg_title"),
            "",
            tr("pick_bg_filter"),
        )
        if not path:
            return
        save_config({"custom_background_path": path})
        self._custom_bg_path = path
        self._selected_bg_id = "__custom__"
        for btn in self._bg_thumb_buttons.values():
            btn.setChecked(False)
        self._update_custom_bg_label()
        self._on_appearance_changed()
        self.log_info(f"Đã đặt hình nền tùy chỉnh: {os.path.basename(path)}")

    def _select_background(self, bg_id):
        self._selected_bg_id = bg_id
        self._custom_bg_path = None
        save_config({"custom_background_path": ""})
        for bid, btn in self._bg_thumb_buttons.items():
            btn.setChecked(bid == bg_id)
        self._update_custom_bg_label()
        self._on_appearance_changed()
        self.log_info(f"Đã đổi hình nền: {bg_id}")

    def _resolve_active_background(self):
        custom = get_config().get("custom_background_path") or getattr(
            self, "_custom_bg_path", None
        )
        if custom and os.path.exists(custom):
            return custom
        if custom:
            save_config({"custom_background_path": ""})
            self._custom_bg_path = None
            self._update_custom_bg_label()
        bg_id = getattr(self, "_selected_bg_id", "sakura_sky")
        if bg_id == "__custom__":
            bg_id = self._settings.get("background_id", "sakura_sky")
        return resolve_background(bg_id)

    def _refresh_nav_icons(self):
        p = PALETTES.get(
            self.combo_theme.currentData() or self._settings.get("theme_id", "teal"),
            PALETTES["teal"],
        )
        nav_text = "#64748b" if self.combo_mode.currentData() == "light" else "#71717a"
        for i, btn in enumerate(self._nav_btns):
            if i >= len(self._nav_icon_ids):
                break
            color = p["accent"] if btn.isChecked() else nav_text
            btn.setIcon(themed_icon(self._nav_icon_ids[i], color, 26))

    def apply_appearance(self):
        theme_id = self.combo_theme.currentData() or "teal"
        mode = self.combo_mode.currentData() or "dark"
        visual_style = self.combo_visual.currentData() or "classic"
        light = mode == "light"
        transparent = self.chk_transparent.isChecked()
        overlay_base = float(self._settings.get("bg_overlay", 0.45))

        if visual_style in ("glass", "frosted"):
            transparent = True
        if transparent:
            overlay_base = 0.08 if light else 0.12
        elif self.chk_fast_ui.isChecked():
            overlay_base = min(overlay_base + 0.08, 0.75)

        ss, overlay = build_stylesheet(
            theme_id,
            mode,
            overlay_base,
            transparent=transparent,
            visual_style=visual_style,
        )
        self.setStyleSheet(ss)
        self._refresh_nav_icons()

        popup_ss = combo_popup_stylesheet(theme_id, mode)
        for combo in (
            getattr(self, "combo_mode", None),
            getattr(self, "combo_theme", None),
            getattr(self, "combo_visual", None),
            getattr(self, "combo_profile", None),
        ):
            if combo is not None:
                view = combo.view()
                if view is not None:
                    view.setStyleSheet(popup_ss)

        p = PALETTES.get(theme_id, PALETTES["teal"])
        bars = getattr(self, "_about_music_bars", None)
        if bars is not None:
            bars.set_accent(p["accent"])
        self._btn_login_style = login_button_style(mode, p["accent"], p["accent2"])
        if not self.is_logged_in:
            self.btn_action.setStyleSheet(self._btn_login_style)

        log_fg = "#64748b" if light else "#a1a1aa"
        log_text = "#334155" if light else "#d4d4d8"
        if transparent:
            log_bg = "rgba(255,255,255,0.48)" if light else "rgba(9,9,11,0.48)"
            log_border = "rgba(255,255,255,0.35)" if light else "rgba(255,255,255,0.15)"
        else:
            log_bg = "rgba(255,255,255,0.9)" if light else "rgba(24,24,27,0.88)"
            log_border = "rgba(148,163,184,0.6)" if light else "rgba(63,63,70,0.7)"
        self.txt_log.setStyleSheet(f"""
            QTextEdit {{
                background-color: {log_bg}; color: {log_fg};
                border: 1px solid {log_border}; border-radius: 14px;
                font-family: Consolas, monospace; font-size: 11px; padding: 10px;
            }}
        """)

        bg_path = self._resolve_active_background()
        self._bg.set_background(bg_path)
        self._bg.set_overlay(overlay, light=light)

        info_color = "#2dd4bf" if not light else p["accent2"]
        self._log_info_color = info_color
        self._log_text_color = log_text
        self._log_time_color = "#94a3b8" if light else "#52525b"

    def _refresh_profiles(self):
        self.combo_profile.blockSignals(True)
        self.combo_profile.clear()
        self.combo_profile.addItem(tr("combo_profile_empty"), None)
        for p in list_profiles():
            self.combo_profile.addItem(p["name"], p)
        self.combo_profile.blockSignals(False)

    def _refresh_history_list(self):
        self.list_history.clear()
        for h in self._session_history[:20]:
            icon = "✓" if h.get("success") else "✗"
            self.list_history.addItem(
                f"{icon} {h['user']}@{h['host']}:{h['port']}  — {h['time']}"
            )

    def _default_profile_name(self):
        self._flush_connect_form_from_widgets()
        host = self._connect_form["host"].strip()
        port = self._connect_form["port"].strip() or "22"
        user = self._connect_form["user"].strip()
        if user and host:
            return f"{user}@{host}:{port}"
        if host:
            return f"{host}:{port}"
        return ""

    def _select_profile_by_name(self, name):
        for i in range(self.combo_profile.count()):
            data = self.combo_profile.itemData(i)
            if data and data.get("name") == name:
                self.combo_profile.blockSignals(True)
                self.combo_profile.setCurrentIndex(i)
                self.combo_profile.blockSignals(False)
                return True
        return False

    def _connect_port_value(self):
        self._flush_connect_form_from_widgets()
        port_text = self._connect_form["port"].strip()
        if not port_text:
            return 22
        try:
            return int(port_text)
        except ValueError:
            return 22

    def _on_profile_activated(self, index):
        """Chỉ tải profile khi user chọn từ dropdown — không đè khi đang gõ port/pass."""
        if index <= 0:
            return
        self._load_profile()

    def _load_profile(self):
        p = self.combo_profile.currentData()
        if not p:
            return
        refreshed = refresh_profile_entry(p, get_default_dns_host())
        self._connect_form["host"] = refreshed.get("host", "")
        self._connect_form["dns"] = refreshed.get("dns_host", "")
        if is_hostname(self._connect_form["host"]) and not self._connect_form["dns"]:
            self._connect_form["dns"] = self._connect_form["host"]
        self._connect_form["port"] = refreshed.get("port", "22")
        self._connect_form["user"] = refreshed.get("user", "")
        self._connect_form["key"] = refreshed.get("key_path", "")
        info, _ = self._prepare_connect_target(require_host=False)
        if info and info.get("resolved_ip"):
            self._connect_form["host"] = info["resolved_ip"]
        self._restore_connect_form_fields()
        self.log_info(f"Đã tải profile: {p.get('name')}")

    def _update_connect_button_label(self):
        if self.is_logged_in or not hasattr(self, "btn_action"):
            return
        port = self._effective_connect_port()
        if port == RDP_PORT:
            self.btn_action.setText(tr("btn_connect_rdp"))
            if hasattr(self, "txt_host"):
                self.txt_host.setPlaceholderText(tr("placeholder_host_rdp"))
            if hasattr(self, "txt_dns"):
                self.txt_dns.setPlaceholderText(tr("placeholder_dns_rdp"))
        elif port == 22:
            self.btn_action.setText(tr("btn_connect_ssh"))
            if hasattr(self, "txt_host"):
                self.txt_host.setPlaceholderText(tr("placeholder_host"))
            if hasattr(self, "txt_dns"):
                self.txt_dns.setPlaceholderText(tr("placeholder_dns"))
        else:
            self.btn_action.setText(tr("btn_connect_ssh"))
            if hasattr(self, "txt_host"):
                self.txt_host.setPlaceholderText(tr("placeholder_host"))
            if hasattr(self, "txt_dns"):
                self.txt_dns.setPlaceholderText(tr("placeholder_dns"))

    def _load_from_history(self, item):
        text = item.text()
        try:
            part = text.split(" ")[1]
            user, rest = part.split("@")
            host, port = rest.rsplit(":", 1)
            self._connect_form["user"] = user
            self._connect_form["host"] = host
            self._connect_form["port"] = port
            self._restore_connect_form_fields()
            self._switch_page(0)
        except Exception:
            pass

    def _save_current_profile(self):
        self._flush_connect_form_from_widgets()
        host = self._connect_form["host"].strip()
        dns_host = self._connect_form.get("dns", "").strip()
        if not host and not dns_host:
            QMessageBox.warning(
                self, tr("profile_title"), tr("warn_profile_host"),
            )
            return
        info, err = self._prepare_connect_target(require_host=False)
        if err:
            QMessageBox.warning(self, tr("profile_title"), err)
            return
        if info:
            host = info.get("resolved_ip") or host
            dns_host = info.get("dns_host") or dns_host
        default_name = self._default_profile_name()
        name, ok = QInputDialog.getText(
            self,
            tr("save_profile_title"),
            tr("save_profile_prompt"),
            text=default_name,
        )
        if not ok:
            return
        name = (name.strip() or default_name).strip()
        if not name:
            QMessageBox.warning(
                self, tr("profile_title"), tr("warn_profile_host"),
            )
            return
        port = self._connect_form["port"].strip() or "22"
        user = self._connect_form["user"].strip()
        key_path = self._connect_form["key"].strip()
        try:
            save_profile(name, host, port, user, key_path=key_path, dns_host=dns_host)
        except OSError as e:
            QMessageBox.critical(
                self,
                tr("profile_title"),
                tr("profile_save_fail", msg=str(e)),
            )
            self.log_info(tr("profile_save_fail", msg=str(e)))
            return
        self._refresh_profiles()
        self._select_profile_by_name(name)
        self.log_info(tr("profile_saved", name=name))

    def _delete_current_profile(self):
        p = self.combo_profile.currentData()
        if not p:
            QMessageBox.information(
                self, tr("profile_title"), tr("profile_select_delete"),
            )
            return
        delete_profile(p["name"])
        self._refresh_profiles()
        self.log_info(f"Đã xóa profile '{p['name']}'")

    def _browse_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("pick_key_title"), "", "All (*)",
        )
        if path:
            self.txt_key.setText(path)

    def ping_host(self):
        info, err = self._prepare_connect_target()
        if err:
            QMessageBox.warning(self, tr("warn_title"), err)
            return
        host = validate_ssh_host(info["connect_host"])
        port_text = self._connect_form["port"].strip() or "22"
        try:
            port = validate_ssh_port(port_text)
        except ValueError as e:
            QMessageBox.warning(self, tr("warn_title"), str(e))
            return
        self._persist_dns_to_profile(info)
        self.log_info(f"Ping TCP {host}:{port}...")
        ok, msg = self.ssh_manager.test_tcp(host, port)
        self.log_info(msg if ok else f"Ping thất bại: {msg}")
        if ok:
            QMessageBox.information(
                self, tr("ping_title"), tr("ping_ok", host=host, port=port),
            )
        else:
            QMessageBox.warning(
                self, tr("ping_title"), tr("ping_fail", msg=msg),
            )

    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("export_log_title"), "pettie-session.log", "Log (*.log);;All (*)",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.txt_log.toPlainText())
            self.log_info(f"Đã xuất log → {path}")

    def copy_log(self):
        QGuiApplication.clipboard().setText(self.txt_log.toPlainText())
        self.log_info("Đã copy log vào clipboard.")

    def _require_login(self):
        if not self.is_logged_in:
            QMessageBox.warning(self, tr("warn_title"), tr("warn_connect_first"))
            return False
        return True

    def _prepare_taskbar_window(self, win):
        """Tách cửa sổ con khỏi parent để hiện nút riêng trên taskbar Windows."""
        win.setParent(None)
        win.setWindowFlag(Qt.WindowType.Window, True)
        win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        icon = self.windowIcon()
        if not icon.isNull():
            win.setWindowIcon(icon)

    def _track_window(self, win):
        self._prepare_taskbar_window(win)

        def _on_destroyed():
            if win in self._child_windows:
                self._child_windows.remove(win)

        win.destroyed.connect(_on_destroyed)
        self._child_windows.append(win)
        win.show()
        win.raise_()
        win.activateWindow()

    def open_remote_desktop(self):
        """RDP trực tiếp — giống Windows Remote Desktop (mstsc)."""
        if self.is_logged_in:
            host = self._connect_form.get("dns", "").strip() or self._session_host()
            user = self._session_user()
            password = self.ssh_manager.get_session_password()
            if not password:
                dlg = RemoteDesktopDialog(
                    self.ssh_manager,
                    self._session_host(),
                    self._session_user(),
                    password="",
                    parent=None,
                )
                self._prepare_taskbar_window(dlg)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self.log_info("Remote Desktop: đã khởi chạy client RDP.")
                return
            info, err = self._prepare_connect_target(require_resolve=False)
            if err:
                QMessageBox.warning(self, tr("warn_title"), err)
                return
            rdp_host = info.get("resolved_ip") or info.get("connect_host") or host
            dns_host = info.get("dns_host") or self._connect_form.get("dns", "").strip()
            display = dns_host or rdp_host
            self.log_info(f"Đang mở Remote Desktop → {display}:{RDP_PORT}...")
            ok, msg = connect_direct_rdp(
                rdp_host, user, password, port=RDP_PORT, parent=self, dns_host=dns_host,
            )
            if ok:
                self.log_info(msg)
            else:
                QMessageBox.warning(
                    self, tr("rdp_connect_fail"), msg or tr("rdp_connect_fail"),
                )
            return

        self._flush_connect_form_from_widgets()
        user = self._connect_form["user"].strip()
        password = self._connect_form["pass"]
        port_text = self._connect_form["port"].strip()
        info, err = self._prepare_connect_target(require_resolve=False)
        if err:
            QMessageBox.warning(self, tr("warn_title"), err)
            return
        host = info.get("resolved_ip") or info.get("connect_host", "")
        dns_host = info.get("dns_host") or self._connect_form.get("dns", "").strip()
        self._persist_dns_to_profile(info)
        try:
            port = int(port_text) if port_text else RDP_PORT
        except ValueError:
            port = RDP_PORT
        if not host:
            QMessageBox.warning(self, tr("warn_title"), tr("warn_enter_host"))
            return
        if not user:
            QMessageBox.warning(self, tr("warn_title"), tr("warn_enter_user"))
            return
        if not password:
            QMessageBox.warning(self, tr("warn_title"), tr("warn_enter_pass"))
            return
        if port != RDP_PORT:
            QMessageBox.information(
                self,
                tr("tool_rdp"),
                tr("rdp_use_port_3389"),
            )
            return
        try:
            rdp_user = validate_windows_logon(user)
        except ValueError as e:
            QMessageBox.warning(self, tr("warn_title"), str(e))
            return
        self._connect_rdp_direct(host, port, rdp_user, password, dns_host=dns_host)

    def open_system_info(self):
        if not self._require_login():
            return
        w = SystemInfoWindow(self.ssh_manager, self._session_host())
        self._track_window(w)
        self.log_info("Đã mở System Info.")

    def open_port_forward(self):
        if not self._require_login():
            return
        w = PortForwardWindow(self.ssh_manager)
        self._track_window(w)
        self.log_info("Đã mở Port Forwarding.")

    def show_fingerprint(self):
        if not self._require_login():
            return
        fp = self.ssh_manager.get_host_key_fingerprint()
        if fp:
            QMessageBox.information(
                self, tr("host_key_title"), tr("host_key_body", fp=fp),
            )
            self.log_info(f"Host key: SHA256:{fp[:48]}...")
        else:
            QMessageBox.warning(self, tr("host_key_title"), tr("host_key_fail"))

    def log_info(self, message):
        from html import escape
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        ic = getattr(self, "_log_info_color", "#2dd4bf")
        tc = getattr(self, "_log_time_color", "#52525b")
        mc = getattr(self, "_log_text_color", "#d4d4d8")
        safe_msg = escape(str(message))
        self.txt_log.append(
            f"<span style='color:{ic};'>[INFO]</span> "
            f"<span style='color:{tc};'>{now}</span> "
            f"<span style='color:{mc};'>{safe_msg}</span>"
        )

    def _set_connect_form_enabled(self, enabled):
        for w in (
            self.txt_host, self.txt_dns, self.txt_port, self.txt_user, self.txt_pass,
            self.txt_key, self.btn_action,
        ):
            w.setEnabled(enabled)

    def _begin_connect_progress(self, host, port):
        self._connect_progress = QProgressDialog(
            tr("connecting_body", host=host, port=port),
            None,
            0,
            0,
            self,
        )
        self._connect_progress.setWindowTitle(tr("connecting_title"))
        self._connect_progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._connect_progress.setMinimumDuration(0)
        self._connect_progress.setCancelButton(None)
        self._connect_progress.setRange(0, 0)
        self._connect_progress.show()
        QApplication.processEvents()

    def _end_connect_progress(self):
        if self._connect_progress:
            self._connect_progress.close()
            self._connect_progress = None

    def _start_ssh_connect(self, host, port, user, password, key_path):
        if self._connect_worker and self._connect_worker.isRunning():
            return
        self._pending_connect = {
            "host": host,
            "port": port,
            "user": user,
        }
        self._save_settings_from_ui()
        self.log_info("Initiating handshake sequence.")
        self.log_info(f"Connecting to encrypted tunnel {host}:{port}...")
        self.lbl_status.setText(tr("status_connecting"))
        self.lbl_status.setStyleSheet(
            "color: #fbbf24; background-color: #422006;"
            " border-radius: 12px; padding: 6px;"
        )
        self._set_connect_form_enabled(False)
        self._begin_connect_progress(host, port)
        worker = _SSHConnectWorker(
            self.ssh_manager, host, port, user, password, key_path,
            self._connect_ui_bridge,
        )
        worker.connect_result.connect(
            self._on_ssh_connect_finished,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(worker.deleteLater)
        self._connect_worker = worker
        worker.start()

    def _on_ssh_connect_finished(self, success, message):
        if self._connect_worker and not self._connect_worker.isRunning():
            self._connect_worker = None
        self._end_connect_progress()
        self._set_connect_form_enabled(True)
        pending = self._pending_connect or {}
        host = pending.get("host", "")
        port = pending.get("port", 22)
        user = pending.get("user", "")
        self._pending_connect = None

        if not success:
            self._set_connected_ui(False)
            self.log_info(f"Handshake aborted. {message}")
            QMessageBox.warning(
                self,
                tr("connect_failed_title"),
                message or f"Không kết nối được tới {host}.",
            )
            return

        self.is_logged_in = True
        self.txt_pass.clear()
        self._connect_form["pass"] = ""
        self._session_history.insert(0, {
            "host": host,
            "port": str(port),
            "user": user,
            "success": True,
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self._session_history = self._session_history[:20]
        self._refresh_history_list()

        self._enter_workspace_after_connect()
        self.log_info("Tunnel secure. Authentication completed successfully.")
        self.log_info(f"Máy bạn: {local_os_display_name(self._local_os)}")
        self._sync_dns_from_server()
        if self.ssh_manager.remote_os:
            self.log_info(
                f"Máy chủ: {format_os_display(self.ssh_manager.remote_os)}"
            )
        else:
            self.log_info("Đang nhận diện hệ điều hành máy chủ…")
        fp = self.ssh_manager.get_host_key_fingerprint()
        if fp:
            self.log_info(f"Host key SHA256:{fp[:40]}...")

        if self.chk_auto_term.isChecked():
            self.open_terminal_action()
        if self.chk_auto_fm.isChecked():
            self.open_sftp_action()
        if self.chk_auto_rdp.isChecked():
            self.open_remote_desktop()

        QMessageBox.information(
            self, tr("success_title"), tr("success_connected"),
        )

    def _connect_rdp_direct(self, host, port, user, password, dns_host=""):
        if not self._ensure_freerdp_for_rdp():
            return
        display = dns_host or host
        self.log_info(f"Đang mở Remote Desktop → {display}:{port}...")
        ok, msg = connect_direct_rdp(
            host, user, password, port=port, parent=self, dns_host=dns_host,
        )
        if ok:
            self._session_history.insert(0, {
                "host": host,
                "port": str(port),
                "user": user,
                "success": True,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            self._session_history = self._session_history[:20]
            self._refresh_history_list()
            self.log_info(msg)
        else:
            self._session_history.insert(0, {
                "host": host,
                "port": str(port),
                "user": user,
                "success": False,
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            self._session_history = self._session_history[:20]
            self._refresh_history_list()
            self.log_info(f"RDP: {msg}")
            QMessageBox.warning(
                self,
                tr("rdp_connect_fail"),
                msg or tr("rdp_connect_fail"),
            )

    def handle_action(self):
        """Kết nối SSH, RDP (port 3389) hoặc ngắt kết nối."""
        if not self.is_logged_in:
            focused = QApplication.focusWidget()
            if focused in self._connect_field_map.values():
                self._capture_connect_field_by_widget(focused)
            self._flush_connect_form_from_widgets()
            port_text = self._connect_form["port"].strip()
            user = self._connect_form["user"].strip()
            password = self._connect_form["pass"]

            info, err = self._prepare_connect_target(
                require_resolve=(self._effective_connect_port(port_text) != RDP_PORT),
            )
            if err:
                QMessageBox.warning(self, tr("warn_title"), err)
                return

            if not user:
                QMessageBox.warning(self, tr("warn_title"), tr("warn_enter_user"))
                return
            if not password:
                QMessageBox.warning(self, tr("warn_title"), tr("warn_enter_pass"))
                return
            try:
                port = validate_ssh_port(
                    port_text if port_text else self._default_connect_port()
                )
            except ValueError as e:
                QMessageBox.warning(self, tr("warn_title"), str(e))
                return

            self._persist_dns_to_profile(info)

            if port == RDP_PORT:
                try:
                    user = validate_windows_logon(user)
                except ValueError as e:
                    QMessageBox.warning(self, tr("warn_title"), str(e))
                    return
                rdp_host = info.get("resolved_ip") or info.get("connect_host", "")
                dns_host = info.get("dns_host") or self._connect_form.get("dns", "").strip()
                if not rdp_host:
                    QMessageBox.warning(self, tr("warn_title"), tr("warn_enter_host"))
                    return
                self._connect_rdp_direct(
                    rdp_host, port, user, password, dns_host=dns_host,
                )
                return

            try:
                host = validate_ssh_host(info["connect_host"])
                user = validate_ssh_user(user)
            except ValueError as e:
                QMessageBox.warning(self, tr("warn_title"), str(e))
                return

            key_path = self.txt_key.text().strip() or None
            if key_path:
                try:
                    key_path = validate_ssh_key_path(key_path)
                except ValueError as e:
                    QMessageBox.warning(self, tr("warn_title"), str(e))
                    return
            self._start_ssh_connect(host, port, user, password, key_path)
        else:
            self._disconnect_session()

    def open_sftp_action(self):
        """Mở File Manager SFTP tích hợp (hoạt động với Windows & Linux remote)."""
        if not self.is_logged_in:
            QMessageBox.warning(self, tr("warn_title"), tr("warn_login_ssh"))
            return

        host = self._session_host()
        user = self._session_user()
        remote_os = self.ssh_manager.remote_os or "unknown"

        try:
            if self._fm_window and self._fm_window.isVisible():
                self._fm_window.raise_()
                self._fm_window.activateWindow()
                self.log_info("File Manager đã mở — đưa lên trước.")
                return

            self._fm_window = SftpFileManagerWindow(
                self.ssh_manager, host, user, remote_os,
            )
            self._prepare_taskbar_window(self._fm_window)
            self._fm_window.destroyed.connect(
                lambda: setattr(self, "_fm_window", None)
            )
            self._fm_window.show()
            self._fm_window.raise_()
            self._fm_window.activateWindow()
            self.log_info(f"Đã mở File Manager SFTP · {remote_os}.")
        except Exception as e:
            self.log_info(f"❌ Không thể mở File Manager: {e}")
            QMessageBox.warning(self, tr("error_title"), f"Không thể mở Trình quản lý file: {e}")

    def open_terminal_action(self):
        """Mở Terminal gốc tự động SSH — argv tách biệt, không qua shell (chống injection)."""
        if not self._require_login():
            return
        host = self._session_host()
        port = self.ssh_manager._last_port or self.txt_port.text().strip() or "22"
        user = self._session_user()

        try:
            argv = ssh_argv(user, host, port)
        except ValueError as e:
            QMessageBox.warning(self, tr("warn_title"), str(e))
            return

        self.log_info("Đang khởi tạo cửa sổ Terminal hệ thống độc lập...")
        ok, msg = launch_system_terminal(argv)
        if ok:
            self.log_info(f"Đã mở terminal hệ thống ({msg}).")
        else:
            self.log_info(f"❌ Lỗi mở Terminal: {msg}")
            QMessageBox.warning(self, tr("error_title"), msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if os.path.isfile(APP_LOGO):
        app.setWindowIcon(QIcon(APP_LOGO))

    splash = StartupSplashScreen(logo_path=APP_LOGO if os.path.isfile(APP_LOGO) else None)
    splash.start()

    main_window = None

    def _build_main_window():
        global main_window
        main_window = PettieSSHClient()
        app.aboutToQuit.connect(main_window._wipe_sensitive_data)
        splash.mark_ready()

    def _show_main_window():
        splash.close()
        if main_window:
            main_window.show()

    splash.finished.connect(_show_main_window)
    QTimer.singleShot(80, _build_main_window)

    sys.exit(app.exec())