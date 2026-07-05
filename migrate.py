"""
migrate.py — Load the old CSS Google-Forms spreadsheets into the new css_is.db.

Design:
  * IDEMPOTENT: every migrated form_instance gets a qr_token prefixed 'MIG-'.
    Re-running first deletes all MIG- tagged data, then reloads — so it can never
    double-insert after an interruption/checkpoint.
  * NON-DESTRUCTIVE to existing (demo/seed) rows: only MIG- data is touched.
  * People are fuzzy-deduped (exact-normalized merge + storage.names_match) and
    reused across runs.
  * Source xlsx is read-only. A fast pickle cache of the sheets is kept in
    /tmp/mig_cache (rebuilt automatically from the xlsx if missing).

Usage:
    python migrate.py            # load (idempotent)
    python migrate.py --verify   # print current MIG- counts
    python migrate.py --purge    # remove all MIG- tagged data and stop
"""
from __future__ import annotations
import sys, os, uuid, math
from collections import defaultdict, Counter
from datetime import datetime
import pandas as pd
import storage as st

DB = "css_is.db"
XLSX = "CSS Spreadsheets.xlsx"
CACHE = "/tmp/mig_cache"
TAG = "MIG-"


# ---------- sheet IO (pickle cache, rebuilt from xlsx if missing) ----------
def _build_cache():
    import openpyxl
    os.makedirs(CACHE, exist_ok=True)
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    for s in wb.sheetnames:
        ws = wb[s]
        data = [r for r in ws.iter_rows(values_only=True)
                if any(c is not None and str(c).strip() != "" for c in r)]
        if not data:
            pd.DataFrame().to_pickle(f"{CACHE}/{s}.pkl"); continue
        w = max(len(r) for r in data)
        data = [list(r) + [None] * (w - len(r)) for r in data]
        if s == "Sheet14":
            df = pd.DataFrame(data)
        else:
            hdr = [str(c) if c is not None else "" for c in data[0]]
            hdr = [h or f"col{i}" for i, h in enumerate(hdr)]
            seen = {}; out = []
            for h in hdr:
                if h in seen: seen[h] += 1; out.append(f"{h}.{seen[h]}")
                else: seen[h] = 0; out.append(h)
            df = pd.DataFrame(data[1:], columns=out)
        df.columns = [str(c) for c in df.columns]
        df.to_pickle(f"{CACHE}/{s}.pkl")


def read_sheet(name):
    p = f"{CACHE}/{name}.pkl"
    if not os.path.exists(p):
        _build_cache()
    df = pd.read_pickle(p)
    return df


# ---------- helpers ----------
def add_dates(df, date_col):
    """Vectorized date parse → adds _sub (iso) and _ev (YYYY-MM-DD) columns."""
    dt = pd.to_datetime(df[date_col], errors="coerce")
    df = df.copy()
    df["_sub"] = dt.dt.strftime("%Y-%m-%dT%H:%M:%S")
    df["_ev"] = dt.dt.strftime("%Y-%m-%d")
    return df


