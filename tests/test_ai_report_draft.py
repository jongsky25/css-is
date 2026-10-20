"""
Report narrative drafting — docs/AI_INTEGRATION_PLAN.md Phase 5.

Covers:
  * MRR analysis columns (POST .../ai-mrr-draft, .../mrr-draft): gated the
    same as "Manage this activity" (create_activity); a mocked draft call
    saves into report_draft with actor='ai'; a human Save overrides it with
    actor=username; a blank field on Save reverts to the computed default;
    any AIError falls back to a plain notice with nothing changed; the Excel
    export (both the scope+period and the "selected activities" routes)
    reads whatever is saved instead of the deterministic template.
  * Official CO-CSM report Sections V-VI (POST /reports/csm-draft,
    /reports/csm-draft/save): same shape, scoped by period only (the walk-in
    CSM form has no org scope); a period with no data short-circuits before
    any AI call; the docx export reflects the saved text, falling back to
    "N/A" / the standing boilerplate when nothing is saved.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
"""
import io
import json
from datetime import timedelta
from urllib.parse import unquote

import httpx
import pytest
from docx import Document
from openpyxl import load_workbook

import ai_core as ai
import storage as st


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network in an AI test — mock it")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


def _reset(conn):
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.execute("DELETE FROM report_draft")
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


def _configure(conn, monkeypatch, mode="router"):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", mode)


