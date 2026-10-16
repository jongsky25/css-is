"""Google Meet relay: the signed client, and the calendar item routes that use it."""
from __future__ import annotations
import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import urlencode

import pytest

import meet_relay as mr
import storage as st
import tzutil as tz
from conftest import in_the_directory

URL, SECRET = "https://script.google.com/macros/s/AKfyc/exec", "s3cret"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
LINK = "https://meet.google.com/abc-defg-hij"


class Resp:
    def __init__(self, status=200, payload=None):
        self.status_code, self._p, self.text = status, payload, json.dumps(payload)
        self.url = "https://script.googleusercontent.com/macros/echo?id=1"

    def json(self):
        return self._p


class FakeRelay(mr.Relay):
    def __init__(self, ok=True, url=LINK):
        self.calls, self.ok, self.url = [], ok, url

    def _r(self, name, entry):
        self.calls.append((name, entry["uid"]))
        self.last = entry
        return mr.RelayResult(True, {"meet_url": self.url}) if self.ok else mr.RelayResult(False, error="unreachable")

    def create(self, entry): return self._r("create", entry)
    def update(self, entry): return self._r("update", entry)
    def delete(self, entry): return self._r("delete", entry)


@pytest.fixture(autouse=True)
def _admin_in_the_section(app_mod):
    with in_the_directory(app_mod, "admin@test.local", path="ADMINFX/ADMIN"):
        yield


@pytest.fixture()
def relay(monkeypatch):
    monkeypatch.setenv(mr.ENV_URL, URL)
    monkeypatch.setenv(mr.ENV_SECRET, SECRET)
    fake = FakeRelay()
    monkeypatch.setattr(mr, "get_relay", lambda: fake)
    return fake


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'MEET %'").fetchall():
        st.cal_delete(c, i)
    c.commit(); c.close()


def post(client, url, **fields):
    d = (tz.today_local() + timedelta(days=5)).isoformat()
    data = {"title": "MEET Online", "kind": "meeting", "status": "confirmed", "start_date": d,
            "audience": "bureau", "modality": "online", **fields}
    return client.post(url, content=urlencode(list(data.items())), headers=FORM, follow_redirects=False)


def eid(resp):
    return int(resp.headers["location"].split("/calendar/entries/")[1].split("?")[0])


def test_the_request_is_signed_and_calls_the_configured_url(monkeypatch):
    monkeypatch.setenv(mr.ENV_URL, URL); monkeypatch.setenv(mr.ENV_SECRET, SECRET)
    seen = {}

    def fake_post(url, json=None, **kw):
        seen.update(url=url, env=json)
        return Resp(200, {"ok": True, "meet_url": LINK})
    monkeypatch.setattr(mr.httpx, "post", fake_post)
    out = mr.call("create_meet", request_id="u1", title="T", start_date="2027-01-05")
    assert out.ok and out.data["meet_url"] == LINK and seen["url"] == URL
    env = seen["env"]
    want = hmac.new(SECRET.encode(), f"{env['ts']}.{env['payload']}".encode(), hashlib.sha256).hexdigest()
    assert env["sig"] == want and json.loads(env["payload"])["action"] == "create_meet"


def test_not_configured_and_relay_errors_are_results_not_exceptions(monkeypatch):
    monkeypatch.delenv(mr.ENV_URL, raising=False)
    assert mr.call("ping").error == "not_configured"
    monkeypatch.setenv(mr.ENV_URL, URL); monkeypatch.setenv(mr.ENV_SECRET, SECRET)
    monkeypatch.setattr(mr.httpx, "post", lambda *a, **k: Resp(200, {"ok": False, "error": "unauthorized"}))
    assert mr.call("ping").error == "unauthorized"


def test_an_online_item_gets_a_link_and_it_is_saved(manager, relay, conn):
    r = post(manager, "/calendar/new")
    i = eid(r)
    assert "Google Meet link was added" in r.headers["location"] or "Meet" in r.headers["location"].replace("%20", " ")
    assert st.cal_get(conn, i)["meeting_url"] == LINK
    assert [c[0] for c in relay.calls] == ["create"]


def test_face_to_face_and_items_with_a_link_already_do_not_call_the_relay(manager, relay, conn):
    post(manager, "/calendar/new", modality="f2f")
    post(manager, "/calendar/new", meeting_url="https://zoom.us/j/1")
    assert relay.calls == []


def test_a_relay_failure_never_blocks_the_save(manager, relay, conn):
    relay.ok = False
    r = post(manager, "/calendar/new")
    assert r.status_code == 303
    assert st.cal_get(conn, eid(r))["meeting_url"] is None


def test_a_bad_link_from_the_relay_is_not_stored(manager, relay, conn):
    relay.url = "javascript:alert(1)"
    r = post(manager, "/calendar/new")
    assert st.cal_get(conn, eid(r))["meeting_url"] is None


def test_cancelling_deletes_the_event_only_for_our_links(manager, relay, conn):
    i = eid(post(manager, "/calendar/new"))
    relay.calls.clear()
    manager.post(f"/calendar/entries/{i}/cancel", follow_redirects=False)
    assert [c[0] for c in relay.calls] == ["delete"]
    j = eid(post(manager, "/calendar/new", meeting_url="https://zoom.us/j/1"))
    relay.calls.clear()
    manager.post(f"/calendar/entries/{j}/cancel", follow_redirects=False)
    assert relay.calls == []


def test_nothing_happens_when_the_relay_is_not_set_up(manager, conn, monkeypatch):
    monkeypatch.delenv(mr.ENV_URL, raising=False)
    r = post(manager, "/calendar/new")
    assert r.status_code == 303 and st.cal_get(conn, eid(r))["meeting_url"] is None


def test_the_people_on_the_item_are_sent_as_guests_by_email(manager, relay, conn):
    ids = [r[0] for r in conn.execute("SELECT id FROM admin_user WHERE active=1 ORDER BY id LIMIT 2")]
    emails = sorted(r[0].lower() for r in conn.execute(
        f"SELECT username FROM admin_user WHERE id IN ({','.join('?' * len(ids))})", ids))
    # the form posts people as repeated fields
    data = [("title", "MEET Guests"), ("kind", "meeting"), ("status", "confirmed"),
            ("start_date", (tz.today_local() + timedelta(days=6)).isoformat()), ("audience", "people"),
            ("modality", "online")] + [("people", str(i)) for i in ids]
    resp = manager.post("/calendar/new", content=urlencode(data), headers=FORM, follow_redirects=False)
    assert resp.status_code == 303
    assert relay.last["_emails"] == emails


def test_the_item_page_has_a_join_button_for_a_meet_link(manager, relay, conn):
    i = eid(post(manager, "/calendar/new"))
    page = manager.get(f"/calendar/entries/{i}").text
    assert "Join Google Meet" in page and LINK in page


def test_a_typed_link_gets_a_plain_join_button_and_a_cancelled_item_none(manager, relay, conn):
    i = eid(post(manager, "/calendar/new", meeting_url="https://zoom.us/j/1"))
    assert "Join meeting" in manager.get(f"/calendar/entries/{i}").text
    manager.post(f"/calendar/entries/{i}/cancel", follow_redirects=False)
    assert "Join meeting" not in manager.get(f"/calendar/entries/{i}").text
