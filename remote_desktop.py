"""Remote Desktop — đăng nhập RDP tới đúng IP người dùng nhập."""

import base64
import os
import sys
import subprocess
import shutil
import tempfile
import threading
import time

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QMessageBox, QCheckBox, QFrame, QGridLayout,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette, QColor

from profile_store import get_settings, save_settings, secure_chmod
from dns_utils import prepare_connect_host, is_ipv4, resolve_ipv4
from security_utils import (
    validate_rdp_ipv4,
    validate_rdp_domain,
    validate_ssh_host,
    validate_ssh_port,
    validate_windows_logon,
)
from platform_utils import is_windows, is_macos, is_linux
from windows_cred import cred_write_generic, cred_delete_generic
from freerdp_bootstrap import (
    find_bundled_freerdp,
    bundled_env,
    run_install_freerdp,
    install_command_display,
    linux_install_hint,
    status_message as freerdp_status_message,
)

RDP_PORT = 3389

# xfreerdp = cửa sổ hiển thị màn hình remote (không bắt cài Remmina)
_LINUX_RDP_BINARIES = (
    "xfreerdp3",
    "xfreerdp",
    "wlfreerdp",
    "freerdp",
    "remmina",
    "krdc",
)

_BUNDLED_FREERDP_NAMES = ("xfreerdp3", "xfreerdp", "wlfreerdp", "freerdp")

_REMMINA_FLATPAK_IDS = (
    "org.remmina.Remmina",
    "com.remmina.Remmina",
)
_FREERDP_FLATPAK_IDS = (
    "com.freerdp.xfreerdp",
    "org.freerdp.xfreerdp",
)


def _parse_rdp_address(address):
    """Tách host và port từ địa chỉ dạng host:3389 hoặc [ipv6]:3389."""
    address = (address or "").strip()
    if address.startswith("["):
        if "]:" in address:
            host, port_s = address.split("]:", 1)
            return host + "]", int(port_s)
        return address, RDP_PORT
    if ":" in address:
        host, port_s = address.rsplit(":", 1)
        try:
            return host, int(port_s)
        except ValueError:
            pass
    return address, RDP_PORT


def _app_base_dirs():
    """Thư mục gốc app (source, PyInstaller, hoặc thư mục chứa file .exe)."""
    dirs = []
    if hasattr(sys, "_MEIPASS"):
        dirs.append(sys._MEIPASS)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    dirs.append(os.path.abspath(os.path.dirname(__file__)))
    dirs.append(os.path.abspath("."))
    seen = set()
    out = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _find_bundled_freerdp():
    """Client RDP đóng gói cùng Pettie (vendor/freerdp hoặc bin/ cạnh app)."""
    path, _lib = find_bundled_freerdp()
    if path:
        return os.path.basename(path), path
    return None, None


def _find_linux_rdp_client():
    """Tìm trình xem RDP — ưu tiên xfreerdp đóng gói / có sẵn trên hệ thống."""
    bundled = _find_bundled_freerdp()
    if bundled[1]:
        return bundled
    for name in _LINUX_RDP_BINARIES:
        path = shutil.which(name)
        if path:
            return name, path
    if shutil.which("flatpak"):
        for flatpak_id in _FREERDP_FLATPAK_IDS + _REMMINA_FLATPAK_IDS:
            try:
                r = subprocess.run(
                    ["flatpak", "info", flatpak_id],
                    capture_output=True,
                    timeout=5,
                )
                if r.returncode == 0:
                    return "flatpak:" + flatpak_id, flatpak_id
            except (OSError, subprocess.SubprocessError):
                pass
    return None, None


def linux_rdp_install_hint() -> str:
    return linux_install_hint()


def linux_rdp_client_available():
    """True nếu máy Linux có client RDP (xfreerdp / Remmina / Flatpak)."""
    if is_windows() or is_macos():
        return True
    return bool(_find_linux_rdp_client()[1])


def linux_rdp_status_message():
    """Thông báo trạng thái client RDP trên Linux."""
    if not is_linux():
        return ""
    return freerdp_status_message(_find_linux_rdp_client)


def ensure_linux_freerdp_installed() -> tuple[bool, str]:
    """Tự cài xfreerdp qua apt/dnf/pacman nếu chưa có. Trả về (ok, message)."""
    if not is_linux():
        return True, ""
    if linux_rdp_client_available():
        return True, ""
    return run_install_freerdp(use_pkexec=True)


def _rdp_install_hint():
    """Hướng dẫn cài / bật RDP theo OS đang chạy Pettie."""
    if is_windows():
        return (
            "Trên Windows: dùng sẵn Remote Desktop Connection (mstsc).\n"
            "Máy đích cần bật Remote Desktop và mở port 3389."
        )
    if is_macos():
        return "brew install freerdp  hoặc Microsoft Remote Desktop (App Store)"
    return linux_rdp_install_hint()


def _rdp_client_label():
    if is_windows():
        return "Remote Desktop (mstsc)"
    if is_macos():
        return "Remote Desktop"
    return "Remote Desktop (xfreerdp)"


def _find_child_by_class_win(parent, class_name, user32):
    child = 0
    while True:
        child = user32.FindWindowExW(parent, child, class_name, None)
        if not child:
            return 0
        if user32.IsWindowVisible(child):
            return child
    return 0


