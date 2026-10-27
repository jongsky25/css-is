# Exact Python image repair after first hosted setup failure

PR #511's first hosted attempt, workflow 3664c4a / diagnostic c76ae40, installed
the exact browser/locked dependencies and passed all 33 preflight tests. It stopped
before measurement: the inherited image digest contained Python 3.12.15, while
the frozen local/native runtime contract is 3.12.14. No controls were captured.
Artifact 12733976306 preserves all sixteen files and verifies twelve internal
hashes plus the upload ZIP digest. Do not rerun that unchanged image or weaken the
runtime check. No measurement/qualification failure is being replaced.

Replace only the workflow container with:
python:3.12.14-trixie@sha256:4d1caded1f729ae443eb803f26ffde7b61e696aeaef62f099abb6dd6b14257c7

Read-only offline command on that downloaded immutable image reports exactly
Python 3.12.14 and x86_64. Keep diagnostic checkout c76ae40, fixtures, dependencies,
all four fixed controls and capture/checker policies unchanged. Freeze the new
workflow before the PR event triggers this distinct corrected setup attempt.
Preserve all subsequent failures and results; no automatic retries or qualification.
