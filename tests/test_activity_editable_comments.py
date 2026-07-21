"""Per-activity "edit the words" (encoding) comment list — Spot Feedback #70.

The activity report's on-screen digest shows only a handful of comments; the
encoder underneath must list the COMPLETE set so any comment is reachable. This
locks in `storage.activity_editable_comments`: what it includes (every overall
remark + every free-text item note), what it excludes (SEX/AFFIL/RESPONSE_NO
metadata), the blank-item_id contract the edit route relies on, and that an edit
round-trips through the existing update helpers.
"""
from datetime import timedelta

import storage as st


_http_seq = [0]


def _http_activity(app_mod):
    """A lone Form-2 activity (build_events keys it by its own form id) with a
    couple of comments, so /reports/activities/<id> has something to edit. Each
    call gets a UNIQUE venue — build_events groups F2s by (date, venue, org), so
    a shared venue would collapse successive activities into one event group and
    the later form's id would not be an event id (a 404)."""
    _http_seq[0] += 1
    conn = st.connect(app_mod.DB)
    recent = (app_mod._today_local() - timedelta(days=2)).isoformat()
    fid = st.create_form_instance(conn, 2, "F2", recent, topic="HTTP Encode QQ",
                                  venue=f"HTTP Encode hall #{_http_seq[0]}", created_by="me@x")
    st.record_response(conn, fid, [("B1", 6)], remarks="Loved the venue choice")
    st.record_response(conn, fid, [("B1", 5)], remarks="Session ran over time")
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()
    return fid


def _activity(app_mod):
    """A lone Form-2 activity with three responses carrying assorted comments:
      #1 overall remark only,
      #2 overall remark + a free-text item note (B4) + a demographic note (SEX),
      #3 no overall remark, only a free-text item note (B2).
    Returns (conn, response_ids newest-first order is by submitted time)."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    recent = (app_mod._today_local() - timedelta(days=2)).isoformat()
    fid = st.create_form_instance(conn, 2, "F2", recent, topic="Encode QQ",
                                  venue="Encode QQ hall", created_by="me@x")
    r1 = st.record_response(conn, fid, [("B1", 6)], remarks="Great facilitators")
    r2 = st.record_response(conn, fid, [("B1", 5)], remarks="Venue too cold",
                            item_remarks={"B4": "More handouts please", "SEX": "M"})
    r3 = st.record_response(conn, fid, [("B1", 6)], remarks="",
                            item_remarks={"B2": "Start on time", "RESPONSE_NO": "12"})
    conn.commit()
    return conn, [r1, r2, r3]


def test_lists_every_comment_and_excludes_metadata(app_mod):
    conn, (r1, r2, r3) = _activity(app_mod)
    try:
        rows = st.activity_editable_comments(conn, [r1, r2, r3])
        # keyed by (rid, item_id) -> text
        got = {(c["response_id"], c["item_id"]): c["text"] for c in rows}
        assert got == {
            (r1, ""):   "Great facilitators",     # overall remark
            (r2, ""):   "Venue too cold",         # overall remark
            (r2, "B4"): "More handouts please",   # free-text item note kept
            (r3, "B2"): "Start on time",          # note kept even with no overall remark
        }
        # SEX (demographic) and RESPONSE_NO (encoding metadata) never appear.
        assert not any(c["item_id"] in ("SEX", "AFFIL", "RESPONSE_NO") for c in rows)
        # The overall comment carries a BLANK item_id — the contract the
        # /responses/<id>/edit-remark route uses to update response.remarks.
        overall = next(c for c in rows if c["response_id"] == r1)
        assert overall["item_id"] == "" and overall["kind"] == "overall"
        item = next(c for c in rows if c["item_id"] == "B4")
        assert item["kind"] == "item"
        # every entry is labelled for the editor UI
        assert all(c.get("activity") and c.get("form_id") for c in rows)
    finally:
        conn.close()


def test_empty_when_no_comments(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    try:
        recent = (app_mod._today_local() - timedelta(days=2)).isoformat()
        fid = st.create_form_instance(conn, 2, "F2", recent, topic="Silent QQ",
                                      venue="Silent QQ hall", created_by="me@x")
        rid = st.record_response(conn, fid, [("B1", 6)])   # a rating, no words
        conn.commit()
        assert st.activity_editable_comments(conn, [rid]) == []
    finally:
        conn.close()


def test_edit_round_trips_through_the_helpers(app_mod):
    """The editor posts to the existing edit-remark route, which calls these
    update helpers — confirm an overall and an item edit both land and then read
    back through activity_editable_comments."""
    conn, (r1, r2, r3) = _activity(app_mod)
    try:
        ok, before = st.update_response_remarks(conn, r1, "Great facilitators (fixed)")
        assert ok and before == "Great facilitators"
        ok, before = st.update_item_remark(conn, r2, "B4", "More handouts, please")
        assert ok and before == "More handouts please"
        got = {(c["response_id"], c["item_id"]): c["text"]
               for c in st.activity_editable_comments(conn, [r1, r2, r3])}
        assert got[(r1, "")] == "Great facilitators (fixed)"
        assert got[(r2, "B4")] == "More handouts, please"
    finally:
        conn.close()


def test_editor_shown_to_managers(app_mod, manager):
    fid = _http_activity(app_mod)
    r = manager.get(f"/reports/activities/{fid}")
    assert r.status_code == 200
    assert "Edit the words (for encoding)" in r.text
    # the actual audited edit route + a comment's text are wired into the form
    assert f'action="/responses/' in r.text and "/edit-remark" in r.text
    assert "Loved the venue choice" in r.text


def test_editor_hidden_from_viewers(app_mod, viewer):
    fid = _http_activity(app_mod)
    r = viewer.get(f"/reports/activities/{fid}")
    assert r.status_code == 200
    assert "Edit the words (for encoding)" not in r.text
    assert "/edit-remark" not in r.text
