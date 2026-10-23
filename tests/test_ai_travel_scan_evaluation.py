"""Offline A22 checks for the direct travel receipt scanner."""
import json
import socket
import sqlite3

import httpx
import pytest

import ai_core as ai
from scripts.ai_evaluation import load_suite
import storage as st
from test_travel_generate import conn, mk, relay  # noqa: F401
from test_travel_scan import GOOD, JPEG


CASES = [c for c in load_suite()["cases"] if c.get("surface") == "travel_scan"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    network = []
    def deny(*args, **kwargs):
        network.append(True)
        raise AssertionError("Travel evaluation attempted network I/O")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    yield
    assert not network


@pytest.mark.parametrize("case", [pytest.param(c, id=c["id"], marks=pytest.mark.ai_evaluation(c["id"]))
                                  for c in CASES])
def test_travel_scan_scenario(case, viewer, encoder, app_mod, conn, relay, monkeypatch):
    name = case["scenario"]
    assert case["id"] == "travel-scan-" + name
    ref = mk(viewer)
    st.set_setting(conn, "ai_mode", "router")
    st.set_setting(conn, "ai_fallback_enabled", "0")
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.commit()
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "offline-travel-key")
    monkeypatch.setenv("CSS_GEMINI_MODEL", "travel-evaluation")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "")
    monkeypatch.setattr(ai.rl, "allow", lambda *args, **kwargs: True)
    ai.reset_cooldown()
    if name == "budget":
        st.set_setting(conn, "ai_cap_travel_scan", "0")
    if name == "disabled":
        st.set_setting(conn, "ai_feature_travel_scan", "0")
    conn.commit()
    calls = []
    def fake_post(url, *, headers, timeout, **kwargs):
        assert url == ai.GEMINI_API_BASE + "/models/travel-evaluation:generateContent"
        assert headers["x-goog-api-key"] == "offline-travel-key"
        assert timeout.connect <= 3 and timeout.read <= 25
        payload = kwargs["json"]
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["maxOutputTokens"] <= 512
        assert payload["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"
        calls.append(1)
        if len(calls) == 1:
            with sqlite3.connect(app_mod.DB) as other:
                if name == "logout":
                    other.execute("DELETE FROM login_session")
                elif name == "deactivate":
                    other.execute("UPDATE admin_user SET active=0 WHERE username='viewer@test.local'")
                elif name == "filing-changed":
                    other.execute("UPDATE travel_filing SET act_title='Changed after scan' WHERE ref_code=?", (ref,))
                elif name == "feature-off-during":
                    other.execute("INSERT OR REPLACE INTO app_setting(key,value) VALUES ('ai_feature_travel_scan','0')")
        if name == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if name == "http503":
            return httpx.Response(503, text="PRIVATE-PROVIDER-ERROR")
        parsed = {**GOOD}
        if name == "unreadable": parsed["readable"] = False
        elif name == "negative-amount": parsed["amount"] = -12
        elif name == "boolean-amount": parsed["amount"] = True
        elif name == "bad-date": parsed["date"] = "2026-99-99"
        elif name == "bad-currency": parsed["currency"] = "FREE"
        elif name == "html-vendor": parsed["vendor"] = "<img src=x>"
        elif name == "extra-field": parsed["account"] = "private"
        elif name == "missing-amount": del parsed["amount"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(parsed)}]}}],
                                         "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5}})
    monkeypatch.setattr(httpx, "post", fake_post)
    actor = encoder if name == "wrong-owner" else viewer
    body = b"<html>" if name == "bad-file" else JPEG
    response = actor.post(f"/travel/f/{ref}/scan", content=body)
    assert response.status_code == case["expect"]["status"]
    result = response.json()
    assert result["ok"] == case["expect"]["ok"]
    if result["ok"]:
        assert result["readable"] == (name != "unreadable")
        if name == "valid":
            assert result["amount"] == 4521.5 and result["vendor"] == "Cebu Pacific"
    assert len(calls) == case["expect"]["calls"]
    rows = conn.execute("SELECT outcome,prompt_masked,response_masked,error FROM ai_interaction ORDER BY id").fetchall()
    assert [row[0] for row in rows] == case["expect"]["outcomes"]
    assert all(row[1] is None and row[2] is None for row in rows)
    assert "PRIVATE-PROVIDER-ERROR" not in json.dumps([tuple(row) for row in rows])
    ai.reset_cooldown()
