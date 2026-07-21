"""
Wellness module (DOH DM 2025-0135) — the 2-hour weekly break: entitlement
validation, section-chief approver resolution, the apply→approve→reflect flow
with its gamification side-effects, in-handler RBAC on the chief/admin pages,
and the monitoring register export.
"""
from datetime import date, datetime, time, timedelta

import pytest

import auth
import storage as st
import tzutil as tz
from tests.conftest import _auth_client


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _future_weekday():
    """A weekday comfortably in the future. Claim creation requires a minimum
    lead time before the start (Spot Feedback #73), so tests that file at fixed
    clock times must not use *today* — their time would read as 'in the past'
    whenever the suite runs late in the day."""
    return _next_weekday(tz.today_local() + timedelta(days=3))


def _monday_this_week():
    t = tz.today_local()
    return t - timedelta(days=t.weekday())


@pytest.fixture()
def wellness_org(app_mod):
    """A section with a chief (section_manager account), an employee (viewer
    account, directory-linked) and a loner (viewer account, no directory link).
    Fresh rows per test; wellness tables are wiped so entitlement math and
    dashboards start from zero."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM wellness_reflection")
    conn.execute("DELETE FROM wellness_badge")
    conn.execute("DELETE FROM wellness_claim")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'w-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'W-Test %'")
    conn.execute("DELETE FROM org_unit WHERE path = 'TEST/WELL/WSec'")
    cur = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('Wellness Test Section','WSec','section','TEST/WELL/WSec')")
    unit = cur.lastrowid
    chief_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('W-Test Chief', 1, ?, 'Section Head')", (unit,)).lastrowid
    emp_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id) "
        "VALUES ('W-Test Employee', 1, ?)", (unit,)).lastrowid
    h, salt = "x", "y"          # never logged in via password — cookies are minted
    chief = st.create_admin_user(conn, "w-chief@test.local", h, salt,
                                 "section_manager", rp_id=chief_rp)
    emp = st.create_admin_user(conn, "w-emp@test.local", h, salt,
                               "viewer", rp_id=emp_rp)
    loner = st.create_admin_user(conn, "w-loner@test.local", h, salt, "viewer")
    conn.commit()
    yield {"conn": conn, "unit": unit, "chief": chief, "emp": emp, "loner": loner}
    conn.close()


def _client_for_id(app_mod, uid):
    from starlette.testclient import TestClient
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user_by_id(conn, uid)
    conn.close()
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(
        {"id": u["id"], "username": u["username"], "role": u["role"]}))
    return c


# ---------------------------------------------------------------- entitlement

def test_third_hour_in_a_week_is_rejected(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    st.create_wellness_claim(conn, emp, d, "15:00", "meditation")
    with pytest.raises(ValueError, match="entitlement"):
        st.create_wellness_claim(conn, emp, d, "16:00", "hobby")


def test_two_hour_break_in_one_claim(wellness_org):
    """The DM allows the whole 2-hour weekly entitlement in a single sitting."""
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    cid = st.create_wellness_claim(conn, emp, d, "09:00", "exercise", hours=2)
    ws = st.wellness_week_start(date.fromisoformat(d))
    assert st.wellness_hours_used(conn, emp, ws) == 2
    assert st.get_wellness_claim(conn, cid)["hours"] == 2
    # The full entitlement is spent — no further hour fits that week.
    with pytest.raises(ValueError, match="entitlement"):
        st.create_wellness_claim(conn, emp, d, "15:00", "meditation")


def test_two_hour_claim_rejected_when_only_one_hour_left(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    st.create_wellness_claim(conn, emp, d, "09:00", "exercise")     # 1 hour used
    with pytest.raises(ValueError, match="Only 1 hour left"):
        st.create_wellness_claim(conn, emp, d, "15:00", "meditation", hours=2)


def test_break_length_bounds(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    with pytest.raises(ValueError, match="1 to 2 hours"):
        st.create_wellness_claim(conn, emp, d, "09:00", "exercise", hours=3)
    with pytest.raises(ValueError, match="1 to 2 hours"):
        st.create_wellness_claim(conn, emp, d, "09:00", "exercise", hours=0)


def test_denied_and_cancelled_hours_return_to_the_week(wellness_org):
    conn, emp, chief = wellness_org["conn"], wellness_org["emp"], wellness_org["chief"]
    u_chief = {"id": chief, "username": "w-chief@test.local", "role": "section_manager"}
    d = _future_weekday().isoformat()
    c1 = st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    c2 = st.create_wellness_claim(conn, emp, d, "15:00", "meditation")
    st.decide_wellness_claim(conn, c1, u_chief, "deny", "busy morning")
    st.cancel_wellness_claim(conn, c2, emp)
    ws = st.wellness_week_start(date.fromisoformat(d))
    assert st.wellness_hours_used(conn, emp, ws) == 0
    st.create_wellness_claim(conn, emp, d, "16:00", "hobby")       # fits again


def test_claim_validation_rules(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    with pytest.raises(ValueError):                                 # bad date
        st.create_wellness_claim(conn, emp, "not-a-date", "09:00", "exercise")
    with pytest.raises(ValueError):                                 # bad time
        st.create_wellness_claim(conn, emp, d, "25:99", "exercise")
    with pytest.raises(ValueError):                                 # bad activity
        st.create_wellness_claim(conn, emp, d, "09:00", "smoking")
    with pytest.raises(ValueError):                                 # backdated
        st.create_wellness_claim(
            conn, emp, (tz.today_local() - timedelta(days=8)).isoformat(),
            "09:00", "exercise")
    st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    with pytest.raises(ValueError, match="already have a break"):   # duplicate slot
        st.create_wellness_claim(conn, emp, d, "09:00", "hobby")


def test_break_needs_minimum_lead_time(wellness_org, monkeypatch):
    """Spot Feedback #73: a break must be filed at least
    WELLNESS_MIN_LEAD_MINUTES before it starts. Pin 'now' to a fixed weekday
    morning so the window is deterministic regardless of when the suite runs."""
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    fixed = datetime.combine(_monday_this_week(), time(10, 0))   # a Monday, 10:00
    monkeypatch.setattr(tz, "now_local", lambda: fixed)
    monkeypatch.setattr(tz, "today_local", lambda: fixed.date())
    day = fixed.date().isoformat()
    lead = st.WELLNESS_MIN_LEAD_MINUTES
    # too soon: only (lead - 15) minutes ahead of the start
    soon = (fixed + timedelta(minutes=lead - 15)).strftime("%H:%M")
    with pytest.raises(ValueError, match="minutes before"):
        st.create_wellness_claim(conn, emp, day, soon, "exercise")
    # a start already passed today is caught by the same rule (date-only check
    # used to let it through)
    with pytest.raises(ValueError, match="minutes before"):
        st.create_wellness_claim(conn, emp, day, "09:00", "exercise")
    # comfortably ahead (lead + 60 min) is accepted
    ok = (fixed + timedelta(minutes=lead + 60)).strftime("%H:%M")
    assert st.create_wellness_claim(conn, emp, day, ok, "meditation")


# ---------------------------------------------------------- approver routing

def test_chief_resolved_through_directory(wellness_org):
    conn = wellness_org["conn"]
    assert st.get_wellness_approvers(conn, wellness_org["emp"]) == [wellness_org["chief"]]
    # no directory link -> nobody resolved; admins are the fallback
    assert st.get_wellness_approvers(conn, wellness_org["loner"]) == []
    u_admin = {"id": 0, "role": "admin"}
    assert st.is_wellness_approver(conn, u_admin, wellness_org["loner"])


def test_nobody_decides_their_own_claim(wellness_org):
    conn, chief = wellness_org["conn"], wellness_org["chief"]
    u_chief = {"id": chief, "username": "w-chief@test.local", "role": "section_manager"}
    d = _future_weekday().isoformat()
    own = st.create_wellness_claim(conn, chief, d, "09:00", "exercise")
    assert not st.is_wellness_approver(conn, u_chief, chief)
    with pytest.raises(PermissionError):
        st.decide_wellness_claim(conn, own, u_chief, "approve")
    # the chief's own request lands in the admins' queue instead
    u_admin = {"id": 0, "role": "admin"}
    assert own in [c["id"] for c in st.list_wellness_approvals(conn, u_admin)]


def test_chief_queue_holds_only_their_unit(wellness_org):
    conn, emp, chief, loner = (wellness_org["conn"], wellness_org["emp"],
                               wellness_org["chief"], wellness_org["loner"])
    u_chief = {"id": chief, "username": "w-chief@test.local", "role": "section_manager"}
    d = _future_weekday().isoformat()
    inside = st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    outside = st.create_wellness_claim(conn, loner, d, "09:00", "exercise")
    ids = [c["id"] for c in st.list_wellness_approvals(conn, u_chief)]
    assert inside in ids and outside not in ids


# -------------------------------------------------- escalation up the full chain

@pytest.fixture()
def wellness_chain(app_mod):
    """A full division -> section -> directorate slice with an account at every
    tier, so escalation can be walked end to end (Spot Feedback #76). Crucially
    the Director carries their rank in `position` ('Director IV'), NOT in
    `designation` — mirroring the real directory, where an exact designation
    match found nobody."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)

    def _wipe():
        # SCOPED to this fixture's namespace. The Director tier is searched
        # GLOBALLY (no org filter), so a leaked 'Director IV' account would
        # pollute other files' escalation tests — clean up at BOTH ends.
        conn.execute("DELETE FROM wellness_claim WHERE user_id IN "
                     "(SELECT id FROM admin_user WHERE username LIKE 'wc-%@test.local')")
        conn.execute("DELETE FROM admin_user WHERE username LIKE 'wc-%@test.local'")
        conn.execute("DELETE FROM resource_person WHERE name LIKE 'WC-%'")
        conn.execute("DELETE FROM org_unit WHERE path LIKE 'TC/%' OR path = 'TC'")
        conn.commit()
    _wipe()

    def unit(name, short, level, path):
        return conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (name, short, level, path)).lastrowid

    def person(name, desig, pos, org):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation, position) "
            "VALUES (?,1,?,?,?)", (name, org, desig, pos)).lastrowid

    unit("Test Bureau", "TC", "bureau", "TC")
    u_od = unit("Office of the Director", "OD", "office", "TC/OD")
    u_div = unit("Test Division", "TDIV", "division", "TC/TDIV")
    u_sec = unit("Test Section", "TSEC", "section", "TC/TDIV/TSEC")

    # Director's leadership lives in `position`, designation left blank on purpose.
    rp_dir = person("WC-Director", None, "Director IV", u_od)
    rp_div = person("WC-DivChief", "Division Chief", "Medical Officer V", u_div)
    rp_sec = person("WC-SecHead", "Section Head", "Chief Health Program Officer", u_sec)
    rp_emp = person("WC-Employee", None, "Health Program Officer II", u_sec)

    h, salt = "x", "y"
    mk = lambda uname, role, rp: st.create_admin_user(conn, uname, h, salt, role, rp_id=rp)
    director = mk("wc-dir@test.local", "section_manager", rp_dir)
    divchief = mk("wc-div@test.local", "section_manager", rp_div)
    sechead = mk("wc-sec@test.local", "section_manager", rp_sec)
    emp = mk("wc-emp@test.local", "viewer", rp_emp)
    conn.commit()
    yield {"conn": conn, "director": director, "divchief": divchief,
           "sechead": sechead, "emp": emp, "rp_sec": rp_sec}
    _wipe()
    conn.close()


