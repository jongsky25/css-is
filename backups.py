"""
Office Connect backups
==============

Self-contained backup engine for the single SQLite database, driven from the
admin Backups module (/admin/backups) — no external scheduler, no new
dependencies.

  * make_backup()  — a consistent snapshot via the SQLite backup API (safe to
                     run while the dev server holds the DB open).
  * list/prune/delete/restore — manage the snapshot files.
  * read_config/write_config — the schedule, stored in app_setting.
  * is_due/next_due — pure schedule arithmetic (unit-tested).
  * run_scheduled_job — what the in-process scheduler fires: backup, then prune
                        old snapshots, then (optionally) the 6-month attendee
                        retention purge. One self-maintaining job.

Snapshots live in _backups/scheduled/ (kept separate from the hand-made
pre-cleanup snapshots in _backups/, which this module never prunes). Filename:
    css_is_YYYYmmdd_HHMMSS_<kind>.db      kind = manual | auto | pre_restore
"""

from __future__ import annotations
import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta

import storage as st
import tzutil as tz

def _default_sched_dir():
    """Where scheduled snapshots live: on PERSISTENT storage, so they survive a
    Space rebuild (the repo folder does NOT). Resolution order:

      1. CSS_PERSIST_DIR (the mounted bucket, e.g. /data) -- the production model:
         the live DB runs on the fast local disk while its durable snapshots are
         written here and restored on boot (see app.py _ensure_live_db).
      2. CSS_DB's own directory -- legacy "live DB directly on /data".
      3. <repo>/_backups/scheduled -- local dev.

    Without (1)/(2) the backups would sit on the ephemeral disk and vanish on
    every push, exactly like the DB used to. See DEPLOY.md."""
    persist = os.environ.get("CSS_PERSIST_DIR", "").strip()
    if persist:
        base = persist
    else:
        db = os.environ.get("CSS_DB", "css_is.db")
        base = os.path.dirname(os.path.abspath(db))
    return os.path.join(base, "_backups", "scheduled")


# Module-level so tests can monkeypatch it; computed once from CSS_DB at import.
SCHED_DIR = _default_sched_dir()
_NAME_RE = re.compile(r"^css_is_(\d{8})_(\d{6})_(manual|auto|pre_restore)\.db$")

FREQS = ("h6", "h12", "daily", "weekly")
FREQ_LABEL = {"h6": "Every 6 hours", "h12": "Every 12 hours",
              "daily": "Daily", "weekly": "Weekly"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Setting keys + defaults.
_DEFAULTS = {
    "backup_enabled": "0",
    "backup_freq": "daily",
    "backup_time": "02:00",     # HH:MM, used by daily/weekly
    "backup_weekday": "0",      # 0=Mon .. 6=Sun, used by weekly
    "backup_keep": "14",        # how many scheduled snapshots to retain
    "backup_purge": "1",        # also run the attendee retention purge in the job
    "last_backup_at": "",       # ISO of the last successful backup (any kind from the job)
    "last_backup_status": "",   # human one-liner
}


# ---------------------------------------------------------------------
# Snapshot files
# ---------------------------------------------------------------------

def _now():
    return tz.now_local()


def make_backup(db_path="css_is.db", kind="manual"):
    """Write a consistent snapshot and return its metadata dict. Raises on I/O
    failure so the caller can surface it (the scheduler catches + records it)."""
    os.makedirs(SCHED_DIR, exist_ok=True)
    name = f"css_is_{_now():%Y%m%d_%H%M%S}_{kind}.db"
    dst = os.path.join(SCHED_DIR, name)
    src = sqlite3.connect(db_path)
    out = sqlite3.connect(dst)
    try:
        with out:
            src.backup(out)
    finally:
        src.close()
        out.close()
    # Advance the high-water mark to the data we just captured (monotonic — it
    # can't be lowered by a stale writer). This is what a later boot compares the
    # newest visible snapshot against to detect a lagging FUSE view.
    # A writer can commit to the live DB after the copy finishes. The recovery
    # marker must describe the data actually saved, not a newer live generation.
    write_highwater(dst, name)
    return _meta(name)


def _meta(name):
    path = os.path.join(SCHED_DIR, name)
    m = _NAME_RE.match(name)
    when = None
    if m:
        try:
            when = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except ValueError:
            when = None
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"name": name, "path": path, "size": size, "human": human_size(size),
            "kind": m.group(3) if m else "?",
            "when": when.isoformat(timespec="seconds") if when else "",
            "when_dt": when}


