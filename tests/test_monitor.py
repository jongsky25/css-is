"""Registration monitor — who registered for an activity (via the public link
tree) and who has answered its CSS, with status.

Two layers:
  * storage logic (isolated temp DB): the completion rule, the funnel summary,
    archived-form denominator, unattributed responses, and PII purge.
  * routes/RBAC (the shared test DB + role clients): the cap gate, the
    creator-only detail view, and the XLSX export.
"""
from __future__ import annotations
import pytest
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


def test_completed_never_exceeds_registered_with_walk_ins(tmp_path):
    # The Monitor funnel (server render AND the live SSE payload) is
    # event_registration_summary. 'completed' counts registrants who finished, so it
    # is always bounded by 'registered' — unlike event_response_total (the value the
    # old live stream pushed), which counts every response row including unattributed
    # walk-in / QR / paper and can read higher than the number of people registered.
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
    st.record_response(conn, f3, [("SQD1", 6)], attendee_id=a)   # Ana completed
    st.add_attendee(conn, eid, name="Cy", email="c@x.com", consent_text="x")  # not started
    for _ in range(4):
        st.record_response(conn, f2, [("B6", 5)])                # 4 unattributed walk-ins

    s = st.event_registration_summary(conn, eid)
    assert s["completed"] == 1 and s["registered"] == 2
    assert s["completed"] <= s["registered"]         # the invariant, always
    # Completion rate counts everyone who took part: each of the 4 walk-ins is a
    # completed response, so it is (completed + unattributed) / (registered +
    # unattributed) = (1 + 4) / (2 + 4) = 5/6 -> 83%, and always <= 100.
    assert s["unattributed"] == 4
    assert s["completion_rate"] == 83
    assert s["completion_rate"] <= 100
    # The old live value would have shown 6 here (2 attributed + 4 walk-in),
    # i.e. more "Completed" than "Registered". The funnel figure cannot.
    assert st.event_response_total(conn, eid) == 6
    assert s["completed"] < st.event_response_total(conn, eid)


def test_completion_rate_hits_100_only_when_all_registrants_complete(tmp_path):
    # 100% must mean truly complete: a near-complete event must not round up to 100.
    assert st._completion_rate(0, 0) is None            # no registrants
    assert st._completion_rate(1, 3) == 33
    assert st._completion_rate(199, 200) == 99          # 99.5% must NOT round to 100
    assert st._completion_rate(1999, 2000) == 99        # 99.95% still capped below 100
    assert st._completion_rate(40, 40) == 100           # only when completed == registered
    assert st._completion_rate(0, 5) == 0

    # End to end through the summary: one registrant left unfinished => 99, not 100.
    conn = _fresh(tmp_path)
    eid, _tok, f2, _f3 = _event_with_two_forms(conn)
    conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (_f3,))  # single form
    conn.commit()
    done = [st.add_attendee(conn, eid, name=f"P{i}", email=f"p{i}@x.com",
                            consent_text="x") for i in range(199)]
    for aid in done:
        st.record_response(conn, f2, [("B6", 6)], attendee_id=aid)
    st.add_attendee(conn, eid, name="Late", email="late@x.com", consent_text="x")  # 200th, unfinished
    s = st.event_registration_summary(conn, eid)
    assert s["registered"] == 200 and s["completed"] == 199
    assert s["completion_rate"] == 99                   # not a misleading 100%


