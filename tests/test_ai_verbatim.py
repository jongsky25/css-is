"""
POST /reports/activities/<id>/ai-reanalyze and .../ai-summary —
docs/AI_INTEGRATION_PLAN.md Phase 4.

Covers: gated the same as "Manage this activity" (create_activity capability);
a mocked classify call re-tags eligible comments into comment_override with
actor='ai'; a comment a HUMAN already re-tagged is never touched even if the
mocked model disagrees (human > ai > lexicon — human wins); more comments than
one batch's worth makes more than one ai.ask() call (chunking, ~30/call); an
out-of-range index or an invalid sentiment value from a (mocked) misbehaving
model is dropped rather than applied (schema-pinned enum + server-side
revalidation); any AIError falls back to a plain notice with nothing changed;
the AI summary panel renders up to 3 bullets from a mocked response or reports
unavailable, never a raw error.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
"""
import json
from datetime import timedelta
from urllib.parse import unquote

import httpx
import pytest

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
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


def _configure(conn, monkeypatch, mode="router"):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", mode)


_activity_seq = [0]


def _activity(app_mod, comments, topic="Verbatim AI QQQ"):
    """A standalone Form-2 activity — build_events keys a lone F2 form by its own
    id (see test_activity_report_none_gap.py) — with one response per comment.
    build_events groups F2s by (event_date, venue, org) (_event_group_key), so
    each call gets its own unique venue — otherwise same-day activities with no
    venue/org would all collapse into one event group and steal each other's id."""
    _activity_seq[0] += 1
    conn = st.connect(app_mod.DB)
    recent = (app_mod._today_local() - timedelta(days=2)).isoformat()
    fid = st.create_form_instance(conn, 2, "F2", recent, topic=topic,
                                  venue=f"{topic} #{_activity_seq[0]}", created_by="me@x")
    rids = [st.record_response(conn, fid, [("B1", 6)], remarks=c) for c in comments]
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()
    return fid, rids


