"""Policy rates (T9): DO 2019-0225 as amended by 2019-0225-A. The tables, the daily allowance rules,
the fare limits, and how they reach the flags and the prepare page."""
from __future__ import annotations
import json
import shutil
import subprocess
from decimal import Decimal as D

import pytest

import rooms
import travel_docs as td
import travel_rates as rt
import travel_rules as tr
from test_travel_generate import conn, dicts, flags, jpost, mk, relay, ride             # noqa: F401


def amount(res):
    return res.total if res else None


# ------------------------------------------------------------------ the tables ---

def test_ltfrb_tables_match_the_add_on_method_printed_on_the_annex():
    """The 60 printed fares were typed in from a scan; the annex also prints the method that makes them."""
    assert len(rt.LTFRB_REGULAR) == len(rt.LTFRB_DISCOUNT) == 60
    for km in range(1, 61):
        assert rt.LTFRB_REGULAR[km - 1] == rt.ltfrb_formula(km), km
        assert rt.LTFRB_DISCOUNT[km - 1] == rt.ltfrb_formula(km, True), km


@pytest.mark.parametrize("km,discounted,fare", [(0.5, False, "10"), (5, False, "10"), (6, False, "11.75"), (12.3, False, "24.75"),
                                                (60, False, "111.75"), (61, False, "113.5"), (6, True, "9.5"), (60, True, "89.5")])
def test_ltfrb_fare(km, discounted, fare):
    assert rt.ltfrb_fare(km, discounted) == D(fare)


def test_ltfrb_fare_needs_a_distance():
    assert rt.ltfrb_fare(0) is None and rt.ltfrb_fare("") is None and rt.ltfrb_fare(-3) is None


def test_every_region_has_a_cluster_and_the_three_rates_are_the_policys():
    assert len(rt.REGIONS) == 17 and len({c for c, _l, _n in rt.REGIONS}) == 17
    assert {n: rt.CLUSTER_DTE[n] for n in (1, 2, 3)} == {1: 1500, 2: 1800, 3: 2200}
    for code, want in {"NCR": 2200, "IV-A": 2200, "IV-B": 2200, "CAR": 1800, "VI": 1800, "VII": 1800, "X": 1800, "XI": 1800,
                       "I": 1500, "II": 1500, "III": 1500, "V": 1500, "VIII": 1500, "IX": 1500, "XII": 1500, "XIII": 1500,
                       "BARMM": 1500}.items():
        assert rt.region_dte(code) == want, code
    assert rt.region_dte("") is None and rt.region_dte("Narnia") is None


def test_annex_c_is_complete_and_consistent():
    codes = [a.code for a in rt.ANNEX_C]
    assert len(codes) == len(set(codes)) == 57
    assert {a.amount for a in rt.ANNEX_C} == {150, 250, 300, 350, 400, 450, 500, 550}
    by = {a.code: a.amount for a in rt.ANNEX_C}
    for code, want in {"paranaque_area_1": 150, "pasay_area_1": 150, "las_pinas_area_1": 250, "makati_area_1": 250,
                       "makati_area_2": 300, "pateros": 300, "manila_area_1": 300, "las_pinas_area_3": 350,
                       "mandaluyong_area_1": 350, "las_pinas_area_4": 400, "san_juan": 400, "quezon_city_area_2": 450,
                       "marikina_area_1": 450, "quezon_city_area_4": 500, "caloocan_area_2": 500, "quezon_city_area_5": 550,
                       "valenzuela_area_3": 550, "caloocan_north_3": 550}.items():
        assert by[code] == want, code
    assert all(a.places for a in rt.ANNEX_C)
    assert rt.area_by_code("outside_metro_manila").amount == 550


def test_find_areas_ignores_accents_and_case():
    assert [a.code for a in rt.find_areas("MAKATI CITY HALL")] == ["makati_area_2"]
    assert "paranaque_area_1" in [a.code for a in rt.find_areas("paranaque")]
    assert [a.code for a in rt.find_areas("Pitogo")] == ["makati_area_2"]
    assert rt.find_areas("x") == [] and rt.find_areas("nowhere at all") == []


