"""Lightweight curate operations for the Activities page.

Section managers use these to tidy the activity data the dashboard groups by
date + office: rename (merge) messy activity titles to one canonical name, and
retag / untag / reassign which section an activity belongs to (plus archive junk).
`rename_activities` only relabels — it cannot combine rows across different
dates/offices, since the dashboard groups on that exact tuple. `merge_activities`
is the one op that can, by actually repointing responses onto a survivor
instance; it's admin-only (see auth.ROLE_CAPS['merge_activity']) because it can
silently fold two different real-world sessions into one if misused.

Everything reuses the harmonize journal + backup machinery (harmonize.py), so every
change is audited and undoable via `harmonize.undo_batch`. No schema changes.
"""
import datetime as _dt

import storage as st
import harmonize as hz

# One automatic full-DB snapshot per process the first time a curate op runs — the
# safety net behind the fine-grained journal undo.
_BACKED_UP = []


def new_batch():
    return f"curate_{_dt.datetime.now():%Y%m%d_%H%M%S_%f}"


def ensure_backup(db_path="css_is.db"):
    """Snapshot the DB once per process, before the first curate write."""
    if _BACKED_UP:
        return None
    path = hz.backup_db(db_path, tag="precurate")
    _BACKED_UP.append(path)
    return path


def rename_activities(conn, f2_ids, title, actor, batch):
    """Give the selected activities' event-review (F2) forms one canonical title.
    Selecting several = a 'merge' of their labels into a single name."""
    conn.execute(hz._UNDO_DDL)
    title = (title or "").strip()
    if not title or not f2_ids:
        return 0
    changed = 0
    for fid in f2_ids:
        row = conn.execute("SELECT topic FROM form_instance WHERE id=?", (fid,)).fetchone()
        if not row or row[0] == title:
            continue
        hz._journal(conn, batch, "fi_topic", fid, {"old": row[0], "new": title})
        conn.execute("UPDATE form_instance SET topic=? WHERE id=?", (title, fid))
        changed += 1
    if changed:
        st.audit(conn, actor, "activity_rename", target_type="form_instance",
                 target_id=f2_ids[0], summary=f"Renamed {changed} activity form(s) to “{title}”.",
                 after=title)
        conn.commit()
    return changed


def retag_section(conn, instance_ids, org_id, actor, batch, label):
    """Set the lead org on every form of the selected activities. `org_id` = a section
    id to (re)assign, or the bureau id to untag (bureau-wide)."""
    conn.execute(hz._UNDO_DDL)
    changed = 0
    for fid in instance_ids:
        row = conn.execute("SELECT lead_org_id FROM form_instance WHERE id=?", (fid,)).fetchone()
        if not row or row[0] == org_id:
            continue
        hz._journal(conn, batch, "fi_lead_org", fid, {"old": row[0], "new": org_id})
        conn.execute("UPDATE form_instance SET lead_org_id=? WHERE id=?", (org_id, fid))
        changed += 1
    if changed:
        st.audit(conn, actor, "activity_retag", target_type="form_instance",
                 target_id=instance_ids[0], summary=f"Tagged {changed} activity form(s) to {label}.",
                 after=label)
        conn.commit()
    return changed


