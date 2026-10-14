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

    def ping(self):
        self.pings += 1
        return self.result if not self.result.data else gr.RelayResult(True, {"version": 1})

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
         "advance_amount": "5000", "mc114_format": "none"}
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
