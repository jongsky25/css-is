"""
HTTP route rendering — every GET route returns a non-5xx response and renders
its template for a fully-authorized (admin) user. The TestClient is configured
with raise_server_exceptions=True, so any unhandled 500 fails as a traceback.
"""
import pytest

# (path-template, builds-with-sample-ids). status must be < 500 and not the
# login redirect (i.e. the page actually rendered for an authorized admin).
GET_ROUTES = [
    "/", "/?view=me", "/dashboard", "/reports/activities", "/dashboard/people",
    "/dashboard/teams", "/dashboard/trends", "/dashboard/participation", "/reports",
    "/reports?type=2", "/reports?type=3",
    "/reports/verbatims", "/directory", "/directory/staff/new",
    "/arta", "/encode", "/admin/users", "/admin/audit",
    "/work-arrangement", "/work-arrangement/file",
    "/work-arrangement/schedule",
]

@pytest.mark.parametrize("path", GET_ROUTES)
def test_get_route_renders_for_admin(admin, path):
    r = admin.get(path)
    assert r.status_code == 200, f"{path} -> {r.status_code}\n{r.text[:300]}"
    assert r.text.strip(), f"{path} rendered empty body"

def test_admin_without_a_chief_seat_has_no_approvals_inbox(admin):
    """The approvals inbox is for people requests are routed to (a directory chief seat or an acting
    OIC), not for the admin role alone, so the old /work-arrangement/approvals bookmark lands on
    "No access" for such an admin. A chief seat is covered in test_wellness."""
    assert admin.get("/approvals").status_code == 403
    assert admin.get("/work-arrangement/approvals").status_code == 403


def test_csm_blhsd_export_honors_period(admin):
    r = admin.get("/csm-blhsd/export?period=year:2026")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers.get("content-type", "")
    assert r.content[:2] == b"PK"  # a real .xlsx (zip) payload


def test_reports_export_formats(admin):
    # Every report type renders in every official format with a valid payload.
    sigs = {"docx": b"PK", "pdf": b"%PDF", "pptx": b"PK"}
    for t in (1, 2, 3):
        for fmt, sig in sigs.items():
            r = admin.get(f"/reports/export?type={t}&fmt={fmt}")
            assert r.status_code == 200, f"type {t} {fmt} -> {r.status_code}"
            assert r.content[:len(sig)] == sig, f"type {t} {fmt} bad payload"


def test_reports_type3_xlsx_export(admin):
    # #44: the Resource Persons (type 3) report offers a raw-data Excel download.
    r = admin.get("/reports/export?type=3&fmt=xlsx")
    assert r.status_code == 200
    assert r.content[:2] == b"PK"                       # a real .xlsx (zip)
    assert "spreadsheetml" in r.headers["content-type"]
    # The type-3 download menu surfaces the link.
    page = admin.get("/reports?type=3").text
    assert "fmt=xlsx" in page
    # Type 2 (activities SERVQUAL) also supports the raw Excel.
    assert admin.get("/reports/export?type=2&fmt=xlsx").content[:2] == b"PK"


def test_reports_type1_xlsx_coerced_to_docx(admin):
    # Type 1 (ARTA/CO-CSM) has no servqual_xlsx; a stray fmt=xlsx must not 500 —
    # it falls back to the Word document instead.
    r = admin.get("/reports/export?type=1&fmt=xlsx")
    assert r.status_code == 200
    assert "wordprocessingml" in r.headers["content-type"]


def test_dashboard_trends_export_all_types_and_formats(admin):
    # The redesigned Trends download must render for every survey type in every
    # format with a valid payload (the multi-panel control-band/CI/unhappy/by-area
    # figure for image formats; the data tables for csv/xlsx/pptx).
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for t in (1, 2, 3):
        for fmt, sig in sigs.items():
            r = admin.get(f"/dashboard/export?visual=trends&survey_type={t}&fmt={fmt}")
            assert r.status_code == 200, f"type {t} {fmt} -> {r.status_code}"
            assert len(r.content) > 100, f"type {t} {fmt} empty"
            if sig:
                assert r.content[:len(sig)] == sig, f"type {t} {fmt} bad payload"


