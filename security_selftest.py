"""Kiểm thử tự động các biện pháp bảo mật đầu vào."""

import sys

from security_utils import (
    validate_ssh_host,
    validate_ssh_user,
    validate_ssh_port,
    validate_ssh_key_path,
    validate_remote_entry_name,
    validate_search_pattern,
    validate_remote_shell_command,
    validate_rdp_ipv4,
    validate_windows_logon,
    ssh_argv,
)


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


def main():
    ok = True

    injection_hosts = [
        "127.0.0.1; rm -rf /",
        "host$(whoami).evil.com",
        "host`id`",
        'host"evil',
        "../../../etc/passwd",
    ]
    for h in injection_hosts:
        ok &= _expect_fail(validate_ssh_host, h, "ssh_host")

    ok &= _expect_ok(validate_ssh_host, "192.168.1.1", "ssh_host")
    ok &= _expect_ok(validate_ssh_host, "server.example.com", "ssh_host")

    for u in ["user;id", "user|cat", ""]:
        ok &= _expect_fail(validate_ssh_user, u, "ssh_user")
    ok &= _expect_ok(validate_ssh_user, "admin", "ssh_user")

    for ip in ["1.2.3.4;calc", "not-an-ip", "256.1.1.1"]:
        ok &= _expect_fail(validate_rdp_ipv4, ip, "rdp_ipv4")
    ok &= _expect_ok(validate_rdp_ipv4, "10.0.0.5", "rdp_ipv4")

    for name in ["../secret", "foo/bar", "..", ""]:
        ok &= _expect_fail(validate_remote_entry_name, name, "entry_name")
    ok &= _expect_ok(validate_remote_entry_name, "readme.txt", "entry_name")

    for pat in ["\x00evil", "x" * 300]:
        ok &= _expect_fail(validate_search_pattern, pat, "search")
    ok &= _expect_ok(validate_search_pattern, "config", "search")

    for cmd in ["ls; rm -rf /", "echo a|b", "echo a&b"]:
        ok &= _expect_fail(validate_remote_shell_command, cmd, "shell_cmd")
    ok &= _expect_ok(validate_remote_shell_command, "df -h", "shell_cmd")

    argv = ssh_argv("user", "host.example.com", 22)
    assert argv[0] == "ssh"
    assert "host.example.com" in argv
    print(f"OK   ssh_argv: {argv}")

    try:
        validate_ssh_key_path("/nonexistent/key.pem")
        print("FAIL key_path: missing file should be rejected")
        ok = False
    except ValueError:
        print("OK   key_path: rejects missing file")

    if sys.platform.startswith("win"):
        import subprocess
        src = open(__file__, encoding="utf-8").read()
        if '"/pass:"' in src or "'/pass:'" in src:
            pass
        from remote_desktop import _store_windows_rdp_credentials
        import inspect
        src_cred = inspect.getsource(_store_windows_rdp_credentials)
        if "/pass:" in src_cred:
            print("FAIL cmdkey: password still on command line in _store_windows_rdp_credentials")
            ok = False
        else:
            print("OK   cmdkey: no /pass: in credential store function")

        from windows_cred import cred_write_generic, cred_delete_generic
        test_target = "TERMSRV/__pettie_security_test__"
        if cred_write_generic(test_target, "testuser", "testpass123"):
            cred_delete_generic(test_target)
            print("OK   CredWrite/CredDelete round-trip")
        else:
            print("WARN CredWrite failed (may need elevation) — fallback uses cmdkey without /pass")

    print()
    if ok:
        print("All security self-tests passed.")
        return 0
    print("Some security self-tests FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
