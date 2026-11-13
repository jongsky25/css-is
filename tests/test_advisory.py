"""Public advisory poster: the renderer (advisory.py), numbering/defaults (activity_advisory.py) and the routes.

Covers:
  * the poster renders as a PNG/PDF at the right proportions and refuses text that cannot fit
  * `**bold**` runs, glued punctuation, icons and normalisation limits
  * the number is YYYY-MMDD-NNN, counts up within a day, restarts the next day and never changes on edit
  * the starting draft comes from the activity's own link-tree details
  * only a manager can edit; a draft is never public; publishing shows it on the link tree; withdrawing hides it
  * an invited ("outside") activity cannot publish one
"""
import io
import re
from datetime import date

import pytest
from PIL import Image

import activity_advisory as aa
import advisory
import storage as st

PNG = b"\x89PNG\r\n\x1a\n"

FIELDS = dict(
    number="2026-1113-001",
    headline="Confirmation of Participants for JOAS under UNA Batch 2 on December 15-17, 2026",
    attention="Local Health System Development (LHSD) Division Chiefs",
    body="We are actively finalizing the logistics for **JOAS Batch 2** happening on **December 15-17, 2026**.",
    rows=[("Confirmation of Participation (Due Nov 20, 12:00 NN)", "https://bit.ly/joasbatch2confirm"),
          ("JOASxCHD Viber Group for updates", "https://tinyurl.com/joasxchdvg"),
          ("Accommodation", "c/o organizers (venue TBA)")],
    qr_url="https://bit.ly/joasbatch2confirm", link_text="https://bit.ly/joasbatch2confirm",
    contact_name="Ms. Eileen Diane S. Cheng-Fernandez", contact_phone="8651-7800 loc 1755",
    contact_email="blhsd@doh.gov.ph")


# ------------------------------------------------------------------------------------------ renderer

def test_png_has_the_office_proportions():
    data = advisory.render_png(FIELDS, 1.0)
    assert data[:8] == PNG
    im = Image.open(io.BytesIO(data))
    assert im.size == (1272, 1800)
    assert im.getpixel((10, 300)) == advisory.GREEN          # the ADVISORY band
    assert im.getpixel((1000, 300)) == advisory.YELLOW       # the number box
    assert im.getpixel((10, 700)) == advisory.CREAM          # the body
    assert im.getpixel((10, 1600)) == advisory.GREEN         # the footer


def test_default_scale_is_twice_the_design_size():
    assert Image.open(io.BytesIO(advisory.render_png(FIELDS))).size == (2544, 3600)


def test_pdf_is_a_single_a4_page():
    pdf = advisory.render_pdf(FIELDS)
    assert pdf[:5] == b"%PDF-"
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 1
    assert b"595.27" in pdf                                   # A4 width in points


def test_rendering_is_repeatable():
    assert advisory.render_png(FIELDS, 0.5) == advisory.render_png(FIELDS, 0.5)


def test_text_that_cannot_fit_is_refused_not_clipped():
    huge = {**FIELDS, "body": ("word " * 400), "rows": [(f"Row {i} " + "x" * 80, "y" * 200) for i in range(8)]}
    with pytest.raises(advisory.AdvisoryTooLong):
        advisory.render_png(huge, 0.25)


def test_fewer_and_more_rows_still_render():
    for rows in ([], FIELDS["rows"][:1], [(f"Row {i}", "https://example.org/x") for i in range(8)]):
        assert advisory.render_png({**FIELDS, "rows": rows}, 0.25)[:8] == PNG


def test_empty_attention_is_omitted_and_other_fields_survive():
    assert advisory.render_png({**FIELDS, "attention": "", "body": ""}, 0.25)[:8] == PNG


def test_long_unbroken_link_is_still_drawn():
    rows = [("Materials", "https://example.org/" + "a" * 150)]
    assert advisory.render_png({**FIELDS, "rows": rows}, 0.25)[:8] == PNG


def test_bold_runs_keep_attached_punctuation_together():
    units = advisory._tokens("see **JOAS Batch 2**, then **2026**.")[0]
    words = ["".join(w for w, _, _ in u) for u in units]
    assert words == ["see", "JOAS", "Batch", "2,", "then", "2026."]
    assert units[3] == [("2", True, False), (",", False, False)]


def test_attention_label_is_underlined_and_first():
    para = advisory._tokens("Division Chiefs", prefix=[[("ATTENTION:", False, True)]])[0]
    assert para[0] == [("ATTENTION:", False, True)]


