"""The read API and the assistant's calendar answers (office calendar H3)."""
from __future__ import annotations
from datetime import date, timedelta

import httpx
import pytest

import ai_core as ai
import calendar_answers as ca
import office_calendar as oc
import qa_rules
import storage as st
import tzutil as tz
from conftest import in_the_directory
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

WED = date(2026, 10, 14)                      # a Wednesday: this week = Oct 14-18, next week = Oct 19-25


def D(n):
    return (WED + timedelta(days=n)).isoformat()


def add(w, title, day, who=("s1",), **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(w["conn"], title, D(day), people=[(w[p]["id"], "attending") for p in who], by="x@x", **kw)


def say(w, key, who="s1", today=WED):
    return ca.SLOTS[key]["user_render"](w["conn"], w[who], today)


# -------------------------------------------------------------- the answers ---

def test_today_and_tomorrow(world):                                                            # noqa: F811
    assert say(world, "calendar_today") == "Nothing on your calendar today."
    add(world, "Orientation", 0, start_time="09:00"); add(world, "Budget call", 1)
    assert say(world, "calendar_today") == "You have one thing today: Wed 14: Orientation at 09:00."
    assert say(world, "calendar_tomorrow") == "You have one thing tomorrow: Thu 15: Budget call."


def test_the_rest_of_this_week_and_next_week(world):                                           # noqa: F811
    add(world, "Past", -2); add(world, "Friday thing", 2); add(world, "Next Monday", 5); add(world, "Next Friday", 9)
    assert say(world, "calendar_this_week") == "For the rest of this week (Oct 14–18) you have one thing: Fri 16: Friday thing."
    nxt = say(world, "calendar_next_week")
    assert nxt.startswith("Next week (Oct 19–25) you have 2 things:") and "Mon 19: Next Monday" in nxt and "Fri 23: Next Friday" in nxt
    assert "Past" not in say(world, "calendar_this_week")
    assert say(world, "calendar_next_week", who="s3").startswith("Next week (Oct 19–25) you have 2 things")      # bureau-wide items


def test_nothing_and_the_cap(world):                                                            # noqa: F811
    assert say(world, "calendar_next_week") == "Nothing on your calendar next week (Oct 19–25)."
    for i in range(9):
        add(world, f"Item {i}", 5 + (i % 5))
    text = say(world, "calendar_next_week")
    assert "you have 9 things" in text and text.endswith("…and 3 more.") and text.count(";") == ca.MAX_LINES - 1


def test_background_and_non_events_are_left_out_and_tentative_is_marked(world):                 # noqa: F811
    add(world, "Banner", 6, kind="banner"); add(world, "Postponed", 6, status="postponed")
    gone = add(world, "Gone", 6); st.cal_cancel(world["conn"], gone)
    add(world, "Maybe", 6, status="tentative")
    assert say(world, "calendar_next_week") == "Next week (Oct 19–25) you have one thing: Tue 20: Maybe (tentative)."


def test_you_are_only_told_about_what_you_may_see(world):                                       # noqa: F811
    add(world, "Secret", 6, who=("s3",), audience="people")
    add(world, "Mine, private", 7, who=("s1",), audience="people")
    mine = say(world, "calendar_next_week")
    assert "Secret" not in mine and "Mine, private" in mine
    assert "Mine, private" not in say(world, "calendar_next_week", who="s3") and "Secret" in say(world, "calendar_next_week", who="s3")
    assert say(world, "calendar_next_week", who="nobody") == "Nothing on your calendar next week (Oct 19–25)."


def test_the_next_item(world):                                                                  # noqa: F811
    assert say(world, "calendar_next_item") == "Nothing coming up on your calendar in the next three months."
    add(world, "Later", 20); add(world, "Soon", 3)
    assert say(world, "calendar_next_item") == "Your next item: Sat 17: Soon."


def test_who_is_away_names_trips_and_leave_without_reasons(world):                              # noqa: F811
    c = world["conn"]
    st.cal_create(c, "Palawan monitoring", D(6), end_date=D(8), kind="travel", audience="bureau",
                  people=[(world["s1b"]["id"], "travel")], by="x@x")
    c.execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
              (world["s1"]["id"], D(7), "leave", "secret reason", "x")); c.commit()
    text = say(world, "calendar_away_next_week")
    assert text.startswith("Away next week (Oct 19–25):") and "(Palawan monitoring)" in text and "on leave Oct 21" in text
    assert "secret reason" not in text
    assert say(world, "calendar_away_this_week") == "Nobody you can see is away this week (Oct 14–18)."
    assert "on leave" not in say(world, "calendar_away_next_week", who="s3")                        # not in S3's team: no leave shown


