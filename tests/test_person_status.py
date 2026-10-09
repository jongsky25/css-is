"""The person_status answer: "where is Mimi today?" (docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 7, item 3).

The model returns the slot key and the name as typed. The name is an untrusted argument: cleaned, checked
against the question, resolved against the directory by the server. What is shown is the directory's own
name and the basic status (which honours the admin's bureau/team switch) — never anything the model wrote.
"""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

import ai_core as ai
import office_answers as oa
import storage as st
from conftest import _auth_client

WED = date(2026, 10, 14)
SECRET = "Secretplace Xyzzy"


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network in an AI test — mock it")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


@pytest.fixture()
def world(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    st.basic_status_clear_cache()
    ua = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('PS-A','PS-A','section','PSN/D1/SA')").lastrowid
    ub = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('PS-B','PS-B','section','PSN/D1/SB')").lastrowid

    def person(name, unit, user, nick=None):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES (?,1,?)", (name, unit)).lastrowid
        uid = st.create_admin_user(conn, user, "x", "y", "viewer", rp_id=rp)
        if nick:
            conn.execute("UPDATE admin_user SET nickname=? WHERE id=?", (nick, uid))
        return uid

    w = {"conn": conn, "mimi": person("Qwerta Zumba", ua, "ps-mimi@test.local", nick="Zumby"),
         "tess1": person("Tessa Quillon", ua, "ps-tess1@test.local"),
         "tess2": person("Tessa Rowland", ub, "ps-tess2@test.local"),
         "viewer": person("Viola Vance", ua, "ps-viewer@test.local"),
         "nobody": st.create_admin_user(conn, "ps-nobody@test.local", "x", "y", "viewer")}
    conn.commit()
    yield w
    conn.execute("DELETE FROM whereabouts WHERE user_id IN (SELECT id FROM admin_user WHERE username LIKE 'ps-%')")
    conn.execute("DELETE FROM app_setting WHERE key IN ('colleague_status_scope','ai_mode')")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ps-%'")
    conn.execute("DELETE FROM resource_person WHERE name IN ('Qwerta Zumba','Tessa Quillon','Tessa Rowland','Viola Vance')")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'PSN%'")
    conn.commit()
    st.basic_status_clear_cache()
    conn.close()


def report(w, who, day, status, note=None):
    w["conn"].execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note) VALUES (?,?,?,?)",
                      (w[who], day.isoformat(), status, note))
    w["conn"].commit()
    st.basic_status_clear_cache()


def U(w, key):
    return st.get_admin_user_by_id(w["conn"], w[key])


# ── the name argument is validated ────────────────────────────────────────────

@pytest.mark.parametrize("raw,query,ok", [
    ("Mimi", "where is mimi today", True),
    ("Ma. Cristina", "where is Ma. Cristina today", True),
    ("Zumby", "WHERE IS ZUMBY", True),
    ("Mimi", "where is jong today", False),              # a name the question never contained
    ("<script>", "where is <script> today", False),
    ("Mimi; DROP", "where is mimi; drop today", False),
    ("M", "where is m", False),
    ("x" * 41, "x" * 41, False),
    ("Mimi 3", "where is mimi 3", False),                # digits are not part of a name
    (None, "where is mimi", False),
    (123, "where is 123", False),
    ("", "where is mimi", False),
])
def test_clean_person_name(raw, query, ok):
    assert (oa.clean_person_name(raw, query) is not None) is ok


# ── resolving against the directory ───────────────────────────────────────────

def test_a_nickname_resolves_to_one_person_and_shows_the_directory_name(world):
    report(world, "mimi", WED, "office")
    out = oa.person_status(world["conn"], U(world, "nobody"), WED, "Zumby")
    assert out["text"] == "Qwerta Zumba is in the office today."
    assert out["links"] == [{"label": "Open card →", "url": f"/people/{world['mimi']}"}]


def test_each_basic_state_has_its_sentence(world):
    for status, expect in (("field", "is in the field today"), ("leave", "is on leave today"), ("office", "is in the office today")):
        report(world, "mimi", WED, status, SECRET)
        out = oa.person_status(world["conn"], U(world, "nobody"), WED, "Zumby")
        assert expect in out["text"] and SECRET.lower() not in json.dumps(out).lower()


def test_a_weekend_reads_off(world):
    out = oa.person_status(world["conn"], U(world, "nobody"), date(2026, 10, 17), "Zumby")
    assert out["text"] == "Qwerta Zumba is off today."


