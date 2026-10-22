"""Travel flags (T6): every ride vector end to end, the Admin Unit verify queue, ready blocking, the bell."""
from __future__ import annotations
import pytest

import storage as st
import travel
import travel_notify
import tzutil as tz
from conftest import join_admin_section
from test_travel_generate import conn, dicts, flags, items, jpost, mk, post, relay, ride   # noqa: F401

MEMBER = "encoder@test.local"          # becomes an Administrative Section member in the tests below


@pytest.fixture()
def unit(conn):
    uid = conn.execute("SELECT id FROM admin_user WHERE username=?", (MEMBER,)).fetchone()[0]
    join_admin_section(conn, uid)
    yield uid
    conn.execute("UPDATE admin_user SET rp_id=NULL WHERE id=?", (uid,)); conn.commit()


def kinds(conn, ref):
    return sorted(f["kind"] for f in flags(conn, ref))


def generate(client, ref, rows):
    r = jpost(client, f"/travel/f/{ref}/generate", {"rows": rows})
    assert r.status_code == 200, r.text
    return r


# ------------------------------------------------------------------ ride vectors, end to end ---

VECTORS = [
    # (id, mode, route, fare, receipt, expected flag kinds)
    ("tnvs 700 ok", "tnvs", "residence_airport", 700, "receipt", []),
    ("tnvs 701 over", "tnvs", "residence_airport", 701, "receipt", ["over_ceiling"]),
    ("airport 550 ok", "public_noreceipt", "residence_airport", 550, "none", []),
    ("airport 551 over", "public_noreceipt", "residence_airport", 551, "none", ["over_ceiling"]),
    ("venue 450 ok", "public_noreceipt", "residence_venue", 450, "none", []),
    ("venue 451 over", "public_noreceipt", "residence_venue", 451, "none", ["over_ceiling"]),
    ("300 is a CENRR", "public_noreceipt", "residence_airport", 300, "none", []),
    ("300.01 is an RER", "public_noreceipt", "residence_airport", 300.01, "none", []),
    ("1000.01 unreceipted", "public_noreceipt", "residence_airport", 1000.01, "none", ["no_receipt_over_1000", "over_ceiling"]),
    ("unknown route", "public_noreceipt", "", 100, "none", ["unlisted_route"]),
    ("unknown route, receipted taxi", "taxi", "", 500, "receipt", ["unlisted_route"]),
    ("plane is not a ride", "plane", "", 9000, "none", []),
]


@pytest.mark.parametrize("name,mode,route,fare,receipt,expected", VECTORS, ids=[v[0] for v in VECTORS])
def test_ride_vectors(viewer, conn, relay, name, mode, route, fare, receipt, expected):     # noqa: F811
    ref = mk(viewer)
    generate(viewer, ref, [ride("2026-09-01", fare, route=route, mode=mode, receipt=receipt)])
    assert kinds(conn, ref) == expected


def test_the_documents_follow_the_same_rides(viewer, conn, relay):                         # noqa: F811
    ref = mk(viewer)
    generate(viewer, ref, [ride("2026-09-01", 300), ride("2026-09-02", 300.01)])
    keys = [c["template_key"] for c in relay.calls]
    assert keys.count("cenrr") == 1 and keys.count("rer") == 1


# ------------------------------------------------------------------ the verify queue ---

def test_only_the_admin_unit_can_open_the_queue(viewer, encoder, admin, conn, relay, unit):   # noqa: F811
    ref = mk(viewer, role="participant"); generate(viewer, ref, [])
    assert encoder.get("/travel/verify").status_code == 200
    assert viewer.get("/travel/verify").status_code == 403
    assert admin.get("/travel/verify").status_code == 403                    # the app admin role is no bypass
    fid = flags(conn, ref)[0]["id"]
    assert post(viewer, f"/travel/verify/{fid}", outcome="verified", supervisor_confirmed="1").status_code == 403
    assert post(admin, f"/travel/verify/{fid}", outcome="verified", supervisor_confirmed="1").status_code == 403
    assert flags(conn, ref)[0]["state"] == "open"


def test_the_queue_lists_open_flags_with_who_and_where(viewer, encoder, conn, relay, unit):    # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    page = encoder.get("/travel/verify").text
    assert "Fare above the ceiling" in page and ref in page and "GENTEST Visit" in page and "above the 550 ceiling" in page


