"""Collect feedback (CSS) from a calendar item, and the duplicate guard in both directions
(office calendar D2)."""
from __future__ import annotations
from datetime import timedelta
from urllib.parse import urlencode

import pytest

import office_calendar as ocal
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
DAY = (tz.today_local() + timedelta(days=5)).isoformat()


def new_event(conn, title, day=DAY, **kw):
    fid = st.create_form_instance(conn, 2, "F2", day, topic=title)
    ev = st.create_event(conn, title, day, form_instance_ids=[fid], **kw)
    conn.commit()
    return ev["id"], ev["event_token"], fid


# ------------------------------------------------------------- similarity ---

@pytest.mark.parametrize("a, b, same", [
    ("LIPH IS Orientation", "liph is orientation", True),
    ("LIPH IS Orientation for CHDs", "Orientation for CHDs", True),          # one inside the other
    ("Learning Exchange Session", "Learning Exchange Sesion", True),           # a typo
    ("Section 1 Mtg", "Mtg", False),                                          # too short to be "inside"
    ("Procurement Training", "Budget Hearing", False), ("", "x", False), ("x", "", False),
])
def test_similar_titles(a, b, same):
    assert ocal.similar_titles(a, b) is same


@pytest.mark.parametrize("kind, status, linked, ok", [
    ("meeting", "confirmed", None, True), ("training", "tentative", None, True),
    ("travel", "confirmed", None, False), ("audit_mr", "confirmed", None, False),
    ("banner", "confirmed", None, False), ("deadline", "confirmed", None, False),
    ("meeting", "cancelled", None, False), ("meeting", "confirmed", 5, False),
])
def test_only_a_live_unlinked_meeting_or_training_can_collect_feedback(kind, status, linked, ok):
    assert ocal.entry_can_collect_feedback({"kind": kind, "status": status, "event_id": linked}) is ok


# --------------------------------------------------------------- storage ---

def test_linking_an_entry_to_an_activity(world):                                              # noqa: F811
    c = world["conn"]
    eid, _, _ = new_event(c, "Orientation")
    ent = st.cal_create(c, "Orientation (calendar)", DAY, kind="training", by="mae")
    before = st.cal_get(c, ent)["sequence"]
    st.cal_link_event(c, ent, eid, by="mae")
    got = st.cal_get(c, ent)
    assert got["event_id"] == eid and got["sequence"] == before and got["title"] == "Orientation (calendar)"
    assert st.cal_revisions(c, ent)[0]["diff"] == {"event_id": [None, eid]}
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='calendar_link_activity'").fetchone()[0] == 1


def test_linking_refuses_what_cannot_be_linked(world):                                        # noqa: F811
    c = world["conn"]
    e1, _, _ = new_event(c, "One"); e2, _, _ = new_event(c, "Two")
    a = st.cal_create(c, "A", DAY); b = st.cal_create(c, "B", DAY)
    st.cal_link_event(c, a, e1)
    for args, msg in (((a, e2), "already linked to an activity"), ((b, e1), "already linked to another"),
                      ((999, e2), "no longer exists"), ((b, 999), "activity no longer exists")):
        with pytest.raises(ValueError, match=msg):
            st.cal_link_event(c, *args)
    st.cal_cancel(c, b)
    with pytest.raises(ValueError, match="Restore"):
        st.cal_link_event(c, b, e2)
    assert st.cal_get(c, b)["event_id"] is None


def test_activity_candidates_for_an_entry(world):                                             # noqa: F811
    c = world["conn"]
    ok, _, _ = new_event(c, "LIPH IS Orientation")
    new_event(c, "Budget Hearing")                                                            # dissimilar
    new_event(c, "LIPH IS Orientation", (tz.today_local() + timedelta(days=40)).isoformat())  # other day
    gone, _, _ = new_event(c, "LIPH IS Orientation"); st.set_event_archived(c, gone, True)    # archived
    taken, _, _ = new_event(c, "LIPH IS Orientation")
    st.cal_create(c, "other", DAY, event_id=taken)                                            # already has an overlay
    ent = st.cal_get(c, st.cal_create(c, "liph is orientation", DAY, kind="training"))
    assert [x["id"] for x in ocal.activity_candidates_for_entry(c, ent)] == [ok]


