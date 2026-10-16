"""Travel filing pages (T2): access, ownership, the new-filing guards, checklist saving, ready /
submit / withdraw, the calendar chip and the enable switch."""
from __future__ import annotations
import re
from datetime import timedelta
from urllib.parse import urlencode

import pytest

import office_calendar as oc
import storage as st
import travel
import tzutil as tz
from conftest import join_admin_section

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def post(client, path, **data):
    return client.post(path, content=urlencode(data), headers=FORM, follow_redirects=False)


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for t in ("travel_flag", "travel_item", "travel_filing"):
        c.execute(f"DELETE FROM {t}")
    c.execute("DELETE FROM calendar_entry WHERE title LIKE 'TRAVELTEST%'")
    st.set_setting(c, "travel.enabled", "1")
    c.commit(); c.close()


def uid(conn, username):
    return st.get_admin_user(conn, username)["id"]


def days(n):
    return (tz.today_local() + timedelta(days=n)).isoformat()


def blank(client, kind="liquidation", start=None, end=None, **over):
    f = {"kind": kind, "title": "TRAVELTEST Visit", "start": start or days(-10), "end": end or days(-8),
         "role": "secretariat", "advance_amount": "5000", "mc114_format": "none"}
    f.update(over)
    return post(client, "/travel/new", **f)


def ref_of(resp):
    return re.search(r"/travel/f/(TF-\d{4}-\d+)", resp.headers["location"]).group(1)


# ---------------------------------------------------------------- access ---

def test_pages_need_a_login(client):
    for path in ("/travel", "/travel/new", "/travel/f/TF-2610-0001"):
        assert client.get(path, follow_redirects=False).status_code in (302, 303, 401)


def test_index_and_nav(viewer, conn):
    r = viewer.get("/travel")
    assert r.status_code == 200 and "Travel claims" in r.text
    assert "My travel claims" in viewer.get("/").text or "/travel" in viewer.get("/").text


def test_switch_off_shows_a_friendly_page(viewer, admin, conn):
    assert post(admin, "/admin/travel").status_code == 303                 # unchecked box = off
    r = viewer.get("/travel")
    assert r.status_code == 200 and "not switched on" in r.text
    assert "not switched on" in viewer.get("/travel/new").text
    assert blank(viewer).status_code == 200                               # the off page, nothing created
    assert conn.execute("SELECT COUNT(*) FROM travel_filing").fetchone()[0] == 0
    post(admin, "/admin/travel", enabled="1")
    assert "not switched on" not in viewer.get("/travel").text


def test_admin_switch_is_for_app_admins_only(viewer, manager):
    assert viewer.get("/admin/travel").status_code in (302, 303, 403)
    assert manager.get("/admin/travel").status_code in (302, 303, 403)


# ----------------------------------------------------------- new filings ---

def test_blank_liquidation_opens_a_filing_with_a_checklist(viewer, conn):
    r = blank(viewer)
    assert r.status_code == 303
    ref = ref_of(r)
    page = viewer.get(f"/travel/f/{ref}")
    assert page.status_code == 200
    for text in ("Liquidation", "Appendix B", "Post Travel Report", "Certificate of Appearance", "Deadline"):
        assert text in page.text
    f = travel.get_by_ref(conn, ref)
    assert f["status"] == "open" and f["advance_amount"] == 5000
    assert f["deadline_rule"] == "after_fact" and f["user_id"] == uid(conn, "viewer@test.local")
    assert conn.execute("SELECT COUNT(*) FROM travel_item WHERE filing_id=?", (f["id"],)).fetchone()[0] >= 6
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_open'").fetchone()[0] >= 1


def test_cash_advance_needs_more_than_a_week(viewer, conn):
    r = blank(viewer, "ca", start=days(5), end=days(7))
    assert r.status_code == 400 and "more than a week" in r.text
    r = blank(viewer, "ca", start=days(7), end=days(9))
    assert r.status_code == 400
    r = blank(viewer, "ca", start=days(8), end=days(10))
    assert r.status_code == 303
    f = travel.get_by_ref(conn, ref_of(r))
    assert f["deadline_date"] is None and f["deadline_rule"] == "none"


