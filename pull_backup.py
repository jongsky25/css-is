#!/usr/bin/env python3
"""
pull_backup.py -- pull the LIVE database into your local environment
====================================================================

A safety net, on demand. This logs in to the live Space as an admin, asks it to
take a fresh snapshot, downloads the newest one, checks it opens cleanly, and
saves it under ``_backups/pulled/`` (gitignored). It is read-only with respect
to live: it never changes live data and never deploys code -- it only copies a
snapshot down to your machine.

Why this exists: a restart once reverted live data, and the only clean copies
were the snapshots someone happened to have downloaded. Run this whenever you
want a local copy you can trust -- e.g. right before a deploy, or after a busy
day of edits. The hardened boot path (v1.55) makes a silent revert far less
likely, but a local copy is the belt to that braces.

Usage
-----
    python pull_backup.py                 # fresh snapshot, then download newest
    python pull_backup.py --no-fresh      # just download the newest EXISTING snapshot
    python pull_backup.py --list          # only list what's on the live bucket
    python pull_backup.py --out DIR       # save somewhere other than _backups/pulled
    python pull_backup.py --seed          # ALSO copy the pulled DB over the local css_is.db
                                          #   (so a local `uvicorn` run shows live data)

Config (environment variables; CLI flags override)
--------------------------------------------------
    CSS_BASE_URL     live site root   (default: the office-connect Space)
    CSS_ADMIN_USER   admin username / email
    CSS_ADMIN_PASS   admin password   (if unset and a terminal is attached,
                                       you'll be prompted without echo)
"""

from __future__ import annotations

import argparse
import getpass
import http.cookiejar
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://equityinhealth-office-connect.hf.space"
SNAP_RE = re.compile(r"css_is_\d{8}_\d{6}_(?:manual|auto|pre_restore)\.db")


def _opener():
    """A urllib opener that keeps cookies (so the login session carries over)."""
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def _post(opener, url, fields, follow=True):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"User-Agent": "css-pull-backup"})
    if follow:
        return opener.open(req, timeout=60)
    # Manual no-follow so we can read the redirect Location.
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    no = urllib.request.build_opener(_NoRedirect,
                                     *[h for h in opener.handlers
                                       if isinstance(h, urllib.request.HTTPCookieProcessor)])
    try:
        return no.open(req, timeout=60)
    except urllib.error.HTTPError as e:
        return e          # 3xx surfaces here with .headers["Location"]


def _get(opener, url):
    req = urllib.request.Request(url, headers={"User-Agent": "css-pull-backup"})
    return opener.open(req, timeout=120)


def login(opener, base, user, password):
    """Sign in; raise a clear error if the credentials are rejected."""
    url = base + "/login"
    try:
        resp = _post(opener, url, {"username": user, "password": password,
                                   "next": "/admin/backups"})
    except urllib.error.HTTPError as e:
        # A wrong password / inactive account renders the login page with a 401
        # (or 400 on first-run validation), which urllib raises rather than
        # returns. That IS the rejection signal.
        if e.code in (400, 401):
            raise SystemExit("Login rejected: wrong username/password, or the "
                             "account is inactive.")
        raise
    body = resp.read().decode("utf-8", "replace")
    final = resp.geturl()
    # On success we land on /admin/backups; on failure we're bounced to the login
    # form (which still contains a password field) or to /reset-password.
    if "/reset-password" in final:
        raise SystemExit("This account is on a temporary password -- set a real "
                         "one in the app first, then re-run.")
    if final.endswith("/login") or 'name="password"' in body:
        raise SystemExit("Login rejected: wrong username/password, or the account "
                         "is inactive.")


def list_snapshots(opener, base):
    """Newest-first list of snapshot filenames the live bucket currently holds."""
    body = _get(opener, base + "/admin/backups").read().decode("utf-8", "replace")
    names = sorted(set(SNAP_RE.findall(body)), reverse=True)   # names sort chronologically
    return names


def make_fresh(opener, base):
    """Trigger 'Back up now' on live; return the new snapshot's name (or None)."""
    resp = _post(opener, base + "/admin/backups/now", {}, follow=False)
    loc = resp.headers.get("Location", "") if hasattr(resp, "headers") else ""
    m = SNAP_RE.search(urllib.parse.unquote(loc))
    return m.group(0) if m else None


