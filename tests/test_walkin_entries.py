"""
Walk-in (Type 1 / ARTA) entries manager — admin-only editing and reversible
archiving of individual responses to the standing walk-in form.
"""
import storage as st
import css_is_engine as eng


def _first_type1_response_id(app_mod):
    conn = st.connect(app_mod.DB)
    row = conn.execute(
        "SELECT r.id FROM response r JOIN form_instance fi ON fi.id = r.form_instance_id "
        "WHERE fi.survey_type = 1 ORDER BY r.id LIMIT 1").fetchone()
    conn.close()
    return row[0]


def test_section_manager_forbidden(manager, app_mod):
    rid = _first_type1_response_id(app_mod)
    assert manager.get("/arta/entries").status_code == 403
    assert manager.get(f"/arta/entries/{rid}").status_code == 403
    assert manager.post(f"/arta/entries/{rid}/archive", data={}).status_code == 403


def test_admin_can_list_and_edit_entry(admin, app_mod):
    rid = _first_type1_response_id(app_mod)
    idx = admin.get("/arta/entries")
    assert idx.status_code == 200
    edit = admin.get(f"/arta/entries/{rid}")
    assert edit.status_code == 200

    form = {"collected_on": "2026-01-15", "served_by_rp_id": "",
            "remarks": "Edited by admin test.", "meta_SERVICE": "Records Request",
            "meta_CLIENT_TYPE": "Citizen"}
    for item in ["SQD0"] + list(eng.ARTA_HEADLINE_ITEMS):
        form[item] = "5"
    r = admin.post(f"/arta/entries/{rid}", data=form, follow_redirects=False)
    assert r.status_code == 303

    conn = st.connect(app_mod.DB)
    entry = st.get_walkin_entry(conn, rid)
    conn.close()
    assert entry["remarks"] == "Edited by admin test."
    assert entry["metadata"]["SERVICE"] == "Records Request"
    assert entry["metadata"]["CLIENT_TYPE"] == "Citizen"
    assert entry["answers"]["SQD0"]["value"] == 5.0
    assert entry["submitted_at"].startswith("2026-01-15")


def test_admin_archive_and_restore_drops_from_atoms(admin, app_mod):
    rid = _first_type1_response_id(app_mod)
    conn = st.connect(app_mod.DB)
    before = conn.execute("SELECT COUNT(*) FROM answer WHERE response_id=?", (rid,)).fetchone()[0]
    assert before > 0

    r = admin.post(f"/arta/entries/{rid}/archive", data={}, follow_redirects=False)
    assert r.status_code == 303
    entry = st.get_walkin_entry(conn, rid)
    assert entry["archived"] is True
    atoms = eng.load_atoms(conn) if hasattr(eng, "load_atoms") else st.load_atoms(conn)
    assert rid not in set(atoms["response_id"].unique())

    r2 = admin.post(f"/arta/entries/{rid}/archive", data={"restore": "1"}, follow_redirects=False)
    assert r2.status_code == 303
    entry = st.get_walkin_entry(conn, rid)
    assert entry["archived"] is False
    atoms = st.load_atoms(conn)
    assert rid in set(atoms["response_id"].unique())
    conn.close()


def test_non_type1_response_not_editable(admin, app_mod):
    conn = st.connect(app_mod.DB)
    row = conn.execute(
        "SELECT r.id FROM response r JOIN form_instance fi ON fi.id = r.form_instance_id "
        "WHERE fi.survey_type != 1 ORDER BY r.id LIMIT 1").fetchone()
    conn.close()
    if not row:
        return   # seeded db has no Type 2/3 responses to check against
    r = admin.get(f"/arta/entries/{row[0]}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/arta/entries"