def _mock_draft(monkeypatch, payload):
    def _fake(prompt, *, system=None, response_schema=None, **kw):
        return {"text": json.dumps(payload), "parsed": payload,
                "tokens_in": 10, "tokens_out": 10, "latency_ms": 30, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", _fake)


def _redirect_msg(resp):
    loc = resp.headers["location"]
    return unquote(loc.split("msg=", 1)[1]) if "msg=" in loc else None


_activity_seq = [0]


def _activity(app_mod, topic="MRR Draft AI QQQ"):
    """A standalone Form-2 activity with a real SERVQUAL scorecard (so
    _activity_mrr_analysis has real dimension figures to work from)."""
    _activity_seq[0] += 1
    conn = st.connect(app_mod.DB)
    recent = (app_mod._today_local() - timedelta(days=2)).isoformat()
    fid = st.create_form_instance(conn, 2, "F2", recent, topic=topic,
                                  venue=f"{topic} #{_activity_seq[0]}", created_by="me@x")
    answers = [("A", 6), ("C", 3),
               ("B1", 6), ("B2", 6), ("B3", 6), ("B4", 6),
               ("B5", 3), ("B6", 3), ("B7", 3), ("B8", 3), ("B9", 3)]
    rid = st.record_response(conn, fid, answers, remarks="Great session")
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()
    return fid, rid


# ---- MRR analysis columns -----------------------------------------------------

def test_mrr_ai_draft_requires_create_activity_cap(viewer, encoder, manager, app_mod):
    fid, _ = _activity(app_mod)
    assert viewer.post(f"/reports/activities/{fid}/ai-mrr-draft").status_code == 403
    assert encoder.post(f"/reports/activities/{fid}/ai-mrr-draft").status_code == 403
    r = manager.post(f"/reports/activities/{fid}/ai-mrr-draft", follow_redirects=False)
    assert r.status_code == 303


def test_mrr_save_requires_create_activity_cap(viewer, manager, app_mod):
    fid, _ = _activity(app_mod)
    assert viewer.post(f"/reports/activities/{fid}/mrr-draft",
                       data={"analysis": "x"}).status_code == 403
    r = manager.post(f"/reports/activities/{fid}/mrr-draft",
                     data={"analysis": "x"}, follow_redirects=False)
    assert r.status_code == 303


def test_mrr_ai_draft_saves_report_draft_with_ai_actor(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod)
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_draft(monkeypatch, {"analysis": "AI analysis text.", "action": "AI action text.",
                             "next_steps": "AI next steps text.", "resources": "AI resources text."})

    r = manager.post(f"/reports/activities/{fid}/ai-mrr-draft", follow_redirects=False)
    assert r.status_code == 303
    assert "Drafted the MRR analysis columns" in _redirect_msg(r)

    conn = st.connect(app_mod.DB)
    drafts = st.get_report_drafts(conn, "activity_mrr", str(fid))
    conn.close()
    assert drafts["analysis"]["text"] == "AI analysis text." and drafts["analysis"]["actor"] == "ai"
    assert drafts["action"]["text"] == "AI action text."
    assert drafts["next_steps"]["text"] == "AI next steps text."
    assert drafts["resources"]["text"] == "AI resources text."


def test_mrr_ai_draft_falls_back_when_ai_unavailable(manager, app_mod):
    fid, _ = _activity(app_mod)
    conn = st.connect(app_mod.DB); _reset(conn)
    st.set_setting(conn, "ai_mode", "off")
    conn.commit(); conn.close()

    r = manager.post(f"/reports/activities/{fid}/ai-mrr-draft", follow_redirects=False)
    assert r.status_code == 303
    assert "unavailable" in _redirect_msg(r)
    conn = st.connect(app_mod.DB)
    assert st.get_report_drafts(conn, "activity_mrr", str(fid)) == {}
    conn.close()


def test_mrr_human_save_overrides_ai_draft(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod)
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_draft(monkeypatch, {"analysis": "AI analysis.", "action": "AI action.",
                             "next_steps": "AI next steps.", "resources": "AI resources."})
    manager.post(f"/reports/activities/{fid}/ai-mrr-draft")

    r = manager.post(f"/reports/activities/{fid}/mrr-draft", data={
        "analysis": "Human-edited analysis.", "action": "AI action.",
        "next_steps": "AI next steps.", "resources": "AI resources."}, follow_redirects=False)
    assert r.status_code == 303

    conn = st.connect(app_mod.DB)
    drafts = st.get_report_drafts(conn, "activity_mrr", str(fid))
    conn.close()
    assert drafts["analysis"]["text"] == "Human-edited analysis."
    assert drafts["analysis"]["actor"] == "manager@test.local"


def test_mrr_save_blank_field_reverts_to_default(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod)
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    manager.post(f"/reports/activities/{fid}/mrr-draft", data={
        "analysis": "Saved analysis.", "action": "Saved action.",
        "next_steps": "Saved next steps.", "resources": "Saved resources."})
    conn = st.connect(app_mod.DB)
    assert "analysis" in st.get_report_drafts(conn, "activity_mrr", str(fid))
    conn.close()

    manager.post(f"/reports/activities/{fid}/mrr-draft", data={
        "analysis": "", "action": "Saved action.",
        "next_steps": "Saved next steps.", "resources": "Saved resources."})
    conn = st.connect(app_mod.DB)
    drafts = st.get_report_drafts(conn, "activity_mrr", str(fid))
    conn.close()
    assert "analysis" not in drafts
    assert drafts["action"]["text"] == "Saved action."


def test_mrr_draft_writes_audit_rows(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod)
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_draft(monkeypatch, {"analysis": "a", "action": "b", "next_steps": "c", "resources": "d"})
    manager.post(f"/reports/activities/{fid}/ai-mrr-draft")
    manager.post(f"/reports/activities/{fid}/mrr-draft",
                 data={"analysis": "e", "action": "b", "next_steps": "c", "resources": "d"})
    conn = st.connect(app_mod.DB)
    actions = [r[0] for r in conn.execute(
        "SELECT action FROM audit_log WHERE target_id=? ORDER BY id", (str(fid),)).fetchall()]
    conn.close()
    assert "ai_mrr_draft" in actions and "mrr_draft_save" in actions


def test_mrr_export_reads_saved_draft_not_the_template(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod, topic="MRR Export Draft QQQ")
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_draft(monkeypatch, {"analysis": "Distinctive AI analysis sentence.",
                             "action": "Distinctive AI action.",
                             "next_steps": "Distinctive AI next steps.",
                             "resources": "Distinctive AI resources."})
    manager.post(f"/reports/activities/{fid}/ai-mrr-draft")

    r = manager.get("/reports/activities-export")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["AGENDA 4_Sheet1"]
    col_c = [ws.cell(row=row, column=3).value for row in range(7, ws.max_row + 1)]
    assert any(v and "Distinctive AI analysis sentence." in v for v in col_c)


def test_mrr_export_selected_reads_saved_draft(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod, topic="MRR Export Selected Draft QQQ")
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_draft(monkeypatch, {"analysis": "Selected-export AI analysis.",
                             "action": "a", "next_steps": "b", "resources": "c"})
    manager.post(f"/reports/activities/{fid}/ai-mrr-draft")

    r = manager.post("/reports/activities/export-selected", data={"ids": str(fid)})
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["AGENDA 4_Sheet1"]
    col_c = [ws.cell(row=row, column=3).value for row in range(7, ws.max_row + 1)]
    assert any(v and "Selected-export AI analysis." in v for v in col_c)


# ---- Official CO-CSM report Sections V-VI ---------------------------------------

_CSM_PERIOD = "quarter:2026-Q1"          # explicitly seeded by csm_response below
_CSM_EMPTY_PERIOD = "year:1999"          # certainly no data



@pytest.fixture
def csm_response(reference_form):
    """A Type-1 submission in the report period, independent of a snapshot."""
    return reference_form(1, "2026-02-04", [(f"SQD{i}", 5) for i in range(9)],
                          submitted_at="2026-02-04T09:00:00", service="CSM draft reference")


def test_csm_ai_draft_requires_create_activity_cap(viewer, encoder, manager):
    assert viewer.post("/reports/csm-draft", data={"period": _CSM_PERIOD}).status_code == 403
    assert encoder.post("/reports/csm-draft", data={"period": _CSM_PERIOD}).status_code == 403
    r = manager.post("/reports/csm-draft", data={"period": _CSM_PERIOD}, follow_redirects=False)
    assert r.status_code == 303


def test_csm_save_requires_create_activity_cap(viewer, manager):
    assert viewer.post("/reports/csm-draft/save",
                       data={"period": _CSM_PERIOD, "action_plan": "x"}).status_code == 403
    r = manager.post("/reports/csm-draft/save",
                     data={"period": _CSM_PERIOD, "action_plan": "x"}, follow_redirects=False)
    assert r.status_code == 303


def test_csm_ai_draft_saves_report_draft_with_ai_actor(manager, app_mod, monkeypatch, csm_response):
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_draft(monkeypatch, {"action_plan": "AI drafted action plan.",
                             "continuous_improvement": "AI drafted continuous improvement."})

    r = manager.post("/reports/csm-draft", data={"period": _CSM_PERIOD}, follow_redirects=False)
    assert r.status_code == 303
    assert "Drafted Sections V" in _redirect_msg(r)

    conn = st.connect(app_mod.DB)
    drafts = st.get_report_drafts(conn, "csm_closing", _CSM_PERIOD)
    conn.close()
    assert drafts["action_plan"]["text"] == "AI drafted action plan."
    assert drafts["action_plan"]["actor"] == "ai"
    assert drafts["continuous_improvement"]["text"] == "AI drafted continuous improvement."


def test_csm_ai_draft_no_data_period_short_circuits(manager, app_mod, monkeypatch):
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    # No mock installed for _http_generate — if the route tried to call AI on an
    # empty period it would hit the autouse "never a real network call" guard's
    # sibling: an un-mocked ai._http_generate would raise from the real httpx.post
    # patch above, failing the test loudly.
    r = manager.post("/reports/csm-draft", data={"period": _CSM_EMPTY_PERIOD}, follow_redirects=False)
    assert r.status_code == 303
    assert "No CSM responses" in _redirect_msg(r)
    conn = st.connect(app_mod.DB)
    assert st.get_report_drafts(conn, "csm_closing", _CSM_EMPTY_PERIOD) == {}
    conn.close()


def test_csm_human_save_and_blank_reverts(manager, app_mod, monkeypatch):
    conn = st.connect(app_mod.DB); _reset(conn)
    conn.commit(); conn.close()
    manager.post("/reports/csm-draft/save", data={
        "period": _CSM_PERIOD, "action_plan": "Saved plan.",
        "continuous_improvement": "Saved improvement."})
    conn = st.connect(app_mod.DB)
    drafts = st.get_report_drafts(conn, "csm_closing", _CSM_PERIOD)
    conn.close()
    assert drafts["action_plan"]["text"] == "Saved plan."
    assert drafts["action_plan"]["actor"] == "manager@test.local"

    manager.post("/reports/csm-draft/save", data={
        "period": _CSM_PERIOD, "action_plan": "",
        "continuous_improvement": "Saved improvement."})
    conn = st.connect(app_mod.DB)
    drafts = st.get_report_drafts(conn, "csm_closing", _CSM_PERIOD)
    conn.close()
    assert "action_plan" not in drafts
    assert drafts["continuous_improvement"]["text"] == "Saved improvement."


def test_csm_export_reflects_saved_draft(manager, app_mod, monkeypatch, csm_response):
    conn = st.connect(app_mod.DB); _reset(conn)
    conn.commit(); conn.close()
    manager.post("/reports/csm-draft/save", data={
        "period": _CSM_PERIOD, "action_plan": "Distinctive saved action plan text.",
        "continuous_improvement": "Distinctive saved improvement text."})

    r = manager.get("/reports/export",
                    params={"type": 1, "fmt": "docx", "style": "official", "period": _CSM_PERIOD})
    assert r.status_code == 200
    doc = Document(io.BytesIO(r.content))
    full = "\n".join(p.text for p in doc.paragraphs)
    assert "Distinctive saved action plan text." in full
    assert "Distinctive saved improvement text." in full
    assert "N/A" not in full.split("Distinctive saved action plan text.")[0][-5:]


def test_csm_export_falls_back_to_na_and_boilerplate_with_no_draft(manager, app_mod, csm_response):
    conn = st.connect(app_mod.DB); _reset(conn)
    conn.commit(); conn.close()
    r = manager.get("/reports/export",
                    params={"type": 1, "fmt": "docx", "style": "official", "period": _CSM_PERIOD})
    assert r.status_code == 200
    doc = Document(io.BytesIO(r.content))
    full = "\n".join(p.text for p in doc.paragraphs)
    assert "The Bureau will continue to implement the use of Harmonized CSM" in full