@pytest.mark.parametrize("km,cap", [(0.1, 100), (10, 100), (10.01, 250), (15, 250), (15.5, 300), (20, 300), (20.1, 400),
                                    (25, 400), (25.01, 450), (80, 450)])
def test_live_out_bands(km, cap):
    assert rt.live_out_max(km) == cap


def test_live_out_needs_a_distance():
    assert rt.live_out_max(0) is None and rt.live_out_max("") is None


# --------------------------------------------------------------- daily allowance ---

def test_a_full_day_is_shared_fifty_thirty_twenty():
    r = rt.day_amount("full", 2200)
    assert (r.lodging, r.meals, r.incidentals, r.total) == (1100, 660, 440, 2200)
    assert rt.day_amount("full", 1500).total == 1500


def test_a_departure_day_is_half_without_lodging():
    r = rt.day_amount("departure", 1800)
    assert (r.lodging, r.meals, r.incidentals, r.total) == (0, 540, 360, 900)


def test_live_in_pays_nothing_but_the_edge_days_pay_incidentals():
    assert rt.day_amount("live_in", 2200).total == 0
    assert rt.day_amount("live_in_edge", 2200).total == 440


def test_a_part_that_someone_else_paid_is_not_allowed():
    assert rt.day_amount("full", 2200, lodging_provided=True).total == 1100
    assert rt.day_amount("full", 2200, meals_provided=True).total == 1540
    assert rt.day_amount("full", 2200, lodging_provided=True, meals_provided=True).total == 440


def test_the_subsistence_allowance_comes_off_meals_on_working_days_only():
    assert rt.day_amount("full", 2200, receives_sa=True, working_day=True).total == 2150
    assert rt.day_amount("full", 2200, receives_sa=True, working_day=False).total == 2200
    assert rt.day_amount("full", 2200, receives_sa=False).total == 2200
    assert rt.day_amount("departure", 1500, receives_sa=True).total == 700
    assert "subsistence" in " ".join(rt.day_amount("full", 2200, receives_sa=True).notes)


def test_the_subsistence_allowance_never_makes_meals_negative():
    assert rt.day_amount("liaison", 100, receives_sa=True).meals == 0


@pytest.mark.parametrize("kind,total", [("commute", 0), ("monitor", 440), ("monitor_late", 660), ("liaison", 220),
                                        ("hpdpb", 440), ("late_activity", 440)])
def test_within_fifty_km_allowances_use_the_ncr_rate(kind, total):
    assert rt.day_amount(kind, rt.region_dte("NCR")).total == total


def test_meal_allowance_loses_the_subsistence_allowance_and_provided_meals():
    assert rt.day_amount("monitor", 2200, receives_sa=True).total == 390
    assert rt.day_amount("monitor", 2200, meals_provided=True).total == 0
    assert rt.day_amount("late_activity", 2200, receives_sa=True).total == 440         # incidentals are not meals


def test_unknown_kind_or_rate_gives_nothing():
    assert rt.day_amount("nope", 2200) is None and rt.day_amount("full", 0) is None and rt.day_amount("full", "") is None


# ------------------------------------------------------------------- fare limits ---

def row(**kw):
    return {"mode": "taxi", "receipt": "receipt", "basis": "", "place": "", "km": 0, **kw}


def test_activity_rates_by_mode():
    assert rt.row_cap(row(basis="activity", mode="taxi")).amount == 550
    assert rt.row_cap(row(basis="activity", mode="tnvs")).amount == 700
    assert rt.row_cap(row(basis="activity", mode="public_noreceipt")) is None


def test_airport_rate_comes_from_the_area():
    assert rt.row_cap(row(basis="airport", place="makati_area_2")).amount == 300
    assert rt.row_cap(row(basis="airport", place="outside_metro_manila")).amount == 550
    assert rt.row_cap(row(basis="airport", place="")) is None and rt.row_cap(row(basis="airport", place="atlantis")) is None


