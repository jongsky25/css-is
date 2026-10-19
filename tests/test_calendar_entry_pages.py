"""Office calendar add / view / edit / cancel / restore pages (increment A4)."""
from __future__ import annotations
from urllib.parse import urlencode

import pytest

import storage as st
from conftest import in_the_directory

DAY = "2026-10-12"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALEP %'").fetchall():
        st.cal_delete(c, i)
    c.commit()
    c.close()


def uid(conn, username):
    return st.get_admin_user(conn, username)["id"]


def post(client, url, **fields):
    data = {"title": "CALEP Thing", "kind": "meeting", "status": "confirmed",
            "start_date": DAY, "audience": "bureau", **fields}
    pairs = []
    for k, v in data.items():
        for x in (v if isinstance(v, list) else [v]):
            pairs.append((k, x))
    return client.post(url, content=urlencode(pairs), headers=FORM, follow_redirects=False)


def create(client, **fields):
    r = post(client, "/calendar/new", **fields)
    assert r.status_code == 303, r.text
    return int(r.headers["location"].split("/calendar/entries/")[1].split("?")[0])


# ------------------------------------------------------------------ access ---

@pytest.mark.parametrize("path", ["/calendar/new", "/calendar/entries/1",
                                  "/calendar/entries/1/edit"])
def test_pages_require_login(client, path):
    assert client.get(path, follow_redirects=False).status_code in (302, 303, 401)


@pytest.mark.parametrize("url", ["/calendar/new", "/calendar/entries/1/edit",
                                 "/calendar/entries/1/cancel", "/calendar/entries/1/restore"])
def test_writes_require_login(client, url):
    r = client.post(url, content="title=x", headers=FORM, follow_redirects=False)
    assert r.status_code in (302, 303, 401)


@pytest.mark.parametrize("who", ["viewer", "encoder", "manager", "admin"])
def test_every_role_can_open_the_add_form(request, who):
    r = request.getfixturevalue(who).get(f"/calendar/new?day={DAY}")
    assert r.status_code == 200 and "Add to the calendar" in r.text and DAY in r.text


# ------------------------------------------------------------------ create ---

def test_create_stores_everything_and_audits(viewer, conn):
    other = uid(conn, "encoder@test.local")
    mark = conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_log").fetchone()[0]   # rowids get reused
    eid = create(viewer, title="CALEP Trip", kind="travel", end_date="2026-10-14",
                 start_time="09:00", end_time="17:00", venue="Palawan", modality="f2f",
                 meeting_url="https://zoom.us/j/1", note="Bring ID", tags="PK, BHW, pk",
                 people=[str(other)])
    e = st.cal_get(conn, eid)
    assert (e["title"], e["kind"], e["end_date"], e["venue"]) == (
        "CALEP Trip", "travel", "2026-10-14", "Palawan")
    assert (e["start_time"], e["modality"], e["note"]) == ("09:00", "f2f", "Bring ID")
    assert e["tags"] == ["BHW", "PK"] and e["created_by"] == "viewer@test.local"
    assert [(p["user_id"], p["role"]) for p in e["people"]] == [(other, "travel")]
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='calendar_create' "
                        "AND target_id=? AND id>?", (str(eid), mark)).fetchone()[0] == 1
    page = viewer.get(f"/calendar/entries/{eid}").text
    assert "CALEP Trip" in page and "Palawan" in page and "BHW" in page and "viewer@test.local" in page


def test_the_agenda_links_to_the_item_and_offers_add(viewer, conn):
    eid = create(viewer, title="CALEP Linked")
    html = viewer.get(f"/calendar?day={DAY}").text
    assert f'href="/calendar/entries/{eid}"' in html and "/calendar/new?day=" in html


@pytest.mark.parametrize("fields, message", [
    ({"title": "  "}, "title is required"),
    ({"end_date": "2026-10-01"}, "end_date cannot be before"),
    ({"meeting_url": "javascript:alert(1)"}, "http://"),
    ({"start_time": "25:99"}, "HH:MM"),
    ({"kind": "activity"}, "Pick a type"),
    ({"status": "cancelled"}, "Pick a status"),
    ({"audience": "people"}, "Choose who this is for"),
    ({"audience": "unit"}, "Choose the unit"),
    ({"people": ["999999"]}, "active account"),
])
def test_validation_errors_redisplay_the_form_with_a_message(viewer, conn, fields, message):
    r = post(viewer, "/calendar/new", **{"title": "CALEP Bad", **fields})
    assert r.status_code == 400 and message in r.text
    assert conn.execute("SELECT COUNT(*) FROM calendar_entry WHERE title LIKE 'CALEP %'"
                        ).fetchone()[0] == 0
    if "title" not in fields:
        assert "CALEP Bad" in r.text                           # what you typed is kept