def test_birthdays_this_week_only_shared_ones_and_not_your_own(world):                          # noqa: F811
    st.set_birthday(world["conn"], world["dir"]["id"], WED.month, WED.day + 2, "bureau")
    st.set_birthday(world["conn"], world["s1b"]["id"], WED.month, WED.day + 1, "none")
    st.set_birthday(world["conn"], world["s1"]["id"], WED.month, WED.day, "bureau")
    text = say(world, "calendar_birthdays")
    assert text.startswith("Birthdays this week: ") and "(Fri 16)" in text and text.count("(") == 1
    assert "(Fri 16)" in say(world, "calendar_birthdays", who="nobody")              # bureau-wide share reaches an unlinked account
    st.clear_birthday(world["conn"], world["dir"]["id"])
    assert say(world, "calendar_birthdays") == "No shared birthdays in the next seven days."


def test_every_slot_is_a_static_label_with_keywords_and_the_seeds_point_at_real_slots():
    for key, slot in ca.SLOTS.items():
        assert key.startswith("calendar_") and slot["label"] and slot["kw"] and callable(slot["user_render"])
        assert "render" not in slot                                          # never mistaken for a statistics slot
    for kind, key, canonical, alts in ca.SEED_RULES:
        assert kind == "answer" and key in ca.SLOTS and canonical and alts


# ----------------------------------------------------- through the assistant ---