def _mock_classify(monkeypatch, mappings):
    """`mappings`: a list of {i: sentiment} dicts, one consumed per successive
    ai.ask() call (so a test can assert on how many chunks were made). Returns
    the list of raw prompts sent, for chunk-count assertions."""
    calls = []

    def _fake(prompt, *, system=None, response_schema=None, **kw):
        calls.append(prompt)
        m = mappings[len(calls) - 1]
        payload = {"items": [{"i": i, "sentiment": s} for i, s in m.items()]}
        return {"text": json.dumps(payload), "parsed": payload,
                "tokens_in": 10, "tokens_out": 10, "latency_ms": 30, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", _fake)
    return calls


def _overrides(app_mod, rids):
    conn = st.connect(app_mod.DB)
    try:
        return st.get_comment_overrides_with_actor(conn, rids)
    finally:
        conn.close()


def _redirect_msg(resp):
    loc = resp.headers["location"]
    return unquote(loc.split("msg=", 1)[1]) if "msg=" in loc else None


# ---- RBAC --------------------------------------------------------------------

def test_reanalyze_requires_create_activity_cap(viewer, encoder, manager, app_mod):
    fid, _ = _activity(app_mod, ["Great session, very helpful"])
    assert viewer.post(f"/reports/activities/{fid}/ai-reanalyze").status_code == 403
    assert encoder.post(f"/reports/activities/{fid}/ai-reanalyze").status_code == 403
    r = manager.post(f"/reports/activities/{fid}/ai-reanalyze", follow_redirects=False)
    assert r.status_code == 303


def test_summary_requires_create_activity_cap(viewer, manager, app_mod):
    fid, _ = _activity(app_mod, ["Great session, very helpful"])
    assert viewer.post(f"/reports/activities/{fid}/ai-summary").status_code == 403
    assert manager.post(f"/reports/activities/{fid}/ai-summary").status_code == 200


# ---- Re-analyze: writes ai overrides, respects human precedence --------------

def test_reanalyze_writes_ai_overrides_for_all_eligible(manager, app_mod, monkeypatch):
    fid, rids = _activity(app_mod, ["Comment A", "Comment B"])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    # Same sentiment for every index regardless of flatten order.
    _mock_classify(monkeypatch, [{0: "mixed", 1: "mixed"}])

    r = manager.post(f"/reports/activities/{fid}/ai-reanalyze", follow_redirects=False)
    assert r.status_code == 303
    msg = _redirect_msg(r)
    assert msg and "Re-analyzed 2 comment(s)" in msg

    overrides = _overrides(app_mod, rids)
    assert len(overrides) == 2
    for rid in rids:
        tag, actor = overrides[(rid, "")]
        assert tag == "mixed" and actor == "ai"


def test_reanalyze_never_overwrites_a_human_retag(manager, app_mod, monkeypatch):
    fid, rids = _activity(app_mod, ["Comment A", "Comment B"])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    # A human already re-tagged the first comment as "appreciate".
    st.set_comment_override(conn, rids[0], "", "appreciate", actor="analyst@x")
    conn.commit(); conn.close()
    # The mocked model would classify BOTH as "improve" — disagreeing with the
    # human's "appreciate" on the first one.
    _mock_classify(monkeypatch, [{0: "improve", 1: "improve"}])

    manager.post(f"/reports/activities/{fid}/ai-reanalyze")

    overrides = _overrides(app_mod, rids)
    tag0, actor0 = overrides[(rids[0], "")]
    assert tag0 == "appreciate" and actor0 == "analyst@x", "a human re-tag must never be overwritten by AI"
    tag1, actor1 = overrides[(rids[1], "")]
    assert tag1 == "improve" and actor1 == "ai"


def test_reanalyze_a_second_ai_pass_can_update_its_own_earlier_tag(manager, app_mod, monkeypatch):
    fid, rids = _activity(app_mod, ["Comment A"])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_classify(monkeypatch, [{0: "improve"}])
    manager.post(f"/reports/activities/{fid}/ai-reanalyze")
    assert _overrides(app_mod, rids)[(rids[0], "")] == ("improve", "ai")

    _mock_classify(monkeypatch, [{0: "appreciate"}])
    manager.post(f"/reports/activities/{fid}/ai-reanalyze")
    assert _overrides(app_mod, rids)[(rids[0], "")] == ("appreciate", "ai")


def test_reanalyze_chunks_in_batches_of_30(manager, app_mod, monkeypatch):
    comments = [f"Comment number {i}" for i in range(35)]
    fid, rids = _activity(app_mod, comments)
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    # First 30-comment batch, then a 5-comment batch.
    calls = _mock_classify(monkeypatch, [
        {i: "mixed" for i in range(30)}, {i: "mixed" for i in range(5)}])

    r = manager.post(f"/reports/activities/{fid}/ai-reanalyze", follow_redirects=False)
    assert len(calls) == 2, "35 comments at 30/call must make exactly two ai.ask() calls"
    assert "Re-analyzed 35 comment(s)" in _redirect_msg(r)
    overrides = _overrides(app_mod, rids)
    assert all(overrides[(rid, "")] == ("mixed", "ai") for rid in rids)


def test_reanalyze_drops_out_of_range_or_invalid_sentiment(manager, app_mod, monkeypatch):
    fid, rids = _activity(app_mod, ["Comment A", "Comment B"])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    # index 0 is valid; index 1 has a bogus sentiment; index 99 is out of range —
    # a misbehaving/adversarial model output must not crash or apply either.
    _mock_classify(monkeypatch, [{0: "improve", 1: "not_a_real_sentiment", 99: "mixed"}])

    r = manager.post(f"/reports/activities/{fid}/ai-reanalyze", follow_redirects=False)
    assert r.status_code == 303
    assert "Re-analyzed 1 comment(s)" in _redirect_msg(r)
    # ev["response_ids"] (a de-duped set under the hood) doesn't promise the same
    # order as `rids`, so assert on the set of outcomes rather than a fixed index.
    overrides = _overrides(app_mod, rids)
    assert len(overrides) == 1
    assert list(overrides.values())[0] == ("improve", "ai")


def test_reanalyze_falls_back_when_ai_unavailable(manager, app_mod, monkeypatch):
    fid, rids = _activity(app_mod, ["Comment A"])
    conn = st.connect(app_mod.DB); _reset(conn)
    st.set_setting(conn, "ai_mode", "off")   # AI left off — no CSS_GEMINI_API_KEY needed
    conn.commit(); conn.close()

    r = manager.post(f"/reports/activities/{fid}/ai-reanalyze", follow_redirects=False)
    assert r.status_code == 303
    msg = _redirect_msg(r)
    assert msg and "unavailable" in msg
    assert not _overrides(app_mod, rids)


def test_reanalyze_no_eligible_comments_is_a_no_op(manager, app_mod, monkeypatch):
    # A response with no remarks (not zero responses — build_events drops an
    # activity entirely once it has no respondents at all) leaves no quote to
    # classify: story_panel/flatten_quotes yields nothing for an empty comment.
    fid, _ = _activity(app_mod, [""])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    r = manager.post(f"/reports/activities/{fid}/ai-reanalyze", follow_redirects=False)
    assert "No comments here are eligible" in _redirect_msg(r)


# ---- AI summary ----------------------------------------------------------------

def test_summary_renders_mocked_bullets(manager, app_mod, monkeypatch):
    fid, _ = _activity(app_mod, ["Great facilitator", "Room was too cold"])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    payload = {"bullets": ["People praised the facilitator.",
                           "The venue temperature needs attention.",
                           "Overall sentiment is positive."]}
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": json.dumps(payload), "parsed": payload,
        "tokens_in": 20, "tokens_out": 20, "latency_ms": 50, "model": "gemini-test"})

    r = manager.post(f"/reports/activities/{fid}/ai-summary")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert len(body["bullets"]) == 3
    assert body["interaction_id"]


def test_summary_falls_back_with_no_comments(manager, app_mod):
    fid, _ = _activity(app_mod, [])
    r = manager.post(f"/reports/activities/{fid}/ai-summary")
    assert r.json() == {"ok": False}


def test_summary_falls_back_when_ai_unavailable(manager, app_mod):
    fid, _ = _activity(app_mod, ["Some comment here"])
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, "ai_mode", "off")
    conn.commit(); conn.close()
    r = manager.post(f"/reports/activities/{fid}/ai-summary")
    assert r.json() == {"ok": False}


# ---- Audit -----------------------------------------------------------------------

def test_reanalyze_writes_an_audit_row(manager, app_mod, monkeypatch):
    fid, rids = _activity(app_mod, ["Comment A"])
    conn = st.connect(app_mod.DB); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    _mock_classify(monkeypatch, [{0: "improve"}])
    manager.post(f"/reports/activities/{fid}/ai-reanalyze")
    conn = st.connect(app_mod.DB)
    row = conn.execute("SELECT action, target_id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row[0] == "ai_verbatim_reanalyze" and str(row[1]) == str(fid)
