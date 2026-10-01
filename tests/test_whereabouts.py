"""Weekly whereabouts — the Monday "where will you be this week?" report.

Storage layer + the scheduled email job run against a throwaway DB (same style
as test_send_reminders.py); the one-click link and signed-in form go through
the HTTP client."""
from __future__ import annotations
from datetime import date

import pytest

import auth
import mailer
import send_reminders as sr
import storage as st
import tzutil as tz
from conftest import in_the_directory

MONDAY = date(2026, 9, 21)          # period 2026-09-16 (Sep 16-30), open to file until 9/11
PERIOD = "2026-09-16"
WED = "2026-09-23"


def _today(monkeypatch, d):
    monkeypatch.setattr(tz, "today_local", lambda: d)


@pytest.fixture()
def org(tmp_path, monkeypatch):
    conn = st.connect(str(tmp_path / "wb.db"))
    st.init_db(conn)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('WB Section','WBS','section','TEST/WB')").lastrowid

    def person(label):
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES (?,1,?)",
            (f"WB {label}", unit)).lastrowid
        return st.create_admin_user(conn, f"wb-{label.lower()}@test.local", "x", "y",
                                    "viewer", rp_id=rp)
    wfh, plain = person("Wfh"), person("Plain")
    loner = st.create_admin_user(conn, "wb-loner@test.local", "x", "y", "viewer")
    conn.commit()
    _today(monkeypatch, date(2026, 9, 7))
    st.create_work_arrangement(conn, wfh, PERIOD, "WFH", weekday=2)   # Wednesdays
    conn.commit()
    _today(monkeypatch, MONDAY)
    return {"conn": conn, "wfh": wfh, "plain": plain, "loner": loner}


@pytest.fixture()
def sent(monkeypatch):
    calls = []

    def _fake(to, subject, body, html=None):
        calls.append({"to": to, "subject": subject, "body": body})
        return {"sent": True, "detail": "ok"}
    monkeypatch.setattr(mailer, "send", _fake)
    return calls


# ------------------------------------------------------------- plotting ---

def test_week_is_plotted_from_the_filed_arrangement(org):
    days = st.whereabouts_week(org["conn"], org["wfh"], MONDAY)
    assert [d["choice"] for d in days] == ["office", "office", "awa", "office", "office"]
    assert days[2]["awa_label"] == "Work from home (AWA)"
    assert days[0]["awa_label"] is None
    assert st.whereabouts_choice_label(days[2]) == "Work from home (AWA)"
    # someone with no filing is simply expected in the office
    plain = st.whereabouts_week(org["conn"], org["plain"], MONDAY)
    assert {d["choice"] for d in plain} == {"office"}


# --------------------------------------------------------------- saving ---

def test_save_overrides_and_awa_is_refused_where_nothing_to_follow(org):
    c = org["conn"]
    n = st.save_whereabouts_week(c, org["plain"], MONDAY, {
        "2026-09-21": ("field", "Brgy. Poblacion"),
        "2026-09-22": ("leave", "dentist"),          # leave never keeps a reason
        "2026-09-23": ("awa", ""),                    # no AWA on file -> office
        "2026-09-24": ("bogus", ""),                  # ignored
        "2026-09-26": ("office", ""),                 # a Saturday: not a day of the week
    })
    assert n == 3
    d = {x["iso"]: x for x in st.whereabouts_week(c, org["plain"], MONDAY)}
    assert (d["2026-09-21"]["choice"], d["2026-09-21"]["note"]) == ("field", "Brgy. Poblacion")
    assert (d["2026-09-22"]["choice"], d["2026-09-22"]["note"]) == ("leave", "")
    assert d["2026-09-23"]["choice"] == "office"
    assert st.whereabouts_week_submitted(c, org["plain"], MONDAY)
    # re-submitting overwrites rather than duplicating
    st.save_whereabouts_week(c, org["plain"], MONDAY, {"2026-09-21": ("office", "")})
    assert c.execute("SELECT COUNT(*) FROM whereabouts WHERE user_id=?",
                     (org["plain"],)).fetchone()[0] == 3