def test_liquidation_needs_a_cash_advance_or_an_amount(viewer, conn):
    r = blank(viewer, advance_amount="")
    assert r.status_code == 400 and "cash advance" in r.text


def test_role_and_dates_are_required(viewer, conn):
    assert blank(viewer, role="").status_code == 400
    assert blank(viewer, start=days(-5), end=days(-9)).status_code == 400
    assert blank(viewer, title="").status_code == 400


def test_unrelated_answers_are_dropped_and_unticked_boxes_count(viewer, conn):
    ref = ref_of(blank(viewer, flew="1", refund="1", official_gasoline="1"))
    ans = travel.answers_of(travel.get_by_ref(conn, ref))
    assert ans["flew"] == 1 and ans["refund"] == 1 and "official_gasoline" not in ans
    assert ans["cert_of_appearance_available"] == 0                       # unticked = not available
    page = viewer.get(f"/travel/f/{ref}").text
    assert 'id="item-plane_ticket"' in page and 'id="item-bto_report"' in page and 'id="item-cert_appearance"' not in page


def test_same_origin_check(viewer, conn):
    f = {"kind": "liquidation", "title": "TRAVELTEST X", "start": days(-10), "end": days(-8), "role": "secretariat",
         "advance_amount": "100"}
    bad = viewer.post("/travel/new", content=urlencode(f), headers={**FORM, "Origin": "https://evil.example"},
                      follow_redirects=False)
    assert bad.status_code == 403
    bad = viewer.post("/travel/new", content=urlencode(f), headers={**FORM, "Referer": "https://evil.example/x"},
                      follow_redirects=False)
    assert bad.status_code == 403
    ok = viewer.post("/travel/new", content=urlencode(f), headers={**FORM, "Origin": "http://testserver"},
                     follow_redirects=False)
    assert ok.status_code == 303


def test_unliquidated_cash_advance_warns_before_a_new_one(viewer, conn):
    u = uid(conn, "viewer@test.local")
    old = travel.create_filing(conn, {"id": u, "username": "viewer@test.local"}, kind="ca",
                               source={"source_kind": "blank", "title": "TRAVELTEST Old", "start": days(-20),
                                       "end": days(-18), "venue": ""},
                               answers={}, role="secretariat", today=tz.today_local() - timedelta(days=40))
    conn.execute("UPDATE travel_filing SET status='submitted' WHERE id=?", (old["id"],)); conn.commit()
    r = blank(viewer, "ca", start=days(20), end=days(22))
    assert r.status_code == 200 and "not been liquidated" in r.text and 'name="ack"' in r.text
    assert conn.execute("SELECT COUNT(*) FROM travel_filing WHERE kind='ca'").fetchone()[0] == 1
    assert blank(viewer, "ca", start=days(20), end=days(22), ack="1").status_code == 303
    assert "no liquidation yet" in viewer.get("/travel").text


def test_liquidating_a_platform_cash_advance_links_it(viewer, conn):
    u = {"id": uid(conn, "viewer@test.local"), "username": "viewer@test.local"}
    ca = travel.create_filing(conn, u, kind="ca", source={"source_kind": "blank", "title": "TRAVELTEST CA",
                              "start": days(10), "end": days(12), "venue": ""}, answers={}, role="participant",
                              advance_amount="2500", today=tz.today_local())
    r = blank(viewer, advance_amount="", ca=str(ca["id"]))
    assert r.status_code == 400 and "Mark that cash advance as submitted" in r.text
    conn.execute("UPDATE travel_filing SET status='submitted' WHERE id=?", (ca["id"],)); conn.commit()
    r = blank(viewer, advance_amount="", ca=str(ca["id"]))
    assert r.status_code == 303
    lq = travel.get_by_ref(conn, ref_of(r))
    assert lq["ca_filing_id"] == ca["id"] and lq["advance_amount"] == 2500
    # the cash advance cannot be withdrawn while a liquidation uses it, and it cannot be liquidated twice
    assert travel.liquidations_of(conn, ca["id"])
    with pytest.raises(travel.TravelError):
        travel.withdraw(conn, travel.get_filing(conn, ca["id"]))