def test_terminal_and_shuttle_zones_are_not_interchangeable():
    assert rt.row_cap(row(basis="terminal", place="t400")).amount == 400
    assert rt.row_cap(row(basis="shuttle", place="s250")).amount == 250
    assert rt.row_cap(row(basis="shuttle", place="t400")) is None and rt.row_cap(row(basis="terminal", place="s250")) is None


def test_live_out_without_a_receipt_is_held_to_three_hundred():
    assert rt.row_cap(row(basis="live_out", km=22, receipt="receipt")).amount == 400
    assert rt.row_cap(row(basis="live_out", km=22, receipt="none")).amount == 300
    assert rt.row_cap(row(basis="live_out", km=8, receipt="none")).amount == 100
    assert rt.row_cap(row(basis="live_out", km=0)) is None


def test_beyond_fifty_km_uses_the_ltfrb_fare_and_the_discount_option():
    assert rt.row_cap(row(basis="beyond50", km=12.3, mode="public_noreceipt")).amount == D("24.75")
    assert rt.row_cap(row(basis="beyond50", km=12.3, mode="public_noreceipt"), discounted=True).amount == D("19.75")


def test_a_row_with_no_basis_or_a_mode_the_rate_does_not_cover_has_no_cap():
    assert rt.row_cap(row(basis="")) is None and rt.row_cap(row(basis="bogus")) is None
    assert rt.row_cap(row(basis="activity", mode="plane")) is None and rt.row_cap(row(basis="airport", mode="none", place="pateros")) is None


def test_every_basis_has_a_place_list_or_an_input_kind():
    for code, _label, inp, _note in rt.BASES:
        assert inp in ("mode", "area", "zone", "km")
        assert bool(rt.place_choices(code)) == (inp in ("area", "zone")), code
    assert len(rt.place_choices("airport")) == 58


def test_rows_report_policy_per_diem_and_notes():
    rows = [{"date": "2026-09-02", "day_kind": "full", "per_diem": 0}, {"date": "2026-09-05", "day_kind": "full", "per_diem": 0},
            {"date": "2026-09-02", "day_kind": ""}, {"date": "2026-09-02", "mode": "govt", "allowance": 80},
            {"date": "2026-09-02", "basis": "shuttle", "place": "s100", "mode": "taxi"}]
    got = rt.rates_for_rows(rows, {"region": "NCR", "receives_sa": True, "trip_days": 2}, lambda d: d.weekday() < 5)
    assert [g.per_diem for g in got[:3]] == [2150, 2200, None]
    assert "government vehicle" in got[3].warnings[0] and "three days" in got[4].warnings[0]
    no_region = rt.rates_for_rows(rows[:1], {})
    assert no_region[0].per_diem is None and "Choose where" in no_region[0].warnings[0]


# ------------------------------------------------------------------------- rules ---

CEIL = {("rer", "residence_airport"): 550, ("rer", "residence_venue"): 450, ("tnvs", "*"): 700, ("taxi", "*"): 700,
        ("cenrr", "*"): 300}


def kinds(res):
    return sorted(f.kind for f in res.flags)


def test_a_policy_limit_replaces_the_route_ceiling_and_approves_the_route():
    # 560 is over the 550 airport ceiling, but inside the 600 limit... there is none that high; use 300:
    assert kinds(tr.ride_check("taxi", "", 300, "receipt", CEIL, cap=D(300))) == []                 # no 'unlisted route'
    assert kinds(tr.ride_check("taxi", "", 350, "receipt", CEIL, cap=D(300))) == ["over_ceiling"]
    assert kinds(tr.ride_check("taxi", "residence_airport", 350, "receipt", CEIL)) == []            # old behaviour untouched


