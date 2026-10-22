"""Admin review of a claim's papers before it can be marked ready (spot feedback #174)."""
from __future__ import annotations
import pytest

import mailer
import storage as st
import travel
import travel_review as review
from conftest import join_admin_section
from test_travel_generate import conn, mk, post, relay   # noqa: F401

LINK = "https://docs.google.com/document/d/example/edit"
REVIEWER = "encoder@test.local"          # joins the Administrative Section below
OTHER = "manager@test.local"     # a second member the traveller did not choose


@pytest.fixture()
def unit(conn):
    ids = {}
    for name in (REVIEWER, OTHER):
        uid = conn.execute("SELECT id FROM admin_user WHERE username=?", (name,)).fetchone()[0]
        join_admin_section(conn, uid)
        ids[name] = uid
    st.set_setting(conn, review.SETTING, "1")
    conn.commit()
    yield ids
    for uid in ids.values():
        conn.execute("UPDATE admin_user SET rp_id=NULL WHERE id=?", (uid,))
    st.set_setting(conn, review.SETTING, "0")
    conn.commit()


@pytest.fixture()
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, body, html=None, **kw: out.append((to, subject, body)) or {"ok": True})
    monkeypatch.setattr(mailer, "send_status", lambda result: "sent")
    return out


def complete(conn, ref):
    f = travel.get_by_ref(conn, ref)
    for it in travel.view_items(conn, f):
        if it["requirement"] == "required" and it["handling"] != "fmis" and it["state"] != "na":
            travel.save_item(conn, travel.get_filing(conn, f["id"]), it["code"], drive_url=LINK)
    return travel.get_by_ref(conn, ref)


def ask(viewer, ref, who):
    return post(viewer, f"/travel/f/{ref}/review/request", reviewer_id=str(who))


def test_marking_ready_waits_for_the_approval(viewer, conn, unit, relay):
    ref = mk(viewer)
    f = complete(conn, ref)
    with pytest.raises(travel.TravelError, match="Administrative Section reviewer"):
        travel.mark_ready(conn, f)
    assert "err=" in post(viewer, f"/travel/f/{ref}/ready").headers["location"]
    assert "Ask an admin to review your papers" in viewer.get(f"/travel/f/{ref}").text


def test_the_review_can_be_switched_off(viewer, conn, unit, relay):
    st.set_setting(conn, review.SETTING, "0"); conn.commit()
    ref = mk(viewer)
    assert travel.mark_ready(conn, complete(conn, ref))["status"] == "ready"


def test_a_claim_with_things_missing_cannot_be_sent_for_review(viewer, conn, unit, relay):
    ref = mk(viewer)
    r = ask(viewer, ref, unit[REVIEWER])
    assert "err=" in r.headers["location"] and travel.get_by_ref(conn, ref)["review_state"] == ""


def test_only_a_section_member_other_than_the_traveller_can_be_chosen(viewer, conn, unit, relay):
    ref = mk(viewer); complete(conn, ref)
    me = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    for bad in (me, 999999, "", "x"):
        assert "err=" in ask(viewer, ref, bad).headers["location"]
    assert travel.get_by_ref(conn, ref)["review_state"] == ""


def test_the_whole_loop_from_request_to_ready(viewer, encoder, conn, unit, relay, sent):
    ref = mk(viewer); complete(conn, ref)
    assert "ok=" in ask(viewer, ref, unit[REVIEWER]).headers["location"]
    f = travel.get_by_ref(conn, ref)
    assert f["review_state"] == "requested" and f["reviewer_id"] == unit[REVIEWER] and f["review_round"] == 1
    assert sent[-1][0] == REVIEWER and "Travel papers to review" in sent[-1][1]
    # the reviewer sees it in the queue and on the claim's review page
    assert ref in encoder.get("/travel/review").text
    page = encoder.get(f"/travel/review/{ref}")
    assert page.status_code == 200 and "Approve the papers" in page.text
    # a missing item, then send it back
    r = encoder.post(f"/travel/review/{ref}/note", data={"item_code": "dpo", "kind": "missing", "note": "The DPO page 2 is not attached."},
                     follow_redirects=False)
    assert r.status_code == 303
    r = encoder.post(f"/travel/review/{ref}/approve", follow_redirects=False)
    assert r.status_code == 400 and "unsent notes" in r.text           # drafts must be sent or removed first
    assert encoder.post(f"/travel/review/{ref}/feedback", follow_redirects=False).status_code == 303
    f = travel.get_by_ref(conn, ref)
    assert f["review_state"] == "changes"
    to, subject, body = sent[-1]
    assert to == "viewer@test.local" and "need changes" in subject and "The DPO page 2 is not attached." in body
    # the traveller sees the note and cannot mark ready
    page = viewer.get(f"/travel/f/{ref}").text
    assert "The DPO page 2 is not attached." in page and "Send for review again" in page
    assert "err=" in post(viewer, f"/travel/f/{ref}/ready").headers["location"]
    # fixed: ask again; the old note is resolved, the reviewer is told it is a second look
    assert "ok=" in ask(viewer, ref, unit[REVIEWER]).headers["location"]
    f = travel.get_by_ref(conn, ref)
    assert f["review_state"] == "requested" and f["review_round"] == 2
    assert [n["state"] for n in review.notes_of(conn, f["id"])] == ["resolved"]
    assert "check the papers again" in sent[-1][2]
    assert encoder.post(f"/travel/review/{ref}/approve", follow_redirects=False).status_code == 303
    assert travel.get_by_ref(conn, ref)["review_state"] == "approved"
    assert sent[-1][0] == "viewer@test.local" and "approved" in sent[-1][1]
    assert "ok=" in post(viewer, f"/travel/f/{ref}/ready").headers["location"]
    assert travel.get_by_ref(conn, ref)["status"] == "ready"
    acts = {r_[0] for r_ in conn.execute("SELECT action FROM audit_log")}
    assert {"travel_review_request", "travel_review_feedback", "travel_review_approve"} <= acts


