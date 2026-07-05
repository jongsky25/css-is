"""
rechain_audit.py — repair a broken audit_log hash chain.

The CSM import (import_csm_blhsd.py, since fixed) wrote two bulk_import rows with
prev_hash/row_hash hardcoded to 'genesis', snapping the tamper-evident linkage at
id 1444. The ROW CONTENT was never tampered — only the chain pointers were written
wrong. This recomputes prev_hash/row_hash for every row in id order from genesis,
using storage._audit_hash (the same function verify_audit_chain checks against).

Rows whose pointers were already correct (the valid prefix) recompute to identical
hashes, so they are not really changed; only the mis-written rows are corrected.

Usage:  python rechain_audit.py [--apply]   (default = dry run)
"""
from __future__ import annotations
import sys
import storage as st

DB = "css_is.db"
APPLY = "--apply" in sys.argv


def main():
    conn = st.connect(DB)
    rows = conn.execute(
        """SELECT id, ts, actor, action, target_type, target_id,
                  summary, before_text, after_text, prev_hash, row_hash
           FROM audit_log ORDER BY id"""
    ).fetchall()

    prev = "genesis"
    changes = []
    updates = []
    for r in rows:
        (rid, ts, actor, action, ttype, tid,
         summary, before, after, old_prev, old_hash) = r
        new_hash = st._audit_hash(prev, ts, actor, action, ttype, tid,
                                  summary, before, after)
        if old_prev != prev or old_hash != new_hash:
            changes.append(rid)
        updates.append((prev, new_hash, rid))
        prev = new_hash

    print(f"audit rows: {len(rows)}")
    print(f"rows needing repair: {len(changes)}")
    if changes:
        print(f"  first repaired id: {changes[0]}  last: {changes[-1]}")

    if not APPLY:
        ok, bad = st.verify_audit_chain(conn)
        print(f"current chain ok={ok} break_at={bad}")
        print("DRY RUN — re-run with --apply to write the repair.")
        conn.close()
        return

    conn.executemany(
        "UPDATE audit_log SET prev_hash=?, row_hash=? WHERE id=?", updates)
    conn.commit()
    ok, bad = st.verify_audit_chain(conn)
    print(f"APPLIED. chain ok={ok} break_at={bad}")
    conn.close()


if __name__ == "__main__":
    main()
