"""
POST /directory/cleanup/ai-suggest — docs/AI_INTEGRATION_PLAN.md Phase 8.

Covers: admin-only RBAC (the existing `/directory` prefix cap, no new gating
code), a successful call returning a same/different/unsure relation + reason
+ interaction_id, the "harmonize" feature defaulting OFF even with the mode
raised (the one AI feature that sends names, so it's opt-in on top of the
generic on-by-default feature flags), AIError and budget-exceeded both
falling back to a plain notice, the audit row, the server-side allow-list
rejecting a pair that isn't a duplicate candidate the page itself surfaced,
and that the endpoint never merges/mutates resource_person — only the
pre-existing POST /directory/cleanup/merge does that.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
"""
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
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'ZZTest%'")
    conn.commit()


def _configure(conn, monkeypatch, *, enable_harmonize=True):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "router")
    if enable_harmonize:
        st.set_setting(conn, "ai_feature_harmonize", "1")


def _make_pair(conn, a_name="ZZTest Aabbccddee Ffgghhiijj", b_name="ZZTest Ffgghhiijj"):
    """Two external resource_person rows candidate_match will pair up (b's
    identity tokens are a subset of a's). Nonsense tokens so this can never
    collide with a real name already in the (copied production) test DB."""
    a = conn.execute(
        "INSERT INTO resource_person(name, is_internal) VALUES (?, 0)", (a_name,)).lastrowid
    b = conn.execute(
        "INSERT INTO resource_person(name, is_internal) VALUES (?, 0)", (b_name,)).lastrowid
    return a, b


def _mock_suggestion(monkeypatch, *, relation="same",
                     reason="Same surname and one is a clear subset of the other."):
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": "{}", "parsed": {"relation": relation, "reason": reason},
        "tokens_in": 60, "tokens_out": 20, "latency_ms": 400, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT outcome, feature FROM ai_interaction "
        "WHERE feature='harmonize' ORDER BY id DESC LIMIT 1").fetchone()


def test_suggest_requires_admin(admin, viewer, manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch)
        payload = {"a_id": a, "b_id": b}
        assert viewer.post("/directory/cleanup/ai-suggest", data=payload).status_code == 403
        assert manager.post("/directory/cleanup/ai-suggest", data=payload).status_code == 403
        assert admin.post("/directory/cleanup/ai-suggest", data=payload).status_code == 200
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_success_returns_relation_reason_and_interaction_id(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch, relation="same", reason="Looks like the same person.")
        r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["relation"] == "same"
        assert "same person" in body["reason"]
        assert "interaction_id" in body
        conn = st.connect(db_path)
        outcome, feature = _last_interaction(conn)
        assert outcome == "ok" and feature == "harmonize"
    finally:
        _reset(conn); conn.close()


def test_harmonize_defaults_off_even_with_mode_raised(admin, db_path, monkeypatch):
    """Unlike every other feature, harmonize must stay off until an admin
    explicitly flips its own flag — even after ai_mode is raised."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, enable_harmonize=False)
        assert ai.feature_enabled(conn, "harmonize") is False
        assert ai.feature_enabled(conn, "verbatim") is True   # sanity: other features stay on-by-default
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch)
        r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "no_config"
    finally:
        _reset(conn); conn.close()


def test_suggest_ai_error_falls_back_to_notice(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: (_ for _ in ()).throw(
            ai.AIBadResponse("boom")))
        r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "notice" in body
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_error"
    finally:
        _reset(conn); conn.close()


def test_suggest_unconfigured_falls_back_to_notice(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    st.set_setting(conn, "ai_mode", "router")
    st.set_setting(conn, "ai_feature_harmonize", "1")
    a, b = _make_pair(conn)
    conn.commit(); conn.close()
    r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_budget_exceeded_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        st.set_setting(conn, "ai_cap_harmonize", "0")
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_budget"
    finally:
        _reset(conn); conn.close()


def test_suggest_writes_audit_row(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch)
        admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        conn = st.connect(db_path)
        row = conn.execute(
            "SELECT action, target_type, target_id FROM audit_log "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "ai_harmonize_suggest"
        assert row[1] == "resource_person"
        assert str(row[2]) == str(a)
    finally:
        _reset(conn); conn.close()


def test_suggest_never_mutates_resource_person(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch, relation="same")
        admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        conn = st.connect(db_path)
        still_two = conn.execute(
            "SELECT COUNT(*) FROM resource_person WHERE id IN (?,?)", (a, b)).fetchone()[0]
        assert still_two == 2
    finally:
        _reset(conn); conn.close()


def test_suggest_rejects_pair_outside_dupe_candidates(admin, db_path, monkeypatch):
    """Two records that aren't candidate_match duplicates of each other must
    never be sent to the model, even if both ids are real."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    a, _b = _make_pair(conn)
    unrelated = conn.execute(
        "INSERT INTO resource_person(name, is_internal) VALUES (?, 0)",
        ("ZZTest Completely Different Person",)).lastrowid
    conn.commit(); conn.close()
    _mock_suggestion(monkeypatch)
    r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": unrelated})
    assert r.status_code == 400
    assert r.json()["ok"] is False
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_rejects_nonexistent_ids(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": 9999991, "b_id": 9999992})
    assert r.status_code == 400
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_invalid_relation_is_rejected(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        a, b = _make_pair(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch, relation="definitely-yes")
        r = admin.post("/directory/cleanup/ai-suggest", data={"a_id": a, "b_id": b})
        assert r.status_code == 200
        assert r.json()["ok"] is False
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()
