"""Kiểm thử tự động — bao gồm các kịch bản tấn công khó hơn."""

import inspect
import sys

from dns_utils import parse_remote_dns_payload
from profile_store import _sanitize_profile
from security_utils import (
    validate_ssh_host,
    validate_ssh_user,
    validate_ssh_port,
    validate_ssh_key_path,
    validate_remote_entry_name,
    validate_search_pattern,
    validate_remote_shell_command,
    validate_rdp_ipv4,
    validate_rdp_domain,
    validate_windows_logon,
    validate_profile_name,
    validate_server_pushed_dns,
    is_loopback_or_linklocal_ip,
    ssh_argv,
)
from sftp_paths import safe_sftp_entry_name, join_windows_sftp


def _expect_fail(fn, value, label):
    try:
        fn(value)
        print(f"FAIL {label}: expected rejection for {value!r}")
        return False
    except ValueError:
        return True


def _expect_ok(fn, value, label):
    try:
        result = fn(value)
        print(f"OK   {label}: {value!r} -> {result!r}")
        return True
    except ValueError as e:
        print(f"FAIL {label}: {value!r} rejected: {e}")
        return False


def test_sftp_traversal():
    ok = True
    evil_names = [
        "..",
        "../etc/passwd",
        "..\\windows\\system32",
        "foo/../../bar",
        "normal\x00evil",
        "a" * 300,
    ]
    for name in evil_names:
        if safe_sftp_entry_name(name) is not None:
            print(f"FAIL sftp_name: {name!r} should be blocked")
            ok = False
    if safe_sftp_entry_name("readme.txt") != "readme.txt":
        print("FAIL sftp_name: legitimate name blocked")
        ok = False
    else:
        print("OK   sftp_name: traversal names blocked")

    try:
        join_windows_sftp("/C:/Users", "../Windows/System32")
        print("FAIL join_windows_sftp: traversal not blocked")
        ok = False
    except ValueError:
        print("OK   join_windows_sftp: rejects traversal")
    return ok


def test_dns_poisoning():
    ok = True
    payloads = [
        "127.0.0.1",
        "localhost",
        "evil.com\nattacker.com",
        "host=evil.com",
        '{"host": "127.0.0.1"}',
        "x" * 600,
    ]
    for p in payloads:
        parsed = parse_remote_dns_payload(p)
        if parsed in ("127.0.0.1", "localhost"):
            print(f"FAIL dns_parse: accepted dangerous {parsed!r} from {p!r}")
            ok = False
        if parsed and "\n" in parsed:
            print(f"FAIL dns_parse: newline in {parsed!r}")
            ok = False
    legit = parse_remote_dns_payload("myserver.example.com")
    if legit != "myserver.example.com":
        print(f"FAIL dns_parse: legit hostname got {legit!r}")
        ok = False
    else:
        print("OK   dns_parse: legit hostname accepted, dangerous rejected")

    for host in ("localhost",):
        ok &= _expect_fail(validate_server_pushed_dns, host, "server_dns")
    return ok


def test_freerdp_injection():
    ok = True
    for domain in ("corp /p:evil", "dom ain", "evil;calc", "/admin"):
        ok &= _expect_fail(validate_rdp_domain, domain, "rdp_domain")
    ok &= _expect_ok(validate_rdp_domain, "CORP", "rdp_domain")
    for user in (".\\admin /p:x", "user|cmd"):
        ok &= _expect_fail(validate_windows_logon, user, "win_logon")
    return ok


def test_profile_tampering():
    ok = True
    bad = _sanitize_profile({
        "name": "<script>alert(1)</script>",
        "host": "1.2.3.4;rm -rf /",
        "port": "99999",
        "user": "root;id",
    })
    if bad is not None:
        print("FAIL profile: malicious entry not filtered")
        ok = False
    else:
        print("OK   profile: malicious JSON entry rejected")

    good = _sanitize_profile({
        "name": "Home Server",
        "host": "192.168.1.10",
        "port": "22",
        "user": "admin",
    })
    if not good or good.get("host") != "192.168.1.10":
        print("FAIL profile: valid entry rejected")
        ok = False
    else:
        print("OK   profile: valid entry accepted")
    return ok


