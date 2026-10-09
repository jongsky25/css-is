"""
Read-only check of who can decide conference-room requests.

    python check_room_approvers.py [path/to/css_is.db]

Lists the accounts the room feature will treat as approvers (the same rule the app
uses, via rooms.is_room_admin / rooms_notify.approver_accounts) and flags the usual
reasons an Administrative Section member is missing:

  * staff in the ADMIN unit with no login account linked to them
  * an active login account with no directory link whose email matches such staff
  * staff in the ADMIN unit who are archived or marked external
  * no ADMIN unit in the directory at all

It never writes: the database is opened read-only.
"""
import os
import sqlite3
import sys

import rooms
import rooms_notify


def _rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args)]


def main(argv):
    path = argv[1] if len(argv) > 1 else os.environ.get("CSS_DB", "css_is.db")
    if not os.path.exists(path):
        print(f"Database not found: {path}")
        return 2
    conn = sqlite3.connect(f"file:{os.path.abspath(path)}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    problems = 0

    units = _rows(conn, f"SELECT ou.id, ou.path FROM org_unit ou WHERE {rooms._ADMIN_UNIT_SQL}")
    print("Administrative Section unit(s):", ", ".join(u["path"] for u in units) or "NONE FOUND")
    if not units:
        problems += 1
        print("  ! No directory unit with a path ending in /ADMIN. Nobody can decide room requests until it exists.")

    print("\nApprovers the app finds now:")
    approvers = rooms_notify.approver_accounts(conn)
    for a in approvers:
        print(f"  - {a['name']} <{a['username']}>{'  (head)' if a['head'] else ''}")
    if not approvers:
        problems += 1
        print("  ! none")

    staff = _rows(conn, (
        "SELECT rp.id, rp.name, rp.email, rp.is_internal, rp.archived_at, ou.path "
        "FROM resource_person rp JOIN org_unit ou ON ou.id=rp.org_unit_id "
        f"WHERE {rooms._ADMIN_UNIT_SQL} ORDER BY rp.name"))
    accounts = _rows(conn, "SELECT id, username, active, role, rp_id FROM admin_user")
    by_rp = {}
    for a in accounts:
        if a["rp_id"]:
            by_rp.setdefault(a["rp_id"], []).append(a)
    by_email = {a["username"].strip().lower(): a for a in accounts}

    print("\nAdministrative Section staff in the directory:")
    for s in staff:
        notes = []
        if s["archived_at"]:
            notes.append("archived: cannot approve")
        if not s["is_internal"]:
            notes.append("marked external: cannot approve")
        linked = by_rp.get(s["id"], [])
        if not linked:
            hint = by_email.get((s["email"] or "").strip().lower())
            if hint:
                notes.append(f"no linked account, but login {hint['username']} has the same email: link it to this record")
            else:
                notes.append("no login account linked")
        elif not any(a["active"] for a in linked):
            notes.append("linked account is inactive (invite pending or deactivated)")
        ok = not notes
        problems += 0 if ok else 1
        print(f"  {'OK ' if ok else '!  '}{s['name']} [{s['path']}]" + ("" if ok else " - " + "; ".join(notes)))
    if not staff:
        print("  (nobody is filed under the ADMIN unit)")

    print()
    print(f"{problems} thing(s) to look at." if problems else "Looks good.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