def test_the_policy_limit_is_checked_even_when_the_fare_fits_a_cenrr():
    res = tr.ride_check("taxi", "", 250, "none", CEIL, cap=D(100))
    assert res.kind == "cenrr" and kinds(res) == ["over_ceiling"]
    assert tr.ride_check("taxi", "", 90, "none", CEIL, cap=D(100)).flags == []


def test_an_unreceipted_fare_above_the_cenrr_amount_is_an_rer_held_to_the_policy_limit():
    res = tr.ride_check("public_noreceipt", "", 500, "none", CEIL, cap=D(450))
    assert res.kind == "rer" and kinds(res) == ["over_ceiling"]
    assert tr.ride_check("public_noreceipt", "", 400, "none", CEIL, cap=D(450)).flags == []


def flags_of(rows, **opts):
    return tr.flags_for({}, rows, {}, CEIL, opts or None, lambda d: d.weekday() < 5)


def drow(per_diem, kind="full", **kw):
    return {"date": "2026-09-02", "mode": "none", "route_type": "", "receipt": "none", "allowance": 0, "per_diem": per_diem,
            "day_kind": kind, **kw}


def test_a_per_diem_above_the_policy_is_flagged_and_one_at_or_below_is_not():
    assert flags_of([drow(2200)], region="NCR") == []
    assert flags_of([drow(1000)], region="NCR") == []
    got = flags_of([drow(2300)], region="NCR")
    assert [f.kind for f in got] == ["over_ceiling"] and got[0].detail.startswith("Per diem") and "100" in got[0].detail
    assert tr.flag_label(got[0].kind, got[0].detail) == tr.PER_DIEM_LABEL
    assert flags_of([drow(2200)], region="NCR", receives_sa=True)[0].detail.startswith("Per diem")      # the allowance brings it to 2150


def test_per_diem_is_only_checked_for_days_with_a_rule_and_a_destination():
    assert flags_of([drow(9999, kind="")], region="NCR") == []
    assert flags_of([drow(9999)]) == []                                                    # no destination chosen: nothing to compare with


def test_a_changed_per_diem_is_a_new_flag():
    a, b = flags_of([drow(2300)], region="NCR")[0], flags_of([drow(2400)], region="NCR")[0]
    assert a.sig != b.sig


def test_rides_with_a_basis_flag_against_the_limit():
    r = {"date": "2026-09-02", "mode": "taxi", "route_type": "", "receipt": "receipt", "allowance": 350, "per_diem": 0,
         "basis": "airport", "place": "makati_area_2", "km": 0}
    assert [f.kind for f in flags_of([r])] == ["over_ceiling"]
    assert flags_of([{**r, "allowance": 300}]) == []


# --------------------------------------------------------- normalize and defaults ---

def test_normalize_keeps_only_known_rate_fields():
    n = td.normalize({"rows": [{"basis": "airport", "place": "pateros", "km": "12.5", "day_kind": "full",
                                "lodging_provided": 1, "meals_provided": 0}, {"basis": "evil", "day_kind": "evil", "km": "999999"}],
                      "rates": {"region": "NCR", "receives_sa": 1, "discounted": 0}})
    a, b = n["rows"]
    assert (a["basis"], a["place"], a["km"], a["day_kind"], a["lodging_provided"], a["meals_provided"]) == ("airport", "pateros", D("12.5"), "full", True, False)
    assert (b["basis"], b["day_kind"], b["km"]) == ("", "", 0)
    assert n["rates"] == {"region": "NCR", "receives_sa": True, "discounted": False}


@pytest.mark.parametrize("raw", [None, "x", [], {"region": "Narnia"}, {"region": 5}])
def test_normalize_rates_never_raises_and_drops_unknown_regions(raw):
    assert td.normalize_rates(raw)["region"] == ""


# ------------------------------------------------------------------------ routes ---

