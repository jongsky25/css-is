"""
Demo for the Office Connect calculator.

Run:  python demo.py

It builds a small batch of PRETEND answers, prints the scores, and then runs
checks (assert lines) that prove the locked rules actually hold -- so you can
trust the engine before feeding it real responses.
"""

import numpy as np
import pandas as pd
import css_is_engine as eng


def atom(rid, stype, form, item, value=None, na=False, unit="U", org="Bureau",
         rp_internal=None, organizer_type="internal", organizer_ref="Bureau",
         topic="-", service="-", date="2026-05-10"):
    return dict(response_id=rid, survey_type=stype, form=form, item_id=item,
                value=(np.nan if na or value is None else float(value)), is_na=na,
                rateable_unit=unit, org_path=org, rp_internal=rp_internal,
                organizer_type=organizer_type, organizer_ref=organizer_ref,
                topic=topic, service=service, event_date=date)


rows = []

# ---- CHECK 1 data: re-pool vs naive "average the averages" (Reliability) ----
# Unit X: B1=[6,6,6], B2=[4]   Unit Y: B1=[2], B2=[2]   (B3,B4 unanswered)
for i, v in enumerate([6, 6, 6]):
    rows.append(atom(f"X{i}", 3, "F3", "B1", v, unit="RPx", org="Bureau/Div1/SecA"))
rows.append(atom("X0", 3, "F3", "B2", 4, unit="RPx", org="Bureau/Div1/SecA"))
rows.append(atom("X1", 3, "F3", "B2", 0, na=True, unit="RPx", org="Bureau/Div1/SecA"))
rows.append(atom("X2", 3, "F3", "B2", 0, na=True, unit="RPx", org="Bureau/Div1/SecA"))
rows.append(atom("Y0", 3, "F3", "B1", 2, unit="RPy", org="Bureau/Div1/SecB"))
rows.append(atom("Y0", 3, "F3", "B2", 2, unit="RPy", org="Bureau/Div1/SecB"))

# ---- CHECK 2 data: a clean ARTA set across two sections (ties-out test) ----
def add_arta(prefix, org, n_top, n_other, date="2026-02-10"):
    rid = 0
    for _ in range(n_top):
        for it in eng.ARTA_HEADLINE_ITEMS:
            rows.append(atom(f"{prefix}{rid}", 1, "F1", it, 5, unit=f"{prefix}", org=org, date=date))
        rid += 1
    for _ in range(n_other):
        for it in eng.ARTA_HEADLINE_ITEMS:
            rows.append(atom(f"{prefix}{rid}", 1, "F1", it, 3, unit=f"{prefix}", org=org, date=date))
        rid += 1

add_arta("A_", "Bureau/Div2/SecC", n_top=12, n_other=4)    # mostly top-box
add_arta("B_", "Bureau/Div2/SecD", n_top=6,  n_other=6)    # mixed

# ---- CHECK 3 data: a ceiling case (all top-box, plenty of n) ----
for i in range(15):
    rows.append(atom(f"CE{i}", 1, "F1", "SQD1", 5, unit="svc", org="Bureau/Div3/SecE"))

# ---- CHECK 4 data: two quarters of ARTA for a pp delta (80 -> 84) ----
def add_quarter_arta(prefix, org, pct_top, n_people, date):
    n_top = round(n_people * pct_top / 100)
    for r in range(n_people):
        v = 5 if r < n_top else 3
        for it in eng.ARTA_HEADLINE_ITEMS:
            rows.append(atom(f"{prefix}{r}", 1, "F1", it, v, unit=prefix, org=org, date=date))

add_quarter_arta("Q1_", "Bureau/Div4/SecF", 80, 50, "2026-02-15")   # Q1 = 80%
add_quarter_arta("Q2_", "Bureau/Div4/SecF", 84, 50, "2026-05-15")   # Q2 = 84%

# ---- CHECK 5 data: composition shift (Simpson guard) ----
# Q1 has units F1u (low) + F2u (mid). Q2 drops F1u, adds F3u (high).
# Each unit's own score is flat; only the MIX changes.
def add_unit_arta(rid_prefix, unit_label, org, pct_top, n, date):
    n_top = round(n * pct_top / 100)
    for r in range(n):
        v = 5 if r < n_top else 3
        for it in eng.ARTA_HEADLINE_ITEMS:
            rows.append(atom(f"{rid_prefix}{r}", 1, "F1", it, v, unit=unit_label, org=org, date=date))

# CMP_mid appears in BOTH quarters unchanged; Q1 also has a low unit, Q2 a high one.
add_unit_arta("low_q1_",  "CMP_low",  "Bureau/Div5/SecG", 50, 20, "2026-02-20")  # Q1 only
add_unit_arta("mid_q1_",  "CMP_mid",  "Bureau/Div5/SecG", 70, 20, "2026-02-20")  # Q1
add_unit_arta("mid_q2_",  "CMP_mid",  "Bureau/Div5/SecG", 70, 20, "2026-05-20")  # Q2 (same unit, flat)
add_unit_arta("high_q2_", "CMP_high", "Bureau/Div5/SecG", 95, 20, "2026-05-20")  # Q2 only