def test_two_matches_are_not_guessed_between(world):
    out = oa.person_status(world["conn"], U(world, "nobody"), WED, "Tessa")
    assert out["text"].startswith("I couldn't tell who you mean.")
    assert {l["label"] for l in out["links"]} == {"Tessa Quillon", "Tessa Rowland"}
    assert {l["url"] for l in out["links"]} == {f"/people/{world['tess1']}", f"/people/{world['tess2']}"}


def test_nobody_by_that_name(world):
    out = oa.person_status(world["conn"], U(world, "nobody"), WED, "Xenophon")
    assert out == {"text": "I couldn't tell who you mean. Try their full name.", "links": []}


def test_someone_without_a_directory_record_is_not_found(world):
    assert oa.person_status(world["conn"], U(world, "viewer"), WED, "Nobody Unlinked")["links"] == []


def test_the_team_switch_applies(world):
    report(world, "mimi", WED, "office")
    st.set_colleague_status_scope(world["conn"], "team")
    out = oa.person_status(world["conn"], U(world, "viewer"), WED, "Zumby")           # same section: visible
    assert out["text"] == "Qwerta Zumba is in the office today."
    other = oa.person_status(world["conn"], U(world, "tess2"), WED, "Zumby")          # a different section
    assert other["text"] == "Colleague status isn't shared with your account for Qwerta Zumba."
    assert oa.person_status(world["conn"], U(world, "nobody"), WED, "Zumby")["text"].startswith("Colleague status isn't shared")


def test_the_slot_alone_asks_for_a_name(world):
    slot = oa.SLOTS["person_status"]
    assert "Tell me whose status" in slot["user_render"](world["conn"], U(world, "nobody"), WED)
    assert slot["takes_name"] is True


# ── through the router, with a mocked model ───────────────────────────────────

def _route(app_mod, world, monkeypatch, query, **payload):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM ai_interaction"); conn.execute("DELETE FROM ai_budget")
    conn.execute("DELETE FROM learned_rule"); conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "answers")
    conn.commit(); conn.close()
    body = {"kind": "answer", "answer_slot": "person_status", "confidence": 0.9, "reason": "x"}
    body.update(payload)
    seen = {}

    def fake(*a, **kw):
        seen["prompt"] = a[3] if len(a) > 3 else kw.get("prompt")
        return {"text": json.dumps(body), "parsed": body, "tokens_in": 5, "tokens_out": 5,
                "latency_ms": 40, "model": "gemini-test"}

    monkeypatch.setattr(ai, "_http_generate", fake)
    return _auth_client(app_mod, "admin").post("/api/ai/route", data={"q": query}).json()


def test_routed_answer_uses_the_directory_name_and_links(app_mod, world, monkeypatch):
    report(world, "mimi", app_mod._today_local(), "office")
    d = _route(app_mod, world, monkeypatch, "where is Zumby today?", person_name="Zumby")
    assert d["kind"] == "answer" and d["label"] == oa.SLOTS["person_status"]["label"]
    if app_mod._today_local().weekday() < 5:
        assert d["text"] == "Qwerta Zumba is in the office today."
    assert d["links"][0]["url"] == f"/people/{world['mimi']}"


def test_a_name_the_question_never_contained_is_refused(app_mod, world, monkeypatch):
    d = _route(app_mod, world, monkeypatch, "where is Zumby today?", person_name="Tessa Quillon")
    assert d["kind"] == "answer" and d["text"].startswith("I couldn't tell who you mean.")
    assert "Quillon" not in json.dumps(d)                     # the model's name never becomes output


def test_a_missing_or_junk_name_gets_the_polite_answer(app_mod, world, monkeypatch):
    for kw in ({}, {"person_name": "<img src=x>"}, {"person_name": "A" * 80}):
        d = _route(app_mod, world, monkeypatch, "where is Zumby today?", **kw)
        assert d["text"] == "I couldn't tell who you mean. Try their full name." and "links" not in d


def test_the_prompt_asks_for_the_name_and_carries_no_directory_data(app_mod, world, monkeypatch):
    _route(app_mod, world, monkeypatch, "where is Zumby today?", person_name="Zumby")
    p = app_mod._ai_router_system_prompt(True, False, False)
    assert "person_name" in p and "Zumba" not in p
    assert "Zumba" not in (json.dumps(app_mod._ai_router_schema(True, False, False)))
    assert "person_name" in app_mod._ai_router_schema(True, False, False)["properties"]


def test_the_assistant_card_renders_links():
    import os
    js = open(os.path.join(os.path.dirname(__file__), "..", "static", "js", "assistant.js"), encoding="utf-8").read()
    assert "linksHtml(data.links)" in js and "esc(l.url)" in js and "esc(l.label)" in js
