#!/usr/bin/env bash
# CSS-IS regression suite runner. Runs the pytest HTTP/RBAC/abuse/integrity
# tests, then the data+export smoke. Usage: bash run_tests.sh
set -e
cd "$(dirname "$0")"
export PYTHONPYCACHEPREFIX=/tmp/pycache
echo "== pytest =="
python3 -m pytest
echo "== qa_smoke =="
python3 qa_smoke.py