def merge_activities(conn, f2_ids, title, event_date, actor, batch):
    """Combine 2+ event-review (F2) activities into ONE, even across different
    dates/venues/offices — the one curate op `rename_activities` deliberately
    can't do (see module docstring). Every response on the ticked instances
    other than the survivor is repointed onto it (most responses first, so the
    fewest rows move), the emptied duplicates are deleted, and the survivor is
    stamped with the given title and corrected date.

    Admin-only in the UI (auth.ROLE_CAPS['merge_activity']) — the caller is
    responsible for warning the operator when the selection doesn't already
    share one date, since this is the one op here that can silently fold
    attendance from two different real-world sessions into one row if misused.

    Reuses harmonize.apply_activity_clusters, so the response repoints + the
    deleted duplicate(s) are journaled and reversible via harmonize.undo_batch,
    same as every other curate op in this file."""
    conn.execute(hz._UNDO_DDL)
    title = (title or "").strip()
    event_date = (event_date or "").strip()
    f2_ids = list(dict.fromkeys(f2_ids or []))     # de-dup, keep order
    if len(f2_ids) < 2 or not title or not event_date:
        return 0, 0
    rows = conn.execute(
        f"SELECT id FROM form_instance WHERE id IN ({','.join('?' * len(f2_ids))}) AND survey_type=2",
        f2_ids).fetchall()
    ids = [r[0] for r in rows]
    if len(ids) < 2:
        return 0, 0
    counts = {i: conn.execute("SELECT COUNT(*) FROM response WHERE form_instance_id=?",
                              (i,)).fetchone()[0] for i in ids}
    anchor = max(ids, key=lambda i: (counts[i], -i))   # most responses stays; ties -> lowest id
    dels = [i for i in ids if i != anchor]
    cluster = {"anchor_id": anchor, "delete_ids": dels, "canonical": title}
    merged, deleted = hz.apply_activity_clusters(conn, [cluster], batch, actor=actor)
    old_date = conn.execute("SELECT event_date FROM form_instance WHERE id=?", (anchor,)).fetchone()[0]
    if old_date != event_date:
        hz._journal(conn, batch, "fi_event_date", anchor, {"old": old_date, "new": event_date})
        conn.execute("UPDATE form_instance SET event_date=? WHERE id=?", (event_date, anchor))
    st.audit(conn, actor, "activity_merge", target_type="form_instance", target_id=anchor,
             summary=f"Merged {len(ids)} activities into “{title}” dated {event_date} (kept #{anchor}).",
             after=f"{title} ({event_date})")
    conn.commit()
    return merged, deleted


def set_activity_date(conn, f2_ids, event_date, actor, batch):
    """Correct the event_date on one or more event-review (F2) activities directly
    — no second activity to merge into needed. This is the other half of "the
    date is wrong": `merge_activities` combines two records AND fixes the date in
    one step, but sometimes there's nothing to combine, just a typo/import error
    to correct after the fact (including on an activity that was itself just the
    survivor of a merge). Same admin gate as merge (auth.ROLE_CAPS['merge_activity']).

    Journaled ("fi_event_date") and reversible via harmonize.undo_batch, same as
    every other curate op here."""
    conn.execute(hz._UNDO_DDL)
    event_date = (event_date or "").strip()
    f2_ids = list(dict.fromkeys(f2_ids or []))     # de-dup, keep order
    if not f2_ids or not event_date:
        return 0
    rows = conn.execute(
        f"SELECT id FROM form_instance WHERE id IN ({','.join('?' * len(f2_ids))}) AND survey_type=2",
        f2_ids).fetchall()
    ids = [r[0] for r in rows]
    changed = 0
    for fid in ids:
        old = conn.execute("SELECT event_date FROM form_instance WHERE id=?", (fid,)).fetchone()[0]
        if old == event_date:
            continue
        hz._journal(conn, batch, "fi_event_date", fid, {"old": old, "new": event_date})
        conn.execute("UPDATE form_instance SET event_date=? WHERE id=?", (event_date, fid))
        changed += 1
    if changed:
        st.audit(conn, actor, "activity_redate", target_type="form_instance",
                 target_id=ids[0], summary=f"Corrected {changed} activity date(s) to {event_date}.",
                 after=event_date)
        conn.commit()
    return changed


def archive_activities(conn, instance_ids, actor, batch):
    """Hide the selected activities' forms from the dashboard (archived=1)."""
    conn.execute(hz._UNDO_DDL)
    changed = 0
    for fid in instance_ids:
        row = conn.execute("SELECT archived FROM form_instance WHERE id=?", (fid,)).fetchone()
        if not row or row[0] or st.is_standing_walkin_form(conn, fid):
            continue                     # the standing walk-in form is never archived
        hz._journal(conn, batch, "fi_archive", fid, None)
        conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (fid,))
        changed += 1
    if changed:
        st.audit(conn, actor, "activity_archive", target_type="form_instance",
                 target_id=instance_ids[0], summary=f"Archived {changed} activity form(s).")
        conn.commit()
    return changed