def test_respondent_target_overrides_completion_denominator(tmp_path):
    """A manager-entered respondent count replaces the registered denominator and
    counts walk-ins toward the numerator, so an activity whose real attendance the
    roster never captured reads honestly."""
    conn = _fresh(tmp_path)
    eid, tok, f2, _f3 = _event_with_two_forms(conn)
    conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (_f3,))  # single form
    conn.commit()
    # 2 registrants complete, plus 3 walk-ins -> 5 respondents in.
    for i in range(2):
        aid = st.add_attendee(conn, eid, name=f"R{i}", email=f"r{i}@x.com", consent_text="x")
        st.record_response(conn, f2, [("B6", 6)], attendee_id=aid)
    for _ in range(3):
        st.record_response(conn, f2, [("B6", 5)])

    # No override yet: the default everyone-who-took-part rate,
    # (completed + unattributed) / (registered + unattributed) = (2 + 3)/(2 + 3) = 100.
    s = st.event_registration_summary(conn, eid)
    assert s["denominator_source"] == "registered"
    assert s["respondent_target"] is None
    assert s["completion_rate"] == 100

    # Override to 10 expected: (2 completed + 3 walk-ins) / 10 -> 50%.
    assert st.set_event_respondent_target(conn, eid, 10) == 10
    assert st.get_event(conn, tok)["respondent_target"] == 10
    s = st.event_registration_summary(conn, eid)
    assert s["denominator_source"] == "target"
    assert s["respondent_target"] == 10
    assert s["completion_rate"] == 50           # (2 + 3) / 10

    # Clearing goes back to the live registered count.
    assert st.set_event_respondent_target(conn, eid, None) is None
    assert st.get_event(conn, tok)["respondent_target"] is None
    assert st.event_registration_summary(conn, eid)["denominator_source"] == "registered"


def test_completion_rate_target_clamps_at_100(tmp_path):
    # The helper never reads above 100 even if a target is later exceeded, and is
    # None when there is no denominator to divide by.
    assert st._completion_rate_target(5, 10) == 50
    assert st._completion_rate_target(10, 10) == 100
    assert st._completion_rate_target(13, 10) == 100        # later drift never > 100%
    assert st._completion_rate_target(0, 10) == 0
    assert st._completion_rate_target(4, 0) is None         # no target -> no rate


def test_unattributed_responses_counted_separately(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, _f3 = _event_with_two_forms(conn)
    # A walk-in / QR response carries no attendee_id: not a registrant, but counted.
    st.record_response(conn, f2, [("B6", 5)])
    s = st.event_registration_summary(conn, eid)
    assert s["registered"] == 0
    assert s["unattributed"] == 1
    # No registrants, but one walk-in that answered -> everyone who took part is
    # done, so (0 + 1) / (0 + 1) = 100%. The rate is only None with nobody at all.
    assert s["completion_rate"] == 100


def test_completion_rate_includes_not_pre_registered(tmp_path):
    """The completion rate folds the not-pre-registered responses into BOTH the
    numerator and the denominator: each walk-in / QR / paper answer counts as a
    completed response out of everyone who took part."""
    conn = _fresh(tmp_path)
    eid, _tok, f2, _f3 = _event_with_two_forms(conn)
    conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (_f3,))  # single form
    conn.commit()
    a = st.add_attendee(conn, eid, name="Ana", email="a@x.com", consent_text="x")
    st.record_response(conn, f2, [("B6", 6)], attendee_id=a)                 # completed
    st.add_attendee(conn, eid, name="Cy", email="c@x.com", consent_text="x")  # not started
    st.record_response(conn, f2, [("B6", 5)])                               # 1 walk-in

    s = st.event_registration_summary(conn, eid)
    assert s["registered"] == 2 and s["completed"] == 1 and s["unattributed"] == 1
    # (completed + unattributed) / (registered + unattributed) = 2/3 -> 67%.
    assert s["completion_rate"] == 67

    # 100% needs every REGISTERED person finished — walk-ins can't push it there
    # on their own. Cy finishing (all registrants done) makes it (2 + 1)/(2 + 1).
    st.record_response(conn, f2, [("B6", 6)],
                       attendee_id=next(p["id"] for p in st.event_attendees_status(conn, eid)
                                        if p["status"] == "not_started"))
    s2 = st.event_registration_summary(conn, eid)
    assert s2["completed"] == 2 and s2["registered"] == 2
    assert s2["completion_rate"] == 100


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
    r = manager.get("/css")
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


def test_concluded_activity_stays_reachable_from_monitor(manager, db_path):
    live = _seed_event(db_path, "manager@test.local")
    done = _seed_event(db_path, "manager@test.local", event_date="2000-01-01")
    # The default list is live-only; the concluded one is on the Concluded view.
    assert live in manager.get("/monitor").text
    assert done not in manager.get("/monitor").text
    r = manager.get("/monitor?view=concluded")
    assert r.status_code == 200
    assert done in r.text and live not in r.text
    # ...and its roster still opens.
    assert "Reg One" in manager.get(f"/monitor/{done}").text


