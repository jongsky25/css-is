#!/usr/bin/env python3
"""
feedback.py -- read LIVE Spot Feedback from here, no download
=============================================================

Logs in to the live Space as an admin and fetches the read-only
``/admin/feedback.json`` digest, then prints it so the current feedback can be
reviewed straight from a chat/tool session -- no 21 MB database pull, no manual
"download from /admin/backups" step. It is strictly read-only: it never changes
live data and never deploys.

This is the "check the feedbacks" half of the loop. The other halves stay the
same: edit the code, then ``python deploy_hf.py``.

Usage
-----
    python feedback.py                  # readable digest of all feedback
    python feedback.py --status New     # only one status
    python feedback.py --open           # hide threads already Done/Won't fix
    python feedback.py --json           # raw JSON (for machine reading)

Credentials (first match wins)
------------------------------
    1. CLI flags / env: CSS_BASE_URL, CSS_ADMIN_USER, CSS_ADMIN_PASS
    2. A gitignored ``.env.local`` next to this file, KEY=VALUE per line:
           CSS_ADMIN_USER=you@example.com
           CSS_ADMIN_PASS=your-password
           CSS_BASE_URL=https://equityinhealth-office-connect.hf.space   (optional)
    3. Interactive prompt (only if a terminal is attached)

Storing the password in .env.local is plaintext-on-your-machine -- fine for a
local dev box, and .gitignore keeps it out of the repo. Rotate it if it leaks.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import urllib.parse

# Force UTF-8 stdout: the digest uses → and curly quotes, which crash under
# Windows' default cp1252 codec. (Same guard deploy_hf.py uses.)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Reuse the exact login/session machinery the backup puller already uses, so
# there's one place that knows how to sign in to live.
import pull_backup as pb

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
DONE_STATUSES = {"Done", "Won't fix"}


def _load_env_local():
    """Read KEY=VALUE lines from .env.local into a dict (missing file -> {})."""
    out = {}
    if not os.path.exists(ENV_FILE):
        return out
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _creds(args):
    """Resolve base/user/pass from flags, then env, then .env.local, then prompt."""
    fenv = _load_env_local()

    def pick(flag, *keys):
        if flag:
            return flag
        for k in keys:
            if os.environ.get(k):
                return os.environ[k]
            if fenv.get(k):
                return fenv[k]
        return None

    base = (pick(args.base, "CSS_BASE_URL") or pb.DEFAULT_BASE).rstrip("/")
    user = pick(args.user, "CSS_ADMIN_USER")
    password = pick(None, "CSS_ADMIN_PASS")
    if not user:
        if not sys.stdin.isatty():
            raise SystemExit("No admin user: set CSS_ADMIN_USER in .env.local "
                             "(or pass --user).")
        user = input("Admin username/email: ").strip()
    if not password:
        if not sys.stdin.isatty():
            raise SystemExit("No admin password: set CSS_ADMIN_PASS in .env.local.")
        password = getpass.getpass("Admin password: ")
    return base, user, password


def fetch(base, user, password, status=""):
    """Sign in and return the parsed /admin/feedback.json payload."""
    opener, _ = pb._opener()
    pb.login(opener, base, user, password)
    url = base + "/admin/feedback.json"
    if status:
        url += "?status=" + urllib.parse.quote(status)
    raw = pb._get(opener, url).read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except ValueError:
        raise SystemExit("Live did not return JSON -- the account may lack the "
                         "'triage_feedback' permission, or the endpoint isn't "
                         "deployed yet. First 200 chars:\n" + raw[:200])


def _digest(payload, open_only=False):
    """A compact, readable rundown -- counts on top, then each thread."""
    counts = payload.get("counts", {})
    order = payload.get("statuses", [])
    chips = "  ".join(f"{s}:{counts.get(s, 0)}" for s in order)
    lines = [f"Spot Feedback @ {payload.get('generated_at', '?')}"
             f"   (total {payload.get('total', 0)})",
             "  " + (chips or "no items"), ""]
    for it in payload.get("items", []):
        if open_only and it.get("status") in DONE_STATUSES:
            continue
        head = (f"#{it['id']}  [{it['status']}]  {it.get('submitter') or 'anon'}"
                f"   {it.get('created_at', '')}")
        lines.append(head)
        page = it.get("page_url") or ""
        if page:
            lines.append(f"    page: {page}"
                         + (f"   ({it['element_selector']})"
                            if it.get("element_selector") else ""))
        lines.append("    “" + (it.get("message") or "").strip() + "”")
        if it.get("admin_note"):
            lines.append(f"    note: {it['admin_note'].strip()}")
        for u in it.get("updates", []):
            tag = u.get("status") or u.get("kind") or ""
            reply = (u.get("reply") or "").strip()
            lines.append(f"      → {u.get('ts', '')}  {tag}"
                         + (f": {reply}" if reply else "")
                         + (f"  ({u['actor']})" if u.get("actor") else ""))
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read live Spot Feedback (read-only).")
    ap.add_argument("--base", help="live site root (default: office-connect Space)")
    ap.add_argument("--user", help="admin username/email (or set CSS_ADMIN_USER)")
    ap.add_argument("--status", default="", help="filter to one status, e.g. New")
    ap.add_argument("--open", action="store_true", dest="open_only",
                    help="hide threads already Done / Won't fix")
    ap.add_argument("--json", action="store_true", help="print raw JSON, not a digest")
    args = ap.parse_args(argv)

    base, user, password = _creds(args)
    payload = fetch(base, user, password, status=args.status)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(_digest(payload, open_only=args.open_only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