@pytest.mark.parametrize("label,value,icon", [
    ("Confirmation of Participation (Due Nov 20)", "https://x.org", "confirm"),
    ("JOASxCHD Viber Group for updates", "https://x.org", "chat"),
    ("JOAS Reference Materials", "https://x.org", "folder"),
    ("Accommodation", "c/o organizers", "building"),
    ("Travel Expenses", "c/o sending agency", "plane"),
    ("Anything else", "https://x.org", "link")])
def test_icons_follow_the_row_wording(label, value, icon):
    assert advisory.icon_for(label, value) == icon


def test_every_icon_and_font_asset_exists():
    import os
    for name in ("confirm", "chat", "folder", "building", "plane", "link", "calendar"):
        assert os.path.exists(os.path.join(advisory._DIR, f"icon_{name}.png"))
    for name in ("Fraunces.ttf", "LibreCaslonText.ttf", "Poppins-Bold.ttf", "megaphone.png", "bagong_pilipinas.png"):
        assert os.path.exists(os.path.join(advisory._DIR, name))


def test_normalise_trims_drops_blank_rows_and_caps_length():
    out = advisory.normalise({"headline": "  A   title \n", "rows": [("", ""), ("a", "b")] + [("x", "y")] * 20,
                              "contact_name": "n" * 500, "number": "2026-1113-001"})
    assert out["headline"] == "A title"
    assert out["rows"][0] == ("a", "b") and len(out["rows"]) == advisory.MAX_ROWS
    assert len(out["contact_name"]) == advisory.LIMITS["contact_name"]


def test_filename_is_safe():
    assert advisory.filename("2026-1113-001", "png") == "BLHSD-Advisory-2026-1113-001.png"
    assert advisory.filename("../x y", "pdf") == "BLHSD-Advisory-xy.pdf"


# ---------------------------------------------------------------------------------- numbers and storage

def _conn(db_path):
    conn = st.connect(db_path)
    st.init_db(conn)
    return conn


def _make_event(conn, title="JOAS Batch 2", **kw):
    made = st.create_event(conn, title, kw.pop("event_date", "2026-12-15"), end_date=kw.pop("end_date", "2026-12-17"),
                           venue=kw.pop("venue", "Manila"), created_by="tester", **kw)
    return st.get_event(conn, made["event_token"])


def test_number_format():
    assert aa.format_number(date(2026, 11, 13), 1) == "2026-1113-001"
    assert aa.format_number(date(2026, 1, 5), 42) == "2026-0105-042"


def test_numbers_count_up_within_a_day_and_restart_the_next(db_path):
    conn = _conn(db_path)
    user = {"username": "tester"}
    values = {**aa.poster_fields(FIELDS, "x"), "rows": FIELDS["rows"]}
    numbers = []
    for i, day in enumerate((date(2026, 11, 13), date(2026, 11, 13), date(2026, 11, 14))):
        ev = _make_event(conn, f"Activity {i}")
        numbers.append(aa.save(conn, ev, values, user, today=day)["number"])
    assert numbers == ["2026-1113-001", "2026-1113-002", "2026-1114-001"]
    conn.close()


def test_editing_keeps_the_number_and_raises_the_revision_only_on_a_change(db_path):
    conn = _conn(db_path)
    ev = _make_event(conn)
    user = {"username": "tester"}
    first = aa.save(conn, ev, aa.poster_fields(FIELDS, "x"), user, today=date(2026, 11, 13))
    same = aa.save(conn, ev, aa.poster_fields(FIELDS, "x"), user, today=date(2026, 11, 20))
    assert same["number"] == first["number"] and same["revision"] == 1
    edited = aa.save(conn, ev, {**aa.poster_fields(FIELDS, "x"), "headline": "A new headline"}, user,
                     today=date(2026, 11, 21))
    assert edited["number"] == first["number"] and edited["revision"] == 2
    assert edited["rows"] == [tuple(r) for r in FIELDS["rows"]]
    conn.close()


def test_the_database_refuses_a_duplicate_number(db_path):
    import sqlite3
    conn = _conn(db_path)
    a, b = _make_event(conn, "One"), _make_event(conn, "Two")
    aa.save(conn, a, aa.poster_fields(FIELDS, "x"), {"username": "t"}, today=date(2026, 11, 13))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO event_advisory(event_id, number, seq_date, seq, headline) VALUES (?,?,?,?,?)",
                     (b["id"], "2026-1113-009", "2026-11-13", 1, "x"))
    conn.close()


