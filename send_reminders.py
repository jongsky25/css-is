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

Run it once a day and leave it: the jobs that shouldn't fire daily gate
themselves on the right weekday (the digest) or the right date (the filing
nudges, the day-before reminders), so there is nothing to stagger by hand.

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
                      Weekly (Mondays), not on every run.
  --csm-rp            Email a resource person their own CSM results once their
                      session's feedback has concluded (only if they have a
                      login — the results page is not public).
  --csm-activity      Email an activity's creator + section chief its overall
                      CSM results once concluded.
  --wellness-file     Nudge staff who haven't used any of this week's wellness
                      break entitlement yet, the day before it lapses.
  --awa-file          Nudge staff with no work arrangement filed for the
                      earliest still-open period, the day before its deadline.

Requires CSS_BASE_URL (same as the live app — see app.py's _base_url) so the
links in these emails point at the real site; a mail transport configured per
mailer.py (CSS_MAIL_RELAY_* or CSS_SMTP_*); nothing is sent if neither is set.
"""
from __future__ import annotations
import argparse
import os
from datetime import date, timedelta
from urllib.parse import quote

import auth
import mailer
import storage as st
import tzutil as tz


_NO_BASE_URL = ("CSS_BASE_URL is not set, so reminder emails would carry no "
                "usable link — skipping. Set it to the site's public origin.")


def _base_url():
    """The public origin for the links in these emails, or None when it isn't
    configured. Deliberately NOT a SystemExit: run() is also called from the
    app's own scheduler loop (app._scheduler_loop), and SystemExit is a
    BaseException — an `except Exception` guard would not hold it, so a
    missing env var would take the whole scheduler down with it."""
    url = os.environ.get("CSS_BASE_URL")
    return url.rstrip("/") if url else None


def _person_name(conn, account_id):
    """Mirrors app.py's _person_name — the directory display name for an
    account, falling back to its username (email)."""
    u = st.get_admin_user_by_id(conn, account_id)
    if not u:
        return None
    rp = st.get_rp(conn, u["rp_id"]) if u.get("rp_id") else None
    return (rp["name"] if rp else None) or u["username"]


def _send(conn, feature, to, subj, body, html=None):
    """mailer.send() + an email_log row (docs/ADMIN_EMAIL_FEATURES_PLAN.md
    Phase 6). Every call site here is a real attempt worth logging — a
    disabled job never reaches its function at all (run() drops it from
    `jobs` before any job function runs), so there is no 'skipped_off' case
    to handle at this level."""
    result = mailer.send(to, subj, body, html=html)
    st.log_email_send(conn, feature, to, subj, mailer.send_status(result), result.get("detail"))
    return result


def remind_tomorrows_events(conn, base, dry_run=False):
    """Email every registrant + the creator/section chief a reminder for each
    activity happening tomorrow. Self-limiting: an activity's event_date only
    ever equals "tomorrow" on one calendar day, so a once-daily run can't
    double-remind the same activity."""
    lead_days = _param(conn, "event_reminder_lead_days")
    tomorrow = (tz.today_local() + timedelta(days=lead_days)).isoformat()
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
                _send(conn, JOB_FEATURE["events"], creator["username"], subj, body, html=html)
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
                _send(conn, JOB_FEATURE["events"], chief["username"], subj, body, html=html)
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
                _send(conn, JOB_FEATURE["events"], att["email"], subj, body, html=html)
            sent += 1
    return sent


_ALL_JOBS = {"events", "wellness_expiry", "digest", "csm_rp", "csm_activity",
            "wellness_file", "awa_file", "whereabouts",
            "whereabouts_nudge", "whereabouts_rollup"}

# job name -> the admin toggle that can switch it off (see /admin/email).
JOB_FEATURE = {
    "events": "job_events",
    "wellness_expiry": "job_wellness_expiry",
    "digest": "job_digest",
    "csm_rp": "job_csm_rp",
    "csm_activity": "job_csm_activity",
    "wellness_file": "job_wellness_file",
    "awa_file": "job_awa_file",
    "whereabouts": "job_whereabouts",
    "whereabouts_nudge": "job_whereabouts_nudge",
    "whereabouts_rollup": "job_whereabouts_rollup",
}

# Admin-tunable schedule/delay knobs for the jobs below (/admin/email "Timing"
# card). key -> (label, default, lo, hi). Stored as app_setting
# "email_param.<key>"; read through _param() so a bad/missing value falls
# back to the default instead of ever raising. Weekdays are Mon=0..Sun=6.
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
        "Weekly whereabouts chief roll-up: weekday", 2, 0, 4),
}


def _param(conn, key):
    """An admin-tunable schedule param's current value, clamped to its
    PARAMS range so a hand-edited or stale setting can't push a job outside
    sane bounds."""
    _label, default, lo, hi = PARAMS[key]
    try:
        n = int(st.get_setting(conn, f"email_param.{key}", str(default)))
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


def remind_wellness_expiring(conn, base, dry_run=False):
    """Re-notify the approver of any still-pending wellness break whose
    one-click decide link is about to expire. The reminder mints a FRESH
    token (a new 14-day window), not a resend of the original — the old one
    would be about to stop verifying anyway. Marked per claim once sent, so
    the days-wide catch-up window can't turn into a daily nag."""
    max_age_days = auth._WELLNESS_DECIDE_MAX_AGE // 86400
    min_age_days = max_age_days - _param(conn, "wellness_expiry_days_before")
    dash_link = f"{base}/approvals#wellness"
    sent = 0
    for claim_id in st.list_stale_pending_wellness_claims(conn, min_age_days, max_age_days):
        claim = st.get_wellness_claim(conn, claim_id)
        if not claim or claim["status"] != "pending":
            continue
        reminded = 0
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
                _send(conn, JOB_FEATURE["wellness_expiry"], approver["username"], subj, body,
                     html=html)
            sent += 1
            reminded += 1
        # Only once something actually went out: a claim whose chain has no
        # reachable approver yet hasn't been reminded, so don't record it as
        # though it had.
        if reminded and not dry_run:
            st.mark_wellness_decide_reminded(conn, claim_id)
    return sent


def send_csm_results_to_rps(conn, base, dry_run=False):
    """Email a resource person their own CSM results once their session's
    feedback has concluded. Only sent when the RP has a login (an
    admin_user account) — the results page requires signing in, so there's
    nowhere useful to send an external speaker with no account."""
    sent = 0
    for row in st.list_concluded_rp_forms_pending_csm_email(conn, _param(conn, "csm_results_delay_days")):
        # No account = no way to reach the (login-gated) results page yet — leave
        # unmarked so this is retried once the RP does get one, rather than a
        # skip that can no longer notify them if that ever changes.
        account = st.get_admin_user_by_rp(conn, row["rp_id"])
        if not account or not account.get("username"):
            continue
        ev = st.get_event_by_id(conn, row["event_id"]) if row["event_id"] else None
        results_path = st.event_rp_results_url(conn, row["event_id"]) if ev else None
        if not ev or not results_path:
            continue
        rp = st.get_rp(conn, row["rp_id"])
        link = f"{base}{results_path}"
        subj, body, html = mailer.csm_rp_results_message(
            rp["name"] if rp else None, row["topic"], ev["title"], link)
        if dry_run:
            print(f"[dry-run] CSM results (RP) -> {account['username']} ({row['topic']})")
        else:
            _send(conn, JOB_FEATURE["csm_rp"], account["username"], subj, body, html=html)
            st.mark_form_csm_results_emailed(conn, row["form_id"])
        sent += 1
    return sent


def send_csm_results_to_activity(conn, base, dry_run=False):
    """Email an activity's creator + section chief its overall CSM results
    once concluded — mirrors send_csm_results_to_rps, but the per-activity
    summary rather than one speaker's own numbers."""
    sent = 0
    for event_id in st.list_concluded_events_pending_csm_email(conn, _param(conn, "csm_results_delay_days")):
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
                _send(conn, JOB_FEATURE["csm_activity"], creator["username"], subj, body,
                     html=html)
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
                _send(conn, JOB_FEATURE["csm_activity"], chief["username"], subj, body, html=html)
            notified_accounts.add(chief_id)
            sent += 1

        if not dry_run:
            st.mark_event_csm_results_emailed(conn, event_id)
    return sent


def remind_wellness_to_file(conn, base, dry_run=False):
    """Nudge staff who haven't used any of this week's 2-hour wellness
    entitlement yet — breaks can only be scheduled Monday-Friday, so unused
    hours lapse once the week's Friday passes."""
    today = tz.today_local()
    if today.weekday() != _param(conn, "wellness_file_weekday"):
        return 0
    week_start = st.wellness_week_start(today)
    friday_label = (date.fromisoformat(week_start) + timedelta(days=4)).isoformat()
    link = f"{base}/wellness/apply"
    sent = 0
    for staffer in st.staff_without_wellness_claim_this_week(conn, week_start):
        name = _person_name(conn, staffer["id"])
        subj, body, html = mailer.wellness_file_reminder_message(name, friday_label, link)
        if dry_run:
            print(f"[dry-run] wellness file reminder -> {staffer['username']}")
        else:
            _send(conn, JOB_FEATURE["wellness_file"], staffer["username"], subj, body, html=html)
        sent += 1
    return sent


def remind_awa_to_file(conn, base, dry_run=False):
    """Nudge staff with no work arrangement filed yet for the earliest
    still-open period, timed for the day before its Friday filing deadline —
    self-limiting to that one day, same trick as remind_wellness_to_file."""
    today = tz.today_local()
    open_periods = st.work_arrangement_open_periods()
    if not open_periods:
        return 0
    period_start = open_periods[0]
    lead_days = _param(conn, "awa_file_lead_days")
    if today != st.work_arrangement_deadline(period_start) - timedelta(days=lead_days):
        return 0
    label = st.work_arrangement_period_label(period_start)
    deadline_label = st.work_arrangement_deadline_label(period_start)
    link = f"{base}/work-arrangement/file"
    sent = 0
    for staffer in st.staff_without_work_arrangement(conn, period_start):
        name = _person_name(conn, staffer["id"])
        subj, body, html = mailer.work_arrangement_file_reminder_message(
            name, label, deadline_label, link)
        if dry_run:
            print(f"[dry-run] AWA file reminder -> {staffer['username']} ({label})")
        else:
            _send(conn, JOB_FEATURE["awa_file"], staffer["username"], subj, body, html=html)
        sent += 1
    return sent


def send_whereabouts_weekly(conn, base, dry_run=False):
    """The Monday "where will you be this week?" email: each staff member gets
    their Monday-Friday already plotted from their filed work arrangement, with a
    signed one-click link to confirm or change it to Office / Field / Leave.

    Sent on the configured weekday, with one day of catch-up so a Space that was
    asleep at 7am Monday still sends on Tuesday. Never twice for the same week:
    each send is recorded per person, so the daily sweep and any manual re-run
    skip anyone already emailed."""
    win = _whereabouts_window(conn, "whereabouts_weekday")
    if not win:
        return 0
    _today, monday = win
    label = st.whereabouts_week_label(monday)
    defaults = st.whereabouts_defaults(conn, monday)
    sent = 0
    for staffer in st.whereabouts_recipients(conn, monday):
        days = st.whereabouts_week(conn, staffer["id"], monday, defaults=defaults)
        plotted = [(d["label"], st.whereabouts_choice_label(d)) for d in days]
        token = auth.make_whereabouts_token(staffer["id"], monday.isoformat())
        link = f"{base}/whereabouts/week?token={quote(token)}"
        name = _person_name(conn, staffer["id"])
        subj, body, html = mailer.whereabouts_week_message(name, label, plotted, link)
        if dry_run:
            print(f"[dry-run] whereabouts -> {staffer['username']} ({label})")
        else:
            res = _send(conn, JOB_FEATURE["whereabouts"], staffer["username"], subj, body,
                        html=html)
            # Only a send that actually went out is recorded as emailed, so a
            # relay outage retries tomorrow instead of silently skipping the week.
            if mailer.send_status(res) == "sent":
                st.mark_whereabouts_emailed(conn, staffer["id"], monday)
        sent += 1
    return sent


def _whereabouts_window(conn, param_key, offset=0):
    """(today, monday) when today is the job's weekday (+ `offset`) or the day
    after it (one day of catch-up), else None. Always within Mon-Fri."""
    today = tz.today_local()
    day = _param(conn, param_key) + offset
    if today.weekday() not in (day, day + 1) or today.weekday() > 4:
        return None
    return today, st.whereabouts_week_start(today)


def nudge_whereabouts(conn, base, dry_run=False):
    """The day after the Monday email, nudge anyone who hasn't answered it —
    once per person per week. Never the same day the Monday email itself went
    out (a catch-up send must not be followed by an instant nudge)."""
    win = _whereabouts_window(conn, "whereabouts_weekday", offset=1)
    if not win:
        return 0
    today, monday = win
    label = st.whereabouts_week_label(monday)
    sent = 0
    for p in st.whereabouts_nonresponders(conn, monday):
        if p["nudged_at"]:
            continue
        emailed = conn.execute(
            "SELECT emailed_at FROM whereabouts_week WHERE user_id=? AND week_start=?",
            (p["id"], monday.isoformat())).fetchone()[0] or ""
        if emailed[:10] >= today.isoformat():
            continue
        token = auth.make_whereabouts_token(p["id"], monday.isoformat())
        link = f"{base}/whereabouts/week?token={quote(token)}"
        subj, body, html = mailer.whereabouts_nudge_message(
            _person_name(conn, p["id"]), label, link)
        if dry_run:
            print(f"[dry-run] whereabouts nudge -> {p['username']} ({label})")
        else:
            res = _send(conn, JOB_FEATURE["whereabouts_nudge"], p["username"], subj, body,
                        html=html)
            if mailer.send_status(res) == "sent":
                st.mark_whereabouts_nudged(conn, p["id"], monday)
        sent += 1
    return sent


def send_whereabouts_rollup(conn, base, dry_run=False):
    """Mid-week (Wednesday by default), tell each chief who among the staff
    they approve for is still undeclared — after the Tuesday nudge has had a
    day to work. Skips a chief with nobody missing; once per chief per week."""
    win = _whereabouts_window(conn, "whereabouts_rollup_weekday")
    if not win:
        return 0
    _today, monday = win
    label = st.whereabouts_week_label(monday)
    link = f"{base}/work-arrangement/day"
    sent = 0
    for chief_id, e in st.whereabouts_rollups(conn, monday).items():
        chief = st.get_admin_user_by_id(conn, chief_id)
        if not chief or not chief.get("username"):
            continue
        subj, body, html = mailer.whereabouts_rollup_message(
            _person_name(conn, chief_id), label, e["missing"], e["total"], link)
        if dry_run:
            print(f"[dry-run] whereabouts roll-up -> {chief['username']} "
                  f"({len(e['missing'])} undeclared)")
        else:
            res = _send(conn, JOB_FEATURE["whereabouts_rollup"], chief["username"], subj,
                        body, html=html)
            if mailer.send_status(res) == "sent":
                st.mark_whereabouts_rollup_sent(conn, chief_id, monday)
        sent += 1
    return sent


def send_approvals_digest(conn, base, dry_run=False):
    """One email per approver bundling EVERY wellness break and work
    arrangement still awaiting their decision — a catch-all in case an
    individual pending-approval notification was missed or lost. Skips an
    approver who has nothing pending; never sent to someone with an empty
    digest.

    Weekly, not daily: the same items stay pending until they're decided, so
    a digest on every run would re-list them every morning and train people
    to ignore it. Gated to one weekday, like the filing nudges below."""
    if tz.today_local().weekday() != _param(conn, "digest_weekday"):
        return 0
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

    wellness_link = f"{base}/approvals#wellness"
    awa_link = f"{base}/approvals#awa"
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
            _send(conn, JOB_FEATURE["digest"], approver["username"], subj, body, html=html)
        sent += 1
    return sent


# Set once the back catalogue has been baselined (see
# storage.baseline_csm_results_emailed). Keyed in app_setting rather than done
# at column-add time, so it is still correct on a database that took the
# columns in an earlier deploy.
_BASELINE_SETTING = "csm_results_baselined"


def _baseline_once(conn, dry_run=False):
    """Before the CSM jobs ever send: stamp everything that concluded BEFORE
    this feature existed, so the first sweep announces nothing retroactively.
    A no-op on every later run."""
    if st.get_setting(conn, _BASELINE_SETTING) == "1":
        return
    delay_days = _param(conn, "csm_results_delay_days")
    if dry_run:
        events = st.list_concluded_events_pending_csm_email(conn, delay_days)
        forms = st.list_concluded_rp_forms_pending_csm_email(conn, delay_days)
        print(f"[dry-run] would baseline {len(events)} past activity/activities and "
              f"{len(forms)} speaker session(s) as already-announced, sending nothing")
        return
    n_events, n_forms = st.baseline_csm_results_emailed(conn, delay_days)
    st.set_setting(conn, _BASELINE_SETTING, "1")
    print(f"Baselined {n_events} past activity/activities and {n_forms} speaker "
          f"session(s) as already-announced (no email sent for the back catalogue).")


def run(db_path="css_is.db", dry_run=False, jobs=None):
    """Run the selected jobs (all of them if `jobs` is None/empty). Returns a
    {job_name: emails_sent} report — empty when there is no CSS_BASE_URL to
    build links with, which is a skip, not a failure."""
    base = _base_url()
    if not base:
        print(_NO_BASE_URL)
        return {}
    jobs = set(jobs) if jobs else set(_ALL_JOBS)
    conn = st.connect(db_path)
    report = {}
    try:
        st.init_db(conn)
        # CLI flags/callers choose which jobs to consider; the admin toggle
        # can only subtract from that set, never add to it. A disabled job
        # is reported as absent, not as 0, so a report can tell "didn't run"
        # apart from "ran, sent nothing".
        disabled = {j for j in jobs if not st.email_feature_enabled(conn, JOB_FEATURE[j])}
        jobs -= disabled
        if dry_run:
            for j in sorted(disabled):
                print(f"{j}: skipped (turned off in /admin/email)")
        _baseline_once(conn, dry_run=dry_run)
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
        if "wellness_file" in jobs:
            report["wellness_file"] = remind_wellness_to_file(conn, base, dry_run=dry_run)
        if "awa_file" in jobs:
            report["awa_file"] = remind_awa_to_file(conn, base, dry_run=dry_run)
        if "whereabouts" in jobs:
            report["whereabouts"] = send_whereabouts_weekly(conn, base, dry_run=dry_run)
        if "whereabouts_nudge" in jobs:
            report["whereabouts_nudge"] = nudge_whereabouts(conn, base, dry_run=dry_run)
        if "whereabouts_rollup" in jobs:
            report["whereabouts_rollup"] = send_whereabouts_rollup(conn, base, dry_run=dry_run)
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
    ap.add_argument("--wellness-file", action="store_true",
                    help="Nudge staff who haven't filed a wellness break this week.")
    ap.add_argument("--awa-file", action="store_true",
                    help="Nudge staff who haven't filed a work arrangement for the open period.")
    ap.add_argument("--whereabouts", action="store_true",
                    help="Email each staff member their week to confirm Office/Field/Leave.")
    ap.add_argument("--whereabouts-nudge", action="store_true",
                    help="Nudge staff who haven't answered the Monday whereabouts email.")
    ap.add_argument("--whereabouts-rollup", action="store_true",
                    help="Tell each chief who in their area hasn't reported their week.")
    args = ap.parse_args()

    jobs = {j for j, flag in (("events", args.events),
                              ("wellness_expiry", args.wellness_expiry),
                              ("digest", args.digest),
                              ("csm_rp", args.csm_rp),
                              ("csm_activity", args.csm_activity),
                              ("wellness_file", args.wellness_file),
                              ("awa_file", args.awa_file),
                              ("whereabouts", args.whereabouts),
                              ("whereabouts_nudge", args.whereabouts_nudge),
                              ("whereabouts_rollup", args.whereabouts_rollup)) if flag}
    # run() treats a missing CSS_BASE_URL as a skip, because the in-process
    # caller must not be killed by it. On the command line it IS a failure:
    # exit non-zero so a cron/Task Scheduler run reports it instead of
    # looking like a quiet night with nothing to send.
    if not _base_url():
        raise SystemExit(_NO_BASE_URL)
    report = run(db_path=args.db, dry_run=args.dry_run, jobs=jobs or None)
    for job, n in report.items():
        print(f"{job}: {n} email(s) {'would be ' if args.dry_run else ''}sent")


if __name__ == "__main__":
    main()
