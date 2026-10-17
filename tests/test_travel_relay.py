"""Travel documents relay (T4): the signed client, and the admin page and link check that use it."""
from __future__ import annotations
import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import urlencode

import httpx
import pytest

import gdocs_relay as gr
import ratelimit
import storage as st
import travel
import tzutil as tz

URL, SECRET = "https://script.google.com/macros/s/AKfyc/exec", "s3cret"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


class Resp:
    def __init__(self, status=200, payload=None, text="", url="https://script.googleusercontent.com/macros/echo?id=1"):
        self.status_code, self._p, self.text, self.url = status, payload, text, url

    def json(self):
        if self._p is None:
            raise ValueError("no json")
        return self._p


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv(gr.ENV_URL, URL)
    monkeypatch.setenv(gr.ENV_SECRET, SECRET)


class Posts(list):
    replies: list


@pytest.fixture()
def posts(monkeypatch):
    log = Posts()
    replies = []

    def fake(url, **kw):
        log.append((url, kw))
        r = replies.pop(0) if replies else Resp(200, {"ok": True})
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(gr.httpx, "post", fake)
    log.replies = replies
    return log


# ------------------------------------------------------------------ client ---

def test_not_configured_never_posts(monkeypatch, posts):
    monkeypatch.delenv(gr.ENV_URL, raising=False); monkeypatch.delenv(gr.ENV_SECRET, raising=False)
    r = gr.call("ping")
    assert not r.ok and r.error == "not_configured" and posts == [] and not gr.configured()


def test_the_envelope_is_signed_over_ts_dot_payload(env, posts):
    assert gr.call("check_link", url="https://drive.google.com/file/d/x").ok
    url, kw = posts[0]
    e = kw["json"]
    assert url == URL and set(e) == {"ts", "payload", "sig"} and isinstance(e["ts"], int)
    want = hmac.new(SECRET.encode(), f"{e['ts']}.{e['payload']}".encode(), hashlib.sha256).hexdigest()
    assert e["sig"] == want
    assert json.loads(e["payload"]) == {"action": "check_link", "url": "https://drive.google.com/file/d/x"}
    assert "s3cret" not in json.dumps(e)


def test_timeout_and_redirects(env, posts):
    gr.call("ping")
    kw = posts[0][1]
    assert kw["follow_redirects"] is True
    assert kw["timeout"].read == 90.0 and kw["timeout"].connect == 10.0


def test_a_transport_error_is_retried_once_with_the_same_request_id(env, posts):
    posts.replies[:] = [httpx.ConnectError("boom"), Resp(200, {"ok": True, "id": "d1", "url": "u"})]
    r = gr.Relay().generate_doc(request_id="TF-2610-0001:appendix_a:1", template_key="appendix_a",
                                folder_key="TF-2610-0001", title="T")
    assert r.ok and len(posts) == 2
    payloads = [json.loads(p[1]["json"]["payload"]) for p in posts]
    assert payloads[0]["request_id"] == payloads[1]["request_id"] == "TF-2610-0001:appendix_a:1"


def test_two_transport_errors_give_unreachable_and_never_raise(env, posts):
    posts.replies[:] = [httpx.ReadTimeout("x"), httpx.ReadTimeout("x")]
    r = gr.call("ping")
    assert not r.ok and r.error == "unreachable" and len(posts) == 2


def test_a_sign_in_page_is_classified_as_script_not_run(env, posts):
    posts.replies[:] = [Resp(200, None, text="<html>sign in</html>", url="https://accounts.google.com/ServiceLogin?x")]
    assert gr.call("ping").error == "script_not_run" and len(posts) == 1


def test_an_unconfirmed_200_is_a_failure_not_a_success(env, posts):
    posts.replies[:] = [Resp(200, None, text="<html>echo</html>")]
    r = gr.call("generate_doc")
    assert not r.ok and r.error == "unconfirmed"