def test_defaults_come_from_the_activity(db_path):
    conn = _conn(db_path)
    ev = _make_event(conn, "JOAS Batch 2")
    st.add_event_link(conn, ev["id"], "slides", "JOAS Reference Materials", "https://bit.ly/joas2026share")
    st.add_event_link(conn, ev["id"], "recording", "Recording", "https://example.org/rec", visible_after_done=True)
    d = aa.defaults(conn, ev, "https://example.org/e/abc")
    assert d["headline"] == "JOAS Batch 2 on December 15-17, 2026"
    assert "**JOAS Batch 2**" in d["body"] and "**December 15-17, 2026**" in d["body"] and "Manila" in d["body"]
    assert ("JOAS Reference Materials", "https://bit.ly/joas2026share") in d["rows"]
    assert all(v != "https://example.org/rec" for _, v in d["rows"])           # after-the-activity links are left out
    assert d["contact_email"] == aa.DEFAULT_EMAIL and d["qr_url"] == "https://example.org/e/abc"
    conn.close()


def test_the_last_contact_is_offered_next_time(db_path):
    conn = _conn(db_path)
    ev = _make_event(conn, "First")
    aa.save(conn, ev, {**aa.poster_fields(FIELDS, "x"), "contact_name": "Ms. Someone"}, {"username": "t"})
    assert aa.defaults(conn, _make_event(conn, "Second"), "u")["contact_name"] == "Ms. Someone"
    conn.close()


def test_validate_asks_for_a_headline_and_a_contact():
    assert "headline" in aa.validate({**aa.poster_fields(FIELDS, "x"), "headline": ""}).lower()
    assert "contact" in aa.validate({**aa.poster_fields(FIELDS, "x"), "contact_name": ""}).lower()
    assert aa.validate(aa.poster_fields(FIELDS, "x")) == ""


def test_publish_summary_exists_only_when_published(db_path):
    conn = _conn(db_path)
    ev = _make_event(conn)
    assert aa.public_summary(conn, ev["id"]) is None
    assert aa.set_published(conn, ev["id"], True) is False                    # nothing saved yet
    aa.save(conn, ev, aa.poster_fields(FIELDS, "x"), {"username": "t"})
    assert aa.public_summary(conn, ev["id"]) is None
    assert aa.set_published(conn, ev["id"], True) is True
    assert aa.public_summary(conn, ev["id"])["headline"] == FIELDS["headline"]
    aa.set_published(conn, ev["id"], False)
    assert aa.public_summary(conn, ev["id"]) is None
    conn.close()


# ----------------------------------------------------------------------------------------------- routes

def _create_event(manager, db_path, title="Advisory Forum"):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": title, "event_date": "2026-12-15", "venue": "Hall A",
        "qr_mode": "combined", "rp_id": str(rp[0]), "topic": "Keynote"}, follow_redirects=True)
    assert r.status_code == 200
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


FORM = {"headline": "Advisory Forum on December 15, 2026", "attention": "All division chiefs",
        "body": "We will hold **Advisory Forum**.", "contact_name": "Ms. Contact", "contact_phone": "8651-7800 loc 1",
        "contact_email": "blhsd@doh.gov.ph", "row_label_0": "Registration", "row_value_0": "https://example.org/r"}


def test_editor_page_loads_with_a_starting_draft(manager, db_path):
    tok = _create_event(manager, db_path)
    r = manager.get(f"/activities/{tok}/advisory")
    assert r.status_code == 200 and "Public advisory" in r.text and "Advisory Forum" in r.text
    assert "assigned when you save" in r.text
    img = manager.get(f"/activities/{tok}/advisory/file.png?draft=1")
    assert img.status_code == 200 and img.content[:8] == PNG


def test_save_then_preview_download_and_pdf(manager, db_path):
    tok = _create_event(manager, db_path)
    r = manager.post(f"/activities/{tok}/advisory", data=FORM, follow_redirects=False)
    assert r.status_code == 303 and "msg=" in r.headers["location"]
    page = manager.get(f"/activities/{tok}/advisory")
    number = re.search(r"No\. (\d{4}-\d{4}-\d{3})", page.text).group(1)
    png = manager.get(f"/activities/{tok}/advisory/file.png?download=1")
    assert png.content[:8] == PNG and number in png.headers["content-disposition"]
    assert manager.get(f"/activities/{tok}/advisory/file.pdf").content[:5] == b"%PDF-"
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    assert aa.get(conn, ev["id"])["published"] is False
    conn.close()


