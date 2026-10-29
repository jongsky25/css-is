"""Send notice of meeting: who gets it, what it says, who may send it, what is recorded, and the stale-notice warning."""
from __future__ import annotations
from urllib.parse import quote, urlencode

import pytest

import activity_docs as ad
import calendar_notice as cn
import mailer
import storage as st
from test_calendar_entry_pages import conn, create, uid, FORM  # noqa: F401  (shared calendar fixtures)


@pytest.fixture()
def sent(monkeypatch):
    out = []

    def fake(to, subject, body, html=None, attachments=None):
        out.append({"to": to, "subject": subject, "body": body, "html": html})
        return {"sent": True, "detail": None}
    monkeypatch.setattr(mailer, "send", fake)
    monkeypatch.setattr(mailer, "send_status", lambda r: "sent")
    yield out


@pytest.fixture(autouse=True)
def _clean(conn):
    yield
    for t in ("calendar_entry_notice_to", "calendar_entry_notice"):
        conn.execute(f"DELETE FROM {t}")
    conn.commit()


def meeting(viewer, conn, **kw):
    ids = [str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))]
    return create(viewer, kind="meeting", title="CALEP Planning", venue="Conference room", people=ids, **kw)


def send(client, eid, **fields):
    return client.post(f"/calendar/entries/{eid}/notice/send", content=urlencode(fields), headers=FORM, follow_redirects=False)


def test_the_page_offers_the_send_form_to_the_person_who_made_it(viewer, conn):
    eid = meeting(viewer, conn)
    html = viewer.get(f"/calendar/entries/{eid}").text
    assert "Send notice of meeting" in html and 'name="agenda"' in html and 'name="extra"' in html


def test_it_emails_the_people_on_the_item_and_the_extra_addresses_and_records_each(viewer, conn, sent):
    eid = meeting(viewer, conn)
    ad.set_visitors(conn, eid, "Dr. Cruz, CHD III", "viewer@test.local")
    r = send(viewer, eid, agenda="1. Opening\n2. Updates", extra="chd3@example.org; CHD3@example.org\n")
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert sorted(m["to"] for m in sent) == ["chd3@example.org", "encoder@test.local", "viewer@test.local"]
    body = sent[0]["body"]
    assert "CALEP Planning" in body and "Conference room" in body and "1. Opening" in body and "Dr. Cruz, CHD III" in body
    (h,) = cn.history(conn, eid)
    assert h["by"] == "viewer@test.local" and h["counts"] == {"sent": 3} and len(h["to"]) == 3
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='meeting_notice_sent' AND target_id=?", (str(eid),)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM email_log WHERE feature='meeting_notice' AND status='sent'").fetchone()[0] >= 3
    assert "Who" in viewer.get(f"/calendar/entries/{eid}").text


def test_someone_who_is_not_on_it_cannot_send(encoder, viewer, conn, sent):
    eid = create(viewer, kind="meeting", title="CALEP Private", people=[str(uid(conn, "viewer@test.local"))])
    r = send(encoder, eid, agenda="x")
    assert r.status_code == 303 and "err=" in r.headers["location"]
    assert sent == [] and cn.history(conn, eid) == []


def test_a_bad_extra_address_sends_nothing(viewer, conn, sent):
    eid = meeting(viewer, conn)
    r = send(viewer, eid, extra="not-an-address")
    assert "err=" in r.headers["location"] and sent == [] and cn.history(conn, eid) == []


def test_a_second_send_within_a_minute_is_refused(viewer, conn, sent):
    eid = meeting(viewer, conn)
    send(viewer, eid, agenda="a")
    again = send(viewer, eid, agenda="a")
    assert "err=" in again.headers["location"] and len(cn.history(conn, eid)) == 1


def test_a_switched_off_email_feature_is_recorded_not_sent(viewer, conn, sent):
    st.set_setting(conn, "email_feature.meeting_notice", "0")
    try:
        eid = meeting(viewer, conn)
        send(viewer, eid, agenda="a")
        assert sent == [] and cn.history(conn, eid)[0]["counts"] == {"skipped_off": 2}
    finally:
        st.set_setting(conn, "email_feature.meeting_notice", "1")


def test_a_change_after_the_notice_warns_that_it_is_out_of_date(viewer, conn, sent):
    eid = meeting(viewer, conn)
    send(viewer, eid, agenda="a")
    assert "changed after the last notice" not in viewer.get(f"/calendar/entries/{eid}").text
    st.cal_update(conn, eid, by="viewer@test.local", venue="Training room")
    assert "changed after the last notice" in viewer.get(f"/calendar/entries/{eid}").text


def test_the_email_preview_exists_for_the_admin_email_page():
    assert "meeting_notice" in mailer.FEATURES and "meeting_notice" in mailer._PREVIEWS
    subject, body, html = mailer._PREVIEWS["meeting_notice"]()
    assert subject.startswith("Notice of meeting") and "<" in html