def test_entry_candidates_for_an_activity_respect_what_the_viewer_may_see(world):             # noqa: F811
    c = world["conn"]
    unit = world["unit"]["T/D1/S1"]
    vis = st.cal_create(c, "Learning Exchange Session", DAY, kind="meeting", audience="bureau")
    st.cal_create(c, "Learning Exchange Session", DAY, kind="audit_mr", audience="bureau")    # wrong kind
    st.cal_create(c, "Learning Exchange Session", DAY, kind="training", owner_org_id=unit)     # S1 only
    st.cal_create(c, "Something else", DAY, kind="meeting", audience="bureau")
    mine = ocal.entry_candidates_for_activity(c, world["s1"], "Learning Exchange Session", DAY)
    assert sorted(x["id"] for x in mine) == sorted([vis, c.execute(
        "SELECT id FROM calendar_entry WHERE kind='training' AND owner_org_id=?", (unit,)).fetchone()[0]])
    other = ocal.entry_candidates_for_activity(c, world["s3"], "Learning Exchange Session", DAY)
    assert [x["id"] for x in other] == [vis]                                                  # s3 can't see S1's own
    assert ocal.entry_candidates_for_activity(c, world["s1"], "Learning Exchange Session",
                                              (tz.today_local() + timedelta(days=30)).isoformat()) == []


# ------------------------------------------------------------------ pages ---

@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    ids = [r[0] for r in c.execute("SELECT id FROM event WHERE title LIKE 'CALLK %'")]
    for i in ids:
        c.execute("DELETE FROM calendar_entry_person WHERE entry_id IN (SELECT id FROM calendar_entry WHERE event_id=?)", (i,))
        c.execute("UPDATE calendar_entry SET event_id=NULL WHERE event_id=?", (i,))
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALLK %'").fetchall():
        st.cal_delete(c, i)
    c.execute("DELETE FROM attendee WHERE event_id IN (SELECT id FROM event WHERE title LIKE 'CALLK %')")
    fids = [r[0] for r in c.execute("SELECT form_instance_id FROM event_form WHERE event_id IN (SELECT id FROM event WHERE title LIKE 'CALLK %')")]
    c.execute("DELETE FROM event_form WHERE event_id IN (SELECT id FROM event WHERE title LIKE 'CALLK %')")
    c.execute("DELETE FROM event WHERE title LIKE 'CALLK %'")
    for f in fids:
        c.execute("DELETE FROM form_instance WHERE id=?", (f,))
    c.execute("DELETE FROM external_organizer WHERE name LIKE 'CALLK %'")
    c.execute("DELETE FROM resource_person WHERE name LIKE 'CALLK %' AND id NOT IN (SELECT rp_id FROM form_instance WHERE rp_id IS NOT NULL)")
    c.commit(); c.close()


def entry(c, title="CALLK Orientation", **kw):
    kw.setdefault("kind", "training"); kw.setdefault("audience", "bureau")
    return st.cal_create(c, title, DAY, **kw)


def create_form(**over):
    d = {"event_type": "bureau", "activity_name": "CALLK Orientation", "event_date": DAY, "qr_mode": "combined",
         "modality": "f2f", **over}
    return urlencode(d)


def test_the_button_is_for_people_who_can_create_activities(app_mod, manager, viewer, conn):
    eid = entry(conn)
    page = manager.get(f"/calendar/entries/{eid}").text
    assert "Collect feedback (CSS)" in page and f"/create?from_entry={eid}" in page
    assert "Collect feedback (CSS)" not in viewer.get(f"/calendar/entries/{eid}").text
    for kind in ("audit_mr", "travel", "banner"):
        assert "Collect feedback (CSS)" not in manager.get(f"/calendar/entries/{entry(conn, 'CALLK x', kind=kind)}").text


