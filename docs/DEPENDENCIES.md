# Dependency maintenance — A08, first increment

## Scope and evidence

The application remains FastAPI/Jinja on Python 3.11. This increment locks and
audits Python libraries, release tools and the deployment client, and verifies
the vendored browser PDF.js distribution. It does not change PDF/OCR process
isolation, account setup, login/reset limits, password storage or log privacy.

The earlier default Python 3.12 workspace contained older PDF packages with
reported advisories. That is not a production package inventory. The recorded
Python 3.11 regression environment already used newer PDF packages; a fresh
scan of that recorded set found no known advisories. The candidate pins those
reviewed versions rather than letting subsequent builds choose versions
independently. No advisories are ignored or accepted by this implementation.

Current clean Python 3.11 installation evidence is summarized in
[verification.json](dependencies/verification.json). The complete normal and
shuffled suites and the container dependency gate must pass before promotion.
Manual production workflow testing remains deferred.

## Dependency files

| Inputs | Generated, hash-verified lock | Purpose |
|---|---|---|
| `requirements.in` | `requirements.txt` | Runtime, including pinned pip/setuptools/wheel |
| `requirements-test.in` | `requirements-test.txt` | Same runtime graph plus pytest, PyMuPDF and Playwright |
| `requirements-tools.in` | `requirements-tools.txt` | Isolated uv/pip-audit release tooling |
| `requirements-deploy.in` | `requirements-deploy.txt` | Hugging Face client and its full dependency graph |

`requirements-test.in` constrains shared packages to the runtime lock. Each lock
includes transitive versions and distribution hashes. Resolution retains
platform markers, including Windows-specific packages and the exclusion of
uvloop on Windows. Python 3.11/Linux is the release-tested platform; universal
lock resolution does not establish test coverage for other platforms.

Runtime no longer installs pytest. PyMuPDF/Playwright and their test-only
dependencies are outside the production image. Direct imports such as Pillow,
Starlette and MarkupSafe are explicitly owned in the runtime input.

## Install and update