def list_backups():
    """All scheduled snapshots, newest first."""
    if not os.path.isdir(SCHED_DIR):
        return []
    metas = [_meta(n) for n in os.listdir(SCHED_DIR) if _NAME_RE.match(n)]
    metas.sort(key=lambda m: m["name"], reverse=True)
    return metas


def newest_valid_snapshot():
    """Path of the newest scheduled snapshot that opens cleanly, or None.

    Used by the boot restore: a container killed mid-snapshot can leave a torn
    final file, so we skip any snapshot that won't open or isn't a real CSS DB
    and fall back to the previous good one."""
    for m in list_backups():
        p = m["path"]
        try:
            c = sqlite3.connect(p)
            try:
                c.execute("SELECT count(*) FROM response").fetchone()
                c.execute("PRAGMA quick_check").fetchone()
            finally:
                c.close()
            return p
        except Exception:
            continue
    return None


def snapshots_present():
    """True if ANY snapshot file exists in SCHED_DIR -- valid or not.

    The boot guard needs to tell two very different situations apart that
    newest_valid_snapshot() collapses into the same None:
      * genuinely empty bucket (first ever boot)  -> seeding is safe;
      * snapshots exist but none open cleanly       -> corruption/half-mount,
        seeding would REVERT live data, so it must abort instead.
    """
    return bool(list_backups())


# ---------------------------------------------------------------------
# High-water mark — the guard against a STALE-SNAPSHOT revert.
#
# The boot restore loads newest_valid_snapshot(). During a restart/handoff the
# bucket is a FUSE mount whose view can lag, so a freshly-booting container can
# briefly see an OLDER snapshot as "newest", restore it, and then let its stale
# lineage overwrite the good one (observed 2026-06-23: a restart rolled the live
# DB back ~19 min, dropping committed rows). To stop that we record, on every
# snapshot, a monotonic high-water mark of the data captured; boot then REFUSES
# to restore a snapshot that sits BELOW the mark (a stale view), and the persist
# loop refuses to snapshot a live DB that is below it (a stale lineage). The mark
# only goes DOWN on a deliberate admin restore.
# ---------------------------------------------------------------------

# Append-only tables whose MAX(rowid) only ever rises in normal use (rows are
# inserted, never renumbered or deleted), so a drop is a hard signal that
# committed data was lost. Survey data (response/answer), governance (audit_log)
# and the feedback-ack trail (feedback_update) between them catch every revert we
# care about. admin_user is here too so the SAME stale-restore guard protects
# LOGIN ACCOUNTS: a new account/password only touches admin_user (it need not
# write a response or even an audit row), so without this a stale FUSE view could
# restore a snapshot predating the account and the boot/persist guards would not
# notice — accounts would silently reset while survey data looked intact (the
# exact "accounts get reset on update" symptom). Production never hard-deletes an
# account (deactivation is an UPDATE active=0, rowid unchanged), so admin_user's
# MAX(rowid) is monotonic and safe as a high-water counter. Missing tables
# (older/newer schema) score 0 and are simply ignored.
_HIGHWATER_TABLES = ("response", "answer", "audit_log", "feedback_update", "admin_user", "integration_change")
_HIGHWATER_FILE = ".css_highwater.json"


def _highwater_path():
    return os.path.join(SCHED_DIR, _HIGHWATER_FILE)


