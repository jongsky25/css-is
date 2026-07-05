"""
CSS-IS data harmonization engine — entity resolution over respondent-typed
activity titles and speaker names.

The problem (measured on the production db): F2 "event review" titles were
free-typed by each attendee, so one real event appears as dozens of spellings,
abbreviations, and typos; 78% of F2 instances carry <=1 response. The speaker
field likewise holds rosters and case/punctuation variants. This module finds
the duplicate clusters so they can be merged to a canonical record.

Design:
  * BLOCK to keep matching cheap + precise — activities by event_date (+organizer),
    speakers globally by normalized name.
  * MATCH with a blend of token-set Jaccard + difflib sequence ratio.
  * TIER every cluster:
      - AUTO   : pure variants (every member >= AUTO_SIM to the canonical) — safe
                 to merge with little/no review.
      - REVIEW : plausible but looser (the 0.6-0.9 band) — needs human approval.
      - NOISE  : singletons / junk titles ('(untitled activity)', bare positions).
  * SUGGEST a canonical label (cleanest frequent variant, not the longest).

This file is import-safe and side-effect free. `build_activity_plan` /
`build_speaker_plan` are READ-ONLY (SELECT only). Applying a plan (the
destructive re-point + delete, with backup + undo journal) lives in apply_*,
which the report mode never calls.
"""
from __future__ import annotations
import difflib
import re
from collections import Counter, defaultdict

import storage as st

# ---- thresholds (tuned against the 2024-02-23 GIDA block PoC) ----
AUTO_SIM = 0.90        # member-to-canonical similarity for an auto-accept cluster
REVIEW_SIM = 0.62      # loose link to pull a member into a review cluster
REVIEW_JACCARD = 0.50  # ...or this token-set overlap
DATE_BLOCK = True      # block activities by exact event_date (multi-day events handled in review)

_STOP = set("""the of on and in for a an to with at by from no none na nan null tbd
activity activities conduct conducted online orientation re session sessions event
events meeting webinar via ms mr mrs dr engr atty prof hon sir maam""".split())

_JUNK_RE = re.compile(r"^\W*(untitled|n/?a|none|tbd|test|conduct(\s+activity)?|activity|same as above|"
                      r"see above|do$|n\.?a\.?)\W*$", re.I)


def _toks(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    return {t for t in s.split() if t and t not in _STOP and len(t) > 1}


def _norm(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sim(a_raw, b_raw, a_tok, b_tok):
    """Blended similarity in [0,1]: max of normalized sequence ratio and token-set
    Jaccard. Catches both typos (sequence) and word-reordering/abbrev overlap (tokens)."""
    seq = difflib.SequenceMatcher(None, _norm(a_raw), _norm(b_raw)).ratio()
    return max(seq, _jaccard(a_tok, b_tok))


def _is_junk(title):
    if not (title or "").strip():
        return True
    if _JUNK_RE.match(title.strip()):
        return True
    return len(_toks(title)) == 0      # nothing but stopwords/positions/punctuation


# Reference codes (DM/AO/memo numbers) are the strongest event-identity signal in
# the data: 'DM No. 2024-0044', 'AO 2020-0023', '2026-0071'. Same code in the same
# date block ⇒ almost certainly the same event. Requires a year followed by a 3-4
# digit serial so bare years ('2025 BHW') don't false-match.
_CODE_RE = re.compile(r"\b((?:19|20)\d{2})\s*[-–]\s*(\d{3,4})\b")

# Domain keyword anchors observed in the data — used to attach un-coded fragments
# to a coded event only when they clearly share its subject.
_ANCHORS = {"gida", "bhw", "uua", "liph", "purokalusugan", "purok", "kalusugan", "pk",
            "lhb", "lhs", "oplan", "sglg", "sdn", "riac", "barmm", "ip", "ml"}


def _ref_code(title):
    """Return a normalized reference code 'YYYY-NNNN' if the title carries one, else None."""
    m = _CODE_RE.search(title or "")
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):04d}"


def _anchors(title):
    return _toks(title) & _ANCHORS


