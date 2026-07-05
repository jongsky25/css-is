"""
One-shot application of the user's hand-curated speaker decisions (from
Book1_columnA.xlsx) + the BLHSD dedup. DESTRUCTIVE — takes a full DB backup
first; revert by restoring that backup.

Actions per speaker record:
  BLHSD     -> is_internal=1
  EXTERNAL  -> is_internal=0
  DELETE    -> remove record + its F3 instances/responses/answers
  MERGE t   -> repoint F3 (rp_id) + served_by to t, delete the source
  DIVIDE    -> split a roster: DUPLICATE each session's ratings to every named
               individual (resolve to an existing person or create a new external
               one), then delete the roster record. (User: "duplicate the entries
               per rows created.")

Order: merges -> canonical renames -> divides -> deletes -> classify survivors.
"""
from __future__ import annotations
import csv, io, re, sys, uuid
import openpyxl
import storage as st
import harmonize as h

XLSX = r"C:\Users\USER\Downloads\Book1_columnA.xlsx"

HON = set("mr ms mrs dr engr atty prof dir hon sir maam ma'am miss doc director dra mons".split())
VSET = {"vlanche", "vlanchie", "april", "dulfo", "dulfu", "adolfo"}

# ---- explicit decisions the user gave by id ----
EXPLICIT = {                      # id -> action tuple
    229: ("EXTERNAL",), 277: ("EXTERNAL",),
    27: ("BLHSD",), 296: ("BLHSD",), 12: ("BLHSD",), 131: ("BLHSD",),
    155: ("MERGE", 17), 310: ("MERGE", 131),
    72: ("MERGE", 74), 258: ("MERGE", 252), 299: ("MERGE", 181), 316: ("MERGE", 314),
    183: ("MERGE", 16), 46: ("MERGE", 37),
    277: ("MERGE", 278), 281: ("MERGE", 278),   # Tamayao variants -> one external record
    60: ("DELETE",),                            # 'JV' — pure junk (user-named)
}
HANDFUL_EXTERNAL = {216, 182, 175, 321, 189, 190, 198, 239, 203, 206, 40}
HCMERGE = {75: 74, 313: 286, 57: 37, 248: 126, 61: 18, 154: 74,
           159: 69, 165: 74, 167: 69, 228: 23, 312: 31}
RENAMES = {17: "Maria Teresa Santiago", 131: "Dr. Mar Wynn Bello"}  # +vlanche anchor, set at runtime


def ctoks(n):
    return [t for t in re.sub(r"[^a-z ]", " ", (n or "").lower()).split()
            if len(t) >= 2 and t not in HON]


def junk(n):
    return bool(re.search(r"\d", n or "")) or len(ctoks(n)) == 0


def is_vlanche(n):
    ts = set(ctoks(n))
    return bool(ts) and ts <= VSET


def is_multi(name):
    """A roster for divide purposes = the name resolves into 2+ individuals.
    More reliable than honorific/comma heuristics for comma-only rosters like
    'Irene Hizon, Modesto Lazo'."""
    return len(split_roster(name)) >= 2


def split_roster(name):
    s = name or ""
    s = re.sub(r'(?i)\b(others?|resource speakers?|speakers?|last speakers?|all speakers?)\b\s*:?', ' ', s)
    s = re.sub(r'(?i)\s+and\s+', ',', s)
    s = s.replace('&', ',').replace('/', ',').replace(';', ',')
    # split space-separated rosters on honorific boundaries:
    # 'Ms. Santiago Mr. Lazo Mr. Ventura' -> commas before each mid-string honorific
    s = re.sub(r'(?i)(?<=\S)\s+(?=(?:mr|ms|mrs|dr|engr|atty|prof|dir|hon|sir|maam|miss|doc)\.?\s+\S)', ', ', s)
    out = []
    for p in s.split(','):
        p = re.sub(r'\s+', ' ', p).strip(' .')
        if [t for t in re.sub(r'[^A-Za-z. ]', ' ', p).split() if len(t) >= 2 and t.lower().strip('.') not in HON]:
            out.append(p)
    return out


def load_remarks():
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    ws = wb.active
    out = {}
    for r in range(2, ws.max_row + 1):
        b = ws.cell(r, 2).value
        a = ws.cell(r, 1).value
        if not b:
            continue
        row = next(csv.reader(io.StringIO(b)))
        out[int(row[0])] = (row[1], (a or "").strip())
    return out