def db_marker(db_path):
    """Composite high-water marker of a DB: {table: MAX(rowid)} for the append-only
    tables. Returns {} if the DB can't be opened (caller treats that as 'unknown')."""
    try:
        c = sqlite3.connect(db_path)
    except Exception:
        return {}
    try:
        have = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        out = {}
        for t in _HIGHWATER_TABLES:
            if t in have:
                out[t] = c.execute(f"SELECT COALESCE(MAX(rowid), 0) FROM {t}").fetchone()[0]
        return out
    except Exception:
        return {}
    finally:
        c.close()


def marker_is_stale(marker, highwater):
    """Pure: True if `marker` sits BELOW `highwater` on any tracked counter — i.e.
    using it would lose committed data. Empty/absent highwater -> never stale (we
    have nothing to compare against yet). Empty marker (unreadable DB) -> stale if a
    highwater exists (don't trust an unreadable candidate over a known good mark)."""
    if not highwater:
        return False
    if not marker:
        return True
    return any(marker.get(k, 0) < hw for k, hw in highwater.items())


def read_highwater():
    """The recorded high-water marker dict, or None if absent/unreadable."""
    try:
        with open(_highwater_path(), encoding="utf-8") as f:
            m = json.load(f).get("marker")
            return m if isinstance(m, dict) else None
    except Exception:
        return None


def write_highwater(db_path, snapshot_name=None):
    """Record the high-water mark for the data just snapshotted. MONOTONIC: merges
    by max() with the existing mark, so an overlapping stale container can never
    push it backwards. Atomic (temp + os.replace). Best-effort — never raises."""
    try:
        marker = db_marker(db_path)
        if not marker:
            return
        cur = read_highwater() or {}
        merged = {k: max(marker.get(k, 0), cur.get(k, 0)) for k in set(marker) | set(cur)}
        payload = {"marker": merged, "snapshot": snapshot_name,
                   "ts": _now().isoformat(timespec="seconds")}
        os.makedirs(SCHED_DIR, exist_ok=True)
        tmp = _highwater_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, _highwater_path())
    except Exception:
        pass


def reset_highwater(db_path):
    """OVERWRITE the high-water mark to this DB's marker (the one place it may go
    DOWN) — used after a DELIBERATE admin restore of an older snapshot, so the
    chosen-older state isn't then rejected as 'stale'. Best-effort."""
    try:
        marker = db_marker(db_path)
        payload = {"marker": marker, "snapshot": "(restore)",
                   "ts": _now().isoformat(timespec="seconds")}
        os.makedirs(SCHED_DIR, exist_ok=True)
        tmp = _highwater_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(tmp, _highwater_path())
    except Exception:
        pass


def live_db_is_stale(db_path):
    """True if the live DB has fallen BELOW the recorded high-water — i.e. this
    container is on a reverted/stale lineage and must NOT snapshot over the good
    backups. The persist loop checks this before every snapshot."""
    return marker_is_stale(db_marker(db_path), read_highwater())


def persist_action(live_marker, best_snapshot_marker, highwater):
    """Pure decision for the persist loop, given the live DB's marker, the newest
    VALID snapshot's marker, and the recorded high-water mark. Returns:

      'ok'      -- live is at/above the mark -> snapshot normally.
      'skip'    -- live is below the mark AND some surviving snapshot is strictly
                   ahead of live -> we ARE a stale lineage; skip to protect that
                   better backup (the original 2026-06-23 guard).
      'realign' -- live is below the mark but NO surviving snapshot beats live ->
                   the mark is ORPHANED: it points at data that no snapshot holds
                   (e.g. a split-brain peer advanced the monotonic mark, then died,
                   and its snapshot was lost/reverted). Skipping forever then kills
                   ALL persistence (the 2026-06-25 deadlock). Realign the mark DOWN
                   to live and resume — we can't be protecting a good backup that
                   does not exist. Safe: it never fires while a richer snapshot is
                   present, so it can't undo the stale-overwrite protection.
    """
    if not marker_is_stale(live_marker, highwater):
        return "ok"
    if best_snapshot_marker and marker_is_stale(live_marker, best_snapshot_marker):
        return "skip"
    return "realign"


