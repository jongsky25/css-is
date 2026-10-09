"""
QA smoke test for the dashboard data + export paths.

Run:  python qa_smoke.py

It exercises every TYPE of subject through the insight layer and the exporter —
speaker-only / walk-in-only / both people, internal and external events, every
survey type, every grain — and every export format. The point is to hit the
type-specific code paths (the kind that hid the name/label bug), not just the
happy path. Any exception fails the run.

It SAMPLES a few subjects per kind rather than looping everything, so it stays
fast on a production-sized database; a kind that simply doesn't exist in the
data is reported as a warning, not a failure.
"""

from __future__ import annotations
from datetime import datetime

import storage as st
import dashboard_insights as di
import dashboard_export as dx
import app

import os  # [QA] env knobs for a fast in-CI subset; defaults = full run
_F = os.environ.get("QA_FORMATS")
FORMATS = _F.split(",") if _F else ["png", "jpeg", "pdf", "csv", "xlsx", "pptx"]
_G = os.environ.get("QA_GRAINS")
GRAINS = _G.split(",") if _G else ["monthly", "quarterly", "yearly"]
SAMPLE = int(os.environ.get("QA_SAMPLE", "3"))   # subjects exercised per kind

checks = 0
fails = []
warns = []


def ok(label, fn):
    global checks
    checks += 1
    try:
        fn()
    except Exception as e:                       # noqa: BLE001 - we want everything
        fails.append(f"{label}: {type(e).__name__}: {e}")


