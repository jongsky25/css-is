# Native PDF reading limits — A08, second increment

## Protected path

Native text extraction for `/documents/intake/read` now executes in a fresh
Linux subprocess instead of parsing untrusted PDF structures in a web-process
thread. Uploaded bytes and downloaded public-link PDFs use the same boundary.
The download's existing public-IP pinning, redirect checks and size/deadline
policy are unchanged. No extra runtime library is introduced.

The parent still prepares suggestions and evidence from bounded text. Sparse
pages still use the existing OCR path. A first-page link reads the following
document only when the first page is a DTRAK slip, including when OCR identified
that slip. Each native parse has its own deadline, so that exceptional second
page can require a second bounded parse. Ordinary links remain first-page only.

## Limits

| Resource | Native worker limit |
|---|---|
| Active parsers | One per application process; no parser queue |
| Elapsed time | 15 seconds per native parse, including pipe transfer |
| CPU time | 5 seconds soft / 6 seconds hard |
| Address space | 256 MiB, set before importing pypdf |
| Input | 20 MiB maximum, signature checked before spawn and in the child |
| PDF pages | 50 maximum |
| Extracted native text | 100,000 characters |
| Result pipe | 1 MiB maximum, read incrementally |
| Other OS limits | No core dump, zero regular-file output allowance, 32 descriptors |

Address space is not an RSS measurement. These limits are fixed policy
constants, not fields a submitted PDF or request can change. Multiple Uvicorn
application processes each have their own one-parser allowance; this is not a
host-wide distributed admission limit. The shipped command runs one worker.

The child receives PDF bytes over stdin and returns bounded JSON. It starts
with isolated Python mode, bytecode writing disabled, a fixed working directory,
closed inherited descriptors and a small locale-only environment. It does not
receive account cookies, provider/session secrets or open database handles.
The worker never imports the application, OCR modules or database code. No
source PDFs, extracted text or parser tracebacks are written to diagnostic logs
or temporary files by this path. Parser stderr is discarded, and only fixed
error codes cross the response boundary.

This is resource/process isolation, not a complete OS sandbox for arbitrary
code execution. It does not create a network or filesystem namespace or change
the container's user. Stronger hostile-code confinement remains separate.

## Failures and cancellation

Busy requests fail promptly with HTTP 429, a short Retry-After value and a
plain-language retry/manual-entry message. They do not start another parser.
Other validation, timeout, memory/CPU and parser failures keep the existing
HTTP 400 JSON error contract and no-store response policy. Existing frontend
handling retains entered form values and requires an explicit retry.

On deadline, cancellation, excessive output or a crash, the parent terminates
the child if needed, closes the pipes and reaps it before reusing capacity.
If the OS delays reaping, capacity stays reserved until a background reaper
confirms exit; no replacement parser is admitted in the meantime. Disconnects
and cancellation of the async request set the native worker's stop event.
No abandoned task writes a document, job, audit event or AI interaction.

Protected native parsing fails closed when Linux/resource-limit support is
unavailable. There is no silent in-process fallback. Local non-Linux users can
use the existing browser-selected-page workflow or manual entry, or run the
Linux deployment environment.

## Deliberate remaining boundary

PDFium rendering, Tesseract and the existing OCR thread path are **not moved**
in this increment. Their current lock, size and timeout controls remain.
Cancellation during OCR is observed when that existing call returns; it cannot
forcibly stop an in-process PDFium render. A scanned document can therefore
still enter that older boundary after native parsing. OCR rendering/process
isolation is the next separate increment. Browser PDF.js processing and public
link download/DNS behavior are also unchanged.

## Verification and rollout

Tests exercise actual Linux subprocesses and actual resource limits: elapsed
timeout, CPU exhaustion, memory exhaustion, oversized result output, malformed
JSON, crashes, secret/descriptor exclusion, cancellation and delayed reaping.
Each failure path is followed by a successful normal read where applicable.
A compressed PDF exercises the extracted-text limit; valid 50-page and exact
20 MiB documents retain support. Native/scanned DTRAK first-page behavior and
the existing real OCR integration are covered.

A concurrent HTTP test confirms an unrelated authenticated page remains
available while a native parser is occupied, another PDF request receives 429,
and the existing document/job/event/AI tables remain unchanged. Synthetic data
is used throughout; manual production workflow testing remains deferred.

Both worker files are included in the Hugging Face runtime payload. No schema
or dependency migration is needed. The complete normal/shuffled Python 3.11
suites and dependency gates remain mandatory. Deployment still requires the
existing backup and live-version checks. Roll back through a forward release
only if necessary, recognizing that an older build restores in-process parsing.
