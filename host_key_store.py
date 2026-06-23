"""Lưu và kiểm tra SSH host key — chống MITM (thay AutoAddPolicy)."""

import hashlib
import os
import socket
import stat

import paramiko

from profile_store import STORE_DIR, secure_chmod, secure_ensure_store_dir

KNOWN_HOSTS_FILE = os.path.join(STORE_DIR, "known_hosts")


def format_host_id(host: str, port: int) -> str:
    port = int(port)
    host = (host or "").strip()
    if port == 22:
        return host
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{host}:{port}"


def _extract_pkey(entry):
    """Lấy PKey từ RSAKey hoặc paramiko HostKeys.SubDict."""
    if entry is None:
        return None
    if hasattr(entry, "asbytes"):
        return entry
    if hasattr(entry, "key"):
        return entry.key
    if hasattr(entry, "values"):
        for val in entry.values():
            if hasattr(val, "asbytes"):
                return val
    return None


def fingerprint_sha256(key) -> str:
    pkey = _extract_pkey(key)
    if pkey is None:
        raise ValueError("Không đọc được host key từ known_hosts")
    digest = hashlib.sha256(pkey.asbytes()).hexdigest()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


def fetch_remote_key(host: str, port: int, timeout: float = 5):
    """Lấy host key trước khi đăng nhập (không gửi mật khẩu)."""
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    transport = None
    try:
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=timeout)
        return transport.get_remote_server_key()
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        try:
            sock.close()
        except Exception:
            pass


def _load_hostkeys():
    secure_ensure_store_dir()
    hk = paramiko.HostKeys()
    if os.path.isfile(KNOWN_HOSTS_FILE):
        try:
            hk.load(KNOWN_HOSTS_FILE)
        except (OSError, paramiko.SSHException):
            pass
    return hk


def _save_hostkeys(hk):
    secure_ensure_store_dir()
    hk.save(KNOWN_HOSTS_FILE)
    secure_chmod(KNOWN_HOSTS_FILE)


def _stored_key_for(host_id: str):
    hk = _load_hostkeys()
    if host_id not in hk:
        return None
    return _extract_pkey(hk[host_id])


def peek_host_key_status(host: str, port: int):
    """
    Chỉ đọc đĩa — không mạng (không block UI).
    Trả về (status, fingerprint, old_fingerprint, stored_key).
    status: trusted | absent
    """
    host_id = format_host_id(host, port)
    stored_key = _stored_key_for(host_id)
    if stored_key is None:
        return "absent", None, None, None
    fp = fingerprint_sha256(stored_key)
    return "trusted", fp, fp, stored_key


def verify_host_key_live(host: str, port: int, timeout: float = 4):
    """
    Lấy key từ server và so với known_hosts.
    Trả về (status, fp, old_fp, key).
    status: trusted | unknown | changed
    """
    host_id = format_host_id(host, port)
    key = fetch_remote_key(host, port, timeout=timeout)
    fp = fingerprint_sha256(key)
    stored_key = _stored_key_for(host_id)
    if stored_key is None:
        return "unknown", fp, None, key
    old_fp = fingerprint_sha256(stored_key)
    if old_fp != fp:
        return "changed", fp, old_fp, key
    return "trusted", fp, old_fp, key


def trust_host_key(host: str, port: int, key) -> str:
    host_id = format_host_id(host, port)
    hk = _load_hostkeys()
    hk.add(host_id, key.get_name(), key)
    _save_hostkeys(hk)
    return fingerprint_sha256(key)


def apply_known_hosts(client: paramiko.SSHClient, hostname: str, port: int):
    secure_ensure_store_dir()
    host_id = format_host_id(hostname, port)
    if os.path.isfile(KNOWN_HOSTS_FILE):
        client.load_host_keys(KNOWN_HOSTS_FILE)
    stored_key = _stored_key_for(host_id)
    if stored_key is not None:
        client.get_host_keys().add(host_id, stored_key.get_name(), stored_key)
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
