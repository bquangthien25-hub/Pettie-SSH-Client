"""Kiểm tra đầu vào — giảm command injection khi gọi shell/SSH."""

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
_CMD_METACHAR_RE = re.compile(r'[&|<>^%!\r\n;]')


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
    if len(cmd) > 8000:
        raise ValueError("Lệnh quá dài.")
    return cmd


def ssh_argv(user: str, host: str, port) -> list:
    """argv an toàn cho subprocess — không qua shell."""
    return [
        "ssh",
        "-p", str(validate_ssh_port(port)),
        "-o", "BatchMode=no",
        "-l", validate_ssh_user(user),
        validate_ssh_host(host),
    ]