def test_escalation_walks_each_tier(wellness_chain):
    """staff -> section head -> division chief -> Director, one hop per rank."""
    conn, w = wellness_chain["conn"], wellness_chain
    assert st.get_wellness_approvers(conn, w["emp"]) == [w["sechead"]]
    assert st.get_wellness_approvers(conn, w["sechead"]) == [w["divchief"]]
    # the Director is matched by POSITION ('Director IV'), not designation —
    # the exact-match bug this fix corrects.
    assert st.get_wellness_approvers(conn, w["divchief"]) == [w["director"]]
    # the Director sits at the top: nobody here, admins are the fallback.
    assert st.get_wellness_approvers(conn, w["director"]) == []
    u_admin = {"id": 0, "role": "admin"}
    assert st.is_wellness_approver(conn, u_admin, w["director"])


def test_director_and_chiefs_see_the_queue(wellness_chain):
    """Everyone who can approve SOMEONE reaches the approvals queue — including
    the Director, whose rank is carried in `position`."""
    conn = wellness_chain["conn"]
    for key in ("sechead", "divchief", "director"):
        u = {"id": wellness_chain[key], "role": "section_manager"}
        assert st.user_is_wellness_chief(conn, u), key
    # a plain employee does not
    assert not st.user_is_wellness_chief(
        conn, {"id": wellness_chain["emp"], "role": "viewer"})