def _auto_confirm_rdp_dialogs(password):
    """Windows: tự bấm Connect / điền pass hộp thoại mstsc (dự phòng)."""
    if not is_windows():
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        BM_CLICK = 0x00F5
        WM_SETTEXT = 0x000C
        VK_RETURN = 0x0D
        KEYEVENTF_KEYUP = 0x0002
        connect_labels = (
            "connect", "kết nối", "&connect", "&kết nối",
        )
        warn_fragments = (
            "remote desktop connection security",
            "cảnh báo bảo mật kết nối remote desktop",
            "unknown remote connection",
        )
        cred_titles = ("Windows Security", "Bảo mật Windows")
        warned = False
        cred_filled = False

        def _window_text(hwnd):
            length = user32.GetWindowTextLengthW(hwnd) + 1
            if length <= 1:
                return ""
            buf = ctypes.create_unicode_buffer(length)
            user32.GetWindowTextW(hwnd, buf, length)
            return buf.value

        def _matching_dialogs():
            found = []

            def enum_cb(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    title = _window_text(hwnd).lower()
                    if any(frag in title for frag in warn_fragments):
                        found.append(hwnd)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
            )
            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
            return found

        def _click_connect_button(dialog_hwnd):
            clicked = [False]

            def child_cb(hwnd, _):
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, cls, 64)
                if cls.value != "Button":
                    return True
                label = _window_text(hwnd).lower()
                if any(tag in label for tag in connect_labels):
                    user32.PostMessageW(hwnd, BM_CLICK, 0, 0)
                    user32.SendMessageW(hwnd, BM_CLICK, 0, 0)
                    clicked[0] = True
                    return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
            )
            user32.EnumChildWindows(dialog_hwnd, WNDENUMPROC(child_cb), 0)
            if clicked[0]:
                return True
            for label in ("Connect", "Kết nối", "&Connect"):
                btn = user32.FindWindowExW(dialog_hwnd, None, "Button", label)
                if btn:
                    user32.PostMessageW(btn, BM_CLICK, 0, 0)
                    return True
            user32.SetForegroundWindow(dialog_hwnd)
            ctypes.windll.user32.keybd_event(VK_RETURN, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)
            return True

        for _ in range(300):
            if not warned:
                for hwnd in _matching_dialogs():
                    if _click_connect_button(hwnd):
                        warned = True
                        break
            if password and not cred_filled:
                for title in cred_titles:
                    hwnd = user32.FindWindowW(None, title)
                    if not hwnd:
                        continue
                    edit = _find_child_by_class_win(hwnd, "Edit", user32)
                    if edit:
                        buf = ctypes.create_unicode_buffer(password)
                        user32.SendMessageW(
                            edit, WM_SETTEXT, 0,
                            ctypes.cast(buf, ctypes.c_void_p).value,
                        )
                    for label in ("OK", "&OK"):
                        btn = user32.FindWindowExW(hwnd, None, "Button", label)
                        if btn:
                            user32.PostMessageW(btn, BM_CLICK, 0, 0)
                            cred_filled = True
                            break
            if warned and (cred_filled or not password):
                if cred_filled or warned:
                    return
            time.sleep(0.1)
    except Exception:
        pass


def _start_auto_confirm_rdp_thread(password, enabled=True):
    if enabled and is_windows():
        threading.Thread(
            target=_auto_confirm_rdp_dialogs,
            args=(password,),
            daemon=True,
        ).start()


def _register_rdp_server_registry(address, username):
    if not is_windows():
        return
    try:
        import winreg
        host, _ = _parse_rdp_address(address)
        path = rf"Software\Microsoft\Terminal Server Client\Servers\{host}"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
            winreg.SetValueEx(key, "UsernameHint", 0, winreg.REG_SZ, username)
    except OSError:
        pass


def _ensure_rdp_windows_trust_registry():
    """
    Giảm hộp thoại cảnh báo RDP trên Windows 11+ (HKCU — không cần admin).
    Kết hợp với mstsc /v:host (không mở file .rdp) để tránh «Unknown publisher».
    """
    if not is_windows():
        return
    try:
        import winreg
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Terminal Server Client",
        ) as key:
            winreg.SetValueEx(key, "RdpLaunchConsentAccepted", 0, winreg.REG_DWORD, 1)
        policy = r"Software\Policies\Microsoft\Windows NT\Terminal Services\Client"
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.CreateKey(hive, policy) as key:
                    winreg.SetValueEx(
                        key, "RedirectionWarningDialogVersion", 0, winreg.REG_DWORD, 1,
                    )
            except OSError:
                pass
    except OSError:
        pass


def _termsrv_targets(address):
    """Danh sách TERMSRV/* cho cmdkey."""
    host_only, port = _parse_rdp_address(address)
    targets = [
        f"TERMSRV/{host_only}",
        f"TERMSRV/{address}",
    ]
    if port != RDP_PORT:
        targets.append(f"TERMSRV/{host_only}:{port}")
    seen = set()
    out = []
    for item in targets:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _store_windows_rdp_credentials(address, usernames, password):
    """Lưu credential RDP qua WinAPI — mật khẩu không xuất hiện trên command line."""
    if not is_windows():
        return []
    flags = subprocess.CREATE_NO_WINDOW
    cmdkey_targets = []
    for termsrv in _termsrv_targets(address):
        for username in usernames:
            if not username:
                continue
            try:
                username = validate_windows_logon(username)
            except ValueError:
                continue
            if not cred_write_generic(termsrv, username, password):
                subprocess.run(
                    ["cmdkey", "/generic:" + termsrv, "/user:" + username],
                    capture_output=True,
                    creationflags=flags,
                )
        cmdkey_targets.append(termsrv)
    return cmdkey_targets


def _mstsc_target(address):
    host, port = _parse_rdp_address(address)
    if port == RDP_PORT:
        return host
    return f"{host}:{port}"


def _local_screen_size():
    screen = QGuiApplication.primaryScreen()
    if not screen:
        return 1600, 900
    rect = screen.availableGeometry()
    return max(800, rect.width()), max(600, rect.height())


def _write_rdp_session_file(address, fullscreen=False):
    """File .rdp tạm — chỉ smart sizing + dynamic resolution (không khóa kích thước)."""
    full_address = _mstsc_target(address)
    lines = [
        f"full address:s:{full_address}",
        "screen mode id:i:1" if fullscreen else "screen mode id:i:2",
        "smart sizing:i:1",
        "dynamic resolution:i:1",
        "prompt for credentials:i:0",
        "authentication level:i:2",
        "negotiate security layer:i:1",
        "enablecredsspsupport:i:1",
        "redirectclipboard:i:1",
    ]
    fd, path = tempfile.mkstemp(suffix=".rdp", prefix="pettie_")
    os.close(fd)
    with open(path, "w", encoding="utf-16-le") as f:
        f.write("\ufeff" + "\r\n".join(lines) + "\r\n")
    secure_chmod(path)
    return path


