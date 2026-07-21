"""
Wellness module (DOH DM 2025-0135) — the 2-hour weekly break: entitlement
validation, section-chief approver resolution, the apply→approve→reflect flow
with its gamification side-effects, in-handler RBAC on the chief/admin pages,
and the monitoring register export.
"""
from datetime import date, timedelta

import pytest

import auth
import storage as st
import tzutil as tz
from tests.conftest import _auth_client


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


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
    d = _next_weekday(tz.today_local()).isoformat()
    st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    st.create_wellness_claim(conn, emp, d, "15:00", "meditation")
    with pytest.raises(ValueError, match="entitlement"):
        st.create_wellness_claim(conn, emp, d, "16:00", "hobby")


def test_denied_and_cancelled_hours_return_to_the_week(wellness_org):
    conn, emp, chief = wellness_org["conn"], wellness_org["emp"], wellness_org["chief"]
    u_chief = {"id": chief, "username": "w-chief@test.local", "role": "section_manager"}
    d = _next_weekday(tz.today_local()).isoformat()
    c1 = st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    c2 = st.create_wellness_claim(conn, emp, d, "15:00", "meditation")
    st.decide_wellness_claim(conn, c1, u_chief, "deny", "busy morning")
    st.cancel_wellness_claim(conn, c2, emp)
    ws = st.wellness_week_start(date.fromisoformat(d))
    assert st.wellness_hours_used(conn, emp, ws) == 0
    st.create_wellness_claim(conn, emp, d, "16:00", "hobby")       # fits again


def test_claim_validation_rules(wellness_org):
    conn, emp = wellness_org["conn"], wellness_org["emp"]
    d = _next_weekday(tz.today_local()).isoformat()
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
    d = _next_weekday(tz.today_local()).isoformat()
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
    d = _next_weekday(tz.today_local()).isoformat()
    inside = st.create_wellness_claim(conn, emp, d, "09:00", "exercise")
    outside = st.create_wellness_claim(conn, loner, d, "09:00", "exercise")
    ids = [c["id"] for c in st.list_wellness_approvals(conn, u_chief)]
    assert inside in ids and outside not in ids


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
    d = _next_weekday(tz.today_local()).isoformat()
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
    d = _next_weekday(tz.today_local()).isoformat()
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                        "activity": "exercise", "note": "jog"},
               follow_redirects=False)
    assert r.status_code == 303
    c.post("/wellness/apply", data={"break_date": d, "start_time": "14:00",
                                    "activity": "meditation"}, follow_redirects=False)
    # third hour that week: the form re-renders with the entitlement error
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
    d = _next_weekday(tz.today_local()).isoformat()
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


def test_home_shows_the_two_doors(viewer):
    r = viewer.get("/")
    assert r.status_code == 200
    assert "Wellness — my 2-hour break" in r.text
    assert 'href="/wellness"' in r.text
