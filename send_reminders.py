"""
Office Connect scheduled reminders
===================================

The app itself never runs a background scheduler (see retention.py's own
docstring on this) — every "email someone on a schedule, not in reaction to a
request" job lives here instead, meant to be run once a day from cron /
Windows Task Scheduler, the same way retention.py and daily_backup.py are:

    python send_reminders.py                 # every job below
    python send_reminders.py --events         # just tomorrow's event reminders
    python send_reminders.py --dry-run        # print what would be sent, send nothing

Jobs (each independently selectable so they can be scheduled at different
times of day; with no flags at all, every job runs):

  --events            Email every registrant with an address on file, plus the
                      activity's creator and section chief, a reminder for
                      activities happening TOMORROW.
  --wellness-expiry   Re-notify the approver of a still-pending wellness break
                      whose one-click decide link is about to expire.
  --digest            One email per approver bundling every wellness break AND
                      work arrangement still awaiting their decision — a
                      catch-all in case an individual notification was missed.
  --csm-rp            Email a resource person their own CSM results once their
                      session's feedback has concluded (only if they have a
                      login — the results page is not public).
  --csm-activity      Email an activity's creator + section chief its overall
                      CSM results once concluded.

Requires CSS_BASE_URL (same as the live app — see app.py's _base_url) so the
links in these emails point at the real site; a mail transport configured per
mailer.py (CSS_MAIL_RELAY_* or CSS_SMTP_*); nothing is sent if neither is set.
"""
from __future__ import annotations
import argparse
import os
from datetime import timedelta
from urllib.parse import quote

import auth
import mailer
import storage as st
import tzutil as tz


def _base_url():
    url = os.environ.get("CSS_BASE_URL")
    if not url:
        raise SystemExit("CSS_BASE_URL must be set so reminder emails carry a real link.")
    return url.rstrip("/")


def _person_name(conn, account_id):
    """Mirrors app.py's _person_name — the directory display name for an
    account, falling back to its username (email)."""
    u = st.get_admin_user_by_id(conn, account_id)
    if not u:
        return None
    rp = st.get_rp(conn, u["rp_id"]) if u.get("rp_id") else None
    return (rp["name"] if rp else None) or u["username"]


def remind_tomorrows_events(conn, base, dry_run=False):
    """Email every registrant + the creator/section chief a reminder for each
    activity happening tomorrow. Self-limiting: an activity's event_date only
    ever equals "tomorrow" on one calendar day, so a once-daily run can't
    double-remind the same activity."""
    tomorrow = (tz.today_local() + timedelta(days=1)).isoformat()
    sent = 0
    for ev in st.list_events_on_date(conn, tomorrow):
        monitor_link = f"{base}/monitor/{ev['event_token']}"
        notified_accounts = set()

        creator = st.get_admin_user(conn, ev["created_by"]) if ev.get("created_by") else None
        if creator and creator.get("username"):
            creator_name = _person_name(conn, creator["id"]) or creator["username"]
            subj, body, html = mailer.event_reminder_message(
                creator_name, ev["title"], ev["event_date"], ev.get("venue"), monitor_link)
            if dry_run:
                print(f"[dry-run] event reminder -> {creator['username']} ({ev['title']})")
            else:
                mailer.send(creator["username"], subj, body, html=html)
            notified_accounts.add(creator["id"])
            sent += 1

        lead_org_id = st.event_lead_org_id(conn, ev["id"])
        for chief_id in st.org_unit_chiefs(conn, lead_org_id):
            if chief_id in notified_accounts:
                continue
            chief = st.get_admin_user_by_id(conn, chief_id)
            if not chief or not chief.get("username"):
                continue
            chief_name = _person_name(conn, chief_id)
            subj, body, html = mailer.event_reminder_message(
                chief_name, ev["title"], ev["event_date"], ev.get("venue"), monitor_link)
            if dry_run:
                print(f"[dry-run] event reminder -> {chief['username']} ({ev['title']})")
            else:
                mailer.send(chief["username"], subj, body, html=html)
            notified_accounts.add(chief_id)
            sent += 1

        for att in st.event_attendees_status(conn, ev["id"]):
            if not att.get("email"):
                continue
            token = auth.make_recovery_token(att["id"])
            link = f"{base}/e/{ev['event_token']}/resume?rt={quote(token)}"
            subj, body, html = mailer.event_reminder_message(
                att["name"], ev["title"], ev["event_date"], ev.get("venue"), link)
            if dry_run:
                print(f"[dry-run] event reminder -> {att['email']} ({ev['title']})")
            else:
                mailer.send(att["email"], subj, body, html=html)
            sent += 1
    return sent


_ALL_JOBS = {"events", "wellness_expiry", "digest", "csm_rp", "csm_activity"}

# How many days before a wellness decide link (auth._WELLNESS_DECIDE_MAX_AGE)
# expires the approver gets re-notified, if the claim is still pending then.
_WELLNESS_REMIND_DAYS_BEFORE_EXPIRY = 3