def _canonical(members):
    """Pick the cleanest frequent variant as the cluster label.
    members = list of raw titles (with repeats reflecting frequency)."""
    freq = Counter(m for m in members if m)
    best, best_score = None, -1e9
    for t, f in freq.items():
        L = len(t)
        score = f * 2.0
        if _is_junk(t):
            score -= 100
        if t.isupper():
            score -= 1.5            # prefer mixed-case over shouting
        if 12 <= L <= 80:
            score += 2
        elif L < 6:
            score -= 2
        elif L > 130:
            score -= 3
        if score > best_score:
            best, best_score = t, score
    return best


# ---------------------------------------------------------------------
# Clustering — two-pass tiered union-find inside a block.
# ---------------------------------------------------------------------

ATTACH_SIM = 0.78        # an un-coded title joins a seed only at this direct similarity
ATTACH_JACCARD = 0.55    # ...or this token overlap WITH a shared anchor keyword


class _Seed:
    __slots__ = ("ids", "titles", "tok", "code")
    def __init__(self, kid, title, code):
        self.ids = [kid]; self.titles = [title]; self.tok = set(_toks(title)); self.code = code
    def add(self, kid, title):
        self.ids.append(kid); self.titles.append(title); self.tok |= _toks(title)
    @property
    def canon(self):
        return _canonical(self.titles)


def _cluster_block(records):
    """records = [(key_id, title)]. Cluster WITHOUT transitive chaining — the failure
    mode that fused 189 unrelated speakers / two distinct events into one blob.

    Strategy, conservative on purpose (un-mergeable fragments are LEFT as NOISE,
    which is the safe default before a destructive merge):
      1. group by reference code (DM/AO number) — strongest same-event signal;
      2. attach each remaining title to the single MOST-similar seed, and only if it
         clears a real bar (direct similarity, no chaining through intermediaries);
         else it seeds its own cluster;
      3. tier by cohesion.
    """
    recs = [(kid, title) for kid, title in records if not _is_junk(title)]
    junk = [(kid, title) for kid, title in records if _is_junk(title)]

    seeds = []
    # --- pass 1: reference-code buckets ---
    by_code = defaultdict(list)
    uncoded = []
    for kid, title in recs:
        code = _ref_code(title)
        (by_code[code] if code else uncoded).append((kid, title))
    for code, members in by_code.items():
        s = _Seed(*members[0], code)
        for kid, title in members[1:]:
            s.add(kid, title)
        seeds.append(s)

    # --- pass 2: centroid attachment for un-coded titles (longest seeds first) ---
    for kid, title in sorted(uncoded, key=lambda r: -len(r[1])):
        tok = _toks(title)
        best, best_score = None, 0.0
        for s in seeds:
            jac = _jaccard(tok, s.tok)
            seq = difflib.SequenceMatcher(None, _norm(title), _norm(s.canon)).ratio()
            shared_anchor = bool(_anchors(title) & (s.tok & _ANCHORS))
            ok = seq >= ATTACH_SIM or (jac >= ATTACH_JACCARD and shared_anchor)
            score = max(seq, jac)
            if ok and score > best_score:
                best, best_score = s, score
        if best is not None:
            best.add(kid, title)
        else:
            seeds.append(_Seed(kid, title, None))

    clusters = []
    for s in seeds:
        canon = s.canon
        ctok = _toks(canon)
        if len(s.ids) == 1:
            tier = "NOISE"
        else:
            # AUTO = pure variants only (every member tight to the canonical): pure
            # typo/case/spacing differences, safe to auto-merge. Everything grouped by
            # reference-code or keyword goes to REVIEW for a human to confirm.
            cohesive = all(_sim(t, canon, _toks(t), ctok) >= AUTO_SIM for t in s.titles)
            tier = "AUTO" if cohesive else "REVIEW"
        clusters.append({"member_ids": list(s.ids), "titles": list(s.titles),
                         "canonical": canon, "tier": tier, "size": len(s.ids)})
    for kid, title in junk:
        clusters.append({"member_ids": [kid], "titles": [title],
                         "canonical": title, "tier": "NOISE", "size": 1})
    return clusters


# ---------------------------------------------------------------------
# Plans (READ-ONLY) — what a harmonization run WOULD do. No writes.
# ---------------------------------------------------------------------