def test_invalid_save_is_explained_and_nothing_is_stored(manager, db_path):
    tok = _create_event(manager, db_path)
    r = manager.post(f"/activities/{tok}/advisory", data={**FORM, "contact_name": ""}, follow_redirects=False)
    assert r.status_code == 303 and "err=" in r.headers["location"]
    conn = st.connect(db_path)
    assert aa.get(conn, st.get_event(conn, tok)["id"]) is None
    conn.close()


def test_a_draft_is_never_public_and_publishing_shows_it_on_the_link_tree(manager, client, db_path):
    tok = _create_event(manager, db_path)
    manager.post(f"/activities/{tok}/advisory", data=FORM)
    assert client.get(f"/e/{tok}/advisory.png").status_code == 404
    assert "advisory.png" not in client.get(f"/e/{tok}").text
    r = manager.post(f"/activities/{tok}/advisory/publish", data={"publish": "1"}, follow_redirects=False)
    assert r.status_code == 303 and "msg=" in r.headers["location"]
    png = client.get(f"/e/{tok}/advisory.png")
    assert png.status_code == 200 and png.content[:8] == PNG
    assert "no-store" in png.headers["cache-control"]                  # the site-wide policy is not weakened
    assert client.get(f"/e/{tok}/advisory.pdf?download=1").headers["content-disposition"].startswith("attachment")
    page = client.get(f"/e/{tok}")
    assert f"/e/{tok}/advisory.png" in page.text and "Advisory No." in page.text
    manager.post(f"/activities/{tok}/advisory/publish", data={"publish": "0"})
    assert client.get(f"/e/{tok}/advisory.png").status_code == 404
    assert "advisory.png" not in client.get(f"/e/{tok}").text


def test_edits_to_a_published_advisory_go_live_with_a_new_revision(manager, client, db_path):
    tok = _create_event(manager, db_path)
    manager.post(f"/activities/{tok}/advisory", data=FORM)
    manager.post(f"/activities/{tok}/advisory/publish", data={"publish": "1"})
    first = client.get(f"/e/{tok}/advisory.png")
    manager.post(f"/activities/{tok}/advisory", data={**FORM, "headline": "A different headline"})
    second = client.get(f"/e/{tok}/advisory.png")
    assert first.content != second.content


def test_publishing_before_saving_is_refused(manager, db_path):
    tok = _create_event(manager, db_path)
    r = manager.post(f"/activities/{tok}/advisory/publish", data={"publish": "1"}, follow_redirects=False)
    assert r.status_code == 303 and "err=" in r.headers["location"]


def test_a_viewer_cannot_open_edit_or_publish(manager, viewer, db_path):
    tok = _create_event(manager, db_path)
    manager.post(f"/activities/{tok}/advisory", data=FORM)
    assert viewer.get(f"/activities/{tok}/advisory", follow_redirects=False).status_code == 303
    assert viewer.get(f"/activities/{tok}/advisory/file.png").status_code == 403
    assert viewer.post(f"/activities/{tok}/advisory", data={**FORM, "headline": "hijack"},
                       follow_redirects=False).status_code == 303
    assert viewer.post(f"/activities/{tok}/advisory/publish", data={"publish": "1"},
                       follow_redirects=False).status_code == 303
    conn = st.connect(db_path)
    a = aa.get(conn, st.get_event(conn, tok)["id"])
    assert a["headline"] == FORM["headline"] and a["published"] is False
    conn.close()


def test_the_public_files_do_not_exist_for_an_unknown_activity_or_format(client):
    assert client.get("/e/000000000000/advisory.png").status_code == 404
    assert client.get("/e/000000000000/advisory.gif").status_code == 404


def test_an_invited_activity_cannot_publish(admin, client, db_path):
    conn = _conn(db_path)
    ev = _make_event(conn, "Invited by another office", event_kind="outside")
    aa.save(conn, ev, aa.poster_fields(FIELDS, "x"), {"username": "t"})
    conn.close()
    r = admin.post(f"/activities/{ev['event_token']}/advisory/publish", data={"publish": "1"}, follow_redirects=False)
    assert "err=" in r.headers["location"]
    assert client.get(f"/e/{ev['event_token']}/advisory.png").status_code == 404


def test_the_manage_page_links_to_the_advisory(manager, db_path):
    tok = _create_event(manager, db_path)
    assert f"/activities/{tok}/advisory" in manager.get(f"/activities/{tok}/manage").text
