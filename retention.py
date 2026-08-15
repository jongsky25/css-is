"""
Office Connect retention enforcement
==============================

Two independent retention jobs live in this script — same "purge what's past
its window" shape, otherwise unrelated:

1. ATTENDEE PII (the original rule). Feature E captures attendee identity
   (name / email / contact) + consent on the event link tree. Capturing PII
   turns anonymous feedback into personal data under the PH Data Privacy Act
   of 2012 (RA 10173), so it must not be kept indefinitely.

   THE RULE (decided with the user): attendee identity is retained for
   RETENTION_MONTHS months from the date consent was given, then PERMANENTLY
   DELETED. The attendee row is kept as a consent record (consent_at +
   consent_text + purged_at survive) but name/email/contact are nulled. The
   ratings themselves are never identifying — they live in response/answer and
   are analysed anonymously — so purging identity never loses a single rating.
   Every purge is written to the hash-chained audit_log as 'retention_purge'.

2. UX TELEMETRY (ui_event — docs/UX_TELEMETRY_HANDOFF_PLAN.md). Passive
   dead-click/rage-click/pageview/error rows are behavioral data, not
   audit-of-record, so they're purged past a rolling window (admin-configurable
   via the ui_telemetry_retention_days app_setting) with no consent record kept
   and no audit_log entry (see purge_stale_ui_events's docstring for why).

3. AI INTERACTION LOG (ai_interaction/ai_budget — docs/AI_INTEGRATION_PLAN.md
   Phase 0). Same shape as UX telemetry: operational log, not audit-of-record,
   purged past a rolling window (ai_log_retention_days app_setting) with no
   audit_log entry. ai_budget's stale day-rows are purged alongside it — once
   a day is past retention nothing reads its spend count anymore.

Run any of these on a schedule (the queued "performance monitoring + backups" task
will wire this into the in-process scheduled job; until then run it by hand or
from cron / Task Scheduler):

    python retention.py                       # attendee PII, default 6-month window
    python retention.py --months 6            # attendee PII, explicit window
    python retention.py --ui-events           # ui_event, default/configured window
    python retention.py --ui-events --days 30 # ui_event, explicit window
    python retention.py --ai-log              # ai_interaction (+ai_budget), default/configured window
    python retention.py --ai-log --days 30    # ai_interaction (+ai_budget), explicit window
    python retention.py --dry-run             # report what WOULD be purged, change nothing
"""

from __future__ import annotations
import argparse
from datetime import datetime, timedelta

import storage as st
import tzutil as tz

RETENTION_MONTHS_DEFAULT = 6

# UX telemetry (ui_event — docs/UX_TELEMETRY_HANDOFF_PLAN.md) is behavioral data,
# not audit-of-record like the tables above, so it doesn't need indefinite
# retention. Admin-configurable via the ui_telemetry_retention_days app_setting;
# this is only the fallback when that setting is unset.
UI_EVENT_RETENTION_DAYS_DEFAULT = 90