def build_activity_plan(conn, survey_type=2):
    """Cluster F2 (or F3) instances into events, blocked by date (+organizer).
    Returns (clusters, stats). Each cluster also carries response counts and which
    instance would be KEPT (the anchor) vs DELETED under a destructive merge."""
    rows = conn.execute("""
        SELECT fi.id, fi.topic, fi.event_date, fi.lead_org_id, fi.organizer_external_id,
               COALESCE(rc.n, 0)
        FROM form_instance fi
        LEFT JOIN (SELECT form_instance_id, COUNT(*) n FROM response GROUP BY form_instance_id) rc
               ON rc.form_instance_id = fi.id
        WHERE fi.survey_type = ?
    """, (survey_type,)).fetchall()

    resp = {r[0]: r[5] for r in rows}
    blocks = defaultdict(list)
    for fid, topic, date, lo, xo, n in rows:
        block = (date if DATE_BLOCK else "*", xo if xo else ("bur", lo))
        blocks[block].append((fid, topic))

    clusters = []
    for (date, org), recs in blocks.items():
        for cl in _cluster_block(recs):
            # anchor = member with most responses, then the canonical title's instance
            ids = cl["member_ids"]
            anchor = max(ids, key=lambda i: (resp.get(i, 0),
                         1 if _title_of(rows, i) == cl["canonical"] else 0, -i))
            cl.update({"date": date, "organizer": org, "anchor_id": anchor,
                       "delete_ids": [i for i in ids if i != anchor],
                       "resp_total": sum(resp.get(i, 0) for i in ids)})
            clusters.append(cl)

    stats = _summize(clusters, total_instances=len(rows), label=f"type {survey_type}")
    return clusters, stats


def _title_of(rows, fid):
    for r in rows:
        if r[0] == fid:
            return r[1]
    return None


def build_speaker_plan(conn):
    """Cluster resource_person rows (speakers) by normalized name. Flags rosters
    (multiple names in one string) and junk. READ-ONLY."""
    ppl = conn.execute("""
        SELECT rp.id, rp.name, rp.is_internal,
               (SELECT COUNT(*) FROM form_instance fi WHERE fi.rp_id = rp.id) AS used
        FROM resource_person rp
    """).fetchall()
    recs = [(pid, name) for pid, name, _, _ in ppl]
    used = {pid: u for pid, _, _, u in ppl}

    clusters = []
    for cl in _cluster_block(recs):
        ids = cl["member_ids"]
        anchor = max(ids, key=lambda i: (used.get(i, 0), -i))
        rosters = [t for t in cl["titles"] if _looks_like_roster(t)]
        cl.update({"anchor_id": anchor, "delete_ids": [i for i in ids if i != anchor],
                   "used_total": sum(used.get(i, 0) for i in ids),
                   "roster_flag": bool(rosters)})
        clusters.append(cl)
    stats = _summize(clusters, total_instances=len(ppl), label="speakers")
    # extra: count rosters across ALL rows (not just clustered)
    stats["roster_rows"] = sum(1 for _, name, _, _ in ppl if _looks_like_roster(name))
    return clusters, stats


_ROSTER_RE = re.compile(r"\b(and|&|,|others?:|speakers?:|resource)\b", re.I)


def _looks_like_roster(name):
    """Heuristic: a speaker string that names more than one person."""
    if not name:
        return False
    # count honorific markers as a proxy for person-count
    honor = len(re.findall(r"\b(mr|ms|mrs|dr|engr|atty|prof|dir|hon)\b", name, re.I))
    return honor >= 2 or bool(re.search(r",.*,", name)) or bool(re.search(r"\b(and|&)\b", name)) and honor >= 1


def _summize(clusters, total_instances, label):
    merge = [c for c in clusters if c["tier"] in ("AUTO", "REVIEW")]
    auto = [c for c in clusters if c["tier"] == "AUTO"]
    review = [c for c in clusters if c["tier"] == "REVIEW"]
    noise = [c for c in clusters if c["tier"] == "NOISE"]
    to_delete = sum(len(c["delete_ids"]) for c in merge)
    return {
        "label": label,
        "total_instances": total_instances,
        "clusters_total": len(clusters),
        "auto_clusters": len(auto), "review_clusters": len(review), "noise_clusters": len(noise),
        "rows_merged_away": to_delete,
        "rows_after": total_instances - to_delete,
        "auto_rows_deleted": sum(len(c["delete_ids"]) for c in auto),
        "review_rows_deleted": sum(len(c["delete_ids"]) for c in review),
    }


