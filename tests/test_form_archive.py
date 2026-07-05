"""Per-form archive for STANDALONE activities (a Form-3 speaker review with no
event record — the shape the event-level archive can't reach).

Contract locked here:
  * POST /activities/form/{fid}/archive flips form_instance.archived, so the form
    drops out of the home "Your recent activities" strip AND the ongoing feed;
  * only the creator or an admin may archive (another manager is refused);
  * restore=1 brings it back and it shows on /activities/archived meanwhile;
  * a form that belongs to an event is refused (those archive at the event level).
"""
import storage as st


def _one_rp(db_path):
    conn = st.connect(db_path)
    row = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return row[0]


def _make_standalone(db_path, created_by, topic):
    """A lone Form-3 speaker review dated today (so it counts as 'ongoing'),
    stamped to `created_by`, with no event_form link. Returns its form id."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    fid = st.create_form_instance(
        conn, survey_type=3, form="F3", event_date=today,
        rp_id=_one_rp(db_path), topic=topic, created_by=created_by)
    conn.close()
    return fid


def _archived_flag(db_path, fid):
    conn = st.connect(db_path)
    v = conn.execute("SELECT COALESCE(archived,0) FROM form_instance WHERE id=?", (fid,)).fetchone()[0]
    conn.close()
    return v


def test_creator_archive_drops_from_strip_and_ongoing(manager, db_path):
    topic = "Standalone Archive — creator"
    fid = _make_standalone(db_path, "manager@test.local", topic)
    # visible before: home strip + ongoing-standalone feed
    conn = st.connect(db_path)
    assert any(a["topic"] == topic and a["archivable"]
               for a in st.activities_by_creator(conn, "manager@test.local", limit=200))
    assert any(o["id"] == fid for o in st.ongoing_standalone(conn, limit=200))
    conn.close()

    r = manager.post(f"/activities/form/{fid}/archive", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert _archived_flag(db_path, fid) == 1

    conn = st.connect(db_path)
    assert not any(a["topic"] == topic
                   for a in st.activities_by_creator(conn, "manager@test.local", limit=200))
    assert not any(o["id"] == fid for o in st.ongoing_standalone(conn, limit=200))
    conn.close()


def test_admin_can_archive_anothers_form(admin, db_path):
    fid = _make_standalone(db_path, "someoneelse@test.local", "Standalone — admin acts")
    r = admin.post(f"/activities/form/{fid}/archive", follow_redirects=False)
    assert r.status_code == 303
    assert _archived_flag(db_path, fid) == 1


def test_all_creators_surfaces_anothers_standalone(db_path):
    """all_creators=True drops the creator scope, so an admin's home strip can reach
    (and archive) a standalone activity someone else — or no one — created."""
    fid = _make_standalone(db_path, "someoneelse@test.local", "Standalone — all creators")
    conn = st.connect(db_path)
    # the creator scope hides it from a different manager...
    assert not any(a["id"] == fid
                   for a in st.activities_by_creator(conn, "manager@test.local", limit=200))
    # ...but all_creators surfaces it, flagged archivable (no event).
    rows = st.activities_by_creator(conn, "", limit=200, all_creators=True)
    conn.close()
    assert any(a["id"] == fid and a["archivable"] for a in rows)


def test_admin_home_strip_shows_archive_for_anothers_form(admin, db_path):
    """The admin home strip lists every recent activity, so a standalone one created
    by someone else renders its per-form Archive button."""
    fid = _make_standalone(db_path, "someoneelse@test.local", "Standalone — on admin home")
    r = admin.get("/")
    assert r.status_code == 200
    assert "Recent activities" in r.text          # admin relabel of the strip
    assert f"/activities/form/{fid}/archive" in r.text


def test_other_manager_is_refused(manager, db_path):
    # Created by someone else; a non-admin manager who isn't the creator can't archive.
    fid = _make_standalone(db_path, "someoneelse@test.local", "Standalone — not yours")
    r = manager.post(f"/activities/form/{fid}/archive", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert _archived_flag(db_path, fid) == 0, "a non-creator non-admin must not archive it"


def test_restore_round_trip_and_archived_page(manager, db_path):
    topic = "Standalone Archive — restore"
    fid = _make_standalone(db_path, "manager@test.local", topic)
    manager.post(f"/activities/form/{fid}/archive", follow_redirects=False)
    assert _archived_flag(db_path, fid) == 1

    # while archived it appears on the Archived page with a Restore action
    r = manager.get("/activities/archived")
    assert r.status_code == 200
    assert topic in r.text
    assert f"/activities/form/{fid}/archive" in r.text

    # restore -> back on the strip, off the Archived page
    r = manager.post(f"/activities/form/{fid}/archive", data={"restore": "1"},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/activities/archived"
    assert _archived_flag(db_path, fid) == 0
    conn = st.connect(db_path)
    assert any(a["topic"] == topic
               for a in st.activities_by_creator(conn, "manager@test.local", limit=200))
    conn.close()


def test_bureau_event_form_is_refused(manager, db_path):
    """A form attached to an event uses the event-level archive; the per-form route
    must refuse it (no change), so the two paths never compete."""
    rp = _one_rp(db_path)
    r = manager.post("/create", data={
        "event_type": "outside", "activity_name": "Form-Archive Event Guard",
        "event_date": "2026-06-20", "venue": "Hall",
        "external_org": "Partner Org", "qr_mode": "combined",
        "rp_id": [str(rp)], "topic": ["Session A"],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:300]
    conn = st.connect(db_path)
    fid = conn.execute(
        "SELECT ef.form_instance_id FROM event_form ef "
        "JOIN event e ON e.id = ef.event_id WHERE e.title=? LIMIT 1",
        ("Form-Archive Event Guard",)).fetchone()[0]
    conn.close()

    r = manager.post(f"/activities/form/{fid}/archive", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert _archived_flag(db_path, fid) == 0, "event-attached form must not be archived here"