def test_concluded_view_skips_activities_nobody_registered_for(manager, db_path):
    conn = st.connect(db_path)
    try:
        _eid, tok, _f2, _f3 = _event_with_two_forms(
            conn, created_by="manager@test.local", event_date="2000-01-01")
    finally:
        conn.close()
    assert tok not in manager.get("/monitor?view=concluded").text


def test_monitor_detail_shows_registrant_and_status(manager, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    r = manager.get(f"/monitor/{tok}")
    assert r.status_code == 200
    assert "Reg One" in r.text
    assert "In progress" in r.text               # answered 1 of 2 forms
    # the registration link has a real Copy control, not just a bare <code>
    assert 'id="regCopy"' in r.text and 'id="regLink"' in r.text


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


def _respondent_target(db_path, tok):
    conn = st.connect(db_path)
    try:
        return st.get_event(conn, tok)["respondent_target"]
    finally:
        conn.close()


def test_respondent_target_route_sets_clears_and_rejects(manager, db_path):
    """The manage-page editor: a creator sets the override, a below-actual value is
    rejected (nothing saved), a non-number is rejected, and blank clears it."""
    tok = _seed_event(db_path, "manager@test.local")   # 1 registrant answered f2 (in progress)

    # The editor is offered on the manage page.
    assert "Number of respondents" in manager.get(f"/activities/{tok}/manage").text

    # Set a valid target -> saved, and the Monitor labels the rate card.
    r = manager.post(f"/activities/{tok}/respondents", data={"respondent_target": "40"},
                     follow_redirects=False)
    assert r.status_code == 303 and "#respondents" in r.headers["location"]
    assert _respondent_target(db_path, tok) == 40
    assert "of 40 expected" in manager.get(f"/monitor/{tok}").text

    # Below the actual respondent count (0 here, since nobody has *completed* both
    # forms and there are no walk-ins) is fine; a negative / non-number is rejected.
    r = manager.post(f"/activities/{tok}/respondents", data={"respondent_target": "-5"},
                     follow_redirects=False)
    assert "err=badtarget" in r.headers["location"]
    assert _respondent_target(db_path, tok) == 40      # unchanged
    r = manager.post(f"/activities/{tok}/respondents", data={"respondent_target": "abc"},
                     follow_redirects=False)
    assert "err=badtarget" in r.headers["location"]
    assert _respondent_target(db_path, tok) == 40      # unchanged

    # Blank clears the override.
    r = manager.post(f"/activities/{tok}/respondents", data={"respondent_target": ""},
                     follow_redirects=False)
    assert r.status_code == 303
    assert _respondent_target(db_path, tok) is None


def test_respondent_target_rejects_below_actual(manager, db_path):
    """A target below the responses already collected is refused, so completion can
    never be gamed above 100% at save time."""
    tok = _seed_event(db_path, "manager@test.local", answer_all=True)  # 1 completed
    r = manager.post(f"/activities/{tok}/respondents", data={"respondent_target": "0"},
                     follow_redirects=False)
    assert "err=targettoolow" in r.headers["location"]
    assert _respondent_target(db_path, tok) is None    # nothing saved


def test_non_creator_cannot_set_respondent_target(manager, db_path):
    tok = _seed_event(db_path, "admin@test.local")     # someone else's event
    r = manager.post(f"/activities/{tok}/respondents", data={"respondent_target": "20"},
                     follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/e/{tok}"
    assert _respondent_target(db_path, tok) is None


def test_admin_can_set_respondent_target_on_any_event(admin, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    r = admin.post(f"/activities/{tok}/respondents", data={"respondent_target": "25"},
                   follow_redirects=False)
    assert r.status_code == 303
    assert _respondent_target(db_path, tok) == 25


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


# --------------------------------------------------------------------------
# who a management feed shows — the ORGANISING section, not the app role
# --------------------------------------------------------------------------
#
# /monitor and /activities/outside used to short-circuit on role == "admin" for
# the whole bureau and fall back to created_by for everyone else. Both halves
# were wrong at once: a section head who also administers the app monitored
# every section, and an administrator filing an activity FOR another section
# carried it on their list for good while the section running it never saw it.
#
# Every helper below opens, commits and CLOSES before handing control back. The
# app opens its own connection per request against the same file, and a reader
# left open across a request is how this suite deadlocks on "database is locked".

import contextlib
import sqlite3


def _unit(db_path, path):
    """The org unit at `path`, created once. Returns its id."""
    conn = st.connect(db_path)
    try:
        row = conn.execute("SELECT id FROM org_unit WHERE path=?", (path,)).fetchone()
        if row:
            return row[0]
        short = path.rsplit("/", 1)[-1]
        uid = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (short, short, "section", path)).lastrowid
        conn.commit()
        return uid
    finally:
        conn.close()


def _person(db_path, name, path):
    # The unit is resolved BEFORE the connection opens. Nesting a second
    # connection inside an open write is the other way this suite deadlocks.
    org = _unit(db_path, path)
    conn = st.connect(db_path)
    try:
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES (?,1,?)",
            (name, org)).lastrowid
        conn.commit()
        return rp
    finally:
        conn.close()


@contextlib.contextmanager
def _seated(app_mod, username, path, *, name="SC-Seat"):
    """Place an account in a directory unit for one test, and undo it after —
    app_mod's database is session-scoped, and a stray directory link silently
    changes what every later test can see."""
    rp = _person(app_mod.DB, name, path)
    conn = st.connect(app_mod.DB)
    try:
        u = st.get_admin_user(conn, username)
        was = conn.execute("SELECT rp_id FROM admin_user WHERE id=?",
                           (u["id"],)).fetchone()[0]
        conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp, u["id"]))
        conn.commit()
    finally:
        conn.close()
    try:
        yield {"rp_id": rp, "unit_id": _unit(app_mod.DB, path), "user_id": u["id"]}
    finally:
        conn = st.connect(app_mod.DB)
        try:
            conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (was, u["id"]))
            conn.commit()
            # Best effort. A test that seeded a Form 3 against this person leaves
            # a real foreign key behind, and unlinking the ACCOUNT is what
            # actually restores the scope — the stray directory row is inert.
            try:
                conn.execute("DELETE FROM resource_person WHERE id=?", (rp,))
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
        finally:
            conn.close()


