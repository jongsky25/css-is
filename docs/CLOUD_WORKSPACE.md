# Cloud workspace commands

Run from the repository root on Linux. No production credentials are required.

```bash
bash scripts/cloud_setup.sh
.venv/bin/python scripts/cloud_workspace.py doctor
.venv/bin/python scripts/cloud_workspace.py test tests/test_auth_rbac.py tests/test_documents_ocr.py tests/test_appearance_browser.py --junitxml=/tmp/office-cloud-results.xml
.venv/bin/python scripts/check_release.py junit /tmp/office-cloud-results.xml
```

Setup creates `.venv` with Python 3.11 (using an installed interpreter or `uv`),
installs the existing hash-verified test lock, checks dependencies, and installs
Playwright Chromium. Node.js 24 and Tesseract with
English data must be installed in the cloud image; missing prerequisites fail
visibly. If browser libraries are missing and package-manager privileges are available,
use `OFFICE_INSTALL_SYSTEM_DEPS=1 bash scripts/cloud_setup.sh`. Managed images may
prohibit su/sudo; use an image with the prerequisites rather than bypassing permissions.
Rerun setup in a fresh workspace; do not copy a virtual environment between machines.
Neither setup nor doctor proves that the complete application regression suite passes.

The doctor checks dependency compatibility, Node's major version, OCR languages,
and an actual headless Chromium page. For the complete suite use:

```bash
.venv/bin/python scripts/cloud_workspace.py test --junitxml=/tmp/office-full.xml --ai-evaluation-report=/tmp/office-ai.json
.venv/bin/python scripts/check_release.py junit /tmp/office-full.xml
.venv/bin/python scripts/ai_evaluation.py check /tmp/office-ai.json
```

CI additionally runs shuffled order (`--shuffle-seed=311`), release metadata,
container/dependency audits, and other gates. These commands do not replace CI.

Large or concurrent suites can fill a small `/tmp` volume with synthetic pytest
databases. Check available space before those runs and place their pytest scratch
data on a larger workspace volume when needed, for example by adding
`--basetemp=/workspace/office-test-tmp/your-run` to the isolated test command.
Reserve a separate path for each concurrent run: pytest removes any existing
contents at its `--basetemp` path. Keep JUnit/evaluation reports outside scratch
directories and preserve them before removing only completed synthetic test data.
Do not count an interrupted disk-full run as passing verification; rerun the
affected command from clean data after restoring capacity.

## Temporary development server

```bash
.venv/bin/python scripts/cloud_workspace.py serve
```

The server listens at `http://127.0.0.1:8000`. Stop with Ctrl-C. It uses a new,
empty temporary database and session key on every invocation. Create only fake
accounts/data; stopping the command deletes its temporary database. Do not add
production integration credentials or settings to this development instance.
Application logs may still be written in the workspace. This is an environment
isolation helper, not a security sandbox or an outbound network firewall.

The wrapper allowlists system/proxy/CA variables, excludes inherited application
and provider credential variables, disables scheduled workers, and sets the same
test clock as CI. Tests retain their own synthetic database fixtures and may
deliberately override these defaults. The wrapper does not load `.env` files.
Infrastructure proxy authentication remains under the platform's control.

Public phone testing and a persistent staging database belong to setup step 4.
This command does not expose a public development server or modify the live app.