def test_verify_and_reject_record_the_outcome_and_unblock_or_block_ready(viewer, encoder, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    [fl] = flags(conn, ref)
    blocked = " ".join(travel.missing_for(conn, travel.get_by_ref(conn, ref)))
    assert "Waiting for the Admin Unit" in blocked
    # a rejection needs a note
    r = post(encoder, f"/travel/verify/{fl['id']}", outcome="rejected")
    assert r.status_code == 400 and "Decision not saved" in r.text and flags(conn, ref)[0]["state"] == "open"
    post(encoder, f"/travel/verify/{fl['id']}", outcome="rejected", note="Use the DOH van instead")
    [got] = flags(conn, ref)
    assert got["state"] == "rejected" and got["note"] == "Use the DOH van instead" and got["decided_by"] == MEMBER and got["decided_at"]
    still = " ".join(travel.missing_for(conn, travel.get_by_ref(conn, ref)))
    assert "did not accept" in still and "DOH van" in still
    post(encoder, f"/travel/verify/{fl['id']}", outcome="verified", note="Exception granted")
    assert flags(conn, ref)[0]["state"] == "verified"
    assert "Admin Unit" not in " ".join(travel.missing_for(conn, travel.get_by_ref(conn, ref)))
    assert "Verified" in encoder.get("/travel/verify").text            # shows under recently decided
    assert "Exception granted" in viewer.get(f"/travel/f/{ref}").text   # the person sees the outcome


def test_participant_only_needs_the_supervisor_confirmation(viewer, encoder, conn, relay, unit):   # noqa: F811
    ref = mk(viewer, role="participant"); generate(viewer, ref, [])
    [fl] = flags(conn, ref)
    r = post(encoder, f"/travel/verify/{fl['id']}", outcome="verified")
    assert r.status_code == 400 and "supervisor" in r.text and flags(conn, ref)[0]["state"] == "open"
    post(encoder, f"/travel/verify/{fl['id']}", outcome="verified", supervisor_confirmed="1", note="Per Dr. Reyes")
    [got] = flags(conn, ref)
    assert got["state"] == "verified" and got["supervisor_confirmed"] == 1


def test_a_rejection_sends_a_ready_filing_back_to_open(viewer, encoder, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    f = travel.get_by_ref(conn, ref)
    conn.execute("UPDATE travel_filing SET status='ready', ready_at=? WHERE id=?", (tz.now_iso(), f["id"])); conn.commit()
    [fl] = flags(conn, ref)
    post(encoder, f"/travel/verify/{fl['id']}", outcome="rejected", note="No")
    assert travel.get_by_ref(conn, ref)["status"] == "open"


def test_verified_survives_regeneration_but_a_changed_fare_comes_back_to_the_queue(viewer, encoder, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); rows = [ride("2026-09-01", 560)]
    generate(viewer, ref, rows)
    [fl] = flags(conn, ref)
    post(encoder, f"/travel/verify/{fl['id']}", outcome="verified", note="ok")
    generate(viewer, ref, rows)
    assert flags(conn, ref)[0]["state"] == "verified" and ref not in encoder.get("/travel/verify").text.split("Recently decided")[0]
    generate(viewer, ref, [ride("2026-09-01", 580)])
    assert flags(conn, ref)[0]["state"] == "open" and ref in encoder.get("/travel/verify").text.split("Recently decided")[0]


def test_withdrawn_and_submitted_filings_leave_the_queue(viewer, encoder, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    post(viewer, f"/travel/f/{ref}/withdraw")
    assert ref not in encoder.get("/travel/verify").text
    [fl] = flags(conn, ref)
    r = post(encoder, f"/travel/verify/{fl['id']}", outcome="verified")
    assert r.status_code == 400 and "no longer open" in r.text and flags(conn, ref)[0]["state"] == "open"


def test_decisions_check_origin_the_switch_and_unknown_ids(viewer, encoder, admin, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    fid = flags(conn, ref)[0]["id"]
    bad = encoder.post(f"/travel/verify/{fid}", content="outcome=verified", follow_redirects=False,
                       headers={"Content-Type": "application/x-www-form-urlencoded", "Origin": "https://evil.example"})
    assert bad.status_code == 403 and flags(conn, ref)[0]["state"] == "open"
    assert post(encoder, "/travel/verify/999999", outcome="verified").status_code == 404
    post(admin, "/admin/travel")                                                   # switch off
    assert "not switched on" in encoder.get("/travel/verify").text
    post(encoder, f"/travel/verify/{fid}", outcome="verified")
    assert flags(conn, ref)[0]["state"] == "open"


def test_a_decision_is_audited(viewer, encoder, conn, relay, unit):                  # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    post(encoder, f"/travel/verify/{flags(conn, ref)[0]['id']}", outcome="verified")
    rows = dicts(conn, "SELECT * FROM audit_log WHERE action='travel_flag_decide'")
    assert rows and MEMBER in str(rows[-1])


def test_the_nav_shows_the_queue_only_to_the_admin_unit(viewer, encoder, conn, unit):
    assert 'href="/travel/verify"' in encoder.get("/travel").text
    assert 'href="/travel/verify"' not in viewer.get("/travel").text


# ------------------------------------------------------------------------- the bell ---

def test_bell_for_the_admin_unit_counts_open_flags_and_links_to_the_queue(viewer, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560), ride("2026-09-02", 600, route="")])
    rows = travel_notify.bell_rows(conn, unit, tz.today_local())
    line = [r for r in rows if "to verify" in r["text"]]
    assert line and line[0]["count"] == 2 and line[0]["url"] == "/travel/verify"
    post(viewer, f"/travel/f/{ref}/withdraw")
    assert not [r for r in travel_notify.bell_rows(conn, unit, tz.today_local()) if "to verify" in r["text"]]


def test_bell_tells_the_person_when_something_was_rejected(viewer, encoder, conn, relay, unit):   # noqa: F811
    ref = mk(viewer); generate(viewer, ref, [ride("2026-09-01", 560)])
    uid = conn.execute("SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
    assert not [r for r in travel_notify.bell_rows(conn, uid, tz.today_local()) if "did not accept" in r["text"]]
    post(encoder, f"/travel/verify/{flags(conn, ref)[0]['id']}", outcome="rejected", note="No")
    got = [r for r in travel_notify.bell_rows(conn, uid, tz.today_local()) if "did not accept" in r["text"]]
    assert got and got[0]["count"] == 1 and got[0]["url"] == "/travel"
