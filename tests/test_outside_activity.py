"""Phase 1 foundation — RP-only / "outside event — we were invited" activities.

An outside activity is grouped into a registration-DISABLED event record so it has
a name + identity to manage and monitor, but it has no public link tree and no
registration (no Form 2). These tests lock that contract:
  * /create (outside) persists an event with event_kind='outside', the typed
    activity name as its title, and both speaker forms linked to it;
  * the combined QR for an outside activity is the /seq sequence, NOT an /e/ link
    tree, and the link-tree URL 404s for it;
  * the home "Your recent activities" strip collapses the activity to ONE row that
    shows the activity name and the total responses across its speakers.
"""
import re
import storage as st


def _two_internal_rps(db_path):
    conn = st.connect(db_path)
    rows = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 ORDER BY id LIMIT 2").fetchall()
    conn.close()
    assert len(rows) >= 2, "need two internal resource persons in the test DB"
    return rows[0][0], rows[1][0]


def _make_outside(manager, db_path, name="Invited Immunization Forum", date="2026-06-12"):
    rp1, rp2 = _two_internal_rps(db_path)
    r = manager.post("/create", data={
        "event_type": "outside", "activity_name": name,
        "event_date": date, "venue": "Partner Hall",
        "external_org": "DOH Regional Office", "qr_mode": "combined",
        "rp_id": [str(rp1), str(rp2)], "topic": ["Cold chain", "Surveillance"],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:500]
    return r, name


def _outside_event(db_path, title):
    conn = st.connect(db_path)
    row = conn.execute(
        "SELECT id, event_token, event_kind, lead_org_id FROM event "
        "WHERE title=? ORDER BY id DESC LIMIT 1", (title,)).fetchone()
    conn.close()
    return row


def test_outside_creates_registration_disabled_event(manager, db_path):
    _make_outside(manager, db_path, name="Outside Grouping Test")
    ev = _outside_event(db_path, "Outside Grouping Test")
    assert ev is not None, "an event record should group the outside activity"
    event_id, token, kind, lead_org_id = ev
    assert kind == "outside"
    assert lead_org_id is None, "outside activities have an external organizer, no lead unit"
    # Both speaker forms are linked to the event, and they're Form 3 (no Form 2).
    conn = st.connect(db_path)
    forms = conn.execute(
        "SELECT fi.survey_type FROM event_form ef "
        "JOIN form_instance fi ON fi.id = ef.form_instance_id WHERE ef.event_id=?",
        (event_id,)).fetchall()
    conn.close()
    types = sorted(t[0] for t in forms)
    assert types == [3, 3], f"expected two Form 3 speakers, got {types}"
    # get_event exposes the kind.
    assert st.get_event(st.connect(db_path), token)["event_kind"] == "outside"


def test_outside_combined_qr_is_sequence_not_link_tree(manager, db_path):
    r, _ = _make_outside(manager, db_path, name="Outside Seq Test")
    assert "/seq?tokens=" in r.text, "combined QR for an outside activity is the /seq sequence"
    assert "/e/" not in r.text, "outside activities must not get a public link tree"


def test_link_tree_404s_for_outside_event(client, manager, db_path):
    _make_outside(manager, db_path, name="Outside NoTree Test")
    token = _outside_event(db_path, "Outside NoTree Test")[1]
    r = client.get(f"/e/{token}")
    assert r.status_code == 404, "the link-tree URL must not resolve for an outside activity"


def test_recent_strip_collapses_outside_to_one_named_row(manager, db_path):
    name = "Outside Strip Test"
    _make_outside(manager, db_path, name=name)
    # created_by is the manager account username (see conftest ROLE_USERS).
    conn = st.connect(db_path)
    items = st.activities_by_creator(conn, "manager@test.local", limit=20)
    conn.close()
    mine = [a for a in items if a["topic"] == name]
    assert len(mine) == 1, "the two speakers should collapse to ONE activity row named for the activity"
    row = mine[0]
    assert row["event_kind"] == "outside"
    # Phase 2: the strip row opens the activity's manage page.
    token = _outside_event(db_path, name)[1]
    assert row["link"] == f"/activities/{token}/manage"
    assert row["tip"] == "Manage this activity"
    assert row["responses"] == 0  # no responses recorded yet


# --------------------------------------------------------------------------
# Phase 2 — the focused manage page for an outside activity.
# --------------------------------------------------------------------------

def test_manage_page_renders_for_outside(manager, db_path):
    name = "Manage Render Test"
    _make_outside(manager, db_path, name=name)
    token = _outside_event(db_path, name)[1]
    r = manager.get(f"/activities/{token}/manage")
    assert r.status_code == 200
    assert name in r.text
    assert "Invited activity" in r.text
    assert "Combined — all speakers" in r.text          # combined QR present
    assert "Cold chain" in r.text and "Surveillance" in r.text


def test_add_and_rename_speaker(manager, db_path):
    name = "Edit Speakers Test"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    # add a third speaker
    rp1, _ = _two_internal_rps(db_path)
    r = manager.post(f"/activities/{token}/speakers",
                     data={"rp_id": str(rp1), "topic": "Logistics"}, follow_redirects=True)
    assert r.status_code == 200 and "Logistics" in r.text
    # rename the first speaker's topic
    conn = st.connect(db_path)
    speakers = st.manage_event_speakers(conn, event_id)
    conn.close()
    first = speakers[0]
    r = manager.post(f"/activities/{token}/speakers/{first['id']}/rename",
                     data={"topic": "Cold-chain mgmt"}, follow_redirects=True)
    assert r.status_code == 200 and "Cold-chain mgmt" in r.text


def test_remove_blocked_once_responses_exist(manager, db_path):
    name = "Remove Guard Test"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    conn = st.connect(db_path)
    speakers = st.manage_event_speakers(conn, event_id)
    target = speakers[0]
    # record a real response against this speaker form
    st.record_response(conn, target["id"], [("RP1", 7)])
    conn.close()
    # removal must be refused (its ratings would be lost)
    r = manager.post(f"/activities/{token}/speakers/{target['id']}/remove", follow_redirects=False)
    assert r.status_code == 303 and "err=hasresponses" in r.headers["location"]
    conn = st.connect(db_path)
    assert st.speaker_response_count(conn, target["id"]) == 1   # still there
    still = [s["id"] for s in st.manage_event_speakers(conn, event_id)]
    conn.close()
    assert target["id"] in still
    # a speaker with NO responses can still be removed
    other = speakers[1]
    r = manager.post(f"/activities/{token}/speakers/{other['id']}/remove", follow_redirects=True)
    assert r.status_code == 200
    conn = st.connect(db_path)
    remaining = [s["id"] for s in st.manage_event_speakers(conn, event_id)]
    conn.close()
    assert other["id"] not in remaining


def test_close_and_archive_then_restore(manager, db_path):
    name = "Close Archive Test"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    # close: every form gets a close_at
    manager.post(f"/activities/{token}/close", follow_redirects=False)
    conn = st.connect(db_path)
    win = st.get_event_window(conn, event_id)
    conn.close()
    assert win["close_at"], "closing should stamp a close_at on the forms"
    # archive: forms vanish from the creator's strip
    manager.post(f"/activities/{token}/archive", follow_redirects=False)
    conn = st.connect(db_path)
    active, archived = st.event_form_counts(conn, event_id)
    strip = [a for a in st.activities_by_creator(conn, "manager@test.local", limit=50)
             if a["topic"] == name]
    conn.close()
    assert active == 0 and archived >= 1
    assert strip == [], "archived activity should drop off the recent strip"
    # the manage page shows the archived/restore state
    r = manager.get(f"/activities/{token}/manage")
    assert r.status_code == 200 and "archived" in r.text.lower()
    # restore brings it back
    manager.post(f"/activities/{token}/archive", data={"restore": "1"}, follow_redirects=False)
    conn = st.connect(db_path)
    active2, _ = st.event_form_counts(conn, event_id)
    conn.close()
    assert active2 >= 1


# --------------------------------------------------------------------------
# Phase 3 — the anonymous response tracker in the monitor.
# --------------------------------------------------------------------------

def test_monitor_index_groups_outside_separately(manager, db_path):
    name = "Monitor Index Invited"
    _make_outside(manager, db_path, name=name, date="2027-06-15")   # future → still listed
    r = manager.get("/monitor")
    assert r.status_code == 200
    assert "Invited activities" in r.text                 # its own section
    assert name in r.text
    token = _outside_event(db_path, name)[1]
    assert f"/monitor/{token}" in r.text                  # links to the tracker


def test_tracker_counts_and_stays_anonymous(manager, db_path):
    name = "Tracker Counts"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    conn = st.connect(db_path)
    speakers = st.manage_event_speakers(conn, event_id)
    for _ in range(3):
        st.record_response(conn, speakers[0]["id"], [("RP1", 6)],
                           item_remarks={"SEX": "F", "AFFIL": "DOH"})
    st.record_response(conn, speakers[1]["id"], [("RP1", 5)],
                       item_remarks={"SEX": "M", "AFFIL": "NON-DOH"})
    conn.close()
    r = manager.get(f"/monitor/{token}")
    assert r.status_code == 200
    body = r.text
    assert ">4<" in body                                  # 4 total responses
    assert "Cold chain" in body and "Surveillance" in body
    assert "no participant names" in body.lower()         # framed as anonymous


def test_outside_monitor_links_to_comments_once_answered(manager, db_path):
    """#50: the invited-activity tracker offers a 'What people said' link to its
    Type-3 results (anchored at the comments) — only after a response lands."""
    name = "Comments Link Invited"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    # No responses yet -> no link.
    assert "What people said" not in manager.get(f"/monitor/{token}").text
    # One scored response -> the link appears, pointing at the Type-3 results + #comments.
    conn = st.connect(db_path)
    sp = st.manage_event_speakers(conn, event_id)[0]
    st.record_response(conn, sp["id"], [("B1", 6)], remarks="Very clear talk")
    conn.close()
    page = manager.get(f"/monitor/{token}").text
    assert "What people said" in page
    assert "type=3" in page and "#comments" in page


def test_tracker_demographics_suppressed_until_threshold(manager, db_path):
    name = "Tracker Suppress"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    conn = st.connect(db_path)
    sp = st.manage_event_speakers(conn, event_id)[0]
    for _ in range(st.MIN_DEMOG_N - 1):                   # below threshold
        st.record_response(conn, sp["id"], [("RP1", 6)], item_remarks={"SEX": "F"})
    conn.close()
    assert "Hidden until" in manager.get(f"/monitor/{token}").text
    conn = st.connect(db_path)
    for _ in range(3):                                    # cross the threshold
        st.record_response(conn, sp["id"], [("RP1", 6)], item_remarks={"SEX": "M"})
    conn.close()
    body = manager.get(f"/monitor/{token}").text
    assert "Hidden until" not in body
    assert "Female" in body and "Male" in body


# --------------------------------------------------------------------------
# Phase 4 — the combined QR is now ONE page with a single submit.
# --------------------------------------------------------------------------

def _speaker_tokens(db_path, event_id):
    conn = st.connect(db_path)
    toks = [s["qr_token"] for s in st.manage_event_speakers(conn, event_id)]
    conn.close()
    return toks


def test_combined_form_is_one_page_not_a_menu(client, manager, db_path):
    name = "Combined OnePage"
    _make_outside(manager, db_path, name=name)
    event_id = _outside_event(db_path, name)[0]
    toks = _speaker_tokens(db_path, event_id)
    r = client.get("/seq", params={"tokens": ",".join(toks)})
    assert r.status_code == 200
    body = r.text
    assert 'action="/seq"' in body and 'name="tokens"' in body   # single combined form
    assert "About you" in body                                   # demographics asked once
    assert "Cold chain" in body and "Surveillance" in body       # both speakers on the page
    assert body.count("Submit my answers") == 1                  # exactly ONE submit
    assert "complete each survey in turn" not in body            # not the old menu


def test_combined_submit_records_one_response_per_speaker(client, manager, db_path):
    name = "Combined Submit"
    _make_outside(manager, db_path, name=name)
    event_id = _outside_event(db_path, name)[0]
    t1, t2 = _speaker_tokens(db_path, event_id)
    data = {"tokens": f"{t1},{t2}", "sex": "F", "affil": "DOH",
            f"{t1}::A": "6", f"{t2}::A": "5"}
    r = client.post("/seq", data=data)
    assert r.status_code == 200
    assert "2" in r.text and "resource person" in r.text.lower()
    conn = st.connect(db_path)
    speakers = {s["qr_token"]: s for s in st.manage_event_speakers(conn, event_id)}
    c1 = st.speaker_response_count(conn, speakers[t1]["id"])
    c2 = st.speaker_response_count(conn, speakers[t2]["id"])
    # each recorded response carries the shared demographics
    demo = conn.execute(
        "SELECT COUNT(*) FROM item_remark WHERE item_id='SEX'").fetchone()[0]
    conn.close()
    assert c1 == 1 and c2 == 1
    assert demo >= 2


def _speaker_fid(db_path, tok):
    conn = st.connect(db_path)
    fid = st.get_form_context(conn, tok)["id"]
    conn.close()
    return fid


def test_close_hard_locks_paper_entry_and_details(manager, encoder, db_path):
    """v1.62: closing an invited activity stops paper entry too (not just the
    public link), flags the event closed, and locks the manage page details."""
    name = "Hard Close Test"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    tok = _speaker_tokens(db_path, event_id)[0]

    # before close: not flagged closed, paper entry context is unlocked
    conn = st.connect(db_path)
    assert st.event_is_closed(conn, event_id) is False
    assert st.get_form_context(conn, tok)["encoding_locked"] is False
    conn.close()

    # close: every form gets close_at AND encoding_locked; event reads as closed
    manager.post(f"/activities/{token}/close", follow_redirects=False)
    conn = st.connect(db_path)
    assert st.event_is_closed(conn, event_id) is True
    assert st.get_form_context(conn, tok)["encoding_locked"] is True
    conn.close()

    # the encode form now shows the locked state with no entry form
    g = encoder.get(f"/encode/{tok}")
    assert g.status_code == 200
    assert "no longer accepts entries" in g.text
    assert "Save &amp; enter next" not in g.text          # the entry form is gone

    # a paper-entry POST is refused and records nothing
    fid = _speaker_fid(db_path, tok)
    p = encoder.post(f"/encode/{tok}", data={}, follow_redirects=False)
    assert p.status_code == 409
    conn = st.connect(db_path)
    assert st.speaker_response_count(conn, fid) == 0
    conn.close()

    # the manage page surfaces the closed banner, Reopen, locks the cards
    m = manager.get(f"/activities/{token}/manage").text
    assert "This activity is closed" in m
    # Outside activities have no Form-2 SERVQUAL report — the old /reports/activities/<id>
    # link 404'd for them, so it's gone. Their RP results link is responses-gated, and
    # this activity has none, so no results link shows here either.
    assert f"/reports/activities/{event_id}" not in m
    assert f"/activities/{token}/reopen" in m              # Reopen action
    assert "inert" in m                                    # editable region locked
    assert "Close responses now" not in m                 # close button swapped out


def test_reopen_unlocks_and_restores_paper_entry(manager, encoder, db_path):
    """Reopen reverses the close: entry resumes and details unlock again."""
    name = "Reopen Test"
    _make_outside(manager, db_path, name=name)
    event_id, token = _outside_event(db_path, name)[0], _outside_event(db_path, name)[1]
    tok = _speaker_tokens(db_path, event_id)[0]
    fid = _speaker_fid(db_path, tok)

    manager.post(f"/activities/{token}/close", follow_redirects=False)
    assert encoder.post(f"/encode/{tok}", data={}).status_code == 409

    manager.post(f"/activities/{token}/reopen", follow_redirects=False)
    conn = st.connect(db_path)
    assert st.event_is_closed(conn, event_id) is False
    assert st.get_form_context(conn, tok)["encoding_locked"] is False
    conn.close()

    # paper entry is accepted again
    r = encoder.post(f"/encode/{tok}", data={}, follow_redirects=True)
    assert r.status_code == 200
    conn = st.connect(db_path)
    assert st.speaker_response_count(conn, fid) == 1
    conn.close()


def test_combined_skipped_speaker_records_nothing(client, manager, db_path):
    name = "Combined Skip"
    _make_outside(manager, db_path, name=name)
    event_id = _outside_event(db_path, name)[0]
    t1, t2 = _speaker_tokens(db_path, event_id)
    # answer only the first speaker; the second is left untouched (skipped)
    r = client.post("/seq", data={"tokens": f"{t1},{t2}", "sex": "M", "affil": "NON-DOH",
                                  f"{t1}::A": "7"})
    assert r.status_code == 200
    conn = st.connect(db_path)
    speakers = {s["qr_token"]: s for s in st.manage_event_speakers(conn, event_id)}
    c1 = st.speaker_response_count(conn, speakers[t1]["id"])
    c2 = st.speaker_response_count(conn, speakers[t2]["id"])
    conn.close()
    assert c1 == 1 and c2 == 0


# --------------------------------------------------------------------------
# Phase 5 — a still-open invited activity stays reachable on the home page.
# An outside activity has only Form-3 speakers grouped under an event record, so
# it falls through BOTH other ongoing feeds (`ongoing_events` needs a Form 2,
# `ongoing_standalone` needs NO event). `ongoing_invited` keeps it in the home
# "Ongoing" card for as long as its /seq window is open, linking to manage —
# otherwise it vanishes from the home page once it ages off the 7-day strip while
# its public form keeps collecting.
# --------------------------------------------------------------------------

def _set_window_all(db_path, event_id, close_at):
    """Stamp the same close_at on every form of an outside event (they share a
    window), the way the /close route does — but to an arbitrary instant."""
    conn = st.connect(db_path)
    for r in conn.execute("SELECT form_instance_id FROM event_form WHERE event_id=?",
                          (event_id,)).fetchall():
        st.set_response_window(conn, r[0], None, close_at)
    conn.close()


def test_ongoing_invited_lists_open_past_activity(manager, db_path):
    name = "Ongoing Invited Open"
    _make_outside(manager, db_path, name=name)          # past event date, no close_at
    token = _outside_event(db_path, name)[1]
    conn = st.connect(db_path)
    rows = [a for a in st.ongoing_invited(conn) if a["topic"] == name]
    conn.close()
    assert len(rows) == 1, "the two speakers collapse to ONE ongoing row for the activity"
    row = rows[0]
    assert row["kind"] == "Invited activity"
    assert row["standalone"] is True and row["event_token"] is None
    assert row["link"] == f"/activities/{token}/manage"
    assert row["tip"] == "Manage this activity"
    assert row["responses"] == 0


def test_ongoing_invited_excludes_future_activity(manager, db_path):
    name = "Ongoing Invited Future"
    _make_outside(manager, db_path, name=name, date="2027-06-15")   # not held yet
    conn = st.connect(db_path)
    names = [a["topic"] for a in st.ongoing_invited(conn)]
    conn.close()
    assert name not in names, "a future invited activity is upcoming, not ongoing"


def test_ongoing_invited_excludes_closed_window(manager, db_path):
    name = "Ongoing Invited Closed"
    _make_outside(manager, db_path, name=name)
    event_id = _outside_event(db_path, name)[0]
    _set_window_all(db_path, event_id, "2026-06-13T00:00")   # window already elapsed
    conn = st.connect(db_path)
    names = [a["topic"] for a in st.ongoing_invited(conn)]
    conn.close()
    assert name not in names, "a closed invited activity leaves the ongoing feed"


def test_ongoing_invited_honours_app_clock_not_container_zone(manager, db_path, monkeypatch):
    """Spot Feedback #59: an activity closed EARLIER THE SAME DAY must leave the Ongoing
    feed at once — and against the app's Asia/Manila clock (tzutil), NOT SQLite's
    date/datetime('now','localtime'), which follows the container (UTC on Hugging Face)
    and drifts ~8 h from the Manila-stamped close_at. Pin the app clock either side of an
    08:57 close and the feed must flip, proving it reads the bound clock, not 'localtime'."""
    name = "Ongoing Invited AppClock"
    _make_outside(manager, db_path, name=name)
    event_id = _outside_event(db_path, name)[0]
    _set_window_all(db_path, event_id, "2026-07-09T08:57:40")   # closed at 08:57 (Manila)

    # App clock AFTER the close (10:35) → gone, even if the container's UTC 'localtime'
    # would still read pre-close and (pre-fix) keep it "collecting".
    monkeypatch.setattr(st, "_local_now", lambda: "2026-07-09T10:35:00")
    monkeypatch.setattr(st, "_local_today", lambda: "2026-07-09")
    conn = st.connect(db_path)
    names = [a["topic"] for a in st.ongoing_invited(conn)]
    conn.close()
    assert name not in names, "closed-before-now activity must leave Ongoing at once"

    # App clock BEFORE the close (08:00) → still collecting.
    monkeypatch.setattr(st, "_local_now", lambda: "2026-07-09T08:00:00")
    conn = st.connect(db_path)
    names = [a["topic"] for a in st.ongoing_invited(conn)]
    conn.close()
    assert name in names, "before the close it is still ongoing"


def test_lifecycle_of_concluded_when_closed_earlier_same_day():
    """lifecycle_of normalises the separator too: a space-form `now` (as the events
    list passes via datetime('now','localtime')) after a 'T'-form close_at on the same
    day is CONCLUDED, not ongoing."""
    # closed at 08:57, viewed at 09:22 the same day → concluded
    assert st.lifecycle_of("2026-06-24", "2026-07-09T08:57:40",
                           "2026-07-09", "2026-07-09 09:22:00") == "concluded"
    # still-open window (close in the future) stays ongoing across the separator
    assert st.lifecycle_of("2026-06-24", "2026-07-09T23:59:00",
                           "2026-07-09", "2026-07-09 09:22:00") == "ongoing"


def test_ongoing_invited_included_while_window_open(manager, db_path):
    name = "Ongoing Invited FutureWindow"
    _make_outside(manager, db_path, name=name)
    event_id = _outside_event(db_path, name)[0]
    _set_window_all(db_path, event_id, "2099-12-31T23:59")   # window still open
    conn = st.connect(db_path)
    names = [a["topic"] for a in st.ongoing_invited(conn)]
    conn.close()
    assert name in names


def test_home_ongoing_shows_open_invited_activity(manager, db_path):
    """End-to-end: an invited activity whose event has passed but whose /seq window
    is still open now surfaces on the home page, linking to its manage page — the
    reported gap where the combined-QR link worked but the activity 'didn't reflect'
    in Upcoming / Ongoing / Recent."""
    name = "Home Ongoing Invited"
    _make_outside(manager, db_path, name=name)          # past event date, still open
    token = _outside_event(db_path, name)[1]
    body = manager.get("/css").text
    assert name in body
    assert f"/activities/{token}/manage" in body