def test_http_errors_and_script_errors(env, posts):
    posts.replies[:] = [Resp(500, None)]
    assert gr.call("ping").error == "http_500"
    posts.replies[:] = [Resp(200, {"ok": False, "error": "unauthorized"})]
    r = gr.call("ping")
    assert r.error == "unauthorized" and "secret" in gr.describe(r.error)


def test_describe_never_returns_empty():
    for code in ("", "not_configured", "unreachable", "script_not_run", "unconfirmed", "http_500", "weird"):
        assert gr.describe(code)


def test_the_script_source_matches_the_signing_scheme():
    src = open("apps_script/travel_docs.gs").read()
    assert "computeHmacSha256Signature(env.ts + '.' + env.payload" in src
    assert "5 * 60 * 1000" in src and "ALLOWED_DOMAIN" in src and "request_id=" in src


# --------------------------------------------------------- admin and routes ---

class FakeRelay(gr.Relay):
    def __init__(self):
        self.pings, self.checks, self.result = 0, [], gr.RelayResult(True, {"id": "FILEID123", "name": "scan.pdf", "mime": "application/pdf"})
        self.uploads, self.trashed, self.ping_version = [], [], 1
        self.upload_result = gr.RelayResult(True, {"id": "F1", "name": "n.pdf", "count": 1, "folder_id": "FOLDER1234567890123456",
                                                   "folder_url": "https://drive.google.com/drive/folders/FOLDER1234567890123456"})
        self.trash_ok = True

    def upload_file(self, **kw):
        self.uploads.append(kw)
        return self.upload_result

    def trash_file(self, file_id):
        self.trashed.append(file_id)
        return gr.RelayResult(self.trash_ok, error="" if self.trash_ok else "unreachable")

    def ping(self):
        self.pings += 1
        return self.result if not self.result.data else gr.RelayResult(True, {"version": self.ping_version})

    def check_link(self, url):
        self.checks.append(url)
        return self.result


@pytest.fixture()
def fake(monkeypatch):
    f = FakeRelay()
    monkeypatch.setattr(gr, "get_relay", lambda: f)
    ratelimit._HITS.clear()
    return f


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for t in ("travel_flag", "travel_item", "travel_filing"):
        c.execute(f"DELETE FROM {t}")
    for k in ("head_name", "station"):
        st.set_setting(c, f"travel.sig.{k}", "")
    st.set_setting(c, "travel.template_admins", ""); st.set_setting(c, "travel.enabled", "1")
    c.commit(); c.close()


def post(client, path, **data):
    return client.post(path, content=urlencode(data), headers=FORM, follow_redirects=False)


def mk(client, **over):
    f = {"kind": "liquidation", "title": "RELAYTEST Visit", "start": (tz.today_local() - timedelta(days=10)).isoformat(),
         "end": (tz.today_local() - timedelta(days=8)).isoformat(), "role": "secretariat",
         "advance_amount": "5000", "mc114_format": "none", "dpo_no": "2026-100"}
    f.update(over)
    r = post(client, "/travel/new", **f)
    return r.headers["location"].split("?")[0].rsplit("/", 1)[1]


def jpost(client, path, body, headers=None):
    return client.post(path, content=json.dumps(body), headers={"Content-Type": "application/json", **(headers or {})})


def test_admin_page_shows_status_and_ping_reports_the_result(admin, fake, env):
    page = admin.get("/admin/travel").text
    assert "Test the relay" in page and "script.google.com" in page and "s3cret" not in page
    r = post(admin, "/admin/travel/ping")
    assert r.status_code == 303 and fake.pings == 1
    assert "answered" in admin.get(r.headers["location"]).text
    fake.result = gr.RelayResult(False, error="unauthorized")
    assert "rejected the signature" in admin.get(post(admin, "/admin/travel/ping").headers["location"]).text


def test_admin_page_without_setup_says_so(admin, monkeypatch):
    monkeypatch.delenv(gr.ENV_URL, raising=False); monkeypatch.delenv(gr.ENV_SECRET, raising=False)
    page = admin.get("/admin/travel").text
    assert "Not set up yet" in page and "Test the relay" not in page


