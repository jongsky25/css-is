"""DM 2026-0521 pre-audit checks (DM4): the optional details the AI reads off receipts, tickets and fare
screenshots, how they are kept, the flags they raise at generate, and the flag-kind migration."""
from __future__ import annotations
import os
import sqlite3
import tempfile

import pytest

import ai_core as ai
import storage as st
import travel
import travel_readings as trd
import travel_rules as tr
import travel_scan as ts
from test_travel_generate import conn, items, jpost, mk, relay, flags   # noqa: F401  (fixtures + helpers)
from test_travel_scan import GOOD


def rd(i, code, **kw):
    base = {"id": i, "item_code": code, "doc": "receipt", "kind": code, "amount": 250.0, "currency": "PHP",
            "day": "2026-09-01", "origin": "", "destination": "", "vendor": "", "reference": "", "dep_time": "",
            "arr_time": "", "date_from": None, "date_to": None, "stops": None, "passengers": None, "fare_split": None,
            "receipt_source": None, "fare_brand": None, "cabin": None, "booked_at": None, "captured_at": None,
            "round_trip": None}
    return {**base, **kw}


def ride(day, fare, mode="tnvs"):
    return {"date": day, "from": "Home", "to": "Venue", "mode": mode, "route_type": "", "receipt": "receipt",
            "allowance": fare, "per_diem": 0}


def kinds(flags_):
    return sorted(f.kind for f in flags_)


# ------------------------------------------------------------------------------ the reading ---

def test_an_older_answer_without_the_details_is_still_valid():
    got = ts.validated_receipt(GOOD)
    assert got["readable"] and got["stops"] is None and got["cabin"] == "" and got["booked_at"] == ""


def test_the_details_are_kept_when_well_formed():
    got = ts.validated_receipt({**GOOD, "kind": "ridehail_receipt", "stops": 2, "passengers": 3, "fare_split": False,
                                "receipt_source": "app_or_email"})
    assert (got["stops"], got["passengers"], got["fare_split"], got["receipt_source"]) == (2, 3, False, "app_or_email")
    got = ts.validated_receipt({**GOOD, "kind": "plane_ticket", "fare_brand": "GO BASIC", "cabin": "economy",
                                "round_trip": True, "booked_at": "2026-08-20 14:05"})
    assert (got["fare_brand"], got["cabin"], got["round_trip"], got["booked_at"]) == ("GO BASIC", "economy", True,
                                                                                        "2026-08-20 14:05")
    got = ts.validated_receipt({**GOOD, "kind": "fare_screenshot", "captured_at": "2026-08-20 14:01"})
    assert got["kind"] == "fare_screenshot" and got["captured_at"] == "2026-08-20 14:01"


@pytest.mark.parametrize("bad", [{"stops": "2"}, {"stops": 0}, {"stops": 99}, {"passengers": True},
                                 {"fare_split": "no"}, {"round_trip": 1}, {"receipt_source": "forged"},
                                 {"cabin": "luxury"}, {"fare_brand": "<b>GO</b>"}, {"fare_brand": 5},
                                 {"booked_at": "yesterday"}, {"captured_at": "2026-13-40 10:00"}])
def test_a_malformed_detail_rejects_the_reading(bad):
    with pytest.raises(ai.AIBadResponse):
        ts.validated_receipt({**GOOD, **bad})


def test_a_fare_screenshot_upload_is_read():
    assert "plane_fare_proof" in ts.READ_CODES and ts.DOC_FOR["plane_fare_proof"] == ts.DOC_RECEIPT


def test_readings_keep_the_details(conn, viewer, relay):
    ref = mk(viewer)
    f = travel.get_by_ref(conn, ref)
    reading = ts.clean({**GOOD, "kind": "ridehail_receipt", "stops": 2, "fare_split": False, "receipt_source": "screenshot"})
    assert trd.save(conn, f["id"], "ridehail_receipt", "receipt", reading)
    kept = trd.for_filing(conn, f["id"])[0]
    assert (kept["stops"], kept["fare_split"], kept["receipt_source"], kept["passengers"]) == (2, 0, "screenshot", None)