def test_only_this_and_next_week_can_be_reported(org):
    st.save_whereabouts_week(org["conn"], org["plain"], date(2026, 9, 28),
                             {"2026-09-28": ("office", "")})          # next week: fine
    for monday in (date(2026, 9, 14), date(2026, 10, 5), date(2026, 9, 22)):
        with pytest.raises(ValueError):
            st.save_whereabouts_week(org["conn"], org["plain"], monday, {})


# ------------------------------------------------------- Who's in override ---

def test_reported_status_overrides_the_schedule_on_whos_in(org):
    c = org["conn"]
    st.save_whereabouts_week(c, org["plain"], MONDAY, {
        "2026-09-21": ("field", "Site visit"), "2026-09-22": ("leave", "")})
    st.save_whereabouts_week(c, org["wfh"], MONDAY, {WED: ("office", "")})

    mon = st.work_arrangement_day(c, date(2026, 9, 21))
    names = lambda g: {p["name"] for p in mon["groups"][g]}
    assert "WB Plain" in names("field") and "WB Plain" not in names("onsite")
    field_row = next(p for p in mon["groups"]["field"] if p["name"] == "WB Plain")
    assert field_row["remarks"] == "Site visit" and field_row["reported"]
    assert mon["counts"]["field"] == 1
    assert "WB Plain" in {p["name"] for p in
                          st.work_arrangement_day(c, date(2026, 9, 22))["groups"]["leave"]}

    # the WFH person reported Office on their WFH Wednesday: reported wins
    wed = st.work_arrangement_day(c, date(2026, 9, 23))
    assert "WB Wfh" in names_of(wed, "onsite") and "WB Wfh" not in names_of(wed, "wfh")
    # unreported days still follow the filing
    thu = st.work_arrangement_day(c, date(2026, 9, 24))
    assert "WB Plain" in names_of(thu, "unfiled")


def names_of(day, group):
    return {p["name"] for p in day["groups"][group]}


def test_awa_choice_keeps_the_derived_wfh_state(org):
    st.save_whereabouts_week(org["conn"], org["wfh"], MONDAY, {WED: ("awa", "")})
    wed = st.work_arrangement_day(org["conn"], date(2026, 9, 23))
    assert "WB Wfh" in names_of(wed, "wfh")


# ---------------------------------------------------------------- token ---

def test_token_round_trip_expiry_and_purpose():
    t = auth.make_whereabouts_token(7, "2026-09-21", issued_at=1000)
    assert auth.verify_whereabouts_token(t, now=1000 + 60) == (7, "2026-09-21")
    assert auth.verify_whereabouts_token(t, now=1000 + 11 * 86400) == (None, None)
    assert auth.verify_whereabouts_token(t + "x") == (None, None)
    assert auth.verify_whereabouts_token(auth.make_wellness_decide_token(1, 7)) == (None, None)
    assert auth.verify_whereabouts_token("") == (None, None)


# ------------------------------------------------------------------ job ---

def test_job_emails_linked_staff_once_per_week(org, sent):
    c = org["conn"]
    n = sr.send_whereabouts_weekly(c, "https://css.example")
    assert n == 2
    assert {s["to"] for s in sent} == {"wb-wfh@test.local", "wb-plain@test.local"}
    wfh_mail = next(s for s in sent if s["to"] == "wb-wfh@test.local")
    assert "Work from home (AWA)" in wfh_mail["body"]
    assert "https://css.example/whereabouts/week?token=" in wfh_mail["body"]
    # the daily sweep running again, or a manual re-run, sends nothing new
    assert sr.send_whereabouts_weekly(c, "https://css.example") == 0
    assert len(sent) == 2


def test_job_runs_on_its_weekday_with_one_day_of_catch_up(org, sent, monkeypatch):
    c = org["conn"]
    _today(monkeypatch, date(2026, 9, 23))                      # Wednesday: too late
    assert sr.send_whereabouts_weekly(c, "https://x") == 0
    _today(monkeypatch, date(2026, 9, 22))                      # Tuesday: catch-up
    assert sr.send_whereabouts_weekly(c, "https://x") == 2
    _today(monkeypatch, date(2026, 9, 26))                      # weekend
    assert sr.send_whereabouts_weekly(c, "https://x") == 0


