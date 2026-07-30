"""
Admin-only "Merge (any date)" action on the Activities bulk-edit bar.

Unlike the existing "Rename / merge" (label only), this actually combines two
activities' responses onto one record and re-dates it — the fix for one real
event logged twice under different dates (the case that motivated this: two
near-duplicate F2 titles, 6 days apart, that "Rename / merge" alone can't
combine because the dashboard groups by exact event_date/venue/org).
"""
import itertools
import storage as st
import activity_admin as aa
import harmonize as hz

_seq = itertools.count()


def _make_pair(app_mod, sec_id):
    conn = st.connect(app_mod.DB)
    try:
        big = st.create_form_instance(conn, survey_type=2, form="F2", event_date="2026-05-26",
                                      venue="Zoom", lead_org_id=sec_id,
                                      topic="Updating DOH Representatives on Local Health Systems Policies and Programs")
        small = st.create_form_instance(conn, survey_type=2, form="F2", event_date="2026-05-20",
                                        venue="Zoom", lead_org_id=sec_id,
                                        topic="Updating of DOH Representatives on Local Health Systems Policies and Programs")
        for _ in range(5):
            st.record_response(conn, big, [("A", 6), ("C", 6)])
        for _ in range(3):
            st.record_response(conn, small, [("A", 6), ("C", 6)])
        conn.commit()
    finally:
        conn.close()
    return big, small


def _section_id(app_mod):
    conn = st.connect(app_mod.DB)
    try:
        bureau_id, _, _ = st.get_or_create_blhsd(conn)
        return st.add_org_unit(conn, "Test Section", "section", f"BLHSD/TestSection-{next(_seq)}")
    finally:
        conn.close()


def test_merge_activities_helper_combines_responses_and_redates(app_mod):
    sec_id = _section_id(app_mod)
    big, small = _make_pair(app_mod, sec_id)
    conn = st.connect(app_mod.DB)
    try:
        aa.ensure_backup(app_mod.DB)
        batch = aa.new_batch()
        merged, deleted = aa.merge_activities(
            conn, [big, small],
            "Updating DOH Representatives on Local Health Systems Policies and Programs",
            "2026-05-26", "test@test.local", batch)
        conn.commit()
        assert merged == 1 and deleted == 1
        rows = conn.execute("SELECT id, event_date FROM form_instance WHERE id IN (?,?)",
                            (big, small)).fetchall()
        assert rows == [(big, "2026-05-26")]        # small is gone, big kept its date
        n = conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?", (big,)).fetchone()[0]
        assert n == 8                                 # 5 + 3 combined onto the survivor

        undone = hz.undo_batch(conn, batch)
        assert undone > 0
        rows = conn.execute("SELECT id FROM form_instance WHERE id IN (?,?)", (big, small)).fetchall()
        assert {r[0] for r in rows} == {big, small}   # undo restores the duplicate
    finally:
        conn.close()


