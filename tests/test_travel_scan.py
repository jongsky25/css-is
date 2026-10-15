"""Reading the fare off a ticket or receipt (travel_scan.py, POST /travel/f/<ref>/scan, ai_core `images`).
The model is always mocked one layer down; nothing reaches the network."""
from __future__ import annotations
import base64
import json

import httpx
import pytest

import ai_core as ai
import storage as st
import travel_scan as ts
from test_travel_generate import conn, mk, relay                                  # noqa: F401

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("real network")))
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


def ai_on(conn, monkeypatch, parsed):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "router")
    conn.execute("DELETE FROM ai_budget"); conn.commit()
    seen = {}

    def fake(prompt, **kw):
        seen.update(kw)
        return {"text": json.dumps(parsed), "parsed": parsed, "tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "model": "m"}
    monkeypatch.setattr(ai, "_http_generate", fake)
    return seen


GOOD = {"readable": True, "kind": "plane_ticket", "amount": 4521.5, "currency": "PHP", "date": "2026-09-02",
        "origin": "Manila", "destination": "Cebu", "vendor": "Cebu Pacific", "reference": "ABC123", "note": ""}


def scan(client, ref, body=JPEG, **kw):
    return client.post(f"/travel/f/{ref}/scan", content=body, **kw)


# ----------------------------------------------------------------- clean() ---

def test_clean_keeps_a_good_reading():
    c = ts.clean(GOOD)
    assert c["readable"] and c["amount"] == 4521.5 and c["currency"] == "PHP" and c["date"] == "2026-09-02"


@pytest.mark.parametrize("bad", [{}, None, "x", {"readable": True, "amount": "abc"}, {"readable": True, "amount": -5},
                                 {"readable": True, "amount": 0}, {"readable": True, "amount": 10 ** 9},
                                 {"readable": False, "amount": 500}])
def test_clean_never_trusts_a_bad_amount(bad):
    c = ts.clean(bad)
    assert c["readable"] is False and (c["amount"] == 0 or bad == {"readable": False, "amount": 500})


def test_clean_drops_a_bad_date_and_unknown_kind_and_names_pesos():
    c = ts.clean({**GOOD, "date": "02/09/2026", "kind": "spaceship", "currency": "pesos"})
    assert c["date"] == "" and c["kind"] == "other" and c["currency"] == "PHP"
    assert ts.clean({**GOOD, "date": "2026-13-45"})["date"] == ""


def test_sniff_goes_by_the_bytes_not_the_label():
    assert ts.sniff(JPEG) == "image/jpeg" and ts.sniff(PDF) == "application/pdf"
    assert ts.sniff(b"\x89PNG\r\n\x1a\n" + b"0" * 9) == "image/png"
    assert ts.sniff(b"<html>") == "" and ts.sniff(b"") == ""


# -------------------------------------------------------------- ai_core ---

def test_gemini_body_carries_the_image_before_the_prompt(monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "k")
    sent = {}

    class R:
        status_code = 200
        text = ""
        def json(self): return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    monkeypatch.setattr(httpx, "post", lambda url, json=None, **k: sent.update(body=json) or R())
    ai._http_generate("read it", images=[("image/jpeg", JPEG)], response_schema={"type": "OBJECT"})
    parts = sent["body"]["contents"][0]["parts"]
    assert parts[0]["inline_data"] == {"mime_type": "image/jpeg", "data": base64.b64encode(JPEG).decode()}
    assert parts[1] == {"text": "read it"}


def test_an_image_call_never_goes_to_groq(conn, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "g")
    st.set_setting(conn, "ai_mode", "router"); st.set_setting(conn, "ai_fallback_enabled", "1")
    called = []
    monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **k: called.append(1))
    with pytest.raises(ai.AIUnavailable):
        ai.ask(conn, None, "travel_scan", "p", images=[("image/jpeg", JPEG)])
    assert not called


def test_a_quota_failure_does_not_fall_back_to_groq_for_images(conn, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "g"); monkeypatch.setenv("CSS_GROQ_API_KEY", "g")
    st.set_setting(conn, "ai_mode", "router"); st.set_setting(conn, "ai_fallback_enabled", "1")
    conn.execute("DELETE FROM ai_budget"); conn.commit()

    def limited(*a, **k): raise ai.AIUnavailable("429")
    monkeypatch.setattr(ai, "_http_generate", limited)
    called = []
    monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **k: called.append(1))
    with pytest.raises(ai.AIUnavailable):
        ai.ask(conn, None, "travel_scan", "p", images=[("image/jpeg", JPEG)])
    assert not called


# ---------------------------------------------------------------- route ---

def test_scan_returns_the_reading_and_passes_the_file(viewer, conn, relay, monkeypatch):
    ref = mk(viewer)
    seen = ai_on(conn, monkeypatch, GOOD)
    r = scan(viewer, ref, PDF)
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["amount"] == 4521.5 and j["vendor"] == "Cebu Pacific"
    assert seen["images"] == [("application/pdf", PDF)]
    assert seen["response_schema"] is ts.SCHEMA


def test_scan_stores_nothing_but_the_ai_log_without_the_file(viewer, conn, relay, monkeypatch):
    ref = mk(viewer)
    ai_on(conn, monkeypatch, GOOD)
    scan(viewer, ref)
    assert b"0" * 64 not in json.dumps([tuple(r) for r in conn.execute("SELECT * FROM ai_interaction")]).encode()


def test_scan_says_so_when_the_ai_is_off(viewer, conn, relay, monkeypatch):
    ref = mk(viewer)
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    st.set_setting(conn, "ai_mode", "off")
    j = scan(viewer, ref).json()
    assert j["ok"] is False and j["ai"] is False and "Type the amount" in j["error"]


def test_scan_refuses_other_file_types_empty_and_oversize(viewer, conn, relay, monkeypatch):
    ref = mk(viewer)
    ai_on(conn, monkeypatch, GOOD)
    assert scan(viewer, ref, b"<html>hi</html>").status_code == 415
    assert scan(viewer, ref, b"").status_code == 413
    assert scan(viewer, ref, JPEG + b"0" * ts.MAX_BYTES).status_code == 413


def test_scan_is_owner_only_and_same_origin(viewer, encoder, conn, relay, monkeypatch):
    ref = mk(viewer)
    ai_on(conn, monkeypatch, GOOD)
    assert scan(encoder, ref).status_code == 404
    assert scan(viewer, ref, headers={"Origin": "https://evil.example"}).status_code == 403
    assert scan(viewer, "nope").status_code == 404