# ---------------------------------------------------------------------
# Report writer (READ-ONLY) — the dry-run deliverable.
# ---------------------------------------------------------------------

def write_report(conn, path="harmonize_report.md", sample=12):
    a_cl, a_st = build_activity_plan(conn, survey_type=2)
    f3_cl, f3_st = build_activity_plan(conn, survey_type=3)
    s_cl, s_st = build_speaker_plan(conn)

    def block(stats):
        return (f"- instances: **{stats['total_instances']}** -> after merge **{stats['rows_after']}** "
                f"(removes {stats['rows_merged_away']})\n"
                f"- clusters: {stats['clusters_total']}  "
                f"(AUTO {stats['auto_clusters']} · REVIEW {stats['review_clusters']} · NOISE {stats['noise_clusters']})\n"
                f"- rows deleted by tier: AUTO {stats['auto_rows_deleted']} · REVIEW {stats['review_rows_deleted']}\n")

    lines = ["# Harmonization dry-run report (NO changes written)\n",
             "Tiers: **AUTO** = pure variants, safe to auto-merge · **REVIEW** = needs approval · **NOISE** = singleton/junk, left alone.\n",
             "\n## Activities — F2 event reviews\n", block(a_st),
             "\n## Activities — F3 speaker topics\n", block(f3_st),
             "\n## Directory — speakers (resource_person)\n", block(s_st),
             f"- rows that look like multi-person rosters: **{s_st.get('roster_rows', 0)}**\n"]

    def dump(title, clusters, key="canonical", showdel=True):
        out = [f"\n## Sample {title} (largest merge clusters)\n"]
        merge = sorted([c for c in clusters if c["tier"] in ("AUTO", "REVIEW")],
                       key=lambda c: -c["size"])[:sample]
        for c in merge:
            out.append(f"\n### [{c['tier']}] “{c[key]}”  (n={c['size']}, "
                       f"keep id {c['anchor_id']}, delete {len(c['delete_ids'])})\n")
            for t in sorted(set(c["titles"]))[:10]:
                out.append(f"  - {t!r}\n")
        return out

    lines += dump("F2 events", a_cl)
    lines += dump("speakers", s_cl)

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return {"activities_f2": a_st, "activities_f3": f3_st, "speakers": s_st, "path": path}


# ---------------------------------------------------------------------
# Apply (DESTRUCTIVE) — re-point responses onto one anchor instance and delete the
# duplicates. Every step is journaled (so a batch is reversible) and audited. A DB
# file backup is taken first by the CLI. Speaker rosters are never auto-split — a
# roster's rating can't be divided across individuals.
# ---------------------------------------------------------------------
import json as _json
import os as _os
import base64 as _b64
import datetime as _dt
import sqlite3 as _sqlite

_UNDO_DDL = """CREATE TABLE IF NOT EXISTS harmonize_undo (
    id INTEGER PRIMARY KEY, batch TEXT NOT NULL, kind TEXT NOT NULL,
    ref_id INTEGER, payload TEXT, ts TEXT NOT NULL);"""


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def backup_db(db_path="css_is.db", tag="preharmonize"):
    """Consistent snapshot via the SQLite backup API (safe with the dev server open)."""
    _os.makedirs("_backups", exist_ok=True)
    dst = _os.path.join("_backups", f"css_is_{_dt.datetime.now():%Y%m%d_%H%M%S}_{tag}.db")
    src = _sqlite.connect(db_path)
    out = _sqlite.connect(dst)
    with out:
        src.backup(out)
    src.close(); out.close()
    return dst


def _journal(conn, batch, kind, ref_id, payload):
    conn.execute("INSERT INTO harmonize_undo(batch, kind, ref_id, payload, ts) VALUES (?,?,?,?,?)",
                 (batch, kind, ref_id, _json.dumps(payload), _now()))


def _row_dict(conn, table, pk):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    row = conn.execute(f"SELECT {','.join(cols)} FROM {table} WHERE id=?", (pk,)).fetchone()
    if not row:
        return None
    d = dict(zip(cols, row))
    if "photo" in d and d["photo"] is not None:           # BLOB -> base64 for JSON
        d["photo"] = _b64.b64encode(d["photo"]).decode("ascii")
    return d