def test_the_create_form_starts_from_the_item(app_mod, admin, conn):
    sec = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('CALLK Section','CALLK','section','CALLK/S')").lastrowid
    rp = conn.execute("INSERT INTO resource_person(name, is_internal) VALUES ('CALLK Lead', 1)").lastrowid
    uid = st.create_admin_user(conn, "callk-lead@test.local", "x", "y", "viewer", rp_id=rp)
    other = st.create_admin_user(conn, "callk-other@test.local", "x", "y", "viewer",
                                 rp_id=conn.execute("INSERT INTO resource_person(name, is_internal) VALUES ('CALLK Other', 1)").lastrowid)
    eid = entry(conn, end_date=(tz.today_local() + timedelta(days=7)).isoformat(), venue="Room 5", modality="hybrid",
                owner_org_id=sec, people=[(uid, "lead"), (other, "attending")])
    conn.commit()
    try:
        html = admin.get(f"/create?from_entry={eid}").text
        assert 'value="CALLK Orientation"' in html and f'value="{DAY}"' in html and 'value="Room 5"' in html
        assert f'name="from_entry" id="from_entry" value="{eid}"' in html
        assert 'value="hybrid" checked' in html and 'value="f2f" checked' not in html
        assert f'<option value="{sec}" selected>' in html
        assert f'[["{rp}", "CALLK Orientation"]]' in html.replace("'", '"')                  # the lead only, not the attendee
        assert 'class="dup-warn " id="calLinked"' in html                                   # banner is showing
    finally:
        conn.execute("DELETE FROM calendar_entry_person WHERE entry_id=?", (eid,)); conn.commit()
        for u in (uid, other):
            conn.execute("DELETE FROM admin_user WHERE id=?", (u,))
        conn.execute("DELETE FROM resource_person WHERE name LIKE 'CALLK %'")
        conn.execute("UPDATE calendar_entry SET owner_org_id=NULL WHERE id=?", (eid,))
        conn.execute("DELETE FROM org_unit WHERE id=?", (sec,)); conn.commit()


def test_the_create_form_ignores_items_it_may_not_turn_into_activities(app_mod, admin, conn):
    cancelled = entry(conn, "CALLK Gone"); st.cal_cancel(conn, cancelled)
    audit = entry(conn, "CALLK Audit", kind="audit_mr")
    linked_ev, _, _ = new_event(conn, "CALLK Linked event")
    linked = entry(conn, "CALLK Linked"); st.cal_link_event(conn, linked, linked_ev)
    private = entry(conn, "CALLK Private", audience="people", people=[], by="someone-else@test.local")
    for bad in (cancelled, audit, linked, private, 99999, "abc", ""):
        html = admin.get(f"/create?from_entry={bad}").text
        assert 'id="from_entry" value=""' in html and 'class="dup-warn hidden" id="calLinked"' in html     # banner stays hidden
        assert "CALLK" not in html.split('id="activity_name"')[1][:200]                  # nothing prefilled


def test_creating_the_activity_links_the_item_and_shows_it_once(app_mod, admin, conn):
    eid = entry(conn, people=[])
    r = admin.post("/create", content=create_form(from_entry=str(eid), from_entry_title="CALLK Orientation"), headers=FORM)
    assert r.status_code == 200 and "Linked to the calendar item" in r.text and "CALLK Orientation" in r.text
    got = st.cal_get(conn, eid)
    ev = conn.execute("SELECT id, event_token FROM event WHERE title='CALLK Orientation'").fetchone()
    assert got["event_id"] == ev[0] and got["title"] == "CALLK Orientation"
    agenda = admin.get(f"/calendar?scope=bureau&day={DAY}").text
    assert agenda.count("CALLK Orientation") == 1 and f'href="/monitor/{ev[1]}"' in agenda    # one card: the activity
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='calendar_link_activity'").fetchone()[0] >= 1


def test_an_outside_activity_can_be_linked_too(app_mod, admin, conn):
    rp = conn.execute("INSERT INTO resource_person(name, is_internal) VALUES ('CALLK Guest', 0)").lastrowid
    eid = entry(conn, "CALLK Invited talk", kind="meeting"); conn.commit()
    r = admin.post("/create", content=urlencode({
        "event_type": "outside", "activity_name": "CALLK Invited talk", "event_date": DAY, "qr_mode": "separate",
        "external_org": "CALLK Agency", "rp_id": str(rp), "topic": "A topic", "from_entry": str(eid)}), headers=FORM)
    assert r.status_code == 200 and st.cal_get(conn, eid)["event_id"]


