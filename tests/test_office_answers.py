"""Office answers for the assistant (docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 6): each slot renders
from the asker's own data, the seeded FAQ rules route to them with the model switched off, and nothing
private (a whereabouts note) ever appears in an answer."""
from __future__ import annotations

from datetime import date

import httpx
import pytest
from starlette.testclient import TestClient

import ai_core as ai
import auth
import office_answers as oa
import office_connect as oconn
import qa_rules
import rooms
import storage as st

WED = date(2026, 10, 14)
SAT = date(2026, 10, 17)
SECRET = "Secretplace Xyzzy"


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("a rule hit must never reach the model")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


@pytest.fixture()
def world(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    st.basic_status_clear_cache()
    unit_a = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('OA-A','OA-A','section','OAN/D1/SA')").lastrowid
    unit_b = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('OA-B','OA-B','section','OAN/D1/SB')").lastrowid

    def person(name, unit, user):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES (?,1,?)", (name, unit)).lastrowid
        return st.create_admin_user(conn, user, "x", "y", "viewer", rp_id=rp)

    w = {"conn": conn, "ann": person("Annie Yarax", unit_a, "oa-ann@test.local"),
         "ben": person("Benny Yarax", unit_b, "oa-ben@test.local"),
         "nobody": st.create_admin_user(conn, "oa-nobody@test.local", "x", "y", "viewer")}
    conn.commit()
    yield w
    conn.execute("DELETE FROM whereabouts WHERE user_id IN (SELECT id FROM admin_user WHERE username LIKE 'oa-%')")
    conn.execute("DELETE FROM app_setting WHERE key='colleague_status_scope'")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'oa-%'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE '% Yarax'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'OAN%'")
    conn.execute("DELETE FROM holiday WHERE day IN ('2026-10-15')")
    conn.commit()
    st.basic_status_clear_cache()
    conn.close()


def U(w, key):
    return st.get_admin_user_by_id(w["conn"], w[key])


def say(w, key, who="ann", today=WED):
    return oa.SLOTS[key]["user_render"](w["conn"], U(w, who), today)


def report(w, who, day, status, note=None):
    w["conn"].execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note) VALUES (?,?,?,?)",
                      (w[who], day.isoformat(), status, note))
    w["conn"].commit()
    st.basic_status_clear_cache()


# ── every slot renders for someone with no data ───────────────────────────────

def test_every_slot_renders_text_for_a_user_with_no_data(world):
    for key in oa.SLOTS:
        out = say(world, key, who="nobody")
        assert isinstance(out, str) and out.strip(), key


def test_the_slot_set_and_seed_rules_agree(world):
    assert {k for _kind, k, _c, _a in oa.SEED_RULES} == set(oa.SLOTS)


def test_empty_todo_and_approvals_and_bookings(world, monkeypatch):
    monkeypatch.setattr(oconn, "home_tasks", lambda conn, user, today: [])
    assert say(world, "todo_summary") == "You have nothing on your to-do."
    assert say(world, "approvals_waiting") == "No approvals are waiting on you."
    assert say(world, "my_room_bookings") == "You have no upcoming conference room bookings."


def test_todo_lists_titles_only_in_order_and_caps(world, monkeypatch):
    tasks = [{"title": f"Task {i}", "detail": "SECRETDETAIL", "url": "/x", "tone": "todo"} for i in range(8)]
    monkeypatch.setattr(oconn, "home_tasks", lambda conn, user, today: tasks)
    out = say(world, "todo_summary")
    assert out.startswith("On your to-do: Task 0; Task 1;") and "SECRETDETAIL" not in out
    assert out.endswith("…and 2 more.") and out.count(";") == oa.MAX_LINES - 1


def test_approvals_counts(world, monkeypatch):
    monkeypatch.setattr(st, "pending_approval_counts", lambda conn, user: {"wellness": 2, "awa": 1})
    assert say(world, "approvals_waiting") == "Waiting for your decision: 2 wellness breaks and 1 work arrangement."


def test_wellness_left_and_next_break(world, monkeypatch):
    monkeypatch.setattr(st, "wellness_hours_used", lambda conn, uid, ws: 1)
    monkeypatch.setattr(st, "list_my_wellness_claims", lambda conn, uid, limit=25: [
        {"status": "approved", "break_date": "2026-10-16", "start_time": "10:00"},
        {"status": "denied", "break_date": "2026-10-15", "start_time": "09:00"}])
    out = say(world, "wellness_left")
    assert out == ("You have 1 hour of wellness break left this week (1 of 2 used). "
                   "Your next approved break: Fri Oct 16 at 10:00.")


def test_awa_answer_mentions_the_deadline(world, monkeypatch):
    monkeypatch.setattr(st, "work_arrangement_open_periods", lambda: ["2026-10-16"])
    monkeypatch.setattr(oconn, "_task_awa", lambda conn, user, today: {
        "title": "File your work arrangement for October 16-31, 2026", "detail": "due today"})
    out = say(world, "awa_status")
    assert out.startswith("File your work arrangement for October 16-31, 2026 (due today).")
    assert "The deadline is" in out


# ── who is in the office ──────────────────────────────────────────────────────

