"""Duplicate-activity heads-up on the /create screen (spot-feedback #67).

The live system twice ended up with a same-day, same-title, same-creator pair of
events where the second was an accidental resubmit that left an empty twin (once
26 minutes apart, once 3 minutes apart), and by the time anyone noticed the empty
one had already aged off the "Ongoing" feed with no Archive button left anywhere.

This is a live, NON-blocking heads-up: /create/check-duplicate reports whether the
signed-in user already made an event with this title + date recently, and the
create screen's JS shows a note with a link to it — but /create itself is
untouched, so submitting twice on purpose (a legitimate second activity that
happens to share a name) still works exactly as before. See
storage.find_recent_duplicate_event for the match rule.
"""
import storage as st


def _bureau(manager, name="Duplicate Warning Probe", date="2026-06-15", **extra):
    data = {"event_type": "bureau", "activity_name": name,
            "event_date": date, "qr_mode": "combined"}
    data.update(extra)
    return manager.post("/create", data=data, follow_redirects=True)


def _events(db_path, title):
    conn = st.connect(db_path)
    rows = conn.execute("SELECT id, event_token, created_by FROM event WHERE title=? "
                        "ORDER BY id", (title,)).fetchall()
    conn.close()
    return rows


# ── storage.find_recent_duplicate_event ─────────────────────────────────────

def test_storage_finds_same_creator_same_title_and_date(manager, db_path):
    title = "Storage Dup — same creator"
    _bureau(manager, name=title)
    conn = st.connect(db_path)
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-15", "manager@test.local")
    conn.close()
    assert dup is not None
    assert dup["responses"] == 0
    assert dup["event_kind"] == "bureau"


def test_storage_ignores_a_different_creator(manager, db_path):
    title = "Storage Dup — different creator"
    _bureau(manager, name=title)
    conn = st.connect(db_path)
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-15", "someone-else@test.local")
    conn.close()
    assert dup is None


def test_storage_ignores_a_different_date(manager, db_path):
    title = "Storage Dup — different date"
    _bureau(manager, name=title, date="2026-06-15")
    conn = st.connect(db_path)
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-16", "manager@test.local")
    conn.close()
    assert dup is None


def test_storage_ignores_outside_the_lookback_window(manager, db_path):
    title = "Storage Dup — outside window"
    _bureau(manager, name=title)
    conn = st.connect(db_path)
    # A negative window pushes the cutoff into the future, so even an event
    # created this instant reads as "too old" — deterministic, no clock races.
    dup = st.find_recent_duplicate_event(
        conn, title, "2026-06-15", "manager@test.local", within_hours=-1)
    conn.close()
    assert dup is None, "a cutoff in the future should never match anything"


# ── GET /create/check-duplicate ──────────────────────────────────────────────

def test_check_duplicate_endpoint_reports_none_when_nothing_matches(manager):
    r = manager.get("/create/check-duplicate", params={
        "activity_name": "Never Created This", "event_date": "2026-06-15"})
    assert r.status_code == 200
    assert r.json() == {"duplicate": None}


def test_check_duplicate_endpoint_reports_the_existing_event(manager, db_path):
    title = "Check-Duplicate Endpoint Probe"
    _bureau(manager, name=title)
    ev = _events(db_path, title)[0]

    r = manager.get("/create/check-duplicate", params={
        "activity_name": title, "event_date": "2026-06-15"})
    assert r.status_code == 200
    dup = r.json()["duplicate"]
    assert dup is not None
    assert dup["event_token"] == ev[1]
    assert dup["event_kind"] == "bureau"
    assert dup["responses"] == 0
    assert dup["created_at_human"]                 # a non-empty human-readable stamp


def test_check_duplicate_endpoint_requires_login(app_mod):
    from starlette.testclient import TestClient
    anon = TestClient(app_mod.app, follow_redirects=False)
    r = anon.get("/create/check-duplicate", params={
        "activity_name": "Whatever", "event_date": "2026-06-15"})
    assert r.status_code in (302, 303, 401, 403)


# ── /create itself stays exactly as it was — advisory only, never blocking ──

def test_create_still_allows_a_genuine_second_activity_with_the_same_name(manager, db_path):
    title = "Duplicate Warning — legitimately created twice"
    r1 = _bureau(manager, name=title)
    assert r1.status_code == 200, r1.text[:600]
    r2 = _bureau(manager, name=title)
    assert r2.status_code == 200, r2.text[:600]
    assert len(_events(db_path, title)) == 2, "the heads-up must never block a real resubmit"


# ── create screen renders the wiring ────────────────────────────────────────

def test_create_screen_renders_duplicate_check_wiring(manager):
    r = manager.get("/create")
    assert r.status_code == 200
    assert 'id="dupWarn"' in r.text
    assert "/create/check-duplicate" in r.text
    assert "checkDuplicate" in r.text
