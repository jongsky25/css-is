"""Lightweight curate operations for the Activities page.

Section managers use these to tidy the activity data the dashboard groups by
date + office: rename (merge) messy activity titles to one canonical name, and
retag / untag / reassign which section an activity belongs to (plus archive junk).

Everything reuses the harmonize journal + backup machinery (harmonize.py), so every
change is audited and undoable via `harmonize.undo_batch`. No schema changes — this
is the lightweight option agreed with the user (it cannot combine activities across
different dates/offices, only relabel and retag what's there).
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


def archive_activities(conn, instance_ids, actor, batch):
    """Hide the selected activities' forms from the dashboard (archived=1)."""
    conn.execute(hz._UNDO_DDL)
    changed = 0
    for fid in instance_ids:
        row = conn.execute("SELECT archived FROM form_instance WHERE id=?", (fid,)).fetchone()
        if not row or row[0]:
            continue
        hz._journal(conn, batch, "fi_archive", fid, None)
        conn.execute("UPDATE form_instance SET archived=1 WHERE id=?", (fid,))
        changed += 1
    if changed:
        st.audit(conn, actor, "activity_archive", target_type="form_instance",
                 target_id=instance_ids[0], summary=f"Archived {changed} activity form(s).")
        conn.commit()
    return changed