def test_failed_send_is_retried_not_recorded(org, monkeypatch):
    monkeypatch.setattr(mailer, "send", lambda *a, **k: {"sent": False, "detail": "boom"})
    c = org["conn"]
    sr.send_whereabouts_weekly(c, "https://x")
    assert len(st.whereabouts_recipients(c, MONDAY)) == 2       # still owed


def test_dry_run_sends_and_records_nothing(org, sent):
    assert sr.send_whereabouts_weekly(org["conn"], "https://x", dry_run=True) == 2
    assert sent == [] and len(st.whereabouts_recipients(org["conn"], MONDAY)) == 2


def test_job_is_switchable_in_admin_email(org):
    assert "whereabouts" in sr._ALL_JOBS
    assert sr.JOB_FEATURE["whereabouts"] in mailer.FEATURES


# ----------------------------------------------------------------- HTTP ---

def test_one_click_link_shows_and_saves_the_week(app_mod, client, monkeypatch):
    monday = st.whereabouts_week_start()
    with in_the_directory(app_mod, "viewer@test.local"):
        conn = st.connect(app_mod.DB)
        uid = st.get_admin_user(conn, "viewer@test.local")["id"]
        conn.close()
        token = auth.make_whereabouts_token(uid, monday.isoformat())
        r = client.get(f"/whereabouts/week?token={token}")
        assert r.status_code == 200 and "Where will you be this week?" in r.text
        tue = st.whereabouts_week_days(monday)[1].isoformat()
        r = client.post("/whereabouts/week", content=(
            f"token={token}&s_{tue}=field&n_{tue}=Calabarzon+visit"),
            headers={"content-type": "application/x-www-form-urlencoded"})
        assert r.status_code == 200 and "Saved" in r.text
        conn = st.connect(app_mod.DB)
        row = conn.execute("SELECT status, note FROM whereabouts WHERE user_id=? AND day=?",
                           (uid, tue)).fetchone()
        conn.execute("DELETE FROM whereabouts WHERE user_id=?", (uid,))
        conn.execute("DELETE FROM whereabouts_week WHERE user_id=?", (uid,))
        conn.commit(); conn.close()
        assert tuple(row) == ("field", "Calabarzon visit")


def test_bad_or_expired_link_is_refused(client):
    assert client.get("/whereabouts/week?token=nope").status_code == 400
    old = auth.make_whereabouts_token(1, "2026-09-21", issued_at=1)
    assert client.get(f"/whereabouts/week?token={old}").status_code == 400
    assert client.post("/whereabouts/week", content="token=nope").status_code == 400


def test_signed_in_form_requires_login_and_renders(client, viewer):
    assert client.get("/work-arrangement/week", follow_redirects=False).status_code in (302, 303, 401)
    r = viewer.get("/work-arrangement/week")
    assert r.status_code == 200 and "Where will you be this week?" in r.text
    assert viewer.get("/work-arrangement/week?week=garbage").status_code == 200
    assert viewer.get("/work-arrangement/day").status_code == 200


# --------------------------------------------------------------- mailer ---

def test_message_lists_every_day_and_the_link():
    days = [("Monday, October 5", "Office"), ("Wednesday, October 7", "Work from home (AWA)")]
    subj, body, html = mailer.whereabouts_week_message("Juan", "October 5-9, 2026", days, "https://l")
    assert "October 5-9, 2026" in subj
    assert "Work from home (AWA)" in body and "https://l" in body
    assert "Work from home (AWA)" in html and 'href="https://l"' in html


# ------------------------------------------- nudge, roll-up, undeclared ---