def build_actions(remarks, vanchor):
    act = {}
    for sid, (name, rem) in remarks.items():
        r = rem.lower().strip()
        if sid in HANDFUL_EXTERNAL:
            act[sid] = ("EXTERNAL",); continue
        if sid in EXPLICIT:
            act[sid] = EXPLICIT[sid]; continue
        if is_vlanche(name):
            act[sid] = ("BLHSD",) if sid == vanchor else ("MERGE", vanchor); continue
        if sid in HCMERGE:
            act[sid] = ("MERGE", HCMERGE[sid]); continue
        if r == "delete" or r.startswith("not archive"):
            act[sid] = ("DELETE",); continue
        if "divide" in r or sid == 108:
            act[sid] = ("DIVIDE",); continue
        if r.startswith("same") or "same person" in r or "same with" in r:
            act[sid] = ("MERGE", None); continue           # unresolved -> treat as keep/blhsd fallback
        if "flores and not veridiano" in r:
            act[sid] = ("MERGE", 16); continue
        if "john vincent naranjo" in r:
            act[sid] = ("MERGE", 37); continue
        if r.startswith("not external"):
            if junk(name): act[sid] = ("DELETE",)
            elif is_multi(name): act[sid] = ("DIVIDE",)
            else: act[sid] = ("BLHSD",)
            continue
        if r == "":
            act[sid] = ("EXTERNAL",); continue
        if r == "blhsd":
            act[sid] = ("DIVIDE",) if (is_multi(name) or h._looks_like_roster(name)) else ("BLHSD",); continue
        if r.startswith("not blhsd"):
            act[sid] = ("EXTERNAL",); continue
        act[sid] = ("BLHSD",)        # safe default: keep, user reviews in dashboard
    return act


# ---------- low-level DB ops ----------

def _names(conn):
    return conn.execute("SELECT id, name FROM resource_person").fetchall()


def resolve_or_create(conn, name, fb):
    cands = [(sid, nm) for sid, nm in _names(conn)
             if not h._looks_like_roster(nm) and st.names_match(name, nm)]
    if cands:
        cands.sort(key=lambda x: -fb.get(x[0], 0))
        return cands[0][0], False
    nid = st.add_rp(conn, name.strip(" ."), is_internal=False)
    return nid, True


def delete_instance(conn, fi_id):
    rids = [r[0] for r in conn.execute("SELECT id FROM response WHERE form_instance_id=?", (fi_id,))]
    for rid in rids:
        conn.execute("DELETE FROM answer WHERE response_id=?", (rid,))
        conn.execute("DELETE FROM item_remark WHERE response_id=?", (rid,))
    conn.execute("DELETE FROM response WHERE form_instance_id=?", (fi_id,))
    conn.execute("DELETE FROM form_instance WHERE id=?", (fi_id,))


def copy_instance_to(conn, fi_id, new_rp):
    cols = [c[1] for c in conn.execute("PRAGMA table_info(form_instance)")]
    row = dict(zip(cols, conn.execute(f"SELECT {','.join(cols)} FROM form_instance WHERE id=?", (fi_id,)).fetchone()))
    row.pop("id"); row["rp_id"] = new_rp; row["qr_token"] = uuid.uuid4().hex[:12]
    nc = list(row.keys())
    nfi = conn.execute(f"INSERT INTO form_instance({','.join(nc)}) VALUES ({','.join('?'*len(nc))})",
                       [row[c] for c in nc]).lastrowid
    for rid, sub, rem, sb in conn.execute(
            "SELECT id, submitted_at, remarks, served_by_rp_id FROM response WHERE form_instance_id=?", (fi_id,)).fetchall():
        nrid = conn.execute("INSERT INTO response(form_instance_id, submitted_at, remarks, served_by_rp_id) VALUES (?,?,?,?)",
                            (nfi, sub, rem, sb)).lastrowid
        for it, v, na in conn.execute("SELECT item_id, value, is_na FROM answer WHERE response_id=?", (rid,)).fetchall():
            conn.execute("INSERT INTO answer(response_id, item_id, value, is_na) VALUES (?,?,?,?)", (nrid, it, v, na))
        for it, tx in conn.execute("SELECT item_id, text FROM item_remark WHERE response_id=?", (rid,)).fetchall():
            conn.execute("INSERT INTO item_remark(response_id, item_id, text) VALUES (?,?,?)", (nrid, it, tx))
    return nfi


