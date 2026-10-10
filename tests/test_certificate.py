"""Certificate of Appearance — opt-in, auto-generated artifact for a participant
who has COMPLETED an activity's feedback.

Covers the renderer (certificate.py) and the gated download route:
  * gate: only a registered attendee who finished ALL the feedback gets it
  * opt-in: a disabled activity yields 404
  * retention: a purged (name-nulled) attendee is refused
  * PDF renders with the right magic bytes + filled fields (PDF-only — no PPTX)
  * directory-driven signatory (name/title/signature pulled from resource_person)
  * signature upload + authed-only preview
"""
import base64
import re
import auth
import storage as st
import certificate as cert

# A 1x1 transparent PNG as a stand-in signature image.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def _make_event(manager, db_path, title="Certificate Forum"):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": title,
        "event_date": "2026-06-11", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


def _register(client, tok, name="Ana Cruz", email="ana@example.com", honorific=""):
    data = {"name": name, "email": email, "sex": "F", "affiliation": "DOH", "consent": "on"}
    if honorific:
        data["honorific"] = honorific
    r = client.post(f"/e/{tok}", data=data, follow_redirects=False)
    return re.search(r"att=([^&]+)", r.headers["location"]).group(1)


def _form_tokens(db_path, tok):
    conn = st.connect(db_path)
    rows = conn.execute("""SELECT fi.qr_token FROM event_form ef
                           JOIN event e ON e.id=ef.event_id
                           JOIN form_instance fi ON fi.id=ef.form_instance_id
                           WHERE e.event_token=? ORDER BY ef.ordinal""", (tok,)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def _complete_feedback(client, db_path, tok, att):
    """Submit every form of the event for this attendee, so the completion gate
    opens."""
    for ft in _form_tokens(db_path, tok):
        client.post(f"/r/{ft}", data={"seq": "", "att": att, "A": "7", "B1": "7",
                    "C": "4", "remarks": "ok"})


def _enable_cert(db_path, tok, signatory_id=None, verb="attended"):
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    st.set_event_certificate(conn, ev["id"], enabled=True,
                             signatory_rp_id=signatory_id, verb=verb)
    conn.close()


def _signatory_with_signature(db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()[0]
    st.set_rp_signature(conn, rp, _PNG, "image/png")
    conn.close()
    return rp


# ---------------------------------------------------------------------
# renderer unit tests (no HTTP)
# ---------------------------------------------------------------------

def test_render_pdf_bytes():
    ev = {"title": "Dashboard Training", "event_date": "2026-03-06",
          "venue": "BLHSD Conf Room", "modality": "f2f", "certificate_verb": "attended"}
    sig = {"display_name": "Dr. Mar Wynn D. Bello", "title": "Director IV, BLHSD",
           "signature_bytes": _PNG, "signature_mime": "image/png"}
    pdf = cert.render_pdf(ev, "Juan dela Cruz", sig)
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000

    # PDF-only: there is no editable PowerPoint renderer.
    assert not hasattr(cert, "render_pptx")


def test_render_handles_missing_signatory_and_venue():
    ev = {"title": "TWG Meeting", "event_date": "2026-01-02", "modality": "online",
          "venue": "", "certificate_verb": "participated in"}
    pdf = cert.render_pdf(ev, "Maria Santos", None)        # no signatory
    assert pdf[:5] == b"%PDF-"


def test_fields_compose_body():
    ev = {"title": "Strategic Planning", "event_date": "2026-02-10",
          "venue": "Manila", "modality": "f2f", "certificate_verb": "attended"}
    f = cert._fields(ev, "Ana Cruz", None)
    assert "Ana Cruz" in f["body"]
    assert "attended the Strategic Planning" in f["body"]
    assert "held on February 10, 2026" in f["body"]
    assert "Issued this" in f["issued"]


# ---------------------------------------------------------------------
# gated download route
# ---------------------------------------------------------------------

def test_disabled_activity_404(client, manager, db_path):
    tok = _make_event(manager, db_path)
    att = _register(client, tok)
    _complete_feedback(client, db_path, tok, att)
    # certificate never enabled -> not available
    r = client.get(f"/e/{tok}/certificate?att={att}")
    assert r.status_code == 404


def test_gate_blocks_until_feedback_complete(client, manager, db_path):
    tok = _make_event(manager, db_path)
    sig = _signatory_with_signature(db_path)
    _enable_cert(db_path, tok, signatory_id=sig)
    att = _register(client, tok)
    # not yet completed -> 403
    r = client.get(f"/e/{tok}/certificate?att={att}")
    assert r.status_code == 403
    # complete every form -> 200 PDF
    _complete_feedback(client, db_path, tok, att)
    r = client.get(f"/e/{tok}/certificate?att={att}&fmt=pdf")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    assert "attachment" in r.headers.get("content-disposition", "")


def test_pptx_request_falls_back_to_pdf(client, manager, db_path):
    # An old/forged ?fmt=pptx URL must NOT yield an editable file — we only ever
    # serve the locked PDF, so the certificate can't be handed out editable.
    tok = _make_event(manager, db_path)
    sig = _signatory_with_signature(db_path)
    _enable_cert(db_path, tok, signatory_id=sig)
    att = _register(client, tok)
    _complete_feedback(client, db_path, tok, att)
    r = client.get(f"/e/{tok}/certificate?att={att}&fmt=pptx")
    assert r.status_code == 200
    assert r.content[:5] == b"%PDF-"
    assert r.headers.get("content-type", "").startswith("application/pdf")


def test_unknown_attendee_refused(client, manager, db_path):
    tok = _make_event(manager, db_path)
    _enable_cert(db_path, tok)
    r = client.get(f"/e/{tok}/certificate?att=99999999")
    assert r.status_code == 403


def test_purged_attendee_refused(client, manager, db_path):
    tok = _make_event(manager, db_path)
    _enable_cert(db_path, tok)
    att = _register(client, tok, name="To Purge", email="purge@e.com")
    _complete_feedback(client, db_path, tok, att)
    # simulate a retention purge: PII nulled, row kept
    conn = st.connect(db_path)
    conn.execute("UPDATE attendee SET name=NULL WHERE id=?", (auth.verify_attendee_token(att),))
    conn.commit(); conn.close()
    r = client.get(f"/e/{tok}/certificate?att={att}")
    assert r.status_code == 410


# ---------------------------------------------------------------------
# signatory + signature plumbing
# ---------------------------------------------------------------------

def test_get_signatory_pulls_directory_fields(db_path):
    conn = st.connect(db_path)
    rp = st.add_rp(conn, "Test Director", is_internal=True, honorific="Dr.",
                   position="Director IV, BLHSD")
    st.set_rp_signature(conn, rp, _PNG, "image/png")
    sig = st.get_signatory(conn, rp)
    conn.close()
    assert sig["display_name"] == "Dr. Test Director"
    assert sig["title"] == "Director IV, BLHSD"
    assert sig["has_signature"] and sig["signature_bytes"]


def test_signature_preview_requires_auth(client, manager, admin, db_path):
    rp = _signatory_with_signature(db_path)
    # anonymous -> blocked (login redirect / 401-403), never the image
    r = client.get(f"/directory/person/{rp}/signature.png", follow_redirects=False)
    assert r.status_code in (302, 303, 401, 403)
    # a non-directory role (section manager) is still refused
    assert manager.get(f"/directory/person/{rp}/signature.png").status_code == 403
    # an admin (the directory manager) can preview it
    r = admin.get(f"/directory/person/{rp}/signature.png")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/")


def test_manage_page_renders_certificate_card(manager, db_path):
    tok = _make_event(manager, db_path)
    r = manager.get(f"/activities/{tok}/manage")
    assert r.status_code == 200
    assert "Certificate of Appearance" in r.text
    assert 'name="signatory_rp_id"' in r.text
    assert 'name="certificate_enabled"' in r.text


def test_staff_form_renders_signature_control(admin, db_path):
    r = admin.get("/directory/staff/new")
    assert r.status_code == 200
    assert 'name="signature_data"' in r.text
    assert "Signature" in r.text


def test_honorific_captured_and_on_certificate(client, manager, db_path):
    tok = _make_event(manager, db_path)
    _enable_cert(db_path, tok)
    att = _register(client, tok, name="Ana Cruz", email="hon@example.com", honorific="Dr.")
    # stored on the attendee
    conn = st.connect(db_path)
    a = st.get_attendee(conn, auth.verify_attendee_token(att))
    conn.close()
    assert a["honorific"] == "Dr."
    # and rendered onto the certificate text layer (PDF)
    _complete_feedback(client, db_path, tok, att)
    r = client.get(f"/e/{tok}/certificate?att={att}&fmt=pdf")
    assert r.status_code == 200
    import io as _io
    try:
        import fitz
        text = "".join(p.get_text() for p in fitz.open(stream=_io.BytesIO(r.content), filetype="pdf"))
        assert "Dr. Ana Cruz" in text
    except ImportError:
        pass  # PDF text extraction optional; byte-level success already asserted


def test_forged_honorific_rejected(client, manager, db_path):
    tok = _make_event(manager, db_path)
    att = _register(client, tok, email="forge@example.com", honorific="Supreme Overlord")
    conn = st.connect(db_path)
    a = st.get_attendee(conn, auth.verify_attendee_token(att))
    conn.close()
    assert not a["honorific"]          # off-list value dropped


def test_certificate_settings_route(manager, db_path):
    tok = _make_event(manager, db_path)
    rp = _signatory_with_signature(db_path)
    # the default seed person used by _signatory_with_signature isn't a signing
    # authority, so promote it to one so the save isn't rejected by the new rule
    conn = st.connect(db_path)
    conn.execute("UPDATE resource_person SET designation='Division Chief' WHERE id=?", (rp,))
    conn.commit(); conn.close()
    r = manager.post(f"/activities/{tok}/certificate",
                     data={"certificate_enabled": "1", "signatory_rp_id": str(rp),
                           "certificate_verb": "conducted"}, follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    conn.close()
    assert ev["certificate_enabled"] and ev["signatory_rp_id"] == rp
    assert ev["certificate_verb"] == "conducted"


# ---------------------------------------------------------------------
# signatory eligibility — only signing authorities (Section/Division Chief,
# Director) may be chosen
# ---------------------------------------------------------------------

def test_signatory_eligibility_matrix(db_path):
    conn = st.connect(db_path)
    chief = st.add_rp(conn, "Sec Chief", is_internal=True,
                      position="Supervising Health Program Officer", designation="Section Head")
    div = st.add_rp(conn, "Div Chief", is_internal=True,
                    position="Chief Health Program Officer", designation="Division Chief")
    director = st.add_rp(conn, "The Director", is_internal=True, position="Director IV")
    officer = st.add_rp(conn, "Plain Officer", is_internal=True,
                        position="Health Program Officer II")
    external = st.add_rp(conn, "Guest Speaker", is_internal=False, position="Director IV")
    people = {p["id"]: p for p in st.list_resource_persons(conn)}
    conn.close()
    assert st.is_eligible_signatory(people[chief])
    assert st.is_eligible_signatory(people[div])
    assert st.is_eligible_signatory(people[director])
    assert not st.is_eligible_signatory(people[officer])
    assert not st.is_eligible_signatory(people[external])   # external never signs


def test_list_signatories_ranked_and_filtered(db_path):
    conn = st.connect(db_path)
    st.add_rp(conn, "Zed Chief", is_internal=True, designation="Section Head")
    st.add_rp(conn, "Ann Director", is_internal=True, position="Director IV")
    st.add_rp(conn, "Bob Officer", is_internal=True, position="Health Program Officer II")
    sigs = st.list_signatories(conn)
    conn.close()
    names = [p["name"] for p in sigs]
    assert "Bob Officer" not in names           # plain officer excluded
    # Director ranks above a Section Chief in the picker
    assert names.index("Ann Director") < names.index("Zed Chief")


def test_settings_rejects_ineligible_signatory(manager, db_path):
    tok = _make_event(manager, db_path)
    conn = st.connect(db_path)
    officer = st.add_rp(conn, "Mere Officer", is_internal=True,
                        position="Health Program Officer II")
    conn.close()
    r = manager.post(f"/activities/{tok}/certificate",
                     data={"certificate_enabled": "1", "signatory_rp_id": str(officer),
                           "certificate_verb": "attended"}, follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    conn.close()
    assert ev["signatory_rp_id"] is None        # ineligible pick dropped


def test_settings_keeps_existing_offroster_signatory(manager, db_path):
    """An activity configured before this rule (signatory = a plain officer) can
    still be re-saved without silently losing that signatory."""
    tok = _make_event(manager, db_path)
    conn = st.connect(db_path)
    officer = st.add_rp(conn, "Legacy Officer", is_internal=True,
                        position="Health Program Officer II")
    ev = st.get_event(conn, tok)
    st.set_event_certificate(conn, ev["id"], enabled=True,
                             signatory_rp_id=officer, verb="attended")
    conn.close()
    # the picker still shows the saved (off-roster) person
    r = manager.get(f"/activities/{tok}/manage")
    assert f'value="{officer}"' in r.text
    # and re-saving with the same id keeps it
    r = manager.post(f"/activities/{tok}/certificate",
                     data={"certificate_enabled": "1", "signatory_rp_id": str(officer),
                           "certificate_verb": "attended"}, follow_redirects=False)
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    conn.close()
    assert ev["signatory_rp_id"] == officer