def test_only_app_admins_reach_the_relay_controls(viewer, manager, fake):
    for c in (viewer, manager):
        assert post(c, "/admin/travel/ping").status_code in (302, 303, 403) and fake.pings == 0
        r = post(c, "/admin/travel/signatories", head_name="X")
        assert r.status_code in (302, 303, 403)


def test_signatories_and_template_admins_save_and_keep_the_switch(admin, conn):
    post(admin, "/admin/travel/signatories", head_name="  Dr  Ana  Cruz ", station="Manila",
         template_admins="B@doh.gov.ph, a@doh.gov.ph,b@doh.gov.ph")
    assert st.get_setting(conn, "travel.sig.head_name") == "Dr Ana Cruz"
    assert st.get_setting(conn, "travel.template_admins") == "b@doh.gov.ph,a@doh.gov.ph"
    assert travel.enabled(conn)
    assert "Dr Ana Cruz" in admin.get("/admin/travel").text


def test_link_check_saves_the_link_and_file_id(viewer, conn, fake):
    ref = mk(viewer)
    r = jpost(viewer, f"/travel/f/{ref}/link-check", {"code": "dpo", "url": "https://drive.google.com/file/d/ABC/view"})
    assert r.status_code == 200 and r.json() == {"ok": True, "name": "scan.pdf", "mime": "application/pdf"}
    row = conn.execute("SELECT drive_url, drive_file_id, state FROM travel_item WHERE item_code='dpo'").fetchone()
    assert tuple(row) == ("https://drive.google.com/file/d/ABC/view", "FILEID123", "present")


def test_link_check_rejects_bad_input_without_calling_the_relay(viewer, conn, fake):
    ref = mk(viewer)
    p = f"/travel/f/{ref}/link-check"
    assert jpost(viewer, p, {"code": "dpo", "url": "https://evil.example/x"}).status_code == 400
    assert jpost(viewer, p, {"code": "nope", "url": "https://drive.google.com/file/d/ABC/view"}).status_code == 400
    assert viewer.post(p, content="not json", headers={"Content-Type": "application/json"}).status_code == 400
    assert jpost(viewer, p, {"code": "dpo", "url": "https://drive.google.com/x"},
                 headers={"Origin": "https://evil.example"}).status_code == 403
    assert fake.checks == []


def test_link_check_reports_relay_problems_in_plain_words(viewer, conn, fake):
    ref = mk(viewer)
    fake.result = gr.RelayResult(False, error="not_accessible")
    r = jpost(viewer, f"/travel/f/{ref}/link-check", {"code": "dpo", "url": "https://drive.google.com/file/d/ABC/view"})
    assert r.status_code == 400 and "Share it" in r.json()["error"]
    assert conn.execute("SELECT drive_url FROM travel_item WHERE item_code='dpo'").fetchone()[0] is None
    fake.result = gr.RelayResult(False, error="not_configured")
    r = jpost(viewer, f"/travel/f/{ref}/link-check", {"code": "dpo", "url": "https://drive.google.com/file/d/ABC/view"})
    assert r.status_code == 502