def apply_activity_clusters(conn, clusters, batch, actor="(harmonize:auto)"):
    """Merge each cluster's members into its anchor instance. Returns (clusters, rows)."""
    conn.execute(_UNDO_DDL)
    merged = deleted = 0
    for c in clusters:
        dels = c["delete_ids"]
        if not dels:
            continue
        anchor, canon = c["anchor_id"], c["canonical"]
        old_topic = conn.execute("SELECT topic FROM form_instance WHERE id=?", (anchor,)).fetchone()[0]
        if canon and canon != old_topic:                  # give the survivor the clean title
            _journal(conn, batch, "fi_topic", anchor, {"old": old_topic, "new": canon})
            conn.execute("UPDATE form_instance SET topic=? WHERE id=?", (canon, anchor))
        for d in dels:
            for (rid,) in conn.execute("SELECT id FROM response WHERE form_instance_id=?", (d,)).fetchall():
                _journal(conn, batch, "resp_repoint", rid, {"old_fi": d, "new_fi": anchor})
                conn.execute("UPDATE response SET form_instance_id=? WHERE id=?", (anchor, rid))
            _journal(conn, batch, "fi_delete", d, _row_dict(conn, "form_instance", d))
            conn.execute("DELETE FROM form_instance WHERE id=?", (d,))
            deleted += 1
        st.audit(conn, actor, "harmonize_merge", target_type="form_instance", target_id=anchor,
                 summary=f"Merged {len(dels)} duplicate activity instance(s) into “{canon}” (kept #{anchor})",
                 before=old_topic if old_topic != canon else None, after=canon)
        merged += 1
    return merged, deleted


def apply_speaker_clusters(conn, clusters, batch, actor="(harmonize:auto)"):
    """Merge speaker rows into the anchor, repointing every reference first."""
    conn.execute(_UNDO_DDL)
    merged = deleted = 0
    for c in clusters:
        dels = c["delete_ids"]
        if not dels:
            continue
        anchor, canon = c["anchor_id"], c["canonical"]
        a_row = conn.execute("SELECT name, is_internal FROM resource_person WHERE id=?", (anchor,)).fetchone()
        old_name, anchor_internal = a_row[0], a_row[1]
        # For internal staff the directory (official plantilla) name is authoritative —
        # never overwrite it with a frequency-derived display string. Only external-only
        # clusters get the clean canonical name.
        if canon and canon != old_name and not anchor_internal:
            _journal(conn, batch, "rp_name", anchor, {"old": old_name, "new": canon})
            conn.execute("UPDATE resource_person SET name=? WHERE id=?", (canon, anchor))
        for d in dels:
            for (fid,) in conn.execute("SELECT id FROM form_instance WHERE rp_id=?", (d,)).fetchall():
                _journal(conn, batch, "fi_rp_repoint", fid, {"old_rp": d, "new_rp": anchor})
                conn.execute("UPDATE form_instance SET rp_id=? WHERE id=?", (anchor, fid))
            for (rid,) in conn.execute("SELECT id FROM response WHERE served_by_rp_id=?", (d,)).fetchall():
                _journal(conn, batch, "resp_servedby", rid, {"old_rp": d, "new_rp": anchor})
                conn.execute("UPDATE response SET served_by_rp_id=? WHERE id=?", (anchor, rid))
            _journal(conn, batch, "rp_delete", d, _row_dict(conn, "resource_person", d))
            conn.execute("DELETE FROM resource_person WHERE id=?", (d,))
            deleted += 1
        kept_name = old_name if anchor_internal else (canon or old_name)
        st.audit(conn, actor, "harmonize_merge", target_type="resource_person", target_id=anchor,
                 summary=f"Merged {len(dels)} duplicate speaker record(s) into “{kept_name}” (kept #{anchor})",
                 before=old_name if old_name != kept_name else None, after=kept_name)
        merged += 1
    return merged, deleted