def persist_is_stalled(*, last_tick, last_ok, unsaved, now, tick, stall_ticks=5):
    """Pure: True if the persist loop is STALLED — i.e. live data is not actually
    reaching the bucket right now — even when the recorded state still reads the
    last 'ok'. This is the 2026-06-26 blind spot: a worker thread hung on bucket
    (FUSE) I/O froze the loop AND left the /ops card falsely green. All times are
    monotonic seconds; `None` means 'never happened yet'. Two independent signals,
    either of which is a stall (window = stall_ticks * tick):

      * the loop stopped TICKING — `last_tick` is older than the window (a wedged
        worker never reaches the top of the loop again); or
      * data is WAITING to be saved (`unsaved`) yet the last successful save
        (`last_ok`) is older than the window — the saver isn't keeping up.

    Returns False before the loop has ever ticked (`last_tick is None`) so a
    just-booted app isn't reported stalled. The unsaved-staleness signal needs a
    real `last_ok` reference; before the first successful save, a ticking-but-
    failing loop is already caught by its recorded skip/fail state (and by the
    tick-staleness signal if it wedges)."""
    if last_tick is None:
        return False                         # loop never ticked -> 'pending', not stalled
    window = max(1, int(stall_ticks)) * max(1, int(tick))
    if (now - last_tick) > window:
        return True                          # loop stopped ticking -> wedged worker
    if unsaved and last_ok is not None and (now - last_ok) > window:
        return True                          # changes unwritten since the last good save
    return False


def bucket_writable(d):
    """True if `d` is present and we can create+read+delete a probe file there.

    A Hugging Face Storage Bucket is a FUSE mount that can lag a few seconds
    behind container start; until it is ready the directory may be missing,
    empty, or raise on I/O. A real write/read round-trip is the only reliable
    'is the bucket actually here?' test -- os.path.isdir() alone returns True for
    a not-yet-populated mount and False for a slow one, both of which would fool
    the boot restore into thinking the bucket is empty."""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".css_write_probe")
        with open(probe, "w") as f:
            f.write("ok")
        with open(probe) as f:
            ok = f.read() == "ok"
        os.remove(probe)
        return ok
    except Exception:
        return False


def wait_for_bucket(d, timeout=60, interval=2):
    """Block until `d` is writable (the bucket mount is ready), or `timeout`
    seconds elapse. Returns True if it became ready. Rides out FUSE mount lag at
    boot so a transient delay can't be mistaken for an empty bucket."""
    import time as _t
    waited = 0
    while True:
        if bucket_writable(d):
            return True
        if waited >= timeout:
            return False
        _t.sleep(min(interval, max(0, timeout - waited)))
        waited += interval


def boot_decision(*, valid_snapshot, mount_ready, snapshots_present,
                  initialized, allow_seed):
    """Decide what the boot restore should do on a bucket-backed Space. Pure (no
    I/O) so the rule that prevents silent reverts is unit-tested directly.

    Returns one of:
      * 'restore' -- a valid snapshot was found; load it (normal path).
      * 'seed'    -- safe to copy the shipped seed (genuine first boot, or an
                     explicit operator override).
      * 'abort'   -- refuse to start rather than overwrite live data with the
                     old seed. Covers: mount not ready, snapshots present but
                     none valid, or the bucket was initialized before yet is now
                     empty. The container crash-loops (visible) and self-heals
                     once the mount comes back -- far safer than reverting.
    """
    if valid_snapshot:
        return "restore"
    if allow_seed:                       # CSS_PERSIST_ALLOW_SEED=1 escape hatch
        return "seed"
    if not mount_ready:
        return "abort"                   # can't confirm the bucket -> never seed
    if snapshots_present:
        return "abort"                   # files exist but none valid -> corruption
    if initialized:
        return "abort"                   # ran here before, bucket now empty -> data vanished
    return "seed"                        # mount ready + truly empty + never initialized


