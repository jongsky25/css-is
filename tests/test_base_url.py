"""
The public origin for QR codes, share/copy links, and email links must ALWAYS
derive from the request (or the CSS_BASE_URL pin) — never a hard-coded host — so
the same build works on localhost, a LAN IP, or any staging/prod domain, and the
generated links + QR codes resolve there.
"""
from __future__ import annotations
import types


def _req(base_url):
    """Minimal stand-in for a Starlette Request: _base_url only reads base_url."""
    return types.SimpleNamespace(base_url=base_url)


def test_css_base_url_pins_canonical_domain(app_mod, monkeypatch):
    # Staging/prod: pin the domain. Even if a request arrives on some other host
    # (or a spoofed Host header), every generated link uses the pinned origin.
    monkeypatch.setenv("CSS_BASE_URL", "https://staging.example.gov.ph")
    got = app_mod._base_url(_req("http://10.0.0.5:8000/"))
    assert got == "https://staging.example.gov.ph"


def test_pin_trailing_slash_is_trimmed(app_mod, monkeypatch):
    monkeypatch.setenv("CSS_BASE_URL", "https://staging.example.gov.ph/")
    assert app_mod._base_url(_req("http://x/")) == "https://staging.example.gov.ph"


def test_derives_from_request_when_unpinned(app_mod, monkeypatch):
    # No pin: follow the request. Behind a reverse proxy run with --proxy-headers,
    # request.base_url already reflects the public https origin, so this is it.
    monkeypatch.delenv("CSS_BASE_URL", raising=False)
    got = app_mod._base_url(_req("https://css.example.gov.ph/"))
    assert got == "https://css.example.gov.ph"


def test_localhost_request_falls_back_to_lan_ip(app_mod, monkeypatch):
    # A QR built from "localhost" is useless on a phone, so a localhost request
    # swaps in the machine's LAN IP (preserves the original local-dev behaviour).
    monkeypatch.delenv("CSS_BASE_URL", raising=False)
    monkeypatch.setattr(app_mod, "_lan_ip", lambda: "192.168.1.42")
    got = app_mod._base_url(_req("http://localhost:8000/"))
    assert got == "http://192.168.1.42:8000"


def test_qr_url_uses_derived_origin(app_mod, monkeypatch):
    # End-to-end through the QR builder: the encoded URL carries the pinned origin.
    monkeypatch.setenv("CSS_BASE_URL", "https://staging.example.gov.ph")
    base = app_mod._base_url(_req("http://localhost:8000/"))
    qrs = app_mod._build_qrs(
        [{"qr_token": "abc", "form_id": "F1", "kind": "event", "label": "x"}],
        "combined", base, event_token="EV123")
    assert qrs[0]["url"] == "https://staging.example.gov.ph/e/EV123"
    assert qrs[0]["img"].startswith("data:image/png;base64,")
