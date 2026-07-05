"""
Populate the directory from the official BLHSD plantilla
('List of BLHSD Personnel (1).xlsx'). The official list is authoritative:

  * build the real org tree (2 divisions, 5 sections, Admin, Office of Director);
  * ALIGN existing speaker records to their official entry (canonical name +
    designation/position + employment status + section), keeping their ratings;
  * ADD official staff that have no record yet (no ratings);
  * keep Dr. Apple Charm Agulto as BLHSD (Section 4, Project, Monitoring and
    Capacity Building Specialist) per the user — she is staff though off-plantilla;
  * MERGE 'JD Salonga' (#49) into 'John David Salonga' (#50);
  * DEMOTE everyone still flagged BLHSD but not on the list -> external.

DESTRUCTIVE-ish (renames, reclassifies, one merge). Backs up first.
"""
from __future__ import annotations
import re, sys
import openpyxl
import storage as st
import harmonize as h

XLSX = r"C:\Users\USER\Downloads\List of BLHSD Personnel (1).xlsx"
HON = set("dir dr mr ms mrs engr atty prof hon sir maam miss doc dra".split())

EMP = {"permanent": "plantilla", "job order": "job_order", "detailed": "detailed",
       "co-terminus": "co_terminus", "project": "project"}

# section official name -> (short, parent-division official name)
DIVS = {
    "Health Systems Development Division": "HSDD",
    "Health Systems Monitoring and Evaluation Division": "HSMED",
}
SECTIONS = {
    "Section 1 - Local Health System Integration": ("S1", "Health Systems Development Division"),
    "Section 2 - Local Health Planning & Financing": ("S2", "Health Systems Development Division"),
    "Section 3 - Leadership and Governance for Health": ("S3", "Health Systems Development Division"),
    "Section 4 - Equity in Health and Special Concerns": ("S4", "Health Systems Monitoring and Evaluation Division"),
    "Section 5 - LGU Performance and Monitoring": ("S5", "Health Systems Monitoring and Evaluation Division"),
}

AGULTO_ID = 286
JD_SALONGA_ID, JOHN_DAVID_ID = 49, 50


def norm(n):
    n = re.sub(r"^\s*\d+\.\s*", "", str(n or "")).lower().replace("-", "")
    n = re.sub(r"[^a-z ]", " ", n)
    return [t for t in n.split() if t not in HON and len(t) > 1]


def match(a, b):
    import difflib
    na, nb = norm(a), norm(b)
    sa, sb = set(na), set(nb)
    if not sa or not sb:
        return 0
    if sa == sb:
        return 1.0
    if sa <= sb or sb <= sa:
        return 0.9
    if na[-1] == nb[-1] and difflib.SequenceMatcher(None, na[0], nb[0]).ratio() >= 0.85:
        return 0.88
    return difflib.SequenceMatcher(None, " ".join(sorted(sa)), " ".join(sorted(sb))).ratio()


def parse_official():
    ws = openpyxl.load_workbook(XLSX, data_only=True)["Sheet 1"]
    out = []
    for row in ws.iter_rows(values_only=True):
        if not row[0]:
            continue
        m = re.match(r"^\s*\d+\.\s+(.*)$", str(row[0]))
        if not m:
            continue
        out.append({"name": m.group(1).strip(),
                    "desig": (row[1] or "").strip(),
                    "status": (row[2] or "").strip(),
                    "div": (row[3] or "").strip() if len(row) > 3 else "",
                    "sec": (row[4] or "").strip() if len(row) > 4 else "",
                    "role": (row[5] or "").strip() if len(row) > 5 else ""})
    return out


def ensure_org(conn):
    """Build divisions/sections/admin/OD under the bureau. Idempotent (keyed on path)."""
    bureau = conn.execute("SELECT id, path FROM org_unit WHERE level='bureau' ORDER BY id LIMIT 1").fetchone()
    bid, bpath = bureau
    by_path = {u[0]: u[1] for u in [(r[4], r[0]) for r in conn.execute("SELECT id,name,short_name,level,path FROM org_unit")]}
    ids = {}

    def ensure(name, level, path, short=None):
        row = conn.execute("SELECT id FROM org_unit WHERE path=?", (path,)).fetchone()
        if row:
            return row[0]
        return st.add_org_unit(conn, name, level, path, short_name=short)

    for dname, short in DIVS.items():
        ids[dname] = ensure(dname, "division", f"{bpath}/{short}", short)
    for sname, (short, dname) in SECTIONS.items():
        dshort = DIVS[dname]
        ids[sname] = ensure(sname, "section", f"{bpath}/{dshort}/{short}", short)
    ids["Administrative Section"] = ensure("Administrative Section", "section", f"{bpath}/ADMIN", "ADMIN")
    ids["Office of the Director"] = ensure("Office of the Director", "section", f"{bpath}/OD", "OD")
    ids["__bureau__"] = bid
    return ids


