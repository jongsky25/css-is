"""mailer.py — the IPv4-only DNS workaround for hosting sandboxes that get an
IPv6 address with no route out (send() would otherwise fail instantly with
"Network is unreachable" before ever trying the IPv4 address that works).

Regression coverage here specifically guards against a recursion bug: send()
reassigns socket.getaddrinfo to _ipv4_only_getaddrinfo for the duration of the
SMTP connection, so _ipv4_only_getaddrinfo must NOT resolve through the
(now-patched) socket.getaddrinfo name — it must call the real function it
captured at import time (_real_getaddrinfo), or it recurses into itself
forever. The earlier version of this test file asserted identity
(`socket.getaddrinfo is mailer._ipv4_only_getaddrinfo`) but never actually
CALLED it during a fake connection, so it passed even with the recursion bug
live in production."""
from __future__ import annotations
import socket
import pytest
import mailer

MIXED_RESULTS = [
    (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2607:f8b0::1", 587, 0, 0)),
    (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.0.1", 587)),
]


def _fake_resolver(mixed):
    def resolver(host, port, family=0, type=0, proto=0, flags=0):
        # mimic the real OS resolver: honor the requested family
        if family:
            return [r for r in mixed if r[0] == family]
        return mixed
    return resolver


def test_ipv4_only_getaddrinfo_filters_out_ipv6(monkeypatch):
    monkeypatch.setattr(mailer, "_real_getaddrinfo", _fake_resolver(MIXED_RESULTS))
    result = mailer._ipv4_only_getaddrinfo("smtp.example.com", 587)
    assert result == [MIXED_RESULTS[1]]
    assert all(r[0] == socket.AF_INET for r in result)


def test_ipv4_only_getaddrinfo_does_not_recurse_once_patched_onto_socket(monkeypatch):
    """Regression: this is the exact failure mode hit in production. Once
    socket.getaddrinfo IS mailer._ipv4_only_getaddrinfo (as send() sets it up),
    anything that calls socket.getaddrinfo(...) — as smtplib does internally
    — must resolve through the real function, not itself."""
    monkeypatch.setattr(mailer, "_real_getaddrinfo", _fake_resolver(MIXED_RESULTS))
    monkeypatch.setattr(socket, "getaddrinfo", mailer._ipv4_only_getaddrinfo)
    result = socket.getaddrinfo("smtp.example.com", 587)
    assert result == [MIXED_RESULTS[1]]


def test_send_restores_getaddrinfo_after_success(monkeypatch):
    orig = socket.getaddrinfo
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15):
            # smtplib resolves the host internally on connect — actually call
            # it here (not just check identity) so a recursion bug surfaces.
            # Resolve a plain IP literal so this needs no real DNS/network,
            # and leave mailer._real_getaddrinfo untouched (patching it here
            # would make send()'s own restore-to-real "correctly" restore to
            # a fake, defeating the `is orig` check below).
            addrs = socket.getaddrinfo("127.0.0.1", port)
            assert addrs, "expected at least one resolved address"
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg): pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is True, result["detail"]
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