def _seed_scoped_event(db_path, created_by, *, lead_org_id=None, rp_id=None,
                       kind="bureau", event_date="2099-01-01"):
    """One event owned by `lead_org_id` (bureau) or spoken at by `rp_id`
    (invited). An invited activity carries NO organising unit — that is exactly
    how the app creates one, and it is why the speaker's section has to answer."""
    conn = st.connect(db_path)
    try:
        ids = [st.create_form_instance(conn, 3, "F3", event_date, topic="Talk",
                                       rp_id=rp_id, lead_org_id=lead_org_id)]
        if kind == "bureau":
            ids.insert(0, st.create_form_instance(conn, 2, "F2", event_date,
                                                  topic="Event review",
                                                  lead_org_id=lead_org_id))
        ev = st.create_event(conn, "Scoped activity", event_date,
                             lead_org_id=lead_org_id, form_instance_ids=ids,
                             created_by=created_by, event_kind=kind)
        return ev["event_token"]
    finally:
        conn.close()


def test_event_in_team_scope_needs_no_database():
    """The predicate itself, away from any route."""
    ours = {"lead_path": "A/S1", "rp_paths": []}
    theirs = {"lead_path": "A/S9", "rp_paths": []}
    spoke = {"lead_path": None, "rp_paths": ["A/S1/Team"]}
    assert st.event_in_team_scope(ours, "A/S1")
    assert not st.event_in_team_scope(theirs, "A/S1")
    assert st.event_in_team_scope(spoke, "A/S1")          # a descendant counts
    assert not st.event_in_team_scope({"lead_path": None, "rp_paths": []}, "A/S1")
    assert st.event_in_team_scope(theirs, None)           # None scope = bureau-wide
    # S1 must not swallow S10 — the boundary a bare startswith gets wrong
    assert not st.event_in_team_scope({"lead_path": "A/S10", "rp_paths": []}, "A/S1")


