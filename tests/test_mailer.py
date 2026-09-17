"""mailer.py — the IPv4-only DNS workaround for hosting sandboxes that get an
IPv6 address with no route out (send() would otherwise fail instantly with
"Network is unreachable" before ever trying the IPv4 address that works)."""
from __future__ import annotations
import socket
import pytest
import mailer


def test_ipv4_only_getaddrinfo_filters_out_ipv6(monkeypatch):
    mixed = [
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2607:f8b0::1", 587, 0, 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.0.1", 587)),
    ]
    def _fake_resolver(host, port, family=0, type=0, proto=0, flags=0):
        # mimic the real OS resolver: honor the requested family, like the
        # AF_INET mailer._ipv4_only_getaddrinfo asks for
        if family:
            return [r for r in mixed if r[0] == family]
        return mixed
    monkeypatch.setattr(socket, "getaddrinfo", _fake_resolver)
    result = mailer._ipv4_only_getaddrinfo("smtp.example.com", 587)
    assert result == [mixed[1]]
    assert all(r[0] == socket.AF_INET for r in result)


def test_send_restores_getaddrinfo_after_success(monkeypatch):
    orig = socket.getaddrinfo
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15):
            # while inside the connection, getaddrinfo must be the IPv4-only one
            assert socket.getaddrinfo is mailer._ipv4_only_getaddrinfo
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg): pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is True
    assert socket.getaddrinfo is orig, "getaddrinfo must be restored after send()"


def test_send_restores_getaddrinfo_after_failure(monkeypatch):
    orig = socket.getaddrinfo
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15):
            raise OSError(101, "Network is unreachable")

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is False
    assert "Network is unreachable" in result["detail"]
    assert socket.getaddrinfo is orig, "getaddrinfo must be restored even after a failed send"
