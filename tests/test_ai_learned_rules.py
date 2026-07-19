"""
End-to-end tests for the deterministic FAQ layer in front of the NL router
(qa_rules.py, storage.learned_rule, app._ai_try_rules, /admin/rules).

Proves the two things the feature exists for:
  1. A learned rule answers a matching question with NO model call and NO
     budget spend (provider='rules', tokens_out=0) — even when AI is off.
  2. A non-matching query still falls through to the model path unchanged.

Plus: role/cap gating on rule targets, the clean question captured for mining,
top_questions candidate aggregation, and the /admin/rules gate + create flow.
"""
import httpx
import pytest

import ai_core as ai
import storage as st


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Any real HTTP from an AI test is a bug — a rule hit must never reach the
    model, and the miss paths here are configured to fail fast, not call out."""
    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network — a rule hit should skip the model")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


def _reset(conn):
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM learned_rule")
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


def _add_rule(conn, pattern, kind, target_key, **kw):
    import qa_rules
    return st.create_learned_rule(conn, pattern=qa_rules.normalize(pattern),
                                  kind=kind, target_key=target_key, **kw)


def _last(conn):
    return conn.execute(
        "SELECT outcome, provider, tokens_out, feature, question_norm "
        "FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()


# ── 1. A rule answers a navigate question with no model call ──────────────────

def test_rule_serves_navigate_without_ai(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _add_rule(conn, "open the dashboard", "navigate", "pulse", source="seed")
        conn.commit(); conn.close()
        r = admin.post("/api/ai/route", data={"q": "Open the dashboard!"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "navigate" and body["destination"] == "pulse"
        assert body["url"] == "/dashboard" and body["served_by"] == "rules"
        conn = st.connect(db_path)
        outcome, provider, tokens_out, feature, qnorm = _last(conn)
        assert outcome == "ok" and provider == "rules" and tokens_out == 0
        assert feature == "nl_router" and qnorm == "open the dashboard"
        # and the rule's hit counter advanced
        assert st.list_learned_rules(conn)[0]["hits"] == 1
    finally:
        _reset(conn); conn.close()


# ── 2. A rule works even when AI is completely OFF (the credit-saving path) ────

def test_rule_serves_answer_when_ai_off(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_setting(conn, "ai_mode", "off")
        _add_rule(conn, "how many responses this month", "answer", "responses_30d",
                  keywords="responses received submissions recently", source="seed")
        conn.commit(); conn.close()
        r = admin.post("/api/ai/route", data={"q": "responses received this month"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "answer" and body["served_by"] == "rules"
        assert "responses" in body["text"].lower()
        conn = st.connect(db_path)
        assert _last(conn)[1] == "rules"          # provider
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ── 3. A non-matching query falls through to the model path unchanged ─────────

def test_miss_falls_through_to_model(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _add_rule(conn, "open the dashboard", "navigate", "pulse")
        st.set_setting(conn, "ai_mode", "router")
        monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
        conn.commit(); conn.close()
        called = {"n": 0}

        def _mock(*a, **kw):
            called["n"] += 1
            payload = {"destination": "trends", "confidence": 0.9, "reason": "x"}
            return {"text": "{}", "parsed": payload, "tokens_in": 5, "tokens_out": 5,
                    "latency_ms": 10, "model": "gemini-test"}
        monkeypatch.setattr(ai, "_http_generate", _mock)

        r = admin.post("/api/ai/route", data={"q": "show me the trend charts please"})
        assert r.status_code == 200
        assert r.json()["kind"] == "navigate" and r.json()["destination"] == "trends"
        assert called["n"] == 1                    # the model WAS called on a miss
        conn = st.connect(db_path)
        # question captured for mining, and it was the model (not a rule) serving
        outcome, provider, tokens_out, feature, qnorm = _last(conn)
        assert provider != "rules" and qnorm == "show me the trend charts please"
    finally:
        _reset(conn); conn.close()


# ── 4. A rule can't send a user to a screen they can't open ───────────────────

def test_rule_target_out_of_user_catalog_falls_through(viewer, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        # 'users' (=/admin/users) is admin-only; a viewer's catalog never has it,
        # so a rule pointing there must fall through, not leak the admin page.
        _add_rule(conn, "show me the user accounts", "navigate", "users")
        monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
        st.set_setting(conn, "ai_mode", "off")
        conn.commit(); conn.close()
        r = viewer.post("/api/ai/route", data={"q": "show me the user accounts"})
        assert r.status_code == 200
        assert r.json() == {"kind": "fallback"}    # no rule served, AI off -> fallback
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ── 5. The master switch disables the whole layer ─────────────────────────────

def test_master_switch_off_bypasses_rules(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _add_rule(conn, "open the dashboard", "navigate", "pulse")
        st.set_setting(conn, "ai_rules_enabled", "0")
        monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
        st.set_setting(conn, "ai_mode", "off")
        conn.commit(); conn.close()
        r = admin.post("/api/ai/route", data={"q": "open the dashboard"})
        assert r.json() == {"kind": "fallback"}     # layer off + AI off -> fallback
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ── 6. top_questions surfaces model-answered questions as candidates ──────────

def test_top_questions_candidates(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        for _ in range(3):
            st.create_ai_interaction(conn, feature="nl_router", mode="router", outcome="ok",
                                     destination="trends", confidence=0.9,
                                     question_norm="show me the trends", provider="gemini")
        # a rules-served row must NOT be mined as a candidate
        st.create_ai_interaction(conn, feature="nl_router", mode="router", outcome="ok",
                                 destination="pulse", confidence=1.0,
                                 question_norm="open the dashboard", provider="rules")
        cands = st.top_questions(conn)
        by_q = {c["question"]: c for c in cands}
        assert by_q["show me the trends"]["count"] == 3
        assert by_q["show me the trends"]["destination"] == "trends"
        assert "open the dashboard" not in by_q     # served by a rule -> excluded
    finally:
        _reset(conn); conn.close()


# ── 7. /admin/rules gating + create flow ──────────────────────────────────────

def test_admin_rules_gated_and_create(admin, viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.commit(); conn.close()
    assert viewer.get("/admin/rules").status_code in (302, 303, 403)
    assert admin.get("/admin/rules").status_code == 200
    # create a rule via the admin form and confirm it lands enabled
    r = admin.post("/admin/rules/create",
                   data={"pattern": "open the dashboard", "kind": "navigate",
                         "target_key": "pulse", "source": "manual"},
                   follow_redirects=False)
    assert r.status_code in (302, 303)
    conn = st.connect(db_path)
    try:
        rules = st.list_learned_rules(conn)
        assert any(x["pattern"] == "open the dashboard" and x["target_key"] == "pulse"
                   for x in rules)
    finally:
        _reset(conn); conn.close()


def test_admin_rules_create_rejects_invalid_target(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.commit(); conn.close()
    r = admin.post("/admin/rules/create",
                   data={"pattern": "do a thing", "kind": "navigate",
                         "target_key": "not_a_real_key"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    conn = st.connect(db_path)
    try:
        assert not any(x["pattern"] == "do a thing" for x in st.list_learned_rules(conn))
    finally:
        _reset(conn); conn.close()