def test_title_names_the_seat_even_without_an_account(wellness_chain):
    """The apply-page copy names the org-correct approver as long as that seat is
    filled in the directory — it must not fall back to 'an administrator' just
    because the chief has no app account yet (the reported symptom)."""
    conn, w = wellness_chain["conn"], wellness_chain
    assert st.wellness_approver_title(conn, w["emp"]) == "your section chief"
    assert st.wellness_approver_title(conn, w["sechead"]) == "your division chief"
    assert st.wellness_approver_title(conn, w["divchief"]) == "the Director"
    assert st.wellness_approver_title(conn, w["director"]) == "an administrator"

    # Drop the division chief's ACCOUNT but keep the person in the directory:
    # the section head's copy still reads 'your division chief' (the seat is
    # filled), while the actual claim now escalates to the admin fallback.
    conn.execute("DELETE FROM admin_user WHERE id=?", (w["divchief"],))
    conn.commit()
    assert st.wellness_approver_title(conn, w["sechead"]) == "your division chief"
    assert st.get_wellness_approvers(conn, w["sechead"]) == []


# ------------------------------------------- the full flow + gamification

def test_approve_complete_reflect_awards_points_and_badges(app_mod, wellness_org):
    conn, emp, chief = wellness_org["conn"], wellness_org["emp"], wellness_org["chief"]
    u_chief = {"id": chief, "username": "w-chief@test.local", "role": "section_manager"}
    monday = _monday_this_week().isoformat()     # always a weekday <= today
    # inserted directly (create_wellness_claim only files today-or-later; the
    # completion path is what's under test here)
    ws = st.wellness_week_start(date.fromisoformat(monday))
    cid = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
        " hours, activity, status, created_at) VALUES (?,?,?,?,1,'exercise','pending',?)",
        (emp, ws, monday, "09:00", tz.now_iso())).lastrowid
    conn.commit()
    st.decide_wellness_claim(conn, cid, u_chief, "approve")
    claim, badges = st.complete_wellness_claim(
        conn, cid, emp, 2, 4, "brisk walk", "felt lighter after")
    assert claim["status"] == "completed"
    assert "First break" in badges
    stats = st.wellness_stats(conn, emp)
    # +10 break, +5 reflection, +2 for the 1-week streak
    assert stats["points"] == 17
    assert stats["streak"] == 1
    assert stats["stage"] == 1 and stats["level"] == 1
    assert [b["key"] for b in stats["badges"]] == ["first_break"]
    # a second completed hour that week earns the full-week bonus + badge
    cid2 = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
        " hours, activity, status, created_at) VALUES (?,?,?,?,1,'hobby','approved',?)",
        (emp, ws, monday, "15:00", tz.now_iso())).lastrowid
    conn.commit()
    _, badges2 = st.complete_wellness_claim(conn, cid2, emp, 3, 5, "sketching", None)
    assert "Full week" in badges2
    stats = st.wellness_stats(conn, emp)
    # 2 breaks (20) + 2 reflections (10) + full week (5) + streak 1 (2)
    assert stats["points"] == 37 and stats["level"] == 2


