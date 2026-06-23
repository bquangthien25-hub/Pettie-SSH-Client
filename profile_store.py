"""Lưu profile kết nối và lịch sử — JSON local."""

import json
import os
import stat
from datetime import datetime

STORE_DIR = os.path.join(os.path.expanduser("~"), ".pettie-ssh")


def secure_chmod(path: str):
    if os.name == "nt":
        return
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def secure_ensure_store_dir():
    os.makedirs(STORE_DIR, exist_ok=True)
    if os.name != "nt":
        try:
            os.chmod(STORE_DIR, stat.S_IRWXU)
        except OSError:
            pass
PROFILES_FILE = os.path.join(STORE_DIR, "profiles.json")
HISTORY_FILE = os.path.join(STORE_DIR, "history.json")
SETTINGS_FILE = os.path.join(STORE_DIR, "settings.json")
CONFIG_FILE = os.path.join(STORE_DIR, "config.json")
SNIPPETS_FILE = os.path.join(STORE_DIR, "snippets.json")


def _ensure_dir():
    secure_ensure_store_dir()


def _load(path, default):
    _ensure_dir()
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save(path, data):
    _ensure_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    secure_chmod(path)


def list_profiles():
    return _load(PROFILES_FILE, [])


def save_profile(name, host, port, user, notes="", key_path="", dns_host=""):
    profiles = list_profiles()
    port_str = str(port).strip() or "22"
    protocol = "rdp" if port_str == "3389" else "ssh"
    entry = {
        "name": name,
        "host": host,
        "dns_host": (dns_host or "").strip(),
        "port": port_str,
        "user": user,
        "protocol": protocol,
        "key_path": key_path or "",
        "notes": notes,
        "updated": datetime.now().isoformat(),
    }
    profiles = [p for p in profiles if p.get("name") != name]
    profiles.insert(0, entry)
    _save(PROFILES_FILE, profiles[:50])
    return entry


def delete_profile(name):
    profiles = [p for p in list_profiles() if p.get("name") != name]
    _save(PROFILES_FILE, profiles)


def update_profile_fields(name, **fields):
    """Cập nhật một phần profile (vd. dns_host / host sau khi resolve DNS)."""
    profiles = list_profiles()
    changed = False
    for entry in profiles:
        if entry.get("name") != name:
            continue
        for key, val in fields.items():
            if val is not None:
                entry[key] = val
        entry["updated"] = datetime.now().isoformat()
        changed = True
        break
    if changed:
        _save(PROFILES_FILE, profiles)
    return changed


def refresh_all_profile_dns(refresh_fn):
    """Gọi refresh_fn(profile) cho từng profile có dns_host — lưu nếu IP đổi."""
    profiles = list_profiles()
    if not profiles:
        return []
    updated_names = []
    new_profiles = []
    for entry in profiles:
        dns_host = (entry.get("dns_host") or "").strip()
        if not dns_host:
            new_profiles.append(entry)
            continue
        refreshed = refresh_fn(entry, get_default_dns_host())
        if refreshed.get("host") != entry.get("host"):
            updated_names.append(refreshed.get("name", ""))
        new_profiles.append(refreshed)
    if updated_names:
        _save(PROFILES_FILE, new_profiles)
    return [n for n in updated_names if n]


def add_history(host, port, user, success):
    """Giữ API tương thích — không lưu host/user lên đĩa (bảo mật)."""
    _ = (host, port, user, success)


def list_history():
    return _load(HISTORY_FILE, [])


def clear_connection_history():
    """Xóa lịch sử kết nối (host/user) trên đĩa."""
    _save(HISTORY_FILE, [])


def get_settings():
    return _load(SETTINGS_FILE, {
        "auto_terminal": False,
        "auto_file_manager": False,
        "auto_rdp": False,
        "auto_reconnect": False,
        "rdp_local_port": 33890,
        "socks_port": 1080,
        "theme_id": "teal",
        "color_mode": "dark",
        "background_id": "sakura_sky",
        "bg_overlay": 0.45,
        "transparent_ui": False,
        "visual_style": "classic",
        "start_with_windows": False,
        "language": "vi",
    })


def save_settings(data):
    cur = get_settings()
    cur.update(data)
    _save(SETTINGS_FILE, cur)


def get_config():
    from dns_utils import DEFAULT_SERVER_DNS
    return _load(CONFIG_FILE, {
        "custom_background_path": "",
        "server_dns_host": DEFAULT_SERVER_DNS,
    })


def get_default_dns_host() -> str:
    """Hostname DDNS mặc định của server (đọc từ config hoặc hằng số trong dns_utils)."""
    from dns_utils import DEFAULT_SERVER_DNS
    return (get_config().get("server_dns_host") or DEFAULT_SERVER_DNS).strip()


def save_config(data):
    cur = get_config()
    cur.update(data)
    _save(CONFIG_FILE, cur)


def list_snippets():
    default = [
        {"name": "Disk usage", "cmd": "df -h 2>/dev/null || wmic logicaldisk get size,freespace,caption"},
        {"name": "Memory", "cmd": "free -h 2>/dev/null || systeminfo | findstr Memory"},
        {"name": "Uptime", "cmd": "uptime 2>/dev/null || net statistics workstation"},
        {"name": "Processes", "cmd": "ps aux --sort=-%mem 2>/dev/null | head -15 || tasklist"},
    ]
    return _load(SNIPPETS_FILE, default)


def save_snippets(snippets):
    _save(SNIPPETS_FILE, snippets)