def test_loopback_detection():
    ok = True
    for ip in ("127.0.0.1", "127.0.0.2", "169.254.169.254", "0.0.0.0"):
        if not is_loopback_or_linklocal_ip(ip):
            print(f"FAIL loopback: {ip} not detected")
            ok = False
    if is_loopback_or_linklocal_ip("8.8.8.8"):
        print("FAIL loopback: 8.8.8.8 falsely flagged")
        ok = False
    else:
        print("OK   loopback: metadata/link-local detected")
    return ok


def test_host_key_always_live():
    src = inspect.getsource(
        __import__("main_gui")._SSHConnectWorker._ensure_host_key_trusted
    )
    if "peek_host_key_status" in src or 'disk_status == "trusted"' in src:
        print("FAIL host_key: still skips live verification")
        return False
    if "verify_host_key_live" not in src:
        print("FAIL host_key: live verify missing")
        return False
    print("OK   host_key: always verifies live before connect")
    return True


def main():
    ok = True

    injection_hosts = [
        "127.0.0.1; rm -rf /",
        "host$(whoami).evil.com",
        "host`id`",
        'host"evil',
        "../../../etc/passwd",
        "evil.com\r\nattacker.com",
    ]
    for h in injection_hosts:
        ok &= _expect_fail(validate_ssh_host, h, "ssh_host")

    ok &= _expect_ok(validate_ssh_host, "192.168.1.1", "ssh_host")
    ok &= _expect_ok(validate_ssh_host, "server.example.com", "ssh_host")

    for u in ["user;id", "user|cat", "", "a" * 100]:
        ok &= _expect_fail(validate_ssh_user, u, "ssh_user")

    for name in ["../secret", "foo/bar", "..", "", "a\\b"]:
        ok &= _expect_fail(validate_remote_entry_name, name, "entry_name")

    for cmd in ["ls; rm -rf /", "echo a|b", "echo a&b", "echo %PATH%"]:
        ok &= _expect_fail(validate_remote_shell_command, cmd, "shell_cmd")

    ok &= _expect_fail(validate_profile_name, "name<script>", "profile_name")
    ok &= _expect_ok(validate_profile_name, "My Server 1", "profile_name")

    argv = ssh_argv("user", "host.example.com", 22)
    assert "host.example.com" in argv
    print(f"OK   ssh_argv: {argv}")

    try:
        validate_ssh_key_path("/nonexistent/key.pem")
        print("FAIL key_path: missing file should be rejected")
        ok = False
    except ValueError:
        print("OK   key_path: rejects missing file")

    ok &= test_sftp_traversal()
    ok &= test_dns_poisoning()
    ok &= test_freerdp_injection()
    ok &= test_profile_tampering()
    ok &= test_loopback_detection()
    ok &= test_host_key_always_live()

    if sys.platform.startswith("win"):
        from remote_desktop import _store_windows_rdp_credentials
        src_cred = inspect.getsource(_store_windows_rdp_credentials)
        if "/pass:" in src_cred:
            print("FAIL cmdkey: password still on command line")
            ok = False
        else:
            print("OK   cmdkey: no /pass: in credential store")

        from windows_cred import cred_write_generic, cred_delete_generic
        test_target = "TERMSRV/__pettie_security_test__"
        if cred_write_generic(test_target, "testuser", "testpass123"):
            cred_delete_generic(test_target)
            print("OK   CredWrite/CredDelete round-trip")
        else:
            print("WARN CredWrite failed — fallback uses cmdkey without /pass")

    print()
    if ok:
        print("All security self-tests passed.")
        return 0
    print("Some security self-tests FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
