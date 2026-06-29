"""Đa ngôn ngữ — tiếng Việt (vi) và English (en)."""

LANG_VI = "vi"
LANG_EN = "en"
SUPPORTED_LANGS = (LANG_VI, LANG_EN)

_current_lang = LANG_VI

_STRINGS: dict[str, dict[str, str]] = {
    "vi": {
        "nav_connect": "Kết nối",
        "nav_tools": "Công cụ",
        "nav_settings": "Cài đặt",
        "nav_about": "About",
        "connect_setup": "Thiết lập kết nối",
        "welcome_msg": "Chào mừng đến với Pettie SSH Client",
        "field_host": "Host / IP",
        "field_server": "Server",
        "field_dns_host": "DNS / Hostname",
        "field_rdp_domain": "Domain",
        "field_port": "Port",
        "field_protocol": "Loại kết nối",
        "protocol_rdp": "Remote Desktop (RDP)",
        "protocol_ssh": "SSH",
        "field_username": "Username",
        "field_password": "Password",
        "field_ssh_key": "SSH Key tuỳ chọn",
        "field_profile": "Profile",
        "placeholder_host": "VD: 192.168.0.1 hoặc example.com",
        "placeholder_server_rdp": "VD: 192.168.0.1 hoặc example.com",
        "placeholder_dns": "VD: myserver.example.com (DDNS)",
        "placeholder_rdp_domain": "Trống = tài khoản local Windows",
        "placeholder_host_rdp": "Tùy chọn — để trống nếu đã nhập domain bên dưới",
        "placeholder_dns_rdp": "VD: myserver.example.com (máy tính remote)",
        "placeholder_port": "VD: 3389 (Remote) hoặc 22 (SSH)",
        "placeholder_user": "VD: Administrator",
        "chk_hide_pass": "Ẩn MK",
        "placeholder_pass": "Chỉ dùng khi kết nối — xóa sau khi đăng nhập",
        "placeholder_key": "Đường dẫn file id_rsa...",
        "btn_save_profile": "Lưu profile",
        "btn_delete": "Xóa",
        "btn_ping_host": "Ping host",
        "btn_connect_ssh": "  Kết nối SSH  ",
        "btn_connect_rdp": "  Connect  ",
        "rdp_connect_hint": (
            "Remote Desktop (RDP) — giống Remmina: nhập Server, Username, "
            "Password, Domain (nếu có) rồi bấm Connect."
        ),
        "btn_disconnect": "  Ngắt kết nối  ",
        "btn_exit": "Thoát",
        "combo_profile_empty": "— Chọn profile —",
        "workspace_title": "Bàn làm việc",
        "session_not_connected": "Chưa kết nối",
        "session_login_hint": "Chưa kết nối — đăng nhập ở tab Kết nối",
        "session_your_machine": "Máy bạn",
        "session_remote_server": "Máy chủ",
        "session_detecting": "đang nhận diện…",
        "session_not_connected_local": "Chưa kết nối  ·  Máy bạn: {local}",
        "session_connected_fmt": "{user}@{host}  ·  Máy bạn: {local}  ·  Máy chủ: {remote}",
        "session_rdp_fmt": "Remote Desktop · {user}@{host}  ·  Máy bạn: {local}",
        "warn_already_remote": (
            "Bạn đang dùng Remote Desktop tới máy này.\n\n"
            "Không cần mở thêm phiên Remote Desktop."
        ),
        "warn_rdp_ok_ssh_fail": (
            "Remote Desktop đã mở, nhưng SSH nền (cổng 22) không kết nối được.\n\n"
            "Terminal, SFTP và các công cụ khác cần SSH.\n\n{detail}"
        ),
        "warn_ssh_for_tools": (
            "Phiên Remote Desktop đang mở.\n\n"
            "Terminal, SFTP và các công cụ khác cần SSH (cổng 22) trên máy chủ.\n"
            "Kiểm tra OpenSSH Server đã bật và user/password đúng."
        ),
        "session_ssh_pending": "SSH nền chưa kết nối",
        "tool_terminal": "Terminal hệ thống",
        "tool_terminal_hint_win": "Mở CMD + SSH",
        "tool_terminal_hint_linux": "Mở Terminal hệ thống + SSH",
        "tool_sftp": "Pettie Transfer",
        "tool_sftp_desc": "Dual-pane SFTP",
        "tool_rdp": "Remote Desktop",
        "tool_rdp_desc": "Màn hình máy đích (port 3389)",
        "tool_sysinfo": "System Info",
        "tool_sysinfo_desc": "CPU, RAM, Disk, OS",
        "tool_portfwd": "Port Forward",
        "tool_portfwd_desc": "Tunnel cổng local/remote",
        "tool_hostkey": "Host Key",
        "tool_hostkey_desc": "SHA256 fingerprint",
        "settings_title": "Tùy chọn",
        "section_general": "Chung",
        "section_ui": "Giao diện",
        "section_background": "Hình nền",
        "section_perf": "Hiệu suất & tự động",
        "field_language": "Ngôn ngữ",
        "lang_vi": "🇻🇳  Tiếng Việt",
        "lang_en": "🇬🇧  English",
        "field_color_mode": "Chế độ màu",
        "color_dark": "🌙  Tối",
        "color_light": "☀  Sáng",
        "field_theme": "Theme màu",
        "field_visual": "Kiểu đồ họa",
        "visual_tooltip": "Liquid Glass, Neon, Minimal, Aurora… — đổi ngay không cần khởi động lại",
        "chk_transparent": "Nền trong suốt toàn app",
        "chk_transparent_tip": "Làm mờ panel thêm — kết hợp tốt với Liquid Glass / Frosted",
        "chk_smooth": "Chế độ mượt",
        "chk_auto_term": "Tự mở Terminal sau khi kết nối",
        "chk_auto_fm": "Tự mở Pettie Transfer sau khi kết nối",
        "chk_auto_rdp": "Tự mở Remote Desktop sau khi kết nối",
        "chk_startup_win": "Khởi động cùng Windows",
        "chk_startup_win_tip": "Chỉ khả dụng trên Windows",
        "btn_custom_bg": "Chọn hình nền tùy chỉnh từ máy tính…",
        "history_title": "Lịch sử kết nối",
        "btn_export_log": "Xuất session log ra file",
        "btn_copy_log": "Copy log",
        "custom_bg_using": "Đang dùng: {name}",
        "about_headline": "Pettie SSH Client 2.5 — Copyright © 2026 OASIS GROUP",
        "about_version_status": 'Trạng thái phiên bản: <a href="#">Hiện tại</a>',
        "about_group_app": "Ứng dụng",
        "about_app_desc": (
            "Pettie SSH Client — kết nối SSH, SFTP dual-pane, Remote Desktop, "
            "port forwarding và quản trị máy chủ từ xa."
        ),
        "about_version_build": "Phiên bản 2.5 · Build 2026",
        "about_group_features": "Tính năng",
        "about_features_desc": (
            "<b>Đã bao gồm:</b> Profiles, lịch sử, 7 theme tối/sáng, 8 hình nền, "
            "Pettie Transfer SFTP, RDP, port forwarding và system info."
        ),
        "about_group_dev": "Phát triển bởi",
        "about_dev_credit": "<b>Phát triển bởi Chery from with love</b>",
        "about_dev_oasis": "OASIS GROUP — mã nguồn mở phục vụ quản trị hệ thống từ xa.",
        "about_group_contact": "Liên hệ",
        "about_contact_hint": "Hỗ trợ, góp ý và báo lỗi qua email:",
        "status_offline": "● Offline",
        "status_online": "● Online",
        "status_connecting": "● Đang kết nối…",
        "log_ready": "Pettie SSH Client 2.5 — đầy đủ tính năng.",
        "log_ready_connect": "Sẵn sàng kết nối.",
        "log_dns_updated": "DNS cập nhật: {dns} → {ip}",
        "log_dns_sync_server": "Server báo DNS: {dns} → IP hiện tại {ip}",
        "log_dns_profiles_refreshed": "Đã cập nhật IP cho {count} profile theo DNS.",
        "dlg_trust_host_title": "Tin cậy host key?",
        "dlg_trust_host_body": (
            "Lần đầu kết nối tới {host}:{port}.\n\n"
            "SHA256 fingerprint:\n{fingerprint}\n\n"
            "Chỉ chấp nhận nếu bạn đã đối chiếu với máy chủ thật."
        ),
        "warn_title": "Cảnh báo",
        "warn_connect_first": "Vui lòng kết nối SSH trước!",
        "warn_login_ssh": "Vui lòng đăng nhập SSH trước!",
        "warn_enter_host": "Vui lòng nhập IP hoặc hostname.",
        "warn_enter_user": "Vui lòng nhập User.",
        "warn_enter_pass": "Vui lòng nhập Password!",
        "connect_failed_title": "Không kết nối được",
        "success_title": "Thành công",
        "success_connected": "Kết nối an toàn thiết lập thành công!",
        "profile_title": "Profile",
        "profile_select_delete": "Chọn profile cần xóa.",
        "save_profile_title": "Lưu profile",
        "save_profile_prompt": "Tên profile:",
        "warn_profile_host": "Nhập Host / IP trước khi lưu profile.",
        "profile_saved": "Đã lưu profile «{name}».",
        "profile_save_fail": "Không lưu được profile: {msg}",
        "rdp_connect_ok": (
            "Đang mở màn hình máy đích {host}:{port}.\n\n"
            "Mật khẩu đã gửi tự đăng nhập — không cần gõ lại trên Windows."
        ),
        "rdp_connect_fail": "Không kết nối RDP được.",
        "rdp_use_port_3389": (
            "Kết nối màn hình máy đích dùng port 3389.\n\n"
            "Nhập port 3389 rồi bấm «Kết nối Remote (RDP)» — không cần SSH."
        ),
        "freerdp_install_title": "Cài Remmina (Remote Desktop)",
        "freerdp_install_body": (
            "Để dùng Remote Desktop trên Linux, app cần Remmina.\n\n"
            "Bấm Yes để tự cài từ kho phần mềm (cần mật khẩu admin).\n"
            "Hoặc chạy một lệnh: bash install-linux.sh"
        ),
        "freerdp_install_rdp_body": (
            "Chưa có Remmina để mở màn hình remote.\n\n"
            "Cài ngay từ kho phần mềm? (cần quyền admin)"
        ),
        "freerdp_install_progress": "Đang cài Remmina — có thể hỏi mật khẩu hệ thống…",
        "freerdp_install_ok": "Đã cài Remmina — sẵn sàng dùng Remote Desktop.",
        "freerdp_install_fail": "Không cài được Remmina:\n{msg}",
        "freerdp_install_skipped": "Bỏ qua cài Remmina — Remote Desktop chưa dùng được.",
        "ping_title": "Ping",
        "ping_ok": "Host {host}:{port} phản hồi OK.",
        "ping_fail": "Không kết nối được: {msg}",
        "export_log_title": "Xuất log",
        "pick_key_title": "Chọn SSH private key",
        "pick_bg_title": "Chọn hình nền",
        "pick_bg_filter": "Ảnh (*.png *.jpg *.jpeg *.webp)",
        "connecting_title": "Đang kết nối",
        "connecting_body": "Đang kết nối tới {host}:{port}…\n(Thường xong trong 3–10 giây)",
        "host_key_title": "Host Key SHA256",
        "host_key_body": (
            "Fingerprint máy chủ:\n\nSHA256:{fp}\n\n"
            "So sánh khi kết nối lần đầu để tránh MITM."
        ),
        "host_key_fail": "Không lấy được fingerprint.",
        "startup_win_title": "Khởi động cùng Windows",
        "startup_win_fail": "Không cấu hình được.",
        "error_title": "Lỗi",
        "unknown_os": "Không rõ",
        "language_changed": "Đã đổi ngôn ngữ sang {lang}.",
    },
    "en": {
        "nav_connect": "Connect",
        "nav_tools": "Tools",
        "nav_settings": "Settings",
        "nav_about": "About",
        "connect_setup": "Connection setup",
        "welcome_msg": "Welcome to Pettie SSH Client",
        "field_host": "Host / IP",
        "field_server": "Server",
        "field_dns_host": "DNS / Hostname",
        "field_rdp_domain": "Domain",
        "field_port": "Port",
        "field_protocol": "Connection",
        "protocol_rdp": "Remote Desktop (RDP)",
        "protocol_ssh": "SSH",
        "field_username": "Username",
        "field_password": "Password",
        "field_ssh_key": "Optional SSH key",
        "field_profile": "Profile",
        "placeholder_host": "e.g. 192.168.0.1 or example.com",
        "placeholder_server_rdp": "e.g. 192.168.0.1 or example.com",
        "placeholder_dns": "e.g. myserver.example.com (DDNS)",
        "placeholder_rdp_domain": "Leave empty for local Windows account",
        "placeholder_host_rdp": "Optional — leave empty if domain is set below",
        "placeholder_dns_rdp": "e.g. myserver.example.com (remote computer)",
        "placeholder_port": "e.g. 3389 (Remote) or 22 (SSH)",
        "placeholder_user": "e.g. Administrator",
        "chk_hide_pass": "Hide",
        "placeholder_pass": "Used only for login — cleared after connect",
        "placeholder_key": "Path to id_rsa...",
        "btn_save_profile": "Save profile",
        "btn_delete": "Delete",
        "btn_ping_host": "Ping host",
        "btn_connect_ssh": "  Connect SSH  ",
        "btn_connect_rdp": "  Connect  ",
        "rdp_connect_hint": (
            "Remote Desktop (RDP) — like Remmina: enter Server, Username, "
            "Password, Domain (optional), then Connect."
        ),
        "btn_disconnect": "  Disconnect  ",
        "btn_exit": "Exit",
        "combo_profile_empty": "— Select profile —",
        "workspace_title": "Workspace",
        "session_not_connected": "Not connected",
        "session_login_hint": "Not connected — sign in on the Connect tab",
        "session_your_machine": "Your machine",
        "session_remote_server": "Server",
        "session_detecting": "detecting…",
        "session_not_connected_local": "Not connected  ·  Your machine: {local}",
        "session_connected_fmt": "{user}@{host}  ·  Your machine: {local}  ·  Server: {remote}",
        "session_rdp_fmt": "Remote Desktop · {user}@{host}  ·  Your machine: {local}",
        "warn_already_remote": (
            "You are already connected via Remote Desktop.\n\n"
            "No need to open another Remote Desktop session."
        ),
        "warn_rdp_ok_ssh_fail": (
            "Remote Desktop is open, but background SSH (port 22) failed.\n\n"
            "Terminal, SFTP and other tools require SSH.\n\n{detail}"
        ),
        "warn_ssh_for_tools": (
            "Remote Desktop session is active.\n\n"
            "Terminal, SFTP and other tools require SSH (port 22) on the server.\n"
            "Ensure OpenSSH Server is enabled with correct credentials."
        ),
        "session_ssh_pending": "background SSH not connected",
        "tool_terminal": "System terminal",
        "tool_terminal_hint_win": "Open CMD + SSH",
        "tool_terminal_hint_linux": "Open system terminal + SSH",
        "tool_sftp": "Pettie Transfer",
        "tool_sftp_desc": "Dual-pane SFTP",
        "tool_rdp": "Remote Desktop",
        "tool_rdp_desc": "Remote machine screen (port 3389)",
        "tool_sysinfo": "System Info",
        "tool_sysinfo_desc": "CPU, RAM, Disk, OS",
        "tool_portfwd": "Port Forward",
        "tool_portfwd_desc": "Local/remote port tunnel",
        "tool_hostkey": "Host Key",
        "tool_hostkey_desc": "SHA256 fingerprint",
        "settings_title": "Preferences",
        "section_general": "General",
        "section_ui": "Appearance",
        "section_background": "Background",
        "section_perf": "Performance & automation",
        "field_language": "Language",
        "lang_vi": "🇻🇳  Tiếng Việt",
        "lang_en": "🇬🇧  English",
        "field_color_mode": "Color mode",
        "color_dark": "🌙  Dark",
        "color_light": "☀  Light",
        "field_theme": "Color theme",
        "field_visual": "Visual style",
        "visual_tooltip": "Liquid Glass, Neon, Minimal, Aurora… — applies instantly",
        "chk_transparent": "Transparent app background",
        "chk_transparent_tip": "Extra panel blur — works well with Liquid Glass / Frosted",
        "chk_smooth": "Smooth mode",
        "chk_auto_term": "Open terminal after connect",
        "chk_auto_fm": "Open Pettie Transfer after connect",
        "chk_auto_rdp": "Open Remote Desktop after connect",
        "chk_startup_win": "Start with Windows",
        "chk_startup_win_tip": "Windows only",
        "btn_custom_bg": "Choose custom background from computer…",
        "history_title": "Connection history",
        "btn_export_log": "Export session log to file",
        "btn_copy_log": "Copy log",
        "custom_bg_using": "Using: {name}",
        "about_headline": "Pettie SSH Client 2.5 — Copyright © 2026 OASIS GROUP",
        "about_version_status": 'Version status: <a href="#">Current</a>',
        "about_group_app": "Application",
        "about_app_desc": (
            "Pettie SSH Client — SSH, dual-pane SFTP, Remote Desktop, "
            "port forwarding, and remote server administration."
        ),
        "about_version_build": "Version 2.5 · Build 2026",
        "about_group_features": "Features",
        "about_features_desc": (
            "<b>Included:</b> Profiles, history, 7 dark/light themes, 8 backgrounds, "
            "Pettie Transfer SFTP, RDP, port forwarding, and system info."
        ),
        "about_group_dev": "Developed by",
        "about_dev_credit": "<b>Developed by Chery from with love</b>",
        "about_dev_oasis": "OASIS GROUP — open source for remote system administration.",
        "about_group_contact": "Contact",
        "about_contact_hint": "Support, feedback, and bug reports via email:",
        "status_offline": "● Offline",
        "status_online": "● Online",
        "status_connecting": "● Connecting…",
        "log_ready": "Pettie SSH Client 2.5 — full feature set.",
        "log_ready_connect": "Ready to connect.",
        "log_dns_updated": "DNS updated: {dns} → {ip}",
        "log_dns_sync_server": "Server DNS: {dns} → current IP {ip}",
        "log_dns_profiles_refreshed": "Updated IP for {count} profile(s) from DNS.",
        "dlg_trust_host_title": "Trust host key?",
        "dlg_trust_host_body": (
            "First connection to {host}:{port}.\n\n"
            "SHA256 fingerprint:\n{fingerprint}\n\n"
            "Accept only if you verified this against the real server."
        ),
        "warn_title": "Warning",
        "warn_connect_first": "Please connect SSH first!",
        "warn_login_ssh": "Please sign in via SSH first!",
        "warn_enter_host": "Please enter an IP or hostname.",
        "warn_enter_user": "Please enter a username.",
        "warn_enter_pass": "Please enter a password!",
        "connect_failed_title": "Connection failed",
        "success_title": "Success",
        "success_connected": "Secure connection established successfully!",
        "profile_title": "Profile",
        "profile_select_delete": "Select a profile to delete.",
        "save_profile_title": "Save profile",
        "save_profile_prompt": "Profile name:",
        "warn_profile_host": "Enter Host / IP before saving a profile.",
        "profile_saved": "Saved profile «{name}».",
        "profile_save_fail": "Could not save profile: {msg}",
        "rdp_connect_ok": (
            "Opening remote screen {host}:{port}.\n\n"
            "Look for the «Pettie Remote Desktop» window — Alt+Tab if hidden."
        ),
        "rdp_connect_fail": "RDP connection failed.",
        "rdp_use_port_3389": (
            "Direct Remote Desktop uses port 3389.\n\n"
            "Enter port 3389 on the Connect tab and press «Connect Remote (RDP)» — no SSH required."
        ),
        "freerdp_install_title": "Install Remmina (Remote Desktop)",
        "freerdp_install_body": (
            "Remote Desktop on Linux requires Remmina.\n\n"
            "Click Yes to install from system packages (admin password).\n"
            "Or run one command: bash install-linux.sh"
        ),
        "freerdp_install_rdp_body": (
            "Remmina is not installed.\n\n"
            "Install now from system packages? (admin required)"
        ),
        "freerdp_install_progress": "Installing Remmina — you may be prompted for your password…",
        "freerdp_install_ok": "Remmina installed — Remote Desktop is ready.",
        "freerdp_install_fail": "Could not install Remmina:\n{msg}",
        "freerdp_install_skipped": "Skipped Remmina install — Remote Desktop unavailable.",
        "ping_title": "Ping",
        "ping_ok": "Host {host}:{port} responded OK.",
        "ping_fail": "Could not connect: {msg}",
        "export_log_title": "Export log",
        "pick_key_title": "Choose SSH private key",
        "pick_bg_title": "Choose background",
        "pick_bg_filter": "Images (*.png *.jpg *.jpeg *.webp)",
        "connecting_title": "Connecting",
        "connecting_body": "Connecting to {host}:{port}…\n(Usually finishes in 3–10 seconds)",
        "host_key_title": "Host Key SHA256",
        "host_key_body": (
            "Server fingerprint:\n\nSHA256:{fp}\n\n"
            "Verify on first connect to avoid MITM."
        ),
        "host_key_fail": "Could not get fingerprint.",
        "startup_win_title": "Start with Windows",
        "startup_win_fail": "Could not configure startup.",
        "error_title": "Error",
        "unknown_os": "Unknown",
        "language_changed": "Language changed to {lang}.",
    },
}


def init_language(lang: str | None = None) -> str:
    """Khởi tạo ngôn ngữ từ settings (mặc định vi)."""
    global _current_lang
    if lang in SUPPORTED_LANGS:
        _current_lang = lang
    else:
        _current_lang = LANG_VI
    return _current_lang


def get_language() -> str:
    return _current_lang


def set_language(lang: str) -> str:
    return init_language(lang)


def tr(key: str, **kwargs) -> str:
    table = _STRINGS.get(_current_lang) or _STRINGS[LANG_VI]
    text = table.get(key, _STRINGS[LANG_VI].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text


def language_display_name(lang: str | None = None) -> str:
    lang = lang or _current_lang
    return tr("lang_vi") if lang == LANG_VI else tr("lang_en")
