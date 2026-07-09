"""Registration monitor — who registered for an activity (via the public link
tree) and who has answered its CSS, with status.

Two layers:
  * storage logic (isolated temp DB): the completion rule, the funnel summary,
    archived-form denominator, unattributed responses, and PII purge.
  * routes/RBAC (the shared test DB + role clients): the cap gate, the
    creator-only detail view, and the XLSX export.
"""
from __future__ import annotations
import storage as st


# --------------------------------------------------------------------------
# storage layer — deterministic, on its own throwaway database
# --------------------------------------------------------------------------

def _fresh(tmp_path):
    conn = st.connect(str(tmp_path / "mon.db"))
    st.init_db(conn)
    return conn


def _event_with_two_forms(conn, created_by="manager@test.local",
                          event_date="2026-06-12"):
    f2 = st.create_form_instance(conn, 2, "F2", event_date, topic="Event review")
    f3 = st.create_form_instance(conn, 3, "F3", event_date, topic="Talk")
    ev = st.create_event(conn, "Forum", event_date,
                         form_instance_ids=[f2, f3], created_by=created_by)
    return ev["id"], ev["event_token"], f2, f3


def test_status_three_states(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    # A answers both -> completed; B answers one -> in_progress; C none -> not_started
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", sex="F",
                        affiliation="DOH", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    st.record_response(conn, f3, [("SQD1", 6)], attendee_id=a)
    b = st.add_attendee(conn, eid, name="Ben", email="b@x.com", sex="M",
                        affiliation="NON-DOH", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=b)
    st.add_attendee(conn, eid, name="Cy", email="c@x.com", sex="M",
                    affiliation="DOH", consent_text="x")

    people = st.event_attendees_status(conn, eid)
    assert [p["name"] for p in people] == ["Ana", "Ben", "Cy"]   # consent order
    by_name = {p["name"]: p for p in people}
    assert by_name["Ana"]["status"] == "completed"   and by_name["Ana"]["n_answered"] == 2
    assert by_name["Ben"]["status"] == "in_progress" and by_name["Ben"]["n_answered"] == 1
    assert by_name["Cy"]["status"]  == "not_started" and by_name["Cy"]["n_answered"] == 0
    assert all(p["n_forms"] == 2 for p in people)


def test_summary_funnel_and_rate(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    st.record_response(conn, f3, [("SQD1", 6)], attendee_id=a)
    b = st.add_attendee(conn, eid, name="Ben", email="b@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=b)
    st.add_attendee(conn, eid, name="Cy", email="c@x.com", consent_text="x")

    s = st.event_registration_summary(conn, eid)
    assert s["registered"] == 3
    assert s["completed"] == 1
    assert s["in_progress"] == 1
    assert s["not_started"] == 1
    assert s["answered_any"] == 2
    assert s["completion_rate"] == 33      # 1/3 -> 33%
    assert s["n_forms"] == 2


def test_completed_count_matches_summary_and_is_bounded(tmp_path):
    # The Monitor "Completed CSS" card is server-rendered with summ.completed but
    # updated live off event_completed_count — they must agree, and (unlike the raw
    # response total the stream used to push) the live figure must never exceed the
    # number of registrants, even when unattributed walk-in responses pile up.
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    st.record_response(conn, f3, [("SQD1", 6)], attendee_id=a)   # Ana completed
    st.add_attendee(conn, eid, name="Cy", email="c@x.com", consent_text="x")  # not started
    # Four unattributed walk-in responses — these inflate event_response_total (the
    # old live value) well past 'registered', but must not touch the completed card.
    for _ in range(4):
        st.record_response(conn, f2, [("B6", 5)])

    s = st.event_registration_summary(conn, eid)
    completed = st.event_completed_count(conn, eid)
    assert completed == s["completed"] == 1          # tracks the header, exactly
    assert completed <= s["registered"] == 2         # bounded by registrants
    # The metric the buggy stream pushed would have shown 6 here (2 attributed
    # responses + 4 walk-in) — more "Completed" than "Registered".
    assert st.event_response_total(conn, eid) == 6
    assert completed < st.event_response_total(conn, eid)


def test_unattributed_responses_counted_separately(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, _f3 = _event_with_two_forms(conn)
    # A walk-in / QR response carries no attendee_id: not a registrant, but counted.
    st.record_response(conn, f2, [("B6", 5)])
    s = st.event_registration_summary(conn, eid)
    assert s["registered"] == 0
    assert s["unattributed"] == 1
    assert s["completion_rate"] is None      # no registrants -> no rate


def test_archived_form_drops_out_of_denominator(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    b = st.add_attendee(conn, eid, name="Ben", email="b@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=b)   # answered only f2
    # Two live forms -> in progress.
    assert st.event_attendees_status(conn, eid)[0]["status"] == "in_progress"
    # Archive the unanswered form -> denominator is now 1 -> completed.
    conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (f3,))
    conn.commit()
    p = st.event_attendees_status(conn, eid)[0]
    assert p["n_forms"] == 1 and p["status"] == "completed"


def test_purged_attendee_keeps_status_loses_pii(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", contact="0917",
                        consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    st.record_response(conn, f3, [("SQD1", 6)], attendee_id=a)
    # Purge everything (cutoff far in the future nulls all PII).
    st.purge_expired_attendees(conn, "2999-01-01")
    p = st.event_attendees_status(conn, eid)[0]
    assert p["purged"] is True
    assert p["name"] is None and p["email"] is None and p["contact"] is None
    assert p["status"] == "completed"          # the rating survives the purge


def test_list_events_filters_by_creator(tmp_path):
    conn = _fresh(tmp_path)
    _mine = _event_with_two_forms(conn, created_by="manager@test.local")
    _other = _event_with_two_forms(conn, created_by="someone@else.local")
    mine = st.list_events(conn, created_by="manager@test.local")
    assert {e["created_by"] for e in mine} == {"manager@test.local"}
    assert len(st.list_events(conn)) == 2      # None = all events


# --------------------------------------------------------------------------
# lifecycle — upcoming / ongoing / concluded classification + the home feeds
# --------------------------------------------------------------------------

def test_lifecycle_of_rules():
    today, now = "2026-06-15", "2026-06-15 10:00:00"
    # Future event day -> upcoming (registration phase).
    assert st.lifecycle_of("2026-06-20", None, today, now) == "upcoming"
    # Event day is today, no close set -> ongoing.
    assert st.lifecycle_of("2026-06-15", None, today, now) == "ongoing"
    # Past event day, no close set -> concluded.
    assert st.lifecycle_of("2026-06-10", None, today, now) == "concluded"
    # Past event day but the feedback window is still open -> ongoing.
    assert st.lifecycle_of("2026-06-10", "2026-06-16 17:00", today, now) == "ongoing"
    # Past event day, window already closed -> concluded.
    assert st.lifecycle_of("2026-06-10", "2026-06-14 17:00", today, now) == "concluded"
    # No event date at all -> concluded (safe default).
    assert st.lifecycle_of("", None, today, now) == "concluded"
    # Multi-day activity: stays ongoing across its run (start..end), no close set.
    assert st.lifecycle_of("2026-06-14", None, today, now, end_date="2026-06-17") == "ongoing"
    # Multi-day activity whose last day has passed -> concluded.
    assert st.lifecycle_of("2026-06-10", None, today, now, end_date="2026-06-12") == "concluded"
    # Multi-day activity not yet started -> upcoming (keys off the START).
    assert st.lifecycle_of("2026-06-18", None, today, now, end_date="2026-06-20") == "upcoming"


def test_upcoming_excludes_today_and_past(tmp_path):
    conn = _fresh(tmp_path)
    today = st.today_local(conn)
    _event_with_two_forms(conn, event_date="2099-01-01")        # future -> upcoming
    _event_with_two_forms(conn, event_date=today)               # today  -> ongoing
    _event_with_two_forms(conn, event_date="2000-01-01")        # past   -> concluded
    up = st.upcoming_events(conn, limit=50)
    dates = {u["event_date"] for u in up}
    assert "2099-01-01" in dates
    assert today not in dates and "2000-01-01" not in dates


def test_ongoing_picks_event_day_and_open_window(tmp_path):
    conn = _fresh(tmp_path)
    today = st.today_local(conn)
    # Today's event, no close window -> ongoing; register someone who answers one form.
    eid, _tok, f2, _f3 = _event_with_two_forms(conn, event_date=today)
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    # A future event must NOT be ongoing (it is upcoming).
    _event_with_two_forms(conn, event_date="2099-01-01")
    # A past event with no open window must NOT be ongoing (it is concluded).
    _event_with_two_forms(conn, event_date="2000-01-01")

    on = st.ongoing_events(conn, limit=50)
    assert [o["event_date"] for o in on] == [today]    # only the live one
    row = on[0]
    assert row["registered"] == 1 and row["answered_any"] == 1


def test_home_renders_ongoing_feed(manager):
    r = manager.get("/")
    assert r.status_code == 200
    assert "Ongoing — CSS collecting" in r.text


# --------------------------------------------------------------------------
# routes + RBAC — the shared test DB and the role clients
# --------------------------------------------------------------------------

def _seed_event(db_path, created_by, answer_all=False, event_date="2099-01-01"):
    # Default to a future date so the activity is 'upcoming' and shows on the
    # /monitor index (which is restricted to upcoming + ongoing).
    conn = st.connect(db_path)
    try:
        eid, tok, f2, f3 = _event_with_two_forms(conn, created_by=created_by,
                                                 event_date=event_date)
        a = st.add_attendee(conn, eid, name="Reg One", email="r1@x.com",
                            sex="F", affiliation="DOH", consent_text="x")
        st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
        if answer_all:
            st.record_response(conn, f3, [("SQD1", 6)], attendee_id=a)
    finally:
        conn.close()
    return tok


def test_monitor_requires_manage_event_cap(viewer, encoder, manager, admin):
    assert viewer.get("/monitor").status_code == 403
    assert encoder.get("/monitor").status_code == 403
    assert manager.get("/monitor").status_code == 200
    assert admin.get("/monitor").status_code == 200


def test_monitor_index_lists_managers_event(manager, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    r = manager.get("/monitor")
    assert r.status_code == 200
    assert tok in r.text                         # links to the detail page


def test_monitor_detail_shows_registrant_and_status(manager, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    r = manager.get(f"/monitor/{tok}")
    assert r.status_code == 200
    assert "Reg One" in r.text
    assert "In progress" in r.text               # answered 1 of 2 forms


def test_non_creator_manager_is_redirected(manager, db_path):
    tok = _seed_event(db_path, "admin@test.local")   # someone else's event
    r = manager.get(f"/monitor/{tok}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/monitor"


def test_admin_can_open_any_event(admin, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    assert admin.get(f"/monitor/{tok}").status_code == 200


def test_export_returns_xlsx(manager, db_path):
    tok = _seed_event(db_path, "manager@test.local", answer_all=True)
    r = manager.get(f"/monitor/{tok}/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK"                # a real .xlsx (zip) payload


# --------------------------------------------------------------------------
# close / reopen a regular (link-tree) activity + the "open until" surface
# --------------------------------------------------------------------------

def _is_closed(db_path, tok):
    conn = st.connect(db_path)
    try:
        return st.event_is_closed(conn, st.get_event(conn, tok)["id"])
    finally:
        conn.close()


def test_manage_offers_close_and_close_reopen_cycle(manager, db_path):
    """A link-tree activity (not just outside ones) can be stopped now, without
    waiting for the entry window to elapse — and reopened."""
    tok = _seed_event(db_path, "manager@test.local")

    m = manager.get(f"/activities/{tok}/manage").text
    assert "Close survey now" in m                     # the action is offered
    assert _is_closed(db_path, tok) is False

    manager.post(f"/activities/{tok}/close", follow_redirects=False)
    assert _is_closed(db_path, tok) is True
    m = manager.get(f"/activities/{tok}/manage").text
    assert "Reopen to make a correction" in m          # button swaps to Reopen
    assert "Close survey now" not in m

    manager.post(f"/activities/{tok}/reopen", follow_redirects=False)
    assert _is_closed(db_path, tok) is False


def test_non_creator_cannot_close(manager, db_path):
    """Ownership is enforced — a manager can't close someone else's activity."""
    tok = _seed_event(db_path, "admin@test.local")     # not the manager's
    r = manager.post(f"/activities/{tok}/close", follow_redirects=False)
    assert r.status_code == 303
    assert _is_closed(db_path, tok) is False


def test_monitor_shows_open_until_and_closed(manager, db_path):
    """The roster header states when the survey is open until, then flips to
    Closed once it's stopped (feedback #47)."""
    tok = _seed_event(db_path, "manager@test.local")

    # No window set yet -> open, no closing date.
    assert "no closing date set" in manager.get(f"/monitor/{tok}").text

    # Set a closing date -> "open until <date>".
    manager.post(f"/activities/{tok}/window", data={"close_at": "2099-12-31"},
                 follow_redirects=False)
    assert "until <strong>December 31, 2099</strong>" in manager.get(f"/monitor/{tok}").text

    # Stop it now -> Closed banner.
    manager.post(f"/activities/{tok}/close", follow_redirects=False)
    assert "Closed</span>" in manager.get(f"/monitor/{tok}").text


# --------------------------------------------------------------------------
# report link on a closed activity (#49)
# --------------------------------------------------------------------------

def test_monitor_links_to_comments_once_responses_exist(manager, db_path):
    """#50: the monitor page offers a 'What people said' link to the activity's
    report (anchored at its comments) — but only once someone has answered."""
    # Registered, nobody answered yet -> no comments to show, no link.
    conn = st.connect(db_path)
    try:
        eid, tok, _f2, _f3 = _event_with_two_forms(conn, created_by="manager@test.local",
                                                   event_date="2099-01-01")
        st.add_attendee(conn, eid, name="Reg", email="r@x.com", consent_text="x")
    finally:
        conn.close()
    assert "What people said" not in manager.get(f"/monitor/{tok}").text

    # A seeded event has its Form-2 answered -> the link appears, anchored to #comments.
    tok2 = _seed_event(db_path, "manager@test.local")
    page = manager.get(f"/monitor/{tok2}").text
    assert "What people said" in page
    assert "#comments" in page


def test_event_report_url_follows_the_responses(tmp_path):
    """The link points where the answers are: a Form-2 review with responses -> the
    per-activity SERVQUAL report; a bureau event answered only on the RP side, or a
    Form-3-only activity -> the Type-3 results. Both key off the min form id. No
    forms -> None."""
    conn = _fresh(tmp_path)

    # Bureau event, Form-2 answered -> per-activity report.
    eid, _tok, f2, f3 = _event_with_two_forms(conn)       # f2 + f3
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    assert st.event_report_url(conn, eid) == f"/reports/activities/{min(f2, f3)}"

    # Same shape but answered ONLY on the Form-3 side -> RP results, not an empty
    # per-activity report.
    eid2, _t2, f2b, f3b = _event_with_two_forms(conn)
    st.record_response(conn, f3b, [("B6", 6)])
    assert st.event_report_url(conn, eid2) == f"/reports?type=3&activity={min(f2b, f3b)}"

    # Form-3-only activity -> Type-3 results.
    f3c = st.create_form_instance(conn, 3, "F3", "2026-06-12", topic="Talk only")
    ev3 = st.create_event(conn, "RP only", "2026-06-12", form_instance_ids=[f3c])
    assert st.event_report_url(conn, ev3["id"]) == f"/reports?type=3&activity={f3c}"

    ev_empty = st.create_event(conn, "Empty", "2026-06-12", form_instance_ids=[])
    assert st.event_report_url(conn, ev_empty["id"]) is None


def test_closed_activity_manage_shows_report_link(manager, db_path):
    """#49: closing a bureau activity surfaces a prominent report link on its Manage
    page, pointing at that activity's report; not offered while it is still open."""
    tok = _seed_event(db_path, "manager@test.local")      # bureau f2+f3, f2 answered
    conn = st.connect(db_path)
    report_url = st.event_report_url(conn, st.get_event(conn, tok)["id"])
    conn.close()
    assert report_url.startswith("/reports/activities/")  # Form-2 side has responses

    # Not offered while open...
    assert "View the report" not in manager.get(f"/activities/{tok}/manage").text
    # ...offered once closed, linking to this activity's report.
    manager.post(f"/activities/{tok}/close", follow_redirects=False)
    page = manager.get(f"/activities/{tok}/manage").text
    assert "View the report" in page and report_url in page


# --------------------------------------------------------------------------
# delete a registrant entry (#45) — no-response cleanup only
# --------------------------------------------------------------------------

def test_delete_attendee_entry_rules(tmp_path):
    """A no-response entry deletes; a responded entry is refused (its ratings are
    in the reports); an unknown/wrong-event id is notfound."""
    conn = _fresh(tmp_path)
    eid, _tok, f2, _f3 = _event_with_two_forms(conn)
    ghost = st.add_attendee(conn, eid, name="Ghost", email="g@x.com", consent_text="x")
    ana = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=ana)

    assert st.delete_attendee_entry(conn, eid, ghost) == ("ok", None)
    assert st.get_attendee(conn, ghost) is None                 # gone

    status, n = st.delete_attendee_entry(conn, eid, ana)
    assert status == "hasresponses" and n == 1
    assert st.get_attendee(conn, ana) is not None               # kept

    assert st.delete_attendee_entry(conn, eid, 999999)[0] == "notfound"


def test_monitor_delete_attendee_route(manager, db_path):
    tok = _seed_event(db_path, "manager@test.local")            # 'Reg One' answered f2
    conn = st.connect(db_path)
    eid = st.get_event(conn, tok)["id"]
    ghost = st.add_attendee(conn, eid, name="Ghost", email="g@x.com", consent_text="x")
    conn.commit()
    answered = next(p["id"] for p in st.event_attendees_status(conn, eid) if p["n_answered"])
    conn.close()

    # The roster offers Remove for the no-response entry.
    assert "Remove" in manager.get(f"/monitor/{tok}").text

    # Delete the no-response entry -> removed.
    r = manager.post(f"/monitor/{tok}/attendee/{ghost}/delete", follow_redirects=False)
    assert r.status_code == 303 and "flash=removed" in r.headers["location"]
    conn = st.connect(db_path)
    assert st.get_attendee(conn, ghost) is None
    conn.close()

    # The responded entry is refused and stays.
    r = manager.post(f"/monitor/{tok}/attendee/{answered}/delete", follow_redirects=False)
    assert "flash=hasresponses" in r.headers["location"]
    conn = st.connect(db_path)
    assert st.get_attendee(conn, answered) is not None
    conn.close()


def test_non_creator_cannot_delete_attendee(manager, db_path):
    tok = _seed_event(db_path, "admin@test.local")              # someone else's event
    conn = st.connect(db_path)
    eid = st.get_event(conn, tok)["id"]
    ghost = st.add_attendee(conn, eid, name="Ghost", consent_text="x")
    conn.commit()
    conn.close()
    r = manager.post(f"/monitor/{tok}/attendee/{ghost}/delete", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/monitor"
    conn = st.connect(db_path)
    assert st.get_attendee(conn, ghost) is not None             # untouched
    conn.close()


# --------------------------------------------------------------------------
# per-registrant response view (feedback #57): the data behind the CSS status
# --------------------------------------------------------------------------

def test_attendee_response_detail_only_own_and_attributed(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("A", 7), ("B6", 6), ("C", 4)],
                       remarks="Great session, learned a lot.",
                       item_remarks={"B6": "Very clear speaker."}, attendee_id=a)
    # A different registrant's answer and an anonymous walk-in must NOT leak in.
    b = st.add_attendee(conn, eid, name="Ben", email="b@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 3)], attendee_id=b)
    st.record_response(conn, f2, [("B6", 2)])                    # anonymous, attendee_id NULL

    detail = st.attendee_response_detail(conn, eid, a)
    assert len(detail) == 1                                      # only the f2 she answered
    d = detail[0]
    assert d["form_instance_id"] == f2
    assert d["answers"]["B6"] == {"value": 6.0, "is_na": False}
    assert d["answers"]["A"]["value"] == 7.0
    assert d["item_remarks"]["B6"] == "Very clear speaker."
    assert d["remark"] == "Great session, learned a lot."
    # An N/A answer is preserved as such, not dropped.
    st.record_response(conn, f3, [("B1", None)], attendee_id=a)
    f3_detail = [x for x in st.attendee_response_detail(conn, eid, a)
                 if x["form_instance_id"] == f3][0]
    assert f3_detail["answers"]["B1"] == {"value": None, "is_na": True}
    # No attendee -> nothing.
    assert st.attendee_response_detail(conn, eid, None) == []


def _seed_event_with_response(db_path, created_by):
    """One activity whose single registrant answered f2 with distinctive
    ratings/comments — returns (token, attendee_id)."""
    conn = st.connect(db_path)
    try:
        eid, tok, f2, _f3 = _event_with_two_forms(conn, created_by=created_by)
        a = st.add_attendee(conn, eid, name="Reg One", email="r1@x.com",
                            consent_text="x")
        st.record_response(conn, f2, [("A", 7), ("B6", 6), ("C", 4)],
                           remarks="Loved the facilitator.",
                           item_remarks={"B6": "Knew the topic cold."}, attendee_id=a)
    finally:
        conn.close()
    return tok, a


def test_response_view_renders_answers_and_comment(manager, db_path):
    tok, aid = _seed_event_with_response(db_path, "manager@test.local")
    r = manager.get(f"/monitor/{tok}/attendee/{aid}/response")
    assert r.status_code == 200
    assert "Reg One" in r.text
    assert "Excellent" in r.text                    # C=4 -> OSQ label, distinctive
    assert "Loved the facilitator." in r.text       # the overall verbatim
    assert "Knew the topic cold." in r.text         # the per-item note


def test_roster_links_answered_registrant_to_response(manager, db_path):
    tok, aid = _seed_event_with_response(db_path, "manager@test.local")
    r = manager.get(f"/monitor/{tok}")
    assert r.status_code == 200
    assert f"/monitor/{tok}/attendee/{aid}/response" in r.text
    assert "View response" in r.text


def test_response_view_is_creator_only(manager, db_path):
    tok, aid = _seed_event_with_response(db_path, "admin@test.local")  # not the manager's
    r = manager.get(f"/monitor/{tok}/attendee/{aid}/response",
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/monitor"


def test_response_view_hides_purged_identity(manager, db_path):
    tok, aid = _seed_event_with_response(db_path, "manager@test.local")
    conn = st.connect(db_path)
    st.purge_expired_attendees(conn, "2999-01-01")               # null all PII
    conn.close()
    r = manager.get(f"/monitor/{tok}/attendee/{aid}/response")
    assert r.status_code == 200
    assert "identity removed" in r.text
    assert "Excellent" not in r.text                             # ratings not surfaced
    assert "Loved the facilitator." not in r.text
    # And the roster no longer offers the link for a purged row.
    assert f"/monitor/{tok}/attendee/{aid}/response" not in manager.get(f"/monitor/{tok}").text


def test_response_view_records_audit(manager, db_path):
    tok, aid = _seed_event_with_response(db_path, "manager@test.local")
    manager.get(f"/monitor/{tok}/attendee/{aid}/response")
    conn = st.connect(db_path)
    actions = [a["action"] for a in st.list_audit(conn, action="attendee_view_response")]
    conn.close()
    assert "attendee_view_response" in actions
