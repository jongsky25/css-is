"""Feature E — event link tree + attendee identity/consent capture + retention.

Exercises the public flow end to end on the throwaway test DB:
  create event (manager) -> public link tree gated by consent -> capture with
  name+email required -> rating tagged to the consented attendee -> analytics
  stays anonymous -> retention purge nulls PII but keeps ratings + consent.
"""
import re
import auth
import storage as st


def _make_event(manager, db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Unit Test Forum",
        "event_date": "2026-06-11", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    tok = re.search(r"/e/([0-9a-f]{12})", r.text)
    assert tok, "result page should link to the /e/<token> link tree"
    return tok.group(1)


def test_link_tree_public_and_gated(client, manager, db_path):
    tok = _make_event(manager, db_path)
    # public, no login needed
    r = client.get(f"/e/{tok}")
    assert r.status_code == 200
    assert "Unit Test Forum" in r.text
    assert "Data Privacy Act" in r.text          # consent notice present
    assert 'name="consent"' in r.text
    assert "/r/" not in r.text                    # rating links hidden pre-consent


def test_consent_required_fields(client, manager, db_path):
    tok = _make_event(manager, db_path)
    before = st.count_attendees(st.connect(db_path))
    # missing consent + missing email -> re-renders with errors, no capture
    r = client.post(f"/e/{tok}", data={"name": "Ana", "email": "", "consent": ""})
    assert r.status_code == 200 and "consent box" in r.text
    # invalid email shape -> rejected
    r = client.post(f"/e/{tok}", data={"name": "Ana", "email": "not-an-email", "consent": "on"})
    assert r.status_code == 200 and "valid email" in r.text
    assert st.count_attendees(st.connect(db_path)) == before


def test_consent_capture_and_rating_link(client, manager, db_path):
    tok = _make_event(manager, db_path)
    r = client.post(f"/e/{tok}", data={"name": "Ana Cruz", "email": "ana@example.com",
                    "contact": "0917", "sex": "F", "affiliation": "DOH", "consent": "on"},
                    follow_redirects=False)
    assert r.status_code == 303
    att = re.search(r"att=([^&]+)", r.headers["location"]).group(1)

    conn = st.connect(db_path)
    row = conn.execute("SELECT name, email, contact, consent_at, consent_text, purged_at "
                       "FROM attendee WHERE id=?", (auth.verify_attendee_token(att),)).fetchone()
    conn.close()
    assert row[0] == "Ana Cruz" and row[1] == "ana@example.com" and row[2] == "0917"
    assert row[3] and "Data Privacy Act" in row[4] and row[5] is None

    # post-consent page exposes the rating links carrying the (signed) att session
    r = client.get(f"/e/{tok}?att={att}")
    assert "&att=" in r.text and "/r/" in r.text
    ftok = re.search(r"/r/([0-9a-f]{12})\?seq=", r.text).group(1)

    # a rating submitted in this session is tagged to the attendee
    r = client.post(f"/r/{ftok}", data={"seq": "", "att": att, "A": "7", "B1": "7",
                    "C": "4", "remarks": "Good"}, follow_redirects=False)
    assert r.status_code == 200 and "Thank" in r.text
    conn = st.connect(db_path)
    linked = conn.execute("SELECT COUNT(*) FROM response WHERE attendee_id=?", (auth.verify_attendee_token(att),)).fetchone()[0]
    # analytics must not surface identity
    df = st.load_atoms(conn)
    conn.close()
    assert linked == 1
    assert not ({"name", "email", "contact", "attendee_id"} & set(df.columns))


def test_forged_attendee_dropped(client, manager, db_path):
    tok = _make_event(manager, db_path)
    r = client.get(f"/e/{tok}", follow_redirects=True)
    # mint a real attendee so a *different* (forged) id can be contrasted
    client.post(f"/e/{tok}", data={"name": "Z", "email": "z@e.com", "sex": "M",
                "affiliation": "NON-DOH", "consent": "on"})
    conn = st.connect(db_path)
    ftok = conn.execute("""SELECT fi.qr_token FROM event_form ef
                           JOIN event e ON e.id=ef.event_id
                           JOIN form_instance fi ON fi.id=ef.form_instance_id
                           WHERE e.event_token=? ORDER BY ef.ordinal LIMIT 1""",
                        (tok,)).fetchone()[0]
    conn.close()
    client.post(f"/r/{ftok}", data={"seq": "", "att": "99999999", "A": "5", "C": "4"})
    conn = st.connect(db_path)
    bad = conn.execute("SELECT COUNT(*) FROM response WHERE attendee_id=99999999").fetchone()[0]
    conn.close()
    assert bad == 0


def test_retention_purge(client, manager, db_path):
    import retention
    tok = _make_event(manager, db_path)
    r = client.post(f"/e/{tok}", data={"name": "Old Attendee", "email": "old@e.com",
                    "sex": "M", "affiliation": "DOH", "consent": "on"}, follow_redirects=False)
    att = re.search(r"att=([^&]+)", r.headers["location"]).group(1)
    conn = st.connect(db_path)
    att = auth.verify_attendee_token(att)
    conn.execute("UPDATE attendee SET consent_at='2020-01-01T00:00:00' WHERE id=?", (att,))
    conn.commit(); conn.close()

    n = retention.run(db_path=db_path, months=6)
    assert n >= 1
    conn = st.connect(db_path)
    row = conn.execute("SELECT name, email, contact, consent_at, consent_text, purged_at "
                       "FROM attendee WHERE id=?", (att,)).fetchone()
    chain_ok = st.verify_audit_chain(conn)[0]
    audited = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='retention_purge'").fetchone()[0]
    conn.close()
    assert row[0] is None and row[1] is None and row[2] is None   # PII gone
    assert row[3] and row[4] and row[5]                            # consent record kept
    assert chain_ok and audited >= 1
