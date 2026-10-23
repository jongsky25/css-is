"""Offline A22 checks for DPO and appearance readings on travel uploads."""
import json
import socket
import sqlite3

import httpx
import pytest

import ai_core as ai
import gdocs_relay as gr
from scripts.ai_evaluation import load_suite
import storage as st
import travel
from test_travel_relay import conn, env, fake, mk, on, up, row, PDF  # noqa: F401


CASES = [c for c in load_suite()["cases"] if c.get("surface") == "checklist_upload"]
DPO = {"readable": True, "dpo_no": "2026-100", "dpo_date": "2026-09-20",
       "travel_start": "2026-10-01", "travel_end": "2026-10-31",
       "funding_stated": True, "funding": "GAA MOOE", "note": ""}
APPEARANCE = {"readable": True, "date_from": "2026-10-05", "date_to": "2026-10-07", "note": ""}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    network = []
    def deny(*args, **kwargs):
        network.append(True)
        raise AssertionError("Checklist evaluation attempted network I/O")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    yield
    assert not network


@pytest.mark.parametrize("case", [pytest.param(c, id=c["id"], marks=pytest.mark.ai_evaluation(c["id"]))
                                  for c in CASES])
def test_checklist_upload_scenario(case, viewer, encoder, app_mod, conn, fake, on, monkeypatch):
    name = case["scenario"]
    assert case["id"] == "checklist-" + name
    appearance = name.startswith("appearance-")
    ref = mk(viewer, **({"cert_of_appearance_available": "1"} if appearance else {}))
    code = "cert_appearance" if appearance else "dpo"
    st.set_setting(conn, "ai_mode", "router")
    st.set_setting(conn, "ai_fallback_enabled", "0")
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    if name == "budget": st.set_setting(conn, "ai_cap_travel_scan", "0")
    if name == "disabled": st.set_setting(conn, "ai_feature_travel_scan", "0")
    conn.commit()
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "offline-checklist-key")
    monkeypatch.setenv("CSS_GEMINI_MODEL", "checklist-evaluation")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "")
    monkeypatch.setattr(ai.rl, "allow", lambda *args, **kwargs: True)
    ai.reset_cooldown()
    if name == "relay-failure":
        fake.upload_result = gr.RelayResult(False, error="unreachable")
    if name == "cleanup-failure":
        fake.trash_ok = False
    calls = []
    def fake_post(url, *, headers, timeout, **kwargs):
        assert url == ai.GEMINI_API_BASE + "/models/checklist-evaluation:generateContent"
        assert headers["x-goog-api-key"] == "offline-checklist-key"
        assert timeout.connect <= 3 and timeout.read <= 25
        payload = kwargs["json"]
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["generationConfig"]["maxOutputTokens"] <= 512
        assert payload["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "application/pdf"
        calls.append(1)
        if len(calls) == 1:
            with sqlite3.connect(app_mod.DB) as other:
                if name in ("logout", "cleanup-failure"): other.execute("DELETE FROM login_session")
                elif name == "deactivate":
                    other.execute("UPDATE admin_user SET active=0 WHERE username='viewer@test.local'")
                elif name == "filing-changed":
                    other.execute("UPDATE travel_filing SET act_title='Changed during upload' WHERE ref_code=?", (ref,))
                elif name == "travel-off":
                    other.execute("INSERT OR REPLACE INTO app_setting(key,value) VALUES ('travel.enabled','0')")
                elif name == "feature-off-during":
                    other.execute("INSERT OR REPLACE INTO app_setting(key,value) VALUES ('ai_feature_travel_scan','0')")
        if name == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if name == "http503":
            return httpx.Response(503, text="PRIVATE-CHECKLIST-ERROR")
        parsed = dict(APPEARANCE if appearance else DPO)
        if name == "dpo-missing-number": parsed["dpo_no"] = ""
        elif name == "dpo-no-funding": parsed["funding"] = ""
        elif name == "dpo-bad-date": parsed["dpo_date"] = "2026-99-99"
        elif name == "dpo-reversed-range": parsed["travel_start"], parsed["travel_end"] = "2026-10-31", "2026-10-01"
        elif name == "dpo-html-number": parsed["dpo_no"] = "<script>private</script>"
        elif name == "dpo-extra-field": parsed["account"] = "private"
        elif name == "dpo-bad-boolean": parsed["funding_stated"] = "true"
        elif name == "dpo-unreadable": parsed["readable"] = False
        elif name == "appearance-missing-dates": parsed["date_from"] = parsed["date_to"] = ""
        elif name == "appearance-reversed": parsed["date_from"], parsed["date_to"] = "2026-10-07", "2026-10-05"
        elif name == "appearance-html-note": parsed["note"] = "<img src=x>"
        elif name == "appearance-extra-field": parsed["person"] = "private"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(parsed)}]}}],
                                         "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 5}})
    monkeypatch.setattr(httpx, "post", fake_post)
    actor = encoder if name == "wrong-owner" else viewer
    response = up(actor, ref, code=code, body=b"<html>" if name == "bad-file" else PDF)
    assert response.status_code == case["expect"]["status"]
    result = response.json()
    assert result["ok"] == case["expect"]["ok"]
    assert len(calls) == case["expect"]["calls"]
    saved = row(conn, code)
    assert bool(saved and saved["drive_source"] == "upload") == case["expect"]["saved"]
    if case["expect"]["reading"]:
        assert result["reading"] and result["reading"]["readable"]
    elif result["ok"]:
        assert not result["reading"] or not result["reading"]["readable"]
    if name == "dpo-date-only":
        assert result["fill"] == {"dpo_no": "", "dpo_date": "2026-09-20"}
        assert travel.get_by_ref(conn, ref)["dpo_date"] is None
    if name in ("logout", "deactivate", "filing-changed", "travel-off", "cleanup-failure"):
        assert fake.trashed == ["F1"]
    if name == "cleanup-failure":
        assert "ask records staff" in result["error"]
    rows = conn.execute("SELECT outcome,prompt_masked,response_masked,error FROM ai_interaction ORDER BY id").fetchall()
    assert [item[0] for item in rows] == case["expect"]["outcomes"]
    assert all(item[1] is None and item[2] is None for item in rows)
    assert "PRIVATE-CHECKLIST-ERROR" not in json.dumps([tuple(item) for item in rows])
    ai.reset_cooldown()
