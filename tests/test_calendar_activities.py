"""CSS activities on the calendar (office calendar D1): every non-archived activity shows up with
no copying, an optional overlay adds people / tags / audience, and the card says where the
activity is in its life."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import office_calendar as ocal
import office_connect as oc
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

NOW = tz.today_local()


def d(n):
    return (NOW + timedelta(days=n)).isoformat()


def make(w, title, start, *, end=None, owner="T/D1/S1", kind="bureau", speakers=(), forms=True, by=None,
         venue="Hall 1", modality="f2f", close_at=None):
    """An activity the way /create makes one: an F2 review + an F3 per speaker, grouped in an event."""
    conn = w["conn"]
    fids = []
    if forms and kind == "bureau":
        fids.append(st.create_form_instance(conn, 2, "F2", start, end_date=end, topic=title, venue=venue,
                                            lead_org_id=w["unit"].get(owner), modality=modality))
        if close_at:
            conn.execute("UPDATE form_instance SET close_at=? WHERE id=?", (close_at, fids[0]))
    for rp in speakers:
        fids.append(st.create_form_instance(conn, 3, "F3", start, end_date=end, topic=title, rp_id=rp,
                                            lead_org_id=w["unit"].get(owner)))
    ev = st.create_event(conn, title, start, end_date=end, venue=venue, modality=modality,
                         lead_org_id=w["unit"].get(owner), form_instance_ids=fids, created_by=by,
                         event_kind=kind)
    conn.commit()
    return ev["id"], ev["event_token"], fids


def items(w, who, a=-3, b=10, scope="bureau", **kw):
    return [i for i in ocal.items_between(w["conn"], w[who], NOW + timedelta(days=a), NOW + timedelta(days=b),
                                          scope=scope, **kw) if i["layer"] == "activities"]


def titles(w, who, **kw):
    return sorted(i["title"] for i in items(w, who, **kw))


# ------------------------------------------------------------------ basics ---

def test_an_activity_is_on_the_calendar_with_no_copy_and_no_backfill(world):                 # noqa: F811
    eid, token, _ = make(world, "LIPH IS Orientation", d(2), end=d(4), venue="Room 5", modality="online")
    (it,) = items(world, "s1")
    assert (it["key"], it["layer"], it["kind"], it["title"]) == (f"event:{eid}", "activities", "activity", "LIPH IS Orientation")
    assert (it["start"], it["end"], it["all_day"], it["venue"], it["modality"]) == (d(2), d(4), True, "Room 5", "online")
    assert it["owner_label"] == "S1" and it["editable"] is False and it["people"] == [] and it["tags"] == []
    assert it["url"] == f"/e/{token}" and it["css"]["event_id"] == eid and it["css"]["event_kind"] == "bureau"
    assert world["conn"].execute("SELECT COUNT(*) FROM calendar_entry").fetchone()[0] == 0     # nothing was written


def test_staff_who_manage_activities_land_on_the_monitor_page(world):                             # noqa: F811
    _, token, _ = make(world, "Managed", d(1))
    boss = {**world["s1"], "role": "admin"}
    (it,) = [i for i in ocal.items_between(world["conn"], boss, NOW, NOW + timedelta(days=3), scope="bureau")
             if i["layer"] == "activities"]
    assert it["url"] == f"/monitor/{token}"


def test_the_window_picks_activities_that_overlap_it(world):                                      # noqa: F811
    make(world, "Before", d(-20)); make(world, "Under way", d(-2), end=d(1)); make(world, "Inside", d(5))
    make(world, "After", d(30))
    assert titles(world, "s1", a=0, b=7) == ["Inside", "Under way"]
    st.cal_create(world["conn"], "x", d(0))                                                       # entries don't leak in
    assert "x" not in titles(world, "s1", a=0, b=7)


def test_an_event_without_a_date_is_never_drawn(world):                                          # noqa: F811
    world["conn"].execute("INSERT INTO event(event_token, title, event_date) VALUES ('nodate', 'No date', '')")
    world["conn"].commit()
    assert "No date" not in titles(world, "s1", a=-400, b=400)


def test_archived_activities_are_hidden_and_come_back_when_restored(world):                       # noqa: F811
    eid, _, _ = make(world, "Put away", d(1))
    st.set_event_archived(world["conn"], eid, True)
    assert titles(world, "s1") == []
    st.set_event_archived(world["conn"], eid, False)
    assert titles(world, "s1") == ["Put away"]
    make(world, "Formless", d(1), forms=False)                      # no forms at all is not "archived"
    assert "Formless" in titles(world, "s1")


def test_invited_outside_activities_are_included(world):                                         # noqa: F811
    rp = world["conn"].execute("INSERT INTO resource_person(name, is_internal) VALUES ('Dr Guest', 0)").lastrowid
    make(world, "Invited talk", d(2), kind="outside", speakers=[rp], owner=None)
    (it,) = items(world, "s1")
    assert it["title"] == "Invited talk" and it["css"]["event_kind"] == "outside" and it["owner_label"] is None


# ------------------------------------------------------------------ chips ---

def test_chip_by_lifecycle(world):                                                                # noqa: F811
    up, _, _ = make(world, "Upcoming", d(3))
    st.register_attendee(world["conn"], up, name="Ana", email="a@x.org", consent_text="ok")
    st.register_attendee(world["conn"], up, name="Ben", email="b@x.org", consent_text="ok")
    make(world, "Open now", d(0), end=d(1), close_at=(NOW + timedelta(days=2)).isoformat() + "T23:59:00")
    make(world, "Over", d(-2), close_at=(NOW - timedelta(days=1)).isoformat() + "T00:00:00")
    by = {i["title"]: i["css"] for i in items(world, "s1")}
    assert (by["Upcoming"]["lifecycle"], by["Upcoming"]["chip"], by["Upcoming"]["registered"]) == (
        "upcoming", "2 registered", 2)
    assert (by["Open now"]["lifecycle"], by["Open now"]["chip"]) == ("ongoing", "feedback open · 0 answered")
    assert (by["Over"]["lifecycle"], by["Over"]["chip"]) == ("concluded", "concluded · 0 responses")


# ------------------------------------------------------------------ overlay ---

def test_an_overlay_adds_people_tags_and_kind_but_is_never_a_second_card(world):                  # noqa: F811
    eid, _, _ = make(world, "Linked activity", d(2))
    ov = st.cal_create(world["conn"], "Different title", d(9), event_id=eid, kind="training", audience="bureau",
                       owner_org_id=world["unit"]["T/D2/S3"], tags=["PK", "BHW"],
                       people=[(world["s1"]["id"], "attending"), (world["s3"]["id"], "lead")])
    both = [i for i in ocal.items_between(world["conn"], world["s1"], NOW, NOW + timedelta(days=12), scope="bureau")
            if "Linked" in i["title"] or "Different" in i["title"]]
    assert len(both) == 1                                            # the overlay is NOT drawn as an entry too
    (it,) = both
    assert it["title"] == "Linked activity" and it["start"] == d(2)  # the event owns title and dates
    assert it["tags"] == ["BHW", "PK"] and it["owner_label"] == "S3"
    assert {(p["user_id"], p["role"]) for p in it["people"]} == {(world["s1"]["id"], "attending"),
                                                                 (world["s3"]["id"], "lead")}
    assert ov


def test_an_overlay_can_narrow_who_sees_the_activity(world):                                      # noqa: F811
    eid, _, _ = make(world, "Closed activity", d(2))
    st.cal_create(world["conn"], "o", d(2), event_id=eid, audience="people", people=[world["s1"]["id"]])
    assert titles(world, "s1") == ["Closed activity"]
    for who in ("s1b", "s3", "dir", "nobody"):
        assert titles(world, who) == [], who


# ------------------------------------------------------------------ people ---

def test_internal_speakers_with_accounts_are_the_people_on_the_activity(world):                  # noqa: F811
    rp = world["conn"].execute("SELECT rp_id FROM admin_user WHERE id=?", (world["s3"]["id"],)).fetchone()[0]
    make(world, "Talk by s3", d(2), speakers=[rp])
    (it,) = items(world, "s1")
    assert [(p["user_id"], p["role"]) for p in it["people"]] == [(world["s3"]["id"], "lead")]
    assert it["people"][0]["name"] == "P s3"


# ------------------------------------------------------------------- scope ---

def test_scopes_follow_the_organising_unit_the_creator_and_the_speakers(world):                  # noqa: F811
    rp3 = world["conn"].execute("SELECT rp_id FROM admin_user WHERE id=?", (world["s3"]["id"],)).fetchone()[0]
    make(world, "S1 organised", d(1), owner="T/D1/S1")
    make(world, "S3 organised", d(1), owner="T/D2/S3")
    make(world, "S1 organised, s3 speaks", d(2), owner="T/D1/S1", speakers=[rp3])
    make(world, "Made by s1b", d(3), owner="T/D2/S3", by=world["s1b"]["username"])
    assert titles(world, "s1", scope="section") == ["S1 organised", "S1 organised, s3 speaks"]
    assert titles(world, "s3", scope="section") == ["Made by s1b", "S3 organised"]
    assert titles(world, "s1", scope="bureau") == sorted(["S1 organised", "S3 organised", "S1 organised, s3 speaks",
                                                          "Made by s1b"])
    assert titles(world, "s3", scope="mine") == ["S1 organised, s3 speaks"]                       # speaks at it
    assert titles(world, "s1b", scope="mine") == ["Made by s1b"]                                  # created it
    assert titles(world, "s1", scope="mine") == [] and titles(world, "s1", scope="blend") == []
    assert titles(world, "s1", scope="division") == ["S1 organised", "S1 organised, s3 speaks"]
    assert titles(world, "nobody", scope="bureau") == sorted(["S1 organised", "S3 organised",
                                                              "S1 organised, s3 speaks", "Made by s1b"])


# ------------------------------------------------------------ other layers ---

def test_layers_and_filters_know_about_activities(world):                                         # noqa: F811
    eid, _, _ = make(world, "Act", d(1))
    st.cal_create(world["conn"], "Tagged overlay", d(1), event_id=eid, tags=["ZBB"])
    st.cal_create(world["conn"], "Plain meeting", d(1), audience="bureau")
    every = ocal.items_between(world["conn"], world["s1"], NOW, NOW + timedelta(days=3), scope="bureau")
    assert {i["layer"] for i in every} >= {"activities", "entries"}
    only = ocal.items_between(world["conn"], world["s1"], NOW, NOW + timedelta(days=3), scope="bureau",
                              layers=["activities"])
    assert [i["title"] for i in only] == ["Act"]
    kept = ocal.apply_filters(every, {"kinds": {"activity"}})
    assert [i["title"] for i in kept if i["layer"] != "holidays"] == ["Act"]
    kept = ocal.apply_filters(every, {"tags": {"ZBB"}})
    assert [i["title"] for i in kept if i["layer"] != "holidays"] == ["Act"]


def test_the_week_view_puts_an_activity_on_its_speakers_row(world):                              # noqa: F811
    rp1 = world["conn"].execute("SELECT rp_id FROM admin_user WHERE id=?", (world["s1"]["id"],)).fetchone()[0]
    world["conn"].execute("UPDATE resource_person SET is_internal=1"); world["conn"].commit()
    monday = ocal.monday_of(NOW + timedelta(days=7))
    day = monday + timedelta(days=1)
    make(world, "Speaker session", day.isoformat(), speakers=[rp1])
    its = ocal.items_between(world["conn"], world["s1"], monday, monday + timedelta(days=4), scope="bureau")
    g = ocal.people_week(world["conn"], world["s1"], monday, its)
    row = {p["name"]: p for sec in g["sections"] for p in sec["people"]}["P s1"]
    assert [b["item"]["title"] for b in row["bars"]] == ["Speaker session"] and not g["has_band"]


def test_the_home_card_and_todays_task_include_activities(world):                                # noqa: F811
    eid, _, _ = make(world, "Today's activity", d(0), by=world["s1"]["username"])
    block = oc.calendar_week_block(world["conn"], world["s1"], view="me", today=NOW)
    (row,) = block["items"]
    assert row["title"] == "Today's activity" and row["chip"] and row["life"] == "ongoing"
    t = oc._task_calendar_today(world["conn"], world["s1"], NOW)
    assert t["title"] == "1 thing on the calendar today"


# ------------------------------------------------------------------- pages ---

def test_the_agenda_shows_the_activity_with_its_chip_and_the_kind_filter_names_it(app_mod, viewer):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    fid = st.create_form_instance(conn, 2, "F2", d(1), topic="CALAC Agenda activity", venue="Hall")
    ev = st.create_event(conn, "CALAC Agenda activity", d(1), venue="Hall", form_instance_ids=[fid])
    conn.commit()
    try:
        html = viewer.get(f"/calendar?scope=bureau&day={d(0)}").text
        assert "CALAC Agenda activity" in html and 'class="cal-css-chip"' in html and "registered" in html
        assert f'href="/e/{ev["event_token"]}"' in html and 'data-kind="activity"' in html
        assert 'value="activity"' in html and "CSS activity" in html
        only = viewer.get(f"/calendar?scope=bureau&day={d(0)}&kind=activity").text
        assert "CALAC Agenda activity" in only
        other = viewer.get(f"/calendar?scope=bureau&day={d(0)}&kind=meeting").text
        assert "CALAC Agenda activity" not in other
        month = viewer.get(f"/calendar?scope=bureau&view=month&month={d(1)[:7]}").text
        assert "CALAC Agenda activity" in month
    finally:
        conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
        conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
        conn.execute("DELETE FROM form_instance WHERE id=?", (fid,))
        conn.commit(); conn.close()


def test_a_person_still_cannot_post_the_activity_kind_in_the_form(viewer):
    r = viewer.post("/calendar/new", content="title=x&kind=activity&status=confirmed&start_date=2026-10-12&audience=bureau",
                    headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 400 and "Pick a type" in r.text
