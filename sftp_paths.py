"""Đường dẫn SFTP trên Windows (OpenSSH) — /C:/Users/... thay vì os.path trên Linux."""

import re

_WIN_DRIVE_RE = re.compile(r"^/?([A-Za-z]):", re.IGNORECASE)


def is_windows_sftp_path(path: str) -> bool:
    if not path:
        return False
    return bool(_WIN_DRIVE_RE.match(path.replace("\\", "/")))


def normalize_windows_sftp(path: str) -> str:
    """Chuẩn hóa về dạng /C:/Users/... hoặc / (danh sách ổ đĩa)."""
    if not path or path in (".", "/"):
        return "/"
    p = path.replace("\\", "/").strip()
    if p == "/":
        return "/"
    m = re.match(r"^/([A-Za-z]):/?(.*)$", p)
    if m:
        drive, rest = m.group(1).upper(), m.group(2).strip("/")
        return f"/{drive}:/{rest}" if rest else f"/{drive}:/"
    m = re.match(r"^([A-Za-z]):/?(.*)$", p)
    if m:
        drive, rest = m.group(1).upper(), m.group(2).strip("/")
        return f"/{drive}:/{rest}" if rest else f"/{drive}:/"
    return p if p.startswith("/") else f"/{p}"


def _drive_root(drive_part: str) -> str:
    """'C:' hoặc 'C' → '/C:/'."""
    drive = drive_part.rstrip(":").upper()
    return f"/{drive}:/"


def parent_windows_sftp(path: str) -> str:
    p = normalize_windows_sftp(path)
    if p == "/":
        return "/"
    if re.match(r"^/[A-Za-z]:/?$", p):
        return "/"
    parts = [x for x in p.split("/") if x]
    if len(parts) <= 1:
        return "/"
    parent_parts = parts[:-1]
    if len(parent_parts) == 1:
        return _drive_root(parent_parts[0])
    return "/" + "/".join(parent_parts)


def join_windows_sftp(base: str, name: str) -> str:
    base = normalize_windows_sftp(base)
    name = (name or "").replace("\\", "/").strip("/")
    if not name:
        return base
    if base == "/":
        if re.match(r"^[A-Za-z]:?$", name, re.IGNORECASE):
            return _drive_root(name)
        return f"/{name}"
    return f"{base.rstrip('/')}/{name}"


def sftp_list_path(path: str, remote_os: str) -> str:
    """Đường dẫn gửi cho SFTP listdir."""
    if remote_os == "windows" or is_windows_sftp_path(path):
        return normalize_windows_sftp(path)
    return path or "/"
