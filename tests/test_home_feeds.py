"""
Home activity feeds — the 'Upcoming activities' and 'Recently concluded' cards.

Two layers:
* Route level — the home page renders both cards, and every 'Recently concluded'
  link resolves (guards the id-matching contract: the card id must equal the
  build_events representative id the report route expects, never a raw
  form_instance id, which would 404).
* Storage level — `upcoming_events` selects future-dated activities only and
  surfaces the link-tree token; `today_local` returns the local calendar day.
"""
import re
import storage as st


def test_home_renders_both_feeds(admin):
    r = admin.get("/css")
    assert r.status_code == 200
    assert "Upcoming activities" in r.text
    assert "Recently concluded" in r.text
    # The concluded card carries its window filters (week / 30 days / quarter).
    assert "Last week" in r.text and "Last 30 days" in r.text and "Last quarter" in r.text


def test_css_hub_is_titled_css_hub(admin):
    # /css is the CSS hub, not the home page: the personal greeting lives on `/`.
    r = admin.get("/css")
    assert "<h1>CSS hub</h1>" in r.text


def test_recently_concluded_links_resolve(admin):
    """Every concluded card must link somewhere renderable. Bureau (Form-2) events
    open their SERVQUAL report — the card id must equal the build_events
    representative id that route expects, never a raw form_instance id (404).
    Invited / Form-3-only events have no Form-2 report (that route 404s on f2-less
    events), so they open their resource-person results in the Type-3 report,
    narrowed to that activity. We follow each item's own `url`, which encodes that
    rule."""
    import json
    r = admin.get("/css")
    assert r.status_code == 200
    blob = r.text.split("window.HOME_CONCLUDED =", 1)[1].split(";", 1)[0]
    items = json.loads(blob)
    # The delivered test DB has recent activities with feedback, so this is non-empty.
    assert items, "no concluded activities passed to the home feed"
    saw_invited = False
    for a in items[:12]:        # sample — every url is built the same way
        url = a.get("url") or f"/reports/activities/{a['id']}"
        if a.get("invited"):
            saw_invited = True
            # #48: an invited/F3-only activity links to its Type-3 results, not the
            # generic invited-events list — so the organizer sees its numbers.
            assert url == f"/reports?type=3&activity={a['id']}"
        else:
            assert url.startswith("/reports/activities/")
        assert admin.get(url).status_code == 200, f"concluded link {url} did not resolve"
    # The delivered DB includes the HRH PK Reorientation invited activity, so the
    # invited branch is actually exercised here (not silently skipped).
    assert saw_invited, "expected at least one invited/F3-only concluded activity"


def test_upcoming_events_helper(db_path):
    """upcoming_events returns future-dated Type-2 activities (today-or-later),
    excludes past ones, and carries the link-tree token when present."""
    conn = st.connect(db_path)
    try:
        def _mk(event_date, token):
            cur = conn.execute(
                "INSERT INTO form_instance(survey_type, form, qr_token, event_date, "
                "topic, venue) VALUES (2,'F2',?,?,?,?)",
                (token, event_date, f"Probe {token}", "Probe Hall"))
            return cur.lastrowid

        future_fid = _mk("2099-01-01", "probe_future")
        past_fid = _mk("2000-01-01", "probe_past")
        ev = st.create_event(conn, "Probe Future Activity", "2099-01-01",
                             venue="Probe Hall", form_instance_ids=[future_fid])
        conn.commit()

        up = st.upcoming_events(conn, limit=100)
        ids = {row["id"] for row in up}
        assert future_fid in ids, "future activity missing from upcoming"
        assert past_fid not in ids, "past activity leaked into upcoming"
        row = next(r for r in up if r["id"] == future_fid)
        assert row["event_token"] == ev["event_token"]
        assert row["topic"] == "Probe probe_future"  # the form_instance topic
    finally:
        # leave the shared session DB as we found it
        conn.execute("DELETE FROM event_form WHERE form_instance_id IN (?,?)",
                     (future_fid, past_fid))
        conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
        conn.execute("DELETE FROM form_instance WHERE id IN (?,?)", (future_fid, past_fid))
        conn.commit()
        conn.close()