def test_dashboard_pulse_export_all_formats(admin):
    # The whole-page Pulse download (all 3 vital signs + summary) renders in every
    # format and honors the window param.
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for win in ("all", "d30"):
        for fmt, sig in sigs.items():
            r = admin.get(f"/dashboard/export?visual=pulse&win={win}&fmt={fmt}")
            assert r.status_code == 200, f"win {win} {fmt} -> {r.status_code}"
            assert len(r.content) > 100, f"win {win} {fmt} empty"
            if sig:
                assert r.content[:len(sig)] == sig, f"win {win} {fmt} bad payload"


def test_dashboard_verbatims_export_all_formats(admin):
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for fmt, sig in sigs.items():
        r = admin.get(f"/dashboard/export?visual=verbatims&survey_type=0&fmt={fmt}")
        assert r.status_code == 200, f"{fmt} -> {r.status_code}"
        assert len(r.content) > 100
        if sig:
            assert r.content[:len(sig)] == sig


def test_dashboard_people_export_all_formats(admin):
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for fmt, sig in sigs.items():
        r = admin.get(f"/dashboard/export?visual=people&fmt={fmt}&sort=score")
        assert r.status_code == 200, f"{fmt} -> {r.status_code}"
        assert len(r.content) > 100
        if sig:
            assert r.content[:len(sig)] == sig


def test_dashboard_teams_index_export_all_formats(admin):
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for fmt, sig in sigs.items():
        r = admin.get(f"/dashboard/export?visual=teams_index&fmt={fmt}")
        assert r.status_code == 200, f"{fmt} -> {r.status_code}"
        assert len(r.content) > 100
        if sig:
            assert r.content[:len(sig)] == sig


def test_dashboard_team_export_all_formats(admin):
    import re
    idx = admin.get("/dashboard/teams")
    m = re.search(r"/dashboard/teams/([A-Za-z0-9/_-]+)", idx.text)
    path = m.group(1) if m else "BLHSD"
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for fmt, sig in sigs.items():
        r = admin.get("/dashboard/export", params={"visual": "team", "team_path": path, "fmt": fmt})
        assert r.status_code == 200, f"{fmt} -> {r.status_code}\n{r.text[:200]}"
        assert len(r.content) > 100
        if sig:
            assert r.content[:len(sig)] == sig


def test_dashboard_event_export_all_formats(admin):
    # The per-activity SERVQUAL report renders in every format.
    eid = _first_activity_id(admin)
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for fmt, sig in sigs.items():
        r = admin.get(f"/dashboard/export?visual=event&event_id={eid}&fmt={fmt}")
        assert r.status_code == 200, f"{fmt} -> {r.status_code}\n{r.text[:200]}"
        assert len(r.content) > 100, f"{fmt} empty"
        if sig:
            assert r.content[:len(sig)] == sig, f"{fmt} bad payload"


def test_dashboard_participation_export_all_formats(admin):
    # The whole-page Participation report (volume + coverage + engagement + by-unit
    # + blind spots) renders in every format.
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for grain in ("quarterly", "monthly"):
        for fmt, sig in sigs.items():
            r = admin.get(f"/dashboard/export?visual=participation&grain={grain}&fmt={fmt}")
            assert r.status_code == 200, f"{grain} {fmt} -> {r.status_code}"
            assert len(r.content) > 100, f"{grain} {fmt} empty"
            if sig:
                assert r.content[:len(sig)] == sig, f"{grain} {fmt} bad payload"


