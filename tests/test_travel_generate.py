"""Prepare and generate (T5): the routes, flag syncing, generation state, failure and retry."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytest

import gdocs_relay as gr
import ratelimit
import storage as st
import travel
import tzutil as tz
from travel_requests import operation_id

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
URL, SECRET = "https://script.google.com/macros/s/AKfyc/exec", "s3cret"


class Recorder(gr.Relay):
    def __init__(self):
        self.calls, self.fail = [], {}                    # fail: {template_key: error_code}

    def generate_doc(self, **kw):
        self.calls.append(kw)
        err = self.fail.get(kw["template_key"])
        if err:
            return gr.RelayResult(False, error=err)
        n = len(self.calls)
        return gr.RelayResult(True, {"ok": True, "id": f"id{n}", "url": f"https://docs.google.com/document/d/doc{n}/edit", "name": kw["title"]})


@pytest.fixture()
def relay(monkeypatch):
    monkeypatch.setenv(gr.ENV_URL, URL); monkeypatch.setenv(gr.ENV_SECRET, SECRET)
    r = Recorder()
    monkeypatch.setattr(gr, "get_relay", lambda: r)
    ratelimit._HITS.clear()
    return r


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for t in ("travel_flag", "travel_item", "travel_filing"):
        c.execute(f"DELETE FROM {t}")
    st.set_setting(c, "travel.enabled", "1"); c.commit(); c.close()


def post(client, path, **data):
    if path == '/travel/new' and 'operation_id' not in data:
        data['operation_id'] = operation_id(client)
    return client.post(path, content=urlencode(data), headers=FORM, follow_redirects=False)


def jpost(client, path, body, headers=None):
    return client.post(path, content=json.dumps(body), headers={"Content-Type": "application/json", **(headers or {})})


def mk(client, **over):
    f = {"kind": "liquidation", "title": "GENTEST Visit", "start": (tz.today_local() - timedelta(days=10)).isoformat(),
         "end": (tz.today_local() - timedelta(days=8)).isoformat(), "role": "secretariat", "advance_amount": "5000",
         "mc114_format": "none", "dpo_no": "2026-100"}
    f.update(over)
    r = post(client, "/travel/new", **f)
    return r.headers["location"].split("?")[0].rsplit("/", 1)[1]


def ride(day, fare, route="residence_airport", mode="public_noreceipt", receipt="none"):
    return {"date": day, "from": "Home", "to": "Airport", "dep": "", "arr": "", "mode": mode, "route_type": route,
            "receipt": receipt, "allowance": fare, "per_diem": 0}


def dicts(conn, sql, args=()):
    cur = conn.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def items(conn, ref):
    return {r["item_code"]: r for r in dicts(
        conn, "SELECT i.* FROM travel_item i JOIN travel_filing f ON f.id=i.filing_id WHERE f.ref_code=?", (ref,))}


def flags(conn, ref):
    return dicts(conn, "SELECT g.* FROM travel_flag g JOIN travel_filing f ON f.id=g.filing_id WHERE f.ref_code=? ORDER BY g.id", (ref,))


# ------------------------------------------------------------------ prepare page ---

def test_prepare_page_embeds_defaults_and_never_the_secret(viewer, conn, relay):
    ref = mk(viewer)
    r = viewer.get(f"/travel/f/{ref}/prepare")
    assert r.status_code == 200 and "prep-data" in r.text and "Post Travel Report" in r.text and "s3cret" not in r.text
    data = json.loads(r.text.split('id="prep-data">', 1)[1].split("</script>", 1)[0])
    assert len(data["rows"]) == 3 and data["post_url"] == f"/travel/f/{ref}/generate"
    assert ["rer", "residence_airport", 550.0] in data["ceilings"]


def test_prepare_is_owner_only(viewer, encoder, conn, relay):
    ref = mk(viewer)
    assert encoder.get(f"/travel/f/{ref}/prepare").status_code == 404


def test_filing_page_links_to_prepare(viewer, conn, relay):
    ref = mk(viewer)
    assert f"/travel/f/{ref}/prepare" in viewer.get(f"/travel/f/{ref}").text


# --------------------------------------------------------------------- generating ---

def test_generate_makes_every_required_form_and_marks_them_present(viewer, conn, relay):
    ref = mk(viewer)
    r = jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-01", 0)], "texts": {"overview": "Fine"}})
    assert r.status_code == 200 and r.json()["ok"] and set(r.json()["started"]) == {"appendix_b", "travel_report"}
    got = items(conn, ref)
    for code in ("appendix_b", "travel_report"):
        assert got[code]["doc_url"].startswith("https://docs.google.com/") and got[code]["doc_state"] == "done:1"
        assert got[code]["state"] == "present"
    assert conn.execute("SELECT gen_state FROM travel_filing WHERE ref_code=?", (ref,)).fetchone()[0] == "done"
    ids = {c["request_id"] for c in relay.calls}
    assert ids == {f"{ref}:appendix_b:1:1", f"{ref}:travel_report:1:1"}
    assert all(c["folder_key"] == ref for c in relay.calls)
    st_ = viewer.get(f"/travel/f/{ref}/status").json()
    assert st_["gen_state"] == "done" and {i["state"] for i in st_["items"]} == {"done"}


def test_form_contents_are_not_stored(viewer, conn, relay):
    ref = mk(viewer)
    secret = "ZEBRA-UNIQUE-TEXT-9931"
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [], "texts": {"overview": secret, "explanation": secret},
                                                "mc114_text": secret, "signatories": {"head_name": secret}})
    assert any(secret in json.dumps(c) for c in relay.calls)                       # it reached the relay ...
    for table in ("travel_filing", "travel_item", "travel_flag"):                   # ... and nowhere in the database
        for row in conn.execute(f"SELECT * FROM {table}"):
            assert secret not in json.dumps([str(x) for x in row])


def test_rides_add_cenrr_and_rer_forms_and_open_flags(viewer, conn, relay):
    ref = mk(viewer)
    rows = [ride("2026-09-01", 250), ride("2026-09-02", 500), ride("2026-09-03", 600, route="")]
    r = jpost(viewer, f"/travel/f/{ref}/generate", {"rows": rows})
    assert r.json()["ok"] and {"cenrr", "rer", "appendix_b", "travel_report"} == set(r.json()["started"])
    keys = [c["template_key"] for c in relay.calls]
    assert keys.count("rer") == 2 and keys.count("cenrr") == 1
    assert items(conn, ref)["rer"]["note"].startswith("More: https://docs.google.com/")
    assert [f["kind"] for f in flags(conn, ref)] == ["unlisted_route"]
    assert flags(conn, ref)[0]["state"] == "open"
    page = viewer.get(f"/travel/f/{ref}").text
    assert "Waiting for the Admin Unit to verify" in page


def test_a_decided_flag_survives_an_unchanged_regeneration_and_resets_when_the_fare_changes(viewer, conn, relay):
    ref = mk(viewer)
    rows = [ride("2026-09-02", 560)]                                      # over the 550 ceiling
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": rows})
    [fl] = flags(conn, ref); assert fl["kind"] == "over_ceiling"
    conn.execute("UPDATE travel_flag SET state='verified', note='ok' WHERE id=?", (fl["id"],)); conn.commit()
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": rows})
    [same] = flags(conn, ref); assert same["id"] == fl["id"] and same["state"] == "verified"
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-02", 570)]})
    [new] = flags(conn, ref); assert new["sig"] != fl["sig"] and new["state"] == "open" and new["note"] is None
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [ride("2026-09-02", 500)]})
    assert flags(conn, ref) == []


def test_participant_role_opens_a_flag(viewer, conn, relay):
    ref = mk(viewer, role="participant")
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []})
    assert [f["kind"] for f in flags(conn, ref)] == ["participant_only"]


def test_a_failed_document_can_be_retried_with_a_new_revision(viewer, conn, relay):
    ref = mk(viewer)
    relay.fail["appendix_b"] = "template_not_set"
    r = jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []})
    assert r.json()["ok"]
    got = items(conn, ref)
    assert got["appendix_b"]["doc_state"] == "failed:1" and not got["appendix_b"]["doc_url"]
    assert "not been set up" in got["appendix_b"]["note"] and got["travel_report"]["doc_state"] == "done:1"
    status = viewer.get(f"/travel/f/{ref}/status").json()
    assert status["gen_state"] == "failed" and [i for i in status["items"] if i["state"] == "failed"][0]["code"] == "appendix_b"
    assert "Generate" in " ".join(travel.missing_for(conn, travel.get_by_ref(conn, ref)))
    relay.fail.clear(); relay.calls.clear()
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [], "codes": ["appendix_b"]})
    got = items(conn, ref)
    assert got["appendix_b"]["doc_state"] == "done:2" and got["appendix_b"]["note"] is None
    assert [c["request_id"] for c in relay.calls] == [f"{ref}:appendix_b:2:1"]
    assert got["travel_report"]["doc_state"] == "done:1"                       # untouched
    assert conn.execute("SELECT gen_state FROM travel_filing WHERE ref_code=?", (ref,)).fetchone()[0] == "done"


def test_a_relay_that_raises_never_leaves_a_run_stuck(viewer, conn, relay, monkeypatch):
    ref = mk(viewer)
    monkeypatch.setattr(relay, "generate_doc", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []}).json()["ok"]
    assert conn.execute("SELECT gen_state FROM travel_filing WHERE ref_code=?", (ref,)).fetchone()[0] == "failed"
    assert {v["doc_state"] for k, v in items(conn, ref).items() if k in ("appendix_b", "travel_report")} == {"failed:1"}


# -------------------------------------------------------------------- guards ---

def test_not_configured_starts_nothing(viewer, conn, monkeypatch):
    monkeypatch.delenv(gr.ENV_URL, raising=False); monkeypatch.delenv(gr.ENV_SECRET, raising=False)
    ref = mk(viewer)
    r = jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []})
    assert r.status_code == 503 and "not set up" in r.json()["error"]
    assert conn.execute("SELECT gen_state FROM travel_filing WHERE ref_code=?", (ref,)).fetchone()[0] == "idle"


def test_generate_checks_origin_owner_json_status_and_switch(viewer, encoder, admin, conn, relay):
    ref = mk(viewer)
    p = f"/travel/f/{ref}/generate"
    assert jpost(viewer, p, {}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert jpost(encoder, p, {"rows": []}).status_code == 404
    assert viewer.post(p, content="nope", headers={"Content-Type": "application/json"}).status_code == 400
    assert relay.calls == []
    post(viewer, f"/travel/f/{ref}/withdraw")
    assert jpost(viewer, p, {"rows": []}).status_code == 409
    ref2 = mk(viewer, title="GENTEST Two")
    post(admin, "/admin/travel")                                                            # switch off
    assert jpost(viewer, f"/travel/f/{ref2}/generate", {"rows": []}).status_code == 403 and relay.calls == []


def test_rate_limited(viewer, conn, relay, monkeypatch):
    ref = mk(viewer)
    monkeypatch.setenv("CSS_RL_TRAVEL_RELAY", "1/60"); ratelimit._HITS.clear()
    assert jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []}).status_code == 200
    assert jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []}).status_code == 429


def test_cannot_start_a_second_run_or_mark_ready_while_running(viewer, conn, relay):
    ref = mk(viewer)
    conn.execute("UPDATE travel_filing SET gen_state='running', updated_at=? WHERE ref_code=?", (tz.now_iso(), ref)); conn.commit()
    assert jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []}).status_code == 409
    f = travel.get_by_ref(conn, ref)
    with pytest.raises(travel.TravelError, match="still being made"):
        travel.mark_ready(conn, f)


def test_a_stuck_run_is_closed_as_failed_after_ten_minutes(viewer, conn, relay):
    ref = mk(viewer)
    old = (datetime.fromisoformat(tz.now_iso()) - timedelta(minutes=11)).isoformat()
    conn.execute("UPDATE travel_filing SET gen_state='running', updated_at=? WHERE ref_code=?", (old, ref))
    conn.execute("UPDATE travel_item SET doc_state='pending:1' WHERE item_code='appendix_b'"); conn.commit()
    s = viewer.get(f"/travel/f/{ref}/status").json()
    assert s["gen_state"] == "failed" and [i for i in s["items"] if i["code"] == "appendix_b"][0]["state"] == "failed"
    assert jpost(viewer, f"/travel/f/{ref}/generate", {"rows": []}).status_code == 200            # can try again


def test_status_is_visible_to_the_admin_unit_but_not_strangers(viewer, encoder, conn, relay):
    ref = mk(viewer)
    assert viewer.get(f"/travel/f/{ref}/status").status_code == 200
    assert encoder.get(f"/travel/f/{ref}/status").status_code == 404
    assert viewer.get("/travel/f/not-a-ref/status").status_code == 404