def safe_name(name):
    """Return the validated basename of a snapshot, or None if it isn't one of
    ours (blocks path traversal / arbitrary file access)."""
    base = os.path.basename(name or "")
    return base if _NAME_RE.match(base) else None


def delete_backup(name):
    base = safe_name(name)
    if not base:
        return False
    path = os.path.join(SCHED_DIR, base)
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def prune_backups(keep, keep_daily=0):
    """Delete scheduled snapshots beyond the newest `keep`. Returns the list of
    deleted names. Three things are NEVER pruned:

      * pre_restore safety snapshots (they're the undo for a restore);
      * the newest `keep` prunable snapshots (the fine-grained recent window);
      * the newest snapshot of each of the most recent `keep_daily` days
        (deep 'anchor' restore points).

    keep_daily defaults to 0 (legacy behaviour) so the admin schedule is
    unchanged; the live persistence loop passes keep_daily so a burst of
    activity can't churn 24 minute-snapshots and silently rotate every restore
    point older than half an hour off the bucket -- there is always at least one
    snapshot per recent day to fall back to."""
    keep = max(0, int(keep))
    keep_daily = max(0, int(keep_daily))
    metas = list_backups()                       # newest first
    protected = set()
    # 1) never touch the restore-undo snapshots
    for m in metas:
        if m["kind"] == "pre_restore":
            protected.add(m["name"])
    # 2) the newest `keep` prunable snapshots (fine-grained recent window)
    prunable = [m for m in metas if m["kind"] != "pre_restore"]
    for m in prunable[:keep]:
        protected.add(m["name"])
    # 3) one deep anchor per day for the most recent `keep_daily` days
    if keep_daily:
        days_kept, seen = 0, set()
        for m in metas:                          # newest first
            mm = _NAME_RE.match(m["name"])
            if not mm:
                continue
            day = mm.group(1)                    # YYYYMMDD
            if day in seen:
                continue
            seen.add(day)
            if days_kept < keep_daily:
                protected.add(m["name"])         # newest snapshot of this day
                days_kept += 1
    deleted = []
    for m in metas:
        if m["name"] not in protected and delete_backup(m["name"]):
            deleted.append(m["name"])
    return deleted


def clear_restored_sessions(db_path, *, revoke_integrations=False):
    """Clear restored browser sessions; deliberate restores also revoke tools.

    Routine boot recovery from the newest snapshot preserves unexpired tool
    grants. An operator-selected historical restore must not revive old keys.
    Two-way Telegram work is paused on every recovery, even routine hydration,
    because snapshots can predate locally committed actions and deliveries.
    """
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            import telegram_storage
            telegram_storage.reset_after_restore(conn)
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='login_session'").fetchone():
                conn.execute("DELETE FROM login_session")
            if revoke_integrations and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                                     "AND name='integration_credential'").fetchone():
                conn.execute("UPDATE integration_credential SET revoked_at=COALESCE(revoked_at,CAST(strftime('%s','now') AS INTEGER))")
            if revoke_integrations and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                                     "AND name='mcp_oauth_grant'").fetchone():
                conn.execute("UPDATE mcp_oauth_grant SET revoked_at=COALESCE(revoked_at,CAST(strftime('%s','now') AS INTEGER))")
                conn.execute("DELETE FROM mcp_oauth_code")
                conn.execute("DELETE FROM mcp_oauth_pending")
            if revoke_integrations and conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                                     "AND name='work_channel_preference'").fetchone():
                conn.execute("UPDATE work_channel_preference SET cadence='off',binding=lower(hex(randomblob(16))),revision=revision+1")
                if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_channel_digest'").fetchone():
                    conn.execute("UPDATE work_channel_digest SET state='unknown' WHERE state='sending'")
            if revoke_integrations:
                from integration_changes import reset_after_restore
                reset_after_restore(conn)
    finally:
        conn.close()