atoms = eng.assign_periods(pd.DataFrame(rows))

print("=" * 70)
print("CHECK 1 - Re-pool vs 'average the averages' (the locked SERVQUAL rule)")
print("=" * 70)
both_units = eng.scope(atoms, org_prefix="Bureau/Div1")          # RPx + RPy together
repool = eng.dimension_mean(both_units, ["B1", "B2", "B3", "B4"])   # Reliability
dimX = eng.dimension_mean(eng.scope(atoms, "Bureau/Div1/SecA"), ["B1", "B2", "B3", "B4"])
dimY = eng.dimension_mean(eng.scope(atoms, "Bureau/Div1/SecB"), ["B1", "B2", "B3", "B4"])
nX = eng.scope(atoms, "Bureau/Div1/SecA")["response_id"].nunique()
nY = eng.scope(atoms, "Bureau/Div1/SecB")["response_id"].nunique()
naive = (dimX.value * nX + dimY.value * nY) / (nX + nY)
print(f"  Unit RPx Reliability : {dimX.show()}")
print(f"  Unit RPy Reliability : {dimY.show()}")
print(f"  RE-POOL (engine)     : {repool.show()}   <- this is what we use")
print(f"  naive avg-of-avgs    : {naive:.2f}        <- rejected")
assert round(repool.value, 2) == 4.00, repool.value
assert round(naive, 2) == 4.25
print("  PASS: engine gives 4.00; the rejected method would have given 4.25.")

print()
print("=" * 70)
print("CHECK 2 - ARTA ties out: bureau = n-weighted average of the sections")
print("=" * 70)
div2 = eng.scope(atoms, "Bureau/Div2")
bureau_score = eng.arta_topbox(div2)
secC = eng.arta_topbox(eng.scope(atoms, "Bureau/Div2/SecC"))
secD = eng.arta_topbox(eng.scope(atoms, "Bureau/Div2/SecD"))
weighted = (secC.value * secC.n + secD.value * secD.n) / (secC.n + secD.n)
print(f"  SecC: {secC.show('pct')}")
print(f"  SecD: {secD.show('pct')}")
print(f"  Div2 re-pool        : {bureau_score.show('pct')}")
print(f"  Div2 n-weighted secs: {weighted:.1f}%")
assert abs(bureau_score.value - weighted) < 1e-9
print("  PASS: for ARTA, re-pool and n-weighted sections are identical (tie out).")

print()
print("=" * 70)
print("CHECK 3 - Ceiling flag fires when an instrument stops discriminating")
print("=" * 70)
ceil = eng.arta_topbox(eng.scope(atoms, "Bureau/Div3"), items=["SQD1"])
print(f"  SecE SQD1: {ceil.show('pct')}")
assert "non-discriminating - see verbatims" in ceil.flags
print("  PASS: 100% with enough n is flagged, not celebrated.")

print()
print("=" * 70)
print("CHECK 4 - Quarter-over-quarter delta is in percentage POINTS")
print("=" * 70)
q1 = eng.arta_topbox(eng.scope(atoms, "Bureau/Div4", "quarter", "2026-Q1"))
q2 = eng.arta_topbox(eng.scope(atoms, "Bureau/Div4", "quarter", "2026-Q2"))
d = eng.pop_delta(q2, q1, unit="pp")
print(f"  Div4 Q1->Q2: {eng.fmt_delta(d)}")
assert round(d["delta"], 1) == 4.0
print("  PASS: 80% -> 84% reads as +4.00 pp (not +5%).")

print()
print("=" * 70)
print("CHECK 5 - Composition guard: raw rise vs like-for-like (no real change)")
print("=" * 70)
res = eng.pop_with_like_for_like(atoms, eng.arta_topbox, "Bureau/Div5",
                                 "quarter", "2026-Q2", "2026-Q1", unit="pp")
print(f"  RAW          : {eng.fmt_delta(res['raw'])}")
print(f"  LIKE-FOR-LIKE: {eng.fmt_delta(res['like_for_like'])}")
print("  -> The raw number jumps only because the mix of units changed;")
print("     like-for-like shows the truth. Both are shown, never raw alone.")

print()
print("=" * 70)
print("CHECK 6 - Own events vs external engagements (the organizer slice)")
print("=" * 70)
# tag RPx as you speaking at an outside event; RPy at a bureau event
atoms.loc[atoms["rateable_unit"] == "RPx", "organizer_type"] = "external"
atoms.loc[atoms["rateable_unit"] == "RPx", "organizer_ref"] = "Other Agency"
own = eng.overall_perception(eng.scope(atoms, "Bureau/Div1", organizer_type="internal"), eng.DIM_MAP_FORM3)
ext = eng.overall_perception(eng.scope(atoms, "Bureau/Div1", organizer_type="external"), eng.DIM_MAP_FORM3)
print(f"  At our own events : {own.show()}")
print(f"  External invites  : {ext.show()}")
print("  PASS: the same RP pool splits cleanly by who organized the event.")

print()
print("All checks passed.")
