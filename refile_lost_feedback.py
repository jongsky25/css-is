#!/usr/bin/env python3
"""
refile_lost_feedback.py -- re-inject the 10 Spot Feedback items lost in the
2026-06-25 revert back into LIVE, via the public /feedback POST.

LOCAL-ONLY one-off. NOT in deploy_hf.py's RUNTIME_PY allowlist, so it never ships.

Constraint: /feedback attributes `submitter` to the logged-in account and stamps
created_at = now. We can't set the original submitter/timestamp remotely (no import
endpoint, and restore only swaps whole bucket snapshots). So we preserve the
original submitter + date in a [RECOVERED ...] prefix in the message body, keep the
original page_url + selector, and post as the .env.local admin account.

Usage:
    python refile_lost_feedback.py            # re-file all items
    python refile_lost_feedback.py --dry-run  # print what would be posted, send nothing
"""
from __future__ import annotations
import argparse, os, sys
import urllib.parse, urllib.request, urllib.error
import pull_backup as pb   # reuse its cookie-jar opener + login

# (orig #, submitter, created PH, page_url, element_selector, message)
LOST = [
    (28, "gbcanoy@doh.gov.ph", "2026-06-23T11:29:56",
     "https://equityinhealth-office-connect.hf.space/reports?type=3",
     "#maincontent > h1",
     "Would it be possible to filter RP Responses by Activity? This would help "
     "users quickly locate and review responses for a specific activity."),
    (29, "caaventurado@doh.gov.ph", "2026-06-24T15:45:34",
     "https://equityinhealth-office-connect.hf.space/",
     "#ongoingFeed",
     "Recent Activities not shown in my home screen. PK Orientation and HRH "
     "Capacity Building on June 24 not shown."),
    (30, "caaventurado@doh.gov.ph", "2026-06-24T15:47:09",
     "https://equityinhealth-office-connect.hf.space/monitor",
     "#maincontent > h1",
     "Activity not shown in my Monitor module"),
    (31, "caaventurado@doh.gov.ph", "2026-06-24T16:07:25",
     "https://equityinhealth-office-connect.hf.space/encode",
     "#maincontent",
     "Concluded events should not be editable"),
    (32, "ray@gmail.com", "2026-06-24T22:41:03",
     "https://equityinhealth-office-connect.hf.space/",
     "ul > li:nth-of-type(2) > div > a > span:nth-of-type(3) > b",
     "archive"),
    (33, "ray@gmail.com", "2026-06-24T22:42:25",
     "https://equityinhealth-office-connect.hf.space/activities/69bf926ac9db/manage#danger",
     "#danger > div > form:nth-of-type(1) > button",
     "when this is clicked, it should not be activated anymore. reports for the "
     "event should be generated too"),
    (34, "ray@gmail.com", "2026-06-24T22:45:56",
     "https://equityinhealth-office-connect.hf.space/activities/42e21444c427/manage",
     "#topic",
     "check the rules set. the activity is supposed to be closed and done but "
     "input fields are still open"),
    (35, "ray@gmail.com", "2026-06-24T22:47:51",
     "https://equityinhealth-office-connect.hf.space/reports/activities?org=&period=all",
     "#curateForm > div:nth-of-type(2)",
     "problem with mobile view. can't see the list of activities"),
    (36, "ray@gmail.com", "2026-06-24T22:50:12",
     "https://equityinhealth-office-connect.hf.space/monitor/69bf926ac9db",
     "#maincontent > div > div:nth-of-type(2) > div:nth-of-type(3) > div",
     "what does it show?"),
    (37, "ray@gmail.com", "2026-06-24T23:02:24",
     "https://equityinhealth-office-connect.hf.space/",
     "ul > li:nth-of-type(1) > div > a > span:nth-of-type(2) > div:nth-of-type(2)",
     "where do i see the reports non bureau organized events?"),
]


def post_feedback(opener, base, page_url, selector, message):
    data = urllib.parse.urlencode({
        "page_url": page_url, "element_selector": selector,
        "region_json": "", "message": message,
    }).encode("utf-8")
    req = urllib.request.Request(base + "/feedback", data=data, method="POST",
                                 headers={"User-Agent": "css-refile",
                                          "Origin": pb.request_origin(base),
                                          "X-Requested-With": "fetch"})
    resp = opener.open(req, timeout=60)
    return resp.status


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("CSS_BASE_URL", pb.DEFAULT_BASE))
    ap.add_argument("--user", default=os.environ.get("CSS_ADMIN_USER"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    base = args.base.rstrip("/")
    user = args.user or input("Admin username/email: ").strip()
    password = os.environ.get("CSS_ADMIN_PASS")
    if not password and sys.stdin.isatty():
        import getpass
        password = getpass.getpass("Admin password: ")
    if not (user and password):
        raise SystemExit("Set CSS_ADMIN_USER / CSS_ADMIN_PASS (or pass --user).")

    opener, _ = pb._opener()
    if not args.dry_run:
        print(f"[refile] signing in to {base} as {user} ...")
        pb.login(opener, base, user, password)

    for n, who, when, url, sel, msg in LOST:
        body = (f"[RECOVERED from 2026-06-25 data-loss — originally Spot "
                f"Feedback #{n} from {who} on {when[:10]} {when[11:19]} PH] {msg}")
        if args.dry_run:
            print(f"\n#{n}  ({who}, {when})  -> {url}\n    {body}")
            continue
        try:
            code = post_feedback(opener, base, url, sel, body)
            print(f"[refile] #{n} ({who}): posted, HTTP {code}")
        except urllib.error.HTTPError as e:
            print(f"[refile] #{n} ({who}): FAILED HTTP {e.code} {e.reason}")
    print("\n[refile] done." if not args.dry_run else "\n[refile] dry-run only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
