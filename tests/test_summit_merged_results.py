"""Regression: a multi-session activity's report link must RESOLVE, not 404.

A summit/forum is often created as several activities on the SAME day, at the SAME
venue, organized by the SAME unit (e.g. a morning plenary + an afternoon workshop).
`dashboard_insights.build_events` collapses those into ONE activity, keyed on the
LOWEST form id in the merged group. But each session's Manage/Monitor "View the
report" link is built from THAT session's own min form id (`event_report_url`),
which — for every session except the one owning the group minimum — is a MEMBER id
of the group, not its representative.

Before the fix the report routes matched only `e["id"] == event_id`, so following a
member-id link 404'd: the organizer closed the session and could not see the CSS
results. The routes now resolve any member id to its merged activity, so every
session's link opens the (merged) report. These tests FOLLOW the link end-to-end —
a URL-string assertion alone never caught the 404.
"""
from __future__ import annotations
import storage as st

DATE = "2027-09-15"          # a date nothing else in the delivered DB uses
VENUE = "Regional Summit Center ZZ"


def _make_session(client, name):
    """Create a bureau session (Form-2 event review only — no speaker, so the test
    doesn't depend on the DB carrying an internal resource person) on the shared
    date+venue+organizer, then answer its event review so it has a SERVQUAL report."""
    r = client.post("/create", data={
        "event_type": "bureau", "activity_name": name,
        "event_date": DATE, "venue": VENUE, "qr_mode": "combined",
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:400]


def _event_and_forms(db_path, title):
    conn = st.connect(db_path)
    ev = conn.execute("SELECT id, event_token FROM event WHERE title=? ORDER BY id DESC LIMIT 1",
                      (title,)).fetchone()
    fids = [r[0] for r in conn.execute(
        "SELECT fi.id FROM event_form ef JOIN form_instance fi ON fi.id=ef.form_instance_id "
        "WHERE ef.event_id=? AND COALESCE(fi.archived,0)=0 ORDER BY fi.id", (ev[0],))]
    conn.close()
    return ev[0], ev[1], fids


def _answer_f2(db_path, fid, n=12):
    conn = st.connect(db_path)
    ans = [("A", 6)] + [(f"B{i}", 6) for i in range(1, 10)] + [("C", 4)]
    for _ in range(n):
        st.record_response(conn, fid, ans)
    conn.commit(); conn.close()


def test_second_session_report_link_resolves_not_404(manager, db_path, app_mod):
    _make_session(manager, "Summit Session One ZZ")
    _make_session(manager, "Summit Session Two ZZ")
    e1, t1, f1 = _event_and_forms(db_path, "Summit Session One ZZ")
    e2, t2, f2 = _event_and_forms(db_path, "Summit Session Two ZZ")
    # Distinct event records, and the second's forms sort AFTER the first's — so its
    # own min id is a MEMBER of the merged group, not the representative.
    assert e1 != e2 and min(f2) > min(f1)

    _answer_f2(db_path, f1[0])
    _answer_f2(db_path, f2[0])
    conn = st.connect(db_path)
    st.close_event_now(conn, e2)                       # close the SECOND session
    url2 = st.event_report_url(conn, e2)               # link the Manage page will show
    conn.close()
    app_mod.invalidate_atoms()

    # The helper still keys off the session's own min form id (a member id)…
    assert url2 == f"/reports/activities/{min(f2)}"
    # …and the Manage page surfaces it in the closed banner.
    page = manager.get(f"/activities/{t2}/manage").text
    assert "View the report" in page
    assert f"/reports/activities/{min(f2)}" in page

    # Following it must RESOLVE to the merged activity's report, not 404.
    r = manager.get(url2, follow_redirects=True)
    assert r.status_code == 200, f"member-id report link 404'd: {url2}"
    # It renders a real SERVQUAL scorecard (merged), not an empty/None page.
    assert ("Reliability" in r.text or "Responsiveness" in r.text)


def test_type3_filter_resolves_member_id(app_mod):
    """The Resource-person report's Activity filter engages on a member id too:
    `_rp_activity_scope` resolves it to the merged group's representative option."""
    import app as app_module
    opts = [{"value": "10", "text": "Merged Summit", "instance_ids": [10, 11, 12]}]
    # A member id (12) resolves to the representative option (value "10").
    val, label, ids = app_module._rp_activity_scope(opts, "12")
    assert val == "10" and label == "Merged Summit" and ids == [10, 11, 12]
    # The representative id itself still matches directly.
    val, label, ids = app_module._rp_activity_scope(opts, "10")
    assert val == "10" and ids == [10, 11, 12]
    # A genuinely unknown id still yields the empty, clearly-labelled view.
    val, label, ids = app_module._rp_activity_scope(opts, "999")
    assert val == "999" and label == "this activity" and ids == []
