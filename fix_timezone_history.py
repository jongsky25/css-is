"""
fix_timezone_history.py — shift pre-fix UTC time logs into local (PH) time.
===========================================================================

WHY
    Until the tzutil fix, every "now" stamp was written with a bare
    datetime.now() = the SERVER's wall clock. On a Hugging Face Space the server
    runs in UTC, so all those rows landed ~8 h behind Asia/Manila — the audit
    trail showing "June 16" for an edit you made just after PH midnight. New
    rows are now stamped correctly (see tzutil); this one-time script fixes the
    OLD rows so history lines up with them.

WHAT IT TOUCHES — only the PURELY runtime-generated logs, which on a UTC host
    are unambiguously 8 h behind:
        audit_log.ts
        feedback_update.ts
        spot_feedback.created_at / updated_at / submitter_seen_at
    Then it RE-CHAINS audit_log (its hash chain covers `ts`, so shifting the
    timestamps would otherwise break verify_audit_chain).

MIXED TABLES (opt-in, --since)
    response.submitted_at, form_instance/event/event_link.created_at,
    attendee.consent_at/purged_at, activity_demographics.updated_at,
    comment_override.set_at, admin_user.created_at — these MIX live HF writes
    (UTC, 8 h behind) with rows imported from spreadsheets (migrate.py,
    import_csm_blhsd.py) whose timestamps came from the source data, NOT a UTC
    clock. A blanket +8 h would corrupt the imported history, so these are
    skipped UNLESS you pass --since YYYY-MM-DD: then only rows whose stamp is on
    or after that date are shifted. Set --since to your HF go-live date (the
    imported history all predates it), ideally a day earlier to catch rows
    written just after PH midnight (which were stored ~8 h earlier in UTC).

SAFETY
    * Dry-run by default — prints what would change. Pass --apply to write.
    * RUN IT ONLY against a DB whose runtime rows were written under UTC
      (the Hugging Face DB, or a snapshot taken from it). Do NOT run it on a DB
      that was already written in PH local time — you'd push it 8 h ahead.
    * Records `tz_history_fixed_at` in app_setting and refuses to run twice
      (so you can't accidentally double-shift to +16 h). Override with --force.

USAGE
    python fix_timezone_history.py                 # dry run, default DB + offset
    python fix_timezone_history.py --apply
    python fix_timezone_history.py --db /data/css_is.db --hours 8 --apply
"""
from __future__ import annotations
import argparse
import os
from datetime import datetime, timedelta

import storage as st

# (table, column) pairs that are 100% runtime-stamped — safe to shift wholesale.
# (audit_log includes the two bulk_import rows, but those were stamped with
# utcnow() too, so +offset lands them in PH correctly as well.)
SHIFT_TARGETS = [
    ("audit_log", "ts"),
    ("feedback_update", "ts"),
    ("spot_feedback", "created_at"),
    ("spot_feedback", "updated_at"),
    ("spot_feedback", "submitter_seen_at"),
]

# Mixed live+imported tables — only shifted for rows on/after --since (go-live).
MIXED_TARGETS = [
    ("response", "submitted_at"),
    ("form_instance", "created_at"),
    ("event", "created_at"),
    ("event_link", "created_at"),
    ("attendee", "consent_at"),
    ("attendee", "purged_at"),
    ("activity_demographics", "updated_at"),
    ("comment_override", "set_at"),
    ("admin_user", "created_at"),
]

MARKER = "tz_history_fixed_at"


def _shift_value(s, delta):
    """Return the ISO string `s` shifted by `delta`, preserving its surface form
    (the 'T'-vs-space separator). Non-parseable or blank values pass through."""
    if not s:
        return s
    raw = str(s)
    sep = "T" if "T" in raw else " "
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return s  # don't touch anything we can't parse
    shifted = dt + delta
    return shifted.isoformat(sep=sep, timespec="seconds")


def _table_has(conn, table, col):
    try:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except Exception:
        return False
    return col in cols


