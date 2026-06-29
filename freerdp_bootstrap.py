"""
Linux — cài Remmina (engine RDP chính) hoặc xfreerdp dự phòng.

Luồng ưu tiên trong app:
  1. Remmina (remmina -c profile) — ổn định nhất
  2. xfreerdp trên PATH hệ thống
  3. xfreerdp đóng gói trong vendor/freerdp/
  4. Tự cài qua apt/dnf/pacman/zypper khi người dùng đồng ý
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
        vendor = os.path.join(base, "vendor", "freerdp")
        roots = (
            (os.path.join(base, "bin"), os.path.join(base, "lib")),
            (os.path.join(base, "libexec"), os.path.join(base, "lib")),
            (base, os.path.join(base, "lib")),
            (os.path.join(vendor, "bin"), os.path.join(vendor, "lib")),
        )
        for bin_dir, lib_dir in roots:
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


def rdp_client_packages() -> list[str]:
    """Gói cài Remote Desktop — Remmina trước, xfreerdp dự phòng."""
    pm = detect_pkg_manager()
    if pm == "apt":
        return ["remmina", "remmina-plugin-rdp", "freerdp2-x11"]
    if pm == "dnf":
        return ["remmina", "freerdp"]
    if pm == "pacman":
        return ["remmina", "freerdp2"]
    if pm == "zypper":
        return ["remmina", "freerdp"]
    return []


def freerdp_packages() -> list[str]:
    """Giữ tên cũ — trả về danh sách gói RDP đầy đủ."""
    return rdp_client_packages()


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
        return "sudo apt install remmina remmina-plugin-rdp freerdp2-x11"
    return "sudo " + " ".join(argv)


def linux_install_hint() -> str:
    return install_command_display()


def run_install_freerdp(use_pkexec: bool = True) -> tuple[bool, str]:
    """
    Cài Remmina + xfreerdp qua trình quản lý gói hệ thống.
    Trả về (thành_công, thông_báo).
    """
    if not _is_linux():
        return False, "Chỉ hỗ trợ tự cài trên Linux."

    argv = install_command_argv()
    if not argv:
        return False, (
            "Không nhận diện được distro Linux (apt/dnf/pacman/zypper).\n"
            "Cài thủ công: sudo apt install remmina remmina-plugin-rdp"
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
            return True, "Đã cài Remmina (Remote Desktop) từ kho phần mềm hệ thống."
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, detail or f"Cài đặt thất bại (mã {proc.returncode})."
    except subprocess.TimeoutExpired:
        return False, "Hết thời gian chờ cài đặt Remmina."
    except OSError as exc:
        return False, str(exc)


def status_message(system_lookup) -> str:
    if _is_linux() and shutil.which("remmina"):
        return "Client RDP: Remote Desktop (Remmina engine)"
    if _is_linux() and shutil.which("flatpak"):
        for flatpak_id in ("org.remmina.Remmina", "com.remmina.Remmina"):
            try:
                r = subprocess.run(
                    ["flatpak", "info", flatpak_id],
                    capture_output=True,
                    timeout=5,
                )
                if r.returncode == 0:
                    return "Client RDP: Remote Desktop (Remmina Flatpak)"
            except (OSError, subprocess.SubprocessError):
                pass
    try:
        kind, ref = system_lookup()
        if ref:
            return f"Client RDP: {kind or ref}"
    except Exception:
        pass
    path, _lib = find_bundled_freerdp()
    if path:
        return f"Client RDP: xfreerdp đóng gói ({os.path.basename(path)})"
    return f"Chưa có client RDP — cài Remmina hoặc: {install_command_display()}"