def download(opener, base, name, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    url = base + "/admin/backups/download?name=" + urllib.parse.quote(name)
    dst = os.path.join(out_dir, name)
    with _get(opener, url) as resp, open(dst, "wb") as f:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    return dst


# (table, label, optional recency column) -- the things we care to see arrived.
# Recency column is used to print the newest timestamp so you can confirm the
# pull is current, not stale.
_CHECK_TABLES = [
    ("admin_user", "user accounts", "created_at"),
    ("response", "survey responses", "submitted_at"),
    ("spot_feedback", "spot feedback", "created_at"),
    ("feedback_update", "feedback updates", None),
    ("event", "events/activities", "created_at"),
    ("attendee", "attendees", None),
    ("resource_person", "resource persons", None),
    ("external_organizer", "external organizers", None),
    ("answer", "answers", None),
    ("item_remark", "written comments", None),
    ("audit_log", "audit-log entries", "ts"),
    ("app_setting", "settings", None),
]


def verify(path):
    """Open the pulled DB, run an integrity check, and print a per-table report
    so you can confirm users, feedback, events, etc. all came down -- not just
    response counts. Raises if the file is corrupt or the schema is unexpected."""
    c = sqlite3.connect(path)
    try:
        qc = c.execute("PRAGMA quick_check").fetchone()[0]
        if qc != "ok":
            raise SystemExit(f"Integrity check FAILED on {path}: {qc}")
        have = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        print("[pull] contents:")
        for table, label, recency in _CHECK_TABLES:
            if table not in have:
                print(f"        {label:<20} (table missing!)")
                continue
            n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            when = ""
            if recency:
                mx = c.execute(f"SELECT MAX({recency}) FROM {table}").fetchone()[0]
                when = f"   newest {mx}" if mx else "   (none)"
            print(f"        {label:<20} {n:>7,}{when}")
        # Active vs inactive accounts -- a quick sanity check on the user list.
        act = c.execute("SELECT COUNT(*) FROM admin_user WHERE active=1").fetchone()[0]
        tot = c.execute("SELECT COUNT(*) FROM admin_user").fetchone()[0]
        print(f"        ({act} of {tot} accounts active)")
    finally:
        c.close()
    size_mb = os.path.getsize(path) / 1e6
    return f"OK, {size_mb:.1f} MB"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pull the live CSS-IS database locally.")
    ap.add_argument("--base", default=os.environ.get("CSS_BASE_URL", DEFAULT_BASE),
                    help="live site root URL")
    ap.add_argument("--user", default=os.environ.get("CSS_ADMIN_USER"),
                    help="admin username/email (or set CSS_ADMIN_USER)")
    ap.add_argument("--out", default=os.path.join("_backups", "pulled"),
                    help="directory to save the pulled snapshot into")
    ap.add_argument("--no-fresh", action="store_true",
                    help="download the newest EXISTING snapshot; don't take a new one")
    ap.add_argument("--list", action="store_true",
                    help="only list the snapshots on the live bucket, then exit")
    ap.add_argument("--seed", action="store_true",
                    help="also copy the pulled DB over the local css_is.db")
    args = ap.parse_args(argv)

    base = args.base.rstrip("/")
    user = args.user or input("Admin username/email: ").strip()
    password = os.environ.get("CSS_ADMIN_PASS")
    if not password:
        if not sys.stdin.isatty():
            raise SystemExit("Set CSS_ADMIN_PASS (no terminal to prompt on).")
        password = getpass.getpass("Admin password: ")

    opener, _ = _opener()
    print(f"[pull] signing in to {base} as {user} ...")
    login(opener, base, user, password)

    if args.list:
        for n in list_snapshots(opener, base):
            print("  " + n)
        return 0

    name = None
    if not args.no_fresh:
        print("[pull] asking live to take a fresh snapshot ...")
        name = make_fresh(opener, base)
        if name:
            print(f"[pull] live created {name}")
        else:
            print("[pull] couldn't confirm the new snapshot name; using newest listed.")
    if not name:
        snaps = list_snapshots(opener, base)
        if not snaps:
            raise SystemExit("No snapshots found on the live bucket.")
        name = snaps[0]

    print(f"[pull] downloading {name} -> {args.out} ...")
    dst = download(opener, base, name, args.out)
    print(f"[pull] saved {dst}")
    print(f"[pull] verified: {verify(dst)}")

    if args.seed:
        import shutil
        shutil.copy2(dst, "css_is.db")
        print("[pull] copied over local css_is.db -- a local run now shows live data.")
    print("[pull] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
