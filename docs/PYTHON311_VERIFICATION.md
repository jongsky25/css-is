# Python 3.11 verification — A10 step 3

## Scope

Verified application source is release **7.35**, commit
`0f06eed42623fda3bfb981454aead07472b78375`. The Dockerfile uses
`python:3.11-slim`; this check runs CPython **3.11.17** in an isolated virtual
environment with dependencies freshly resolved from `requirements.txt`.
The normal and shuffled runs use separate detached source checkouts, synthetic
test databases, and the controlled application clock introduced in 7.35.

This verifies the Python minor version used by production. It does not establish
parity with the exact live image, operating-system packages, or production data.
No manual production testing was performed.

## Reproduction

```bash
python3.11 -m venv .venv311
.venv311/bin/python -m pip install -r requirements-test.txt
.venv311/bin/python -m pip check
.venv311/bin/python -m pytest --tb=short --junitxml=python311-normal.xml
.venv311/bin/python -m pytest --shuffle-seed=311 --tb=short \
  --junitxml=python311-shuffled.xml
```

For the exact dependency versions used in this verification, install
`docs/phase1/python311/resolved-requirements.txt` instead. This file is an evidence
snapshot, not a change to the production dependency policy. Node.js was available
for the JavaScript contract tests. The runtime and result details are recorded in
`docs/phase1/python311/verification.json`.

## Results

| Run | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Normal order | 4,195 | 0 | 16 |
| Shuffled, seed 311 | 4,195 | 0 | 16 |

Both processes exited successfully. Dependency consistency checks passed. The
16 skips in each run are the existing Chromium-dependent browser tests. No
application compatibility fixes were needed. Two non-failing warnings concern
Starlette’s httpx TestClient integration and PyMuPDF’s `fitz` import alias.

## Clean-install finding

Installing only `requirements.txt` initially prevented test collection:
`tests/test_csm_official.py` imports `fitz`, supplied by PyMuPDF, which was not
declared. `requirements-test.txt` now includes the runtime requirements,
PyMuPDF, and Playwright. This makes the suite's additional Python dependencies
explicit without adding PDF-test tooling to the production image.

Browser binaries are a separate prerequisite:
`python -m playwright install chromium`. The existing browser tests retain their
explicit skip behavior when Chromium is unavailable.

## Limits and next step

Two successful orders do not establish correctness for every possible ordering
or date. Dependencies remain largely unpinned in production; a later fresh
resolution can differ from this recorded environment. Mandatory CI and deployment
gates are the next A10 increment.

## Release integration — 7.39

Preserved main's 7.36–7.38 travel changes and bumped the application and service-worker cache to 7.39. The combined source passed the full Python 3.11 suite with seed 739: **4,196 passed, zero failures, 18 existing Chromium-dependent skips**. The original 7.35 verification remains above as historical evidence; the integration result and source commit are in `verification.json`.
