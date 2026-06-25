"""Kiểm tra đầu vào — giảm command injection khi gọi shell/SSH."""

import os
import re

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$",
)
_SSH_USER_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_SSH_HOST_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*"
    r"|localhost|\[[0-9a-fA-F:]+\])$",
)
_WIN_LOGON_RE = re.compile(r"^(?:[a-zA-Z0-9._-]+\\)?[a-zA-Z0-9._@-]{1,128}$")
_RDP_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9._ -]{1,64}$")
_CMD_METACHAR_RE = re.compile(r'[&|<>^%!\r\n;]')
_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})


def validate_ssh_port(port) -> int:
    p = int(port)
    if p < 1 or p > 65535:
        raise ValueError("Cổng SSH không hợp lệ.")
    return p


def validate_ssh_user(user: str) -> str:
    user = (user or "").strip()
    if not user or not _SSH_USER_RE.match(user):
        raise ValueError("Tên user SSH chứa ký tự không hợp lệ.")
    return user


def validate_ssh_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValueError("Thiếu hostname/IP.")
    if _IPV4_RE.match(host):
        return host
    if host.startswith("[") and host.endswith("]"):
        inner = host[1:-1]
        if re.match(r"^[0-9a-fA-F:]+$", inner):
            return host
    if _SSH_HOST_RE.match(host):
        return host
    raise ValueError("Hostname/IP không hợp lệ.")


def validate_rdp_ipv4(ip: str) -> str:
    """IP cho net use / RDP — chỉ IPv4 để tránh injection trong cmd."""
    ip = (ip or "").strip()
    if ip in ("127.0.0.1", "localhost"):
        return "127.0.0.1"
    if not _IPV4_RE.match(ip):
        raise ValueError("IP RDP phải là địa chỉ IPv4 hợp lệ.")
    return ip


def validate_windows_logon(name: str) -> str:
    name = (name or "").strip()
    if not name or not _WIN_LOGON_RE.match(name):
        raise ValueError("Tên đăng nhập Windows không hợp lệ.")
    return name


def validate_rdp_domain(domain: str) -> str:
    """Domain RDP — chặn ký tự phá argv xfreerdp (/d:...)."""
    domain = (domain or "").strip()
    if not domain or domain in (".", ""):
        return ""
    if not _RDP_DOMAIN_RE.match(domain):
        raise ValueError("Domain RDP không hợp lệ.")
    return domain


def validate_profile_name(name: str) -> str:
    name = (name or "").strip()
    if not name or not _PROFILE_NAME_RE.match(name):
        raise ValueError("Tên profile không hợp lệ.")
    return name


def validate_user_image_path(path: str) -> str:
    """Ảnh nền tùy chỉnh — chỉ file ảnh trong phạm vi kích thước hợp lý."""
    path = (path or "").strip()
    if not path:
        return ""
    resolved = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(resolved):
        raise ValueError("File ảnh nền không tồn tại.")
    try:
        if os.path.islink(resolved):
            raise ValueError("Không dùng symlink làm ảnh nền.")
    except OSError:
        pass
    ext = os.path.splitext(resolved)[1].lower()
    if ext not in _IMAGE_EXTS:
        raise ValueError("Ảnh nền phải là PNG, JPG, WEBP, GIF hoặc BMP.")
    try:
        size = os.path.getsize(resolved)
    except OSError:
        raise ValueError("Không đọc được file ảnh nền.") from None
    if size > 20 * 1024 * 1024:
        raise ValueError("File ảnh nền quá lớn (tối đa 20 MB).")
    return resolved


def is_loopback_or_linklocal_ip(ip: str) -> bool:
    """IPv4 loopback / link-local — chặn DNS redirect nguy hiểm."""
    if not _IPV4_RE.match(ip or ""):
        return False
    parts = [int(x) for x in ip.split(".")]
    if parts[0] == 127:
        return True
    if parts[0] == 169 and parts[1] == 254:
        return True
    if ip == "0.0.0.0":
        return True
    return False


def validate_server_pushed_dns(hostname: str) -> str:
    """
    Hostname DNS do server SSH publish — chặt hơn nhập tay.
    Không cho localhost; sau resolve phải không phải loopback/link-local.
    """
    hostname = validate_ssh_host((hostname or "").strip())
    if hostname.lower() in ("localhost",):
        raise ValueError("DNS từ server không hợp lệ.")
    from dns_utils import resolve_ipv4
    resolved = resolve_ipv4(hostname)
    if resolved and is_loopback_or_linklocal_ip(resolved):
        raise ValueError("DNS từ server trỏ về địa chỉ nội bộ không an toàn.")
    return hostname


def validate_forward_host(host: str) -> str:
    """Host đích cho port forward — IPv4, hostname hoặc 127.0.0.1."""
    host = (host or "").strip()
    if host in ("127.0.0.1", "localhost", "::1"):
        return "127.0.0.1"
    if _IPV4_RE.match(host):
        return host
    if _SSH_HOST_RE.match(host):
        return host
    raise ValueError("Host đích tunnel không hợp lệ.")


def validate_remote_shell_command(cmd: str) -> str:
    """Lệnh console từ UI — chặn null byte và lệnh quá dài."""
    cmd = (cmd or "").strip()
    if not cmd:
        raise ValueError("Lệnh trống.")
    if "\x00" in cmd:
        raise ValueError("Lệnh không hợp lệ.")
    if _CMD_METACHAR_RE.search(cmd):
        raise ValueError("Lệnh chứa ký tự shell không hợp lệ.")
    if len(cmd) > 8000:
        raise ValueError("Lệnh quá dài.")
    return cmd


def validate_ssh_key_path(key_path: str) -> str:
    """Đường dẫn file khóa SSH — phải là file thường, kích thước hợp lý."""
    key_path = (key_path or "").strip()
    if not key_path:
        return ""
    path = os.path.abspath(os.path.expanduser(key_path))
    if not os.path.isfile(path):
        raise ValueError("File khóa SSH không tồn tại.")
    try:
        if os.path.islink(path):
            raise ValueError("Không dùng symlink làm khóa SSH.")
    except OSError:
        pass
    try:
        size = os.path.getsize(path)
    except OSError:
        raise ValueError("Không đọc được file khóa SSH.") from None
    if size > 1024 * 1024:
        raise ValueError("File khóa SSH quá lớn.")
    return path


def validate_remote_entry_name(name: str) -> str:
    """Tên file/thư mục trên remote — chặn path traversal."""
    name = (name or "").strip()
    if not name or name in (".", ".."):
        raise ValueError("Tên không hợp lệ.")
    if "\x00" in name or "/" in name or "\\" in name:
        raise ValueError("Tên không được chứa / hoặc \\.")
    if len(name) > 255:
        raise ValueError("Tên quá dài.")
    return name


def validate_search_pattern(pattern: str) -> str:
    """Chuỗi tìm kiếm file — giới hạn độ dài, chặn null byte."""
    pattern = (pattern or "").strip()
    if not pattern:
        raise ValueError("Chuỗi tìm kiếm trống.")
    if "\x00" in pattern:
        raise ValueError("Chuỗi tìm kiếm không hợp lệ.")
    if len(pattern) > 200:
        raise ValueError("Chuỗi tìm kiếm quá dài.")
    return pattern


def ssh_argv(user: str, host: str, port) -> list:
    """argv an toàn cho subprocess — không qua shell."""
    return [
        "ssh",
        "-p", str(validate_ssh_port(port)),
        "-o", "BatchMode=no",
        "-l", validate_ssh_user(user),
        validate_ssh_host(host),
    ]