def test_ongoing_standalone_surfaces_collecting_invited(db_path):
    """A standalone speaker review (Form 3, no event record) that is collecting
    today must surface in `ongoing_standalone` with a response count and its public
    rating link — this is the home Ongoing feed's coverage of "open surveys" the
    bureau `ongoing_events` deliberately skips. The undated historical backlog
    (created_by NULL) must NOT leak in."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    try:
        # app-created, collecting today, no event -> should appear
        cur = conn.execute(
            "INSERT INTO form_instance(survey_type, form, qr_token, event_date, "
            "topic, venue, created_by, close_at) VALUES (3,'F3',?,?,?,?,?,?)",
            ("probe_seq", today, "Probe Speaker Review", "Probe Hall",
             "probe@doh.gov.ph", today + "T23:59"))
        standalone_fid = cur.lastrowid
        # backlog: same day but no creator -> must be excluded
        cur = conn.execute(
            "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic) "
            "VALUES (3,'F3',?,?,?)", ("probe_backlog", today, "Probe Backlog"))
        backlog_fid = cur.lastrowid
        conn.commit()

        rows = st.ongoing_standalone(conn, limit=100)
        by_id = {r["id"]: r for r in rows}
        assert standalone_fid in by_id, "collecting standalone activity missing"
        assert backlog_fid not in by_id, "historical backlog leaked into feed"
        row = by_id[standalone_fid]
        assert row["standalone"] is True
        assert row["link"] == "/r/probe_seq"
        assert row["registered"] is None      # no registration funnel
        assert row["responses"] == 0
    finally:
        conn.execute("DELETE FROM form_instance WHERE id IN (?,?)",
                     (standalone_fid, backlog_fid))
        conn.commit()
        conn.close()


def test_ongoing_inline_archive_standalone(admin, db_path):
    """An admin can archive a collecting STANDALONE activity straight from the home
    Ongoing feed: the row carries an Archive form posting to /activities/instance/
    <fid>/archive, and after the POST the activity drops out of the feed (archived)."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    cur = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, "
        "topic, venue, created_by, close_at) VALUES (3,'F3',?,?,?,?,?,?)",
        ("probe_inline_std", today, "Probe Inline Standalone", "Probe Hall",
         "probe@doh.gov.ph", today + "T23:59"))
    fid = cur.lastrowid
    conn.commit(); conn.close()
    try:
        # The feed renders the row with its inline archive control.
        r = admin.get("/css")
        assert r.status_code == 200
        assert f"/activities/instance/{fid}/archive" in r.text
        # Archiving it from the feed hides it.
        p = admin.post(f"/activities/instance/{fid}/archive", follow_redirects=False)
        assert p.status_code == 303
        conn = st.connect(db_path)
        archived = conn.execute(
            "SELECT archived FROM form_instance WHERE id=?", (fid,)).fetchone()[0]
        conn.close()
        assert archived == 1
        assert f"/activities/instance/{fid}/archive" not in admin.get("/css").text
    finally:
        conn = st.connect(db_path)
        conn.execute("DELETE FROM form_instance WHERE id=?", (fid,))
        conn.commit(); conn.close()


