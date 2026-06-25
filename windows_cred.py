"""Lưu/xóa Windows Credential qua WinAPI — tránh /pass: trên command line."""

import ctypes
import subprocess
from ctypes import wintypes

from platform_utils import is_windows

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


def _credential_struct():
    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", wintypes.DWORD),
            ("dwHighDateTime", wintypes.DWORD),
        ]

    class CREDENTIAL(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    return CREDENTIAL


def cred_write_generic(target: str, username: str, password: str) -> bool:
    """Ghi generic credential (TERMSRV/...) — mật khẩu không qua argv."""
    if not is_windows() or not target or not username:
        return False
    try:
        advapi32 = ctypes.windll.advapi32
        CREDENTIAL = _credential_struct()
        pwd_bytes = password.encode("utf-16-le")
        blob = (ctypes.c_byte * len(pwd_bytes)).from_buffer_copy(pwd_bytes)
        cred = CREDENTIAL()
        cred.Flags = 0
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = target
        cred.Comment = None
        cred.CredentialBlobSize = len(pwd_bytes)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = 0
        cred.Attributes = None
        cred.TargetAlias = None
        cred.UserName = username
        return bool(advapi32.CredWriteW(ctypes.byref(cred), 0))
    except (OSError, ValueError, ctypes.ArgumentError):
        return False


def cred_delete_generic(target: str) -> bool:
    """Xóa generic credential theo target."""
    if not is_windows() or not target:
        return False
    try:
        if ctypes.windll.advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
            return True
    except (OSError, ctypes.ArgumentError):
        pass
    flags = subprocess.CREATE_NO_WINDOW
    proc = subprocess.run(
        ["cmdkey", "/delete:" + target],
        capture_output=True,
        creationflags=flags,
    )
    return proc.returncode == 0