def test_titles_and_notes_are_escaped_everywhere(viewer, conn):
    eid = create(viewer, title="CALEP <script>x()</script>", note="<img src=x onerror=y()>")
    for url in (f"/calendar/entries/{eid}", f"/calendar/entries/{eid}/edit", f"/calendar?day={DAY}"):
        html = viewer.get(url).text
        assert "<script>x()</script>" not in html and "<img src=x" not in html, url


# -------------------------------------------------------------------- edit ---

def test_edit_changes_fields_bumps_sequence_and_keeps_a_lead(admin, viewer, conn):
    lead = uid(conn, "encoder@test.local")
    eid = create(admin, title="CALEP Plan")
    st.cal_update(conn, eid, people=[(lead, "lead")])
    form = viewer.get(f"/calendar/entries/{eid}/edit")
    assert form.status_code == 200 and "CALEP Plan" in form.text
    stamp = st.cal_get(conn, eid)["updated_at"]
    r = post(viewer, f"/calendar/entries/{eid}/edit", title="CALEP Plan v2",
             start_date="2026-10-13", venue="Room 2", updated_at=stamp, people=[str(lead)])
    assert r.status_code == 303
    e = st.cal_get(conn, eid)
    assert (e["title"], e["start_date"], e["venue"], e["sequence"]) == (
        "CALEP Plan v2", "2026-10-13", "Room 2", 1)
    assert e["updated_by"] == "viewer@test.local" and e["created_by"] == "admin@test.local"
    assert [p["role"] for p in e["people"]] == ["lead"]
    page = viewer.get(f"/calendar/entries/{eid}").text
    assert "changed title, start date and venue" in page and "viewer@test.local" in page


def test_a_simultaneous_edit_is_shown_not_overwritten(admin, viewer, conn):
    eid = create(admin, title="CALEP Race", venue="Room 1")
    loaded = st.cal_get(conn, eid)["updated_at"]
    st.cal_update(conn, eid, venue="Room 7", by="admin@test.local")
    conn.execute("UPDATE calendar_entry SET updated_at='2099-01-01T00:00:00' WHERE id=?", (eid,))
    conn.commit()
    r = post(viewer, f"/calendar/entries/{eid}/edit", title="CALEP Race", venue="My room",
             updated_at=loaded)
    assert r.status_code == 409
    assert "changed this item while you were editing" in r.text and "changed venue" in r.text
    assert "My room" in r.text                                   # your text is kept in the form
    assert st.cal_get(conn, eid)["venue"] == "Room 7"            # and nothing was overwritten
    r = post(viewer, f"/calendar/entries/{eid}/edit", title="CALEP Race", venue="My room",
             updated_at="2099-01-01T00:00:00")
    assert r.status_code == 303 and st.cal_get(conn, eid)["venue"] == "My room"


# --------------------------------------------------------- cancel / restore ---

def test_cancel_then_restore_round_trip(viewer, conn):
    eid = create(viewer, title="CALEP Round", status="tentative")
    assert viewer.post(f"/calendar/entries/{eid}/cancel", follow_redirects=False).status_code == 303
    assert st.cal_get(conn, eid)["status"] == "cancelled"
    assert "CALEP Round" not in viewer.get(f"/calendar?day={DAY}").text      # gone from the agenda
    detail = viewer.get(f"/calendar/entries/{eid}").text
    assert "Restore" in detail and "Cancelled" in detail
    gate = viewer.get(f"/calendar/entries/{eid}/edit", follow_redirects=False)
    assert gate.status_code == 303 and "Restore" in gate.headers["location"]
    assert viewer.post(f"/calendar/entries/{eid}/restore", follow_redirects=False).status_code == 303
    assert st.cal_get(conn, eid)["status"] == "tentative"
    acts = [r[0] for r in conn.execute(
        "SELECT action FROM calendar_entry_revision WHERE entry_id=? ORDER BY id", (eid,))]
    assert acts == ["create", "cancel", "restore"]


def test_restore_after_thirty_days_is_refused_politely(viewer, conn):
    eid = create(viewer, title="CALEP Old")
    st.cal_cancel(conn, eid)
    conn.execute("UPDATE calendar_entry SET cancelled_at='2020-01-01T00:00:00' WHERE id=?", (eid,))
    conn.commit()
    r = viewer.post(f"/calendar/entries/{eid}/restore", follow_redirects=True)
    assert r.status_code == 200 and "30 days" in r.text
    assert st.cal_get(conn, eid)["status"] == "cancelled"


