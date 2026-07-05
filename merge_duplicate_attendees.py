"""merge_duplicate_attendees.py — one-off cleanup for ACCIDENTAL duplicate
registrations created before the dedup fix landed.

Why this is a script and NOT a UNIQUE(event_id, email) constraint
-----------------------------------------------------------------
The registration flow now *deliberately* allows two people to share one email
(an office inbox): the "Is this you? → No, I'm a different person" path. A hard
UNIQUE(event_id, email) index would forbid that. So uniqueness is enforced in
the application layer (register_attendee), and this script only cleans the
*accidental* duplicates that predate the fix.

What counts as an accidental duplicate
---------------------------------------
Same event AND same email (case-insensitive) AND same normalized name. That is
exactly the "lost my link, filled it in again" footprint. Two rows with the same
email but DIFFERENT names are left ALONE — they are the legitimate shared-inbox
case.

Merge = keep the earliest attendee id, repoint every response.attendee_id to it,
delete the duplicate rows. response is the only table that references attendee.

Usage
-----
    python merge_duplicate_attendees.py              # dry run (report only)
    python merge_duplicate_attendees.py --apply      # back up, then merge
    python merge_duplicate_attendees.py --db other.db --apply
"""
from __future__ import annotations
import argparse
import storage as st


def _norm_name(name):
    """Match the app's same-person rule: case-fold + collapse whitespace."""
    return " ".join((name or "").strip().lower().split())


def find_duplicate_groups(conn):
    """Return [{event_id, email, name, survivor, dups:[ids]}] for accidental dups
    only (same event + email + normalized name, ≥2 rows). Survivor = smallest id."""
    rows = conn.execute(
        "SELECT id, event_id, name, email FROM attendee "
        "WHERE email IS NOT NULL AND purged_at IS NULL ORDER BY id").fetchall()
    groups = {}
    for id_, eid, name, email in rows:
        key = (eid, (email or "").strip().lower(), _norm_name(name))
        groups.setdefault(key, []).append(id_)
    out = []
    for (eid, email, nname), ids in groups.items():
        if len(ids) > 1:
            ids.sort()
            out.append({"event_id": eid, "email": email, "name": nname,
                        "survivor": ids[0], "dups": ids[1:]})
    return out


def merge_group(conn, survivor, dups):
    """Repoint responses then delete the duplicate attendee rows. Returns the
    number of responses moved. Caller commits."""
    moved = 0
    for d in dups:
        cur = conn.execute(
            "UPDATE response SET attendee_id=? WHERE attendee_id=?", (survivor, d))
        moved += cur.rowcount
        conn.execute("DELETE FROM attendee WHERE id=?", (d,))
    return moved


def run(db_path="css_is.db", apply=False, conn=None):
    """Find (and optionally merge) accidental duplicates. Pass `conn` to run on an
    open connection (tests); otherwise opens db_path. Returns the groups found."""
    own = conn is None
    if own:
        conn = st.connect(db_path)
    try:
        groups = find_duplicate_groups(conn)
        if apply:
            for g in groups:
                moved = merge_group(conn, g["survivor"], g["dups"])
                g["responses_moved"] = moved
            conn.commit()
        return groups
    finally:
        if own:
            conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="css_is.db")
    ap.add_argument("--apply", action="store_true",
                    help="commit the merge (default is a dry-run report)")
    args = ap.parse_args()

    if args.apply:
        import harmonize
        print("backup:", harmonize.backup_db(args.db, tag="premerge"))

    groups = run(db_path=args.db, apply=args.apply)
    if not groups:
        print("No accidental duplicate registrations found. Nothing to do.")
        return
    total_dups = sum(len(g["dups"]) for g in groups)
    verb = "Merged" if args.apply else "Would merge"
    print(f"{verb} {total_dups} duplicate row(s) across {len(groups)} person(s):")
    for g in groups:
        moved = g.get("responses_moved")
        tail = f" (moved {moved} response(s))" if moved is not None else ""
        print(f"  event {g['event_id']} · {g['email']} · '{g['name']}': "
              f"keep #{g['survivor']}, drop {g['dups']}{tail}")
    if not args.apply:
        print("\nDry run only — re-run with --apply to commit (a backup is taken first).")


if __name__ == "__main__":
    main()
