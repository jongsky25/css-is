"""
wipe_external_rps.py — clear the entire EXTERNAL resource-person registry so the
directory can be rebuilt from scratch with the new structured fields (honorific,
agency, email). User-requested fresh start ("remove them all").

Removes every is_internal=0 resource_person plus its Type-3 (speaker) form
instances, responses, answers and item_remarks. BLHSD/internal plantilla staff
are left completely untouched, as is all Type-2 event-feedback data (it is keyed
by activity/org, not by resource_person).

Set-based deletes in child->parent order with FK enforcement off for the batch,
then a PRAGMA foreign_key_check PROVES the result has no dangling references
before commit (aborts if it would). DESTRUCTIVE — takes a consistent backup
first; revert by restoring it. Audited.

Usage:  python wipe_external_rps.py [db] [--apply]   (default = dry run)
"""
from __future__ import annotations
import sys
import storage as st
import harmonize as h

EXT  = "(SELECT id FROM resource_person WHERE COALESCE(is_internal,0)=0)"
FIS  = f"(SELECT id FROM form_instance WHERE rp_id IN {EXT})"
RESP = f"(SELECT id FROM response WHERE form_instance_id IN {FIS})"


def run(db_path="css_is.db", apply=False):
    bk = h.backup_db(db_path, tag="pre_external_wipe") if apply else None
    conn = st.connect(db_path)
    conn.execute("PRAGMA busy_timeout=10000")   # wait up to 10s for any stray lock

    ext_n = conn.execute("SELECT COUNT(*) FROM resource_person WHERE COALESCE(is_internal,0)=0").fetchone()[0]
    fi_n = conn.execute(f"SELECT COUNT(*) FROM form_instance WHERE id IN {FIS}").fetchone()[0]
    resp_n = conn.execute(f"SELECT COUNT(*) FROM response WHERE id IN {RESP}").fetchone()[0]

    conn.execute("PRAGMA foreign_keys=OFF")
    # cut cross-references from rows that SURVIVE (so they don't dangle)
    conn.execute(f"UPDATE response SET served_by_rp_id=NULL WHERE served_by_rp_id IN {EXT}")
    conn.execute(f"UPDATE admin_user SET rp_id=NULL WHERE rp_id IN {EXT}")
    # delete children -> parents
    conn.execute(f"DELETE FROM answer        WHERE response_id IN {RESP}")
    conn.execute(f"DELETE FROM item_remark   WHERE response_id IN {RESP}")
    conn.execute(f"DELETE FROM event_form    WHERE form_instance_id IN {FIS}")
    conn.execute(f"DELETE FROM response      WHERE form_instance_id IN {FIS}")
    conn.execute(f"DELETE FROM form_instance WHERE id IN {FIS}")
    conn.execute("DELETE FROM resource_person WHERE COALESCE(is_internal,0)=0")
    conn.execute("PRAGMA foreign_keys=ON")

    fk_problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    internal_left = conn.execute("SELECT COUNT(*) FROM resource_person WHERE is_internal=1").fetchone()[0]
    ext_left = conn.execute("SELECT COUNT(*) FROM resource_person WHERE COALESCE(is_internal,0)=0").fetchone()[0]
    orphan_resp = conn.execute(
        "SELECT COUNT(*) FROM response r LEFT JOIN form_instance fi ON fi.id=r.form_instance_id "
        "WHERE fi.id IS NULL").fetchone()[0]

    if fk_problems:
        conn.rollback(); conn.close()
        print("ABORTED — foreign_key_check found dangling refs after delete:")
        for p in fk_problems[:10]:
            print("  ", p)
        return bk

    if apply:
        conn.commit()
        st.audit(conn, "(external wipe)", "external_wipe", target_type="directory",
                 summary=(f"Removed all {ext_n} external resource persons + their "
                          f"{fi_n} speaker form(s) / {resp_n} response(s) for a fresh start. "
                          f"BLHSD staff ({internal_left}) and event data untouched."))
        ig = conn.execute("PRAGMA integrity_check").fetchone()[0]
        chain_ok = st.verify_audit_chain(conn)[0]
    else:
        conn.rollback()
        ig, chain_ok = "(dry run)", "(dry run)"

    print(f"DB {db_path}  apply={apply}  backup={bk}")
    print(f"external RPs removed: {ext_n}  | form_instances: {fi_n}  | responses: {resp_n}")
    print(f"after -> internal staff: {internal_left}  external: {ext_left}")
    print(f"orphans(resp): {orphan_resp}  | fk_check clean: {not fk_problems}  | integrity: {ig}  | chain ok: {chain_ok}")
    if not apply:
        print("DRY RUN (rolled back) — pass --apply to write.")
    conn.close()
    return bk


if __name__ == "__main__":
    db = "css_is.db"
    apply = "--apply" in sys.argv
    for a in sys.argv[1:]:
        if not a.startswith("--"):
            db = a
    run(db, apply=apply)