# --------------------------------------------------------------- visibility ---

def test_an_entry_you_may_not_see_is_a_404_for_every_action(app_mod, viewer, conn):
    with in_the_directory(app_mod, "viewer@test.local", path="CALEP/D1/S1"):
        other = conn.execute("INSERT INTO org_unit(name, short_name, level, path) "
                             "VALUES ('o','o','section','CALEP/D9/S9')").lastrowid
        hidden = st.cal_create(conn, "CALEP Hidden", DAY, owner_org_id=other, audience="unit")
        private = st.cal_create(conn, "CALEP Private", DAY, audience="people",
                                people=[uid(conn, "admin@test.local")])
        conn.commit()
        for eid in (hidden, private):
            assert viewer.get(f"/calendar/entries/{eid}").status_code == 404
            assert viewer.get(f"/calendar/entries/{eid}/edit").status_code == 404
            for action in ("edit", "cancel", "restore"):
                r = viewer.post(f"/calendar/entries/{eid}/{action}", content="title=x",
                                headers=FORM, follow_redirects=False)
                assert r.status_code == 404, (eid, action)
            assert st.cal_get(conn, eid)["status"] == "confirmed"
        assert "CALEP Hidden" not in viewer.get("/calendar/entries/%d" % hidden).text
        conn.execute("DELETE FROM calendar_entry_revision WHERE entry_id IN "
                     "(SELECT id FROM calendar_entry WHERE title LIKE 'CALEP %')")
        conn.execute("DELETE FROM calendar_entry WHERE title LIKE 'CALEP %'")
        conn.execute("DELETE FROM org_unit WHERE path='CALEP/D9/S9'")
        conn.commit()


def test_a_missing_entry_is_a_404(viewer):
    assert viewer.get("/calendar/entries/987654").status_code == 404


def test_add_form_is_sectioned_and_keeps_every_field(admin):
    html = admin.get(f"/calendar/new?day={DAY}").text
    for name in ("title", "kind", "status", "start_date", "end_date", "start_time", "end_time", "time_note",
                 "repeat", "until", "venue", "modality", "meeting_url", "owner_org_id", "audience", "people",
                 "tags", "note"):
        assert f'name="{name}"' in html, name
    assert "cf-sectioned" in html and "cf-save" in html and "cf-cancel" in html


def test_add_form_loads_the_room_card_styles(admin):
    html = admin.get(f"/calendar/new?day={DAY}").text
    assert 'id="room-chip"' in html and "/static/css/rooms.css" in html     # the card is styled even with no room banner


def test_an_item_can_involve_several_sections(viewer, conn):
    """Spot Feedback #129: the owning unit stays the main one; ticked units are added to it."""
    ids = [conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                        (n, n, "section", f"CALEP/{n}")).lastrowid for n in ("CALEPA", "CALEPB", "CALEPC")]
    conn.commit()
    try:
        eid = create(viewer, title="CALEP Joint", audience="unit", owner_org_id=str(ids[0]),
                     extra_org_ids=[str(ids[1]), str(ids[2])])
        e = st.cal_get(conn, eid)
        assert e["owner_org_id"] == ids[0] and e["extra_org_ids"] == [ids[1], ids[2]]
        page = viewer.get(f"/calendar/entries/{eid}").text
        assert all(n in page for n in ("CALEPA", "CALEPB", "CALEPC"))
        edit = viewer.get(f"/calendar/entries/{eid}/edit").text
        assert f'name="extra_org_ids" value="{ids[1]}" checked' in edit
        assert f'name="extra_org_ids" value="{ids[0]}" checked' not in edit
        r = post(viewer, f"/calendar/entries/{eid}/edit", title="CALEP Joint", audience="unit",
                 owner_org_id=str(ids[0]), extra_org_ids=[str(ids[2])],
                 updated_at=e["updated_at"])
        assert r.status_code == 303, r.text
        assert st.cal_get(conn, eid)["extra_org_ids"] == [ids[2]]
        r = post(viewer, "/calendar/new", title="CALEP Bad", audience="unit",
                 owner_org_id=str(ids[0]), extra_org_ids=["99999999"])
        assert r.status_code == 400 and "isn&#39;t in the directory" in r.text.replace("&#x27;", "&#39;")
    finally:
        for (i,) in conn.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALEP %'").fetchall():
            st.cal_delete(conn, i)
        conn.execute("DELETE FROM org_unit WHERE path LIKE 'CALEP/%'")
        conn.commit()
