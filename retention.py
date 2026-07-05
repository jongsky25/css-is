"""
CSS-IS attendee retention enforcement
======================================

Feature E captures attendee identity (name / email / contact) + consent on the
event link tree. Capturing PII turns anonymous feedback into personal data under
the PH Data Privacy Act of 2012 (RA 10173), so it must not be kept indefinitely.

THE RULE (decided with the user): attendee identity is retained for
RETENTION_MONTHS months from the date consent was given, then PERMANENTLY
DELETED. The attendee row is kept as a consent record (consent_at +
consent_text + purged_at survive) but name/email/contact are nulled. The
ratings themselves are never identifying — they live in response/answer and are
analysed anonymously — so purging identity never loses a single rating.

This script enforces the rule. Run it on a schedule (the queued
"performance monitoring + backups" task will wire it into the scheduled job;
until then run it by hand or from cron / Task Scheduler):

    python retention.py            # purge with the default 6-month window
    python retention.py --months 6 # explicit window
    python retention.py --dry-run  # report what WOULD be purged, change nothing

Every purge is written to the hash-chained audit_log as 'retention_purge'.
"""

from __future__ import annotations
import argparse
from datetime import datetime

import storage as st
import tzutil as tz

RETENTION_MONTHS_DEFAULT = 6


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


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Purge expired attendee PII (retention rule).")
    ap.add_argument("--db", default="css_is.db", help="database file (default css_is.db)")
    ap.add_argument("--months", type=int, default=RETENTION_MONTHS_DEFAULT,
                    help=f"retention window in months (default {RETENTION_MONTHS_DEFAULT})")
    ap.add_argument("--dry-run", action="store_true", help="report only, change nothing")
    args = ap.parse_args()
    run(db_path=args.db, months=args.months, dry_run=args.dry_run)
