"""
POST /api/ai/route kind=answer — the "maximize" grounded-answer engine
(docs/AI_INTEGRATION_PLAN.md Phase 2, extended). The default "catalog" engine
stays classify-only (covered by test_ai_answers.py); this file covers the
opt-in engine that composes a real answer from a server-built data pack.

What's asserted:
* the grounded engine only runs when BOTH the engine is set to "maximize" AND
  the nl_answer_grounded feature flag is on — otherwise the classic canned slot
  render is used (byte-for-byte the catalog behaviour);
* a grounded, confident model answer is returned as model-authored prose with
  served_by="grounded" and its own nl_answer_grounded log row;
* every failure mode of the grounded call (model says grounded=false, low
  confidence, or an AIError) falls back to the canned slot render / palette —
  the assistant never errors and never invents a number;
* the data pack is PII-safe: resource-person names are excluded unless the
  admin opts in (ai_answer_people), and attendee emails never appear.

Autouse fixture guarantees this file never reaches the real network.
"""
import json

import httpx
import pytest

import ai_core as ai
import app as app_mod
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
    conn.execute("DELETE FROM learned_rule")   # seeded FAQ rules would preempt the model path
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


def _configure_maximize(conn, monkeypatch, *, engine="maximize", grounded_flag="1",
                        people="0"):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "answers")
    st.set_setting(conn, "ai_answer_engine", engine)
    st.set_setting(conn, "ai_feature_nl_answer_grounded", grounded_flag)
    st.set_setting(conn, "ai_answer_people", people)
    # Skip the deterministic FAQ layer so we always exercise the model path.
    st.set_setting(conn, "ai_rules_enabled", "0")


def _mock_router_then_grounded(monkeypatch, *, router_fields, grounded=None,
                               grounded_raises=False):
    """Dispatch the two model calls the maximize path makes: the classifying
    nl_router call and the composing nl_answer_grounded call. They are told
    apart by the grounded call's distinctive system prompt."""
    router_payload = {"kind": "answer", "confidence": 0.9, "reason": "x"}
    router_payload.update(router_fields)

    def _gen(prompt, *, system=None, response_schema=None, **kw):
        if system == app_mod._AI_GROUNDED_SYSTEM:
            if grounded_raises:
                raise ai.AIBadResponse("grounded call blew up")
            payload = grounded
        else:
            payload = router_payload
        return {"text": json.dumps(payload), "parsed": payload,
                "tokens_in": 5, "tokens_out": 5, "latency_ms": 10, "model": "gemini-test"}

    monkeypatch.setattr(ai, "_http_generate", _gen)


FAKE_STATS = {"responses": {"d30": 42, "ytd": 100, "quarter": 60, "all": 500},
              "people_rated": {"d30": 7, "ytd": 20, "quarter": 12, "all": 90},
              "satisfaction": {"d30": 88, "ytd": 91, "quarter": 90, "all": 92},
              "activities": {"d30": 3, "ytd": 15, "quarter": 8, "all": 60}}


def _rows(conn, feature):
    return conn.execute(
        "SELECT outcome FROM ai_interaction WHERE feature=? ORDER BY id", (feature,)).fetchall()


# ---- grounded happy path ------------------------------------------------------

def test_maximize_returns_grounded_prose(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "data_question", "confidence": 0.9},
            grounded={"answer": "Satisfaction is 88% over the last 30 days.",
                      "grounded": True, "confidence": 0.9})
        r = admin.post("/api/ai/route", data={"q": "how have we been doing lately"})
        body = r.json()
        assert body["kind"] == "answer"
        assert body["served_by"] == "grounded"
        assert body["text"] == "Satisfaction is 88% over the last 30 days."
        conn = st.connect(db_path)
        assert _rows(conn, "nl_answer_grounded") == [("ok",)]
    finally:
        _reset(conn); conn.close()


# ---- fallbacks: grounded call fails -> canned slot render ----------------------