def _rechain_audit(conn):
    """Recompute prev_hash/row_hash for every audit row in id order, over the
    (already shifted) ts values — same logic as rechain_audit.py."""
    rows = conn.execute(
        """SELECT id, ts, actor, action, target_type, target_id,
                  summary, before_text, after_text
           FROM audit_log ORDER BY id""").fetchall()
    prev = "genesis"
    updates = []
    for (rid, ts, actor, action, ttype, tid, summary, before, after) in rows:
        new_hash = st._audit_hash(prev, ts, actor, action, ttype, tid,
                                  summary, before, after)
        updates.append((prev, new_hash, rid))
        prev = new_hash
    conn.executemany(
        "UPDATE audit_log SET prev_hash=?, row_hash=? WHERE id=?", updates)


def _shift_table(conn, table, col, delta, since, apply):
    """Shift one (table, col). If `since` is set, only rows whose stamp is on or
    after it are touched (used for the mixed live+imported tables). Returns the
    number of rows shifted."""
    if not _table_has(conn, table, col):
        print(f"  skip {table}.{col} (not present)")
        return 0
    rows = conn.execute(
        f"SELECT rowid, {col} FROM {table} WHERE {col} IS NOT NULL AND {col} != ''"
    ).fetchall()
    changed = []
    for rid, v in rows:
        if since is not None and str(v) < since:
            continue
        nv = _shift_value(v, delta)
        if nv != v:
            changed.append((rid, nv, v))
    print(f"  {table}.{col}: {len(changed)} rows to shift", end="")
    if changed:
        _, nv, v = changed[0]
        print(f"   e.g. {v!r} -> {nv!r}", end="")
    print()
    if apply and changed:
        conn.executemany(
            f"UPDATE {table} SET {col}=? WHERE rowid=?",
            [(nv, rid) for rid, nv, _ in changed])
    return len(changed)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=os.environ.get("CSS_DB", "css_is.db"))
    ap.add_argument("--hours", type=int,
                    default=int(os.environ.get("CSS_TZ_OFFSET", "8")),
                    help="hours to add (UTC->local offset; default 8)")
    ap.add_argument("--since", default=None,
                    help="also shift mixed live+imported tables (responses/events/"
                         "attendees) for rows on/after this date, e.g. 2026-06-01. "
                         "Set to (a day before) your HF go-live date.")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--force", action="store_true", help="run even if already fixed")
    args = ap.parse_args()

    delta = timedelta(hours=args.hours)
    conn = st.connect(args.db)

    print(f"DB: {args.db}")
    print(f"Shift: +{args.hours} h")
    print(f"Mixed tables (--since): {args.since or 'SKIPPED'}\n")

    prior = st.get_setting(conn, MARKER)
    if prior and not args.force:
        print(f"ALREADY FIXED on {prior} — refusing to run again (would double-shift).")
        print("Pass --force only if you are certain this DB still holds UTC rows.")
        conn.close()
        return

    ok_before, bad_before = st.verify_audit_chain(conn)
    print(f"audit chain before migration: ok={ok_before} break_at={bad_before}\n")

    total = 0
    print("Pure-runtime logs (always shifted):")
    for table, col in SHIFT_TARGETS:
        total += _shift_table(conn, table, col, delta, None, args.apply)

    if args.since:
        print(f"\nMixed tables (rows on/after {args.since}):")
        for table, col in MIXED_TARGETS:
            total += _shift_table(conn, table, col, delta, args.since, args.apply)

    print(f"\nTotal stamps to shift: {total}")

    if not args.apply:
        print("\nDRY RUN — re-run with --apply to write.")
        conn.close()
        return

    _rechain_audit(conn)
    conn.commit()
    ok_after, bad_after = st.verify_audit_chain(conn)
    print(f"audit chain re-chained: ok={ok_after} break_at={bad_after}")

    st.set_setting(conn, MARKER, st.tz.now_iso())
    conn.commit()
    conn.close()
    print("APPLIED.")


if __name__ == "__main__":
    main()