def test_office_today_lists_first_names_by_state(world):
    report(world, "ann", WED, "office")
    report(world, "ben", WED, "field", SECRET)
    out = say(world, "office_today")
    assert "In the office (" in out and "Annie" in out or "Benny" in out and "In the field (" in out
    assert SECRET.lower() not in out.lower()


def test_wfh_today_names_only_the_wfh_group(world):
    world["conn"].execute(
        "INSERT INTO work_arrangement(user_id, period_start, arrangement, weekday, status, created_at) "
        "VALUES (?, '2026-10-01', 'WFH', 2, 'approved', '2026-09-20')", (world["ann"],))
    world["conn"].commit()
    try:
        st.basic_status_clear_cache()
        out = say(world, "wfh_today")
        assert out.startswith("Working from home (") and "Annie" in out or "Benny" in out and "In the office" not in out
    finally:
        world["conn"].execute("DELETE FROM work_arrangement WHERE user_id=?", (world["ann"],))
        world["conn"].commit()


def test_a_weekend_is_not_a_working_day(world):
    assert say(world, "office_today", today=SAT) == "Today is not a working day."


def test_office_today_honours_the_team_switch(world):
    report(world, "ann", WED, "office")
    report(world, "ben", WED, "office")
    st.set_colleague_status_scope(world["conn"], "team")
    out = say(world, "office_today", who="ann")
    assert "Annie" in out and "Benny" not in out
    assert "isn't shared" in say(world, "office_today", who="nobody")


# ── the conference room ───────────────────────────────────────────────────────

def test_room_free_windows_and_closed_days(world):
    out = say(world, "room_today")
    assert out.startswith("The conference room is free today: ") and "–" in out
    assert say(world, "room_today", today=SAT) == "The conference room is closed today (not a working day)."
    st.set_holiday(world["conn"], "2026-10-15", "Test holiday")
    assert say(world, "room_tomorrow") == "The conference room is closed tomorrow (not a working day)."


def test_room_windows_split_around_a_booked_hour(world):
    slots = rooms.list_slots(world["conn"])
    assert len(slots) >= 3
    mid = slots[1]
    rooms.add_block(world["conn"], "oa-ann@test.local", WED, [mid["id"]], "test", today=WED)
    try:
        out = say(world, "room_today")
        assert out.count("–") >= 2          # two windows either side of the blocked hour
    finally:
        world["conn"].execute("DELETE FROM room_block WHERE reason='test'")
        world["conn"].commit()


def test_my_room_bookings_lists_own_upcoming(world, monkeypatch):
    monkeypatch.setattr(rooms, "list_for_user", lambda conn, uid, upcoming_only=False, today=None: [
        {"id": 2, "title": "Budget huddle", "day": "2026-10-20", "status": "approved"},
        {"id": 1, "title": "Planning", "day": "2026-10-15", "status": "requested"}])
    out = say(world, "my_room_bookings")
    assert out == ("Your conference room bookings: Thu Oct 15: Planning (waiting for approval); "
                   "Tue Oct 20: Budget huddle.")


# ── seed rules answer with the model switched off ─────────────────────────────

QUESTIONS = {
    "todo_summary": ["what is on my to do", "my to do list"],
    "approvals_waiting": ["do i have approvals"],
    "wellness_left": ["how many wellness hours do i have left", "ilan oras wellness ko"],
    "awa_status": ["did i file my awa", "when is the awa deadline"],
    "office_today": ["who is in the office today", "sino ang nasa opisina"],
    "wfh_today": ["who is working from home today"],
    "room_today": ["is the conference room free today", "free ba ang conference room ngayon"],
    "room_tomorrow": ["free ba ang conference room bukas"],
    "my_room_bookings": ["my room bookings"],
}


def test_seed_rules_route_to_their_slot_with_ai_off(app_mod, admin):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    st.set_setting(conn, "ai_mode", "off")
    conn.execute("DELETE FROM learned_rule")
    conn.execute("DELETE FROM app_setting WHERE key='office_rules_seeded'")
    conn.commit()
    app_mod._seed_office_rules(conn)
    assert st.get_setting(conn, "office_rules_seeded") == "1"
    app_mod._seed_office_rules(conn)                               # idempotent
    assert len(st.list_learned_rules(conn)) == sum(1 + len(a) for _k, _t, _c, a in oa.SEED_RULES)
    conn.close()
    try:
        for key, questions in QUESTIONS.items():
            for q in questions:
                body = admin.post("/api/ai/route", data={"q": q}).json()
                assert body["kind"] == "answer" and body.get("served_by") == "rules", (q, body)
                assert body["label"] == oa.SLOTS[key]["label"], (q, body)
    finally:
        conn = st.connect(app_mod.DB)
        conn.execute("DELETE FROM learned_rule")
        conn.execute("DELETE FROM app_setting WHERE key IN ('office_rules_seeded', 'ai_mode')")
        conn.commit()
        conn.close()


def test_the_router_prompt_names_the_new_topics_and_carries_no_data(app_mod):
    p = app_mod._ai_router_system_prompt(True, False, False)
    assert "to-dos" in p and "who is in the office" in p
    assert "Yarax" not in p