def undo_batch(conn, batch):
    """Reverse a whole apply batch using the journal (newest entries first, so deleted
    rows are re-inserted before anything is repointed back to them)."""
    conn.execute(_UNDO_DDL)
    rows = conn.execute("SELECT id, kind, ref_id, payload FROM harmonize_undo "
                        "WHERE batch=? ORDER BY id DESC", (batch,)).fetchall()
    for _id, kind, ref_id, payload in rows:
        p = _json.loads(payload)
        if kind == "fi_topic":
            conn.execute("UPDATE form_instance SET topic=? WHERE id=?", (p["old"], ref_id))
        elif kind == "fi_archive":
            conn.execute("UPDATE form_instance SET archived=0 WHERE id=?", (ref_id,))
        elif kind == "fi_lead_org":
            conn.execute("UPDATE form_instance SET lead_org_id=? WHERE id=?", (p["old"], ref_id))
        elif kind == "resp_repoint":
            conn.execute("UPDATE response SET form_instance_id=? WHERE id=?", (p["old_fi"], ref_id))
        elif kind == "fi_delete":
            _reinsert(conn, "form_instance", p)
        elif kind == "rp_name":
            conn.execute("UPDATE resource_person SET name=? WHERE id=?", (p["old"], ref_id))
        elif kind == "fi_rp_repoint":
            conn.execute("UPDATE form_instance SET rp_id=? WHERE id=?", (p["old_rp"], ref_id))
        elif kind == "resp_servedby":
            conn.execute("UPDATE response SET served_by_rp_id=? WHERE id=?", (p["old_rp"], ref_id))
        elif kind == "rp_delete":
            _reinsert(conn, "resource_person", p)
    conn.execute("DELETE FROM harmonize_undo WHERE batch=?", (batch,))
    conn.commit()
    return len(rows)


def _reinsert(conn, table, d):
    d = dict(d)
    if table == "resource_person" and d.get("photo") is not None:
        d["photo"] = _b64.b64decode(d["photo"])
    cols = list(d.keys())
    conn.execute(f"INSERT OR REPLACE INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 [d[c] for c in cols])


def archive_junk_activities(conn, batch, actor="(harmonize:archive)"):
    """Set archived=1 on every Type-2 instance whose title is junk/untitled
    ('(untitled activity)', bare 'Orientation'/'Meeting', etc.). Audited; reversible
    via the journal (or by clearing the flag)."""
    conn.execute(_UNDO_DDL)
    rows = conn.execute("SELECT id, topic FROM form_instance WHERE survey_type=2 AND COALESCE(archived,0)=0").fetchall()
    n = 0
    for fid, topic in rows:
        if _is_junk(topic):
            _journal(conn, batch, "fi_archive", fid, {"topic": topic})
            conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (fid,))
            n += 1
    st.audit(conn, actor, "archive_activities", target_type="form_instance",
             summary=f"Archived {n} junk/untitled activity instance(s) — excluded from dashboard + reports, kept in DB.")
    return n


if __name__ == "__main__":
    import sys
    conn = st.connect("css_is.db")
    if len(sys.argv) > 1 and sys.argv[1] == "archive-junk":
        bk = backup_db(); print("backup:", bk)
        batch = f"archive-{_dt.datetime.now():%Y%m%d_%H%M%S}"
        n = archive_junk_activities(conn, batch)
        print(f"batch {batch}: archived {n} junk activities")
    elif len(sys.argv) > 1 and sys.argv[1] in ("apply-auto", "apply-all"):
        tiers = {"AUTO"} if sys.argv[1] == "apply-auto" else {"AUTO", "REVIEW"}
        bk = backup_db()
        print("backup:", bk)
        batch = f"{'auto' if tiers == {'AUTO'} else 'all'}-{_dt.datetime.now():%Y%m%d_%H%M%S}"
        a_cl, _ = build_activity_plan(conn, survey_type=2)
        s_cl, _ = build_speaker_plan(conn)
        am, ad = apply_activity_clusters(conn, [c for c in a_cl if c["tier"] in tiers], batch)
        sm, sd = apply_speaker_clusters(conn, [c for c in s_cl if c["tier"] in tiers], batch)
        print(f"batch {batch} (tiers {sorted(tiers)}): activities {am} clusters / {ad} rows deleted; "
              f"speakers {sm} merged / {sd} rows deleted")
    else:
        print("usage: harmonize.py [archive-junk | apply-auto | apply-all]")
    conn.close()
