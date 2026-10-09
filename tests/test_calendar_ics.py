"""iCalendar output: the writer, the per-item download, the attachments and the personal feed
(office calendar G4)."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import calendar_ics as ics
import mailer
import office_calendar as oc
import send_reminders as sr
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)


def unfold(text):
    return text.replace("\r\n ", "").split("\r\n")


def props(text):
    """[(NAME, params, value)] of the unfolded lines, for structural assertions."""
    out = []
    for line in unfold(text):
        if not line:
            continue
        head, _, value = line.partition(":")
        name, _, params = head.partition(";")
        out.append((name, params, value))
    return out


EV = {"uid": "abc123", "sequence": 3, "title": "Planning, Q4; \"draft\"", "status": "confirmed",
      "start": "2026-10-14", "end": "2026-10-14", "start_time": "09:00", "end_time": "10:30",
      "venue": "Room 5", "url": "https://x.test/e/1", "description": "Line one\nLine two",
      "tags": ["PK", "BHW"], "stamp": "2026-10-09T08:00:00"}


# ------------------------------------------------------------- the writer ---

def test_text_escaping():
    assert ics.escape_text("a;b,c\\d\ne\r\nf") == r"a\;b\,c\\d\ne\nf"
    assert ics.escape_text(None) == ""


def test_folding_is_at_75_octets_and_never_splits_a_character():
    for text in ("x" * 200, "é" * 120, "日本語の予定" * 30, "🎂" * 40, "a" + "é" * 74):
        folded = ics.fold("SUMMARY:" + text)
        for line in folded.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75
        for line in folded.split("\r\n")[1:]:
            assert line.startswith(" ")
        assert folded.replace("\r\n ", "") == "SUMMARY:" + text                       # unfolds back exactly
    assert ics.fold("short") == "short"


def test_a_timed_event():
    t = ics.vevent(EV)
    p = {(n, v) for n, _pa, v in props(t)}
    assert ("UID", "abc123") in p and ("SEQUENCE", "3") in p and ("STATUS", "CONFIRMED") in p
    assert ("DTSTART", "20261014T090000") in p and ("DTEND", "20261014T103000") in p
    assert "DTSTART;TZID=Asia/Manila:20261014T090000" in unfold(t)
    assert ("DTSTAMP", "20261009T000000Z") in p                                      # Manila 08:00 = 00:00 UTC
    assert ("SUMMARY", r'Planning\, Q4\; "draft"') in p and ("LOCATION", "Room 5") in p
    assert ("DESCRIPTION", "Line one\\nLine two") in p and ("CATEGORIES", "PK,BHW") in p
    assert "TRANSP:OPAQUE" in unfold(t)


def test_all_day_events_use_date_values_and_an_exclusive_end():
    t = ics.vevent({**EV, "start_time": None, "end_time": None, "end": "2026-10-16"})
    lines = unfold(t)
    assert "DTSTART;VALUE=DATE:20261014" in lines and "DTEND;VALUE=DATE:20261017" in lines
    one = unfold(ics.vevent({**EV, "start_time": None, "end_time": None}))
    assert "DTEND;VALUE=DATE:20261015" in one


def test_a_start_time_with_no_end_runs_an_hour_and_a_multi_day_untimed_end_is_all_day():
    assert "DTEND;TZID=Asia/Manila:20261014T100000" in unfold(ics.vevent({**EV, "end_time": None}))
    span = unfold(ics.vevent({**EV, "end_time": None, "end": "2026-10-16"}))
    assert "DTSTART;VALUE=DATE:20261014" in span                                      # not a 3-day-long meeting at 9


@pytest.mark.parametrize("status, want, title", [("tentative", "TENTATIVE", "T"), ("cancelled", "CANCELLED", "T"),
                                                  ("postponed", "TENTATIVE", "[Postponed] T")])
def test_statuses(status, want, title):
    t = ics.vevent({**EV, "status": status, "title": "T"})
    assert f"STATUS:{want}" in unfold(t) and f"SUMMARY:{title}" in unfold(t)


def test_a_complete_calendar_is_well_formed():
    text = ics.vcalendar([EV, {**EV, "uid": "second"}], name="BLHSD, calendar", method="PUBLISH")
    assert text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    names = [n for n, _p, _v in props(text)]
    stack = []
    for n, _pa, v in props(text):
        if n == "BEGIN":
            stack.append(v)
        elif n == "END":
            assert stack.pop() == v
    assert not stack
    assert names.count("VEVENT") == 0 and [v for n, _p, v in props(text) if n == "BEGIN"].count("VEVENT") == 2
    assert ("VERSION", "", "2.0") in props(text) and ("METHOD", "", "PUBLISH") in props(text)
    assert ("TZID", "", "Asia/Manila") in props(text) and ("TZOFFSETTO", "", "+0800") in props(text)
    assert ("X-WR-CALNAME", "", "BLHSD\\, calendar") in props(text)
    assert "METHOD" not in [n for n, _p, _v in props(ics.vcalendar([EV]))]               # a feed has no METHOD


def test_a_golden_event():
    got = ics.vevent({"uid": "u1", "sequence": 0, "title": "Banner day", "status": "confirmed",
                      "start": "2026-10-14", "end": "2026-10-14", "stamp": "2026-10-09T08:00:00"})
    assert got.split("\r\n") == ["BEGIN:VEVENT", "UID:u1", "DTSTAMP:20261009T000000Z", "SEQUENCE:0",
                                 "DTSTART;VALUE=DATE:20261014", "DTEND;VALUE=DATE:20261015",
                                 "SUMMARY:Banner day", "STATUS:CONFIRMED", "TRANSP:OPAQUE", "END:VEVENT"]


def test_birthdays_repeat_yearly_and_carry_no_birth_year():
    b = ics.vevent(ics.birthday_event(7, "Riza", 3, 9, 2026))
    assert "RRULE:FREQ=YEARLY" in unfold(b) and "DTSTART;VALUE=DATE:20260309" in unfold(b)
    assert "UID:birthday-7@officeconnect" in unfold(b) and "TRANSP:TRANSPARENT" in unfold(b)
    leap = unfold(ics.vevent(ics.birthday_event(8, "Tek", 2, 29, 2027)))
    assert "RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1" in leap and "DTSTART;VALUE=DATE:20270228" in leap
    assert "DTSTART;VALUE=DATE:20280229" in unfold(ics.vevent(ics.birthday_event(8, "Tek", 2, 29, 2028)))


def test_an_entry_keeps_its_uid_and_sequence_across_edits(world):                              # noqa: F811
    c = world["conn"]
    e = st.cal_create(c, "Meeting", "2026-10-20", by="x@x", people=[(world["s1"]["id"], "attending")])
    first = ics.entry_event(st.cal_get(c, e), "https://x.test")
    st.cal_update(c, e, by="x@x", start_time="14:00", end_time="15:00")
    second = ics.entry_event(st.cal_get(c, e), "https://x.test")
    assert first["uid"] == second["uid"] and (first["sequence"], second["sequence"]) == (0, 1)
    assert second["url"] == f"https://x.test/calendar/entries/{e}"


# ------------------------------------------------------------ attachments ---

def test_mailer_sends_attachments_through_the_relay(monkeypatch):
    seen = {}
    monkeypatch.setenv("CSS_MAIL_RELAY_URL", "https://relay.test/exec"); monkeypatch.setenv("CSS_MAIL_RELAY_SECRET", "s")
    monkeypatch.setattr(mailer, "_post_to_relay", lambda url, payload: seen.update(payload) or (_Resp(), None))
    monkeypatch.setattr(mailer, "_parse_relay_json", lambda r: {"ok": True})
    mailer.send("a@b.c", "s", "b", attachments=[ics.attachment([EV])])
    att = seen["attachments"][0]
    import base64
    assert att["name"] == "calendar.ics" and att["mimeType"] == "text/calendar"
    assert base64.b64decode(att["base64"]).decode().startswith("BEGIN:VCALENDAR")
    seen.clear()
    mailer.send("a@b.c", "s", "b")
    assert "attachments" not in seen


class _Resp:
    status_code = 200
    url = "https://relay.test/exec"


def test_change_emails_carry_the_items_uid_and_sequence(world):                                 # noqa: F811
    c = world["conn"]
    far = (tz.today_local() + timedelta(days=20)).isoformat()
    e = st.cal_create(c, "Planning", far, people=[(world["s1"]["id"], "attending")], by="editor@x")
    st.cal_update(c, e, by="editor@x", venue="Cebu")
    got = {}

    def fake(to, subj, body, html=None, attachments=None):
        got["att"] = attachments
        return {"sent": True, "detail": "ok"}
    mailer_ok = mailer.email_configured
    mailer.email_configured = lambda: True
    try:
        oc.flush_outbox(c, "https://x.test", now=tz.now_local() + timedelta(minutes=11), send=fake)
    finally:
        mailer.email_configured = mailer_ok
    (name, mime, data), = got["att"]
    text = data.decode()
    uid = st.cal_get(c, e)["uid"]
    assert name == "calendar-update.ics" and "method=PUBLISH" in mime
    assert f"UID:{uid}" in text and "SEQUENCE:0" in text and "LOCATION:Cebu" in text


def test_a_cancellation_email_says_cancelled_to_the_calendar_app_too(world):                    # noqa: F811
    c = world["conn"]
    far = (tz.today_local() + timedelta(days=20)).isoformat()
    e = st.cal_create(c, "Planning", far, people=[(world["s1"]["id"], "attending")], by="editor@x")
    c.execute("DELETE FROM calendar_outbox"); c.commit()
    st.cal_cancel(c, e, by="editor@x")
    got = {}
    mailer_ok = mailer.email_configured
    mailer.email_configured = lambda: True
    try:
        oc.flush_outbox(c, "https://x.test", now=tz.now_local() + timedelta(minutes=11),
                        send=lambda to, s, b, html=None, attachments=None: got.update(a=attachments) or {"sent": True})
    finally:
        mailer.email_configured = mailer_ok
    text = got["a"][0][2].decode()
    assert "STATUS:CANCELLED" in text and "SEQUENCE:1" in text


def test_the_day_before_reminder_attaches_tomorrows_items(world, monkeypatch):                 # noqa: F811
    c = world["conn"]
    tomorrow = date(2026, 10, 15)
    monkeypatch.setattr(tz, "today_local", lambda: date(2026, 10, 14))
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    got = []
    monkeypatch.setattr(mailer, "send", lambda to, s, b, html=None, attachments=None: got.append(attachments) or {"sent": True, "detail": "ok"})
    e = st.cal_create(c, "Thing", tomorrow.isoformat(), start_time="09:00", people=[(world["s1"]["id"], "attending")], by="x@x")
    assert sr.send_calendar_day_before(c, "https://x.test") == 1
    assert f"UID:{st.cal_get(c, e)['uid']}" in got[0][0][2].decode()


# --------------------------------------------------------------- the pages ---

@pytest.fixture()
def pg(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    made = []
    yield c, uid, made
    st.feed_off(c, uid); st.feed_set(c, uid, "mine", False)
    for e in made:
        st.cal_delete(c, e)
    c.close()


def test_one_item_downloads_with_the_visibility_of_its_page(app_mod, viewer, pg):
    c, uid, made = pg
    D = (tz.today_local() + timedelta(days=9)).isoformat()
    pub = st.cal_create(c, "ICSTEST visible", D, audience="bureau", by="x@x"); made.append(pub)
    priv = st.cal_create(c, "ICSTEST private", D, audience="people", by="x@x"); made.append(priv)
    r = viewer.get(f"/calendar/entries/{pub}/event.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert f'filename="calendar-item-{pub}.ics"' in r.headers["content-disposition"]
    assert f"UID:{st.cal_get(c, pub)['uid']}" in r.text and "METHOD:PUBLISH" in r.text
    assert viewer.get(f"/calendar/entries/{priv}/event.ics").status_code == 404
    assert viewer.get(f"/calendar/entries/{pub}").text.count("event.ics") == 1


def test_the_item_download_needs_a_login(app_mod, client, pg):
    c, uid, made = pg
    e = st.cal_create(c, "ICSTEST x", (tz.today_local() + timedelta(days=9)).isoformat(), audience="bureau", by="x@x"); made.append(e)
    assert client.get(f"/calendar/entries/{e}/event.ics", follow_redirects=False).status_code in (302, 303, 401)


def test_creating_using_resetting_and_turning_off_the_feed(app_mod, viewer, client, pg):
    c, uid, made = pg
    D = (tz.today_local() + timedelta(days=9)).isoformat()
    made.append(st.cal_create(c, "ICSTEST in feed", D, audience="bureau", by="x@x"))
    assert "Create my calendar link" in viewer.get("/me").text
    assert viewer.post("/me/calendar-feed/reset", follow_redirects=False).status_code == 303
    tok = st.feed_get(c, uid)["token"]
    assert len(tok) >= 30 and f"/calendar/feed/{tok}.ics" in viewer.get("/me").text
    r = client.get(f"/calendar/feed/{tok}.ics")                                      # NOT signed in
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar")
    assert "ICSTEST in feed" in r.text and "METHOD" not in r.text and "BEGIN:VTIMEZONE" in r.text
    assert "noindex" in r.headers["x-robots-tag"] and "private" in r.headers["cache-control"]
    viewer.post("/me/calendar-feed/reset")
    assert client.get(f"/calendar/feed/{tok}.ics").status_code == 404                # the old link is dead
    new = st.feed_get(c, uid)["token"]
    assert new != tok and client.get(f"/calendar/feed/{new}.ics").status_code == 200
    viewer.post("/me/calendar-feed/off")
    assert client.get(f"/calendar/feed/{new}.ics").status_code == 404 and st.feed_get(c, uid) is None
    assert client.get("/calendar/feed/not-a-real-token-at-all-0000.ics").status_code == 404
    assert client.get("/calendar/feed/short.ics").status_code == 404


def test_the_feed_shows_only_what_its_owner_may_see(app_mod, viewer, client, pg):
    c, uid, made = pg
    D = (tz.today_local() + timedelta(days=9)).isoformat()
    made.append(st.cal_create(c, "ICSTEST bureau", D, audience="bureau", by="x@x"))
    made.append(st.cal_create(c, "ICSTEST private", D, audience="people", by="x@x"))
    made.append(st.cal_create(c, "ICSTEST mine", D, audience="people", by="x@x", people=[(uid, "attending")]))
    tok = st.feed_reset(c, uid)
    body = client.get(f"/calendar/feed/{tok}.ics").text
    assert "ICSTEST bureau" in body and "ICSTEST mine" in body and "ICSTEST private" not in body


def test_recently_cancelled_items_say_cancelled_so_the_app_removes_them(app_mod, viewer, client, pg):
    c, uid, made = pg
    D = (tz.today_local() + timedelta(days=9)).isoformat()
    e = st.cal_create(c, "ICSTEST gone", D, audience="bureau", by="x@x"); made.append(e)
    st.cal_cancel(c, e, by="x@x")
    tok = st.feed_reset(c, uid)
    body = client.get(f"/calendar/feed/{tok}.ics").text
    block = body[body.index("ICSTEST gone") - 300:body.index("ICSTEST gone") + 200]
    assert "STATUS:CANCELLED" in block and f"SEQUENCE:1" in block


def test_birthdays_in_the_feed_are_opt_in_and_respect_sharing(app_mod, viewer, client, pg):
    c, uid, made = pg
    other = st.get_admin_user(c, "encoder@test.local")["id"]
    st.set_birthday(c, other, 6, 7, "bureau")
    tok = st.feed_reset(c, uid)
    assert "RRULE:FREQ=YEARLY" not in client.get(f"/calendar/feed/{tok}.ics").text
    viewer.post("/me/calendar-feed/settings", content="scope=mine&birthdays=1",
                headers={"Content-Type": "application/x-www-form-urlencoded"})
    body = client.get(f"/calendar/feed/{tok}.ics").text
    assert "RRULE:FREQ=YEARLY" in body and "DTSTART;VALUE=DATE:" in body
    st.set_birthday(c, other, 6, 7, "none")                                          # no longer shared
    assert "RRULE:FREQ=YEARLY" not in client.get(f"/calendar/feed/{tok}.ics").text
    st.clear_birthday(c, other)


def test_feed_settings_need_a_link_and_a_valid_scope(app_mod, viewer, pg):
    c, uid, made = pg
    F = {"Content-Type": "application/x-www-form-urlencoded"}
    r = viewer.post("/me/calendar-feed/settings", content="scope=mine", headers=F, follow_redirects=False)
    assert "err=" in r.headers["location"] and st.feed_get(c, uid) is None
    st.feed_reset(c, uid)
    r = viewer.post("/me/calendar-feed/settings", content="scope=everything", headers=F, follow_redirects=False)
    assert "err=" in r.headers["location"] and st.feed_get(c, uid)["scope"] == "mine"
    viewer.post("/me/calendar-feed/settings", content="scope=section", headers=F)
    assert st.feed_get(c, uid)["scope"] == "section"


def test_a_deactivated_owner_s_link_stops_working(app_mod, viewer, client, pg):
    c, uid, made = pg
    tok = st.feed_reset(c, uid)
    c.execute("UPDATE admin_user SET active=0 WHERE id=?", (uid,)); c.commit()
    try:
        assert client.get(f"/calendar/feed/{tok}.ics").status_code == 404
    finally:
        c.execute("UPDATE admin_user SET active=1 WHERE id=?", (uid,)); c.commit()