def months_ago(months, now=None):
    """The date `months` calendar months before `now` (clamped to a valid day)."""
    now = now or tz.now_local()
    y, m = now.year, now.month - months
    while m <= 0:
        m += 12
        y -= 1
    # Clamp the day so e.g. 31 Mar - 1 month -> 28/29 Feb, not an invalid date.
    leap = (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    dim = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return now.replace(year=y, month=m, day=min(now.day, dim))


def run(db_path="css_is.db", months=RETENTION_MONTHS_DEFAULT, dry_run=False,
        actor="(system)"):
    conn = st.connect(db_path)
    try:
        st.init_db(conn)  # ensure the attendee table/columns exist
        cutoff = months_ago(months).isoformat(timespec="seconds")
        if dry_run:
            n = conn.execute(
                "SELECT COUNT(*) FROM attendee WHERE consent_at < ? AND purged_at IS NULL",
                (cutoff,)).fetchone()[0]
            print(f"[dry-run] {n} attendee record(s) older than {months} months "
                  f"(consent before {cutoff}) would have their name/email/contact purged.")
            return n
        n = st.purge_expired_attendees(conn, cutoff)
        if n:
            st.audit(conn, actor, "retention_purge", target_type="attendee",
                     summary=(f"Purged identity (name/email/contact) of {n} attendee "
                              f"record(s) past the {months}-month retention window "
                              f"(consent before {cutoff}); ratings kept."))
        print(f"Purged {n} attendee record(s) past the {months}-month retention window.")
        return n
    finally:
        conn.close()


def purge_stale_ui_events(db_path="css_is.db", days=None, dry_run=False):
    """Purge passive UX-telemetry rows (ui_event — docs/UX_TELEMETRY_HANDOFF_PLAN.md)
    older than the retention window. `days` overrides; otherwise the window comes
    from the ui_telemetry_retention_days app_setting (UI_EVENT_RETENTION_DAYS_DEFAULT
    if that's never been set). Unlike attendee PII, there's no consent record to
    keep and no audit_log entry — this is high-volume behavioral data, not
    audit-of-record, and logging every purge would just add more of the same kind
    of row this is trying to bound."""
    conn = st.connect(db_path)
    try:
        st.init_db(conn)
        window = days if days is not None else int(st.get_setting(
            conn, "ui_telemetry_retention_days", str(UI_EVENT_RETENTION_DAYS_DEFAULT)))
        cutoff = (tz.now_local() - timedelta(days=window)).isoformat(timespec="seconds")
        if dry_run:
            n = conn.execute("SELECT COUNT(*) FROM ui_event WHERE created_at < ?",
                             (cutoff,)).fetchone()[0]
            print(f"[dry-run] {n} ui_event row(s) older than {window} days "
                  f"(before {cutoff}) would be purged.")
            return n
        n = st.purge_stale_ui_events(conn, cutoff)
        print(f"Purged {n} ui_event row(s) older than {window} days.")
        return n
    finally:
        conn.close()


AI_LOG_RETENTION_DAYS_DEFAULT = 90


def purge_stale_ai_log(db_path="css_is.db", days=None, dry_run=False):
    """Purge ai_interaction rows (+ matching stale ai_budget day-rows) past the
    retention window (docs/AI_INTEGRATION_PLAN.md Phase 0). Same shape as
    purge_stale_ui_events: operational log, not audit-of-record — no consent
    record to keep, no audit_log entry."""
    conn = st.connect(db_path)
    try:
        st.init_db(conn)
        window = days if days is not None else int(st.get_setting(
            conn, "ai_log_retention_days", str(AI_LOG_RETENTION_DAYS_DEFAULT)))
        cutoff_ts = (tz.now_local() - timedelta(days=window)).isoformat(timespec="seconds")
        cutoff_day = (tz.now_local() - timedelta(days=window)).date().isoformat()
        if dry_run:
            n = conn.execute("SELECT COUNT(*) FROM ai_interaction WHERE created_at < ?",
                             (cutoff_ts,)).fetchone()[0]
            print(f"[dry-run] {n} ai_interaction row(s) older than {window} days "
                  f"(before {cutoff_ts}) would be purged.")
            return n
        n = st.purge_stale_ai_interactions(conn, cutoff_ts)
        st.purge_stale_ai_budget(conn, cutoff_day)
        print(f"Purged {n} ai_interaction row(s) older than {window} days.")
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Purge expired attendee PII (retention rule).")
    ap.add_argument("--db", default="css_is.db", help="database file (default css_is.db)")
    ap.add_argument("--months", type=int, default=RETENTION_MONTHS_DEFAULT,
                    help=f"retention window in months (default {RETENTION_MONTHS_DEFAULT})")
    ap.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    ap.add_argument("--ui-events", action="store_true",
                    help="purge stale ui_event rows (passive UX telemetry) instead of "
                         "attendee PII")
    ap.add_argument("--ai-log", action="store_true",
                    help="purge stale ai_interaction rows (+ matching ai_budget day-rows) "
                         "instead of attendee PII")
    ap.add_argument("--days", type=int, default=None,
                    help="retention window in days for --ui-events or --ai-log (default: "
                         "the matching app_setting, or the module default if unset)")
    args = ap.parse_args()
    if args.ui_events:
        purge_stale_ui_events(db_path=args.db, days=args.days, dry_run=args.dry_run)
    elif args.ai_log:
        purge_stale_ai_log(db_path=args.db, days=args.days, dry_run=args.dry_run)
    else:
        run(db_path=args.db, months=args.months, dry_run=args.dry_run)
