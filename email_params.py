"""Admin-tunable email schedule/delay knobs (/admin/email "Timing" card).

key -> (label, default, lo, hi). Stored as app_setting "email_param.<key>"; read
through param() so a bad or missing value falls back to the default (clamped to
its range) instead of ever raising. Weekdays are Mon=0..Sun=6. Kept apart from
send_reminders so the room, calendar and shared-work senders can read the same
settings without importing the reminder sweep.
"""
import storage as st

PARAMS = {
    "event_reminder_lead_days": (
        "Day-before activity reminder: days ahead", 1, 1, 14),
    "wellness_expiry_days_before": (
        "Wellness decide-link expiry reminder: days before expiry", 3, 1, 13),
    "digest_weekday": (
        "Weekly pending-approvals digest: weekday", 0, 0, 6),
    "csm_results_delay_days": (
        "CSM results announcement: delay after activity concludes (days)", 3, 0, 30),
    "wellness_file_weekday": (
        "Wellness filing nudge: weekday", 3, 0, 6),
    "awa_file_lead_days": (
        "Work arrangement filing nudge: days before deadline", 1, 1, 14),
    "whereabouts_weekday": (
        "Weekly whereabouts email: weekday", 0, 0, 4),
    "whereabouts_rollup_weekday": (
        "Weekly whereabouts chief roll-up: weekday", 1, 0, 4),
    "travel_filing_lead_days": (
        "Travel filing reminder: days before", 2, 1, 14),
    "supplies_digest_weekday": (
        "Supplies weekly custodian summary: weekday", 0, 0, 6),
    "work_digest_weekday": (
        "Shared work weekly digest: weekday", 0, 0, 6),
    "room_morning_hour": (
        "Conference room morning summary: hour of day (24-hour)", 8, 5, 12),
    "room_afternoon_hour": (
        "Conference room afternoon schedule: hour of day (24-hour)", 16, 12, 20),
    "room_escalate_hours": (
        "Conference room request: hours waiting before the Admin Head is told", 24, 1, 168),
    "calendar_quiet_minutes": (
        "Calendar changes: minutes of quiet before one combined email goes out", 10, 1, 120),
    "calendar_max_wait_minutes": (
        "Calendar changes: longest an email is held back (minutes)", 60, 5, 480),
    "send_retry_attempts": (
        "Room and calendar emails: tries before giving up on a failed send", 3, 1, 10),
    "update_email_cooldown_min": (
        "Pinned update emails: minutes between two for the same activity", 15, 1, 240),
    "update_email_daily_cap": (
        "Pinned update emails: most emails sent per day, all activities together", 300, 10, 1000),
}


def param(conn, key):
    """An admin-tunable schedule param's current value, clamped to its
    PARAMS range so a hand-edited or stale setting can't push a job outside
    sane bounds."""
    _label, default, lo, hi = PARAMS[key]
    try:
        n = int(st.get_setting(conn, f"email_param.{key}", str(default)))
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


# ---- Delivery policy (staging redirect, sender name, reply-to, subject prefix) ----
import time as _time

POLICY_KEYS = ("redirect_to", "from_name", "reply_to", "subject_prefix")
_POLICY_TTL = 10.0
_policy_cache = {}


def get_policy(conn):
    return {k: st.get_setting(conn, f"email_policy.{k}", "") or "" for k in POLICY_KEYS}


def set_policy(conn, values):
    for k in POLICY_KEYS:
        st.set_setting(conn, f"email_policy.{k}", values.get(k, ""))
    clear_policy_cache()


def clear_policy_cache():
    _policy_cache.clear()


def install_policy(db_path):
    """Give mailer a loader for the admin's delivery policy. `db_path` is a string or a
    zero-argument callable (the app's DB can be re-pointed in tests). Cached for a few
    seconds, so a burst of mail costs one read, and cleared whenever the policy is saved."""
    import mailer

    def load():
        path = db_path() if callable(db_path) else db_path
        hit = _policy_cache.get(path)
        if hit and _time.monotonic() - hit[0] < _POLICY_TTL:
            return hit[1]
        conn = st.connect(path)
        try:
            pol = get_policy(conn)
        finally:
            conn.close()
        _policy_cache[path] = (_time.monotonic(), pol)
        return pol
    mailer.set_policy_loader(load)