def clean_val(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    if f == 0:
        return (None, 1)           # 0 == N/A on SERVQUAL B-items
    return (float(f), 0)


def clean_text(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip()
    return s or None


def norm_title(s):
    """Normalize a free-text activity title for grouping: lowercase, strip
    punctuation, collapse whitespace. Merges case/spacing/punctuation variants of
    the same activity (e.g. 'Orientation on BHW connect' / 'Orientation  on BHW
    Connect') so they form ONE activity instead of many near-duplicates. High
    precision (no fuzzy guessing) — genuinely different titles stay separate."""
    import re
    s = (s or "").lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def pick(df, prefix):
    for c in df.columns:
        if str(c).strip().startswith(prefix):
            return c
    return None


# ---------- people resolver (fuzzy, idempotent) ----------
class PeopleResolver:
    def __init__(self, conn, bureau_id):
        self.conn = conn
        self.bureau_id = bureau_id
        self.existing = {}
        for rid, name in conn.execute("SELECT id, name FROM resource_person"):
            self.existing.setdefault(st._norm_name(name), rid)

    def cluster(self, names):
        """Deterministic clustering: exact-normalized merge, then fuzzy union."""
        cnt = Counter(n for n in names if n)
        uniq = sorted(cnt)
        by_norm = defaultdict(list)
        for n in uniq:
            by_norm[st._norm_name(n)].append(n)
        norm_keys = sorted(k for k in by_norm if k)
        parent = {k: k for k in norm_keys}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb: parent[max(ra, rb)] = min(ra, rb)
        import difflib
        for i in range(len(norm_keys)):
            a = norm_keys[i]
            for j in range(i + 1, len(norm_keys)):
                b = norm_keys[j]
                if abs(len(a) - len(b)) <= 3 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85:
                    union(a, b)
        members = defaultdict(list)
        for k in norm_keys:
            members[find(k)].extend(by_norm[k])
        canon = {}
        for root, ms in members.items():
            best = max(ms, key=lambda m: (cnt[m], -len(m)))
            for m in ms:
                canon[m] = best
        return canon

    def resolve(self, canonical_name, is_internal=True):
        norm = st._norm_name(canonical_name)
        if norm in self.existing:
            return self.existing[norm]
        rid = st.add_rp(self.conn, canonical_name, is_internal=is_internal,
                        org_unit_id=self.bureau_id if is_internal else None)
        self.existing[norm] = rid
        return rid


# ---------- MIG- data management ----------
def purge_mig(conn):
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM form_instance WHERE qr_token LIKE ?", (TAG + "%",))]
    if not ids:
        return 0
    q = ",".join("?" * len(ids))
    rids = [r[0] for r in conn.execute(
        f"SELECT id FROM response WHERE form_instance_id IN ({q})", ids)]
    if rids:
        rq = ",".join("?" * len(rids))
        conn.execute(f"DELETE FROM answer WHERE response_id IN ({rq})", rids)
        conn.execute(f"DELETE FROM item_remark WHERE response_id IN ({rq})", rids)
        conn.execute(f"DELETE FROM response WHERE id IN ({rq})", rids)
    conn.execute(f"DELETE FROM form_instance WHERE id IN ({q})", ids)
    conn.commit()
    return len(ids)


def mig_token():
    return TAG + uuid.uuid4().hex[:16]


def insert_form_instance(conn, survey_type, form, event_date, **ctx):
    cols = ["survey_type", "form", "qr_token", "event_date", "created_at"]
    vals = [survey_type, form, mig_token(), event_date,
            datetime.now().isoformat(timespec="seconds")]
    for k, v in ctx.items():
        cols.append(k); vals.append(v)
    cur = conn.execute(
        f"INSERT INTO form_instance({','.join(cols)}) VALUES ({','.join('?'*len(vals))})", vals)
    return cur.lastrowid


def insert_response(conn, fi_id, submitted_at, remarks=None, served_by_rp_id=None):
    cur = conn.execute(
        "INSERT INTO response(form_instance_id, submitted_at, remarks, served_by_rp_id) "
        "VALUES (?,?,?,?)", (fi_id, submitted_at, remarks, served_by_rp_id))
    return cur.lastrowid


def flush_atoms(conn, atom_rows):
    if atom_rows:
        conn.executemany(
            "INSERT INTO answer(response_id,item_id,value,is_na) VALUES (?,?,?,?)", atom_rows)


# ---------- per-sheet loaders ----------
def _load_servqual(conn, df, resolver, report, *, survey_type, prefix,
                   nb, title_col=None, rp_col=None, date_col, cmt_col,
                   staff_col=None, purpose_col=None):
    A = pick(df, "A."); C = pick(df, "C.")
    Bs = [pick(df, f"B{i}.") for i in range(1, nb + 1)]
    items = [("A", A)] + [(f"B{i}", Bs[i-1]) for i in range(1, nb + 1)] + [("C", C)]
    rate_cols = [c for _, c in items if c is not None]
    before = len(df)
    df = df[~df[rate_cols].isna().all(axis=1)]
    report[prefix + "_ratingless_dropped"] = before - len(df)
    return items, rate_cols, df


def load_form2(conn, resolver, report):
    df = read_sheet("Form Responses 2")
    n_in = len(df)
    items, rate_cols, df = _load_servqual(conn, df, resolver, report,
        survey_type=2, prefix="F2", nb=9, date_col=None, cmt_col=None)
    title_c = pick(df, "6. Activity Title"); date_c = pick(df, "Date"); cmt_c = pick(df, "D.")
    before = len(df); df = df.drop_duplicates(subset=[date_c, title_c] + rate_cols)
    report["F2_dups"] = before - len(df)
    df = add_dates(df, date_c)
    # Pick a representative (most frequent) original title per normalized key so the
    # displayed activity name keeps natural casing while variants are consolidated.
    rep = {}
    cnt = Counter()
    for row in df.to_dict("records"):
        t = clean_text(row[title_c])
        if t:
            cnt[(norm_title(t), t)] += 1
    rep_best = {}
    for (nt, t), c in cnt.items():
        if nt not in rep_best or c > rep_best[nt][1]:
            rep_best[nt] = (t, c)
    groups = defaultdict(list); nod = 0
    for row in df.to_dict("records"):
        ev = row["_ev"]
        if not ev or ev != ev: nod += 1; continue
        t = clean_text(row[title_c])
        nt = norm_title(t) if t else ""
        groups[(nt, ev)].append(row)
    report["F2_nodate_skipped"] = nod
    report["F2_title_consolidation"] = "%d raw -> %d normalized" % (len(cnt), len(rep_best))
    atoms = []; resp = 0
    for (nt, ev), rows in groups.items():
        title = rep_best.get(nt, ("(untitled activity)", 0))[0] if nt else "(untitled activity)"
        fi = insert_form_instance(conn, 2, "F2", ev, topic=title, lead_org_id=resolver.bureau_id)
        for row in rows:
            rid = insert_response(conn, fi, row["_sub"], remarks=clean_text(row[cmt_c])); resp += 1
            for item_id, col in items:
                cv = clean_val(row[col]) if col is not None else None
                if cv: atoms.append((rid, item_id, cv[0], cv[1]))
    flush_atoms(conn, atoms); conn.commit()
    report.update(F2_in=n_in, F2_instances=len(groups), F2_responses=resp, F2_atoms=len(atoms))


def load_form3(conn, resolver, report):
    df = read_sheet("Form Responses 3")
    n_in = len(df)
    items, rate_cols, df = _load_servqual(conn, df, resolver, report,
        survey_type=3, prefix="F3", nb=9, date_col=None, cmt_col=None)
    rp_c = pick(df, "5. What is the name of the BLHSD Resource")
    date_c = pick(df, "Timestamp"); cmt_c = pick(df, "D.")
    before = len(df); df = df.drop_duplicates(subset=[date_c, rp_c] + rate_cols)
    report["F3_dups"] = before - len(df)
    canon = resolver.cluster([clean_text(v) for v in df[rp_c].tolist() if clean_text(v)])
    df = add_dates(df, date_c)
    groups = defaultdict(list); nod = 0; norp = 0
    for row in df.to_dict("records"):
        ev = row["_ev"]
        if not ev or ev != ev: nod += 1; continue
        nm = clean_text(row[rp_c])
        if not nm: norp += 1; continue
        rp_id = resolver.resolve(canon.get(nm, nm), is_internal=True)
        groups[(rp_id, ev)].append(row)
    report["F3_nodate_skipped"] = nod; report["F3_norp_skipped"] = norp
    atoms = []; resp = 0
    for (rp_id, ev), rows in groups.items():
        fi = insert_form_instance(conn, 3, "F3", ev, rp_id=rp_id)
        for row in rows:
            rid = insert_response(conn, fi, row["_sub"], remarks=clean_text(row[cmt_c])); resp += 1
            for item_id, col in items:
                cv = clean_val(row[col]) if col is not None else None
                if cv: atoms.append((rid, item_id, cv[0], cv[1]))
    flush_atoms(conn, atoms); conn.commit()
    report.update(F3_in=n_in, F3_rp_people=len(set(canon.values())),
                  F3_instances=len(groups), F3_responses=resp, F3_atoms=len(atoms))


def load_form1(conn, resolver, report):
    """Old walk-in form. Per VINCE's decision, remapped to **Type 2 (Activity
    SERVQUAL)** so its A/B1-B6/C ratings score on the SERVQUAL path. The old form
    only had B1-B6, so the Empathy (B7) and Tangible (B8/B9) dimensions simply have
    no data for these rows. Each walk-in becomes a Type-2 'activity' grouped by
    (purpose, date); the serving staff is kept on the instance for reference but is
    not scored (Type 2 does not attribute to a server)."""
    df = read_sheet("Form Responses 1")
    n_in = len(df)
    items, rate_cols, df = _load_servqual(conn, df, resolver, report,
        survey_type=2, prefix="F1", nb=6, date_col=None, cmt_col=None)
    staff_c = pick(df, "5. What is the name of the BLHSD staff")
    purp_c = pick(df, "6. What was the purpose")
    date_c = pick(df, "Timestamp"); cmt_c = pick(df, "D.")
    df = add_dates(df, date_c)
    groups = defaultdict(list); nod = 0
    for row in df.to_dict("records"):
        ev = row["_ev"]
        if not ev or ev != ev: nod += 1; continue
        purpose = clean_text(row[purp_c]) or "service"
        staff = clean_text(row[staff_c])
        groups[(norm_title(purpose), ev)].append((row, purpose, staff))
    report["F1_nodate_skipped"] = nod
    atoms = []; resp = 0
    for (npurp, ev), rows in groups.items():
        purpose = rows[0][1]
        # one representative serving-staff label (informational only)
        staff_label = next((s for _, _, s in rows if s), None)
        topic = "Walk-in: " + purpose
        fi = insert_form_instance(conn, 2, "F2", ev, topic=topic,
                                  serving_staff=staff_label, service=purpose,
                                  lead_org_id=resolver.bureau_id)
        for row, _, _ in rows:
            rid = insert_response(conn, fi, row["_sub"], remarks=clean_text(row[cmt_c])); resp += 1
            for item_id, col in items:
                cv = clean_val(row[col]) if col is not None else None
                if cv: atoms.append((rid, item_id, cv[0], cv[1]))
    flush_atoms(conn, atoms); conn.commit()
    report.update(F1_in=n_in, F1_instances=len(groups), F1_responses=resp,
                  F1_atoms=len(atoms), F1_note="remapped to Type 2 (Activity)")


def load_sheet14(conn, resolver, report):
    df = read_sheet("Sheet14")
    df.columns = list(range(df.shape[1]))            # integer positions
    f2 = read_sheet("Form Responses 2")
    t2 = pick(f2, "6. Activity Title"); d2 = pick(f2, "Date")
    tmp = f2[[t2, d2]].dropna().copy()
    tmp["d"] = pd.to_datetime(tmp[d2], errors="coerce").dt.date.astype(str)
    title_date = tmp.dropna().groupby(t2)["d"].agg(
        lambda s: s.mode().iloc[0] if len(s.mode()) else None).to_dict()
    items = [("A", 4)] + [(f"B{i}", 4 + i) for i in range(1, 10)] + [("C", 14)]
    groups = defaultdict(list); matched = 0; unmatched = 0
    for _, row in df.iterrows():
        title = clean_text(row[3]); ev = title_date.get(title) if title else None
        if not ev: unmatched += 1; continue
        matched += 1; groups[(title, ev)].append(row)
    atoms = []; resp = 0
    for (title, ev), rows in groups.items():
        fi = insert_form_instance(conn, 2, "F2", ev, topic=title, lead_org_id=resolver.bureau_id)
        for row in rows:
            cmt = clean_text(row[17]) if 17 in df.columns else None
            rid = insert_response(conn, fi, ev + "T00:00:00", remarks=cmt); resp += 1
            for item_id, idx in items:
                cv = clean_val(row[idx])
                if cv: atoms.append((rid, item_id, cv[0], cv[1]))
    flush_atoms(conn, atoms); conn.commit()
    report.update(S14_matched=matched, S14_unmatched_parked=unmatched,
                  S14_responses=resp, S14_atoms=len(atoms))


def mig_counts(conn):
    fi = conn.execute("SELECT COUNT(*) FROM form_instance WHERE qr_token LIKE ?", (TAG+"%",)).fetchone()[0]
    rs = conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id IN "
                      "(SELECT id FROM form_instance WHERE qr_token LIKE ?)", (TAG+"%",)).fetchone()[0]
    an = conn.execute("SELECT COUNT(*) FROM answer WHERE response_id IN "
                      "(SELECT id FROM response WHERE form_instance_id IN "
                      "(SELECT id FROM form_instance WHERE qr_token LIKE ?))", (TAG+"%",)).fetchone()[0]
    return fi, rs, an


def main():
    conn = st.connect(DB)
    st.init_db(conn)
    if "--verify" in sys.argv:
        print("MIG counts (form_instance, response, answer):", mig_counts(conn)); return
    if "--purge" in sys.argv:
        print("Purged", purge_mig(conn), "MIG form_instances."); return
    print("Purging any prior MIG- data for idempotent reload...")
    purge_mig(conn)
    bureau_id, bname, bpath = st.get_or_create_blhsd(conn)
    print(f"Bureau root: id={bureau_id} name={bname!r} path={bpath!r}")
    resolver = PeopleResolver(conn, bureau_id)
    report = {}
    print("Loading Form Responses 2 (activity)...");        load_form2(conn, resolver, report)
    print("Loading Form Responses 3 (resource person)..."); load_form3(conn, resolver, report)
    print("Loading Form Responses 1 (walk-in)...");         load_form1(conn, resolver, report)
    print("Loading Sheet14 (fragment)...");                 load_sheet14(conn, resolver, report)
    print("\n=== MIGRATION REPORT (counts) ===")
    for k in sorted(report):
        print(f"  {k:24} {report[k]}")
    print("\nMIG totals (fi, resp, atoms):", mig_counts(conn))
    conn.close()


if __name__ == "__main__":
    main()