def test_list_events_drops_what_is_outside_the_team_scope(tmp_path):
    conn = _fresh(tmp_path)
    try:
        mine = conn.execute("INSERT INTO org_unit(name, short_name, level, path)"
                            " VALUES ('S1','S1','section','TS/S1')").lastrowid
        yours = conn.execute("INSERT INTO org_unit(name, short_name, level, path)"
                             " VALUES ('S9','S9','section','TS/S9')").lastrowid
        for org in (mine, yours):
            f2 = st.create_form_instance(conn, 2, "F2", "2026-06-12",
                                         topic="Review", lead_org_id=org)
            st.create_event(conn, f"Event {org}", "2026-06-12", lead_org_id=org,
                            form_instance_ids=[f2], created_by="anyone@x.local")
        conn.commit()
        scoped = st.list_events(conn, team_scope=("TS/S1", "unit"))
        assert [e["lead_path"] for e in scoped] == ["TS/S1"]
        assert len(st.list_events(conn)) == 2            # unscoped still sees both
    finally:
        conn.close()


def test_an_admin_filing_for_another_section_does_not_keep_it_on_their_monitor(
        app_mod, admin, db_path):
    """The regression this section exists for. Creating an activity is a fact
    about the app, not about whose work it is."""
    other = _unit(db_path, "SCOPE/D1/S9")
    with _seated(app_mod, "admin@test.local", "SCOPE/D1/S1") as me:
        theirs = _seed_scoped_event(db_path, "admin@test.local", lead_org_id=other)
        ours = _seed_scoped_event(db_path, "someone@else.local",
                                  lead_org_id=me["unit_id"])
        html = admin.get("/monitor").text
        assert theirs not in html          # S9's, however typed it in
        assert ours in html                # S1's, whoever typed it in


def test_a_sibling_section_is_not_a_prefix_match_on_the_feed(app_mod, admin, db_path):
    sib = _unit(db_path, "SCOPE/D1/S10")
    with _seated(app_mod, "admin@test.local", "SCOPE/D1/S1"):
        tok = _seed_scoped_event(db_path, "admin@test.local", lead_org_id=sib)
        assert tok not in admin.get("/monitor").text


def test_an_invited_activity_is_placed_by_the_speakers_section(
        app_mod, admin, db_path):
    """An invited activity has no organising unit of ours at all, so the section
    whose person was invited is the only thing that can place it — and is also
    the right answer."""
    far_rp = _person(db_path, "SC-Far", "SCOPE/D2/S8")
    with _seated(app_mod, "admin@test.local", "SCOPE/D1/S1") as me:
        ours = _seed_scoped_event(db_path, "someone@else.local",
                                  rp_id=me["rp_id"], kind="outside")
        theirs = _seed_scoped_event(db_path, "admin@test.local",
                                    rp_id=far_rp, kind="outside")
        html = admin.get("/activities/outside").text
        assert ours in html                # one of ours was the resource person
        assert theirs not in html          # nobody of ours was, however filed it


def test_an_unlinked_account_still_sees_what_it_created(admin, db_path):
    """No directory record means no team to scope by, and _path_in_scope(p, None)
    is True for everything — so it falls back to what this account created
    rather than to the whole bureau. Blanking a management page is a lockout,
    not a safety measure."""
    mine = _seed_scoped_event(db_path, "admin@test.local")
    theirs = _seed_scoped_event(db_path, "someone@else.local")
    html = admin.get("/monitor").text          # the seeded accounts carry no rp_id
    assert mine in html
    assert theirs not in html