def org_for(staff, ids):
    sec, div = staff["sec"], staff["div"]
    if sec in SECTIONS:
        return ids[sec]
    if div in DIVS:               # division chief, no section
        return ids[div]
    if div == "Administrative Section" or sec == "Administrative Section":
        return ids["Administrative Section"]
    if div == "Director":
        return ids["Office of the Director"]
    return ids["__bureau__"]


def run(db_path):
    bk = h.backup_db(db_path, tag="predirectory")
    conn = st.connect(db_path)
    ids = ensure_org(conn)
    staff = parse_official()
    rps = conn.execute("SELECT id, name, is_internal FROM resource_person").fetchall()

    # match each official -> existing record (greedy, >=0.85)
    align, used = {}, set()
    for s in staff:
        best, bs = None, 0
        for rid, nm, isint in rps:
            if rid in used:
                continue
            sc = match(s["name"], nm)
            if sc > bs:
                bs, best = sc, rid
        if best and bs >= 0.85:
            align[best] = s; used.add(best)

    n = {"align": 0, "add": 0, "demote": 0, "merge": 0}
    blhsd_ids = set()
    # align + add
    aligned_official = set()
    for rid, s in align.items():
        emp = EMP.get(s["status"].lower())
        st.update_rp(conn, rid, name=s["name"], org_unit_id=org_for(s, ids),
                     position=s["desig"] or None, designation=s["role"] or None,
                     employment_type=emp)
        conn.execute("UPDATE resource_person SET is_internal=1 WHERE id=?", (rid,))
        blhsd_ids.add(rid); aligned_official.add(id(s)); n["align"] += 1
    for s in staff:
        if id(s) in aligned_official:
            continue
        emp = EMP.get(s["status"].lower())
        nid = st.add_rp(conn, s["name"], is_internal=True, org_unit_id=org_for(s, ids),
                        position=s["desig"] or None, designation=s["role"] or None,
                        employment_type=emp)
        blhsd_ids.add(nid); n["add"] += 1

    # Agulto: keep BLHSD, Section 4, Project, capacity-building specialist
    if conn.execute("SELECT 1 FROM resource_person WHERE id=?", (AGULTO_ID,)).fetchone():
        st.update_rp(conn, AGULTO_ID, org_unit_id=ids["Section 4 - Equity in Health and Special Concerns"],
                     position="Monitoring and Capacity Building Specialist", employment_type="project")
        conn.execute("UPDATE resource_person SET is_internal=1 WHERE id=?", (AGULTO_ID,))
        blhsd_ids.add(AGULTO_ID)

    # JD Salonga -> John David Salonga
    if conn.execute("SELECT 1 FROM resource_person WHERE id=?", (JD_SALONGA_ID,)).fetchone():
        conn.execute("UPDATE form_instance SET rp_id=? WHERE rp_id=?", (JOHN_DAVID_ID, JD_SALONGA_ID))
        conn.execute("UPDATE response SET served_by_rp_id=? WHERE served_by_rp_id=?", (JOHN_DAVID_ID, JD_SALONGA_ID))
        conn.execute("DELETE FROM resource_person WHERE id=?", (JD_SALONGA_ID,))
        n["merge"] += 1

    # demote every remaining internal that isn't on the authoritative roster
    for (rid,) in conn.execute("SELECT id FROM resource_person WHERE is_internal=1").fetchall():
        if rid not in blhsd_ids:
            conn.execute("UPDATE resource_person SET is_internal=0 WHERE id=?", (rid,))
            n["demote"] += 1
    conn.commit()
    st.audit(conn, "(directory populate)", "directory_populate",
             summary=f"Populated from official plantilla: built org tree; aligned {n['align']}, "
                     f"added {n['add']} staff, merged {n['merge']}, demoted {n['demote']} non-conforming to external. "
                     f"BLHSD roster now {len(blhsd_ids)}.")
    conn.close()
    return bk, n, len(blhsd_ids)


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "css_is.db"
    bk, n, total = run(db)
    print("DB:", db, "| backup:", bk)
    print("result:", n, "| BLHSD roster:", total)