# ------------------------------------------------------------------------------- the checks ---

def test_nothing_is_flagged_when_the_details_were_not_read():
    readings = [rd(1, "ridehail_receipt"), rd(2, "plane_ticket", amount=4000.0)]
    assert tr.reading_flags(readings, [ride("2026-09-01", 250)]) == []


def test_a_receipt_that_does_not_match_the_itinerary_is_flagged():
    rows = [ride("2026-09-01", 250)]
    assert kinds(tr.reading_flags([rd(1, "ridehail_receipt", day="2026-09-02")], rows)) == ["receipt_mismatch"]
    assert kinds(tr.reading_flags([rd(1, "ridehail_receipt", amount=400.0)], rows)) == ["receipt_mismatch"]
    assert tr.reading_flags([rd(1, "ridehail_receipt", amount=250.5)], rows) == []          # rounding is fine
    assert tr.reading_flags([rd(1, "ridehail_receipt", day="2026-09-02")], []) == []      # no itinerary yet


def test_a_multi_stop_or_shared_ride_is_flagged_with_what_it_needs():
    rows = [ride("2026-09-01", 250)]
    got = tr.reading_flags([rd(1, "ridehail_receipt", stops=2, fare_split=0)], rows)
    assert kinds(got) == ["shared_ride"] and "every passenger's claim" in got[0].detail and "no fare split" in got[0].detail
    got = tr.reading_flags([rd(1, "taxi_receipt", passengers=3)], [ride("2026-09-01", 250, "taxi")])
    assert kinds(got) == ["shared_ride"] and "3 passengers" in got[0].detail
    assert tr.reading_flags([rd(1, "ridehail_receipt", stops=1, passengers=1)], rows) == []


def test_premium_cabins_and_other_fare_types_are_flagged():
    assert kinds(tr.reading_flags([rd(1, "plane_ticket", cabin="business")], [])) == ["fare_class"]
    assert kinds(tr.reading_flags([rd(1, "plane_ticket", cabin="premium_economy")], [])) == ["fare_class"]
    assert kinds(tr.reading_flags([rd(1, "plane_ticket", vendor="Cebu Pacific", fare_brand="GO FLEX")], [])) == ["fare_class"]
    assert tr.reading_flags([rd(1, "plane_ticket", vendor="Cebu Pacific", fare_brand="Go Basic")], []) == []
    assert tr.reading_flags([rd(1, "plane_ticket", vendor="Philippine Airlines", fare_brand="Economy Value")], []) == []
    assert tr.reading_flags([rd(1, "plane_ticket", vendor="AirAsia", fare_brand="Value Pack")], []) == []   # brand not checked


def test_fare_screenshots_must_come_before_booking():
    ticket = rd(1, "plane_ticket", amount=4000.0, booked_at="2026-08-20 14:05")
    late = rd(2, "plane_fare_proof", kind="fare_screenshot", captured_at="2026-08-20 15:00")
    early = rd(3, "plane_fare_proof", kind="fare_screenshot", captured_at="2026-08-20 14:01")
    assert kinds(tr.reading_flags([ticket, late], [])) == ["fare_proof"]
    assert tr.reading_flags([ticket, late, early], []) == []
    assert tr.reading_flags([ticket], []) == []                                              # nothing read: nothing said


def test_a_pal_round_trip_needs_both_fares_unless_supersaver():
    trip = rd(1, "plane_ticket", amount=9000.0, vendor="Philippine Airlines", fare_brand="Economy Saver", round_trip=1)
    shot = rd(2, "plane_fare_proof", kind="fare_screenshot")
    got = tr.reading_flags([trip, shot], [])
    assert kinds(got) == ["fare_proof"] and "outbound and the return" in got[0].detail
    assert tr.reading_flags([trip, shot, rd(3, "plane_fare_proof", kind="fare_screenshot")], []) == []
    assert tr.reading_flags([{**trip, "fare_brand": "Economy Supersaver"}, shot], []) == []


