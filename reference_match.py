"""
reference_match.py — clean Type-2 activity naming/grouping using the authoritative
CSS Reports_reference write-ups (96 docs, 2024 Q2-2026 Q1). See REFERENCE_MATCHING_PLAN.md.

Ground truth per reference doc: canonical title + date(s) (filename), official response
count + SERVQUAL means (score table). We match DB records to each reference activity by
date window + title similarity, and GATE every merge on COUNT RECONCILIATION (merged DB
responses must be near the official count). Reversible: backup + harmonize_undo journal.

  python reference_match.py plan    # Phase 1+2, read-only: writes activity_registry.csv + reference_match_review.csv
  python reference_match.py apply   # Phase 3: apply reconciling matches on a copy, verify, write back
"""
from __future__ import annotations
import csv, datetime as dt, glob, os, re, shutil, sys
from collections import defaultdict

import storage as st
import harmonize as h

REF_DIR = "CSS Reports_reference"
REG_CSV = "activity_registry.csv"
MATCH_CSV = "reference_match_review.csv"
DB = "css_is.db"
WIN_BEFORE, WIN_AFTER = 5, 9     # date window around the reference span (late submissions)
SIM_MIN = 0.45                   # min title similarity for a candidate
RECONCILE = 0.12                 # merged count must be within +-12% of official count

MONTHS = {m.lower(): i for i, m in enumerate(
    ["", "January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"])}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items()) if m})