def restore_backup(name, db_path="css_is.db"):
    """Overwrite the live DB with a chosen snapshot, after auto-snapshotting the
    current DB first (so a restore is itself reversible). Returns the safety
    snapshot's metadata. Uses the SQLite backup API to write pages into the live
    file in place — safe while the server holds connections open."""
    base = safe_name(name)
    if not base:
        raise ValueError("Unknown backup file.")
    src_path = os.path.join(SCHED_DIR, base)
    if not os.path.exists(src_path):
        raise FileNotFoundError(base)
    safety = make_backup(db_path, kind="pre_restore")
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(db_path)
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()
    # A deliberate restore may legitimately move the live DB to an OLDER state, so
    # realign the high-water mark DOWN to it — otherwise the boot/persist guards
    # would reject the admin's own chosen snapshot as "stale".
    clear_restored_sessions(db_path,revoke_integrations=True)
    reset_highwater(db_path)
    return safety


def human_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


# ---------------------------------------------------------------------
# Schedule config + arithmetic
# ---------------------------------------------------------------------

def read_config(conn):
    """Typed schedule config (settings merged over defaults)."""
    raw = dict(_DEFAULTS)
    raw.update(st.get_settings(conn, list(_DEFAULTS)))
    freq = raw["backup_freq"] if raw["backup_freq"] in FREQS else "daily"
    return {
        "enabled": raw["backup_enabled"] == "1",
        "freq": freq,
        "time": _valid_time(raw["backup_time"]),
        "weekday": _int(raw["backup_weekday"], 0, 0, 6),
        "keep": _int(raw["backup_keep"], 14, 1, 999),
        "purge": raw["backup_purge"] == "1",
        "last_backup_at": raw["last_backup_at"] or "",
        "last_backup_status": raw["last_backup_status"] or "",
    }


def write_config(conn, *, enabled=None, freq=None, time=None, weekday=None,
                 keep=None, purge=None):
    if enabled is not None:
        st.set_setting(conn, "backup_enabled", "1" if enabled else "0")
    if freq is not None and freq in FREQS:
        st.set_setting(conn, "backup_freq", freq)
    if time is not None:
        st.set_setting(conn, "backup_time", _valid_time(time))
    if weekday is not None:
        st.set_setting(conn, "backup_weekday", str(_int(weekday, 0, 0, 6)))
    if keep is not None:
        st.set_setting(conn, "backup_keep", str(_int(keep, 14, 1, 999)))
    if purge is not None:
        st.set_setting(conn, "backup_purge", "1" if purge else "0")


def _int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _valid_time(s):
    m = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", (s or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else "02:00"


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def next_due(cfg, last_at, now=None):
    """When the next scheduled backup is due, given the last one. last_at is an
    ISO string or None. Returns a datetime. Pure (no I/O) so it's unit-testable."""
    now = now or _now()
    base = _parse_iso(last_at) or now      # no history -> measure from now (no surprise immediate run)
    freq = cfg["freq"]
    if freq in ("h6", "h12"):
        return base + timedelta(hours=6 if freq == "h6" else 12)
    hh, mm = (int(x) for x in cfg["time"].split(":"))
    if freq == "daily":
        cand = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand <= base:
            cand += timedelta(days=1)
        return cand
    # weekly: next chosen weekday at HH:MM strictly after base
    cand = base.replace(hour=hh, minute=mm, second=0, microsecond=0)
    days = (cfg["weekday"] - cand.weekday()) % 7
    cand += timedelta(days=days)
    if cand <= base:
        cand += timedelta(days=7)
    return cand


def is_due(cfg, last_at, now=None):
    now = now or _now()
    return cfg["enabled"] and now >= next_due(cfg, last_at, now)