def test_prepare_page_carries_the_policy_tables(viewer, conn, relay):
    ref = mk(viewer)
    html = viewer.get(f"/travel/f/{ref}/prepare").text
    data = json.loads(html.split('id="prep-data">', 1)[1].split("</script>", 1)[0])
    pol = data["policy"]
    assert len(pol["regions"]) == 17 and pol["rates_url"] == f"/travel/f/{ref}/rates"
    assert [b[0] for b in pol["bases"]] == list(rt.BASIS_CODES) and [k[0] for k in pol["day_kinds"]] == list(rt.DAY_KIND_CODES)
    assert len(pol["places"]["airport"]) == 58 and len(pol["places"]["shuttle"]) == 5 and len(pol["places"]["terminal"]) == 4
    assert data["rates"] == {"region": "", "receives_sa": False, "discounted": False}
    assert {"basis", "place", "km", "day_kind"} <= set(data["rows"][0])


def test_calculator_answers_per_row(viewer, conn, relay):
    ref = mk(viewer)
    rows = [{**ride("2026-09-02", 0), "basis": "airport", "place": "pateros", "mode": "taxi", "receipt": "receipt"},
            {**ride("2026-09-02", 0), "day_kind": "full"}, {**ride("2026-09-02", 0)}]
    r = jpost(viewer, f"/travel/f/{ref}/rates", {"rows": rows, "rates": {"region": "CAR"}})
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["dte"] == 1800 and len(j["rows"]) == 3
    assert j["rows"][0]["cap"] == 300 and "Annex C" in j["rows"][0]["cap_rule"]
    assert j["rows"][1]["per_diem"] == 1800 and j["rows"][1]["day"]["lodging"] == 900
    assert j["rows"][2]["cap"] is None and j["rows"][2]["per_diem"] is None


def test_calculator_takes_the_working_day_from_the_calendar(viewer, conn, relay):
    ref = mk(viewer)
    assert rooms.is_working_day(conn, "2026-09-02") and not rooms.is_working_day(conn, "2026-09-05")
    rows = [{**ride("2026-09-02", 0), "day_kind": "full"}, {**ride("2026-09-05", 0), "day_kind": "full"}]
    j = jpost(viewer, f"/travel/f/{ref}/rates", {"rows": rows, "rates": {"region": "NCR", "receives_sa": True}}).json()
    assert [x["per_diem"] for x in j["rows"]] == [2150, 2200]


