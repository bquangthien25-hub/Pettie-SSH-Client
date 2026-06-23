"""
Linux — đóng gói hoặc tự cài xfreerdp cùng Pettie SSH Client.

Luồng ưu tiên:
  1. xfreerdp đóng gói trong thư mục bin/ (+ lib/ nếu có) cạnh app
  2. xfreerdp đã có trên PATH hệ thống
  3. Tự cài qua apt/dnf/pacman/zypper (pkexec/sudo) khi người dùng đồng ý
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

_FREERDP_NAMES = ("xfreerdp3", "xfreerdp", "wlfreerdp", "freerdp")


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def app_base_dirs() -> list[str]:
    """Thư mục gốc app (PyInstaller _MEIPASS, thư mục exe, source)."""
    dirs: list[str] = []
    if hasattr(sys, "_MEIPASS"):
        dirs.append(sys._MEIPASS)
    if getattr(sys, "frozen", False):
        dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.extend([here, os.path.abspath(".")])
    seen: set[str] = set()
    out: list[str] = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def find_bundled_freerdp() -> tuple[str | None, str | None]:
    """
    Tìm xfreerdp đóng gói cùng app.
    Trả về (đường_dẫn_binary, thư_mục_lib hoặc None).
    """
    for base in app_base_dirs():
        for sub in ("bin", "libexec", ""):
            bin_dir = os.path.join(base, sub) if sub else base
            lib_dir = os.path.join(base, "lib")
            if not os.path.isdir(bin_dir):
                continue
            for name in _FREERDP_NAMES:
                path = os.path.join(bin_dir, name)
                if os.path.isfile(path) and os.access(path, os.X_OK):
                    libs = lib_dir if os.path.isdir(lib_dir) else None
                    return path, libs
    return None, None


def bundled_env(lib_dir: str | None) -> dict[str, str]:
    """LD_LIBRARY_PATH cho xfreerdp đóng gói."""
    env = os.environ.copy()
    if not lib_dir or not os.path.isdir(lib_dir):
        return env
    old = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = lib_dir + (os.pathsep + old if old else "")
    return env


def detect_pkg_manager() -> str | None:
    if not _is_linux():
        return None
    if os.path.isfile("/etc/debian_version") and shutil.which("apt-get"):
        return "apt"
    if os.path.isfile("/etc/fedora-release") and shutil.which("dnf"):
        return "dnf"
    if os.path.isfile("/etc/arch-release") and shutil.which("pacman"):
        return "pacman"
    if shutil.which("zypper"):
        return "zypper"
    if shutil.which("apt-get"):
        return "apt"
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("pacman"):
        return "pacman"
    return None


def freerdp_packages() -> list[str]:
    pm = detect_pkg_manager()
    if pm == "apt":
        return ["freerdp2-x11"]
    if pm == "dnf":
        return ["freerdp"]
    if pm == "pacman":
        return ["freerdp2"]
    if pm == "zypper":
        return ["freerdp"]
    return []


def install_command_argv() -> list[str] | None:
    pm = detect_pkg_manager()
    pkgs = freerdp_packages()
    if not pm or not pkgs:
        return None
    if pm == "apt":
        return ["apt-get", "install", "-y", *pkgs]
    if pm == "dnf":
        return ["dnf", "install", "-y", *pkgs]
    if pm == "pacman":
        return ["pacman", "-S", "--noconfirm", *pkgs]
    if pm == "zypper":
        return ["zypper", "install", "-y", *pkgs]
    return None


def install_command_display() -> str:
    argv = install_command_argv()
    if not argv:
        return "sudo apt install freerdp2-x11"
    return "sudo " + " ".join(argv)


def linux_install_hint() -> str:
    return install_command_display()


def run_install_freerdp(use_pkexec: bool = True) -> tuple[bool, str]:
    """
    Cài xfreerdp qua trình quản lý gói hệ thống.
    Trả về (thành_công, thông_báo).
    """
    if not _is_linux():
        return False, "Chỉ hỗ trợ tự cài trên Linux."

    argv = install_command_argv()
    if not argv:
        return False, (
            "Không nhận diện được distro Linux (apt/dnf/pacman/zypper).\n"
            "Cài thủ công: sudo apt install freerdp2-x11"
        )

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        full = argv
    elif use_pkexec and shutil.which("pkexec"):
        full = ["pkexec", "--disable-internal-agent"] + argv
    elif shutil.which("sudo"):
        full = ["sudo", "-n"] + argv
        if subprocess.run(full, capture_output=True).returncode != 0:
            full = ["sudo"] + argv
    else:
        return False, f"Cần quyền admin. Chạy trong terminal:\n  {install_command_display()}"

    try:
        proc = subprocess.run(
            full,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if proc.returncode == 0:
            return True, "Đã cài xfreerdp (FreeRDP) từ kho phần mềm hệ thống."
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, detail or f"Cài đặt thất bại (mã {proc.returncode})."
    except subprocess.TimeoutExpired:
        return False, "Hết thời gian chờ cài đặt xfreerdp."
    except OSError as exc:
        return False, str(exc)


def status_message(system_lookup) -> str:
    path, lib = find_bundled_freerdp()
    if path:
        return f"Client RDP: xfreerdp đóng gói ({os.path.basename(path)})"
    try:
        kind, ref = system_lookup()
        if ref:
            return f"Client RDP: {kind or ref}"
    except Exception:
        pass
    return f"Chưa có xfreerdp — sẽ tự cài khi bạn dùng Remote hoặc chạy: {install_command_display()}"