def test_dashboard_person_export_all_formats(admin, sample_ids):
    # The full-breadth person report renders in every format and honors the period.
    rid = sample_ids["rp_id"]
    sigs = {"png": b"\x89PNG", "pdf": b"%PDF", "csv": b"", "xlsx": b"PK", "pptx": b"PK"}
    for fmt, sig in sigs.items():
        r = admin.get(f"/dashboard/export?visual=person&rp_id={rid}&fmt={fmt}&period=all")
        assert r.status_code == 200, f"{fmt} -> {r.status_code}\n{r.text[:200]}"
        assert len(r.content) > 100, f"{fmt} empty"
        if sig:
            assert r.content[:len(sig)] == sig, f"{fmt} bad payload"


def test_dashboard_person_detail(admin, sample_ids):
    r = admin.get(f"/dashboard/people/{sample_ids['rp_id']}")
    assert r.status_code == 200, r.text[:300]

def _first_activity_id(admin):
    import re
    idx = admin.get("/reports/activities")
    assert idx.status_code == 200
    ids = re.findall(r'/reports/activities/(\d+)"', idx.text)
    assert ids, "no activity links on the activities index"
    return ids[0]

def test_dashboard_activity_report(admin):
    # The per-activity report renders the SERVQUAL scorecard, never 500.
    eid = _first_activity_id(admin)
    r = admin.get(f"/reports/activities/{eid}")
    assert r.status_code == 200, r.text[:300]
    assert "Service quality, dimension by dimension" in r.text


def test_activity_report_links_to_rated_resource_person(viewer, manager, admin, app_mod, sample_ids):
    import storage as st

    rp_id = sample_ids["rp_id"]
    response = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Linked RP activity",
        "event_date": "2026-08-14", "venue": "Linked RP hall", "qr_mode": "combined",
        "rp_id": [str(rp_id)], "topic": ["Workshop"],
    }, follow_redirects=True)
    assert response.status_code == 200
    conn = st.connect(app_mod.DB)
    event_id = conn.execute("SELECT id FROM event WHERE title=? ORDER BY id DESC LIMIT 1",
                            ("Linked RP activity",)).fetchone()[0]
    forms = conn.execute(
        "SELECT fi.id, fi.survey_type FROM event_form ef "
        "JOIN form_instance fi ON fi.id=ef.form_instance_id WHERE ef.event_id=?",
        (event_id,)).fetchall()
    eid = min(row[0] for row in forms)
    answers = [("A", 6), *[(f"B{i}", 6) for i in range(1, 10)], ("C", 4)]
    for form_id, _survey_type in forms:
        st.record_response(conn, form_id, answers)
    conn.close()
    app_mod.invalidate_atoms()
    detail = f"/dashboard/people/{rp_id}/activity/{eid}"
    page = viewer.get(f"/reports/activities/{eid}")
    assert page.status_code == 200
    assert "Resource-person ratings for this activity" in page.text
    assert detail in page.text
    assert f"/reports?type=3&amp;activity={eid}" in page.text
    assert viewer.get(detail).status_code == 200

    conn = st.connect(app_mod.DB)
    st.set_rp_hidden(conn, rp_id, True)
    conn.close()
    app_mod.invalidate_atoms()
    hidden_page = viewer.get(f"/reports/activities/{eid}")
    assert detail not in hidden_page.text
    assert detail in admin.get(f"/reports/activities/{eid}").text

def test_dashboard_activity_bogus_id(admin):
    # Unknown activity id -> a clean 404 page, never a 500.
    r = admin.get("/reports/activities/99999999")
    assert r.status_code == 404