@pytest.fixture()
def assistant(app_mod, viewer, monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("a calendar question reached the network")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    c = st.connect(app_mod.DB); st.init_db(c)
    c.execute("DELETE FROM learned_rule"); c.commit()
    for kind, key, canonical, alts in ca.SEED_RULES:
        st.create_learned_rule(c, pattern=qa_rules.normalize(canonical), kind=kind, target_key=key,
                               keywords=" ".join([canonical] + alts), sample_query=canonical, source="seed")
    yield c
    c.execute("DELETE FROM learned_rule"); c.execute("DELETE FROM ai_interaction")
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'ASKTEST %'").fetchall():
        st.cal_delete(c, i)
    c.commit(); c.close()


def test_a_calendar_question_is_answered_from_the_askers_calendar_with_no_model(app_mod, viewer, assistant):
    c = assistant
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    day = tz.today_local()
    st.cal_create(c, "ASKTEST Orientation", day.isoformat(), audience="people", people=[(uid, "attending")], by="x@x")
    st.cal_create(c, "ASKTEST Someone else's", day.isoformat(), audience="people", by="x@x")
    r = viewer.post("/api/ai/route", data={"q": "What do I have today?"})
    body = r.json()
    assert r.status_code == 200 and body["kind"] == "answer" and body["served_by"] == "rules"
    assert "ASKTEST Orientation" in body["text"] and "Someone else's" not in body["text"]
    row = c.execute("SELECT provider, tokens_out, feature FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()
    assert row == ("rules", 0, "nl_answer")


def test_the_same_question_gives_each_person_their_own_answer(app_mod, viewer, admin, assistant):
    c = assistant
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    st.cal_create(c, "ASKTEST Mine", tz.today_local().isoformat(), audience="people", people=[(uid, "attending")], by="x@x")
    assert "ASKTEST Mine" in viewer.post("/api/ai/route", data={"q": "what do i have today"}).json()["text"]
    assert "ASKTEST Mine" not in admin.post("/api/ai/route", data={"q": "what do i have today"}).json()["text"]


def test_the_model_is_only_ever_offered_labels_and_keywords(app_mod):
    offered = " ".join(f"{k}: {v['label']} — {v['kw']}" for k, v in app_mod.AI_ANSWER_SLOTS.items() if k.startswith("calendar_"))
    assert "calendar_next_week" in offered and "2026" not in offered and "Orientation" not in offered


def test_the_calendar_rules_are_seeded_once_on_an_existing_install(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    saved = c.execute("SELECT value FROM app_setting WHERE key='calendar_rules_seeded'").fetchone()
    try:
        c.execute("DELETE FROM learned_rule"); c.execute("DELETE FROM app_setting WHERE key='calendar_rules_seeded'")
        st.create_learned_rule(c, pattern="an existing curated rule", kind="navigate", target_key="pulse", source="manual"); c.commit()
        app_mod._seed_calendar_rules(c)
        keys = {r["target_key"] for r in st.list_learned_rules(c) if r["target_key"].startswith("calendar_")}
        assert keys == {k for _kind, k, _c, _a in ca.SEED_RULES}
        c.execute("DELETE FROM learned_rule WHERE target_key LIKE 'calendar_%'"); c.commit()
        app_mod._seed_calendar_rules(c)                                       # the admin removed them: not resurrected
        assert not [r for r in st.list_learned_rules(c) if r["target_key"].startswith("calendar_")]
    finally:
        c.execute("DELETE FROM learned_rule")
        if saved:
            c.execute("INSERT OR REPLACE INTO app_setting(key, value) VALUES ('calendar_rules_seeded', ?)", (saved[0],))
        c.commit(); c.close()


# ------------------------------------------------------------------ the API ---

API_KEYS = {"id", "layer", "title", "kind", "status", "start", "end", "start_time", "end_time", "all_day", "owner", "venue",
            "modality", "has_meeting_link", "tags", "url", "repeats", "people", "activity"}


@pytest.fixture()
def api(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    yield c, uid
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'APITEST %'").fetchall():
        st.cal_delete(c, i)
    c.execute("DELETE FROM whereabouts WHERE note='APITEST reason'")
    st.clear_birthday(c, uid); c.commit(); c.close()


def day_n(n):
    return (tz.today_local() + timedelta(days=n)).isoformat()


def test_signed_out_callers_get_nothing(app_mod, client):
    r = client.get("/api/calendar", follow_redirects=False)
    assert r.status_code in (302, 303, 401) and "items" not in r.text


def test_the_default_answer_is_a_whitelisted_list_of_items(app_mod, viewer, api):
    c, uid = api
    st.cal_create(c, "APITEST Visit", day_n(2), kind="meeting", audience="bureau", venue="Room 5", people=[(uid, "attending")],
                  note="PRIVATE NOTE", meeting_url="https://zoom.example/secret", by="x@x")
    r = viewer.get("/api/calendar")
    body = r.json()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert body["start"] == day_n(0) and body["end"] == day_n(13) and body["scope"] == "blend" and body["count"] == len(body["items"])
    item = next(i for i in body["items"] if i["title"] == "APITEST Visit")
    assert set(item) == API_KEYS and item["has_meeting_link"] is True and item["venue"] == "Room 5"
    assert item["people"][0]["user_id"] == uid and set(item["people"][0]) == {"user_id", "name", "role"}
    assert "PRIVATE NOTE" not in r.text and "zoom.example" not in r.text


def test_it_returns_exactly_what_the_calendar_page_allows(app_mod, viewer, api):
    c, uid = api
    st.cal_create(c, "APITEST open", day_n(1), audience="bureau", by="x@x")
    st.cal_create(c, "APITEST hidden", day_n(1), audience="people", by="x@x")
    st.cal_create(c, "APITEST mine", day_n(1), audience="people", people=[(uid, "attending")], by="x@x")
    titles = {i["title"] for i in viewer.get("/api/calendar?scope=bureau").json()["items"] if i["title"].startswith("APITEST")}
    assert titles == {"APITEST open", "APITEST mine"}
    page = viewer.get("/calendar?scope=bureau").text
    assert "APITEST hidden" not in page and "APITEST mine" in page


def test_scope_and_filters(app_mod, viewer, api):
    c, uid = api
    st.cal_create(c, "APITEST bureau meeting", day_n(1), kind="meeting", audience="bureau", by="x@x")
    st.cal_create(c, "APITEST mine training", day_n(1), kind="training", audience="people", people=[(uid, "attending")], by="x@x")
    mine = {i["title"] for i in viewer.get("/api/calendar?scope=mine").json()["items"] if i["title"].startswith("APITEST")}
    assert mine == {"APITEST mine training"}
    only = viewer.get("/api/calendar?scope=bureau&kind=meeting").json()["items"]
    assert [i["title"] for i in only if i["title"].startswith("APITEST")] == ["APITEST bureau meeting"]


@pytest.mark.parametrize("qs, msg", [("start=nope", "dates"), ("start=2026-10-10&end=2026-10-01", "before"),
                                     ("start=2026-01-01&end=2026-12-31", "at most 92"), ("scope=galaxy", "scope must"),
                                     ("scope=section", "scope must"), ("layers=entries,secrets", "layers must"),
                                     ("kind=nonsense", "unknown kind")])
def test_bad_requests_are_answered_plainly(app_mod, viewer, qs, msg):
    r = viewer.get("/api/calendar?" + qs)
    assert r.status_code == 400 and msg in r.json()["error"]


def test_a_section_scope_is_offered_only_to_people_in_one(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALAPI/D1/S1"):
        assert viewer.get("/api/calendar?scope=section").status_code == 200


def test_leave_has_no_reason_and_birthdays_have_no_year(app_mod, viewer, api):
    c, uid = api
    c.execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)", (uid, day_n(1), "leave", "APITEST reason", "x"))
    other = st.get_admin_user(c, "encoder@test.local")["id"]
    st.set_birthday(c, other, 6, 7, "bureau"); c.commit()
    try:
        r = viewer.get(f"/api/calendar?scope=bureau&layers=leave,birthdays&start={day_n(0)}&end={day_n(30)}")
        assert any(i["kind"] == "leave" for i in r.json()["items"]) and "APITEST reason" not in r.text
        b = viewer.get("/api/calendar?scope=bureau&layers=birthdays&start=2026-06-01&end=2026-06-30").json()["items"]
        assert [i["start"] for i in b if i["kind"] == "birthday"] == ["2026-06-07"] and "19" not in b[0]["start"][:2]
    finally:
        st.clear_birthday(c, other); c.commit()


def test_a_private_birthday_never_appears(app_mod, viewer, api):
    c, uid = api
    other = st.get_admin_user(c, "encoder@test.local")["id"]
    st.set_birthday(c, other, 6, 7, "none")
    try:
        r = viewer.get("/api/calendar?scope=bureau&layers=birthdays&start=2026-06-01&end=2026-06-30")
        assert r.json()["items"] == []
    finally:
        st.clear_birthday(c, other)


def test_a_repeating_item_says_so_per_occurrence(app_mod, viewer, api):
    c, uid = api
    d = tz.today_local() + timedelta(days=1)
    import recurrence as rc
    st.cal_create(c, "APITEST weekly", d.isoformat(), audience="bureau", rrule=rc.build("weekly", d, d + timedelta(days=21)), by="x@x")
    items = [i for i in viewer.get("/api/calendar?scope=bureau&end=" + (d + timedelta(days=30)).isoformat()).json()["items"] if i["title"] == "APITEST weekly"]
    assert len(items) == 4 and all(i["repeats"] for i in items)