def test_a_bureau_grant_is_how_a_seat_gets_every_section_back(
        app_mod, admin, db_path):
    """The named, audited, revocable way past your own unit — a role is not."""
    far = _unit(db_path, "SCOPE/D3/S7")
    with _seated(app_mod, "admin@test.local", "SCOPE/D1/S1") as me:
        tok = _seed_scoped_event(db_path, "someone@else.local", lead_org_id=far)
        assert tok not in admin.get("/monitor").text          # seated in S1

        conn = st.connect(db_path)
        try:
            st.set_bureau_access(conn, me["user_id"], "all")
        finally:
            conn.close()
        try:
            assert tok in admin.get("/monitor").text
        finally:
            conn = st.connect(db_path)
            st.set_bureau_access(conn, me["user_id"], "")
            conn.close()


# ---- "Remind N not finished" (Spot Feedback, Sept 23) -------------------------

def _seed_remind_roster(db_path):
    """Reg One in progress (email), Done Dan completed (email), No-mail Nia
    not started with no email — only Reg One is reachable and unfinished."""
    conn = st.connect(db_path)
    try:
        eid, tok, f2, f3 = _event_with_two_forms(conn, event_date="2099-01-01")
        a = st.add_attendee(conn, eid, name="Reg One", email="r1@x.com", consent_text="x")
        st.record_response(conn, f2, [("B6", 6)], attendee_id=a)
        d = st.add_attendee(conn, eid, name="Done Dan", email="dan@x.com", consent_text="x")
        st.record_response(conn, f2, [("B6", 6)], attendee_id=d)
        st.record_response(conn, f3, [("SQD1", 6)], attendee_id=d)
        st.add_attendee(conn, eid, name="No-mail Nia", email=None, consent_text="x")
    finally:
        conn.close()
    return eid, tok


@pytest.fixture()
def sent_mail(app_mod, monkeypatch):
    out = []
    monkeypatch.setattr(app_mod.mailer, "email_configured", lambda: True)
    monkeypatch.setattr(app_mod.mailer, "send", lambda to, subject, body, html=None: (
        out.append({"to": to, "subject": subject, "body": body, "html": html}),
        {"sent": True, "detail": "Email sent."})[1])
    return out


def test_remind_unfinished_emails_only_reachable_unfinished_registrants(
        manager, db_path, sent_mail):
    _eid, tok = _seed_remind_roster(db_path)
    page = manager.get(f"/monitor/{tok}").text
    assert 'id="remindAll"' in page and "Remind 1 not finished" in page

    r = manager.post(f"/monitor/{tok}/remind-unfinished")
    assert r.status_code == 200 and r.json()["queued"] == 1
    assert [m["to"] for m in sent_mail] == ["r1@x.com"]          # not Dan, not Nia
    assert f"/e/{tok}/resume?rt=" in sent_mail[0]["body"]        # their own resume link
    assert "Forum" in sent_mail[0]["subject"]


def test_remind_unfinished_holds_a_cooldown(manager, db_path, sent_mail):
    """A double-click or a second organizer can't mail everyone twice."""
    _eid, tok = _seed_remind_roster(db_path)
    assert manager.post(f"/monitor/{tok}/remind-unfinished").json()["queued"] == 1
    r = manager.post(f"/monitor/{tok}/remind-unfinished")
    assert r.status_code == 429 and r.json()["queued"] == 0
    assert len(sent_mail) == 1
    page = manager.get(f"/monitor/{tok}").text
    assert "Last reminder sent" in page
    assert 'id="remindAll" data-count="1"\n            disabled' in page


def test_remind_unfinished_refuses_a_closed_activity(manager, db_path, sent_mail):
    eid, tok = _seed_remind_roster(db_path)
    conn = st.connect(db_path)
    try:
        st.close_event_now(conn, eid)
    finally:
        conn.close()
    r = manager.post(f"/monitor/{tok}/remind-unfinished")
    assert r.status_code == 409 and sent_mail == []
    assert 'id="remindAll"' not in manager.get(f"/monitor/{tok}").text


def test_remind_unfinished_without_email_sends_nothing(manager, db_path, app_mod, monkeypatch):
    _eid, tok = _seed_remind_roster(db_path)
    monkeypatch.setattr(app_mod.mailer, "email_configured", lambda: False)
    r = manager.post(f"/monitor/{tok}/remind-unfinished")
    assert r.json()["queued"] == 0 and "isn't set up" in r.json()["detail"]


