#!/usr/bin/env python3
"""
daily_backup.py -- OFF-SITE daily safety copy of the live prod database.

Runs unattended (Windows Task Scheduler): logs in as admin, takes a fresh live
snapshot, downloads + integrity-checks it into a folder on THIS machine (off the
Hugging Face bucket), rotates to the newest N, and appends one line to a log.

This is the independent, off-HF copy: even a total Hugging Face failure leaves you
with yesterday's database on your own computer. It does NOT touch live data and
does NOT deploy.

LOCAL-ONLY one-off. NOT in deploy_hf.py's RUNTIME_PY allowlist, so it never ships.

Config (env, or .env.local next to this file):
    CSS_ADMIN_USER / CSS_ADMIN_PASS   admin login (required)
    CSS_BASE_URL                      live root (defaults to the office-connect Space)
    CSS_OFFSITE_DIR                   where to save (default: ~/CSS-IS-prod-backups)
    CSS_OFFSITE_KEEP                  how many daily copies to keep (default: 30)
"""
from __future__ import annotations
import os, sys, glob, traceback
from datetime import datetime

import pull_backup as pb   # reuse login / fresh-snapshot / download / verify


def _load_env_local():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.local")
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


def _prune(out_dir, keep):
    files = sorted(glob.glob(os.path.join(out_dir, "css_is_*.db")), reverse=True)
    for old in files[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


def _mirror_to_github(db_path):
    """Encrypt the just-downloaded DB (GPG / AES256) and push it to the PRIVATE GitHub
    backup repo as a flat single-commit history, so the repo never bloats. GitHub only
    ever sees opaque ciphertext; the key (CSS_BACKUP_KEY) stays local. Enabled only when
    CSS_BACKUP_KEY + CSS_GH_BACKUP_DIR (a git repo) are set. Returns the pushed filename
    or None. Raises on failure (caller logs it; the local backup already succeeded)."""
    import subprocess
    key = os.environ.get("CSS_BACKUP_KEY")
    repo = os.environ.get("CSS_GH_BACKUP_DIR")
    keep = int(os.environ.get("CSS_GH_BACKUP_KEEP", "7"))
    if not key or not (repo and os.path.isdir(os.path.join(repo, ".git"))):
        return None                                  # not configured — skip silently
    # Full exe paths: Task Scheduler runs with a minimal PATH where bare 'git'/'gpg'
    # aren't found (FileNotFoundError). CSS_GIT_EXE / CSS_GPG_EXE pin them.
    gpg_exe = os.environ.get("CSS_GPG_EXE", "gpg")
    git_exe = os.environ.get("CSS_GIT_EXE", "git")
    name = os.path.basename(db_path).replace("css_is_", "prod_").replace(".db", "") + ".db.gpg"
    subprocess.run([gpg_exe, "--batch", "--yes", "--pinentry-mode", "loopback",
                    "--passphrase", key, "--symmetric", "--cipher-algo", "AES256",
                    "-o", os.path.join(repo, name), db_path],
                   check=True, capture_output=True)
    for old in sorted(glob.glob(os.path.join(repo, "*.db.gpg")), reverse=True)[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass
    def g(*a):
        subprocess.run([git_exe, "-C", repo, *a], check=True, capture_output=True)
    g("checkout", "--orphan", "_tmp")                # fresh single-commit history each push
    g("add", "-A")
    g("-c", "user.email=backup@local", "-c", "user.name=css-backup",
      "commit", "-m", f"Encrypted CSS-IS backups (rolling) {datetime.now():%Y-%m-%d %H:%M}")
    g("branch", "-M", "main")
    g("push", "-f", "origin", "main")
    return name


def _log(out_dir, msg):
    # Write straight to the log file (NOT via print): under Task Scheduler there is
    # no console, and a separate `print` to a console-less stdout can block.
    line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    try:
        with open(os.path.join(out_dir, "backup_log.txt"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _redirect_output_to_log(out_dir):
    """Point stdout/stderr at the log file. pull_backup prints a progress report to
    stdout; under Task Scheduler that stdout has no reader and a write can BLOCK once
    the pipe buffer fills — which hangs the whole task. A real file sink avoids it."""
    try:
        f = open(os.path.join(out_dir, "backup_log.txt"), "a", encoding="utf-8",
                 buffering=1)
        sys.stdout = f
        sys.stderr = f
    except OSError:
        pass


def main():
    _load_env_local()
    base = (os.environ.get("CSS_BASE_URL") or pb.DEFAULT_BASE).rstrip("/")
    user = os.environ.get("CSS_ADMIN_USER")
    pwd = os.environ.get("CSS_ADMIN_PASS")
    out_dir = os.environ.get("CSS_OFFSITE_DIR") or os.path.expanduser("~/CSS-IS-prod-backups")
    keep = int(os.environ.get("CSS_OFFSITE_KEEP", "30"))
    os.makedirs(out_dir, exist_ok=True)
    _redirect_output_to_log(out_dir)

    if not (user and pwd):
        _log(out_dir, "FAILED: missing CSS_ADMIN_USER / CSS_ADMIN_PASS (set them in .env.local).")
        return 2
    try:
        opener, _ = pb._opener()
        pb.login(opener, base, user, pwd)
        name = pb.make_fresh(opener, base)
        if not name:                       # fall back to newest existing snapshot
            snaps = pb.list_snapshots(opener, base)
            name = snaps[0] if snaps else None
        if not name:
            _log(out_dir, "FAILED: no snapshot available on the live bucket.")
            return 1
        dst = pb.download(opener, base, name, out_dir)
        info = pb.verify(dst)              # raises if corrupt
        _prune(out_dir, keep)
        kept = len(glob.glob(os.path.join(out_dir, "css_is_*.db")))
        _log(out_dir, f"OK: saved {name} ({info}) -> {out_dir} · keeping {kept}/{keep}")
        # Off-site encrypted mirror to the private GitHub repo (best-effort: a push
        # failure must NOT fail the local backup, which is already safely on disk).
        try:
            pushed = _mirror_to_github(dst)
            if pushed:
                _log(out_dir, f"OK: pushed encrypted {pushed} to GitHub backup repo")
        except Exception as e:                       # noqa: BLE001
            _log(out_dir, f"WARN: GitHub mirror failed ({e!r}); local backup is fine")
        return 0
    except SystemExit as e:               # verify() integrity failure
        _log(out_dir, f"FAILED integrity check: {e}")
        return 1
    except Exception as e:                # noqa: BLE001
        _log(out_dir, f"FAILED: {e!r}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
