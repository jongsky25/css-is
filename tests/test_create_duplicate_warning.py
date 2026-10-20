"""Duplicate-activity heads-up on the /create screen (spot-feedback #67).

The live system twice ended up with a same-day, same-title, same-creator pair of
events where the second was an accidental resubmit that left an empty twin (once
26 minutes apart, once 3 minutes apart), and by the time anyone noticed the empty
one had already aged off the "Ongoing" feed with no Archive button left anywhere.
A follow-up report (a real-world DOH policy-orientation duplicate) showed the
original same-creator/6-hour match rule missed the common case: two different
staff logging the same activity, or a resubmit hours or days later — so the match
now keys on title + date alone, regardless of who created it or when.

The live check lists possible matches. Strong matches require a second, explicit
submission so an accidental resubmit cannot silently create another activity.
"""
import re
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
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-15")
    conn.close()
    assert dup is not None
    assert dup["responses"] == 0
    assert dup["event_kind"] == "bureau"


def test_storage_finds_it_across_different_creators(admin, db_path):
    # Two different staff logging the same activity is the common real-world
    # case (e.g. a policy-orientation meeting entered by two encoders) — the
    # match must not be scoped to "same login". This event is created by
    # `admin`; find_recent_duplicate_event takes no creator identity at all.
    title = "Storage Dup — different creator"
    _bureau(admin, name=title)
    conn = st.connect(db_path)
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-15")
    conn.close()
    assert dup is not None


def test_storage_ignores_a_different_date(manager, db_path):
    title = "Storage Dup — different date"
    _bureau(manager, name=title, date="2026-06-15")
    conn = st.connect(db_path)
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-16")
    conn.close()
    assert dup is None


def test_storage_finds_it_regardless_of_age(manager, db_path):
    title = "Storage Dup — old resubmit"
    _bureau(manager, name=title)
    conn = st.connect(db_path)
    # Backdate creation well outside the old 6-hour window — a delayed
    # re-entry days later must still be flagged.
    conn.execute("UPDATE event SET created_at = '2000-01-01T00:00:00' WHERE title = ?",
                 (title,))
    conn.commit()
    dup = st.find_recent_duplicate_event(conn, title, "2026-06-15")
    conn.close()
    assert dup is not None


# ── GET /create/check-duplicate ──────────────────────────────────────────────

def test_check_duplicate_endpoint_reports_none_when_nothing_matches(manager):
    r = manager.get("/create/check-duplicate", params={
        "activity_name": "Never Created This", "event_date": "2026-06-15"})
    assert r.status_code == 200
    assert r.json() == {"duplicate": None, "matches": []}


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


def test_check_duplicate_endpoint_reports_it_across_different_creators(admin, manager):
    # admin creates it, section_manager checks for it later — the endpoint must
    # flag it regardless of who's asking or who made the original.
    title = "Check-Duplicate Endpoint — cross-creator"
    r = _bureau(admin, name=title)
    assert r.status_code == 200, r.text[:600]

    r = manager.get("/create/check-duplicate", params={
        "activity_name": title, "event_date": "2026-06-15"})
    assert r.status_code == 200
    assert r.json()["duplicate"] is not None


def test_save_confirmation_applies_across_creators(admin, manager):
    title = "Cross Creator Confirmation Probe"
    assert _bureau(admin, name=title).status_code == 200
    attempt = _bureau(manager, name=title)
    assert attempt.status_code == 409
    assert title in attempt.text


def test_check_duplicate_endpoint_requires_login(app_mod):
    from starlette.testclient import TestClient
    anon = TestClient(app_mod.app, follow_redirects=False)
    r = anon.get("/create/check-duplicate", params={
        "activity_name": "Whatever", "event_date": "2026-06-15"})
    assert r.status_code in (302, 303, 401, 403)


# ── Save-time confirmation for strong matches ───────────────────────────────

def test_create_requires_confirmation_for_a_genuine_second_activity(manager, db_path):
    title = "Duplicate Warning — legitimately created twice"
    r1 = _bureau(manager, name=title)
    assert r1.status_code == 200, r1.text[:600]
    r2 = _bureau(manager, name=title)
    assert r2.status_code == 409, r2.text[:600]
    assert "Create a separate activity anyway" in r2.text
    assert len(_events(db_path, title)) == 1
    key = re.search(r'name="duplicate_confirm" value="([a-f0-9]+)"', r2.text).group(1)
    r3 = _bureau(manager, name=title, duplicate_confirm=key)
    assert r3.status_code == 200, r3.text[:600]
    assert len(_events(db_path, title)) == 2


def test_fuzzy_title_and_reordered_words_are_suggested(manager):
    title = "Regional Immunization Forum Fuzzy Probe"
    _bureau(manager, name=title)
    r = manager.get("/create/check-duplicate", params={
        "activity_name": "Forum Regional Immunization Fuzzy Probe",
        "event_date": "2026-06-15"})
    assert r.status_code == 200
    assert r.json()["matches"][0]["title"] == title
    assert r.json()["matches"][0]["strength"] == "strong"


def test_multi_day_overlap_is_suggested(manager):
    title = "Multi Day Duplicate Probe"
    _bureau(manager, name=title, end_date="2026-06-17")
    r = manager.get("/create/check-duplicate", params={
        "activity_name": title, "event_date": "2026-06-16"})
    assert r.status_code == 200
    assert r.json()["matches"][0]["title"] == title


def test_weaker_fuzzy_match_warns_without_save_confirmation(manager):
    _bureau(manager, name="Regional Health Planning Session")
    probe = manager.get("/create/check-duplicate", params={
        "activity_name": "Regional Health Plan Session",
        "event_date": "2026-06-15"})
    assert probe.json()["matches"][0]["strength"] == "possible"
    saved = _bureau(manager, name="Regional Health Plan Session")
    assert saved.status_code == 200


def test_confirmation_is_bound_to_activity_details(manager, db_path):
    title = "Confirmation Bound Probe"
    _bureau(manager, name=title)
    prompt = _bureau(manager, name=title)
    key = re.search(r'name="duplicate_confirm" value="([a-f0-9]+)"', prompt.text).group(1)
    changed = _bureau(manager, name=title, end_date="2026-06-16",
                      duplicate_confirm=key)
    assert changed.status_code == 409
    assert len(_events(db_path, title)) == 1


# ── create screen renders the wiring ────────────────────────────────────────

def test_create_screen_renders_duplicate_check_wiring(manager):
    r = manager.get("/create")
    assert r.status_code == 200
    assert 'id="dupWarn"' in r.text
    assert "/create/check-duplicate" in r.text
    assert "checkDuplicate" in r.text
