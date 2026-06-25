import os
import socket
import select
import stat
import threading
import paramiko

from host_key_store import apply_known_hosts
from sftp_paths import (
    is_windows_sftp_path,
    join_windows_sftp,
    normalize_windows_sftp,
    safe_sftp_entry_name,
    sftp_list_path,
)


class PortForwardHandle:
  """Handle cho một tunnel port forward đang chạy."""

  def __init__(self, label, local_port, server, thread):
    self.label = label
    self.local_port = local_port
    self.server = server
    self.thread = thread

  def stop(self):
    try:
      self.server.shutdown()
      self.server.server_close()
    except Exception:
      pass


_WIN_INFO_CMD = (
    'powershell -NoProfile -NonInteractive -Command "'
    "$os=Get-CimInstance Win32_OperatingSystem;"
    "$cpu=(Get-CimInstance Win32_Processor|Select-Object -First 1).Name;"
    "$disks=Get-CimInstance Win32_LogicalDisk|Where-Object DriveType -eq 3;"
    "$up=((Get-Date)-$os.LastBootUpTime).ToString();"
    "Write-Output ('PETTIE_HOST='+$env:COMPUTERNAME);"
    "Write-Output ('PETTIE_OS='+$os.Caption);"
    "Write-Output ('PETTIE_CPU='+$cpu);"
    "Write-Output ('PETTIE_RAM='+[string]([math]::Round($os.FreePhysicalMemory/1024))"
    "+' MB free / '+[string]([math]::Round($os.TotalVisibleMemorySize/1024))+' MB total');"
    "$d=($disks|ForEach-Object{$_.DeviceID+' '+[math]::Round($_.FreeSpace/1GB,1)"
    "+'GB free / '+[math]::Round($_.Size/1GB,1)+'GB'}) -join '; ';"
    "Write-Output ('PETTIE_DISK='+$d);"
    "Write-Output ('PETTIE_UPTIME='+$up)"
    '"'
)

_LINUX_INFO_CMD = (
    "echo PETTIE_HOST=$(hostname); "
    "echo PETTIE_OS=$(uname -a); "
    "echo PETTIE_CPU=$( (grep -m1 'model name' /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs)"
    " ) cores:$(nproc 2>/dev/null); "
    "echo PETTIE_RAM=$(free -h 2>/dev/null | awk '/Mem:/{print $3\" / \"$2}'); "
    "echo PETTIE_DISK=$(df -h 2>/dev/null | awk 'NR>1 && $1 ~ /^\\// "
    "{print $1\" \"$3\"/\"$2}' | head -6 | tr '\\n' '; '); "
    "echo PETTIE_UPTIME=$(uptime -p 2>/dev/null || uptime)"
)