def _mstsc_startupinfo_maximized():
    """Yêu cầu Windows mở cửa sổ mstsc ở trạng thái maximize."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 3  # SW_MAXIMIZE
    return si


def _windows_mstsc_argv(address, fullscreen=False):
    """mstsc /v:host — để Windows tự quản lý kích thước / maximize như mở tay."""
    mstsc = _find_mstsc()
    if not mstsc:
        return None
    args = [mstsc, f"/v:{_mstsc_target(address)}"]
    if fullscreen:
        args.append("/f")
    return args


def _run_windows_mstsc(address, fullscreen=True, cmdkey_targets=None, password=None):
    """mstsc /v:host /f — Full screen; cmdkey giữ đến khi phiên đóng."""
    mstsc = _find_mstsc()
    if not mstsc:
        return None
    _ensure_rdp_windows_trust_registry()
    if password:
        _start_auto_confirm_rdp_thread(password, enabled=True)
    target = _mstsc_target(address)
    subprocess.Popen([mstsc, f"/v:{target}", "/f"])
    _schedule_windows_rdp_cleanup(None, cmdkey_targets or [], mstsc_proc=None)
    return True


def _cmdkey_delete_targets(targets):
    """Xóa credential TERMSRV đã lưu."""
    if not is_windows() or not targets:
        return
    for target in targets:
        cred_delete_generic(target)


def _mstsc_session_running():
    """Còn tiến trình mstsc.exe đang chạy không."""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq mstsc.exe", "/NH"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "mstsc.exe" in (out.stdout or "").lower()
    except OSError:
        return False


def _wait_for_mstsc_session_end(poll_sec=2.0, start_timeout=45.0, max_wait=86400):
    """Chờ mstsc khởi động rồi chờ đến khi phiên đóng (launcher PID không dùng được)."""
    deadline = time.monotonic() + max_wait
    started = False
    start_deadline = time.monotonic() + start_timeout
    while time.monotonic() < start_deadline:
        if _mstsc_session_running():
            started = True
            break
        time.sleep(0.5)
    if not started:
        return
    while time.monotonic() < deadline:
        if not _mstsc_session_running():
            return
        time.sleep(poll_sec)


def _schedule_windows_rdp_cleanup(rdp_file, cmdkey_targets, mstsc_proc=None, max_wait=86400):
    """Xóa file .rdp tạm và cmdkey sau khi phiên mstsc đóng hẳn."""

    def worker():
        try:
            if mstsc_proc is not None:
                try:
                    mstsc_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            _wait_for_mstsc_session_end(max_wait=max_wait)
        finally:
            _cmdkey_delete_targets(cmdkey_targets)
            if rdp_file and os.path.isfile(rdp_file):
                try:
                    os.remove(rdp_file)
                except OSError:
                    pass

    threading.Thread(target=worker, daemon=True).start()


def _find_mstsc():
    if not is_windows():
        return None
    candidates = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "mstsc.exe"),
        shutil.which("mstsc"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _find_windows_freerdp():
    """FreeRDP trên Windows (tùy chọn) nếu không có mstsc."""
    if not is_windows():
        return None, None
    for name in _BUNDLED_FREERDP_NAMES:
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def _sanitize_remmina_field(value, max_len=256):
    """Chặn newline injection trong file cấu hình Remmina."""
    return (value or "").replace("\n", "").replace("\r", "")[:max_len]


def _secure_remove_file(path):
    """Ghi đè rồi xóa file tạm chứa dữ liệu nhạy cảm."""
    try:
        if os.path.isfile(path):
            size = os.path.getsize(path)
            with open(path, "r+b") as f:
                f.write(b"\x00" * min(size, 8192))
        os.remove(path)
    except OSError:
        pass


def _schedule_remmina_profile_cleanup(path, proc=None, max_wait=3600):
    def worker():
        if proc is not None:
            try:
                proc.wait(timeout=max_wait)
            except subprocess.TimeoutExpired:
                time.sleep(5)
        else:
            time.sleep(15)
        _secure_remove_file(path)

    threading.Thread(target=worker, daemon=True).start()


def _launch_remmina(host, port, user, password, domain="", client_ref="remmina", flatpak_id=None):
    """
    Mở Remmina với profile tạm (IP + user + pass) — giống bấm Connect trong Remmina.
    """
    domain = _sanitize_remmina_field((domain or "").strip())
    rdp_user = _sanitize_remmina_field(user.lstrip(".\\"))
    if domain:
        rdp_user = _sanitize_remmina_field(user)
    safe_password = _sanitize_remmina_field(password, max_len=512)
    lines = [
        "[remmina]",
        "name=Pettie SSH Client",
        "protocol=RDP",
        f"server={_sanitize_remmina_field(host)}",
        f"port={int(port)}",
        f"username={rdp_user}",
        f"password={safe_password}",
        "domain=" + domain,
        "security=ntlm",
        "window_maximize=0",
        "scale=1",
        "disableclipboard=0",
    ]
    fd, path = tempfile.mkstemp(suffix=".remmina", prefix="pettie_rdp_")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    secure_chmod(path)

    if flatpak_id:
        cmd = ["flatpak", "run", flatpak_id, "-c", path]
        label = "Remmina (Flatpak)"
    else:
        cmd = [client_ref, "-c", path]
        label = "Remmina"

    proc, _ = _popen_rdp_process(cmd, check_exit=False, gui_window=True)
    _try_focus_rdp_window()
    _schedule_remmina_profile_cleanup(path, proc=proc)
    return True, label


def _try_focus_rdp_window():
    """Đưa cửa sổ xfreerdp lên trước (Linux)."""
    if sys.platform.startswith("win"):
        return
    for cmd in (
        ["wmctrl", "-xa", "xfreerdp"],
        ["wmctrl", "-a", "FreeRDP"],
        ["xdotool", "search", "--name", "FreeRDP", "windowactivate"],
        ["xdotool", "search", "--class", "xfreerdp", "windowactivate"],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=3)
            if r.returncode == 0:
                return
        except (OSError, subprocess.SubprocessError):
            continue


def _write_password_stdin(proc, password):
    """Ghi pass sau khi xfreerdp sẵn sàng đọc /from-stdin."""
    time.sleep(0.35)
    try:
        if proc.stdin and proc.poll() is None:
            proc.stdin.write((password + "\n").encode("utf-8"))
            proc.stdin.flush()
            proc.stdin.close()
    except OSError:
        pass


def _popen_rdp_process(args, check_exit=True, password=None, gui_window=True):
    """Khởi chạy client RDP; password qua /p: hoặc /from-stdin (thread)."""
    stdin_pipe = subprocess.PIPE if password else subprocess.DEVNULL
    env = os.environ.copy()
    if is_linux() and args:
        bundled_path, lib_dir = find_bundled_freerdp()
        if bundled_path and os.path.abspath(args[0]) == os.path.abspath(bundled_path):
            env = bundled_env(lib_dir)
    proc = subprocess.Popen(
        args,
        start_new_session=not gui_window,
        stdin=stdin_pipe,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        env=env,
    )
    if password and proc.stdin:
        threading.Thread(
            target=_write_password_stdin,
            args=(proc, password),
            daemon=True,
        ).start()
    if not check_exit:
        return proc, None
    time.sleep(0.6)
    if proc.poll() is None:
        return proc, None
    err = ""
    try:
        err = (proc.stderr.read() or b"").decode(errors="replace").strip()
    except OSError:
        pass
    return proc, err or "Client RDP thoát ngay (sai user/domain hoặc máy không mở port 3389)."


def _summarize_rdp_error(stderr_text):
    """Rút gọn log xfreerdp thành thông báo ngắn, dễ đọc."""
    if not stderr_text:
        return (
            "Không kết nối được RDP.\n"
            "Kiểm tra user, password, port 3389 và Remote Desktop đã bật trên Windows."
        )
    low = stderr_text.lower()
    if "cannot find kdc for realm" in low or "kerberos_acquirecredentials" in low:
        return (
            "xfreerdp cố dùng Kerberos (Active Directory) nhưng máy đích dùng tài khoản local.\n\n"
            "• Để trống ô Domain\n"
            "• User: Administrator (hoặc tên user local)\n"
            "• Chỉ điền Domain nếu máy thật sự join domain AD"
        )
    if "authentication only" in low or "connect_cancelled" in low:
        return (
            "Xác thực RDP thất bại.\n"
            "Kiểm tra user/password, bật Remote Desktop và mở port 3389 trên Windows."
        )
    if "smart-sizing" in low and "parsing failed" in low:
        return (
            "Lỗi tham số xfreerdp. Hãy chạy lại app bản mới nhất "
            "hoặc thử bỏ tick «Mở toàn màn hình» rồi kết nối lại."
        )
    if "errconnect" in low or "unable to connect" in low:
        return "Không kết nối tới máy đích — kiểm tra IP, firewall và port 3389."
    errors = [
        ln.strip()
        for ln in stderr_text.splitlines()
        if "[ERROR]" in ln
    ]
    if errors:
        last = errors[-1]
        for tag in ("[ERROR]", "[WARN]"):
            if tag in last:
                last = last.split(tag, 1)[-1].strip()
        if len(last) > 220:
            last = last[:220] + "…"
        return f"Lỗi RDP: {last}"
    return (
        "Không kết nối được RDP.\n"
        "Kiểm tra user, password và Remote Desktop trên máy Windows."
    )


_MSG_BOX_STYLE = """
    QMessageBox {
        background-color: #ffffff;
        color: #000000;
    }
    QMessageBox QLabel {
        color: #000000;
        background-color: #ffffff;
        font-size: 13px;
    }
    QMessageBox QPushButton {
        background-color: #f4f4f5;
        color: #18181b;
        border: 1px solid #d4d4d8;
        border-radius: 6px;
        padding: 6px 18px;
        min-width: 72px;
        font-size: 13px;
    }
    QMessageBox QPushButton:hover {
        background-color: #e4e4e7;
    }