def test_a_failed_link_never_undoes_the_activity(app_mod, admin, conn):
    eid = entry(conn, "CALLK Audit thing", kind="audit_mr")
    r = admin.post("/create", content=create_form(activity_name="CALLK Audit thing", from_entry=str(eid)), headers=FORM)
    assert r.status_code == 200 and "Linked to the calendar item" not in r.text
    assert conn.execute("SELECT COUNT(*) FROM event WHERE title='CALLK Audit thing'").fetchone()[0] == 1
    assert st.cal_get(conn, eid)["event_id"] is None


def test_a_validation_error_keeps_the_link(app_mod, admin, conn):
    eid = entry(conn)
    r = admin.post("/create", content=create_form(activity_name="", from_entry=str(eid), from_entry_title="CALLK Orientation"),
                   headers=FORM)
    assert r.status_code == 400 and f'name="from_entry" id="from_entry" value="{eid}"' in r.text


def test_the_item_page_offers_an_activity_that_already_exists_and_links_it(app_mod, manager, viewer, conn):
    ev, token, _ = new_event(conn, "CALLK Orientation")
    eid = entry(conn)
    page = manager.get(f"/calendar/entries/{eid}").text
    assert "This may already be an activity" in page and f'value="{ev}"' in page and "Link to this activity" in page
    assert viewer.post(f"/calendar/entries/{eid}/link-activity", content=urlencode({"event_id": ev}), headers=FORM).status_code == 403
    r = manager.post(f"/calendar/entries/{eid}/link-activity", content=urlencode({"event_id": ev}), headers=FORM, follow_redirects=False)
    assert r.status_code == 303 and st.cal_get(conn, eid)["event_id"] == ev
    after = manager.get(f"/calendar/entries/{eid}").text
    assert "linked to the CSS activity" in after and "Collect feedback (CSS)" not in after and "may already be" not in after
    again = manager.post(f"/calendar/entries/{eid}/link-activity", content=urlencode({"event_id": ev}), headers=FORM, follow_redirects=True)
    assert "already linked" in again.text


def test_link_activity_validates_its_input(app_mod, manager, conn):
    eid = entry(conn)
    for body, msg in (({"event_id": ""}, "Choose the activity"), ({"event_id": "99999"}, "no longer exists")):
        r = manager.post(f"/calendar/entries/{eid}/link-activity", content=urlencode(body), headers=FORM, follow_redirects=True)
        assert msg in r.text
    hidden = entry(conn, "CALLK Hidden", audience="people", people=[], by="someone-else@test.local")
    r = manager.post(f"/calendar/entries/{hidden}/link-activity", content=urlencode({"event_id": "1"}), headers=FORM)
    assert r.status_code == 404


def test_the_create_screen_warns_about_a_matching_calendar_item(app_mod, manager, viewer, conn):
    eid = entry(conn, "CALLK Learning Exchange", kind="meeting")
    hidden = entry(conn, "CALLK Learning Exchange (private)", kind="meeting", audience="people", people=[], by="someone-else@test.local")
    audit = entry(conn, "CALLK Learning Exchange (audit)", kind="audit_mr")
    r = manager.get("/create/check-calendar", params={"activity_name": "CALLK Learning Exchange", "event_date": DAY})
    got = r.json()["entries"]
    assert [x["id"] for x in got] == [eid] and got[0]["url"] == f"/calendar/entries/{eid}"
    assert hidden not in [x["id"] for x in got] and audit not in [x["id"] for x in got]
    assert manager.get("/create/check-calendar", params={"activity_name": "CALLK Learning Exchange", "event_date": "nope"}).json() == {"entries": []}
    assert manager.get("/create/check-calendar", params={"activity_name": "Unrelated", "event_date": DAY}).json() == {"entries": []}
    html = manager.get("/create").text
    assert 'id="calWarn"' in html and "checkCalendar" in html and "textContent" in html


def test_titles_are_escaped_on_the_create_form_and_the_item_page(app_mod, admin, conn):
    eid = entry(conn, "CALLK <script>alert(1)</script>")
    for html in (admin.get(f"/create?from_entry={eid}").text, admin.get(f"/calendar/entries/{eid}").text):
        assert "<script>alert(1)</script>" not in html