# ------------------------------------------------------------- ownership ---

def test_a_stranger_cannot_see_or_change_a_filing(viewer, encoder, conn):
    ref = ref_of(blank(viewer))
    assert encoder.get(f"/travel/f/{ref}").status_code == 404
    assert encoder.get(f"/travel/f/{ref}/ready").status_code == 404
    for path, data in ((f"/travel/f/{ref}/item/dpo", {"drive_url": "https://drive.google.com/file/d/abc/view"}),
                       (f"/travel/f/{ref}/answers", {"role": "participant"}),
                       (f"/travel/f/{ref}/ready", {}), (f"/travel/f/{ref}/withdraw", {})):
        assert post(encoder, path, **data).status_code == 404
    assert travel.get_by_ref(conn, ref)["status"] == "open"
    assert ref not in encoder.get("/travel").text


def test_admin_unit_can_look_but_not_edit(viewer, encoder, conn):
    ref = ref_of(blank(viewer))
    join_admin_section(conn, uid(conn, "encoder@test.local"))
    try:
        assert encoder.get(f"/travel/f/{ref}").status_code == 200
        assert post(encoder, f"/travel/f/{ref}/item/dpo", drive_url="https://drive.google.com/file/d/abc/view").status_code == 403
        assert post(encoder, f"/travel/f/{ref}/withdraw").status_code == 403
    finally:
        conn.execute("UPDATE admin_user SET rp_id=NULL WHERE username='encoder@test.local'"); conn.commit()


def test_bad_references_are_404(viewer):
    assert viewer.get("/travel/f/nonsense").status_code == 404
    assert viewer.get("/travel/f/TF-9999-9999").status_code == 404


# ------------------------------------------------- checklist and lifecycle ---

LINK = "https://drive.google.com/file/d/1abcDEF/view"


def fill(client, conn, ref):
    """Give every required, non-FMIS row a link / note."""
    f = travel.get_by_ref(conn, ref)
    for it in travel.view_items(conn, f):
        if it["requirement"] != "required" or it["handling"] == "fmis":
            continue
        assert post(client, f"/travel/f/{ref}/item/{it['code']}", drive_url=LINK).status_code == 303


def test_links_must_be_google_drive(viewer, conn):
    ref = ref_of(blank(viewer))
    r = post(viewer, f"/travel/f/{ref}/item/dpo", drive_url="https://evil.example/x")
    assert "Google%20Drive" in r.headers["location"]
    assert post(viewer, f"/travel/f/{ref}/item/dpo", drive_url="javascript:alert(1)").status_code == 303
    f = travel.get_by_ref(conn, ref)
    assert next(i for i in travel.view_items(conn, f) if i["code"] == "dpo")["drive_url"] is None
    post(viewer, f"/travel/f/{ref}/item/dpo", drive_url=LINK)
    assert next(i for i in travel.view_items(conn, f) if i["code"] == "dpo")["drive_url"] == LINK
    assert LINK in viewer.get(f"/travel/f/{ref}").text


def test_unknown_rows_and_wrong_kinds_of_input_are_refused(viewer, conn):
    ref = ref_of(blank(viewer))
    for path, data in ((f"/travel/f/{ref}/item/nope", {"drive_url": LINK}),
                       (f"/travel/f/{ref}/item/ors", {"drive_url": LINK}),           # FMIS rows take a reference
                       (f"/travel/f/{ref}/item/dpo", {"fmis_ref": "x"}),
                       (f"/travel/f/{ref}/item/travel_report", {"na": "1"})):          # a generated form cannot be N/A
        assert "err=" in post(viewer, path, **data).headers["location"], path


