"""Item 1 of the non-bureau RP-CSS navigation fix — the /activities/outside page
deep-links each invited activity to its resource-person results.

An outside activity is Form-3-only (no Form-2 report), so its RP scores live only in
the Type-3 report's Activity filter. `st.event_rp_results_url` builds that link using
min(non-archived form id) — the same id build_events assigns and the filter matches.
"""
import storage as st


def _two_internal_rps(db_path):
    conn = st.connect(db_path)
    rows = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 ORDER BY id LIMIT 2").fetchall()
    conn.close()
    return rows[0][0], rows[1][0]


def _make_outside(client, db_path, name, date="2025-03-10"):
    rp1, rp2 = _two_internal_rps(db_path)
    r = client.post("/create", data={
        "event_type": "outside", "activity_name": name,
        "event_date": date, "venue": "Partner Hall",
        "external_org": "DOH Regional Office", "qr_mode": "combined",
        "rp_id": [str(rp1), str(rp2)], "topic": ["Cold chain", "Surveillance"],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:400]


def _event_and_forms(db_path, title):
    conn = st.connect(db_path)
    ev = conn.execute("SELECT id FROM event WHERE title=? ORDER BY id DESC LIMIT 1",
                      (title,)).fetchone()[0]
    fids = [r[0] for r in conn.execute(
        "SELECT fi.id FROM event_form ef JOIN form_instance fi ON fi.id=ef.form_instance_id "
        "WHERE ef.event_id=? AND COALESCE(fi.archived,0)=0 ORDER BY fi.id", (ev,))]
    conn.close()
    return ev, fids


def test_helper_uses_min_live_form_id_and_excludes_archived(admin, db_path):
    _make_outside(admin, db_path, "RP Link Helper ZZ")
    ev, fids = _event_and_forms(db_path, "RP Link Helper ZZ")
    assert len(fids) == 2
    conn = st.connect(db_path)
    assert st.event_rp_results_url(conn, ev) == f"/reports?type=3&activity={min(fids)}"
    # Archiving the lowest-id form shifts the representative id to the next one.
    conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (min(fids),))
    conn.commit()
    assert st.event_rp_results_url(conn, ev) == f"/reports?type=3&activity={max(fids)}"
    # All forms archived -> no live RP forms -> None.
    conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (max(fids),))
    conn.commit()
    assert st.event_rp_results_url(conn, ev) is None
    conn.close()


def test_outside_page_links_to_rp_results_when_responses_exist(admin, db_path, app_mod):
    _make_outside(admin, db_path, "RP Link Page ZZ")
    ev, fids = _event_and_forms(db_path, "RP Link Page ZZ")
    # No responses yet -> the page must NOT show a results link (nowhere to narrow to).
    page = admin.get("/activities/outside").text
    assert "RP Link Page ZZ" in page
    assert f"/reports?type=3&amp;activity={min(fids)}" not in page

    # Record an RP response on each speaker form, then the link appears.
    conn = st.connect(db_path)
    for fid in fids:
        st.record_response(conn, fid, [("B1", 6), ("B6", 6), ("B9", 6)])
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()

    page = admin.get("/activities/outside").text
    assert "View resource-person results" in page
    # The href (HTML-escaped &) points at the min live form id.
    assert f"/reports?type=3&amp;activity={min(fids)}" in page


def test_linked_id_actually_narrows_the_rp_report(admin, db_path, app_mod):
    # A unique date so this activity forms its own build_events group (events sharing
    # date+venue+organizer are merged — see _event_group_key); then min(its forms) is
    # the group's representative id, exactly what the helper builds and the filter wants.
    _make_outside(admin, db_path, "RP Link Narrow ZZ", date="2024-11-23")
    ev, fids = _event_and_forms(db_path, "RP Link Narrow ZZ")
    conn = st.connect(db_path)
    for fid in fids:
        st.record_response(conn, fid, [("B1", 6), ("B6", 6), ("B9", 6)])
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()

    # Following the deep link resolves AND the activity filter engages: the route only
    # marks the option `selected` (via sel_activity) when the id matches a build_events
    # activity, so this proves the linked id is the one the filter expects.
    r = admin.get(f"/reports?type=3&activity={min(fids)}")
    assert r.status_code == 200
    assert f'value="{min(fids)}" selected' in r.text


def test_outside_manage_links_to_rp_results_not_the_404_report(admin, db_path, app_mod):
    # Item 2: the outside Manage page's "View report" link used to point at
    # /reports/activities/<event.id>, which 404s for outside events. It now points at
    # the RP results (Type-3 filtered). The link shows in the "closed" bar.
    _make_outside(admin, db_path, "RP Link Manage ZZ", date="2024-12-07")
    ev, fids = _event_and_forms(db_path, "RP Link Manage ZZ")
    conn = st.connect(db_path)
    for fid in fids:
        st.record_response(conn, fid, [("B1", 6), ("B6", 6), ("B9", 6)])
    st.close_event_now(conn, ev)                       # so the closed bar (with the link) shows
    token = conn.execute("SELECT event_token FROM event WHERE id=?", (ev,)).fetchone()[0]
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()

    page = admin.get(f"/activities/{token}/manage").text
    assert "View resource-person results" in page
    assert f"/reports?type=3&amp;activity={min(fids)}" in page
    # The old broken link (event-table id into the SERVQUAL report) is gone.
    assert f"/reports/activities/{ev}" not in page