def test_completion_guards(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    cid = st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    with pytest.raises(ValueError, match="approved"):   # still pending
        st.complete_wellness_claim(conn, cid, emp, 3, 4, "walk", None)
    with pytest.raises(ValueError):                     # not yours
        st.complete_wellness_claim(conn, cid, wellness_org["loner"], 3, 4, "walk", None)


# ----------------------------------------------------------------- HTTP layer

def test_http_apply_flow_and_hub(app_mod, wellness_org):
    c = _client_for_id(app_mod, wellness_org["emp"])
    r = c.get("/wellness")
    # the companion now renders via the shared avatar macro (the mascot is the
    # adopted pet); the .avwrap wrapper is its structural marker
    assert r.status_code == 200 and "avwrap" in r.text
    r = c.get("/wellness/apply")
    assert r.status_code == 200
    # Phase 6a: the activity selector is now illustrated cards — inline SVG icons
    # behind the SAME radio inputs (name="activity"), so the POST below is unchanged.
    assert "<svg" in r.text
    assert 'type="radio" name="activity" value="exercise"' in r.text
    # the break-length picker offers both 1- and 2-hour options
    assert 'name="hours" value="1"' in r.text and 'name="hours" value="2"' in r.text
    d = _future_weekday().isoformat()
    # take the whole 2-hour entitlement in a single claim
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                        "activity": "exercise", "note": "jog",
                                        "hours": "2"},
               follow_redirects=False)
    assert r.status_code == 303
    # no hours left this week: the form re-renders with the entitlement error
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "16:00",
                                        "activity": "hobby"})
    assert r.status_code == 400 and "entitlement" in r.text