def test_ready_needs_everything_then_submit_then_calendar_label(viewer, conn):
    ref = ref_of(blank(viewer))
    r = post(viewer, f"/travel/f/{ref}/ready")
    assert "err=" in r.headers["location"] and travel.get_by_ref(conn, ref)["status"] == "open"
    fill(viewer, conn, ref)
    assert travel.missing_for(conn, travel.get_by_ref(conn, ref)) == []
    assert "err=" in post(viewer, f"/travel/f/{ref}/submit").headers["location"]       # not ready yet
    assert "ok=" in post(viewer, f"/travel/f/{ref}/ready").headers["location"]
    page = viewer.get(f"/travel/f/{ref}/ready").text
    assert "Mark submitted" in page and "sign in ink" in page.lower() or "✎" in page
    assert "ok=" in post(viewer, f"/travel/f/{ref}/submit").headers["location"]
    f = travel.get_by_ref(conn, ref)
    assert f["status"] == "submitted" and f["submitted_at"]
    assert travel.filing_summaries(conn, f["user_id"], [], [])  == {}
    # no further edits, no withdrawal after submission
    assert "err=" in post(viewer, f"/travel/f/{ref}/item/dpo", drive_url=LINK).headers["location"]
    assert "err=" in post(viewer, f"/travel/f/{ref}/withdraw").headers["location"]
    acts = {r_[0] for r_ in conn.execute("SELECT action FROM audit_log")}
    assert {"travel_ready", "travel_submit"} <= acts


def test_editing_a_ready_filing_sends_it_back_to_open(viewer, conn):
    ref = ref_of(blank(viewer))
    fill(viewer, conn, ref)
    post(viewer, f"/travel/f/{ref}/ready")
    assert travel.get_by_ref(conn, ref)["status"] == "ready"
    post(viewer, f"/travel/f/{ref}/answers", role="secretariat", flew="1", cert_of_appearance_available="1")
    f = travel.get_by_ref(conn, ref)
    assert f["status"] == "open" and f["ready_at"] is None
    assert any(i["code"] == "plane_ticket" for i in travel.view_items(conn, f))


def test_changing_answers_keeps_existing_links(viewer, conn):
    ref = ref_of(blank(viewer, flew="1", cert_of_appearance_available="1"))
    post(viewer, f"/travel/f/{ref}/item/plane_ticket", drive_url=LINK)
    post(viewer, f"/travel/f/{ref}/answers", role="secretariat", cert_of_appearance_available="1")   # flew off
    f = travel.get_by_ref(conn, ref)
    assert "plane_ticket" not in {i["code"] for i in travel.view_items(conn, f)}
    post(viewer, f"/travel/f/{ref}/answers", role="secretariat", flew="1", cert_of_appearance_available="1")
    f = travel.get_by_ref(conn, ref)
    assert next(i for i in travel.view_items(conn, f) if i["code"] == "plane_ticket")["drive_url"] == LINK


def test_not_applicable_and_fmis_reference(viewer, conn):
    ref = ref_of(blank(viewer, flew="1", cert_of_appearance_available="1"))
    post(viewer, f"/travel/f/{ref}/item/boarding_pass", na="1")
    post(viewer, f"/travel/f/{ref}/item/liquidation_report", fmis_ref="LR-2026-114")
    f = travel.get_by_ref(conn, ref)
    items = {i["code"]: i for i in travel.view_items(conn, f)}
    assert items["boarding_pass"]["state"] == "na" and items["liquidation_report"]["fmis_ref"] == "LR-2026-114"
    assert not any("Boarding pass" in m for m in travel.missing_for(conn, f))
    post(viewer, f"/travel/f/{ref}/item/boarding_pass", na="0")
    assert any("Boarding pass" in m for m in travel.missing_for(conn, travel.get_by_ref(conn, ref)))