def test_old_activities_path_redirects(admin):
    # Activities moved under Reports — the old /dashboard paths 303-redirect so
    # existing bookmarks survive.
    r = admin.get("/dashboard/activities", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/reports/activities"
    r = admin.get("/dashboard/activities/123", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/reports/activities/123"

def test_activity_manual_demographics(admin):
    # Manual demographic entry round-trips onto the report (M:F + DOH:Non-DOH).
    eid = _first_activity_id(admin)
    admin.post(f"/reports/activities/{eid}/demographics",
               data={"male": "3", "female": "2", "doh": "4", "nondoh": "1"})
    r = admin.get(f"/reports/activities/{eid}")
    assert "3:2" in r.text and "4:1" in r.text and "manual entry" in r.text
    # clearing drops the manual override (captured tallies, if any, show through)
    admin.post(f"/reports/activities/{eid}/demographics",
               data={"male": "", "female": "", "doh": "", "nondoh": ""})
    r = admin.get(f"/reports/activities/{eid}")
    assert "manual entry" not in r.text

def test_dashboard_team_detail(admin):
    # Resolve real unit paths from the Teams index, then load each unit's coaching
    # page (bureau / divisions / sections) — every one must render, never 500.
    import re
    idx = admin.get("/dashboard/teams")
    assert idx.status_code == 200
    paths = re.findall(r'/dashboard/teams/([^"?]+)"', idx.text)
    assert paths, "no unit links on the teams index"
    for p in dict.fromkeys(paths):                 # de-dupe, keep order
        r = admin.get(f"/dashboard/teams/{p}")
        assert r.status_code == 200, f"{p} -> {r.status_code}\n{r.text[:200]}"

def test_dashboard_team_bogus_path(admin):
    # Unknown unit path redirects to the index (never 500).
    r = admin.get("/dashboard/teams/BLHSD/NO/SUCH/UNIT")
    assert r.status_code == 200          # followed the redirect to the index
    assert "Teams" in r.text

def test_directory_person_edit(admin, sample_ids):
    r = admin.get(f"/directory/person/{sample_ids['rp_id']}/edit")
    assert r.status_code == 200, r.text[:300]

def test_photo_route(client, sample_ids):
    # public route; returns an image or a placeholder, never 500
    r = client.get(f"/photo/{sample_ids['rp_id']}")
    assert r.status_code in (200, 302, 404)

def test_photo_etag_and_thumbnail(client, app_mod, sample_ids):
    import io
    from PIL import Image
    import storage as st
    buf = io.BytesIO(); Image.new("RGB", (512, 512), (200, 80, 40)).save(buf, "JPEG")
    conn = st.connect(app_mod.DB)
    try:
        rp = conn.execute("INSERT INTO resource_person(name,is_internal) VALUES('Photo T',1)").lastrowid
        st.set_rp_photo(conn, rp, buf.getvalue(), "image/jpeg")
    finally:
        conn.close()
    full = client.get(f"/photo/{rp}")
    assert full.status_code == 200 and full.headers["cache-control"] == "no-store"
    etag = full.headers["etag"]
    # a repeat view with the validator is a bodyless 304
    again = client.get(f"/photo/{rp}", headers={"If-None-Match": etag})
    assert again.status_code == 304 and not again.content
    # thumbnail: much smaller, correct dimensions, its own ETag
    small = client.get(f"/photo/{rp}?s=128")
    assert small.status_code == 200 and small.headers["etag"] != etag
    assert Image.open(io.BytesIO(small.content)).size == (128, 128)
    assert len(small.content) < len(full.content)
    # unsupported sizes fall back to the original
    assert client.get(f"/photo/{rp}?s=999").content == full.content
    assert client.get("/photo/99999999").status_code == 404


def test_respondent_landing_public(client, sample_ids):
    r = client.get(f"/r/{sample_ids['qr_token']}")
    assert r.status_code in (200, 404)  # valid token -> form; stale -> closed/404
    assert "<" in r.text

def test_respondent_landing_bad_token(client):
    r = client.get("/r/totally-bogus-token")
    assert r.status_code in (200, 404)
    assert r.status_code != 500

def test_export_png(admin):
    r = admin.get("/dashboard/export", params={"visual": "pulse", "survey_type": 2, "fmt": "png"})
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert r.headers["content-type"].startswith("image/")

def test_export_bad_format(admin):
    r = admin.get("/dashboard/export", params={"visual": "pulse", "fmt": "exe"})
    assert r.status_code == 400

def test_seq_no_tokens(client):
    r = client.get("/seq")
    assert r.status_code in (200, 400, 404)
    assert r.status_code != 500

def test_openapi_available_to_admin(admin):
    assert admin.get("/openapi.json").status_code == 200