def test_http_approve_and_reflect(app_mod, wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    monday = _monday_this_week().isoformat()
    ws = st.wellness_week_start(date.fromisoformat(monday))
    cid = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
        " hours, activity, status, created_at) VALUES (?,?,?,?,1,'exercise','pending',?)",
        (emp, ws, monday, "09:00", tz.now_iso())).lastrowid
    conn.commit()
    chief_c = _client_for_id(app_mod, wellness_org["chief"])
    r = chief_c.get("/wellness/approvals")
    assert r.status_code == 200 and "W-Test Employee" in r.text
    r = chief_c.post(f"/wellness/claims/{cid}/decide",
                     data={"action": "approve"}, follow_redirects=False)
    assert r.status_code == 303
    emp_c = _client_for_id(app_mod, emp)
    r = emp_c.get(f"/wellness/claims/{cid}/complete")
    assert r.status_code == 200
    r = emp_c.post(f"/wellness/claims/{cid}/complete",
                   data={"mood_before": "2", "mood_after": "4",
                         "activity_done": "brisk walk", "takeaway": "nice"},
                   follow_redirects=False)
    assert r.status_code == 303 and "cheer=" in r.headers["location"]
    conn2 = st.connect(app_mod.DB)
    assert st.get_wellness_claim(conn2, cid)["status"] == "completed"
    conn2.close()


def test_chief_pages_are_gated(app_mod, wellness_org, viewer, admin):
    # a viewer with no chief designation: hub yes, chief pages no
    assert viewer.get("/wellness").status_code == 200
    for path in ("/wellness/approvals", "/wellness/dashboard", "/wellness/export.csv"):
        assert viewer.get(path).status_code == 403, path
    # admins and directory-resolved chiefs both pass
    chief_c = _client_for_id(app_mod, wellness_org["chief"])
    for c in (admin, chief_c):
        for path in ("/wellness/approvals", "/wellness/dashboard"):
            assert c.get(path).status_code == 200, path
    # deciding someone else's claim from a non-approver account bounces
    d = _future_weekday().isoformat()
    conn = wellness_org["conn"]
    cid = st.create_wellness_claim(conn, wellness_org["emp"], d, "11:00", "exercise")
    loner_c = _client_for_id(app_mod, wellness_org["loner"])
    assert loner_c.post(f"/wellness/claims/{cid}/decide",
                        data={"action": "approve"}).status_code == 403