def test_withdraw_frees_the_activity_for_a_new_cash_advance(viewer, conn):
    u = {"id": uid(conn, "viewer@test.local"), "username": "viewer@test.local"}
    eid = st.cal_create(conn, "TRAVELTEST Trip", days(20), end_date=days(22), kind="travel", audience="bureau",
                        people=[(u["id"], "attending")], by="x@x")
    src = travel.resolve_source(conn, u, tz.today_local(), entry_id=eid)
    a = travel.create_filing(conn, u, kind="ca", source=src, answers={}, role="participant", today=tz.today_local())
    with pytest.raises(travel.TravelError):
        travel.create_filing(conn, u, kind="ca", source=src, answers={}, role="participant", today=tz.today_local())
    with pytest.raises(travel.TravelError):                      # reimbursement hidden while a live CA exists
        travel.create_filing(conn, u, kind="reimbursement", source=src, answers={}, role="participant",
                             today=tz.today_local())
    r = post(viewer, f"/travel/f/{a['ref_code']}/withdraw")
    assert r.headers["location"].startswith("/travel?ok=")
    assert travel.get_by_ref(conn, a["ref_code"])["status"] == "withdrawn"
    travel.create_filing(conn, u, kind="ca", source=src, answers={}, role="participant", today=tz.today_local())


# ------------------------------------------------------------- calendar ---

def test_calendar_chip_labels_and_new_page(viewer, conn):
    u = {"id": uid(conn, "viewer@test.local"), "username": "viewer@test.local"}
    eid = st.cal_create(conn, "TRAVELTEST Field visit", days(20), end_date=days(22), kind="travel",
                        audience="bureau", people=[(u["id"], "attending")], by="x@x")
    today = tz.today_local()
    items = oc.items_between(conn, u, today, today + timedelta(days=40), scope="mine", layers=["entries"])
    it = next(i for i in items if i["title"] == "TRAVELTEST Field visit")
    assert it["filing"]["label"] == "Not filed" and f"entry={eid}" in it["filing"]["url"]
    page = viewer.get(f"/travel/new?entry={eid}")
    assert page.status_code == 200 and "TRAVELTEST Field visit" in page.text
    src = travel.resolve_source(conn, u, today, entry_id=eid)
    f = travel.create_filing(conn, u, kind="ca", source=src, answers={}, role="participant", today=today)
    items = oc.items_between(conn, u, today, today + timedelta(days=40), scope="mine", layers=["entries"])
    it = next(i for i in items if i["title"] == "TRAVELTEST Field visit")
    assert it["filing"]["label"] == "In progress" and it["filing"]["url"] == f"/travel/f/{f['ref_code']}"
    assert "In progress" in viewer.get(f"/calendar/entries/{eid}").text
    # the JSON API whitelist does not leak the key
    item = next(i for i in viewer.get(f"/api/calendar?start={days(18)}&end={days(25)}").json()["items"] if i["title"] == "TRAVELTEST Field visit")
    assert "filing" not in item and "Not filed" not in str(item) and "In progress" not in str(item)


def test_summary_labels(conn):
    u = {"id": 0, "username": "x"}
    today = tz.today_local()
    uid_ = st.create_admin_user(conn, "lbl@test.local", "x", "y", "viewer")
    u = {"id": uid_, "username": "lbl@test.local"}
    def mk(kind, start, end, status="open", **kw):
        f = travel.create_filing(conn, u, kind=kind, source={"source_kind": "blank", "title": "T" + start,
                                 "start": start, "end": end, "venue": ""}, answers={}, role="participant",
                                 advance_amount="100", today=today - timedelta(days=60 if kind != "ca" else 0), **kw)
        conn.execute("UPDATE travel_filing SET status=?, entry_id=? WHERE id=?", (status, 900 + f["id"], f["id"]))
        conn.commit()
        return 900 + f["id"]
    s = lambda e: travel.filing_summaries(conn, uid_, [e], [], today)[("entry", e)]["label"]
    e = mk("reimbursement", days(-50), days(-45)); conn.execute("UPDATE travel_filing SET deadline_date=? WHERE entry_id=?", (days(-1), e)); conn.commit()
    assert s(e) == "Overdue"
    conn.execute("UPDATE travel_filing SET deadline_date=? WHERE entry_id=?", (days(3), e)); conn.commit()
    assert s(e) == "Due in 3 days"
    conn.execute("UPDATE travel_filing SET status='ready' WHERE entry_id=?", (e,)); conn.commit()
    assert s(e) == "Ready to sign"
    conn.execute("UPDATE travel_filing SET status='submitted' WHERE entry_id=?", (e,)); conn.commit()
    assert s(e) == "Filed"
    c = mk("ca", days(20), days(22), "submitted")
    assert s(c).startswith("CA filed, liquidation due ")
    w = mk("ca", days(30), days(32), "withdrawn")
    assert ("entry", w) not in travel.filing_summaries(conn, uid_, [w], [], today)


