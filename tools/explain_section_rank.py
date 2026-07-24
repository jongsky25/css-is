#!/usr/bin/env python3
"""explain_section_rank.py — show, in full, WHY a section lands where it does on
the Teams standing panel (rating-quality rank vs overall rank).

This is the exact computation the dashboard runs, not a re-derivation: it reuses
`dashboard_insights.unit_card` / `_standing` and `css_is_engine.scope`, wired up
the same way the `/dashboard/teams` route wires them (see app.py `_build_unit_cards`
and `_sibling_cards`). Because sections are ranked BUREAU-WIDE, every section card
is built against one shared bureau prior, then ranked together.

It exists to answer the recurring question "our section shows 6.4 like everyone
else, so why did it rank 4th on quality (yet 2nd overall)?" — by printing the
hidden numbers the cards round away: the fair-adjusted quality score (`adj`), the
respondent count behind each 6.4, the engagement (activities run), and how the
45/55 quality/engagement blend produces the overall rank.

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
    adj_vals = [c.get("adj", 0) for c in peers]
    ev_vals = [c.get("events", 0) for c in peers]

    def perf(c):  # the overall composite: engagement-heavy blend of percentiles
        return (di.PERF_W_QUALITY * _pctile(adj_vals, c.get("adj", 0))
                + di.PERF_W_ENGAGEMENT * _pctile(ev_vals, c.get("events", 0)))

    rows = []
    for c in peers:
        q_rank = sum(1 for x in peers if x.get("adj", 0) > c.get("adj", 0)) + 1
        e_rank = sum(1 for x in peers if x.get("events", 0) > c.get("events", 0)) + 1
        o_rank = sum(1 for x in peers if perf(x) > perf(c)) + 1
        rows.append({
            "name": c.get("short") or c.get("name"),
            "raw": c["rp"]["value"], "n": c["respondents"], "adj": c.get("adj", 0),
            "events": c.get("events", 0), "perf": perf(c),
            "q_rank": q_rank, "e_rank": e_rank, "o_rank": o_rank,
            "path": c["path"],
        })

    rows.sort(key=lambda r: r["o_rank"])
    n = len(rows)
    grp_avg = sum(r["raw"] for r in rows) / n

    print(f"\nScope: {args.period}   Sections ranked: {n}   "
          f"Bureau prior (shrinkage target, /7): {prior:.3f}   C (N_MIN): {eng.N_MIN}")
    print(f"Cohort raw-average shown on cards: {grp_avg:.2f} of 7   "
          f"Overall blend: {int(di.PERF_W_QUALITY*100)}% quality / "
          f"{int(di.PERF_W_ENGAGEMENT*100)}% engagement\n")

    hdr = (f"{'section':<22}{'raw/7':>7}{'shown':>7}{'resp':>6}{'adj':>8}"
           f"{'Qrank':>7}{'acts':>6}{'Erank':>7}{'perf':>8}{'Orank':>7}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        star = "  <--" if (args.section and args.section.lower() in r["name"].lower()) else ""
        print(f"{r['name'][:22]:<22}{r['raw']:>7.3f}{r['raw']:>7.1f}{r['n']:>6}"
              f"{r['adj']:>8.2f}{r['q_rank']:>7}{r['events']:>6}{r['e_rank']:>7}"
              f"{r['perf']:>8.1f}{r['o_rank']:>7}{star}")

    print("\nHow to read this:")
    print("  * 'shown' is what the card displays (raw rounded to 1 dp) — that's why")
    print("    several sections all read 6.4. 'raw/7' is the true unrounded mean.")
    print("  * Qrank ranks on 'adj' (fair-adjusted / shrinkage score), NOT the shown 6.4:")
    print("      adj = (resp*raw + C*prior)/(resp+C) / 7 * 100")
    print("    so a 6.4 backed by more respondents beats a 6.4 backed by few.")
    print("  * Orank ranks on 'perf' = 45%*(quality percentile) + 55%*(engagement")
    print("    percentile). Engagement = activities run ('acts'). A section can be 4th")
    print("    on quality yet 2nd overall by running enough activities to win on the")
    print("    heavier-weighted engagement axis.\n")

    if args.section:
        me = next((r for r in rows if args.section.lower() in r["name"].lower()), None)
        if not me:
            print(f"(no section matched '{args.section}')")
            return
        q_pct = round(_pctile(adj_vals, me["adj"]))
        e_pct = round(_pctile(ev_vals, me["events"]))
        print(f"Spotlight: {me['name']}")
        print(f"  Quality  : #{me['q_rank']} of {n}  (adj {me['adj']:.2f}, "
              f"{q_pct}th pct)  raw {me['raw']:.3f} vs cohort avg {grp_avg:.2f}")
        print(f"  Engagement: #{me['e_rank']} of {n}  ({me['events']} activities, "
              f"{e_pct}th pct)")
        print(f"  Overall  : #{me['o_rank']} of {n}  (perf {me['perf']:.1f} = "
              f"0.45*{q_pct} + 0.55*{e_pct})")
        ahead_q = [r['name'] for r in rows if r['q_rank'] < me['q_rank']]
        if ahead_q:
            print(f"  Ahead of it on quality: {', '.join(ahead_q)}")
        print()


if __name__ == "__main__":
    main()