def remind_wellness_expiring(conn, base, dry_run=False):
    """Re-notify the approver of any still-pending wellness break whose
    one-click decide link is about to expire. The reminder mints a FRESH
    token (a new 14-day window), not a resend of the original — the old one
    would be about to stop verifying anyway."""
    max_age_days = auth._WELLNESS_DECIDE_MAX_AGE // 86400
    min_age_days = max_age_days - _WELLNESS_REMIND_DAYS_BEFORE_EXPIRY
    dash_link = f"{base}/wellness/approvals"
    sent = 0
    for claim_id in st.list_stale_pending_wellness_claims(conn, min_age_days, max_age_days):
        claim = st.get_wellness_claim(conn, claim_id)
        if not claim or claim["status"] != "pending":
            continue
        for approver_id in st.get_approvers_for(conn, claim["user_id"]):
            approver = st.get_admin_user_by_id(conn, approver_id)
            if not approver or not approver.get("username"):
                continue
            approver_name = _person_name(conn, approver_id)
            token = auth.make_wellness_decide_token(claim_id, approver_id)
            decide_base = f"{base}/wellness/decide/{claim_id}?token={quote(token)}"
            subj, body, html = mailer.wellness_pending_reminder_message(
                approver_name, claim["person_name"], claim["break_date"],
                claim["start_time"], claim["hours"], dash_link,
                approve_link=f"{decide_base}&action=approve",
                deny_link=f"{decide_base}&action=deny")
            if dry_run:
                print(f"[dry-run] wellness expiry reminder -> {approver['username']} "
                      f"(claim {claim_id})")
            else:
                mailer.send(approver["username"], subj, body, html=html)
            sent += 1
    return sent


# How long after an activity ends (when it set no explicit response-window
# close_at) to wait before announcing CSM results — gives respondents time
# to actually answer first.
_CSM_RESULTS_DELAY_DAYS = 3


def send_csm_results_to_rps(conn, base, dry_run=False):
    """Email a resource person their own CSM results once their session's
    feedback has concluded. Only sent when the RP has a login (an
    admin_user account) — the results page requires signing in, so there's
    nowhere useful to send an external speaker with no account."""
    sent = 0
    for row in st.list_concluded_rp_forms_pending_csm_email(conn, _CSM_RESULTS_DELAY_DAYS):
        # No account = no way to reach the (login-gated) results page yet — leave
        # unmarked so this is retried once the RP does get one, rather than a
        # skip that can no longer notify them if that ever changes.
        account = st.get_admin_user_by_rp(conn, row["rp_id"])
        if not account or not account.get("username"):
            continue
        ev = st.get_event_by_id(conn, row["event_id"]) if row["event_id"] else None
        if not ev:
            continue
        rp = st.get_rp(conn, row["rp_id"])
        link = f"{base}{st.event_rp_results_url(conn, row['event_id'])}"
        subj, body, html = mailer.csm_rp_results_message(
            rp["name"] if rp else None, row["topic"], ev["title"], link)
        if dry_run:
            print(f"[dry-run] CSM results (RP) -> {account['username']} ({row['topic']})")
        else:
            mailer.send(account["username"], subj, body, html=html)
            st.mark_form_csm_results_emailed(conn, row["form_id"])
        sent += 1
    return sent


def send_csm_results_to_activity(conn, base, dry_run=False):
    """Email an activity's creator + section chief its overall CSM results
    once concluded — mirrors send_csm_results_to_rps, but the per-activity
    summary rather than one speaker's own numbers."""
    sent = 0
    for event_id in st.list_concluded_events_pending_csm_email(conn, _CSM_RESULTS_DELAY_DAYS):
        ev = st.get_event_by_id(conn, event_id)
        report_path = st.event_report_url(conn, event_id)
        if not ev or not report_path:
            continue
        link = f"{base}{report_path}"
        notified_accounts = set()

        creator = st.get_admin_user(conn, ev["created_by"]) if ev.get("created_by") else None
        if creator and creator.get("username"):
            creator_name = _person_name(conn, creator["id"]) or creator["username"]
            subj, body, html = mailer.csm_activity_results_message(
                creator_name, ev["title"], link)
            if dry_run:
                print(f"[dry-run] CSM results (activity) -> {creator['username']} ({ev['title']})")
            else:
                mailer.send(creator["username"], subj, body, html=html)
            notified_accounts.add(creator["id"])
            sent += 1

        lead_org_id = st.event_lead_org_id(conn, event_id)
        for chief_id in st.org_unit_chiefs(conn, lead_org_id):
            if chief_id in notified_accounts:
                continue
            chief = st.get_admin_user_by_id(conn, chief_id)
            if not chief or not chief.get("username"):
                continue
            chief_name = _person_name(conn, chief_id)
            subj, body, html = mailer.csm_activity_results_message(chief_name, ev["title"], link)
            if dry_run:
                print(f"[dry-run] CSM results (activity) -> {chief['username']} ({ev['title']})")
            else:
                mailer.send(chief["username"], subj, body, html=html)
            notified_accounts.add(chief_id)
            sent += 1

        if not dry_run:
            st.mark_event_csm_results_emailed(conn, event_id)
    return sent