def test_flags_are_stable_while_nothing_changes():
    a = tr.reading_flags([rd(1, "ridehail_receipt", stops=2)], [ride("2026-09-01", 250)])
    b = tr.reading_flags([rd(1, "ridehail_receipt", stops=2)], [ride("2026-09-01", 250)])
    assert [f.sig for f in a] == [f.sig for f in b] and tr.flag_label("shared_ride") == "Multi-stop or shared ride"


# ---------------------------------------------------------------------- generate and storage ---

def test_generate_raises_the_reading_flags_for_the_admin_unit(viewer, conn, relay):
    ref = mk(viewer, ride_hailing="1")
    f = travel.get_by_ref(conn, ref)
    reading = ts.clean({**GOOD, "kind": "ridehail_receipt", "amount": 250, "date": "2026-09-01", "stops": 3})
    assert trd.save(conn, f["id"], "ridehail_receipt", "receipt", reading)
    r = jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [{**ride("2026-09-01", 250), "route_type": "residence_venue"}]})
    assert r.status_code == 200
    got = flags(conn, ref)
    assert [g["kind"] for g in got] == ["shared_ride"] and got[0]["state"] == "open"
    assert any("Waiting for the Admin Unit" in m for m in travel.missing_for(conn, travel.get_by_ref(conn, ref)))


def test_an_old_database_is_migrated_keeping_its_flags():
    path = os.path.join(tempfile.mkdtemp(), "old.db")
    c = st.connect(path); st.init_db(c)
    uid = st.create_admin_user(c, "old@x.test", "x", "y", "viewer")
    c.executescript("""
    DROP TABLE travel_flag;
    CREATE TABLE travel_flag (id INTEGER PRIMARY KEY,
      filing_id INTEGER NOT NULL REFERENCES travel_filing(id) ON DELETE CASCADE,
      kind TEXT NOT NULL CHECK (kind IN ('over_ceiling','unlisted_route','no_receipt_over_1000','participant_only')),
      sig TEXT NOT NULL, detail TEXT, state TEXT NOT NULL DEFAULT 'open' CHECK (state IN ('open','verified','rejected')),
      supervisor_confirmed INTEGER NOT NULL DEFAULT 0, note TEXT, decided_by TEXT, decided_at TEXT, created_at TEXT,
      UNIQUE (filing_id, sig));
    ALTER TABLE travel_reading DROP COLUMN stops;
    ALTER TABLE travel_reading DROP COLUMN cabin;
    """)
    c.execute("INSERT INTO travel_filing(user_id, kind, source_kind, act_title, act_start, act_end, status, ref_code) "
              "VALUES (?,'ca','blank','Old','2026-01-01','2026-01-02','open','TF-2601-0001')", (uid,))
    fid = c.execute("SELECT id FROM travel_filing").fetchone()[0]
    c.execute("INSERT INTO travel_flag(filing_id, kind, sig, state, note) VALUES (?, 'over_ceiling', 's1', 'verified', 'ok')",
              (fid,))
    c.commit()
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO travel_flag(filing_id, kind, sig) VALUES (?, 'shared_ride', 's0')", (fid,))
    st.init_db(c)
    assert c.execute("SELECT kind, sig, state, note FROM travel_flag").fetchall() == [("over_ceiling", "s1", "verified", "ok")]
    c.execute("INSERT INTO travel_flag(filing_id, kind, sig) VALUES (?, 'shared_ride', 's2')", (fid,))
    cols = {r[1] for r in c.execute("PRAGMA table_info(travel_reading)")}
    assert {"stops", "cabin", "captured_at"} <= cols
    st.init_db(c)                                                                         # again: nothing changes
    assert c.execute("SELECT COUNT(*) FROM travel_flag").fetchone()[0] == 2 and c.execute("PRAGMA foreign_key_check").fetchall() == []
    c.close()
