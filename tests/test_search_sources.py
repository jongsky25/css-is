"""The office-wide search sources (docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 4): calendar,
to-do, own requests, conference room, help. Each calls the same function as the page it links to,
as the signed-in person, so the checks here are mostly "search never shows more than the page".
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import search_sources as ss
import storage as st
import tzutil as tz
from conftest import _auth_client

NEW_SECTIONS = {"Calendar", "My to-do", "My requests", "Conference room", "Help"}


def _sections(rows):
    return {r["section"] for r in rows}


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    c.execute("DELETE FROM calendar_entry WHERE title LIKE 'ZQ%'")
    c.commit()
    c.close()


def _entry(conn, title, days_ahead=2, **kw):
    d = (tz.today_local() + timedelta(days=days_ahead)).isoformat()
    return st.cal_create(conn, title, d, **kw)


# ── Calendar ──────────────────────────────────────────────────────────────────

def test_calendar_finds_a_visible_entry_with_date_only_hint(app_mod, conn):
    eid = _entry(conn, "ZQ Audit Meeting", audience="bureau", start_time="13:00",
                 note="secretnote", meeting_url="https://meet.example/secretlink", by="admin@test.local")
    rows = _auth_client(app_mod, "admin").get("/api/search?q=zq audit").json()
    cal = [r for r in rows if r["section"] == "Calendar"]
    assert [r["title"] for r in cal] == ["ZQ Audit Meeting"]
    assert cal[0]["url"] == f"/calendar/entries/{eid}"
    assert "13:00" in cal[0]["hint"]
    blob = str(rows)
    assert "secretnote" not in blob and "secretlink" not in blob


def test_another_users_private_entry_is_not_found(app_mod, conn):
    _entry(conn, "ZQ Private Thing", audience="people", by="admin@test.local")
    mine = _auth_client(app_mod, "admin").get("/api/search?q=zq private").json()
    assert [r["title"] for r in mine if r["section"] == "Calendar"] == ["ZQ Private Thing"]
    theirs = _auth_client(app_mod, "viewer").get("/api/search?q=zq private").json()
    assert not [r for r in theirs if r["section"] == "Calendar"]


def test_calendar_skips_cancelled_and_postponed(app_mod, conn):
    _entry(conn, "ZQ Called Off", audience="bureau", status="cancelled")
    _entry(conn, "ZQ Pushed Back", audience="bureau", status="postponed")
    rows = _auth_client(app_mod, "admin").get("/api/search?q=zq").json()
    assert not [r for r in rows if r["section"] == "Calendar"]


def test_calendar_is_nearest_first_and_capped(app_mod, conn):
    for n in (9, 1, 5, 3, 7, 4, 2):
        _entry(conn, f"ZQ Day{n}", days_ahead=n, audience="bureau")
    rows = _auth_client(app_mod, "admin").get("/api/search?q=zq day").json()
    assert [r["title"] for r in rows if r["section"] == "Calendar"] == [
        "ZQ Day1", "ZQ Day2", "ZQ Day3", "ZQ Day4", "ZQ Day5"]


# ── My to-do ──────────────────────────────────────────────────────────────────

def test_todo_matches_title_and_detail(app_mod, monkeypatch):
    monkeypatch.setattr(ss.oconn, "home_tasks", lambda conn, user, today: [
        {"title": "Approve zebra requests", "detail": "3 waiting", "url": "/approvals", "tone": "todo"},
        {"title": "Something else", "detail": "nothing", "url": "/x", "tone": "info"}])
    rows = _auth_client(app_mod, "admin").get("/api/search?q=zebra").json()
    assert [(r["section"], r["url"]) for r in rows] == [("My to-do", "/approvals")]
    rows = _auth_client(app_mod, "admin").get("/api/search?q=waiting").json()
    assert [r["title"] for r in rows if r["section"] == "My to-do"] == ["Approve zebra requests"]


def test_wellness_finds_the_todo_and_the_pages(admin):
    rows = admin.get("/api/search?q=wellness").json()
    assert "My to-do" in _sections(rows)


# ── My requests ───────────────────────────────────────────────────────────────

def test_requests_only_ever_asks_for_the_signed_in_users_own_claims(app_mod, monkeypatch):
    asked = []

    def fake(conn, user_id, limit=25):
        asked.append(user_id)
        return [{"id": 1, "break_date": "2026-10-12", "start_time": "10:00", "status": "pending"}]

    monkeypatch.setattr(ss.st, "list_my_wellness_claims", fake)
    me = st.get_admin_user(st.connect(app_mod.DB), "viewer@test.local")["id"]
    rows = _auth_client(app_mod, "viewer").get("/api/search?q=wellness").json()
    assert asked and set(asked) == {me}              # the to-do strip reads it too, also as me
    mine = [r for r in rows if r["section"] == "My requests"]
    assert mine and mine[0]["url"] == "/wellness" and "pending" in mine[0]["hint"]


# ── Conference room ───────────────────────────────────────────────────────────

def test_room_word_gives_the_booking_row(admin):
    rows = admin.get("/api/search?q=room").json()
    assert [r["url"] for r in rows if r["title"] == "Book the conference room"] == ["/rooms"]


def test_room_lists_own_upcoming_reservations_only(app_mod, monkeypatch):
    seen = []

    def fake(conn, user_id, upcoming_only=False, today=None):
        seen.append((user_id, upcoming_only))
        return [{"title": "Strategy huddle", "day": "2026-10-14", "status": "approved"}]

    monkeypatch.setattr(ss.rooms, "list_for_user", fake)
    rows = _auth_client(app_mod, "admin").get("/api/search?q=huddle").json()
    assert [r["title"] for r in rows if r["section"] == "Conference room"] == ["Strategy huddle"]
    assert seen and all(up for _u, up in seen)


# ── Help ──────────────────────────────────────────────────────────────────────

def test_help_finds_a_page_guide_with_the_tour_link(admin):
    rows = admin.get("/api/search?q=jump").json()
    h = [r for r in rows if r["section"] == "Help"]
    assert h and all(r["url"].endswith("tour=1") for r in h)


# ── scope + length ────────────────────────────────────────────────────────────

def test_css_scope_returns_none_of_the_new_sections(app_mod, conn):
    _entry(conn, "ZQ Scoped", audience="bureau")
    for q in ("zq scoped", "room", "wellness", "jump"):
        rows = _auth_client(app_mod, "admin").get(f"/api/search?q={q}&scope=css").json()
        assert not (_sections(rows) & NEW_SECTIONS), q


def test_one_character_searches_nothing(admin):
    assert admin.get("/api/search?q=r").json() == []