def test_maximize_ungrounded_falls_back_to_canned_slot(admin, db_path, monkeypatch):
    """Model says grounded=false: the router picked a real slot, so the classic
    templated sentence answers instead — never an error."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "responses_30d", "confidence": 0.9},
            grounded={"answer": "I don't have that.", "grounded": False, "confidence": 0.9})
        r = admin.post("/api/ai/route", data={"q": "how many responses this month"})
        body = r.json()
        assert body["kind"] == "answer"
        assert body.get("served_by") != "grounded"
        assert "42" in body["text"]              # canned template over FAKE_STATS
        conn = st.connect(db_path)
        assert _rows(conn, "nl_answer_grounded") == [("rejected_validation",)]
        assert ("ok",) in _rows(conn, "nl_answer")
    finally:
        _reset(conn); conn.close()


def test_maximize_grounded_low_confidence_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "responses_30d", "confidence": 0.9},
            grounded={"answer": "maybe 42?", "grounded": True, "confidence": 0.2})
        r = admin.post("/api/ai/route", data={"q": "how many responses this month"})
        assert "42" in r.json()["text"]          # canned fallback
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_maximize_grounded_aierror_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "responses_30d", "confidence": 0.9},
            grounded_raises=True)
        r = admin.post("/api/ai/route", data={"q": "how many responses this month"})
        assert "42" in r.json()["text"]          # canned fallback, no error
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_maximize_broad_key_ungrounded_falls_back_to_palette(admin, db_path, monkeypatch):
    """When the router used the broad data_question key (not a real slot) and
    the grounded call can't answer, there's nothing canned to render — the page
    degrades to the keyword palette (kind=fallback)."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "data_question", "confidence": 0.9},
            grounded={"answer": "no idea", "grounded": False, "confidence": 0.9})
        r = admin.post("/api/ai/route", data={"q": "what colour is the sky"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- the engine is genuinely gated -------------------------------------------

def test_catalog_engine_never_calls_grounded(admin, db_path, monkeypatch):
    """Default engine: the grounded model call must not fire at all — a mock
    that raises if the grounded system prompt is ever used proves it."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch, engine="catalog")
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "responses_30d", "confidence": 0.9},
            grounded_raises=True)   # would surface if the grounded call ran
        r = admin.post("/api/ai/route", data={"q": "how many responses this month"})
        assert "42" in r.json()["text"]
        conn = st.connect(db_path)
        assert _rows(conn, "nl_answer_grounded") == []   # never called
    finally:
        _reset(conn); conn.close()


def test_maximize_feature_flag_off_stays_catalog(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_maximize(conn, monkeypatch, grounded_flag="0")
        conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        _mock_router_then_grounded(
            monkeypatch,
            router_fields={"answer_slot": "responses_30d", "confidence": 0.9},
            grounded_raises=True)
        r = admin.post("/api/ai/route", data={"q": "how many responses this month"})
        assert "42" in r.json()["text"]
        conn = st.connect(db_path)
        assert _rows(conn, "nl_answer_grounded") == []
    finally:
        _reset(conn); conn.close()


# ---- data pack is PII-safe ----------------------------------------------------

def test_data_pack_excludes_people_by_default(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    try:
        pack = app_mod._ai_data_pack(conn, include_people=False)
        assert "ORG-WIDE TOTALS" in pack
        assert "PER-RESOURCE-PERSON" not in pack
        assert "@" not in pack                 # no email ever leaks in
    finally:
        conn.close()


def test_data_pack_includes_people_when_opted_in(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    try:
        with_people = app_mod._ai_data_pack(conn, include_people=True)
        without = app_mod._ai_data_pack(conn, include_people=False)
        # The seed DB has resource-person ratings; opting in surfaces the section
        # (and its names) that the default pack withholds.
        assert "PER-RESOURCE-PERSON" in with_people
        assert "PER-RESOURCE-PERSON" not in without
        assert "@" not in with_people
    finally:
        conn.close()
