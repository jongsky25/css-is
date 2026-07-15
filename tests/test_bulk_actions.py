"""
Bulk actions (UX #11) — the two slices that extend the existing curate bar:

  * Export selected — POST /reports/activities/export-selected returns an XLSX of
    just the ticked activities (reuses the Type-2 inventory workbook).
  * Bulk restore — POST /activities/archived/bulk restores several standalone
    activities at once, honouring the same per-row ownership rule as the single
    Restore button (creator or admin only).
"""
import storage as st


# ── Slice A: export selected ──────────────────────────────────────────────

def test_export_selected_no_ids_redirects_with_error(admin):
    r = admin.post("/reports/activities/export-selected", data={},
                   follow_redirects=False)
    assert r.status_code == 303
    assert "/reports/activities?err=" in r.headers["location"]


def test_export_selected_valid_id_returns_xlsx(admin, app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    try:
        atoms = app_mod.get_atoms(conn)
        events = app_mod.di.build_events(atoms, st.list_activity_instances(conn))
        ev = next((e for e in events if e["f2"]), None)
    finally:
        conn.close()
    assert ev is not None, "test DB has no Type-2 activity to export"
    r = admin.post("/reports/activities/export-selected",
                   data={"ids": str(ev["id"])}, follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert "BLHSD_Activities_selected_" in r.headers["content-disposition"]
    assert r.content[:2] == b"PK"          # xlsx is a zip


def test_export_selected_requires_view(app_mod):
    # A truly anonymous client (the shared `client` fixture can carry an auth
    # cookie left by an earlier login test) is bounced by the auth guard, not
    # handed a file.
    from starlette.testclient import TestClient
    anon = TestClient(app_mod.app)
    r = anon.post("/reports/activities/export-selected",
                  data={"ids": "1"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403)
    assert "spreadsheetml" not in r.headers.get("content-type", "")


# ── Slice B: bulk restore ─────────────────────────────────────────────────

def _make_archived_standalone(app_mod, owner):
    """A throwaway archived standalone form (no event) owned by `owner`."""
    conn = st.connect(app_mod.DB); st.init_db(conn)
    fid = st.create_form_instance(conn, "arta", "css", "2026-06-01",
                                  topic="Bulk-restore test activity",
                                  created_by=owner)
    st.set_form_archived(conn, fid, archived=True)
    conn.close()
    return fid


def _is_archived(app_mod, fid):
    conn = st.connect(app_mod.DB)
    try:
        return st.form_archive_info(conn, fid)["archived"]
    finally:
        conn.close()


def test_bulk_restore_owner_restores(manager, app_mod):
    fid = _make_archived_standalone(app_mod, "manager@test.local")
    assert _is_archived(app_mod, fid) is True
    r = manager.post("/activities/archived/bulk", data={"ids": str(fid)},
                     follow_redirects=False)
    assert r.status_code == 303
    assert "/activities/archived?ok=" in r.headers["location"]
    assert _is_archived(app_mod, fid) is False


def test_bulk_restore_skips_other_owners_form(manager, app_mod):
    # A non-admin manager may not restore a form someone else created.
    fid = _make_archived_standalone(app_mod, "someone-else@test.local")
    r = manager.post("/activities/archived/bulk", data={"ids": str(fid)},
                     follow_redirects=False)
    assert r.status_code == 303
    assert "/activities/archived?err=" in r.headers["location"]
    assert _is_archived(app_mod, fid) is True       # untouched


def test_bulk_restore_admin_restores_any(admin, app_mod):
    fid = _make_archived_standalone(app_mod, "someone-else@test.local")
    r = admin.post("/activities/archived/bulk", data={"ids": str(fid)},
                   follow_redirects=False)
    assert r.status_code == 303
    assert "/activities/archived?ok=" in r.headers["location"]
    assert _is_archived(app_mod, fid) is False


def test_bulk_restore_no_ids_redirects_with_error(manager):
    r = manager.post("/activities/archived/bulk", data={},
                     follow_redirects=False)
    assert r.status_code == 303
    assert "err=" in r.headers["location"]


def test_archived_page_renders_select_to_restore(admin):
    r = admin.get("/activities/archived")
    assert r.status_code == 200
    assert 'id="restoreForm"' in r.text
    assert "Select to restore" in r.text


# ── Slice C: bulk restore of a bundled bureau event ────────────────────────

def _make_archived_bureau_event(app_mod, owner):
    """A throwaway archived bureau event (F2 review + one F3 speaker), owned by
    `owner`. Returns (f2_id, f3_id, event_id)."""
    conn = st.connect(app_mod.DB); st.init_db(conn)
    today = st.today_local(conn)
    f2 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "created_by) VALUES (2,'F2',?,?,?,?)",
        ("bulk_evt_f2", today, "Bulk-restore test event", owner)).lastrowid
    f3 = conn.execute(
        "INSERT INTO form_instance(survey_type, form, qr_token, event_date, topic, "
        "created_by) VALUES (3,'F3',?,?,?,?)",
        ("bulk_evt_f3", today, "Bulk-restore test speaker", owner)).lastrowid
    ev = st.create_event(conn, "Bulk-restore test event", today,
                         form_instance_ids=[f2, f3], created_by=owner)
    st.set_form_archived(conn, f2, archived=True)
    st.set_form_archived(conn, f3, archived=True)
    conn.commit(); conn.close()
    return f2, f3, ev["id"]


def _archived_flags(app_mod, *fids):
    conn = st.connect(app_mod.DB)
    try:
        return [st.form_archive_info(conn, fid)["archived"] for fid in fids]
    finally:
        conn.close()


def test_bulk_restore_bureau_event_restores_every_bundled_form(manager, app_mod):
    """Ticking the event's representative (F2) id restores the whole bundle, gated
    on create_activity — a section_manager may do this for any event, mirroring the
    single-item instance-archive route's permission model (no per-creator check)."""
    f2, f3, ev_id = _make_archived_bureau_event(app_mod, "someone-else@test.local")
    try:
        r = manager.post("/activities/archived/bulk", data={"ids": str(f2)},
                         follow_redirects=False)
        assert r.status_code == 303
        assert "/activities/archived?ok=" in r.headers["location"]
        assert _archived_flags(app_mod, f2, f3) == [False, False]
    finally:
        conn = st.connect(app_mod.DB)
        conn.execute("DELETE FROM event_form WHERE event_id=?", (ev_id,))
        conn.execute("DELETE FROM event WHERE id=?", (ev_id,))
        conn.execute("DELETE FROM form_instance WHERE id IN (?,?)", (f2, f3))
        conn.commit(); conn.close()


def test_bulk_restore_bureau_event_requires_manage_event(viewer, app_mod):
    """A viewer (no manage_event/create_activity capability) is refused before any
    row is even looked at, via the same base gate every archived-page action uses."""
    f2, f3, ev_id = _make_archived_bureau_event(app_mod, "someone-else@test.local")
    try:
        r = viewer.post("/activities/archived/bulk", data={"ids": str(f2)},
                        follow_redirects=False)
        assert r.status_code == 403
        assert _archived_flags(app_mod, f2, f3) == [True, True]
    finally:
        conn = st.connect(app_mod.DB)
        conn.execute("DELETE FROM event_form WHERE event_id=?", (ev_id,))
        conn.execute("DELETE FROM event WHERE id=?", (ev_id,))
        conn.execute("DELETE FROM form_instance WHERE id IN (?,?)", (f2, f3))
        conn.commit(); conn.close()