@pytest.fixture()
def chiefed(org):
    """The two staff plus a section chief who approves for them."""
    c = org["conn"]
    unit = c.execute("SELECT id FROM org_unit WHERE path='TEST/WB'").fetchone()[0]
    rp = c.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
                   "VALUES ('WB Chief',1,?,'Section Head')", (unit,)).lastrowid
    org["chief"] = st.create_admin_user(c, "wb-chief@test.local", "x", "y",
                                        "section_manager", rp_id=rp)
    c.commit()
    return org


def test_nudge_goes_next_day_to_non_responders_once(org, sent, monkeypatch):
    c = org["conn"]
    sr.send_whereabouts_weekly(c, "https://x")                  # Monday
    st.save_whereabouts_week(c, org["plain"], MONDAY, {})       # no entries: not a submit
    st.save_whereabouts_week(c, org["wfh"], MONDAY, {WED: ("awa", "")})   # wfh responds
    sent.clear()
    assert sr.nudge_whereabouts(c, "https://x") == 0            # same day as the email
    _today(monkeypatch, date(2026, 9, 22))
    assert sr.nudge_whereabouts(c, "https://x") == 1
    assert sent[0]["to"] == "wb-plain@test.local"
    assert sr.nudge_whereabouts(c, "https://x") == 0            # once only


def test_catch_up_monday_email_is_not_nudged_the_same_day(org, sent, monkeypatch):
    _today(monkeypatch, date(2026, 9, 22))                      # email goes out Tuesday
    sr.send_whereabouts_weekly(c := org["conn"], "https://x")
    sent.clear()
    assert sr.nudge_whereabouts(c, "https://x") == 0


def test_rollup_tells_the_chief_who_is_undeclared(chiefed, sent, monkeypatch):
    c = chiefed["conn"]
    sr.send_whereabouts_weekly(c, "https://x")
    st.save_whereabouts_week(c, chiefed["wfh"], MONDAY, {WED: ("awa", "")})
    sent.clear()
    _today(monkeypatch, date(2026, 9, 22))                      # Tuesday
    assert sr.send_whereabouts_rollup(c, "https://x") == 1
    mail = sent[0]
    assert mail["to"] == "wb-chief@test.local"
    assert "WB Plain" in mail["body"] and "WB Wfh" not in mail["body"]
    assert sr.send_whereabouts_rollup(c, "https://x") == 0      # once per chief per week
    _today(monkeypatch, date(2026, 9, 21))
    assert sr.send_whereabouts_rollup(c, "https://x") == 0      # not its day


def test_rollup_silent_when_everyone_reported(chiefed, sent, monkeypatch):
    c = chiefed["conn"]
    sr.send_whereabouts_weekly(c, "https://x")
    for k in ("wfh", "plain"):
        st.save_whereabouts_week(c, chiefed[k], MONDAY, {WED: ("office", "")})
    _today(monkeypatch, date(2026, 9, 22))
    assert sr.send_whereabouts_rollup(c, "https://x") == 0


def test_rollup_skips_a_same_day_catch_up_send(chiefed, sent, monkeypatch):
    _today(monkeypatch, date(2026, 9, 22))                      # email goes out Tuesday
    sr.send_whereabouts_weekly(chiefed["conn"], "https://x")
    assert sr.send_whereabouts_rollup(chiefed["conn"], "https://x") == 0


def test_undeclared_is_marked_only_once_people_were_asked(org, sent):
    c = org["conn"]
    d = st.work_arrangement_day(c, date(2026, 9, 22))
    assert d["undeclared"] == 0 and not d["wb_tracked"]         # nobody asked yet
    sr.send_whereabouts_weekly(c, "https://x")
    st.save_whereabouts_week(c, org["plain"], MONDAY, {"2026-09-22": ("office", "")})
    d = st.work_arrangement_day(c, date(2026, 9, 22))
    undecl = {p["name"] for g in d["groups"].values() for p in g if p.get("undeclared")}
    assert d["wb_tracked"] and undecl == {"WB Wfh"}
    assert d["undeclared"] == 1


def test_new_jobs_are_registered_and_previewable():
    for j in ("whereabouts_nudge", "whereabouts_rollup"):
        assert j in sr._ALL_JOBS and mailer.preview(sr.JOB_FEATURE[j])
