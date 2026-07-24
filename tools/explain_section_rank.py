#!/usr/bin/env python3
"""explain_section_rank.py — show, in full, WHY a section lands where it does on
the Teams standing panel (rating-quality rank vs overall rank).

This is the exact computation the dashboard runs, not a re-derivation: it reuses
`dashboard_insights.unit_card` / `_standing` and `css_is_engine.scope`, wired up
the same way the `/dashboard/teams` route wires them (see app.py `_build_unit_cards`
and `_sibling_cards`). Because sections are ranked BUREAU-WIDE, every section card
is built against one shared bureau prior, then ranked together.

It prints why each section lands where it does: quality ranks on the combined
Quality Index (0-100 over all ten satisfaction questions — nine detailed /7 + the
overall-quality /4, each rescaled to 0-100, equal weight, expectation excluded),
with its /7 and /4 components; engagement is a 50/50 blend of activities run and
respondents reached; and the 45/55 quality/engagement blend produces the overall
rank. Low-sample units (< N_MIN ratings) sort below fully-rated ones.

Run (from the repo root, where css_is.db lives):
    python tools/explain_section_rank.py                    # all-time, every section
    python tools/explain_section_rank.py --period year:2026  # one year
    python tools/explain_section_rank.py --section "Section 4"  # spotlight one unit

Read-only. Never writes to the database.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import storage as st                 # noqa: E402
import css_is_engine as eng          # noqa: E402
import dashboard_insights as di      # noqa: E402


def _parse_period(period_val):
    """'all' / 'year:2026' / 'quarter:2026-Q2' / 'semester:2026-H1' -> (col, value).
    Mirrors app._parse_period so period scoping matches the dashboard exactly."""
    if not period_val or ":" not in period_val:
        return None, None
    col, val = period_val.split(":", 1)
    return (col, val) if col in ("year", "quarter", "semester") else (None, None)


def _all_section_units(org):
    """Every section bureau-wide (division sections + administrative sections),
    as unit dicts — the same cohort app._all_section_paths ranks together."""
    units = [s for d in org["divisions"] for s in d["sections"]]
    units += list(org.get("admin_sections", []))
    return [{"path": u["path"], "name": u["name"], "level": u["level"]} for u in units]


def _pctile(values, v):
    n = len(values)
    return (sum(1 for x in values if x <= v) / n * 100.0) if n else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("CSS_DB", "css_is.db"),
                    help="path to css_is.db (default: css_is.db / $CSS_DB)")
    ap.add_argument("--period", default="all",
                    help="all | year:2026 | quarter:2026-Q2 | semester:2026-H1")
    ap.add_argument("--section", default=None,
                    help="spotlight one section by name/short (substring, case-insensitive)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        sys.exit(f"database not found: {args.db} (run from the repo root, or pass --db)")

    conn = st.connect(args.db)
    try:
        atoms = st.load_atoms(conn)
        org = st.org_structure(conn)
        instances = st.list_activity_instances(conn)
    finally:
        conn.close()

    # --- Period scope: identical to app._scoped(atoms, "", period) ---------------
    col, val = _parse_period(args.period)
    scoped = eng.scope(atoms, org_prefix=None, period_col=col, period=val)

    # One bureau-wide prior, shared by every section card (app._build_unit_cards).
    prior = di._form2_prior(scoped)

    # Build a card per section, drop sections with no rated activity in scope.
    cards = []
    for u in _all_section_units(org):
        c = di.unit_card(scoped, u, instances, prior=prior)
        if c:
            cards.append(c)

    peers = [c for c in cards if c and c.get("rp")]
    if len(peers) < 2:
        sys.exit(f"only {len(peers)} section(s) have rated activity in scope "
                 f"'{args.period}' — need >=2 to rank.")

    # --- Reproduce _standing's three rankings across the whole cohort ------------
    # Quality ranks on the combined Quality Index (di._quality_rank_key), low-n guarded.
    # Engagement is a 50/50 percentile blend of activities and respondents.
    act_vals = [c.get("events", 0) for c in peers]
    resp_vals = [c.get("ratings", 0) for c in peers]

    def qkey(c):
        return di._quality_rank_key(c)          # (enough_sample, quality_index)

    def qpct(c):
        k = qkey(c)
        return sum(1 for x in peers if qkey(x) <= k) / len(peers) * 100.0

    def eng_score(c):
        return (di.ENG_W_ACTIVITIES * _pctile(act_vals, c.get("events", 0))
                + di.ENG_W_RESPONDENTS * _pctile(resp_vals, c.get("ratings", 0)))

    def perf(c):
        return di.PERF_W_QUALITY * qpct(c) + di.PERF_W_ENGAGEMENT * eng_score(c)

    rows = []
    for c in peers:
        q = c.get("quality") or {}
        q_rank = sum(1 for x in peers if qkey(x) > qkey(c)) + 1
        e_rank = sum(1 for x in peers if eng_score(x) > eng_score(c)) + 1
        o_rank = sum(1 for x in peers if perf(x) > perf(c)) + 1
        rows.append({
            "name": c.get("short") or c.get("name"),
            "index": q.get("index") or 0.0, "servqual": q.get("servqual"), "osq": q.get("osq"),
            "n": c["respondents"], "low_n": c.get("ratings", 0) < eng.N_MIN,
            "events": c.get("events", 0), "perf": perf(c), "eng": eng_score(c),
            "q_rank": q_rank, "e_rank": e_rank, "o_rank": o_rank,
            "q_pct": round(qpct(c)), "e_pct": round(eng_score(c)),
            "path": c["path"],
        })

    rows.sort(key=lambda r: r["o_rank"])
    n = len(rows)
    grp_avg = sum(r["index"] for r in rows) / n

    print(f"\nScope: {args.period}   Sections ranked: {n}   "
          f"Low-sample threshold (N_MIN): {eng.N_MIN} ratings")
    print(f"Cohort quality index: {grp_avg:.1f}/100   "
          f"Overall blend: {int(di.PERF_W_QUALITY*100)}% quality / "
          f"{int(di.PERF_W_ENGAGEMENT*100)}% engagement   "
          f"Engagement blend: {int(di.ENG_W_ACTIVITIES*100)}% acts / "
          f"{int(di.ENG_W_RESPONDENTS*100)}% resp\n")

    hdr = (f"{'section':<20}{'index':>7}{'/7':>6}{'/4':>5}{'resp':>6}{'lowN':>6}"
           f"{'Qrank':>7}{'acts':>6}{'Erank':>7}{'perf':>7}{'Orank':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        star = "  <--" if (args.section and args.section.lower() in r["name"].lower()) else ""
        sq = f"{r['servqual']:.2f}" if r["servqual"] is not None else "-"
        osq = f"{r['osq']:.2f}" if r["osq"] is not None else "-"
        print(f"{r['name'][:20]:<20}{r['index']:>7.1f}{sq:>6}{osq:>5}{r['n']:>6}"
              f"{('yes' if r['low_n'] else '-'):>6}{r['q_rank']:>7}{r['events']:>6}"
              f"{r['e_rank']:>7}{r['perf']:>7.1f}{r['o_rank']:>7}{star}")

    print("\nHow to read this:")
    print("  * 'index' is the combined Quality Index (0-100) over all ten satisfaction")
    print("    questions (nine detailed /7 + the overall-quality /4), each rescaled to")
    print("    0-100, equal weight, expectation excluded. It IS the quality-rank basis.")
    print("  * '/7' and '/4' are its components (detailed SERVQUAL mean, overall OSQ mean).")
    print(f"  * Qrank ranks on 'index'; units with fewer than {eng.N_MIN} ratings (lowN=yes)")
    print("    sort below all fully-rated units.")
    print("  * Erank ranks on a 50/50 blend of activities ('acts') and respondents ('resp').")
    print("  * Orank ranks on 'perf' = 45%*(quality pctile) + 55%*(engagement blend).\n")

    if args.section:
        me = next((r for r in rows if args.section.lower() in r["name"].lower()), None)
        if not me:
            print(f"(no section matched '{args.section}')")
            return
        print(f"Spotlight: {me['name']}")
        lown = f"  [LOW SAMPLE: {me['n']} < {eng.N_MIN} — ranked below fully-rated units]" if me["low_n"] else ""
        comp = (f"detailed {me['servqual']:.2f}/7"
                + (f", overall {me['osq']:.2f}/4" if me["osq"] is not None else ""))
        print(f"  Quality  : #{me['q_rank']} of {n}  (index {me['index']:.1f}/100 vs cohort "
              f"{grp_avg:.1f}, {me['q_pct']}th pct; {comp}){lown}")
        print(f"  Engagement: #{me['e_rank']} of {n}  ({me['events']} activities, {me['n']} "
              f"respondents, blend {me['eng']:.0f}/100)")
        print(f"  Overall  : #{me['o_rank']} of {n}  (perf {me['perf']:.1f} = "
              f"0.45*{me['q_pct']} + 0.55*{me['e_pct']})")
        ahead_q = [f"{r['name']} ({r['index']:.1f})" for r in rows if r['q_rank'] < me['q_rank']]
        if ahead_q:
            print(f"  Ahead of it on quality: {', '.join(ahead_q)}")
        print()


if __name__ == "__main__":
    main()