def test_bulk_merge_route_requires_admin_not_section_manager(manager, app_mod):
    sec_id = _section_id(app_mod)
    big, small = _make_pair(app_mod, sec_id)
    r = manager.post("/reports/activities/bulk", data={
        "ids": [str(big), str(small)], "action": "merge",
        "title": "Updating DOH Representatives on Local Health Systems Policies and Programs",
        "merge_date": "2026-05-26",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]
    conn = st.connect(app_mod.DB)
    try:
        n = conn.execute("SELECT COUNT(*) FROM form_instance WHERE id IN (?,?)",
                         (big, small)).fetchone()[0]
        assert n == 2                                 # nothing merged — still both rows
    finally:
        conn.close()


def test_bulk_merge_route_admin_merges_across_dates(admin, app_mod):
    sec_id = _section_id(app_mod)
    big, small = _make_pair(app_mod, sec_id)
    r = admin.post("/reports/activities/bulk", data={
        "ids": [str(big), str(small)], "action": "merge",
        "title": "Updating DOH Representatives on Local Health Systems Policies and Programs",
        "merge_date": "2026-05-26",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "ok=" in r.headers["location"]
    conn = st.connect(app_mod.DB)
    try:
        rows = conn.execute("SELECT id, event_date FROM form_instance WHERE id IN (?,?)",
                            (big, small)).fetchall()
        assert rows == [(big, "2026-05-26")]
        n = conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?", (big,)).fetchone()[0]
        assert n == 8
    finally:
        conn.close()


def test_bulk_merge_route_rejects_bad_corrected_date(admin, app_mod):
    sec_id = _section_id(app_mod)
    big, small = _make_pair(app_mod, sec_id)
    r = admin.post("/reports/activities/bulk", data={
        "ids": [str(big), str(small)], "action": "merge",
        "title": "Updating DOH Representatives on Local Health Systems Policies and Programs",
        "merge_date": "not-a-date",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]


def _make_single(app_mod, sec_id, event_date="2026-05-26"):
    conn = st.connect(app_mod.DB)
    try:
        fid = st.create_form_instance(conn, survey_type=2, form="F2", event_date=event_date,
                                      venue="Zoom", lead_org_id=sec_id,
                                      topic="Updating DOH Representatives on Local Health Systems Policies and Programs")
        for _ in range(3):
            st.record_response(conn, fid, [("A", 6), ("C", 6)])
        conn.commit()
    finally:
        conn.close()
    return fid


def test_set_activity_date_helper_corrects_one_activity_and_undoes(app_mod):
    sec_id = _section_id(app_mod)
    fid = _make_single(app_mod, sec_id, "2026-05-26")
    conn = st.connect(app_mod.DB)
    try:
        aa.ensure_backup(app_mod.DB)
        batch = aa.new_batch()
        n = aa.set_activity_date(conn, [fid], "2026-05-20", "test@test.local", batch)
        conn.commit()
        assert n == 1
        row = conn.execute("SELECT event_date FROM form_instance WHERE id=?", (fid,)).fetchone()
        assert row[0] == "2026-05-20"

        undone = hz.undo_batch(conn, batch)
        assert undone > 0
        row = conn.execute("SELECT event_date FROM form_instance WHERE id=?", (fid,)).fetchone()
        assert row[0] == "2026-05-26"
    finally:
        conn.close()


def test_bulk_redate_route_requires_admin_not_section_manager(manager, app_mod):
    sec_id = _section_id(app_mod)
    fid = _make_single(app_mod, sec_id, "2026-05-26")
    r = manager.post("/reports/activities/bulk", data={
        "ids": str(fid), "action": "redate", "merge_date": "2026-05-20",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]
    conn = st.connect(app_mod.DB)
    try:
        row = conn.execute("SELECT event_date FROM form_instance WHERE id=?", (fid,)).fetchone()
        assert row[0] == "2026-05-26"                 # unchanged
    finally:
        conn.close()


def test_bulk_redate_route_admin_corrects_single_activity(admin, app_mod):
    sec_id = _section_id(app_mod)
    fid = _make_single(app_mod, sec_id, "2026-05-26")
    r = admin.post("/reports/activities/bulk", data={
        "ids": str(fid), "action": "redate", "merge_date": "2026-05-20",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "ok=" in r.headers["location"]
    conn = st.connect(app_mod.DB)
    try:
        row = conn.execute("SELECT event_date, topic FROM form_instance WHERE id=?", (fid,)).fetchone()
        assert row[0] == "2026-05-20"
        # redate never touches the title/responses — only rename/merge do
        assert row[1] == "Updating DOH Representatives on Local Health Systems Policies and Programs"
        n = conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?", (fid,)).fetchone()[0]
        assert n == 3
    finally:
        conn.close()


def test_bulk_redate_route_rejects_bad_date(admin, app_mod):
    sec_id = _section_id(app_mod)
    fid = _make_single(app_mod, sec_id, "2026-05-26")
    r = admin.post("/reports/activities/bulk", data={
        "ids": str(fid), "action": "redate", "merge_date": "not-a-date",
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]
