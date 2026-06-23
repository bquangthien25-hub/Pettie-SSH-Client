"""DNS / DDNS — resolve hostname mới trước khi kết nối remote."""

import json
import re
import socket

# Domain server remote — dùng mặc định khi ô DNS trống / profile chưa có dns_host
DEFAULT_SERVER_DNS = "trungtamanninhmang.xyz"

_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$",
)


def is_ipv4(host: str) -> bool:
    return bool(_IPV4_RE.match((host or "").strip()))


def is_hostname(host: str) -> bool:
    host = (host or "").strip()
    return bool(host) and not is_ipv4(host)


def resolve_ipv4(host: str, timeout: float = 5.0) -> str:
    """Resolve hostname → IPv4. Trả về '' nếu thất bại."""
    host = (host or "").strip()
    if not host:
        return ""
    if is_ipv4(host):
        return host
    try:
        old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(timeout)
        try:
            infos = socket.getaddrinfo(
                host, None, socket.AF_INET, socket.SOCK_STREAM,
            )
        finally:
            socket.setdefaulttimeout(old_timeout)
        if not infos:
            return ""
        return infos[0][4][0]
    except OSError:
        return ""


def parse_remote_dns_payload(text: str) -> str:
    """Đọc hostname từ file dns.host hoặc dns.json trên server."""
    text = (text or "").strip()
    if not text:
        return ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                for key in ("host", "dns", "hostname", "name"):
                    val = (data.get(key) or "").strip()
                    if val and not is_ipv4(val):
                        return val
        except (json.JSONDecodeError, TypeError):
            pass
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            return parse_remote_dns_payload(line)
        if "=" in line:
            _, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            if val and not is_ipv4(val):
                return val
        elif not is_ipv4(line):
            return line
    return ""


def canonicalize_dns_label(host: str, default_dns: str = DEFAULT_SERVER_DNS) -> str:
    """Bổ sung TLD khi user chỉ gõ nhãn (vd. trungtamanninhmang → .xyz)."""
    host = (host or "").strip()
    if not host or is_ipv4(host) or "." in host:
        return host
    dd = (default_dns or DEFAULT_SERVER_DNS).strip()
    if not dd or "." not in dd:
        return host
    label = dd.split(".", 1)[0]
    if host.lower() == label.lower():
        return dd
    suffix = dd.split(".", 1)[1]
    return f"{host}.{suffix}"


def prepare_connect_host(
    host: str,
    dns_host: str = "",
    *,
    require_resolve: bool = True,
    default_dns: str = "",
) -> dict:
    """
    Chuẩn bị đích kết nối — ưu tiên DNS/DDNS để bắt IP mới sau khi server cập nhật.
    require_resolve=False: vẫn trả hostname khi DNS chưa resolve (dùng cho RDP/mstsc).
    Trả về: connect_host, resolved_ip, dns_host, changed, error
    """
    host = (host or "").strip()
    dns_host = (dns_host or "").strip()
    dd = (default_dns or DEFAULT_SERVER_DNS).strip()
    if host:
        host = canonicalize_dns_label(host, dd)
    if dns_host:
        dns_host = canonicalize_dns_label(dns_host, dd)

    if dns_host and is_ipv4(dns_host):
        dns_host = ""

    if dns_host:
        canonical = dns_host
    elif is_hostname(host):
        canonical = host
        dns_host = host
    elif host:
        return {
            "connect_host": host,
            "resolved_ip": host,
            "dns_host": "",
            "changed": False,
            "error": "",
        }
    else:
        return {
            "connect_host": "",
            "resolved_ip": "",
            "dns_host": "",
            "changed": False,
            "error": "Thiếu Host / IP hoặc DNS.",
        }

    resolved = resolve_ipv4(canonical)
    if not resolved:
        return {
            "connect_host": canonical,
            "resolved_ip": "",
            "dns_host": canonical,
            "changed": False,
            "error": (
                f"Không resolve được DNS «{canonical}»."
                if require_resolve
                else ""
            ),
        }

    old_ip = host if is_ipv4(host) else ""
    changed = bool(old_ip and old_ip != resolved)
    return {
        "connect_host": canonical,
        "resolved_ip": resolved,
        "dns_host": canonical,
        "changed": changed,
        "error": "",
    }


def refresh_profile_entry(profile: dict, default_dns: str = "") -> dict:
    """Cập nhật IP trong profile theo DNS hiện tại."""
    if not profile:
        return profile
    dns_host = (profile.get("dns_host") or default_dns or "").strip()
    host = (profile.get("host") or "").strip()
    info = prepare_connect_host(host, dns_host)
    if info.get("error") or not info.get("resolved_ip"):
        return profile
    updated = dict(profile)
    if info["dns_host"]:
        updated["dns_host"] = info["dns_host"]
    if info["resolved_ip"]:
        updated["host"] = info["resolved_ip"]
    return updated