def test_ongoing_inline_archive_bureau_event_archives_all_forms(admin, db_path):
    """Archiving a collecting BUREAU event from the feed must hide the WHOLE activity
    — the Type-2 review plus every bundled speaker Type-3 — not just the one form the
    feed row keyed on, mirroring the Edit/merge bulk archive."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    f2 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "venue, created_by, close_at) VALUES (2,'F2',?,?,?,?,?,?)",
        ("probe_inline_f2", today, "Probe Inline Event", "Probe Hall",
         "probe@doh.gov.ph", today + "T23:59")).lastrowid
    f3 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "created_by, close_at) VALUES (3,'F3',?,?,?,?,?)",
        ("probe_inline_f3", today, "Probe Inline Speaker",
         "probe@doh.gov.ph", today + "T23:59")).lastrowid
    ev = st.create_event(conn, "Probe Inline Event", today, venue="Probe Hall",
                         form_instance_ids=[f2, f3])
    conn.commit(); conn.close()
    try:
        # Posting the f2 (the row the feed surfaces) archives both bundled forms.
        p = admin.post(f"/activities/instance/{f2}/archive", follow_redirects=False)
        assert p.status_code == 303
        conn = st.connect(db_path)
        rows = dict(conn.execute(
            "SELECT id, archived FROM form_instance WHERE id IN (?,?)", (f2, f3)).fetchall())
        conn.close()
        assert rows[f2] == 1 and rows[f3] == 1, "bureau event archive must cover every form"
    finally:
        conn = st.connect(db_path)
        conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
        conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
        conn.execute("DELETE FROM form_instance WHERE id IN (?,?)", (f2, f3))
        conn.commit(); conn.close()


def test_instance_archive_restore_round_trip_bureau_event(admin, db_path):
    """The inline archive route also supports restore=1 for a bureau event: archiving
    (as above) hides every bundled form, and posting restore=1 back at the same id
    brings all of them back — closing the gap where an event archived from the
    Ongoing feed or Recent activities had no way to be undone (spot-feedback #67)."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    f2 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "venue, created_by, close_at) VALUES (2,'F2',?,?,?,?,?,?)",
        ("probe_restore_f2", today, "Probe Restore Event", "Probe Hall",
         "probe@doh.gov.ph", today + "T23:59")).lastrowid
    f3 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "created_by, close_at) VALUES (3,'F3',?,?,?,?,?)",
        ("probe_restore_f3", today, "Probe Restore Speaker",
         "probe@doh.gov.ph", today + "T23:59")).lastrowid
    ev = st.create_event(conn, "Probe Restore Event", today, venue="Probe Hall",
                         form_instance_ids=[f2, f3])
    conn.commit(); conn.close()
    try:
        p = admin.post(f"/activities/instance/{f2}/archive", follow_redirects=False)
        assert p.status_code == 303 and p.headers["location"] == "/"
        conn = st.connect(db_path)
        rows = dict(conn.execute(
            "SELECT id, archived FROM form_instance WHERE id IN (?,?)", (f2, f3)).fetchall())
        conn.close()
        assert rows[f2] == 1 and rows[f3] == 1

        # It's now visible on the Archived activities page — previously event-bundled
        # archives were invisible there (only standalone forms showed).
        r = admin.get("/activities/archived")
        assert "Probe Restore Event" in r.text
        assert f"/activities/instance/{f2}/archive" in r.text

        p2 = admin.post(f"/activities/instance/{f2}/archive", data={"restore": "1"},
                        follow_redirects=False)
        assert p2.status_code == 303 and p2.headers["location"] == "/activities/archived"
        conn = st.connect(db_path)
        rows = dict(conn.execute(
            "SELECT id, archived FROM form_instance WHERE id IN (?,?)", (f2, f3)).fetchall())
        conn.close()
        assert rows[f2] == 0 and rows[f3] == 0, "restore must cover every bundled form"
    finally:
        conn = st.connect(db_path)
        conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
        conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
        conn.execute("DELETE FROM form_instance WHERE id IN (?,?)", (f2, f3))
        conn.commit(); conn.close()


def test_recent_activities_strip_offers_archive_for_bureau_event(admin, db_path):
    """'Recent activities' previously offered an inline Archive control only for
    standalone forms; a full bureau event now gets one too — a bureau event drops
    out of the Ongoing feed at the end of its event day (unless close_at is set),
    so that used to be the ONLY window to archive it (spot-feedback #67: a same-day
    duplicate with no responses had no reachable Archive button once it aged out)."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    f2 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "venue, created_by) VALUES (2,'F2',?,?,?,?,?)",
        ("probe_recent_f2", today, "Probe Recent Event", "Probe Hall",
         "admin@test.local")).lastrowid
    ev = st.create_event(conn, "Probe Recent Event", today, venue="Probe Hall",
                         form_instance_ids=[f2], created_by="admin@test.local")
    conn.commit(); conn.close()
    try:
        r = admin.get("/css")
        assert r.status_code == 200
        assert "Probe Recent Event" in r.text
        assert f"/activities/instance/{f2}/archive" in r.text
    finally:
        conn = st.connect(db_path)
        conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
        conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
        conn.execute("DELETE FROM form_instance WHERE id=?", (f2,))
        conn.commit(); conn.close()


def test_ongoing_inline_archive_requires_manage_permission(viewer, db_path):
    """A viewer (no create_activity) must not be able to archive via the inline route."""
    conn = st.connect(db_path)
    today = st.today_local(conn)
    fid = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "created_by, close_at) VALUES (3,'F3',?,?,?,?,?)",
        ("probe_inline_perm", today, "Probe Inline Perm",
         "probe@doh.gov.ph", today + "T23:59")).lastrowid
    conn.commit(); conn.close()
    try:
        viewer.post(f"/activities/instance/{fid}/archive", follow_redirects=False)
        conn = st.connect(db_path)
        archived = conn.execute(
            "SELECT archived FROM form_instance WHERE id=?", (fid,)).fetchone()[0]
        conn.close()
        assert not archived, "viewer must not be able to archive an activity"
    finally:
        conn = st.connect(db_path)
        conn.execute("DELETE FROM form_instance WHERE id=?", (fid,))
        conn.commit(); conn.close()


def test_today_local_is_iso_date(db_path):
    conn = st.connect(db_path)
    try:
        t = st.today_local(conn)
    finally:
        conn.close()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", t), f"today_local returned {t!r}"
