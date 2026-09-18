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


def test_send_uses_smtp_ssl_on_port_465_without_starttls(monkeypatch):
    """Port 465 is implicit TLS from connect — using plain SMTP + starttls()
    on it talks the wrong protocol to the server and fails/hangs."""
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("CSS_SMTP_PORT", "465")
    plain_smtp_used = []

    class _FakeSMTP:
        def __init__(self, *a, **kw):
            plain_smtp_used.append(True)

    class _FakeSMTP_SSL:
        def __init__(self, host, port, timeout=15):
            assert port == 465
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self):
            raise AssertionError("starttls() must not be called on port 465 (already encrypted)")
        def login(self, u, p): pass
        def send_message(self, msg): pass

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", _FakeSMTP_SSL)
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is True, result["detail"]
    assert not plain_smtp_used, "port 465 must use SMTP_SSL, not plain SMTP"


def test_send_uses_starttls_on_port_587(monkeypatch):
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("CSS_SMTP_PORT", "587")
    ssl_used = []

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15):
            assert port == 587
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg): pass

    class _FakeSMTP_SSL:
        def __init__(self, *a, **kw):
            ssl_used.append(True)

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", _FakeSMTP_SSL)
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is True, result["detail"]
    assert not ssl_used, "port 587 must use plain SMTP + starttls, not SMTP_SSL"


# ---- HTTPS relay transport (the Space blocks outbound SMTP on every port) ----

class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else ""

    def json(self):
        if self._payload is None:
            raise ValueError("no JSON")
        return self._payload


def _relay_env(monkeypatch):
    monkeypatch.setenv("CSS_MAIL_RELAY_URL", "https://script.google.com/macros/s/AKfyc/exec")
    monkeypatch.setenv("CSS_MAIL_RELAY_SECRET", "s3cret")


def test_relay_is_preferred_over_smtp_when_both_configured(monkeypatch):
    """SMTP cannot work on the Space's network, so a configured relay must win
    rather than the send falling into the SMTP path and timing out."""
    _relay_env(monkeypatch)
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.gmail.com")
    smtp_used = []
    monkeypatch.setattr(mailer.smtplib, "SMTP",
                        lambda *a, **kw: smtp_used.append(True))
    monkeypatch.setattr(mailer.httpx, "post",
                        lambda *a, **kw: _FakeResponse(200, {"ok": True}))
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is True, result["detail"]
    assert not smtp_used, "relay must be used instead of SMTP"


def test_relay_follows_redirects(monkeypatch):
    """An Apps Script /exec URL answers 302 across to
    script.googleusercontent.com and only that second response carries the
    JSON. httpx does NOT follow redirects by default, so without
    follow_redirects=True every single send would read as a failure."""
    _relay_env(monkeypatch)
    seen = {}

    def _fake_post(url, **kw):
        seen.update(kw)
        if not kw.get("follow_redirects"):
            return _FakeResponse(302, None, text="<HTML>Moved</HTML>")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(mailer.httpx, "post", _fake_post)
    result = mailer.send("to@example.com", "subj", "body")
    assert seen.get("follow_redirects") is True, "relay must follow redirects"
    assert result["sent"] is True, result["detail"]


def test_relay_posts_secret_and_message(monkeypatch):
    _relay_env(monkeypatch)
    monkeypatch.setenv("CSS_MAIL_RELAY_NAME", "Office Connect")
    captured = {}

    def _fake_post(url, **kw):
        captured["url"] = url
        captured["json"] = kw.get("json")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(mailer.httpx, "post", _fake_post)
    mailer.send("someone@doh.gov.ph", "Reset your password", "the link")
    assert captured["url"].endswith("/exec")
    sent = captured["json"]
    assert sent["secret"] == "s3cret"
    assert sent["to"] == "someone@doh.gov.ph"
    assert sent["subject"] == "Reset your password"
    assert sent["text"] == "the link"
    assert sent["fromName"] == "Office Connect"


def test_relay_reports_unauthorized_from_script(monkeypatch):
    _relay_env(monkeypatch)
    monkeypatch.setattr(mailer.httpx, "post",
                        lambda *a, **kw: _FakeResponse(200, {"ok": False, "error": "unauthorized"}))
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is False
    assert "unauthorized" in result["detail"]


def test_relay_reports_non_json_reply_as_access_problem(monkeypatch):
    """A web app deployed without 'Anyone' access serves Google's sign-in HTML
    with a 200 — the admin needs to hear that, not a parse error."""
    _relay_env(monkeypatch)
    monkeypatch.setattr(mailer.httpx, "post",
                        lambda *a, **kw: _FakeResponse(200, None, text="<html>Sign in</html>"))
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is False
    assert "Anyone" in result["detail"]