def test_remind_unfinished_requires_manage_rights(viewer, db_path):
    _eid, tok = _seed_remind_roster(db_path)
    assert viewer.post(f"/monitor/{tok}/remind-unfinished").status_code in (403, 404)


def test_remind_unfinished_refuses_once_the_window_has_lapsed(manager, db_path, sent_mail):
    """Past the close time a resume link lands on a closed form — no reminder."""
    eid, tok = _seed_remind_roster(db_path)
    conn = st.connect(db_path)
    try:
        st.set_event_window(conn, eid, "2020-01-01T08:00", "2020-01-02T17:00")
    finally:
        conn.close()
    r = manager.post(f"/monitor/{tok}/remind-unfinished")
    assert r.status_code == 409 and "window" in r.json()["detail"] and sent_mail == []
    assert 'id="remindAll"' not in manager.get(f"/monitor/{tok}").text


def test_home_tasks_link_an_organizers_open_activities_straight_to_monitor(app_mod, db_path):
    """Skips the /css → /monitor hop: an organizer's own upcoming/ongoing
    activities sit in their to-do with a direct Monitor link."""
    import office_connect as oc
    _eid, tok = _seed_remind_roster(db_path)
    conn = st.connect(db_path)
    try:
        u = st.get_admin_user(conn, "manager@test.local")
        tasks = oc.home_tasks(conn, {"id": u["id"], "username": u["username"],
                                     "role": u["role"]})
    finally:
        conn.close()
    urls = [t["url"] for t in tasks]
    assert f"/monitor/{tok}" in urls
    t = next(t for t in tasks if t["url"] == f"/monitor/{tok}")
    assert "finished" in t["detail"]


# --------------------------------------------------------------------------
# Archive an activity (retire an accidental duplicate)
# --------------------------------------------------------------------------

def test_archive_hides_event_and_restores(tmp_path):
    conn = _fresh(tmp_path)
    eid, _tok, f2, f3 = _event_with_two_forms(conn)
    assert not st.event_is_archived(conn, eid)
    assert [e["id"] for e in st.list_events(conn)] == [eid]
    st.set_event_archived(conn, eid, archived=True)
    assert st.event_is_archived(conn, eid)
    assert st.list_events(conn) == []
    # restoring the forms (what Archived activities does) un-archives the event
    st.set_form_archived(conn, f2, archived=False)
    st.set_form_archived(conn, f3, archived=False)
    assert not st.event_is_archived(conn, eid)
    assert len(st.list_events(conn)) == 1


def test_archive_route_hides_from_monitor_and_closes_public_link(manager, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    assert tok in manager.get("/monitor").text
    assert "Archive this activity" in manager.get(f"/monitor/{tok}").text
    r = manager.post(f"/monitor/{tok}/archive", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/monitor")
    assert tok not in manager.get("/monitor").text
    assert manager.get(f"/e/{tok}").status_code == 404
    manager.post(f"/monitor/{tok}/archive", data={"restore": "1"})
    assert tok in manager.get("/monitor").text
    assert manager.get(f"/e/{tok}").status_code == 200


def test_archive_route_refused_for_non_owner(viewer, db_path):
    tok = _seed_event(db_path, "manager@test.local")
    r = viewer.post(f"/monitor/{tok}/archive", follow_redirects=False)
    assert r.status_code in (303, 403)
    from storage import connect
    c = connect(db_path)
    ev = st.get_event(c, tok)
    assert not st.event_is_archived(c, ev["id"])


def test_monitor_page_script_leaves_submit_buttons_alone(manager, db_path):
    """The copy/resend script disables the button it handles; bound to the Archive
    / Remove submit buttons it cancels their form submission, so it must only
    target buttons carrying data-act."""
    tok = _seed_event(db_path, "manager@test.local")
    html = manager.get(f"/monitor/{tok}").text
    assert "Archive this activity" in html
    assert "querySelectorAll('.act-btn[data-act]')" in html
    assert "querySelectorAll('.act-btn')" not in html