Use a clean Python 3.11 virtual environment:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements.txt
.venv/bin/python -m pip check
```

For the complete test suite, install `requirements-test.txt` instead, followed
by `python -m playwright install --with-deps chromium` and the system Tesseract
packages. On Windows, use the virtual environment's `Scripts` directory.

To update a direct version, edit the appropriate `.in` file, then regenerate
with the locked tool version in an isolated environment:

```bash
python3.11 -m venv .venv-tools
.venv-tools/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-tools.txt
PATH="$PWD/.venv-tools/bin:$PATH" python scripts/lock_dependencies.py
python scripts/lock_dependencies.py --check
```

Use `--upgrade` on the regeneration command to deliberately refresh transitive
versions. Review every lock diff, audit the selected packages, and run the full
release checks. Do not hand-edit generated hashes or remove a failing advisory
from the report. A changed input or runtime constraint invalidates the relevant
lock fingerprint. Hashes verify distributions; they do not replace review of
the selected upstream releases or protect against a malicious reviewed update.

Docker, the test matrix, audit tooling and deployment installs require hashes
and binary wheels. Missing wheels, hash mismatches and incompatible metadata
fail installation. The deployment client is pinned to 2.2.0, the client version
used by the verified 7.48 deployment.

## Required release gate

The reusable release workflow now requires:

1. Current lock fingerprints, vendor file integrity and release metadata.
2. A container built from the production Docker recipe, with `pip check` and
   an actual installed-package inventory, including packaging tools. The first container run caught the base image
   supplying an unpinned wheel package; it is now explicitly pinned to 0.48.0.
3. A strict PyPI advisory scan of that inventory, exact report coverage, and a
   CycloneDX **Python dependency** SBOM.
4. Clean test, tooling and deployment installs and complete scans of their
   installed inventories. Every runtime image package must match the test
   environment's installed version; additional test packages are permitted.
5. The full normal/shuffled Python 3.11 suites with Chromium/Tesseract and no
   failed or skipped tests.

Audit service failures, unknown/unscanned packages, empty or incomplete
reports, version mismatches and known advisories fail the gate. The deployment
job depends on this gate and retains the existing backup/version checks.
Audit reports, inventories, image identity, lock/Dockerfile hashes and the SBOM
are retained as GitHub artifacts for 14 days, including after failures where
results exist. Repository-admin enforcement of checks before merge remains
the separately documented [release-gate limitation](RELEASE_GATES.md).

The Python SBOM is not an OS or full application-code SBOM. The container base
tag and system packages are not made bit-for-bit reproducible by these Python
locks. A CI-built image is evidence for the checked recipe and commit; it is not
a claim that a separately built production image has the same image ID.

## Vendored browser PDF.js

PDF.js remains at the already vendored **4.10.38**. All 188 vendored distribution
files were compared with the npm tarball after verifying its registry-provided
SHA-512 integrity. The reviewed source, integrity and per-file SHA-256 hashes
are recorded in [the vendor manifest](dependencies/pdfjs-manifest.json).

The metadata gate rejects changed, missing or added vendor files. The dependency
gate queries npm's bulk advisory service for that exact version and retains the
receipt. This checks the actual vendored distribution, without introducing an
npm application build or installing unused optional npm packages. The library
remains self-hosted; evaluation stays disabled and user documents are not sent
to a CDN. Future vendor updates require repeating the upstream integrity/file
comparison and browser/PDF workflow checks before replacing the manifest.

## Parser and OCR increments

Native PDF extraction now has a separate bounded subprocess in the current
[PDF reader increment](PDF_READER_LIMITS.md). The current [OCR worker increment](OCR_WORKER_LIMITS.md) moves PDFium, image
decoding and Tesseract into a separate bounded process group as well. Clean
advisory scans and these process limits do not establish resistance to every
hostile document or provide a full OS sandbox.

## Release tooling update in candidate 7.59

The mandatory dependency gate reported **PYSEC-2026-4321 / GHSA-hq85-5cpj-mr62**
in uv 0.12.23 during this candidate's verification. Its bundled trust store
included a root associated with compromised intermediate CA keys; the advisory
identifies **0.13.4** as the fix. The isolated tools input now pins that version,
and its hashed lock was regenerated with uv 0.13.4. Other package versions in
that lock, the application/test/deployment locks and the Docker image are
unchanged. A local strict audit of all 32 installed tooling packages passed
with complete coverage and no known reported advisories. Full CI evidence is
recorded on PR #364; the earlier verification.json remains historical 7.50
evidence rather than a current advisory claim.


## pypdf patch in v8.22

The release audit reported CVE-2026-115572, CVE-2026-115585 and CVE-2026-115580 in pypdf 6.21.1. The reviewed [6.21.2 release](https://github.com/py-pdf/pypdf/releases/tag/6.21.2) fixes repeated full-file loads and malformed cross-reference table limits. The runtime pin is now 6.21.2; runtime/test lock hashes were regenerated with the locked uv 0.13.4. All other package selections were retained. No advisory is suppressed. PDF reader, intake and OCR checks plus the full release suites verify compatibility.

## Document workload charts — Apache ECharts

The dashboard vendors the unmodified **ECharts 6.1.0** full browser build locally.
Its declared bundled runtime graph includes **zrender 6.1.0** and **tslib 2.3.0**.
All three npm archives were checked against their published SHA-512 integrity;
[the manifest](dependencies/echarts-manifest.json) records provenance and each
shipped file's SHA-256 hash. Apache-2.0, BSD-3-Clause, 0BSD and upstream bundled
D3 notices are retained beside the asset. No Python requirement changes or CDN
requests are introduced.

The vendor gate checks the complete ECharts file set and dependency provenance.
The npm bulk audit submits all three exact packages, fails on any advisory or
unexpected response, and writes a separate `vendor-audit-echarts.json` receipt.
The CI dependency artifact includes that receipt and the ECharts manifest.
Local audits found no reported advisories in the pinned graph; full release CI
must pass before deployment. See [the dashboard guide](DOCUMENT_WORKLOAD_DASHBOARD.md).