def send_approvals_digest(conn, base, dry_run=False):
    """One email per approver bundling EVERY wellness break and work
    arrangement still awaiting their decision — a catch-all in case an
    individual pending-approval notification was missed or lost. Skips an
    approver who has nothing pending; never sent to someone with an empty
    digest."""
    wellness_by_approver = {}
    for (claim_id,) in conn.execute("SELECT id FROM wellness_claim WHERE status='pending' ORDER BY id"):
        claim = st.get_wellness_claim(conn, claim_id)
        if not claim:
            continue
        line = (f"{claim['person_name']} — {claim['break_date']} {claim['start_time']} "
               f"({claim['hours']}h)")
        for approver_id in st.get_approvers_for(conn, claim["user_id"]):
            wellness_by_approver.setdefault(approver_id, []).append(line)

    awa_by_approver = {}
    for (wa_id,) in conn.execute("SELECT id FROM work_arrangement WHERE status='pending' ORDER BY id"):
        wa = st.get_work_arrangement(conn, wa_id)
        if not wa:
            continue
        line = f"{wa['person_name']} — {wa['period_label']} ({wa['arrangement_label']})"
        for approver_id in st.get_approvers_for(conn, wa["user_id"]):
            awa_by_approver.setdefault(approver_id, []).append(line)

    wellness_link = f"{base}/wellness/approvals"
    awa_link = f"{base}/work-arrangement/approvals"
    sent = 0
    for approver_id in set(wellness_by_approver) | set(awa_by_approver):
        approver = st.get_admin_user_by_id(conn, approver_id)
        if not approver or not approver.get("username"):
            continue
        approver_name = _person_name(conn, approver_id)
        wellness_lines = wellness_by_approver.get(approver_id, [])
        awa_lines = awa_by_approver.get(approver_id, [])
        subj, body, html = mailer.approvals_digest_message(
            approver_name, wellness_lines, awa_lines, wellness_link, awa_link)
        if dry_run:
            print(f"[dry-run] approvals digest -> {approver['username']} "
                  f"({len(wellness_lines)} wellness, {len(awa_lines)} AWA)")
        else:
            mailer.send(approver["username"], subj, body, html=html)
        sent += 1
    return sent


def run(db_path="css_is.db", dry_run=False, jobs=None):
    """Run the selected jobs (all of them if `jobs` is None/empty). Returns a
    {job_name: emails_sent} report."""
    jobs = set(jobs) if jobs else set(_ALL_JOBS)
    conn = st.connect(db_path)
    report = {}
    try:
        st.init_db(conn)
        base = _base_url()
        if "events" in jobs:
            report["events"] = remind_tomorrows_events(conn, base, dry_run=dry_run)
        if "wellness_expiry" in jobs:
            report["wellness_expiry"] = remind_wellness_expiring(conn, base, dry_run=dry_run)
        if "digest" in jobs:
            report["digest"] = send_approvals_digest(conn, base, dry_run=dry_run)
        if "csm_rp" in jobs:
            report["csm_rp"] = send_csm_results_to_rps(conn, base, dry_run=dry_run)
        if "csm_activity" in jobs:
            report["csm_activity"] = send_csm_results_to_activity(conn, base, dry_run=dry_run)
    finally:
        conn.close()
    return report


def main():
    ap = argparse.ArgumentParser(description="Office Connect scheduled reminder emails.")
    ap.add_argument("--db", default="css_is.db")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print what would be sent; send nothing.")
    ap.add_argument("--events", action="store_true", help="Tomorrow's event reminders.")
    ap.add_argument("--wellness-expiry", action="store_true",
                    help="Re-notify approvers of soon-to-expire pending wellness breaks.")
    ap.add_argument("--digest", action="store_true",
                    help="Send each approver a digest of everything still pending on them.")
    ap.add_argument("--csm-rp", action="store_true",
                    help="Email resource persons their own CSM results once concluded.")
    ap.add_argument("--csm-activity", action="store_true",
                    help="Email an activity's creator/chief its overall CSM results.")
    args = ap.parse_args()

    jobs = {j for j, flag in (("events", args.events),
                              ("wellness_expiry", args.wellness_expiry),
                              ("digest", args.digest),
                              ("csm_rp", args.csm_rp),
                              ("csm_activity", args.csm_activity)) if flag}
    report = run(db_path=args.db, dry_run=args.dry_run, jobs=jobs or None)
    for job, n in report.items():
        print(f"{job}: {n} email(s) {'would be ' if args.dry_run else ''}sent")


if __name__ == "__main__":
    main()
