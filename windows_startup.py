"""Đăng ký / gỡ khởi động cùng Windows (Registry Run)."""

import os
import sys

APP_RUN_NAME = "PettieSSHClient"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_windows():
    return sys.platform.startswith("win")


def get_launch_command():
    """Lệnh chạy app khi Windows login."""
    if getattr(sys, "frozen", False):
        return f'"{os.path.abspath(sys.executable)}"'
    script = os.path.abspath(sys.argv[0])
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    launcher = pythonw if os.path.isfile(pythonw) else sys.executable
    return f'"{launcher}" "{script}"'


def is_startup_enabled():
    if not is_windows():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_RUN_NAME)
            return True
    except OSError:
        return False


def set_startup_enabled(enabled):
    if not is_windows():
        return False, "Chỉ hỗ trợ trên Windows."
    import winreg
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, APP_RUN_NAME, 0, winreg.REG_SZ, get_launch_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, APP_RUN_NAME)
                except FileNotFoundError:
                    pass
        return True, ""
    except OSError as e:
        return False, str(e)