def main():
    conn = st.connect(os.environ.get("CSS_DB", "css_is.db"))
    st.init_db(conn)
    atoms = st.load_atoms(conn)
    staff = st.list_resource_persons(conn)
    bureau = st.get_or_create_blhsd(conn)[1]
    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    events = di.build_events(atoms, st.list_activity_instances(conn))

    # --- classify people, then sample a few of each kind ---
    kinds = {"speaker_only": [], "walkin_only": [], "both": []}
    none_count = 0
    for p in staff:
        card = di.person_card(atoms, p)
        if not card:
            none_count += 1
            continue
        if card["arta"] and card["rp"]:
            kinds["both"].append(p)
        elif card["rp"]:
            kinds["speaker_only"].append(p)
        else:
            kinds["walkin_only"].append(p)
    print("People coverage:", {k: len(v) for k, v in kinds.items()}, "| unrated:", none_count)
    for k, people in kinds.items():
        if not people:
            warns.append(f"no '{k}' people in the data — that path untested this run")

    sampled_people = [p for people in kinds.values() for p in people[:SAMPLE]]

    # --- ranked-bar label integrity (the name/label bug) on the sample ---
    def labels_present():
        for p in sampled_people:
            for row in di.person_arta_items(atoms, p) + di.person_dimensions(atoms, p):
                assert row.get("name"), f"ranked row missing 'name': {row}"
        for e in events[:SAMPLE * 4]:
            for row in e["ranked"]:
                assert row.get("name"), f"event ranked row missing 'name': {row}"
    ok("ranked labels present", labels_present)

    # --- PEOPLE sample: every grain, every format ---
    for p in sampled_people:
        for grain in GRAINS:
            params = {"survey_type": 1, "rp_id": p["id"], "grain": grain,
                      "event_id": 0, "admin": True}
            payload, meta = app._visual_payload(conn, atoms, "person", params, bureau, gen)
            assert payload is not None, f"person {p['name']} payload None"
            for fmt in FORMATS:
                ok(f"person[{p['name']}/{grain}].{fmt}",
                   lambda payload=payload, meta=meta, fmt=fmt: dx.export("person", payload, meta, fmt))

    # --- PULSE + TRENDS: every survey type, every grain, every format ---
    for stype in (1, 2, 3):
        pp, pm = app._visual_payload(conn, atoms, "pulse",
                                     {"survey_type": stype, "rp_id": 0, "grain": "monthly",
                                      "event_id": 0, "admin": False}, bureau, gen)
        if pp:
            for fmt in FORMATS:
                ok(f"pulse[{stype}].{fmt}",
                   lambda pp=pp, pm=pm, fmt=fmt: dx.export("pulse", pp, pm, fmt))
        for grain in GRAINS:
            tp, tm = app._visual_payload(conn, atoms, "trends",
                                         {"survey_type": stype, "rp_id": 0, "grain": grain,
                                          "event_id": 0, "admin": False}, bureau, gen)
            if tp:
                for fmt in FORMATS:
                    ok(f"trends[{stype}/{grain}].{fmt}",
                       lambda tp=tp, tm=tm, fmt=fmt: dx.export("trends", tp, tm, fmt))

    # --- EVENTS: a few internal + a few external, every format ---
    internal = [e for e in events if not e["is_external"]][:SAMPLE]
    external = [e for e in events if e["is_external"]][:SAMPLE]
    if not internal:
        warns.append("no internal events in the data")
    if not external:
        warns.append("no external events in the data")
    for e in internal + external:
        ep, em = app._visual_payload(conn, atoms, "event",
                                     {"survey_type": 2, "rp_id": 0, "grain": "monthly",
                                      "event_id": e["id"], "admin": False}, bureau, gen)
        assert ep is not None, f"event {e['name']} payload None"
        for fmt in FORMATS:
            ok(f"event[{e['name']}].{fmt}",
               lambda ep=ep, em=em, fmt=fmt: dx.export("event", ep, em, fmt))

    # --- story panels (verbatim bucketing) on the sample ---
    def stories():
        for e in internal + external:
            di.story_panel(st.verbatims_for_responses(conn, e["response_ids"]))
        for p in sampled_people:
            rids = list(set(di.arta_slice(atoms, p["id"])["response_id"].tolist())
                        | set(di.rp_slice(atoms, p["id"])["response_id"].tolist()))
            di.story_panel(st.verbatims_for_responses(conn, rids))
    ok("story panels", stories)

    # --- TEAMS: org-unit coaching across every unit kind (bureau/division/section/admin) ---
    import css_is_engine as eng
    org = st.org_structure(conn)
    instances = st.list_activity_instances(conn)
    units = []
    if org.get("bureau"):
        units.append(("bureau", org["bureau"]))
    if org.get("directorate"):
        units.append(("office", org["directorate"]))
    for d in org["divisions"]:
        units.append(("division", d))
        for s in d["sections"]:
            units.append(("section", s))
    for s in org["admin_sections"]:
        units.append(("admin_section", s))
    seen = {}

    def teams_layer():
        for kind, u in units:
            unit = {"path": u["path"], "name": u["name"], "level": u["level"]}
            card = di.unit_card(atoms, unit, instances)
            seen[kind] = seen.get(kind, 0) + (1 if card else 0)
            if not card:
                continue
            for row in card["areas"]:                          # label-bug guard
                assert row.get("name"), f"unit area row missing 'name': {row}"
            f2 = eng.scope(atoms, org_prefix=u["path"])
            f2 = f2[f2["survey_type"] == 2]
            trend = di._trend(di._last_periods(f2, "monthly", 12), "monthly",
                              lambda dd: eng.overall_perception(dd, di.EVENT_DIMS_FORM2))
            di.unit_coach(card, trend, card["areas"])
            parent = u["path"].rsplit("/", 1)[0] if "/" in u["path"] else ""
            di.unit_ta_advice(card, di.unit_event_dims(atoms, parent))
            di.unit_year_over_year(atoms, u["path"])
        # badges + standing within sibling cohorts
        div_cards = [di.unit_card(atoms, {"path": d["path"], "name": d["name"], "level": d["level"]}, instances)
                     for d in org["divisions"]]
        di.assign_unit_badges(div_cards)
        for d in org["divisions"]:
            sec_cards = [di.unit_card(atoms, {"path": s["path"], "name": s["name"], "level": s["level"]}, instances)
                         for s in d["sections"]]
            di.assign_unit_badges(sec_cards)
            live = [c for c in sec_cards if c]
            for sc in live:
                di.unit_standing(sc, live, "sections in " + d["name"])
        # Unit badges must come from the dedicated UNIT set (never the People badges).
        for c in div_cards + [s for d in org["divisions"]
                              for s in [di.unit_card(atoms, {"path": x["path"], "name": x["name"], "level": x["level"]}, instances)
                                        for x in d["sections"]]]:
            if not c:
                continue
            di.assign_unit_badges([c])   # harmless re-assign; just to populate for the assert
            for b in c.get("all_badges", []):
                assert b["key"] in di.UNIT_BADGE_DEFS, f"non-unit badge on a unit: {b['key']}"
    ok("teams unit-coaching layer", teams_layer)
    print("Teams coverage:", seen)
    for kind in ("bureau", "division", "section", "admin_section"):
        if not seen.get(kind):
            warns.append(f"no rated '{kind}' unit in the data — that path untested this run")

    # ---- the office calendar: every layout, scope, filter and search, for every kind of account ----
    def calendar_views():
        import calendar_routes
        import tzutil as tz
        users = st.list_admin_users(conn)
        by_role = {}
        for u in users:
            by_role.setdefault(u["role"], u)                     # one account per role is enough
        today = tz.today_local()
        queries = [{}, {"view": "month"}, {"view": "week"}, {"view": "timeline"},
                   {"scope": "mine"}, {"scope": "bureau"}, {"view": "month", "scope": "bureau", "kind": "meeting"},
                   {"q": "meeting"}, {"q": "zzz-no-such-thing"}, {"view": "week", "q": "a"},
                   {"day": today.isoformat(), "status": "tentative"}]
        env = app.templates.env
        n = 0
        for user in by_role.values():
            u = {"id": user["id"], "username": user["username"], "role": user["role"]}
            for q in queries:
                page = calendar_routes.build_calendar_page(conn, u, today, q)
                assert page is not None, f"{u['role']} {q}: no page"
                assert isinstance(page["range_label"], str) and page["n_items"] >= 0, f"{u['role']} {q}"
                # the template must render too: this is what a missing context key or a bad filter breaks
                html = env.get_template("_calendar_body.html").render(**page)
                assert 'id="cal-f"' in html and 'class="cal-bar"' in html, f"{u['role']} {q}: toolbar missing"
                n += 1
        if not n:
            warns.append("no accounts in the data — the calendar views were not tried this run")
        else:
            print("Calendar views rendered:", n)
    ok("office calendar views", calendar_views)

    conn.close()
    print(f"\nRan {checks} checks.")
    for w in warns:
        print("  WARN:", w)
    if fails:
        print(f"FAILED ({len(fails)}):")
        for f in fails:
            print("  -", f)
        raise SystemExit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()