def test_calculator_is_owner_only_same_origin_and_survives_garbage(viewer, encoder, conn, relay):
    ref = mk(viewer)
    assert jpost(encoder, f"/travel/f/{ref}/rates", {"rows": []}).status_code == 404
    assert jpost(viewer, f"/travel/f/{ref}/rates", {"rows": []}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert viewer.post(f"/travel/f/{ref}/rates", content="not json").status_code == 400
    j = jpost(viewer, f"/travel/f/{ref}/rates", {"rows": [1, "x", {"basis": {}, "km": [], "day_kind": None}], "rates": "bad"}).json()
    assert j["ok"] and len(j["rows"]) == 1 and j["dte"] is None


def test_calculator_stores_nothing(viewer, conn, relay):
    ref = mk(viewer)
    before = [dict(zip(("a", "b"), r)) for r in conn.execute("SELECT answers_json, updated_at FROM travel_filing")]
    jpost(viewer, f"/travel/f/{ref}/rates", {"rows": [{"day_kind": "full", "from": "ZEBRA-9931"}], "rates": {"region": "NCR"}})
    assert [dict(zip(("a", "b"), r)) for r in conn.execute("SELECT answers_json, updated_at FROM travel_filing")] == before


def test_generate_flags_a_ride_over_its_policy_limit_and_an_over_claimed_day(viewer, conn, relay):
    ref = mk(viewer)
    rows = [{**ride("2026-09-02", 350, route="", mode="taxi", receipt="receipt"), "basis": "airport", "place": "makati_area_2"},
            {**ride("2026-09-03", 0, route=""), "day_kind": "full", "per_diem": 2300}]
    r = jpost(viewer, f"/travel/f/{ref}/generate", {"rows": rows, "rates": {"region": "NCR"}})
    assert r.status_code == 200 and r.json()["flags"] == 2
    assert sorted(f["detail"].split()[0] for f in flags(conn, ref)) == ["Fare", "Per"]
    assert {f["kind"] for f in flags(conn, ref)} == {"over_ceiling"}
    rows[0]["allowance"], rows[1]["per_diem"] = 300, 2200
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": rows, "rates": {"region": "NCR"}})
    assert flags(conn, ref) == []


def test_a_fare_keeps_its_label_and_a_per_diem_gets_its_own():
    assert tr.flag_label("over_ceiling", "Fare 350 is 50 above the 300 ceiling.") == "Fare above the ceiling"
    assert tr.flag_label("over_ceiling", "Per diem 2,300 is 100 above") == "Per diem above the policy rate"
    assert tr.flag_label("participant_only") == tr.FLAG_LABELS["participant_only"] and tr.flag_label("mystery") == "mystery"


def test_the_verify_page_headings_a_per_diem_flag_as_one(viewer, encoder, conn, relay):
    from conftest import join_admin_section
    ref = mk(viewer)
    jpost(viewer, f"/travel/f/{ref}/generate", {"rows": [{**ride("2026-09-03", 0, route=""), "day_kind": "full", "per_diem": 2300}],
                                                "rates": {"region": "NCR"}})
    uid = conn.execute("SELECT id FROM admin_user WHERE username='encoder@test.local'").fetchone()[0]
    join_admin_section(conn, uid)
    try:
        page = encoder.get("/travel/verify").text
        assert "Per diem above the policy rate" in page and ref in page
    finally:
        conn.execute("UPDATE admin_user SET rp_id=NULL WHERE id=?", (uid,)); conn.commit()


def test_rate_card_page(viewer, conn):
    r = viewer.get("/travel/rates")
    assert r.status_code == 200
    for text in ("Php 2,200", "Php 1,800", "Php 1,500", "Makati Area 2", "Valenzuela Area 4", "Php 450", "Annex B", "111.75",
                 "Policy rates"):
        assert text in r.text, text
    assert 'href="/travel/rates"' in viewer.get("/travel").text


def test_rate_card_respects_the_switch(viewer, conn):
    import storage as st
    st.set_setting(conn, "travel.enabled", "0"); conn.commit()
    r = viewer.get("/travel/rates")
    assert r.status_code == 200 and "Php 2,200" not in r.text


# ------------------------------------------------- the page and the server agree ---

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_ride_rules_agree_with_the_python_rules_when_a_policy_limit_applies():
    cases = [("taxi", "", 300, "receipt", 300), ("taxi", "", 350, "receipt", 300), ("tnvs", "", 701, "receipt", 700),
             ("public_noreceipt", "", 250, "none", 100), ("public_noreceipt", "", 90, "none", 100),
             ("public_noreceipt", "", 500, "none", 450), ("public_noreceipt", "", 400, "none", 450),
             ("public_noreceipt", "", 1200, "none", 1500), ("taxi", "residence_airport", 560, "receipt", None),
             ("public_noreceipt", "residence_airport", 560, "none", None), ("plane", "", 5000, "none", 300)]
    flat = [[m, r, a] for (m, r), a in CEIL.items()]
    script = ("global.window=undefined;const src=require('fs').readFileSync('static/js/travel_prepare.js','utf8');"
              "const g={};new Function('globalThis',src.replace(/\\}\\)\\(typeof window[^\\n]*$/, '})(globalThis);'))(g);"
              f"const c=g.TravelPrepare.ceilings({json.dumps(flat)});"
              f"console.log(JSON.stringify({json.dumps(cases)}.map(x=>{{const r=g.TravelPrepare.rideCheck(x[0],x[1],x[2],x[3],c,x[4]);return [r.kind,r.flags.length]}})));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    for case, (kind, n) in zip(cases, json.loads(out.stdout)):
        res = tr.ride_check(case[0], case[1], case[2], case[3], CEIL, cap=None if case[4] is None else D(case[4]))
        assert (res.kind, len(res.flags)) == (kind, n), case