def test_relay_reports_transport_failure(monkeypatch):
    _relay_env(monkeypatch)

    def _boom(*a, **kw):
        raise RuntimeError("connection reset")

    monkeypatch.setattr(mailer.httpx, "post", _boom)
    result = mailer.send("to@example.com", "subj", "body")
    assert result["sent"] is False
    assert "unreachable" in result["detail"]
    assert "connection reset" in result["detail"]


def test_email_configured_true_with_relay_alone(monkeypatch):
    monkeypatch.delenv("CSS_SMTP_HOST", raising=False)
    _relay_env(monkeypatch)
    assert mailer.email_configured() is True
    assert mailer.relay_configured() is True
    assert mailer.smtp_configured() is False


def test_relay_needs_both_url_and_secret(monkeypatch):
    monkeypatch.delenv("CSS_SMTP_HOST", raising=False)
    monkeypatch.setenv("CSS_MAIL_RELAY_URL", "https://script.google.com/macros/s/AKfyc/exec")
    monkeypatch.delenv("CSS_MAIL_RELAY_SECRET", raising=False)
    assert mailer.relay_configured() is False
    assert mailer.email_configured() is False


# ---- HTML template (invite_message / reset_message) --------------------------

def test_invite_message_returns_subject_text_html():
    subject, text, html = mailer.invite_message("Juan Dela Cruz", "https://x/set-password?token=abc",
                                                 inviter="admin@doh.gov.ph")
    assert "set your password" in subject.lower()
    # plain text keeps the original wording/shape (still used for SMTP + outbox log)
    assert "Juan Dela Cruz" in text
    assert "https://x/set-password?token=abc" in text
    assert "7 days" in text
    # html carries the same content plus the branded shell
    assert "<!DOCTYPE html>" in html
    assert "Office Connect" in html
    assert "Juan Dela Cruz" in html
    assert "https://x/set-password?token=abc" in html
    assert "Set your password" in html
    assert "admin@doh.gov.ph" in html


def test_reset_message_returns_subject_text_html():
    subject, text, html = mailer.reset_message("Juan Dela Cruz", "https://x/reset-password?token=xyz")
    assert "reset your password" in subject.lower()
    assert "https://x/reset-password?token=xyz" in text
    assert "1 hour" in text
    assert "<!DOCTYPE html>" in html
    assert "https://x/reset-password?token=xyz" in html
    assert "Reset your password" in html


def test_email_html_escapes_untrusted_name():
    """name/inviter come from directory data an admin controls, not attacker
    input, but escaping is cheap and correct — a stray '&' or '<' in a real
    name must not break the HTML structure or inject markup."""
    subject, text, html = mailer.invite_message("Anne & Bo <ops>", "https://x/link", inviter=None)
    assert "Anne & Bo <ops>" in text                # plain text: untouched
    assert "<ops>" not in html                      # html: never raw
    assert "Anne &amp; Bo &lt;ops&gt;" in html       # html: escaped


def test_send_passes_html_through_to_smtp_multipart(monkeypatch):
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg): sent["msg"] = msg

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    _, text, html = mailer.reset_message("Juan", "https://x/reset")
    result = mailer.send("to@example.com", "subj", text, html=html)
    assert result["sent"] is True, result["detail"]
    msg = sent["msg"]
    assert msg.is_multipart()
    html_parts = [p for p in msg.walk() if p.get_content_type() == "text/html"]
    assert html_parts, "expected a text/html alternative part"
    assert "Reset your password" in html_parts[0].get_content()


def test_send_without_html_stays_plain_text_smtp(monkeypatch):
    """No html= arg (every other composer) must keep sending plain-only,
    exactly as before — this is what all the non-account notifications rely on."""
    monkeypatch.setenv("CSS_SMTP_HOST", "smtp.example.com")
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port, timeout=15): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, msg): sent["msg"] = msg

    monkeypatch.setattr(mailer.smtplib, "SMTP", _FakeSMTP)
    result = mailer.send("to@example.com", "subj", "plain body only")
    assert result["sent"] is True, result["detail"]
    assert not sent["msg"].is_multipart()


def test_relay_payload_carries_html(monkeypatch):
    _relay_env(monkeypatch)
    captured = {}

    def _fake_post(url, **kw):
        captured["json"] = kw.get("json")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(mailer.httpx, "post", _fake_post)
    _, text, html = mailer.reset_message("Juan", "https://x/reset")
    mailer.send("to@example.com", "subj", text, html=html)
    assert captured["json"]["html"] == html
    assert captured["json"]["text"] == text


def test_relay_payload_html_is_empty_string_when_not_given(monkeypatch):
    """The Apps Script checks `if (body.html)`, which is falsy for "" — so
    omitting html must send an empty string, not crash on a missing key."""
    _relay_env(monkeypatch)
    captured = {}

    def _fake_post(url, **kw):
        captured["json"] = kw.get("json")
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(mailer.httpx, "post", _fake_post)
    mailer.send("to@example.com", "subj", "plain body only")
    assert captured["json"]["html"] == ""