_DATE_RE = re.compile(
    r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*(?:[-–]\s*(\d{1,2}))?\s*,?\s*(\d{4})")


def parse_dates(stem):
    """Return (date_start, date_end) ISO strings parsed from a filename, or (None,None)."""
    m = None
    for m in _DATE_RE.finditer(stem):
        pass  # take the LAST date expression in the name
    if not m:
        return None, None
    mon = MONTHS.get(m.group(1).lower())
    if not mon:
        return None, None
    d1 = int(m.group(2)); d2 = int(m.group(3)) if m.group(3) else d1; yr = int(m.group(4))
    try:
        s = dt.date(yr, mon, d1).isoformat()
        e = dt.date(yr, mon, d2).isoformat()
        return s, e
    except ValueError:
        return None, None


def parse_batch(stem):
    m = re.search(r"\b(batch|cohort|wave)\s*[#]?\s*(\d+)\b", stem, re.I)
    return f"{m.group(1).title()} {m.group(2)}" if m else ""


def clean_title(stem):
    """Canonical title = filename stem minus the trailing date expression and tidy."""
    t = _DATE_RE.sub("", stem)
    t = re.sub(r"\(\s*\)", "", t)                 # empty parens left by date removal
    t = re.sub(r"[\(\-–\s]+$", "", t).strip()     # trailing separators
    t = re.sub(r"\s{2,}", " ", t)
    return t.strip(" -–()")


def parse_doc_scores(path):
    """Return (official_count, {item:mean}) from the doc's score table, or (None,{})."""
    try:
        import docx
    except ImportError:
        os.system("pip install python-docx --break-system-packages -q")
        import docx
    items = ["A"] + [f"B{i}" for i in range(1, 10)] + ["C"]
    try:
        d = docx.Document(path)
    except Exception:
        return None, {}
    for t in d.tables:
        rows = [[c.text.strip() for c in r.cells] for r in t.rows]
        for i, row in enumerate(rows):
            low = [c.lower() for c in row]
            if "a" in low and "b1" in low and "c" in low and "count" in low:
                # header found; the next row with a numeric first cell is the means row
                for j in range(i + 1, len(rows)):
                    cells = rows[j]
                    if cells and re.fullmatch(r"\d+", cells[0]):
                        cnt = int(cells[0])
                        vals = {}
                        for k, it in enumerate(items, start=1):
                            if k < len(cells):
                                try:
                                    vals[it] = float(cells[k])
                                except ValueError:
                                    pass
                        # skip the SUMS row (values >> 7); means row has values <= ~7.5
                        if vals.get("A", 0) <= 7.5:
                            return cnt, vals
    return None, {}


def build_registry():
    rows = []
    seen = {}
    for path in sorted(glob.glob(os.path.join(REF_DIR, "*", "*.docx"))):
        stem = os.path.splitext(os.path.basename(path))[0]
        quarter = os.path.basename(os.path.dirname(path))
        ds, de = parse_dates(stem)
        batch = parse_batch(stem)
        title = clean_title(stem)
        cnt, vals = parse_doc_scores(path)
        # de-dup preliminary vs final for the same (title,date): keep the one with a count
        key = (re.sub(r"[^a-z0-9]", "", title.lower())[:40], ds, batch)
        rec = {"canonical_title": title, "date_start": ds or "", "date_end": de or "",
               "batch": batch, "quarter": quarter, "official_count": cnt if cnt else "",
               **{it: vals.get(it, "") for it in ["A"] + [f"B{i}" for i in range(1, 10)] + ["C"]},
               "source_file": os.path.basename(path)}
        if key in seen:
            # keep the richer record (one with a count)
            if cnt and not seen[key]["official_count"]:
                rows[seen[key]["_idx"]] = rec
                rec["_idx"] = seen[key]["_idx"]; seen[key] = rec
            continue
        rec["_idx"] = len(rows); rows.append(rec); seen[key] = rec
    for r in rows:
        r.pop("_idx", None)
    cols = ["canonical_title", "date_start", "date_end", "batch", "quarter", "official_count",
            "A"] + [f"B{i}" for i in range(1, 10)] + ["C", "source_file"]
    with open(REG_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows:
            w.writerow(r)
    return rows


def _instances(conn):
    rows = conn.execute("""
        SELECT fi.id, fi.topic, fi.event_date, COALESCE(rc.n,0), COALESCE(fi.pooled,0)
        FROM form_instance fi
        LEFT JOIN (SELECT form_instance_id,COUNT(*) n FROM response GROUP BY form_instance_id) rc
               ON rc.form_instance_id=fi.id
        WHERE fi.survey_type=2 AND COALESCE(fi.archived,0)=0
    """).fetchall()
    return rows


def _d(s):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except Exception:
        return None


def match_registry(conn, registry):
    inst = _instances(conn)
    T = {r[0]: r[1] for r in inst}; D = {r[0]: r[2] for r in inst}
    R = {r[0]: r[3] for r in inst}; P = {r[0]: r[4] for r in inst}
    PD = {i: _d(D[i]) for i in T}
    TOK = {i: h._toks(T[i]) for i in T}
    CODE = {i: h._ref_code(T[i]) for i in T}
    out = []
    for reg in registry:
        ds, de = _d(reg["date_start"]), _d(reg["date_end"])
        if not ds:
            out.append({**_match_row(reg, [], R, T, None, "NONE-nodate")}); continue
        de = de or ds
        lo, hi = ds - dt.timedelta(days=WIN_BEFORE), de + dt.timedelta(days=WIN_AFTER)
        ctok = h._toks(reg["canonical_title"]); ccode = h._ref_code(reg["canonical_title"])
        cands = []
        for i in T:
            di = PD[i]
            if not di or not (lo <= di <= hi):
                continue
            sim = h._sim(reg["canonical_title"], T[i], ctok, TOK[i])
            code_hit = bool(ccode and ccode == CODE[i])
            if sim >= SIM_MIN or code_hit:
                cands.append((i, sim, code_hit))
        # respect batches: if registry entry is a specific batch, require the candidate to
        # share that batch token (or be unspecified); never pull a different explicit batch
        if reg["batch"]:
            bn = reg["batch"].split()[-1]
            cands = [c for c in cands if (bn in (T[c[0]].lower())) or
                     not re.search(r"\b(batch|cohort|wave)\s*\d+", T[c[0]].lower())]
        ids = [c[0] for c in cands]
        summ = sum(R[i] for i in ids)
        official = reg["official_count"] or 0
        tier = "NONE"
        if ids:
            if official and abs(summ - official) <= max(2, RECONCILE * official):
                tier = "MATCH"
            elif official:
                tier = "WEAK"
            else:
                tier = "WEAK-nocount"
        out.append(_match_row(reg, ids, R, T, max(ids, key=lambda i: (R[i], -i)) if ids else None,
                              tier, summ, official, P))
    with open(MATCH_CSV, "w", newline="", encoding="utf-8") as f:
        cols = ["canonical_title", "date_start", "date_end", "batch", "official_count",
                "db_summed_count", "tier", "n_matched", "matched_ids", "pooled_in_match",
                "anchor_id", "anchor_title"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in out:
            w.writerow({k: r.get(k, "") for k in cols})
    return out


def _match_row(reg, ids, R, T, anchor, tier, summ=0, official=0, P=None):
    return {"canonical_title": reg["canonical_title"], "date_start": reg["date_start"],
            "date_end": reg["date_end"], "batch": reg["batch"],
            "official_count": reg["official_count"], "db_summed_count": summ, "tier": tier,
            "n_matched": len(ids), "matched_ids": " ".join(map(str, ids)),
            "pooled_in_match": sum(P.get(i, 0) for i in ids) if P else 0,
            "anchor_id": anchor or "", "anchor_title": (T[anchor] if anchor else ""),
            "date_start_iso": reg["date_start"], "ids": ids}


def do_plan(conn):
    reg = build_registry()
    print(f"Phase 1: registry rows = {len(reg)} -> {REG_CSV}")
    matches = match_registry(conn, reg)
    from collections import Counter
    tc = Counter(m["tier"] for m in matches)
    print(f"Phase 2: {dict(tc)} -> {MATCH_CSV}")
    print("  MATCH (count-reconciled, will auto-apply):", tc.get("MATCH", 0))
    return matches


def do_apply():
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs("_backups", exist_ok=True)
    bak = f"_backups/css_is_{stamp}_prereference.db"; shutil.copy2(DB, bak); print("backup:", bak)
    work = f"/tmp/reference_{stamp}.db"; shutil.copy2(DB, work)
    conn = st.connect(work)
    reg = build_registry()
    matches = match_registry(conn, reg)
    R0 = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
    import css_is_engine as eng, storage as _st
    df0 = _st.load_atoms(conn); ov0 = float(eng.overall_perception(df0[df0["survey_type"] == 2], eng.DIM_MAP_FORM2).value)
    clusters = []; rename_date = {}; unpool = []
    applied = 0
    for m in matches:
        if m["tier"] != "MATCH" or not m["ids"]:
            continue
        ids = m["ids"]; anchor = m["anchor_id"]
        dels = [i for i in ids if i != anchor]
        clusters.append({"anchor_id": anchor, "delete_ids": dels, "canonical": m["canonical_title"]})
        rename_date[anchor] = m["date_start_iso"]
        unpool += ids
        applied += 1
    batch = f"reference-{stamp}"
    merged, deleted = h.apply_activity_clusters(conn, clusters, batch)
    for aid, d in rename_date.items():
        if d:
            conn.execute("UPDATE form_instance SET event_date=? WHERE id=?", (d, aid))
    conn.executemany("UPDATE form_instance SET pooled=0 WHERE id=?", [(i,) for i in set(unpool)])
    conn.commit()
    R1 = conn.execute("SELECT COUNT(*) FROM response").fetchone()[0]
    df1 = _st.load_atoms(conn); ov1 = float(eng.overall_perception(df1[df1["survey_type"] == 2], eng.DIM_MAP_FORM2).value)
    integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
    orph = conn.execute("SELECT COUNT(*) FROM response r LEFT JOIN form_instance fi ON fi.id=r.form_instance_id WHERE fi.id IS NULL").fetchone()[0]
    conn.close()
    print(f"batch {batch}: {applied} reference activities applied, {merged} clusters, {deleted} records merged")
    print(f"responses {R0} -> {R1} (equal) | orphan responses {orph} | integrity {integ}")
    print(f"Type-2 overall {ov0:.4f} -> {ov1:.4f} (<=0.02 drift)")
    ok = (R0 == R1 and orph == 0 and integ == "ok" and abs(ov0 - ov1) <= 0.02)
    if not ok:
        print("VERIFY FAILED — not writing back. Copy left at", work); sys.exit(1)
    shutil.copy2(work, DB)
    with open("REFERENCE_APPLY_DONE.txt", "w", encoding="utf-8") as f:
        f.write(f"batch {batch}\napplied {applied} reference activities; {deleted} records merged; "
                f"responses {R1} (unchanged)\nundo: harmonize.undo_batch(storage.connect('css_is.db'),'{batch}')\n")
    print("VERIFIED — wrote cleaned DB back to", DB)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if cmd == "apply":
        do_apply()
    else:
        do_plan(st.connect(DB))
