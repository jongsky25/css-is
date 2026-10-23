"""Offline A22 checks for calendar invitation uploads and AI readings."""
import json
import socket
import sqlite3

import httpx
import pytest

import activity_docs as ad
import ai_core as ai
import gdocs_relay as gr
from scripts.ai_evaluation import load_suite
import storage as st
from test_activity_docs import conn, up_relay, letter_up, outside, LETTER, PDF  # noqa: F401
from test_calendar_entry_pages import create  # noqa: F401


CASES = [c for c in load_suite()["cases"] if c.get("surface") == "invitation_upload"]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []
    def deny(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Invitation evaluation attempted network I/O")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    yield
    assert not attempts


@pytest.mark.parametrize("case", [pytest.param(c, id=c["id"], marks=pytest.mark.ai_evaluation(c["id"]))
                                  for c in CASES])
def test_invitation_upload_scenario(case, viewer, app_mod, conn, up_relay, monkeypatch):
    name = case["scenario"]
    assert case["id"] == "invitation-" + name
    eid = create(viewer, kind="travel", title="CALEP Invitation")
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    st.set_setting(conn, "ai_mode", "router")
    st.set_setting(conn, "ai_fallback_enabled", "0")
    if name == "disabled": st.set_setting(conn, "ai_feature_travel_scan", "0")
    if name == "budget": st.set_setting(conn, "ai_cap_travel_scan", "0")
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.commit()
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "offline-invitation-key")
    monkeypatch.setenv("CSS_GEMINI_MODEL", "invitation-evaluation")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "")
    monkeypatch.setattr(ai.rl, "allow", lambda *args, **kwargs: True)
    ai.reset_cooldown()
    if name == "relay-failure": up_relay.result = gr.RelayResult(False, error="unreachable")
    if name == "cleanup-failure": up_relay.trash_ok = False
    calls = []

    def fake_post(url, *, headers, timeout, **kwargs):
        assert url == ai.GEMINI_API_BASE + "/models/invitation-evaluation:generateContent"
        assert headers["x-goog-api-key"] == "offline-invitation-key"
        assert timeout.connect <= 3 and timeout.read <= 25
        payload = kwargs["json"]
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["maxOutputTokens"] <= 512
        assert payload["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "application/pdf"
        calls.append(1)
        if len(calls) == 1:
            with sqlite3.connect(app_mod.DB) as other:
                if name in ("logout", "cleanup-failure"):
                    other.execute("DELETE FROM login_session")
                elif name == "deactivate":
                    other.execute("UPDATE admin_user SET active=0 WHERE username='viewer@test.local'")
                elif name == "entry-changed":
                    other.execute("UPDATE calendar_entry SET title='Changed invitation' WHERE id=?", (eid,))
                elif name == "entry-cancelled":
                    other.execute("UPDATE calendar_entry SET status='cancelled' WHERE id=?", (eid,))
                elif name == "outside-changed":
                    other.execute("UPDATE calendar_entry_outside SET host='Different host' WHERE entry_id=?", (eid,))
                elif name == "feature-off-during":
                    other.execute("INSERT OR REPLACE INTO app_setting(key,value) VALUES ('ai_feature_travel_scan','0')")
        if name == "timeout": raise httpx.ReadTimeout("synthetic timeout")
        if name == "http503": return httpx.Response(503, text="PRIVATE-INVITATION-ERROR")
        parsed = dict(LETTER)
        if name == "unreadable": parsed = dict(readable=False, host="", invited_as="unknown", key_lines="", note="")
        elif name == "missing-field": parsed.pop("host")
        elif name == "wrong-type": parsed["host"] = ["CHD VII"]
        elif name == "extra-field": parsed["contact"] = "private"
        elif name == "html": parsed["key_lines"] = "<script>private</script>"
        elif name == "contact": parsed["note"] = "Call 09171234567"
        elif name == "long-text": parsed["key_lines"] = "x" * 601
        elif name == "false-string": parsed["readable"] = "false"
        elif name == "empty-host": parsed["host"] = ""
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(parsed)}]}}],
                                         "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5}})

    monkeypatch.setattr(httpx, "post", fake_post)
    response = letter_up(viewer, eid, body=b"<html>" if name == "bad-file" else PDF)
    assert response.status_code == case["expect"]["status"]
    result = response.json()
    assert result["ok"] == case["expect"]["ok"]
    assert len(calls) == case["expect"]["calls"]
    assert bool(ad.get_outside(conn, eid)["file_url"]) == case["expect"]["saved"]
    if case["expect"]["reading"]:
        assert result["reading"] and result["reading"]["readable"]
    elif result["ok"]:
        assert not result["reading"] or not result["reading"]["readable"]
    if name in ("logout", "deactivate", "entry-changed", "entry-cancelled", "outside-changed", "cleanup-failure"):
        assert up_relay.trashed == ["F1"]
    if name == "cleanup-failure": assert "ask records staff" in result["error"]
    rows = conn.execute("SELECT outcome,prompt_masked,response_masked,error FROM ai_interaction ORDER BY id").fetchall()
    assert [row[0] for row in rows] == case["expect"]["outcomes"]
    assert all(row[1] is None and row[2] is None for row in rows)
    assert "PRIVATE-INVITATION-ERROR" not in json.dumps([tuple(row) for row in rows])
    ai.reset_cooldown()