def test_filing_summaries_is_one_batched_query_per_chunk(conn):
    seen = []
    conn.set_trace_callback(seen.append)
    travel.filing_summaries(conn, 1, list(range(1200)), [])
    conn.set_trace_callback(None)
    assert len([q for q in seen if "FROM travel_filing" in q]) == 3


def test_activity_pages_offer_the_button_only_to_people_on_the_activity(viewer, encoder, conn):
    me = uid(conn, "viewer@test.local")
    eid = conn.execute("INSERT INTO event(event_token, title, event_date, end_date, created_by) VALUES (?,?,?,?,?)",
                       ("tvtesttok", "TRAVELTEST Activity", days(15), days(16), "viewer@test.local")).lastrowid
    conn.commit()
    try:
        user = {"id": me, "username": "viewer@test.local"}
        other = {"id": uid(conn, "encoder@test.local"), "username": "encoder@test.local"}
        assert travel.event_url_for(conn, user, eid) == f"/travel/new?event={eid}"
        assert travel.event_url_for(conn, other, eid) is None
        # the overlay's people count too
        st.cal_create(conn, "TRAVELTEST overlay", days(15), end_date=days(16), event_id=eid, audience="bureau",
                      people=[(other["id"], "attending")], by="x@x")
        assert travel.event_url_for(conn, other, eid) == f"/travel/new?event={eid}"
        assert "File a travel claim" in viewer.get("/e/tvtesttok").text
        st.set_setting(conn, "travel.enabled", "0")
        assert travel.event_url_for(conn, user, eid) is None
        st.set_setting(conn, "travel.enabled", "1")
        # and the same person can open the filing page for it; a stranger cannot
        assert viewer.get(f"/travel/new?event={eid}").status_code == 200
        r = encoder.get("/travel/new?event=%d" % (eid + 999), follow_redirects=False)
        assert r.status_code == 303 and "err=" in r.headers["location"]
    finally:
        conn.execute("DELETE FROM calendar_entry WHERE title='TRAVELTEST overlay'")
        conn.execute("DELETE FROM event WHERE id=?", (eid,)); conn.commit()


def test_next_action_follows_missing_documents_then_review(viewer, conn):
    ref = ref_of(blank(viewer, kind='reimbursement'))
    url = f'/travel/f/{ref}'
    page = viewer.get(url).text
    assert 'href="#item-dpo">Add Department Personnel Order (DPO)</a>' in page
    assert 'href="' + url + '/ready">Review and mark ready</a>' not in page
    post(viewer, url + '/item/dpo', drive_url='https://drive.google.com/file/d/dpo/view')
    page = viewer.get(url).text
    assert f'href="{url}/prepare">Prepare the missing forms</a>' in page
    # Completed attachments are collapsed; the missing forms stay expanded.
    assert '<details >' in page.split('id="item-dpo"', 1)[1].split('</li>', 1)[0]
    assert '<details open>' in page.split('id="item-appendix_a"', 1)[1].split('</li>', 1)[0]
    f = travel.get_by_ref(conn, ref)
    for item in travel.view_items(conn, f):
        if item['handling'] == 'generate':
            post(viewer, url + '/item/' + item['code'], drive_url='https://docs.google.com/document/d/form/edit')
        elif item['handling'] in ('carry', 'upload'):
            post(viewer, url + '/item/' + item['code'], drive_url='https://drive.google.com/file/d/evidence/view')
    assert f'href="{url}/ready">Review and mark ready</a>' in viewer.get(url).text
