"""Activity modality — online vs face-to-face on the create flow.

Online events must NOT require a physical venue; when a platform / meeting link
is given it is stored in the existing `venue` column, and the chosen modality is
persisted on both the event and its form_instances so cards/reports can label it.
"""
import re
import storage as st


def _rp_id(db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    return str(rp[0])


def _create(manager, db_path, **extra):
    data = {"event_type": "bureau", "activity_name": "Modality Forum",
            "event_date": "2026-06-12", "qr_mode": "combined",
            "rp_id": _rp_id(db_path), "topic": "Keynote"}
    data.update(extra)
    r = manager.post("/create", data=data, follow_redirects=True)
    assert r.status_code == 200, r.text
    tok = re.search(r"/e/([0-9a-f]{12})", r.text)
    assert tok, "result page should link to the /e/<token> link tree"
    return tok.group(1), r


def _event_row(db_path, token):
    conn = st.connect(db_path)
    row = conn.execute(
        "SELECT modality, venue FROM event WHERE event_token = ?", (token,)).fetchone()
    fi = conn.execute(
        """SELECT DISTINCT fi.modality FROM form_instance fi
           JOIN event_form ef ON ef.form_instance_id = fi.id
           JOIN event e ON e.id = ef.event_id WHERE e.event_token = ?""", (token,)).fetchall()
    conn.close()
    return row, [r[0] for r in fi]


def test_online_stores_modality_and_link(manager, db_path):
    tok, r = _create(manager, db_path, modality="online",
                     venue="Zoom — https://zoom.us/j/123")
    (modality, venue), fi_modalities = _event_row(db_path, tok)
    assert modality == "online"
    assert venue == "Zoom — https://zoom.us/j/123"          # link kept in venue column
    assert fi_modalities == ["online"]                       # every form tagged online
    assert "Online" in r.text                                # summary shows the format


def test_online_needs_no_venue(manager, db_path):
    # No venue posted at all — an online activity must still succeed.
    tok, _ = _create(manager, db_path, modality="online")
    (modality, venue), _ = _event_row(db_path, tok)
    assert modality == "online"
    assert venue is None


def test_face_to_face_default(manager, db_path):
    tok, _ = _create(manager, db_path, venue="Hall A")       # modality omitted
    (modality, venue), fi_modalities = _event_row(db_path, tok)
    assert modality == "f2f"
    assert venue == "Hall A"
    assert set(fi_modalities) == {"f2f"}
