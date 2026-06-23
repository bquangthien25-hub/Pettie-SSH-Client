"""Nhận diện hệ điều hành máy đang chạy app (local) và nhãn hiển thị."""

import os
import platform
import shlex
import shutil
import subprocess
import sys


def detect_local_os() -> str:
    """OS của user đang mở Pettie SSH (máy bạn)."""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def is_linux() -> bool:
    return not is_windows() and not is_macos()


def local_os_display_name(os_id: str = None) -> str:
    os_id = os_id or detect_local_os()
    if os_id == "windows":
        ver = platform.release()
        return f"Windows {ver}" if ver else "Windows"
    if os_id == "macos":
        return "macOS"
    if os_id == "linux":
        try:
            from pathlib import Path
            release = Path("/etc/os-release")
            if release.is_file():
                for line in release.read_text(encoding="utf-8").splitlines():
                    if line.startswith("PRETTY_NAME="):
                        return line.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return platform.system() or "Linux"
    return os_id or "?"


def format_os_display(os_id: str, role: str = "") -> str:
    """Nhãn OS thân thiện — role: local | remote."""
    from ngonngu import tr

    if not os_id:
        return tr("unknown_os")
    key = (os_id or "").lower()
    names = {
        "windows": "Windows",
        "linux": "Linux",
        "unix": "Unix/BSD",
        "macos": "macOS",
        "unknown": tr("unknown_os"),
    }
    if role == "local" and key == "linux":
        return local_os_display_name("linux")
    return names.get(key, os_id)


def launch_system_terminal(argv):
    """
    Mở terminal hệ thống chạy lệnh argv (vd. ssh user@host).
    Trả về (thành_công, tên terminal hoặc thông báo lỗi).
    """
    if not argv:
        return False, "Không có lệnh để chạy."

    if sys.platform.startswith("win"):
        try:
            subprocess.Popen(
                argv,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return True, "cmd"
        except OSError as e:
            return False, str(e)

    if sys.platform == "darwin":
        cmd = " ".join(shlex.quote(str(x)) for x in argv)
        try:
            subprocess.Popen([
                "osascript", "-e",
                f'tell application "Terminal" to do script "{cmd}"',
            ])
            return True, "Terminal"
        except OSError as e:
            return False, str(e)

    # Linux / BSD — thử nhiều terminal phổ biến (Fedora, Ubuntu, KDE, …)
    candidates = [
        ("gnome-terminal", lambda a: ["gnome-terminal", "--"] + a),
        ("kgx", lambda a: ["kgx", "--"] + a),
        ("ptyxis", lambda a: ["ptyxis", "--"] + a),
        ("konsole", lambda a: ["konsole", "-e"] + a),
        ("xfce4-terminal", lambda a: ["xfce4-terminal", "-e"] + a),
        ("mate-terminal", lambda a: ["mate-terminal", "-e"] + a),
        ("tilix", lambda a: ["tilix", "-e"] + a),
        ("terminator", lambda a: ["terminator", "-x"] + a),
        ("kitty", lambda a: ["kitty"] + a),
        ("alacritty", lambda a: ["alacritty", "-e"] + a),
        ("foot", lambda a: ["foot"] + a),
        ("wezterm", lambda a: ["wezterm", "start", "--"] + a),
        ("xterm", lambda a: ["xterm", "-e"] + a),
        ("uxterm", lambda a: ["uxterm", "-e"] + a),
        ("rxvt", lambda a: ["rxvt", "-e"] + a),
    ]

    env_term = (os.environ.get("TERMINAL") or "").strip()
    if env_term:
        name = env_term.split()[0]
        if shutil.which(name):
            candidates.insert(0, (name, lambda a, n=name: [n, "-e"] + a))

    tried = []
    for name, build_cmd in candidates:
        if not shutil.which(name):
            continue
        tried.append(name)
        try:
            subprocess.Popen(build_cmd(argv))
            return True, name
        except OSError:
            continue

    hint = ", ".join(t[0] for t in candidates[:6])
    if tried:
        return False, (
            f"Đã thử {', '.join(tried)} nhưng không khởi chạy được. "
            f"Cài một terminal: {hint}."
        )
    return False, (
        "Không tìm thấy terminal trên hệ thống. "
        f"Cài một trong: {hint} (vd. sudo dnf install konsole)."
    )
