"""
consolidate_titles.py — locked-ruleset merge of duplicate Type-2 activities.
See FINAL_CONSOLIDATION_PLAN.md.

Rules (only merge with evidence; never fuse different events):
  * candidates blocked by month, refined to a +-7 day window (or same ref code);
  * a record is folded into a larger anchor only if it has <= FOLD_MAX responses
    AND its title is a close variant (uses harmonize._cluster_block, which does
    no-chaining attachment — safe against mega-blobs);
  * different DM/AO reference codes never merge; explicit Batch/Cohort/Wave kept apart;
  * survivor = most responses, keeps cleanest canonical title; responses repoint,
    empty shells deleted; everything journaled (reversible) — see harmonize.undo_batch.

Usage:
  python consolidate_titles.py plan          # dry run: prints summary, writes review CSV
  python consolidate_titles.py apply         # backup + apply on a temp copy + verify + write back
"""
from __future__ import annotations
import csv, datetime as dt, os, re, shutil, sys
from collections import defaultdict

import storage as st
import harmonize as h

WIN = 7            # +- days
FOLD_MAX = 2       # only fold records with <= this many responses
DB = "css_is.db"
REVIEW_CSV = "title_merge_review.csv"


def _parse(d):
    try:
        return dt.date.fromisoformat((d or "")[:10])
    except Exception:
        return None


def _batch(t):
    m = re.search(r"\b(batch|cohort|wave)\s*[#]?\s*(\d+)\b", (t or "").lower())
    return m.group(0) if m else ""


def load(conn):
    rows = conn.execute("""
        SELECT fi.id, fi.topic, fi.event_date, COALESCE(rc.n,0)
        FROM form_instance fi
        LEFT JOIN (SELECT form_instance_id, COUNT(*) n FROM response GROUP BY form_instance_id) rc
               ON rc.form_instance_id = fi.id
        WHERE fi.survey_type = 2
    """).fetchall()
    return rows


def build_clusters(conn):
    """Return AUTO merge clusters (safe) using the locked ruleset."""
    rows = load(conn)
    T = {r[0]: r[1] for r in rows}; D = {r[0]: r[2] for r in rows}; R = {r[0]: r[3] for r in rows}
    PD = {i: _parse(D[i]) for i in T}; BAT = {i: _batch(T[i]) for i in T}

    # coarse block by month, conservative no-chaining cluster, then refine to +-WIN + fold gate
    blocks = defaultdict(list)
    for i in T:
        d = PD[i]
        blocks[(d.year, d.month) if d else ("x", i)].append((i, T[i]))

    clusters = []
    for _, recs in blocks.items():
        for cl in h._cluster_block(recs):
            if cl["size"] < 2:
                continue
            # split the cluster by batch marker so distinct batches stay separate
            bygrp = defaultdict(list)
            for i in cl["member_ids"]:
                bygrp[BAT[i]].append(i)
            for _, gids in bygrp.items():
                if len(gids) < 2:
                    continue
                anchor = max(gids, key=lambda i: (R[i], -i))
                ad = PD[anchor]
                dels = [i for i in gids if i != anchor and R[i] <= FOLD_MAX
                        and PD[i] and ad and abs((PD[i] - ad).days) <= WIN]
                if not dels:
                    continue
                canon = h._canonical([T[i] for i in [anchor] + dels])
                clusters.append({"anchor_id": anchor, "delete_ids": dels,
                                 "canonical": canon, "titles": [T[i] for i in [anchor] + dels],
                                 "date": str(ad), "resp_total": sum(R[i] for i in [anchor] + dels)})
    return clusters, (T, D, R, PD)


def write_review_csv(conn, ctx, path=REVIEW_CSV):
    """Orphans: sub-10 records whose title is a misused scrap (<=2 keywords) sitting
    within +-7 days of a much larger event. For human placement — NOT auto-merged."""
    T, D, R, PD = ctx
    allids = [i for i in T if not h._is_junk(T[i])]
    big = [i for i in allids if R[i] >= 10]
    rows_out = []
    for i in allids:
        if R[i] >= 3 or len(h._toks(T[i])) > 2:
            continue
        di = PD[i]
        if not di:
            continue
        near = [j for j in big if PD[j] and abs((PD[j] - di).days) <= WIN]
        if not near:
            continue
        host = max(near, key=lambda j: R[j])
        rows_out.append((i, D[i], R[i], T[i], host, D[host], R[host], T[host]))
    rows_out.sort(key=lambda r: (-r[6]))
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["orphan_id", "orphan_date", "orphan_resp", "orphan_title",
                    "nearby_big_id", "big_date", "big_resp", "big_title",
                    "DECISION (merge_into_big_id / keep / blank=keep)"])
        for r in rows_out:
            w.writerow(list(r) + [""])
    return len(rows_out)


def summarize(clusters):
    folded = sum(len(c["delete_ids"]) for c in clusters)
    return len(clusters), folded


def do_plan(conn):
    clusters, ctx = build_clusters(conn)
    nc, folded = summarize(clusters)
    n_review = write_review_csv(conn, ctx)
    print(f"AUTO merge clusters: {nc} | duplicate records folded away: {folded}")
    print(f"review CSV (misused-title orphans near big events): {n_review} rows -> {REVIEW_CSV}")
    print("\nsample merges:")
    for c in sorted(clusters, key=lambda c: -len(c["delete_ids"]))[:8]:
        print(f"  [{c['date']}] keep #{c['anchor_id']} -> {c['canonical']!r}  (+{len(c['delete_ids'])})")
        for t in sorted(set(c["titles"]))[:4]:
            print(f"       - {t!r}")
    return clusters


def do_apply():
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("_backups", exist_ok=True)
    bak = f"_backups/css_is_{stamp}_pretitlemerge.db"
    shutil.copy2(DB, bak)
    print("backup:", bak)

    work = f"/tmp/consolidate_{stamp}.db"
    shutil.copy2(DB, work)
    conn = st.connect(work)

    before = conn.execute("SELECT COUNT(*) FROM form_instance WHERE survey_type=2").fetchone()[0]
    resp_before = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
    clusters, ctx = build_clusters(conn)
    n_review = write_review_csv(conn, ctx)
    batch = f"titlemerge-{stamp}"
    merged, deleted = h.apply_activity_clusters(conn, clusters, batch)
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM form_instance WHERE survey_type=2").fetchone()[0]
    resp_after = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
    integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    orphan_resp = conn.execute("SELECT COUNT(*) FROM response r LEFT JOIN form_instance fi "
                               "ON fi.id=r.form_instance_id WHERE fi.id IS NULL").fetchone()[0]
    conn.close()

    print(f"batch {batch}: merged {merged} clusters, deleted {deleted} duplicate records")
    print(f"type-2 activities: {before} -> {after}")
    print(f"responses: {resp_before} -> {resp_after} (must be equal)  | orphan responses: {orphan_resp}")
    print(f"integrity_check: {integ}")
    print(f"review CSV: {n_review} rows -> {REVIEW_CSV}")

    ok = (resp_before == resp_after and orphan_resp == 0 and integ == "ok")
    if not ok:
        print("VERIFY FAILED — NOT writing back. Working copy left at", work)
        sys.exit(1)
    shutil.copy2(work, DB)
    print("verified ok — wrote cleaned DB back to", DB)
    print(f"undo: python -c \"import storage,harmonize; c=storage.connect('{DB}'); harmonize.undo_batch(c,'{batch}')\"")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "apply":
        do_apply()
    else:
        do_plan(st.connect(DB))