class SSHManager:
  def __init__(self):
    self.ssh_client = None
    self.sftp_client = None
    self.remote_os = None
    self._forward_handles = []
    self._last_host = None
    self._last_port = 22
    self._session_password = None
    self._session_user = None
    self._remote_home_cache = None
    self._system_info_cache = None
    self._ssh_lock = threading.Lock()
    self._sftp_lock = threading.Lock()
    self._os_ready_callback = None

  def set_os_ready_callback(self, callback):
    """Gọi khi nhận diện OS xong (từ thread nền) — cập nhật UI."""
    self._os_ready_callback = callback

  @staticmethod
  def _password_to_bytes(password):
    if not password:
      return None
    if isinstance(password, (bytes, bytearray)):
      return bytes(password)
    return str(password).encode("utf-8")

  @staticmethod
  def _wipe_bytes(buf):
    if isinstance(buf, bytearray):
      for i in range(len(buf)):
        buf[i] = 0

  def get_session_password(self):
    """Mật khẩu phiên hiện tại — chỉ trong RAM, không ghi đĩa."""
    if not self._session_password:
      return ""
    return self._session_password.decode("utf-8", errors="replace")

  def get_session_user(self):
    return self._session_user or ""

  def get_session_host(self):
    return self._last_host or ""

  def connect(self, hostname, username, password, port=22, key_path=None, timeout=5):
    """Kết nối SSH. Trả về (thành công, thông báo lỗi)."""
    with self._ssh_lock:
      return self._connect_locked(
          hostname, username, password, port, key_path, timeout,
      )

  def _connect_locked(self, hostname, username, password, port, key_path, timeout):
    self._disconnect_unlocked()
    try:
      client = paramiko.SSHClient()
      apply_known_hosts(client, hostname, int(port))
      kwargs = {
        "hostname": hostname,
        "port": int(port),
        "username": username,
        "timeout": max(3, int(timeout)),
      }
      pwd_bytes = self._password_to_bytes(password)
      if key_path:
        from security_utils import validate_ssh_key_path
        try:
          key_path = validate_ssh_key_path(key_path)
        except ValueError as e:
          return False, str(e)
      if key_path and os.path.isfile(key_path):
        kwargs["key_filename"] = key_path
        if pwd_bytes:
          kwargs["password"] = pwd_bytes.decode("utf-8", errors="replace")
      elif pwd_bytes:
        kwargs["password"] = pwd_bytes.decode("utf-8", errors="replace")

      client.connect(**kwargs)
      sftp = client.open_sftp()
      self.ssh_client = client
      self.sftp_client = sftp
      self.remote_os = self._detect_os_quick()
      self._last_host = hostname
      self._last_port = int(port)
      self._session_user = username
      self._session_password = bytearray(pwd_bytes) if pwd_bytes else None
      self._remote_home_cache = None
      self._system_info_cache = None
      threading.Thread(target=self._post_connect_setup, daemon=True).start()
      return True, ""
    except Exception as e:
      self._disconnect_unlocked()
      return False, self._format_connect_error(hostname, port, e)

  @staticmethod
  def _format_connect_error(hostname, port, exc):
    text = str(exc).strip() or "Không thể kết nối"
    low = text.lower()
    if "timed out" in low or "timeout" in low:
      return f"Không kết nối được tới {hostname}:{port} (hết thời gian chờ)."
    if "name or service not known" in low or "nodename nor servname" in low:
      return f"Không tìm thấy máy chủ «{hostname}» — kiểm tra lại IP/hostname."
    if "host key" in low or "not found in known_hosts" in low:
      return (
        "Host key chưa được tin cậy hoặc đã thay đổi. "
        "Kết nối lại và xác nhận fingerprint SHA256."
      )
    if "authentication failed" in low or "auth" in low:
      return "Máy chủ phản hồi nhưng sai tên đăng nhập hoặc mật khẩu."
    if "connection refused" in low:
      return f"{hostname}:{port} từ chối kết nối — kiểm tra SSH đã bật và đúng cổng."
    if "no route to host" in low or "network is unreachable" in low:
      return f"Không có đường tới {hostname} — kiểm tra mạng hoặc IP."
    return f"Không kết nối được tới {hostname}:{port}.\n{text}"

  def test_tcp(self, hostname, port, timeout=3):
    try:
      sock = socket.create_connection((hostname, int(port)), timeout=timeout)
      sock.close()
      return True, "Host reachable"
    except socket.timeout:
      return False, f"Không phản hồi sau {int(timeout)} giây"
    except OSError as e:
      return False, str(e)

  def get_host_key_fingerprint(self):
    if not self.ssh_client:
      return None
    try:
      from host_key_store import fingerprint_sha256
      key = self.ssh_client.get_transport().get_remote_server_key()
      return fingerprint_sha256(key)
    except Exception:
      return None

  def _detect_os_quick(self):
    """Nhận diện nhanh qua SFTP (Windows OpenSSH → /C:/Users/...)."""
    if not self.sftp_client:
      return None
    try:
      path = self.sftp_client.normalize(".")
      if path and is_windows_sftp_path(path):
        return "windows"
      if path and path.startswith("/") and not is_windows_sftp_path(path):
        return "linux"
    except Exception:
      pass
    return None

  def _notify_os_ready(self):
    cb = self._os_ready_callback
    if cb and self.remote_os:
      try:
        cb(self.remote_os)
      except Exception:
        pass

  def _post_connect_setup(self):
    """Nền: nhận diện OS + cache — không chặn bước đăng nhập."""
    try:
      detected = self.detect_remote_os() or "unknown"
      self.remote_os = detected
    except Exception:
      self.remote_os = self.remote_os or "unknown"
    self._notify_os_ready()
    try:
      self.get_remote_home(fast_only=True)
    except Exception:
      pass
    try:
      self.prefetch_system_info()
    except Exception:
      pass

  def prefetch_system_info(self):
    if not self.ssh_client:
      return
    self._system_info_cache = self._collect_system_info()

  def peek_system_info(self):
    return self._system_info_cache

  def get_remote_home(self, fast_only=False):
    if self._remote_home_cache:
      return self._remote_home_cache
    if not self.sftp_client:
      return "."

    try:
      path = self.sftp_client.normalize(".")
      if path and path not in (".", "/"):
        if self.remote_os == "windows" or is_windows_sftp_path(path):
          path = normalize_windows_sftp(path)
        self._remote_home_cache = path
        return path
    except Exception:
      pass

    if fast_only:
      remote_os = self.remote_os or "unknown"
      return "C:\\" if remote_os == "windows" else "/"

    remote_os = self.remote_os or self.detect_remote_os()
    if remote_os == "windows":
      try:
        exit_code, out, _ = self._exec_and_read("cmd /c echo %USERPROFILE%", timeout=4)
        if exit_code == 0 and out:
          path = out.strip()
          if path and "%" not in path:
            path = normalize_windows_sftp(path)
            self._remote_home_cache = path
            return path
      except Exception:
        pass
    else:
      try:
        exit_code, out, _ = self._exec_and_read("echo $HOME", timeout=4)
        if exit_code == 0 and out:
          path = out.strip()
          if path:
            self._remote_home_cache = path
            return path
      except Exception:
        pass

    fallback = "/C:/" if remote_os == "windows" else "/"
    self._remote_home_cache = fallback
    return fallback

  def list_remote_dir(self, remote_path="."):
    if not self.sftp_client:
      return None
    remote_path = sftp_list_path(
        remote_path,
        self.remote_os or ("windows" if is_windows_sftp_path(remote_path) else "linux"),
    )
    try:
      with self._sftp_lock:
        files = self.sftp_client.listdir_attr(remote_path)
      result = []
      for f in files:
        name = safe_sftp_entry_name(f.filename)
        if not name:
          continue
        is_dir = stat.S_ISDIR(f.st_mode)
        size = int(f.st_size)
        if size < 0:
          size += 1 << 32
        result.append({
          "name": name,
          "size": size,
          "is_dir": is_dir,
          "mtime": f.st_mtime,
        })
      return result
    except Exception as e:
      print(f"Lỗi đọc thư mục remote: {e}")
      return None

  def search_remote_files(self, root_path, pattern, max_results=200):
    """Tìm file theo tên (đệ quy, giới hạn kết quả)."""
    if not self.sftp_client:
      return []
    pattern = pattern.lower()
    found = []

    def walk(path, depth=0):
      if len(found) >= max_results or depth > 8:
        return
      try:
        for entry in self.sftp_client.listdir_attr(path):
          name = safe_sftp_entry_name(entry.filename)
          if not name:
            continue
          if self.remote_os == "windows" or is_windows_sftp_path(path):
            full = join_windows_sftp(path, name)
          else:
            full = f"{path.rstrip('/')}/{name}"

          if pattern in name.lower():
            found.append({
              "path": full,
              "name": name,
              "is_dir": stat.S_ISDIR(entry.st_mode),
              "size": entry.st_size,
            })
          if stat.S_ISDIR(entry.st_mode) and name not in (".", ".."):
            walk(full, depth + 1)
      except Exception:
        pass

    walk(root_path)
    return found

  def rename_remote(self, old_path, new_path):
    if not self.sftp_client:
      return False
    try:
      self.sftp_client.rename(old_path, new_path)
      return True
    except Exception as e:
      print(f"Lỗi rename: {e}")
      return False

  def mkdir(self, remote_path):
    if not self.sftp_client:
      return False
    try:
      self.sftp_client.mkdir(remote_path)
      return True
    except Exception as e:
      print(f"Lỗi mkdir: {e}")
      return False

  def remove_file(self, remote_path):
    if not self.sftp_client:
      return False
    try:
      self.sftp_client.remove(remote_path)
      return True
    except Exception as e:
      print(f"Lỗi xóa file: {e}")
      return False

  def remove_dir(self, remote_path):
    if not self.sftp_client:
      return False
    try:
      self.sftp_client.rmdir(remote_path)
      return True
    except Exception as e:
      print(f"Lỗi xóa thư mục: {e}")
      return False

  def get_remote_file_size(self, remote_path):
    if not self.sftp_client:
      return 0
    try:
      with self._sftp_lock:
        attr = self.sftp_client.stat(remote_path)
      size = int(attr.st_size)
      if size < 0:
        size += 1 << 32
      return size
    except Exception:
      return 0

  def upload_file(self, local_path, remote_path, callback=None):
    if not self.sftp_client:
      return False
    try:
      with self._sftp_lock:
        self.sftp_client.put(local_path, remote_path, callback=callback)
      return True
    except Exception as e:
      print(f"Lỗi upload: {e}")
      return False

  def download_file(self, remote_path, local_path, callback=None):
    if not self.sftp_client:
      return False
    try:
      with self._sftp_lock:
        # prefetch=False — stream trực tiếp ra đĩa, tránh nạp cả ISO vào RAM.
        self.sftp_client.get(
            remote_path, local_path, callback=callback, prefetch=False,
        )
      return True
    except Exception as e:
      print(f"Lỗi download: {e}")
      return False

  def exec_command(self, command, timeout=30):
    if not self.ssh_client:
      return -1, "", "Chưa kết nối"
    return self._exec_and_read(command, timeout=timeout)

  def fetch_remote_dns_host(self):
    """
    Đọc hostname DDNS server publish (khi server cập nhật DNS).
    File chuẩn: ~/.pettie-server/dns.host hoặc dns.json
    """
    from dns_utils import parse_remote_dns_payload

    if not self.ssh_client:
      return ""
    if self.remote_os == "windows":
      cmd = (
          "cmd /c \""
          "for %F in (dns.host dns.json) do @if exist %USERPROFILE%\\.pettie-server\\%F "
          "type %USERPROFILE%\\.pettie-server\\%F\""
      )
    else:
      cmd = (
          "sh -c 'for f in dns.host dns.json; do "
          "p=\"$HOME/.pettie-server/$f\"; "
          "[ -f \"$p\" ] && cat \"$p\" && break; "
          "done'"
      )
    code, out, _ = self.exec_command(cmd, timeout=8)
    if code != 0 or not (out or "").strip():
      return ""
    from security_utils import validate_server_pushed_dns
    host = parse_remote_dns_payload(out)
    if not host:
      return ""
    try:
      return validate_server_pushed_dns(host)
    except ValueError:
      return ""

  def _parse_pettie_info(self, text):
    data = {}
    for line in (text or "").splitlines():
      line = line.strip()
      if line.startswith("PETTIE_") and "=" in line:
        key, val = line.split("=", 1)
        data[key] = val.strip()
    return data

  def _info_from_pettie(self, data):
    labels = (
      ("Hostname", "PETTIE_HOST"),
      ("OS", "PETTIE_OS"),
      ("CPU", "PETTIE_CPU"),
      ("RAM", "PETTIE_RAM"),
      ("Disk", "PETTIE_DISK"),
      ("Uptime", "PETTIE_UPTIME"),
    )
    items = []
    for label, key in labels:
      items.append({"label": label, "value": (data.get(key) or "(n/a)")[:500]})
    return {
      "os": self.remote_os or "unknown",
      "hostname": data.get("PETTIE_HOST", ""),
      "items": items,
    }

  def get_system_info(self, use_cache=True, force_refresh=False):
    """Trả cache ngay nếu có; force_refresh để làm mới."""
    if not self.ssh_client:
      return {"os": self.remote_os or "unknown", "hostname": "", "items": []}
    if use_cache and not force_refresh and self._system_info_cache:
      return self._system_info_cache
    info = self._collect_system_info()
    self._system_info_cache = info
    return info

  def _collect_system_info(self):
    """Thu thập thông tin hệ thống — một lệnh SSH thay vì 6 lần."""
    info = {"os": self.remote_os or "unknown", "hostname": "", "items": []}
    if not self.ssh_client:
      return info

    cmd = _WIN_INFO_CMD if self.remote_os == "windows" else _LINUX_INFO_CMD
    timeout = 20 if self.remote_os == "windows" else 12
    try:
      code, out, err = self._exec_and_read(cmd, timeout=timeout)
      if code == 0 and "PETTIE_HOST=" in out:
        return self._info_from_pettie(self._parse_pettie_info(out))
    except Exception:
      pass

    return self._get_system_info_parallel()

  def _get_system_info_parallel(self):
    """Fallback: chạy song song nếu lệnh gộp thất bại."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    info = {"os": self.remote_os or "unknown", "hostname": "", "items": []}
    if self.remote_os == "windows":
      specs = [
        ("Hostname", "hostname"),
        ("OS", 'cmd /c ver'),
        ("CPU", 'wmic cpu get name /value 2>nul'),
        ("RAM", 'wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /value 2>nul'),
        ("Disk", 'wmic logicaldisk where drivetype=3 get DeviceID,FreeSpace,Size /value 2>nul'),
        ("Uptime", 'cmd /c net statistics workstation | find "Statistics since"'),
      ]
    else:
      specs = [
        ("Hostname", "hostname"),
        ("OS", "uname -a"),
        ("CPU", "nproc 2>/dev/null; grep -m1 'model name' /proc/cpuinfo 2>/dev/null"),
        ("RAM", "free -h 2>/dev/null | grep Mem"),
        ("Disk", "df -h 2>/dev/null | head -8"),
        ("Uptime", "uptime 2>/dev/null"),
      ]

    def run_one(pair):
      label, command = pair
      try:
        code, out, err = self._exec_and_read(command, timeout=10)
        val = (out or err or "(n/a)").strip()[:500]
        return label, val, out.strip() if label == "Hostname" and out else ""
      except Exception as e:
        return label, str(e), ""

    results = {}
    host = ""
    with ThreadPoolExecutor(max_workers=6) as pool:
      futures = {pool.submit(run_one, s): s[0] for s in specs}
      for fut in as_completed(futures):
        label, val, h = fut.result()
        results[label] = val
        if h:
          host = h
    info["hostname"] = host
    for label, _ in specs:
      info["items"].append({"label": label, "value": results.get(label, "(n/a)")})
    return info

  def _forward_handler(self, chan, src):
    while True:
      r, _, _ = select.select([chan, src], [], [], 1)
      if chan in r:
        data = chan.recv(1024)
        if not data:
          break
        src.send(data)
      if src in r:
        data = src.recv(1024)
        if not data:
          break
        chan.send(data)
    chan.close()
    src.close()

  def start_local_forward(self, local_port, remote_host, remote_port, label=None):
    """Local forward: chỉ bind 127.0.0.1 — không lộ ra LAN."""
    if not self.ssh_client:
      return None, "Chưa kết nối SSH"
    from security_utils import validate_forward_host
    try:
      remote_host = validate_forward_host(remote_host)
    except ValueError as e:
      return None, str(e)
    local_port = int(local_port)
    if local_port < 1024 or local_port > 65535:
      return None, "Cổng local phải từ 1024 đến 65535."
    transport = self.ssh_client.get_transport()
    if not transport or not transport.is_active():
      return None, "Transport không hoạt động"

    label = label or f"local:{local_port}->{remote_host}:{remote_port}"

    def handle(client_sock, addr):
      try:
        chan = transport.open_channel(
          "direct-tcpip",
          (remote_host, int(remote_port)),
          addr,
        )
        if chan is None:
          client_sock.close()
          return
        threading.Thread(
          target=self._forward_handler,
          args=(chan, client_sock),
          daemon=True,
        ).start()
      except Exception:
        client_sock.close()

    try:
      server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
      server.bind(("127.0.0.1", int(local_port)))
      server.listen(32)
      server.settimeout(1)

      def serve():
        while True:
          try:
            client, addr = server.accept()
            threading.Thread(
              target=handle, args=(client, addr), daemon=True
            ).start()
          except OSError:
            break

      t = threading.Thread(target=serve, daemon=True)
      t.start()
      h = PortForwardHandle(label, local_port, server, t)
      self._forward_handles.append(h)
      return h, None
    except Exception as e:
      return None, str(e)

  def start_dynamic_forward(self, local_port, label=None):
    """SOCKS proxy động trên local_port."""
    if not self.ssh_client:
      return None, "Chưa kết nối SSH"
    transport = self.ssh_client.get_transport()

    def handle(client_sock, addr):
      try:
        chan = transport.open_channel("direct-tcpip", addr, ("127.0.0.1", local_port))
      except Exception:
        client_sock.close()
        return
      # Simplified — full SOCKS needs more; use direct-tcpip for RDP mainly
      client_sock.close()

    # Paramiko dynamic forward via Handler class is complex; use local forward for RDP
    return self.start_local_forward(local_port, "127.0.0.1", 3389, label or f"socks:{local_port}")

  def stop_all_forwards(self):
    for h in self._forward_handles:
      h.stop()
    self._forward_handles.clear()

  def list_forwards(self):
    return [
      {"label": h.label, "port": h.local_port}
      for h in self._forward_handles
    ]

  def _exec_and_read(self, command, timeout=8):
    if not self.ssh_client:
      return -1, "", "Chưa kết nối"
    with self._ssh_lock:
      stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=timeout)
      out = stdout.read().decode("utf-8", errors="replace").strip()
      err = stderr.read().decode("utf-8", errors="replace").strip()
      exit_code = stdout.channel.recv_exit_status()
    return exit_code, out, err

  def detect_remote_os(self):
    if not self.ssh_client:
      return None
    quick = self._detect_os_quick()
    if quick:
      return quick
    for command in (
        'cmd /c "if defined OS echo %OS%"',
        "powershell -NoProfile -Command \"Write-Output $env:OS\"",
    ):
      try:
        exit_code, out, _ = self._exec_and_read(command, timeout=5)
        if exit_code == 0 and out:
          low = out.lower()
          if "windows" in low:
            return "windows"
      except Exception:
        pass
    try:
      exit_code, out, _ = self._exec_and_read("uname -s", timeout=3)
      if exit_code == 0 and out:
        name = out.strip()
        if name == "Linux":
          return "linux"
        if name in ("Darwin", "FreeBSD", "OpenBSD", "NetBSD"):
          return "unix"
        if "nt" in name.lower() or "windows" in name.lower():
          return "windows"
    except Exception:
      pass
    return "unknown"

  def open_shell_channel(self):
    if not self.ssh_client:
      return None
    return self.ssh_client.invoke_shell(term="xterm-256color", width=120, height=32)

  def disconnect(self):
    with self._ssh_lock:
      self._disconnect_unlocked()

  def _disconnect_unlocked(self):
    self.stop_all_forwards()
    if self.sftp_client:
      self.sftp_client.close()
      self.sftp_client = None
    if self.ssh_client:
      self.ssh_client.close()
      self.ssh_client = None
    self.remote_os = None
    if self._session_password is not None:
      self._wipe_bytes(self._session_password)
    self._session_password = None
    self._session_user = None
    self._remote_home_cache = None
    self._system_info_cache = None
