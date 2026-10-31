#!/usr/bin/env bash
# Repeatable Linux cloud setup. Never reads production secrets or starts the app.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  if command -v python3.11 >/dev/null; then
    python3.11 -m venv .venv
  elif command -v uv >/dev/null; then
    uv python install 3.11
    uv venv --python 3.11 --seed .venv
  else
    echo 'Python 3.11 or uv is required; install one, then rerun.' >&2
    exit 1
  fi
fi
.venv/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 11), "Use a Python 3.11 .venv; preserve/rename any existing environment first"'
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-test.txt
.venv/bin/python -m pip check
node -e 'if (process.versions.node.split(".")[0] !== "24") process.exit(1)'
tesseract --list-langs | grep -qx eng
# Managed images may supply libraries but prohibit system-package installation.
if [[ "${OFFICE_INSTALL_SYSTEM_DEPS:-0}" == "1" ]]; then
  .venv/bin/python -m playwright install --with-deps chromium
else
  .venv/bin/python -m playwright install chromium
fi
.venv/bin/python scripts/cloud_workspace.py doctor
