"""
merge_activities.py — fold one duplicate Type-2 (event review) activity
instance into another, across any date/venue/office gap, once a human has
confirmed they're the same real event (e.g. logged twice under two different
dates by mistake).

Why this exists: the Activities page's built-in "Rename / merge" action
(activity_admin.rename_activities) only relabels a title — by design it
"cannot combine activities across different dates/offices" (see
activity_admin.py). The Activities dashboard groups rows by the exact
(event_date, venue, lead_org/organizer) tuple (dashboard_insights._event_group_key),
so two same-titled activities on different dates still render as two cards.

This script performs the real merge instead: every response on the DUPLICATE
instance is repointed onto the ANCHOR instance, the duplicate's now-empty
form_instance row is deleted, and the anchor gets a canonical title. The
anchor's own event_date/venue/lead_org survive the merge — so pick as the
anchor whichever instance already carries the correct date/venue/section.
Reuses harmonize.apply_activity_clusters, so the change is journaled and
reversible via harmonize.undo_batch.

Usage:
  python merge_activities.py --find "DOH Representatives"          # locate candidate ids
  python merge_activities.py --show 205 101                        # inspect specific ids
  python merge_activities.py --anchor 205 --dup 101 \\
      --title "Updating DOH Representatives on Local Health Systems Policies and Programs"
                                                                    # dry run (default)
  python merge_activities.py --anchor 205 --dup 101 --title "..." --apply
                                                                    # writes, prints undo command
"""
from __future__ import annotations
import argparse
import os

import storage as st
import harmonize as hz

DB = os.environ.get("CSS_DB", "css_is.db")


def _org_label(conn, fid_row):
    lead_org_id, organizer_external_id = fid_row
    if organizer_external_id:
        row = conn.execute("SELECT name FROM external_organizer WHERE id=?",
                           (organizer_external_id,)).fetchone()
        return f"external:{row[0] if row else organizer_external_id}"
    if lead_org_id:
        row = conn.execute("SELECT name FROM org_unit WHERE id=?", (lead_org_id,)).fetchone()
        return row[0] if row else f"org#{lead_org_id}"
    return "(untagged)"


def _detail(conn, fid):
    row = conn.execute(
        """SELECT id, survey_type, event_date, end_date, venue, topic,
                  lead_org_id, organizer_external_id
           FROM form_instance WHERE id=?""", (fid,)).fetchone()
    if not row:
        return None
    (id_, styp, edate, endate, venue, topic, lead_org_id, org_ext_id) = row
    n = conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?", (fid,)).fetchone()[0]
    return {
        "id": id_, "survey_type": styp, "event_date": edate, "end_date": endate,
        "venue": venue, "topic": topic, "responses": n,
        "org": _org_label(conn, (lead_org_id, org_ext_id)),
    }


def cmd_find(conn, text):
    rows = conn.execute(
        """SELECT fi.id FROM form_instance fi WHERE fi.survey_type=2
           AND fi.topic LIKE ? ORDER BY fi.event_date DESC""",
        (f"%{text}%",)).fetchall()
    if not rows:
        print(f"No Type-2 activities matched {text!r}.")
        return
    print(f"{len(rows)} match(es) for {text!r}:\n")
    for (fid,) in rows:
        d = _detail(conn, fid)
        print(f"  #{d['id']:<6} {d['event_date']}  {d['responses']:>4} resp  "
              f"[{d['org']}]  {d['topic']!r}")


def cmd_show(conn, ids):
    for fid in ids:
        d = _detail(conn, fid)
        if not d:
            print(f"#{fid}: not found")
            continue
        print(f"#{d['id']}  survey_type={d['survey_type']}  date={d['event_date']}"
              f"{' -> ' + d['end_date'] if d['end_date'] else ''}  venue={d['venue']!r}")
        print(f"      org={d['org']}  responses={d['responses']}")
        print(f"      topic={d['topic']!r}\n")


def cmd_merge(conn, anchor_id, dup_id, title, apply_):
    anchor = _detail(conn, anchor_id)
    dup = _detail(conn, dup_id)
    if not anchor or not dup:
        missing = anchor_id if not anchor else dup_id
        print(f"ERROR: form_instance #{missing} not found.")
        return 1
    if anchor["survey_type"] != 2 or dup["survey_type"] != 2:
        print("ERROR: both --anchor and --dup must be Type-2 (event review / F2) instances.")
        return 1

    print("ANCHOR (kept, its date/venue/org survive):")
    cmd_show(conn, [anchor_id])
    print("DUPLICATE (its responses move to the anchor, then it's deleted):")
    cmd_show(conn, [dup_id])
    print(f"canonical title -> {title!r}")
    print(f"result: anchor keeps {anchor['responses']} + {dup['responses']} = "
          f"{anchor['responses'] + dup['responses']} responses, "
          f"dated {anchor['event_date']}, filed under {anchor['org']}.\n")

    if not apply_:
        print("DRY RUN — nothing written. Re-run with --apply to merge.")
        return 0

    backup_path = hz.backup_db(DB, tag="premerge")
    print(f"backup: {backup_path}")

    stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    batch = f"manualmerge-{stamp}"
    cluster = {"anchor_id": anchor_id, "delete_ids": [dup_id], "canonical": title}
    merged, deleted = hz.apply_activity_clusters(conn, [cluster], batch,
                                                 actor="(merge_activities.py)")
    conn.commit()
    print(f"batch {batch}: merged {merged} cluster, deleted {deleted} duplicate instance")
    print(f"undo: python -c \"import storage,harmonize; "
          f"c=storage.connect({DB!r}); harmonize.undo_batch(c,{batch!r})\"")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--find", metavar="TEXT", help="search Type-2 activity titles")
    ap.add_argument("--show", metavar="ID", type=int, nargs="+", help="print details for these ids")
    ap.add_argument("--anchor", metavar="ID", type=int, help="instance id to keep (correct date/venue/org)")
    ap.add_argument("--dup", metavar="ID", type=int, help="instance id to fold in and delete")
    ap.add_argument("--title", help="canonical title to set on the anchor")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = ap.parse_args()

    conn = st.connect(args.db)
    try:
        if args.find:
            cmd_find(conn, args.find)
        elif args.show:
            cmd_show(conn, args.show)
        elif args.anchor is not None and args.dup is not None and args.title:
            return cmd_merge(conn, args.anchor, args.dup, args.title, args.apply)
        else:
            ap.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