def ensure_schedule_anchor(conn):
    """Give an enabled schedule a starting point to count from, seeding
    `last_backup_at` to now if it has never recorded a run.

    Why this is needed: next_due() reads an EMPTY last_backup_at as "measure from
    now", which always lands in the FUTURE — so with no anchor is_due() is never
    true, the job never runs, and the run that WOULD set the anchor never happens
    (a deadlock: the schedule looks ON but silently never fires). A manual
    "Back up now" doesn't set last_backup_at either, so nothing else seeds it.

    Seeding to now (not to a past slot) preserves the "no surprise immediate run"
    intent — the first scheduled backup still waits for the next slot — while
    letting the schedule actually start. Idempotent: a no-op once an anchor
    exists, or when the schedule is off. Returns True if it seeded."""
    cfg = read_config(conn)
    if cfg["enabled"] and not cfg["last_backup_at"]:
        st.set_setting(conn, "last_backup_at", _now().isoformat(timespec="seconds"))
        return True
    return False


# ---------------------------------------------------------------------
# The scheduled job
# ---------------------------------------------------------------------

def run_scheduled_job(db_path="css_is.db", actor="(scheduler)", kind="auto"):
    """Backup -> prune -> (optional) retention purge. Updates last_backup_* and
    audits. Returns a result dict. Never raises — failures are recorded."""
    conn = st.connect(db_path)
    try:
        st.init_db(conn)
        cfg = read_config(conn)
        result = {"ok": False, "backup": None, "pruned": [], "purged": 0, "error": None}
        try:
            meta = make_backup(db_path, kind=kind)
            result["backup"] = meta["name"]
            result["pruned"] = prune_backups(cfg["keep"])
            if cfg["purge"]:
                import retention
                cutoff = retention.months_ago(retention.RETENTION_MONTHS_DEFAULT).isoformat(timespec="seconds")
                result["purged"] = st.purge_expired_attendees(conn, cutoff)
            result["ok"] = True
            status = (f"{kind} backup {meta['name']} ({meta['human']})"
                      + (f"; pruned {len(result['pruned'])}" if result["pruned"] else "")
                      + (f"; purged {result['purged']} attendee PII" if result["purged"] else ""))
            st.set_setting(conn, "last_backup_at", meta["when"] or _now().isoformat(timespec="seconds"))
            st.set_setting(conn, "last_backup_status", "OK — " + status)
            st.audit(conn, actor, "backup_run", target_type="backup",
                     target_id=meta["name"], summary=status)
        except Exception as e:           # noqa: BLE001 — record, never crash the loop
            result["error"] = repr(e)
            st.set_setting(conn, "last_backup_status",
                           f"FAILED at {_now().isoformat(timespec='seconds')} — {e!r}")
            try:
                st.audit(conn, actor, "backup_failed", target_type="backup",
                         summary=f"Scheduled backup failed: {e!r}")
            except Exception:
                pass
        return result
    finally:
        conn.close()


def monitoring_status(conn, now=None):
    """Content-free scheduled-backup verdict, with a 15-minute job grace.

    This checks recorded job results/deadlines, not backup integrity. Actual
    periodic durability is checked independently by the app's saver health.
    """
    cfg = read_config(conn)
    now = now or _now()
    if not cfg["enabled"]:
        return "disabled"
    if cfg["last_backup_status"].startswith("FAILED"):
        return "failed"
    last = _parse_iso(cfg["last_backup_at"])
    if last is None or last.tzinfo is not None or last > now + timedelta(minutes=5):
        return "unknown"
    due = next_due(cfg, cfg["last_backup_at"], now=now)
    return "overdue" if now > due + timedelta(minutes=15) else "ok"


def status(conn, db_path="css_is.db"):
    """Everything the admin page header needs."""
    cfg = read_config(conn)
    backups = list_backups()
    total = sum(b["size"] for b in backups)
    db_size = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    nd = next_due(cfg, cfg["last_backup_at"]) if cfg["enabled"] else None
    return {
        "cfg": cfg,
        "count": len(backups),
        "total_human": human_size(total),
        "db_human": human_size(db_size),
        "freq_label": FREQ_LABEL.get(cfg["freq"], cfg["freq"]),
        "weekday_label": WEEKDAYS[cfg["weekday"]],
        "next_due": nd.isoformat(timespec="minutes") if nd else "",
    }