def test_sending_needs_a_note_and_a_note_needs_text(viewer, encoder, conn, unit, relay, sent):
    ref = mk(viewer); complete(conn, ref); ask(viewer, ref, unit[REVIEWER])
    assert encoder.post(f"/travel/review/{ref}/feedback", follow_redirects=False).status_code == 400
    assert encoder.post(f"/travel/review/{ref}/note", data={"kind": "other", "note": "  "}, follow_redirects=False).status_code == 400
    assert encoder.post(f"/travel/review/{ref}/note", data={"kind": "nope", "note": "x"}, follow_redirects=False).status_code == 400
    assert encoder.post(f"/travel/review/{ref}/note", data={"kind": "other", "note": "x", "item_code": "bogus"},
                        follow_redirects=False).status_code == 400


def test_a_draft_note_can_be_removed_before_sending(viewer, encoder, conn, unit, relay, sent):
    ref = mk(viewer); complete(conn, ref); ask(viewer, ref, unit[REVIEWER])
    encoder.post(f"/travel/review/{ref}/note", data={"kind": "other", "note": "Oops"}, follow_redirects=False)
    nid = review.notes_of(conn, travel.get_by_ref(conn, ref)["id"])[0]["id"]
    assert encoder.post(f"/travel/review/{ref}/note/{nid}/delete", follow_redirects=False).status_code == 303
    assert review.notes_of(conn, travel.get_by_ref(conn, ref)["id"]) == []


def test_only_the_chosen_reviewer_can_open_or_decide(viewer, encoder, manager, admin, conn, unit, relay, sent):
    ref = mk(viewer); complete(conn, ref); ask(viewer, ref, unit[REVIEWER])
    assert manager.get(f"/travel/review/{ref}").status_code == 403          # another section member, not chosen
    assert manager.post(f"/travel/review/{ref}/approve", follow_redirects=False).status_code == 403
    assert viewer.get(f"/travel/review/{ref}").status_code == 403           # the traveller is no reviewer
    assert viewer.get("/travel/review").status_code == 403
    assert admin.get(f"/travel/review/{ref}").status_code == 403            # the app admin role is no bypass
    assert travel.get_by_ref(conn, ref)["review_state"] == "requested"


def test_the_bell_and_nav_tell_each_side(viewer, encoder, conn, unit, relay, sent):
    import travel_notify, tzutil as tz
    ref = mk(viewer); complete(conn, ref); ask(viewer, ref, unit[REVIEWER])
    rv = unit[REVIEWER]
    assert any("to review" in r["text"] and r["url"] == "/travel/review" for r in travel_notify.bell_rows(conn, rv, tz.today_local()))
    encoder.post(f"/travel/review/{ref}/note", data={"kind": "missing", "note": "Add the ticket"}, follow_redirects=False)
    encoder.post(f"/travel/review/{ref}/feedback", follow_redirects=False)
    me = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    assert any("sent notes back" in r["text"] for r in travel_notify.bell_rows(conn, me, tz.today_local()))
    assert not any("to review" in r["text"] for r in travel_notify.bell_rows(conn, rv, tz.today_local()))


def test_an_approved_claim_stays_approved_on_the_ready_page(viewer, encoder, conn, unit, relay, sent):
    ref = mk(viewer); complete(conn, ref); ask(viewer, ref, unit[REVIEWER])
    encoder.post(f"/travel/review/{ref}/approve", follow_redirects=False)
    page = viewer.get(f"/travel/f/{ref}/ready").text
    assert "Mark ready" in page and "Go to the review" not in page
