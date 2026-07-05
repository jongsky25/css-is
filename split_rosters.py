"""
split_rosters.py — finish the roster cleanup the speaker pass missed.

15 resource_person records still hold MULTIPLE people in one speaker field
(comma- or 'and'-separated). Reuses the proven apply_speakers machinery:
  DIVIDE  -> duplicate each form's ratings to every named individual, resolving
             each to an existing person or creating a new external one, then
             delete the roster record.
  RENAME  -> a false positive that is actually one person (a credential after a
             comma) — keep as a single person, just normalise the name.
  ARCHIVE -> a 'speaker' that is actually offices/orgs, not a person — archive
             its form(s) and hide the record so it leaves every view (kept in DB).

DESTRUCTIVE — takes a full backup first; revert by restoring it.
Usage: python split_rosters.py [db_path] [--apply]
"""
from __future__ import annotations
import re, sys
import storage as st
import harmonize as h
import apply_speakers as aps

# Explicit identity decisions for cases pure fuzzy-matching gets wrong (bare
# surnames / honorific-only fragments that are clearly an existing canonical
# person). Keyed by the split fragment normalised to lowercase letters+spaces.
# RULE: only map confident same-person variants. When a surname differs or the
# identity is a coin-flip (e.g. 'Gonzales' vs 'Rosales', 'Jed Salonga'), do NOT
# alias it — let it create a safe new record (under-merge), never risk a wrong
# merge onto someone else.
ALIAS = {
    "dr heidi buenavintura": 287,   # Heidi == Haidee Buenaventura (#287)
    "buenaventura":          287,
    "dr medina":             288,   # Dr. Maria Ellen Medina (#288)
    "rosales":               109,   # Dr. Ross Jacob Rosales (#109)
    "loyola":                111,   # Dr. Grethel Loyola (#111)
    "gawilan":               116,   # Ms. Adelita Gawilan (#116)
    "garcia":                118,   # Mr. Vincent Garcia (#118)
    "baldonado":             120,   # Ms. Diana Baldonado (#120)
    "dr dulfo":              127,   # Dr. Vlanche April Dulfo (#127, internal)
    "april dulfo":           127,
    "dr vlanche":            127,
    "mr ventura":             69,   # Mr. Ray Justin C. Ventura (#69, internal)
    "justin ventura":         69,
    "ray justin":             69,
    "dr bello":              131,   # Dir. Mar Wynn D. Bello (#131, internal)
}


def _alias_key(name):
    return " ".join(re.sub(r"[^a-z ]", " ", (name or "").lower()).split())


_orig_resolve = aps.resolve_or_create


def _resolve_with_alias(conn, name, fb):
    cid = ALIAS.get(_alias_key(name))
    if cid and conn.execute("SELECT 1 FROM resource_person WHERE id=?", (cid,)).fetchone():
        return cid, False
    return _orig_resolve(conn, name, fb)


aps.resolve_or_create = _resolve_with_alias   # divide_speaker calls this

# genuine rosters -> split + duplicate ratings per person
DIVIDE_IDS = [93, 289, 128, 139, 110, 107, 298, 172, 51, 162, 166, 101, 138]
# false positive: one person, comma is before a credential -> keep, clean name
RENAME = {240: "Atty. Aragon, MD"}
# not people (government offices) -> archive forms + hide the record
ARCHIVE_NONPERSON = [279]


def _fb_map(conn):
    return {sid: n for sid, n in conn.execute(
        """SELECT rp.id, COUNT(r.id) FROM resource_person rp
           LEFT JOIN form_instance fi ON fi.rp_id=rp.id AND fi.survey_type=3
           LEFT JOIN response r ON r.form_instance_id=fi.id GROUP BY rp.id""")}


def run(db_path, apply=False):
    if apply:
        bk = h.backup_db(db_path, tag="prerosters")
    else:
        bk = None
    conn = st.connect(db_path)
    fb = _fb_map(conn)

    # process rosters with the most feedback first, so the higher-confidence
    # spelling of a shared individual becomes the canonical record others match.
    order = sorted(DIVIDE_IDS, key=lambda i: -fb.get(i, 0))

    n_new = 0
    log = []
    for sid in order:
        row = conn.execute("SELECT name FROM resource_person WHERE id=?", (sid,)).fetchone()
        if not row:
            continue
        name = row[0]
        inds = aps.split_roster(name)
        # record resolution decisions BEFORE the divide mutates state
        decisions = []
        for nm in inds:
            ali = ALIAS.get(_alias_key(nm))
            if ali:
                rn = conn.execute("SELECT name FROM resource_person WHERE id=?", (ali,)).fetchone()
                decisions.append(f"{nm!r} -> ALIAS #{ali} {rn[0]!r}")
                continue
            cands = [(rid, rn) for rid, rn in conn.execute("SELECT id, name FROM resource_person")
                     if not h._looks_like_roster(rn) and st.names_match(nm, rn) and rid != sid]
            if cands:
                cands.sort(key=lambda x: -fb.get(x[0], 0))
                decisions.append(f"{nm!r} -> match #{cands[0][0]} {cands[0][1]!r}")
            else:
                decisions.append(f"{nm!r} -> NEW external")
        created = aps.divide_speaker(conn, sid, name, fb)
        n_new += created
        log.append((sid, name, decisions, created))

    # rename the single-person false positive
    for sid, nm in RENAME.items():
        if conn.execute("SELECT 1 FROM resource_person WHERE id=?", (sid,)).fetchone():
            conn.execute("UPDATE resource_person SET name=? WHERE id=?", (nm, sid))

    # archive + hide the non-person office records
    n_arch = 0
    for sid in ARCHIVE_NONPERSON:
        if conn.execute("SELECT 1 FROM resource_person WHERE id=?", (sid,)).fetchone():
            cur = conn.execute("UPDATE form_instance SET archived=1 WHERE rp_id=?", (sid,))
            n_arch += cur.rowcount
            conn.execute("UPDATE resource_person SET hidden_public=1 WHERE id=?", (sid,))

    if apply:
        conn.commit()
        st.audit(conn, "(roster split)", "roster_split",
                 summary=(f"Split {len(log)} multi-person speaker records "
                          f"({n_new} new external persons, ratings duplicated per person); "
                          f"renamed {len(RENAME)} single-person false positive; "
                          f"archived {len(ARCHIVE_NONPERSON)} non-person office record(s)."))

    # report
    print(f"DB: {db_path}  apply={apply}  backup={bk}")
    for sid, name, decisions, created in log:
        print(f"\n#{sid}  {name!r}  (+{created} new)")
        for d in decisions:
            print(f"     {d}")
    print(f"\nRENAME: {RENAME}")
    print(f"ARCHIVE non-person: ids {ARCHIVE_NONPERSON}, {n_arch} form(s) archived")

    # post-state: any remaining multi-name records?
    remaining = conn.execute(
        "SELECT id, name FROM resource_person WHERE (name LIKE '%,%' OR name LIKE '% and %' "
        "OR name LIKE '% & %' OR name LIKE '%/%') AND COALESCE(hidden_public,0)=0").fetchall()
    print(f"\nRemaining visible multi-name records: {len(remaining)}")
    for rid, nm in remaining:
        print(f"   #{rid} {nm!r}")

    if not apply:
        conn.rollback()
        print("\nDRY RUN (rolled back) — pass --apply to write.")
    conn.close()


if __name__ == "__main__":
    db = "css_is.db"
    apply = "--apply" in sys.argv
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            db = a
    run(db, apply=apply)