def test_register_export(app_mod, wellness_org, admin):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    monday = _monday_this_week().isoformat()
    ws = st.wellness_week_start(date.fromisoformat(monday))
    cid = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
        " hours, activity, status, created_at) VALUES (?,?,?,?,1,'meditation','approved',?)",
        (emp, ws, monday, "13:00", tz.now_iso())).lastrowid
    conn.commit()
    st.complete_wellness_claim(conn, cid, emp, 1, 5, "breathing exercises", "calm")
    r = admin.get("/wellness/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    head, *rows = r.text.strip().splitlines()
    for col in ("Week of", "Section", "Employee", "Date", "Hours", "Activity",
                "Status", "Approved by", "Reflection done", "Mood before"):
        assert col in head
    ours = [x for x in rows if "W-Test Employee" in x]
    assert ours and "Meditation" in ours[0] and "yes" in ours[0]
    # the dashboard shows the same week
    r = admin.get(f"/wellness/dashboard?week={monday}")
    assert r.status_code == 200 and "WSec" in r.text


# ---------------------------------------- "Others" activity needs a specification

def test_other_activity_requires_and_stores_specification(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _future_weekday().isoformat()
    # "other" with no specification is rejected
    with pytest.raises(ValueError, match="Others"):
        st.create_wellness_claim(conn, emp, d, "09:00", "other")
    with pytest.raises(ValueError, match="Others"):
        st.create_wellness_claim(conn, emp, d, "09:00", "other", activity_other="  ")
    # with a specification it is stored and surfaced in the label
    cid = st.create_wellness_claim(conn, emp, d, "10:00", "other",
                                   activity_other="community gardening")
    claim = st.get_wellness_claim(conn, cid)
    assert claim["activity_other"] == "community gardening"
    assert claim["activity_label"] == "Others — community gardening"
    # a non-"other" activity never keeps a stray specification
    cid2 = st.create_wellness_claim(conn, emp, d, "11:00", "exercise",
                                    activity_other="ignored")
    assert st.get_wellness_claim(conn, cid2)["activity_other"] is None


# ---------------------------------------------- rolling 4-week request window

def test_request_allowed_across_the_month(wellness_org):
    """A break can be filed for a future week within the window; each week keeps
    its own 2-hour cap, independent of the current week."""
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    next_week = _next_weekday(_monday_this_week() + timedelta(days=7))
    d = next_week.isoformat()
    cid = st.create_wellness_claim(conn, emp, d, "09:00", "exercise", hours=2)
    ws = st.wellness_week_start(next_week)
    assert st.wellness_hours_used(conn, emp, ws) == 2
    # the current week is untouched by next week's claim
    assert st.wellness_hours_used(conn, emp, st.wellness_week_start()) == 0


def test_request_beyond_window_is_rejected(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    # a workday past the last week of the rolling window
    beyond = _next_weekday(_monday_this_week()
                           + timedelta(days=st.WELLNESS_WINDOW_WEEKS * 7))
    assert beyond > st.wellness_window_last_date()
    with pytest.raises(ValueError, match="weeks ahead"):
        st.create_wellness_claim(conn, emp, beyond.isoformat(), "09:00", "exercise")


# ------------------------------------------- richer post-activity report fields

def test_completion_records_post_activity_fields(app_mod, wellness_org):
    conn, emp, chief = wellness_org["conn"], wellness_org["emp"], wellness_org["chief"]
    u_chief = {"id": chief, "username": "w-chief@test.local", "role": "section_manager"}
    monday = _monday_this_week().isoformat()
    ws = st.wellness_week_start(date.fromisoformat(monday))
    cid = conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
        " hours, activity, status, created_at) VALUES (?,?,?,?,1,'exercise','approved',?)",
        (emp, ws, monday, "09:00", tz.now_iso())).lastrowid
    conn.commit()
    st.complete_wellness_claim(
        conn, cid, emp, 2, 4, "brisk walk", "felt lighter",
        usefulness="5", felt_refreshed="1", managed_stress="0",
        focus_impact="improved", suggestions="more shaded areas")
    claim = st.get_wellness_claim(conn, cid)
    assert claim["usefulness"] == 5
    assert claim["felt_refreshed"] == 1 and claim["managed_stress"] == 0
    assert claim["focus_impact"] == "improved"
    assert claim["suggestions"] == "more shaded areas"


def test_completion_validates_new_fields(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    monday = _monday_this_week().isoformat()
    ws = st.wellness_week_start(date.fromisoformat(monday))

    def _fresh(start):
        return conn.execute(
            "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
            " hours, activity, status, created_at) VALUES (?,?,?,?,1,'exercise','approved',?)",
            (emp, ws, monday, start, tz.now_iso())).lastrowid

    c1 = _fresh("09:00")
    with pytest.raises(ValueError, match="Usefulness"):
        st.complete_wellness_claim(conn, c1, emp, 2, 4, "walk", None, usefulness="9")
    c2 = _fresh("10:00")
    with pytest.raises(ValueError, match="focus"):
        st.complete_wellness_claim(conn, c2, emp, 2, 4, "walk", None, focus_impact="great")
    # the new fields are optional — the legacy 6-arg call still works
    c3 = _fresh("11:00")
    st.complete_wellness_claim(conn, c3, emp, 2, 4, "walk", None)
    assert st.get_wellness_claim(conn, c3)["status"] == "completed"


# --------------------------------------------------- approver named, not generic

def test_approver_name_resolves_seat_holder(wellness_chain):
    conn, w = wellness_chain["conn"], wellness_chain
    # staff -> section chief and section chief -> division chief are org-scoped,
    # so they name exactly the one seat holder in that unit.
    assert st.wellness_approver_name(conn, w["emp"]) == "WC-SecHead"
    assert st.wellness_approver_name(conn, w["sechead"]) == "WC-DivChief"
    # division chief -> the Director is searched bureau-wide (the top tier has no
    # org scope), so just assert our Director is named among them.
    assert "WC-Director" in (st.wellness_approver_name(conn, w["divchief"]) or "")
    # the Director sits at the top — no named approver, callers fall back to title
    assert st.wellness_approver_name(conn, w["director"]) is None


def test_apply_page_names_the_approver(app_mod, wellness_org):
    c = _client_for_id(app_mod, wellness_org["emp"])
    r = c.get("/wellness/apply")
    assert r.status_code == 200
    # the section chief's actual name appears on the submit button
    assert "W-Test Chief" in r.text
    # the "Others" specify field is present for progressive reveal
    assert 'name="activity_other"' in r.text


def test_home_shows_the_two_doors(viewer):
    r = viewer.get("/")
    assert r.status_code == 200
    assert "Wellness — my 2-hour break" in r.text
    assert 'href="/wellness"' in r.text


# ---------------------------------------------- monthly register (PDF) --------

def _seed_availed(conn, uid, chief, break_date, start_time, status, activity="exercise"):
    """Insert a break in a known state, decided by `chief` — the register only
    lists availed (approved/completed) breaks, so tests need real decided rows."""
    ws = st.wellness_week_start(date.fromisoformat(break_date))
    conn.execute(
        "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
        " hours, activity, status, decided_by, decided_at, created_at)"
        " VALUES (?,?,?,?,1,?,?,?,?,?)",
        (uid, ws, break_date, start_time, activity, status, chief,
         tz.now_iso(), tz.now_iso()))
    conn.commit()


def test_availed_months_and_person_month(wellness_org):
    import wellness_register as wreg
    conn, emp, chief = wellness_org["conn"], wellness_org["emp"], wellness_org["chief"]
    _seed_availed(conn, emp, chief, "2026-03-03", "10:00", "completed")
    _seed_availed(conn, emp, chief, "2026-03-17", "14:00", "approved", activity="hobby")
    _seed_availed(conn, emp, chief, "2026-04-07", "09:00", "completed")
    # a denied break must NOT count as availed
    _seed_availed(conn, emp, chief, "2026-03-24", "11:00", "denied")

    months = st.wellness_availed_months(conn, emp)
    yms = [m["ym"] for m in months]
    assert yms == ["2026-04", "2026-03"]          # newest first
    mar = next(m for m in months if m["ym"] == "2026-03")
    assert mar["count"] == 2 and mar["label"] == "March 2026"

    data = st.wellness_person_month(conn, emp, 2026, 3)
    assert data["name"] == "W-Test Employee" and data["office"] == "WSec"
    assert len(data["entries"]) == 2              # the denied one is excluded
    assert {e["date"] for e in data["entries"]} == {"2026-03-03", "2026-03-17"}
    assert all(e["approver"] == "W-Test Chief" for e in data["entries"])

    pdf = wreg.render_month_pdf(data)
    assert pdf[:4] == b"%PDF"
    assert wreg.filename(data) == "Wellness-Register-Employee-2026-03.pdf"


def test_register_pdf_download_and_hub_control(app_mod, wellness_org):
    conn, emp, chief = wellness_org["conn"], wellness_org["emp"], wellness_org["chief"]
    _seed_availed(conn, emp, chief, "2026-03-10", "10:00", "completed")
    c = _client_for_id(app_mod, emp)

    # the hub offers the monthly-register download once a break is availed
    r = c.get("/wellness")
    assert r.status_code == 200
    assert "/wellness/register.pdf" in r.text and "March 2026" in r.text

    # a real month yields a PDF attachment
    r = c.get("/wellness/register.pdf?month=2026-03")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "Wellness-Register-Employee-2026-03.pdf" in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"

    # a month with nothing availed bounces back to the hub with a message
    r = c.get("/wellness/register.pdf?month=2025-01", follow_redirects=False)
    assert r.status_code == 303 and "err=" in r.headers["location"]


def test_register_pdf_is_self_service_only(app_mod, wellness_org):
    # a viewer with no availed breaks still reaches the route (no chief gate),
    # they just get redirected because there is nothing to render
    c = _client_for_id(app_mod, wellness_org["loner"])
    r = c.get("/wellness/register.pdf", follow_redirects=False)
    assert r.status_code == 303