def test_link_check_is_owner_only_and_rate_limited(viewer, encoder, conn, fake, monkeypatch):
    ref = mk(viewer)
    body = {"code": "dpo", "url": "https://drive.google.com/file/d/ABC/view"}
    assert jpost(encoder, f"/travel/f/{ref}/link-check", body).status_code == 404       # a stranger
    monkeypatch.setenv("CSS_RL_TRAVEL_RELAY", "2/60")
    ratelimit._HITS.clear()
    codes = [jpost(viewer, f"/travel/f/{ref}/link-check", body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_link_check_respects_the_switch(viewer, admin, conn, fake):
    ref = mk(viewer)
    post(admin, "/admin/travel")                                                       # off
    r = jpost(viewer, f"/travel/f/{ref}/link-check", {"code": "dpo", "url": "https://drive.google.com/file/d/ABC/view"})
    assert r.status_code == 403 and fake.checks == []


# ------------------------------------------------------------------ uploads ---

PDF = b"%PDF-1.4 test file"
UP = {"Content-Type": "application/octet-stream", "X-Filename": "My%20Ticket%20(1).pdf"}


def up(client, ref, code="dpo", body=PDF, headers=None):
    return client.post(f"/travel/f/{ref}/upload?code={code}", content=body, headers={**UP, **(headers or {})})


@pytest.fixture()
def on(conn, env):
    st.set_setting(conn, "travel.relay_version", "2")
    conn.commit()
    yield
    st.set_setting(conn, "travel.relay_version", "0")
    conn.commit()


def row(conn, code="dpo"):
    r = conn.execute("SELECT drive_url, drive_file_id, drive_source, state FROM travel_item WHERE item_code=?", (code,)).fetchone()
    return None if r is None else dict(zip(("drive_url", "drive_file_id", "drive_source", "state"), r))


def test_the_script_has_the_upload_actions_and_only_trashes_under_the_root():
    src = open("apps_script/travel_docs.gs").read()
    assert "case 'upload_file'" in src and "case 'trash_file'" in src and "version: 2" in src
    assert "underRoot_(item, rootId)" in src and "request_id=" in src


def test_upload_stores_only_the_folder_link_and_sends_the_bytes_once(viewer, conn, fake, on):
    ref = mk(viewer)
    r = up(viewer, ref)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["url"].startswith("https://drive.google.com/")
    assert len(fake.uploads) == 1
    u = fake.uploads[0]
    assert u["data"] == PDF and u["mime"] == "application/pdf" and u["folder_key"] == ref and u["item_key"] == "dpo"
    assert u["name"] == f"{ref}_dpo_My Ticket _1_.pdf" and u["request_id"].startswith(f"{ref}:dpo:")
    assert tuple(row(conn).values()) == ("https://drive.google.com/drive/folders/FOLDER1234567890123456", "FOLDER1234567890123456", "upload", "present")
    assert all(PDF.decode() not in str(v) for v in conn.execute("SELECT * FROM travel_item").fetchall()[0])
    page = viewer.get(f"/travel/f/{ref}").text
    assert "Add another file" in page and "Open the folder" in page and "Remove uploaded files" in page


def test_a_failed_upload_leaves_the_row_missing(viewer, conn, fake, on):
    ref = mk(viewer)
    fake.upload_result = gr.RelayResult(False, error="unreachable")
    r = up(viewer, ref)
    assert r.status_code == 502 and "could not be reached" in r.json()["error"]
    assert row(conn) is None or row(conn)["state"] == "missing"


def test_upload_refuses_bad_files_rows_and_callers_before_the_relay(viewer, encoder, conn, fake, on):
    ref = mk(viewer)
    assert up(viewer, ref, body=b"MZ not a document").status_code == 415
    assert up(viewer, ref, body=b"").status_code in (400, 413)
    assert up(viewer, ref, body=PDF + b"0" * (6 * 1024 * 1024)).status_code == 413
    assert up(viewer, ref, code="nope").status_code == 400
    assert up(viewer, ref, code="fms_routing_slip").status_code == 400          # an FMIS row takes no file
    assert up(viewer, ref, code="appendix_b").status_code == 400                # a generated form takes no file
    assert up(encoder, ref).status_code == 404                                  # a stranger
    assert up(viewer, ref, headers={"Origin": "https://evil.example"}).status_code == 403
    assert fake.uploads == []


def test_upload_is_off_until_the_relay_reports_version_two(viewer, conn, fake, env):
    st.set_setting(conn, "travel.relay_version", "0"); conn.commit()
    ref = mk(viewer)
    assert up(viewer, ref).status_code == 503 and fake.uploads == []
    assert "Choose file" not in viewer.get(f"/travel/f/{ref}").text


def test_ping_records_the_script_version(admin, conn, fake, env):
    fake.ping_version = 2
    post(admin, "/admin/travel/ping")
    assert st.get_setting(conn, "travel.relay_version") == "2"
    st.set_setting(conn, "travel.relay_version", "0"); conn.commit()


def test_upload_is_rate_limited(viewer, conn, fake, on, monkeypatch):
    ref = mk(viewer)
    monkeypatch.setenv("CSS_RL_TRAVEL_UPLOAD", "2/60")
    ratelimit._HITS.clear()
    assert [up(viewer, ref).status_code for _ in range(3)] == [200, 200, 429]


def test_a_submitted_filing_takes_no_more_files(viewer, conn, fake, on):
    ref = mk(viewer)
    conn.execute("UPDATE travel_filing SET status='submitted' WHERE ref_code=?", (ref,)); conn.commit()
    assert up(viewer, ref).status_code == 400 and fake.uploads == []


def test_remove_trashes_the_folder_first_and_only_then_clears_the_row(viewer, conn, fake, on):
    ref = mk(viewer)
    up(viewer, ref)
    fake.trash_ok = False
    r = post(viewer, f"/travel/f/{ref}/item/dpo/remove-upload")
    assert "err=" in r.headers["location"] and row(conn)["drive_source"] == "upload"       # kept: Drive still has it
    fake.trash_ok = True
    r = post(viewer, f"/travel/f/{ref}/item/dpo/remove-upload")
    assert "ok=" in r.headers["location"] and fake.trashed[-1] == "FOLDER1234567890123456"
    assert tuple(row(conn).values()) == (None, None, None, "missing")


def test_a_pasted_link_replaces_uploads_by_trashing_them_but_a_link_is_never_trashed(viewer, conn, fake, on):
    ref = mk(viewer)
    up(viewer, ref)
    post(viewer, f"/travel/f/{ref}/item/dpo", drive_url="https://drive.google.com/file/d/ABC/view")
    assert fake.trashed == ["FOLDER1234567890123456"]
    assert tuple(row(conn).values()) == ("https://drive.google.com/file/d/ABC/view", None, "link", "present")
    post(viewer, f"/travel/f/{ref}/item/dpo", drive_url="")                         # clearing a pasted link
    post(viewer, f"/travel/f/{ref}/item/dpo/remove-upload")
    assert fake.trashed == ["FOLDER1234567890123456"] and row(conn)["state"] == "missing"


def test_a_link_is_not_replaced_when_the_uploaded_files_cannot_be_trashed(viewer, conn, fake, on):
    ref = mk(viewer)
    up(viewer, ref)
    fake.trash_ok = False
    r = post(viewer, f"/travel/f/{ref}/item/dpo", drive_url="https://drive.google.com/file/d/ABC/view")
    assert "err=" in r.headers["location"] and row(conn)["drive_source"] == "upload"


def test_purge_trashes_uploaded_folders_and_waits_when_drive_will_not(viewer, conn, fake, on):
    uid = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    old = (tz.now() - timedelta(days=500)).isoformat() if hasattr(tz, "now") else "2024-01-01T00:00:00"
    fid = conn.execute("INSERT INTO travel_filing(ref_code, user_id, kind, source_kind, act_title, act_start, act_end, status, submitted_at) "
                       "VALUES ('TF-U-0001', ?, 'liquidation', 'blank', 'T', '2024-01-01', '2024-01-02', 'submitted', ?)", (uid, old)).lastrowid
    conn.execute("INSERT INTO travel_item(filing_id, item_code, handling, state, drive_url, drive_file_id, drive_source) "
                 "VALUES (?, 'dpo', 'upload', 'present', 'https://drive.google.com/drive/folders/X', 'FOLDER1234567890123456', 'upload')", (fid,))
    conn.commit()
    fake.trash_ok = False
    assert travel.purge_filings(conn, relay=fake) == 0                              # Drive failed: nothing blanked, retry next run
    assert row(conn)["drive_source"] == "upload"
    fake.trash_ok = True
    assert travel.purge_filings(conn, relay=fake) == 1
    assert fake.trashed[-1] == "FOLDER1234567890123456" and tuple(row(conn).values()) == (None, None, None, "present")


# ------------------------------------------------- reading tickets on upload ---

import ai_core as _ai
from test_travel_scan import GOOD, JPEG, ai_on


@pytest.fixture()
def ai_clean():
    _ai.reset_cooldown()
    yield
    _ai.reset_cooldown()


def test_a_ticket_upload_is_read_and_the_reading_comes_back(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, flew="1")
    seen = ai_on(conn, monkeypatch, GOOD)
    j = up(viewer, ref, code="plane_ticket", body=JPEG).json()
    assert j["ok"] and j["ai"] is True and j["reading"]["amount"] == 4521.5 and j["reading"]["vendor"] == "Cebu Pacific"
    assert seen["images"] == [("image/jpeg", JPEG)] and fake.uploads[0]["data"] == JPEG
    assert row(conn, "plane_ticket")["drive_source"] == "upload"
    cols = " ".join(str(c) for c in conn.execute("SELECT * FROM travel_item").fetchall())
    assert "4521" not in cols and "Cebu" not in cols                         # the checklist row holds the link only (the reading sits in travel_reading)


def test_other_rows_are_not_read(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, representative_signs="1")
    seen = ai_on(conn, monkeypatch, GOOD)
    j = up(viewer, ref, code="dpo_representative").json()
    assert j["ok"] and j["reading"] is None and "images" not in seen


def test_the_file_is_saved_even_when_the_ai_is_off(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, flew="1")
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    st.set_setting(conn, "ai_mode", "off"); conn.commit()
    j = up(viewer, ref, code="plane_ticket", body=JPEG).json()
    assert j["ok"] and j["reading"] is None and j["ai"] is False
    assert row(conn, "plane_ticket")["state"] == "present"


def test_a_failed_upload_returns_no_reading(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, flew="1")
    ai_on(conn, monkeypatch, GOOD)
    fake.upload_result = gr.RelayResult(False, error="unreachable")
    r = up(viewer, ref, code="plane_ticket", body=JPEG)
    assert r.status_code == 502 and "reading" not in r.json()
    assert row(conn, "plane_ticket") is None or row(conn, "plane_ticket")["state"] == "missing"


def test_the_read_limit_skips_the_reading_but_not_the_upload(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, flew="1")
    ai_on(conn, monkeypatch, GOOD)
    monkeypatch.setenv("CSS_RL_TRAVEL_SCAN", "1/60")
    ratelimit._HITS.clear()
    first = up(viewer, ref, code="plane_ticket", body=JPEG).json()
    second = up(viewer, ref, code="plane_ticket", body=JPEG + b"1").json()
    assert first["reading"] and second["ok"] and second["reading"] is None


def test_the_checklist_marks_each_upload_with_its_name_for_the_reading_list(viewer, conn, fake, on):
    ref = mk(viewer, flew="1")
    page = viewer.get(f"/travel/f/{ref}").text
    assert f'data-ref="{ref}"' in page and 'data-label="Plane ticket / e-ticket"' in page


# ------------------------------------------- the DPO and the Certificate of Appearance ---

import travel_scan as _ts

F = {"act_start": "2026-10-05", "act_end": "2026-10-07", "dpo_no": "2026-123", "dpo_date": "2026-09-20"}
DPO_OK = {"readable": True, "dpo_no": "2026-123", "dpo_date": "2026-09-20", "travel_start": "2026-10-04",
          "travel_end": "2026-10-08", "funding_stated": True, "funding": "GAA MOOE", "note": ""}


def test_clean_dpo_and_appearance_never_trust_bad_answers():
    assert _ts.clean_dpo(None)["readable"] is False and _ts.clean_dpo({"readable": True})["readable"] is False
    d = _ts.clean_dpo({**DPO_OK, "dpo_date": "20/09/2026", "funding": ""})
    assert d["dpo_date"] == "" and d["funding_stated"] is False        # no funding words: not "stated"
    a = _ts.clean_appearance({"readable": True, "date_from": "2026-10-07", "date_to": "2026-10-05"})
    assert (a["date_from"], a["date_to"]) == ("2026-10-05", "2026-10-07")
    assert _ts.clean_appearance({"readable": True, "date_from": "2026-10-05", "date_to": ""})["date_to"] == "2026-10-05"
    assert _ts.clean_appearance({"readable": True, "date_from": "", "date_to": ""})["readable"] is False


def test_a_matching_dpo_raises_nothing():
    assert _ts.check("dpo", _ts.clean_dpo(DPO_OK), F) == ([], None)


def test_the_dpo_is_checked_against_the_filing():
    msgs, fill = _ts.check("dpo", _ts.clean_dpo({**DPO_OK, "dpo_no": "2026-999", "funding_stated": False,
                                                 "funding": "", "travel_start": "2026-10-06"}), F)
    text = " ".join(msgs)
    assert "funding source" in text and "2026-999" in text and "2026-123" in text and "covers" in text
    assert fill == {"dpo_no": "2026-999", "dpo_date": "2026-09-20"}


def test_a_dpo_number_that_differs_only_in_dashes_and_case_matches():
    msgs, fill = _ts.check("dpo", _ts.clean_dpo({**DPO_OK, "dpo_no": "2026 123"}), F)
    assert msgs == [] and fill is None


def test_an_empty_filing_gets_the_number_and_date_offered():
    msgs, fill = _ts.check("dpo", _ts.clean_dpo(DPO_OK), {**F, "dpo_no": None, "dpo_date": None})
    assert msgs == [] and fill == {"dpo_no": "2026-123", "dpo_date": "2026-09-20"}
    assert _ts.check("dpo", _ts.clean_dpo(DPO_OK), {**F, "dpo_date": None})[1] == {"dpo_no": "", "dpo_date": "2026-09-20"}   # the number matches: only the date


def test_an_unreadable_dpo_says_so():
    msgs, fill = _ts.check("dpo", _ts.clean_dpo({"readable": False}), F)
    assert "Could not read" in msgs[0] and fill is None


def test_the_certificate_must_cover_the_activity_dates():
    ok = _ts.clean_appearance({"readable": True, "date_from": "2026-10-05", "date_to": "2026-10-07"})
    assert _ts.check("appearance", ok, F) == ([], None)
    short = _ts.clean_appearance({"readable": True, "date_from": "2026-10-05", "date_to": "2026-10-06"})
    assert "covers Oct 5, 2026 to Oct 6, 2026" in _ts.check("appearance", short, F)[0][0]


def test_a_dpo_upload_returns_the_checks_and_stores_nothing(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, dpo_no="2026-123", dpo_date="2026-09-20")
    seen = ai_on(conn, monkeypatch, {**DPO_OK, "funding_stated": False, "funding": "", "dpo_no": "2026-777"})
    j = up(viewer, ref, code="dpo", body=JPEG).json()
    assert j["ok"] and j["doc"] == "dpo" and j["reading"]["dpo_no"] == "2026-777"
    assert any("funding source" in m for m in j["checks"]) and any("2026-777" in m for m in j["checks"])
    assert j["fill"]["dpo_no"] == "2026-777" and seen["response_schema"] is _ts.DPO_SCHEMA
    f = conn.execute("SELECT dpo_no FROM travel_filing WHERE ref_code=?", (ref,)).fetchone()[0]
    assert f == "2026-123"                                                    # the filing is never changed by a reading
    assert "2026-777" not in " ".join(str(c) for c in conn.execute("SELECT * FROM travel_item").fetchall())


def test_an_appearance_upload_is_checked_against_the_activity(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, cert_of_appearance_available="1")
    ai_on(conn, monkeypatch, {"readable": True, "date_from": "2000-01-01", "date_to": "2000-01-02", "note": ""})
    j = up(viewer, ref, code="cert_appearance", body=JPEG).json()
    assert j["ok"] and j["doc"] == "appearance" and "covers" in j["checks"][0] and j["fill"] is None


def test_receipts_still_come_back_marked_as_receipts(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, flew="1")
    ai_on(conn, monkeypatch, GOOD)
    j = up(viewer, ref, code="plane_ticket", body=JPEG).json()
    assert j["doc"] == "receipt" and j["checks"] == [] and j["fill"] is None