"""


def _apply_light_message_box(box):
    """Hộp thoại đọc rõ trên mọi theme — không kế thừa nền tối của dialog RDP."""
    box.setStyleSheet(_MSG_BOX_STYLE)
    pal = box.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#000000"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#000000"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#18181b"))
    box.setPalette(pal)
    box.setAutoFillBackground(True)


def _rdp_message(parent, icon, title, text):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    _apply_light_message_box(box)
    return box.exec()


def _rdp_warning(parent, title, text):
    return _rdp_message(parent, QMessageBox.Icon.Warning, title, text)


def _rdp_info(parent, title, text):
    return _rdp_message(parent, QMessageBox.Icon.Information, title, text)


def _rdp_critical(parent, title, text):
    return _rdp_message(parent, QMessageBox.Icon.Critical, title, text)


class RemoteDesktopDialog(QDialog):
    STYLESHEET = """
        QDialog { background-color: #18181b; color: #fafafa; }
        QLabel#title { font-size: 20px; font-weight: 800; color: #fafafa; }
        QLabel#subtitle { color: #a1a1aa; font-size: 13px; }
        QLabel#fieldLabel {
            color: #d4d4d8; font-size: 12px; font-weight: 600; min-width: 72px;
        }
        QLineEdit {
            background: #09090b; border: 1px solid #3f3f46;
            border-radius: 10px; padding: 10px 14px; color: #fafafa; font-size: 13px;
        }
        QLineEdit:focus { border-color: #2dd4bf; }
        QFrame#formCard {
            background: rgba(9, 9, 11, 0.6); border: 1px solid #3f3f46; border-radius: 14px;
        }
        QPushButton#primary {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #0d9488, stop:1 #0891b2);
            color: white; border: none; border-radius: 12px;
            padding: 12px 24px; font-weight: 700; font-size: 14px;
        }
        QPushButton#primary:hover { background-color: #14b8a6; }
        QPushButton#secondary {
            background: #27272a; color: #e4e4e7; border: none;
            border-radius: 12px; padding: 12px 20px;
        }
        QCheckBox { color: #a1a1aa; spacing: 8px; font-size: 13px; }
        QCheckBox::indicator {
            width: 18px; height: 18px; border-radius: 4px;
            border: 2px solid #3f3f46; background: #09090b;
        }
        QCheckBox::indicator:checked {
            background: #ea580c; border-color: #ea580c;
        }
        QCheckBox::indicator:unchecked { background: #18181b; }
        QLabel#status { color: #2dd4bf; font-size: 12px; }
        QLabel#hint { color: #71717a; font-size: 11px; }
    """

    def __init__(self, ssh_manager, host, user, parent=None, password=None):
        super().__init__(parent)
        self.ssh = ssh_manager
        self.ssh_host = (host or "").strip()
        self.user = user or ""
        self._session_password = (password or "").strip()
        self._forward = None
        self._cmdkey_targets = []
        self._computer_name = ""
        self._rdp_password = ""

        self.setWindowTitle("Remote Desktop — Đăng nhập")
        self.setMinimumWidth(460)
        self.setStyleSheet(self.STYLESHEET)

        settings = get_settings()
        self._local_port = int(settings.get("rdp_local_port", 33890))

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        layout.addWidget(self._title("🖥  Remote Desktop"))
        sub = QLabel(
            "Dùng thông tin đăng nhập SSH hiện tại — chỉnh nếu tài khoản RDP khác."
        )
        sub.setObjectName("subtitle")
        layout.addWidget(sub)

        card = QFrame()
        card.setObjectName("formCard")
        form = QGridLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        form.setSpacing(12)

        ip_hint = self.ssh_host or "192.168.0.1"
        form.addWidget(self._label("IP"), 0, 0)
        self.txt_ip = QLineEdit()
        self.txt_ip.setPlaceholderText(f"VD: {ip_hint}")
        if self.ssh_host:
            info = prepare_connect_host(
                self.ssh_host,
                self.ssh_host if not is_ipv4(self.ssh_host) else "",
            )
            display_ip = info.get("resolved_ip") or self.ssh_host
            self.txt_ip.setText(display_ip)
        form.addWidget(self.txt_ip, 0, 1)

        form.addWidget(self._label("User"), 1, 0)
        self.txt_rdp_user = QLineEdit()
        self.txt_rdp_user.setPlaceholderText("VD: Administrator")
        if self.user:
            self.txt_rdp_user.setText(self.user)
        form.addWidget(self.txt_rdp_user, 1, 1)

        form.addWidget(self._label("Password"), 2, 0)
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_password.setPlaceholderText("Lấy từ phiên SSH — không lưu đĩa")
        if self._session_password:
            self.txt_password.setText(self._session_password)
        form.addWidget(self.txt_password, 2, 1)

        form.addWidget(self._label("Domain"), 3, 0)
        self.txt_domain = QLineEdit()
        self.txt_domain.setPlaceholderText("Trống = local · Có domain = nhập domain")
        form.addWidget(self.txt_domain, 3, 1)
        layout.addWidget(card)

        hint = QLabel(
            "• Mặc định: mở Desktop tới đúng IP ở trên, VD 192.168.0.1:3389\n"
            "• Bật tunnel chỉ khi máy không mở port 3389 trực tiếp"
        )
        hint.setObjectName("hint")
        layout.addWidget(hint)

        self.chk_tunnel = QCheckBox("Kết nối qua SSH tunnel nâng cao")
        self.chk_tunnel.setToolTip(
            "Chỉ dùng khi không RDP trực tiếp được — sẽ qua localhost"
        )
        layout.addWidget(self.chk_tunnel)

        self.chk_fullscreen = QCheckBox("Mở toàn màn hình")
        self.chk_fullscreen.setChecked(True)
        self.chk_fullscreen.setToolTip(
            "Windows: luôn bật Full screen trong Remote Desktop Connection.\n"
            "Thoát full screen: Ctrl+Alt+Break.\n"
            "Linux: Ctrl+Alt+Enter."
        )
        if is_windows():
            self.chk_fullscreen.setEnabled(False)
            self.chk_fullscreen.setText("Full screen (tự động trên Windows)")
        layout.addWidget(self.chk_fullscreen)

        fs_hint = QLabel(
            "Desktop tự co vừa cửa sổ. Fullscreen: Ctrl+Alt+Enter (Linux) · "
            "Ctrl+Alt+Break (Windows). Kéo góc cửa sổ để chỉnh kích thước."
        )
        fs_hint.setObjectName("hint")
        fs_hint.setWordWrap(True)
        layout.addWidget(fs_hint)

        self.chk_auto_confirm = QCheckBox(
            "Tự động bấm Connect, bỏ cảnh báo bảo mật Windows 11"
        )
        self.chk_auto_confirm.setChecked(True)
        layout.addWidget(self.chk_auto_confirm)

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("status")
        layout.addWidget(self.lbl_status)

        btns = QHBoxLayout()
        self.btn_login = QPushButton("Kết nối Desktop")
        self.btn_login.setObjectName("primary")
        self.btn_login.clicked.connect(self.login_and_connect)
        btn_close = QPushButton("Hủy")
        btn_close.setObjectName("secondary")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_login)
        btns.addStretch()
        btns.addWidget(btn_close)
        layout.addLayout(btns)

        self.txt_password.returnPressed.connect(self.login_and_connect)

    def _title(self, text):
        lb = QLabel(text)
        lb.setObjectName("title")
        return lb

    def _label(self, text):
        lb = QLabel(text)
        lb.setObjectName("fieldLabel")
        return lb

    def _normalize_ip(self, ip):
        ip = ip.strip()
        if ip.lower() in ("localhost",):
            return "127.0.0.1"
        if is_ipv4(ip):
            return ip
        resolved = resolve_ipv4(ip)
        return resolved or ip

    def _rdp_address(self, ip):
        """Địa chỉ RDP = IP người dùng nhập + cổng 3389."""
        ip = self._normalize_ip(ip)
        if ":" in ip and not ip.startswith("["):
            return ip
        return f"{ip}:{RDP_PORT}"

    def _tunnel_remote_host(self, user_ip):
        """Đích tunnel phía server SSH (RDP trên cùng máy SSH → 127.0.0.1)."""
        user_ip = self._normalize_ip(user_ip)
        if user_ip in ("127.0.0.1", "::1") or user_ip == self.ssh_host:
            return "127.0.0.1"
        return user_ip

    def _rdp_account_user(self):
        return (self.txt_rdp_user.text() if hasattr(self, "txt_rdp_user") else self.user).strip() or self.user

    def _rdp_target_is_ssh_host(self, user_ip):
        user_ip = self._normalize_ip(user_ip)
        if user_ip in ("127.0.0.1", "::1"):
            return True
        return user_ip == self._normalize_ip(self.ssh_host)

    def _net_use_username(self, domain_field):
        """net use qua IP: local account phải dùng .\\user (MACHINE\\user → lỗi 3775)."""
        rdp_user, rdp_domain = self._split_rdp_account(domain_field)
        if rdp_domain:
            return f"{rdp_domain}\\{rdp_user}"
        return f".\\{rdp_user}"

    def _primary_rdp_username(self, domain_field):
        """User cho cmdkey / mstsc."""
        rdp_user, rdp_domain = self._split_rdp_account(domain_field)
        if rdp_domain:
            return f"{rdp_domain}\\{rdp_user}"
        if self._computer_name and self._rdp_target_is_ssh_host(self.txt_ip.text().strip()):
            return f"{self._computer_name}\\{rdp_user}"
        if "\\" in rdp_user:
            return rdp_user
        return f".\\{rdp_user}"

    def _cmdkey_usernames(self, domain_field):
        """Thử nhiều dạng user — Windows đôi khi chỉ khớp một kiểu."""
        names = []
        primary = self._primary_rdp_username(domain_field)
        names.append(primary)
        alt = self._net_use_username(domain_field)
        if alt not in names:
            names.append(alt)
        rdp_user, _ = self._split_rdp_account(domain_field)
        if rdp_user not in names:
            names.append(rdp_user)
        return names

    def _split_rdp_account(self, domain_field):
        account = self._rdp_account_user()
        if domain_field:
            return account, domain_field
        if "\\" in account:
            dom, _, user = account.partition("\\")
            return user, dom
        return account.lstrip(".\\"), ""

    def _linux_rdp_user_domain(self, domain_field):
        """User/domain cho xfreerdp — không dùng tên máy làm domain (gây lỗi Kerberos)."""
        rdp_user, explicit_domain = self._split_rdp_account(domain_field)
        user = rdp_user.lstrip(".\\")
        if explicit_domain:
            return user, explicit_domain
        return user, ""

    def _fetch_computer_name(self):
        if getattr(self.ssh, "remote_os", None) != "windows":
            return ""
        code, out, _ = self.ssh.exec_command("cmd /c echo %COMPUTERNAME%", timeout=10)
        if code == 0:
            name = (out or "").strip()
            if name and name != "%COMPUTERNAME%":
                return name
        return ""

    def _run_net_use_check(self, verify_ip, username, password):
        """Xác thực qua PowerShell EncodedCommand — hỗ trợ mật khẩu có ký tự đặc biệt."""
        ip = validate_rdp_ipv4(verify_ip)
        user = validate_windows_logon(username)
        if password is None:
            raise ValueError("Thiếu mật khẩu.")
        u_b64 = base64.b64encode(user.encode("utf-16-le")).decode("ascii")
        p_b64 = base64.b64encode(password.encode("utf-16-le")).decode("ascii")
        i_b64 = base64.b64encode(ip.encode("utf-16-le")).decode("ascii")
        ps_script = (
            "$ErrorActionPreference='Stop';"
            f"$u=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{u_b64}'));"
            f"$p=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{p_b64}'));"
            f"$ip=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('{i_b64}'));"
            '$path="\\\\"+$ip+"\\IPC$";'
            "& net.exe use $path $p /user:$u | Out-Null;"
            "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE };"
            "& net.exe use $path /delete /y | Out-Null;"
            "exit 0"
        )
        encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")
        return self.ssh.exec_command(
            f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded}",
            timeout=25,
        )

    def _verify_credentials(self, ip, password, domain):
        remote_os = getattr(self.ssh, "remote_os", None) or "unknown"
        if remote_os != "windows":
            return True, ""

        verify_ip = self._tunnel_remote_host(ip) if self.chk_tunnel.isChecked() else self._normalize_ip(ip)
        if not self._rdp_target_is_ssh_host(ip) and not self.chk_tunnel.isChecked():
            return True, ""

        users_to_try = [self._net_use_username(domain)]
        primary = self._primary_rdp_username(domain)
        if primary not in users_to_try:
            users_to_try.append(primary)

        last_detail = ""
        for user_part in users_to_try:
            try:
                code, out, err = self._run_net_use_check(verify_ip, user_part, password)
            except ValueError:
                continue
            if code == 0:
                return True, ""
            last_detail = (err or out or "").strip()

        detail = last_detail or "Sai IP, mật khẩu hoặc domain."
        low = detail.lower()
        if "3775" in detail or "user context supplied is invalid" in low:
            detail = "Sai định dạng tài khoản. Local: để trống Domain, User = Administrator."
        elif any(x in detail for x in ("1219", "1326", "86", "1323", "logon failure")):
            detail = "Sai mật khẩu hoặc tên đăng nhập / domain."
        return False, detail

    def _register_rdp_server(self, address, username):
        _register_rdp_server_registry(address, username)

    def _start_auto_confirm_thread(self, password):
        _start_auto_confirm_rdp_thread(
            password, enabled=self.chk_auto_confirm.isChecked(),
        )

    def _store_windows_credentials(self, address, usernames, password):
        self._cmdkey_targets = _store_windows_rdp_credentials(
            address, usernames, password,
        )

    def _launch_rdp(self, address, password, domain_field):
        rdp_user, rdp_domain = self._split_rdp_account(domain_field)
        full_user = self._primary_rdp_username(domain_field)
        if not rdp_domain and self._computer_name:
            rdp_domain = self._computer_name

        if is_windows():
            self._register_rdp_server(address, full_user)
            self._store_windows_credentials(
                address, self._cmdkey_usernames(domain_field), password,
            )
            self._rdp_password = password
            self._start_auto_confirm_thread(password)
            fullscreen = self.chk_fullscreen.isChecked()
            proc = _run_windows_mstsc(
                address,
                cmdkey_targets=list(self._cmdkey_targets),
                password=password,
            )
            if not proc:
                return False, None
            return True, "mstsc"

        linux_user, linux_domain = self._linux_rdp_user_domain(domain_field)
        return _launch_rdp_client(
            address, linux_user, password, linux_domain,
            fullscreen=self.chk_fullscreen.isChecked(),
        )

    def _local_screen_size(self):
        """Kích thước màn hình local (logical px)."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return 1600, 900
        rect = screen.availableGeometry()
        return max(800, rect.width()), max(600, rect.height())

    def _rdp_geometry(self):
        """
        win: kích thước cửa sổ + smart-sizing (vừa màn hình).
        session: độ phân giải xin từ máy Windows (giới hạn để không quá to).
        """
        screen_w, screen_h = self._local_screen_size()
        fullscreen = self.chk_fullscreen.isChecked()
        max_session_w, max_session_h = 1920, 1080

        if fullscreen:
            win_w, win_h = screen_w, screen_h
        else:
            win_w = max(1024, int(screen_w * 0.86))
            win_h = max(576, int(screen_h * 0.86))

        session_w = min(win_w, max_session_w)
        session_h = min(win_h, max_session_h)
        return win_w, win_h, session_w, session_h

    def login_and_connect(self):
        ip = self.txt_ip.text().strip()
        password = self.txt_password.text().strip() or self._session_password
        domain = self.txt_domain.text().strip()

        if not ip:
            _rdp_warning(self, "Thiếu thông tin", "Vui lòng nhập IP.")
            return
        if not password:
            _rdp_warning(
                self,
                "Thiếu thông tin",
                "Vui lòng nhập Password (hoặc đăng nhập SSH bằng mật khẩu trước).",
            )
            return

        dns_name = self.ssh_host if self.ssh_host and not is_ipv4(self.ssh_host) else ""
        info = prepare_connect_host(ip, dns_name, require_resolve=False)
        if info.get("error"):
            _rdp_warning(self, "DNS", info["error"])
            return
        if info.get("resolved_ip") and info["resolved_ip"] != ip:
            ip = info["resolved_ip"]
            self.txt_ip.setText(ip)
        connect_target = info.get("connect_host") or ip

        user_ip = self._normalize_ip(connect_target if dns_name else ip)
        rdp_address = self._rdp_address(user_ip)

        self.lbl_status.setText("Đang xác thực...")
        self.btn_login.setEnabled(False)
        QApplication.processEvents()

        if self._rdp_target_is_ssh_host(ip):
            self._computer_name = self._fetch_computer_name()
        else:
            self._computer_name = ""

        ok, err_msg = self._verify_credentials(ip, password, domain)
        if not ok:
            self.btn_login.setEnabled(True)
            self.lbl_status.setText("")
            _rdp_critical(self, "Đăng nhập thất bại", err_msg)
            return

        if self.chk_tunnel.isChecked():
            self.lbl_status.setText("Đang tạo SSH tunnel...")
            QApplication.processEvents()
            remote_host = self._tunnel_remote_host(user_ip)
            handle, err = self.ssh.start_local_forward(
                self._local_port, remote_host, RDP_PORT,
                label=f"RDP->{remote_host}:{RDP_PORT}",
            )
            if err:
                self.btn_login.setEnabled(True)
                self.lbl_status.setText("")
                _rdp_warning(self, "Lỗi tunnel", err)
                return
            self._forward = handle
            save_settings({"rdp_local_port": self._local_port})
            rdp_address = f"127.0.0.1:{self._local_port}"

        self.lbl_status.setText(f"Đang mở Desktop → {rdp_address}")
        QApplication.processEvents()

        try:
            launched, detail = self._launch_rdp(rdp_address, password, domain)
        finally:
            self._wipe_str(password)
        if launched:
            self.btn_login.setEnabled(True)
            client_name = detail or "RDP client"
            self.lbl_status.setText(f"Đã mở {client_name} → {rdp_address}")
            if not sys.platform.startswith("win"):
                fs_tip = ""
                if self.chk_fullscreen.isChecked():
                    fs_tip = (
                        "\n\nThoát fullscreen: Ctrl+Alt+Enter, "
                        "hoặc di chuột lên mép trên để thấy thanh công cụ."
                    )
                _rdp_info(
                    self,
                    "Remote Desktop",
                    f"Đã khởi chạy {client_name}.\n\n"
                    "Cửa sổ Desktop có thể nằm phía sau app khác — "
                    "kiểm tra thanh taskbar."
                    f"{fs_tip}\n\n"
                    "Hộp thoại này sẽ đóng; kết nối SSH vẫn giữ nguyên.",
                )
            self.accept()
        else:
            self.btn_login.setEnabled(True)
            if detail is None:
                hint = linux_rdp_install_hint()
                summary = (
                    "Không tìm thấy ứng dụng RDP trên máy Linux.\n\n"
                    "Cài một trong các gói sau rồi thử lại:\n"
                    f"  • {hint}\n"
                    "  • sudo dnf install remmina"
                )
                _rdp_warning(self, "Lỗi RDP", summary)
            else:
                summary = _summarize_rdp_error(detail)
                _rdp_warning(self, "Không kết nối RDP", summary)

    def _clear_form(self):
        """Xóa dữ liệu nhạy cảm — không giữ sau khi đóng dialog/app."""
        self._wipe_str(self._rdp_password)
        self._wipe_str(self._session_password)
        self.txt_ip.clear()
        self.txt_rdp_user.clear()
        self.txt_password.clear()
        self.txt_domain.clear()
        self._rdp_password = ""
        self._session_password = ""

    @staticmethod
    def _wipe_str(value):
        if not value:
            return
        try:
            ba = bytearray(value.encode("utf-8", errors="ignore"))
            for i in range(len(ba)):
                ba[i] = 0
        except Exception:
            pass

    def closeEvent(self, event):
        if self.result() != QDialog.DialogCode.Accepted:
            self._cleanup_cmdkey()
        self._clear_form()
        super().closeEvent(event)

    def reject(self):
        self._cleanup_cmdkey()
        self._clear_form()
        super().reject()

    def _cleanup_cmdkey(self):
        _cmdkey_delete_targets(self._cmdkey_targets)
        self._cmdkey_targets = []


def _rdp_address(host, port=None):
    """Địa chỉ RDP từ host + port."""
    host = (host or "").strip()
    if host.lower() in ("localhost",):
        host = "127.0.0.1"
    port = int(port) if port else RDP_PORT
    if ":" in host and not host.startswith("["):
        return host
    return f"{host}:{port}"


def _freerdp_geometry(fullscreen=False):
    screen_w, screen_h = _local_screen_size()
    max_session_w, max_session_h = 1920, 1080
    if fullscreen:
        win_w, win_h = screen_w, screen_h
    else:
        win_w = max(1024, int(screen_w * 0.86))
        win_h = max(576, int(screen_h * 0.86))
    session_w = min(win_w, max_session_w)
    session_h = min(win_h, max_session_h)
    return win_w, win_h, session_w, session_h


def _freerdp_flags(
    host, port, user, domain, sec="nla", fullscreen=False,
    local_account=False,
):
    user = validate_windows_logon(user)
    domain = validate_rdp_domain(domain) if domain else ""
    win_w, win_h, session_w, session_h = _freerdp_geometry(fullscreen)
    flags = [
        f"/v:{host}:{port}",
        f"/u:{user}",
        "/from-stdin",
        "/cert:tofu",
        f"/sec:{sec}",
        "/scale:100",
        "/network:auto",
        "/auto-reconnect",
        f"/size:{session_w}x{session_h}",
        f"/smart-sizing:{win_w}x{win_h}",
        "+clipboard",
        "/sound:off",
    ]
    if domain and domain not in (".", ""):
        flags.append(f"/d:{domain}")
    elif local_account:
        flags.append("/auth-pkg-list:ntlm")
    if fullscreen:
        flags.append("/f")
        flags.append("/floatbar:sticky:on,default:visible,show:fullscreen")
    return flags


def _rdp_login_attempts(user, domain=""):
    """
    Thứ tự thử đăng nhập — tài khoản local Windows (không AD) trước.
    Tránh /d:. vì dễ kích hoạt Kerberos trên xfreerdp.
    """
    user = (user or "").strip()
    domain = (domain or "").strip()
    if domain and domain not in (".", ""):
        return [
            (user, domain, "nla"),
            (user, domain, "tls"),
        ]
    if "\\" in user:
        return [(user, "", "nla"), (user, "", "tls")]
    base = user.lstrip(".\\")
    return [
        (f".\\{base}", "", "nla"),
        (base, "", "nla"),
        (base, "", "tls"),
        (f".\\{base}", "", "tls"),
    ]


def _run_freerdp(
    client_ref, host, port, user, password, domain, sec="nla",
    fullscreen=False,
):
    local = not domain or domain in (".", "")
    args = [client_ref] + _freerdp_flags(
        host, port, user, domain, sec=sec, fullscreen=fullscreen,
        local_account=local,
    )
    proc, err = _popen_rdp_process(
        args, password=password, check_exit=False, gui_window=True,
    )
    if err:
        return err
    time.sleep(1.5)
    if proc.poll() is not None:
        try:
            err = (proc.stderr.read() or b"").decode(errors="replace").strip()
        except OSError:
            err = ""
        return err or "xfreerdp thoát sớm — kiểm tra user, password và port 3389."
    _try_focus_rdp_window()
    return None


def _launch_freerdp_client(client_ref, host, port, user, password, domain, fullscreen=False):
    last_err = ""
    for u, d, sec in _rdp_login_attempts(user, domain):
        last_err = _run_freerdp(
            client_ref, host, port, u, password, d, sec=sec,
            fullscreen=fullscreen,
        )
        if not last_err:
            return True, None
    return False, last_err


def _launch_freerdp_via_flatpak(flatpak_id, host, port, user, password, domain, fullscreen=False):
    last_err = ""
    for u, d, sec in _rdp_login_attempts(user, domain):
        local = not d or d in (".", "")
        args = ["flatpak", "run", flatpak_id] + _freerdp_flags(
            host, port, u, d, sec=sec, fullscreen=fullscreen,
            local_account=local,
        )
        proc, err = _popen_rdp_process(
            args, password=password, check_exit=False, gui_window=True,
        )
        if err:
            last_err = err
            continue
        time.sleep(1.5)
        if proc.poll() is None:
            _try_focus_rdp_window()
            return True, None
        try:
            last_err = (proc.stderr.read() or b"").decode(errors="replace").strip()
        except OSError:
            last_err = ""
    return False, last_err


def _launch_linux_rdp(address, user, password, domain=""):
    """Khởi chạy client RDP trên Linux — dùng cho kết nối trực tiếp (không SSH)."""
    client_kind, client_ref = _find_linux_rdp_client()
    if not client_ref:
        return False, None

    host, port = _parse_rdp_address(address)
    try:
        if client_kind.startswith("flatpak:"):
            flatpak_id = client_ref
            if "remmina" in flatpak_id.lower():
                return _launch_remmina(
                    host, port, user, password, domain,
                    flatpak_id=flatpak_id,
                )

            ok, err = _launch_freerdp_via_flatpak(
                flatpak_id, host, port, user, password, domain,
            )
            if not ok:
                return False, err
            return True, client_kind

        if client_kind == "remmina":
            return _launch_remmina(
                host, port, user, password, domain, client_ref=client_ref,
            )

        if client_kind == "krdc":
            _popen_rdp_process(
                [client_ref, f"rdp://{user}@{host}:{port}"],
                check_exit=False,
                gui_window=True,
            )
            _try_focus_rdp_window()
            return True, client_kind

        ok, err = _launch_freerdp_client(
            client_ref, host, port, user, password, domain,
        )
        if not ok:
            return False, err
        return True, client_kind
    except OSError as exc:
        return False, str(exc)


def _find_macos_rdp_client():
    """macOS: xfreerdp (brew) hoặc bản đóng gói cùng Pettie."""
    bundled = _find_bundled_freerdp()
    if bundled[1]:
        return bundled
    for name in ("xfreerdp", "xfreerdp3", "freerdp", "wlfreerdp"):
        path = shutil.which(name)
        if path:
            return name, path
    return None, None


def _launch_macos_rdp(address, user, password, domain="", fullscreen=False):
    """Khởi chạy RDP trên macOS qua xfreerdp."""
    client_kind, client_ref = _find_macos_rdp_client()
    if not client_ref:
        return False, None
    host, port = _parse_rdp_address(address)
    ok, err = _launch_freerdp_client(
        client_ref, host, port, user, password, domain, fullscreen=fullscreen,
    )
    if not ok:
        return False, err
    return True, client_kind


def _windows_launch_rdp(address, user, password, domain="", fullscreen=True):
    """Khởi chạy mstsc /v:host — giống mở Remote Desktop thủ công."""
    if not _find_mstsc():
        kind, ref = _find_windows_freerdp()
        if ref:
            host, port = _parse_rdp_address(address)
            ok, err = _launch_freerdp_client(
                ref, host, port, user, password, domain, fullscreen=fullscreen,
            )
            return (True, kind) if ok else (False, err)
        return False, None

    rdp_user = user.lstrip(".\\")
    rdp_domain = (domain or "").strip()
    full_user = f"{rdp_domain}\\{rdp_user}" if rdp_domain else f".\\{rdp_user}"

    _register_rdp_server_registry(address, full_user)
    cmdkey_targets = _store_windows_rdp_credentials(
        address, [full_user, f".\\{rdp_user}", rdp_user], password,
    )
    ok = _run_windows_mstsc(
        address,
        cmdkey_targets=cmdkey_targets,
        password=password,
    )
    if not ok:
        return False, None
    return True, "mstsc"


def _launch_rdp_client(address, user, password, domain="", fullscreen=None):
    """Một điểm vào RDP — Linux, Windows và macOS."""
    if is_windows():
        return _windows_launch_rdp(address, user, password, domain)
    if is_macos():
        fs = True if fullscreen is None else fullscreen
        return _launch_macos_rdp(address, user, password, domain, fullscreen=fs)
    return _launch_linux_rdp(address, user, password, domain)


def connect_direct_rdp(
    host,
    user,
    password,
    port=RDP_PORT,
    parent=None,
    domain="",
    dns_host="",
):
    """
    Kết nối Remote Desktop trực tiếp (port 3389) — không qua SSH.
    Giống Windows mstsc: nhập domain/hostname, mở màn hình remote ngay.
    Trả về (success: bool, message: str).
    """
    host = (host or "").strip()
    dns_host = (dns_host or "").strip()
    user = (user or "").strip()
    password = (password or "").strip()
    domain = (domain or "").strip()
    if not host and not dns_host:
        return False, "Vui lòng nhập domain hoặc Host / IP."
    if not user:
        return False, "Vui lòng nhập Username."
    if not password:
        return False, "Vui lòng nhập Password cho RDP."

    if is_linux() and not linux_rdp_client_available():
        return False, (
            "Chưa có xfreerdp trên Linux.\n\n"
            "Mở lại app và chọn «Cài xfreerdp», hoặc chạy:\n"
            f"  bash install-linux.sh\n"
            f"  {install_command_display()}"
        )

    info = prepare_connect_host(host, dns_host, require_resolve=False)
    if info.get("error"):
        return False, info["error"]
    connect_host = info.get("connect_host") or host or dns_host
    rdp_host = info.get("resolved_ip") or connect_host

    try:
        rdp_host = validate_ssh_host(rdp_host)
        user = validate_windows_logon(user)
        port = validate_ssh_port(port)
        domain = validate_rdp_domain(domain)
    except ValueError as exc:
        return False, str(exc)

    address = _rdp_address(rdp_host, port)
    try:
        # Windows: luôn Full screen (mstsc tự tích — Maximize mới hoạt động).
        launched, detail = _launch_rdp_client(address, user, password, domain)
        if launched:
            client = detail or _rdp_client_label()
            if parent is not None:
                try:
                    parent.showMinimized()
                except Exception:
                    pass
            focus_hint = (
                "bấm Alt+Tab hoặc xem taskbar"
                if is_windows()
                else "bấm Alt+Tab hoặc xem dock/taskbar"
            )
            return True, (
                f"Đang hiển thị màn hình máy đích → {address}\n"
                f"({client})\n\n"
                f"Cửa sổ Remote Desktop sẽ mở — nếu chưa thấy, {focus_hint}."
            )
        if detail is None:
            return False, (
                "Không mở được màn hình Remote Desktop trên máy này.\n"
                f"{_rdp_install_hint()}"
            )
        return False, _summarize_rdp_error(detail)
    except OSError as exc:
        return False, str(exc)