def merge_speaker(conn, src, dst):
    conn.execute("UPDATE form_instance SET rp_id=? WHERE rp_id=?", (dst, src))
    conn.execute("UPDATE response SET served_by_rp_id=? WHERE served_by_rp_id=?", (dst, src))
    conn.execute("DELETE FROM resource_person WHERE id=?", (src,))


def delete_speaker(conn, sid):
    for (fi,) in conn.execute("SELECT id FROM form_instance WHERE rp_id=?", (sid,)).fetchall():
        delete_instance(conn, fi)
    conn.execute("DELETE FROM resource_person WHERE id=?", (sid,))


def divide_speaker(conn, sid, name, fb):
    inds = split_roster(name)
    if not inds:
        return 0
    created = 0
    for (fi,) in conn.execute("SELECT id FROM form_instance WHERE rp_id=?", (sid,)).fetchall():
        for nm in inds:
            pid, isnew = resolve_or_create(conn, nm, fb)
            copy_instance_to(conn, fi, pid)
            created += 1 if isnew else 0
        delete_instance(conn, fi)
    conn.execute("DELETE FROM resource_person WHERE id=?", (sid,))
    return created


def run(db_path):
    bk = h.backup_db(db_path, tag="prespeakers")
    conn = st.connect(db_path)
    remarks = load_remarks()
    fb = {sid: n for sid, n in conn.execute(
        """SELECT rp.id, COUNT(r.id) FROM resource_person rp
           LEFT JOIN form_instance fi ON fi.rp_id=rp.id AND fi.survey_type=3
           LEFT JOIN response r ON r.form_instance_id=fi.id GROUP BY rp.id""")}
    vmembers = [sid for sid, (nm, _) in remarks.items() if is_vlanche(nm)]
    vanchor = max(vmembers, key=lambda i: fb.get(i, 0)) if vmembers else None
    RENAMES[vanchor] = "Dr. Vlanche April Dulfo"
    act = build_actions(remarks, vanchor)

    n = {"MERGE": 0, "DIVIDE": 0, "DELETE": 0, "BLHSD": 0, "EXTERNAL": 0, "new": 0}
    # 1) merges
    for sid, a in act.items():
        if a[0] == "MERGE" and a[1] and a[1] != sid:
            merge_speaker(conn, sid, a[1]); n["MERGE"] += 1
    # 2) canonical renames (before divides so name-matching resolves)
    for sid, nm in RENAMES.items():
        if sid and conn.execute("SELECT 1 FROM resource_person WHERE id=?", (sid,)).fetchone():
            conn.execute("UPDATE resource_person SET name=? WHERE id=?", (nm, sid))
    # 3) divides
    for sid, a in act.items():
        if a[0] == "DIVIDE" and conn.execute("SELECT 1 FROM resource_person WHERE id=?", (sid,)).fetchone():
            n["new"] += divide_speaker(conn, sid, remarks[sid][0], fb); n["DIVIDE"] += 1
    # 4) deletes
    for sid, a in act.items():
        if a[0] == "DELETE" and conn.execute("SELECT 1 FROM resource_person WHERE id=?", (sid,)).fetchone():
            delete_speaker(conn, sid); n["DELETE"] += 1
    # 5) classify every surviving record
    blhsd_ids = {sid for sid, a in act.items() if a[0] == "BLHSD"}
    for (sid,) in conn.execute("SELECT id FROM resource_person").fetchall():
        internal = 1 if sid in blhsd_ids else 0
        conn.execute("UPDATE resource_person SET is_internal=? WHERE id=?", (internal, sid))
        n["BLHSD" if internal else "EXTERNAL"] += 1
    conn.commit()
    st.audit(conn, "(speaker cleanup)", "speaker_cleanup",
             summary=f"Applied hand-curated speaker decisions: {n['MERGE']} merged, "
                     f"{n['DIVIDE']} rosters split, {n['DELETE']} deleted, "
                     f"{n['new']} new external persons; classified {n['BLHSD']} BLHSD / {n['EXTERNAL']} external.")
    conn.close()
    return bk, n


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "css_is.db"
    bk, n = run(db)
    print("DB:", db, "| backup:", bk)
    print("result:", n)
