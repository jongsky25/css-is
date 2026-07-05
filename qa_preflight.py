#!/usr/bin/env python3
"""
qa_preflight.py — the integrity GATE. Run this FIRST, before any functional QA,
and fail the whole run if it does not pass.

Why this exists
---------------
The 2026-06-10 QA pass discovered the delivered build would not even start:
app.py and templates/activities.html had been silently TRUNCATED by an editor
that drops overflow on large files. No functional test matters if the app can't
import. This gate catches truncation/corruption in seconds so an unattended run
never wastes time testing a dead build — and never SHIPS one.

What it checks (all of it, then reports)
  1. Every *.py compiles (ast.parse).
  2. Key modules import in a clean subprocess (catches import-time errors).
  3. Every template parses in the app's Jinja env (custom filters registered).
  4. Truncation sweep: source files must end in a newline and must not end on an
     obviously-incomplete line (open bracket/quote, dangling '{%' without '%}').
  5. Size regression: compare line counts to the newest _backups/* copy (if any)
     and flag any file that shrank by more than SHRINK_PCT — the truncation
     signature.

Exit code 0 = green (safe to proceed). Non-zero = STOP and fix before testing.
Usage:  python qa_preflight.py            (checks the current folder)
"""
from __future__ import annotations
import ast, os, subprocess, sys, glob, re

ROOT = os.path.dirname(os.path.abspath(__file__))
KEY_MODULES = ["app", "storage", "auth", "css_is_engine",
               "dashboard_insights", "dashboard_export", "migrate", "harmonize"]
SHRINK_PCT = 0.10          # flag a file that lost >10% of its lines vs backup
SKIP_DIRS = {"_backups", "__pycache__", ".git", "tests"}

fails, warns = [], []

def _py_files():
    return sorted(glob.glob(os.path.join(ROOT, "*.py")))

def check_compile():
    for f in _py_files():
        src = open(f, encoding="utf-8", errors="replace").read()
        try:
            ast.parse(src)
        except SyntaxError as e:
            fails.append(f"COMPILE {os.path.basename(f)}:{e.lineno}: {e.msg}")

def check_imports():
    # import each key module in a subprocess so one bad module can't poison others
    for m in KEY_MODULES:
        if not os.path.exists(os.path.join(ROOT, m + ".py")):
            continue
        r = subprocess.run([sys.executable, "-c", f"import {m}"],
                           cwd=ROOT, capture_output=True, text=True,
                           env={**os.environ, "PYTHONPYCACHEPREFIX": "/tmp/qa_pc"})
        if r.returncode != 0:
            last = (r.stderr.strip().splitlines() or ["<no stderr>"])[-1]
            fails.append(f"IMPORT {m}: {last}")

def check_templates():
    tdir = os.path.join(ROOT, "templates")
    if not os.path.isdir(tdir):
        return
    code = (
        "import app, os; env=app.templates.env; bad=[]\n"
        "for fn in sorted(os.listdir('templates')):\n"
        "    if fn.endswith('.html'):\n"
        "        try: env.get_template(fn)\n"
        "        except Exception as e: bad.append(fn+': '+str(e).splitlines()[0])\n"
        "print('\\n'.join(bad))\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPYCACHEPREFIX": "/tmp/qa_pc"})
    if r.returncode != 0:
        fails.append(f"TEMPLATES could not be checked (app import failed): "
                     f"{(r.stderr.strip().splitlines() or [''])[-1]}")
    for line in r.stdout.strip().splitlines():
        if line.strip():
            fails.append("TEMPLATE " + line)

_OPEN_END = re.compile(r"[\(\[\{,]\s*$")           # line ends mid-expression
def check_truncation():
    targets = list(_py_files()) + glob.glob(os.path.join(ROOT, "templates", "*.html"))
    for f in targets:
        data = open(f, encoding="utf-8", errors="replace").read()
        if not data:
            continue
        if not data.endswith("\n"):
            fails.append(f"NO-TRAILING-NEWLINE {os.path.relpath(f, ROOT)} "
                         f"(classic truncation signature)")
        last = data.rstrip("\n").splitlines()[-1] if data.strip() else ""
        # dangling jinja tag e.g. '{% en'  (open without closing %})
        if "{%" in last and "%}" not in last.split("{%")[-1]:
            fails.append(f"DANGLING-JINJA {os.path.relpath(f, ROOT)}: ...{last[-40:]!r}")
        if f.endswith(".py") and _OPEN_END.search(last):
            warns.append(f"line ends mid-expression in {os.path.basename(f)}: {last[-40:]!r}")

def _newest_backup_dir():
    cands = [d for d in glob.glob(os.path.join(ROOT, "_backups", "*")) if os.path.isdir(d)]
    return max(cands, key=os.path.getmtime) if cands else None

def check_size_regression():
    bk = _newest_backup_dir()
    if not bk:
        warns.append("no _backups/* dir to compare sizes against")
        return
    for f in _py_files() + glob.glob(os.path.join(ROOT, "templates", "*.html")):
        rel = os.path.relpath(f, ROOT)
        # match by basename in the backup (orig copies may carry a .orig suffix)
        base = os.path.basename(f)
        for cand in (os.path.join(bk, rel), os.path.join(bk, base),
                     os.path.join(bk, base + ".orig"),
                     os.path.join(bk, "templates", base + ".orig")):
            if os.path.exists(cand):
                now = sum(1 for _ in open(f, errors="replace"))
                was = sum(1 for _ in open(cand, errors="replace"))
                if was and now < was * (1 - SHRINK_PCT):
                    warns.append(f"{rel} shrank {was}->{now} lines vs backup "
                                 f"({bk.split(os.sep)[-1]}) — verify it's intentional")
                break

def main():
    check_compile()
    if not [x for x in fails if x.startswith("COMPILE")]:
        check_imports()
        check_templates()
    check_truncation()
    check_size_regression()

    print(f"=== qa_preflight: {len(fails)} failure(s), {len(warns)} warning(s) ===")
    for w in warns: print("  WARN:", w)
    for x in fails: print("  FAIL:", x)
    if fails:
        print("RESULT: RED — do not run functional QA or ship until these are fixed.")
        sys.exit(1)
    print("RESULT: GREEN — build is importable and intact; proceed to functional QA.")
    sys.exit(0)

if __name__ == "__main__":
    main()
