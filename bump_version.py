#!/usr/bin/env python3
"""Bump APP_VERSION + prepend the changelog entries — the mobile deploy's helper.

The GitHub "Deploy to Hugging Face" workflow runs this so a phone deploy never
has to hand-edit Python. It:

  1. Reads the current APP_VERSION from version.py.
  2. Computes the next version (minor: 1.82 -> 1.83; major: 1.82 -> 2.0).
  3. Rewrites the APP_VERSION line.
  4. Prepends a new entry to the top of the CHANGELOG list in version.py
     (this is what the login "What's new" screen shows).
  5. Prepends a one-line dated entry to CHANGELOG.md (the technical log).

It edits files in place and prints the new version. Run locally to preview:

    python bump_version.py --bump minor --summary "Fixed the export button."

Nothing here talks to Hugging Face — deploy_hf.py still does the shipping. The
version.py edits it makes are exactly what deploy_hf.py's strict-version gate
needs, so after this runs the deploy proceeds without a manual bump.
"""
import argparse
import datetime
import json
import re
import sys

VERSION_PY = "version.py"
CHANGELOG_MD = "CHANGELOG.md"

APP_VERSION_RE = re.compile(r'^(APP_VERSION\s*=\s*)["\']([^"\']+)["\']', re.MULTILINE)
CHANGELOG_LIST_RE = re.compile(r'(CHANGELOG\s*=\s*\[\n)')


def next_version(cur, bump):
    """1.82 --minor-> 1.83 ; 1.82 --major-> 2.0. Two-part major.minor only."""
    parts = cur.split(".")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        sys.exit(f"ABORT — APP_VERSION {cur!r} is not the expected 'major.minor' form.")
    major, minor = int(parts[0]), int(parts[1])
    if bump == "major":
        return f"{major + 1}.0"
    return f"{major}.{minor + 1}"


def bump_version_py(text, new_version, summary, spelled_date):
    """Swap APP_VERSION and insert a CHANGELOG entry matching the file's style."""
    text, n = APP_VERSION_RE.subn(lambda m: f'{m.group(1)}"{new_version}"', text, count=1)
    if n != 1:
        sys.exit("ABORT — could not find the APP_VERSION line in version.py.")

    # json.dumps yields a safely-escaped double-quoted literal that is also valid
    # Python source, so an apostrophe/quote/backslash in the summary can't break it.
    s = json.dumps(summary)
    entry = (
        "    {\n"
        f'        "version": "{new_version}",\n'
        f'        "date": "{spelled_date}",\n'
        f"        \"summary\": {s},\n"
        "        \"changes\": [\n"
        f"            {s},\n"
        "        ],\n"
        "    },\n"
    )
    text, n = CHANGELOG_LIST_RE.subn(lambda m: m.group(1) + entry, text, count=1)
    if n != 1:
        sys.exit("ABORT — could not find the 'CHANGELOG = [' list in version.py.")
    return text


def bump_changelog_md(text, new_version, summary, iso_date):
    """Prepend a '## <date> (v<n> — <summary>)' heading under the title line."""
    line = f"## {iso_date} (v{new_version} — {summary})\n\n"
    lines = text.split("\n", 1)
    if lines and lines[0].startswith("# "):
        rest = lines[1] if len(lines) > 1 else ""
        # keep the blank line the title is followed by, then our heading
        rest = rest.lstrip("\n")
        return f"{lines[0]}\n\n{line}{rest}"
    # no recognizable title — just prepend
    return line + text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bump", choices=("minor", "major"), default="minor")
    ap.add_argument("--summary", required=True,
                    help="One-line, plain-language description of the change.")
    ap.add_argument("--date", default=None,
                    help="Override today's date (ISO, e.g. 2026-07-05); for tests.")
    ap.add_argument("--github-output", default=None,
                    help="Path to append 'new_version=…' (GitHub Actions $GITHUB_OUTPUT).")
    args = ap.parse_args()

    summary = " ".join(args.summary.split()).strip()
    if not summary:
        sys.exit("ABORT — --summary is empty.")

    if args.date:
        d = datetime.date.fromisoformat(args.date)
    else:
        d = datetime.date.today()
    spelled_date = f"{d:%B} {d.day}, {d.year}"   # July 5, 2026
    iso_date = d.isoformat()                      # 2026-07-05

    with open(VERSION_PY, encoding="utf-8") as f:
        vtext = f.read()
    cur = APP_VERSION_RE.search(vtext)
    if not cur:
        sys.exit("ABORT — could not read the current APP_VERSION from version.py.")
    new_version = next_version(cur.group(2), args.bump)

    vtext = bump_version_py(vtext, new_version, summary, spelled_date)
    with open(VERSION_PY, "w", encoding="utf-8") as f:
        f.write(vtext)

    try:
        with open(CHANGELOG_MD, encoding="utf-8") as f:
            ctext = f.read()
        ctext = bump_changelog_md(ctext, new_version, summary, iso_date)
        with open(CHANGELOG_MD, "w", encoding="utf-8") as f:
            f.write(ctext)
    except FileNotFoundError:
        print(f"ℹ️  {CHANGELOG_MD} not found; skipped (version.py was still bumped).")

    print(f"Bumped {cur.group(2)} -> {new_version} ({args.bump}): {summary}")

    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(f"new_version={new_version}\n")


if __name__ == "__main__":
    main()
