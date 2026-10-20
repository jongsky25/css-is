# Scanned PDF and page-image reading — A08, third increment

## Protected paths

`documents_ocr.read_pages` and `documents_page_reader.read_image` now send
bounded bytes to a fresh Linux worker. PDFium opening/rendering, Pillow image
decoding, Tesseract, positional deadline recovery and DTRAK subject-cell OCR
all run outside the web process. Native text extraction retains its existing
[separate worker](PDF_READER_LIMITS.md).

Uploaded PDFs and public-link PDFs use this OCR boundary when text is sparse.
Browser-selected pages use the same boundary for image OCR. Selected-page
aggregation remains in the parent and validates bounded text and metadata.
The first-page/DTRAK following-page behavior, suggestions, page evidence,
subject-cell previews and transient intake contract are preserved.

## Limits

| Resource | OCR policy |
|---|---|
| Active OCR jobs | One per application process, shared between PDFs and images; no OCR queue |
| Elapsed time | 45 seconds per OCR invocation, including worker startup and pipe transfer |
| CPU | 35 seconds soft / 36 seconds hard per process |
| Address space | 512 MiB per process, set before image/PDF library imports |
| PDF input | 20 MiB, at most 50 PDF pages, at most 10 requested OCR pages |
| Rasterized page | At most 12 million pixels; 200 dpi reduced for large sheets |
| Browser page input | 2 MiB JPEG/PNG, at most 4 million pixels |
| Extracted text | 100,000 characters per invocation; combined PDF result retains the same cap |
| Worker JSON response | 2 MiB, enforced incrementally by the parent |
| Tesseract stdout | 2 MiB per pass, enforced incrementally inside the worker |
| Tesseract pass | At most 15 seconds for text, 5 seconds for positional TSV, 4 seconds per subject pass |
| DTRAK subject | Existing 8-second budget, also capped by the overall worker deadline |
| Other OS limits | No core dump, zero regular-file output allowance, 32 descriptors |
| Library threads | OpenMP/OpenBLAS limited to one thread |

CPU and address-space limits apply to each process, not to aggregate RSS or
host-wide consumption. The OCR worker starts at most one Tesseract child at a
time. The native parser has its own independent one-worker allowance; it can
run while OCR is occupied. Multiple application processes multiply these
allowances. The shipped Uvicorn command runs one application process.

## Execution and cancellation

The parent launches an absolute shipped script with isolated Python mode,
bytecode writing disabled, a fixed working directory, closed inherited
descriptors, and an environment containing only locale and library-thread
settings. Tesseract is resolved from the standard executable search path and
uses fixed options, stdin/stdout pipes and disabled debug-file output. No
shell, source filename, temporary document or OCR output artifact is used.
Library stderr is discarded. Worker failures expose reviewed messages, never
parser tracebacks or document text from exceptions. Results are bounded JSON,
with text, page keys, subject fields, box coordinates and JPEG preview data
validated before being used by the parent.

The OCR worker and Tesseract share a fresh process group. Async cancellation
and HTTP disconnects set a stop event observed by the parent controller.
The parent requests worker termination briefly to let Tesseract's wrapper
kill/reap its direct child, then kills the whole group, including on worker
crash or excessive output. A stuck native render cannot block that kill.
The parent reaps the worker and, when it is the adopting PID 1, any adopted
group children. If the OS delays worker exit or leaves a live group member,
OCR capacity stays reserved while a background reaper finishes cleanup.
Dead descendants adopted by another init/subreaper are reaped by that owner.
Linux `/proc` group-state inspection is used to distinguish stopped/zombie
members from live work; unreadable group state keeps capacity reserved.

Busy PDF and page-image requests receive HTTP 429, `Retry-After: 3`, no-store
headers and retry/manual-entry guidance. Other errors retain HTTP 400 and
fixed messages. Existing browser feedback retains the entered form values.
An abandoned request does not create a document, job, event or AI interaction.
There is no silent in-process OCR fallback when Linux limits are unavailable.

Each OCR invocation has its own 45-second budget. A DTRAK first-page link can
need a second invocation for a scanned following document, just as it can
need a second native parse. This is not a single total download/read deadline.

## Scope and verification

This is resource and process isolation. It does not create filesystem/network
namespaces, drop the container user, or claim arbitrary-code containment.
Browser PDF.js, public-link fetching, account policies and log privacy are
unchanged. No dependency or database migration is required. All new helper
and worker files are included in the deployment payload.

Synthetic tests cover real OCR accuracy, mixed/native/scanned documents,
10 scanned pages, DTRAK subject previews, actual CPU/address-space/wall limits,
oversized worker and Tesseract output, malformed responses, missing tools,
resource-setup failure, secret/descriptor exclusion, cancellation/disconnect,
stuck rendering, group cleanup after crashes and delayed capacity reuse.
Concurrent HTTP tests cover both PDF/image admission directions, unrelated
page responsiveness and unchanged document/sequence/file/job/event/AI counts.
The full normal/shuffled Python 3.11 suites and dependency gates remain
mandatory. Manual production workflow testing remains deferred; deployment
retains the existing fresh-backup and live-version checks.

Rollback requires a forward versioned release. Returning to older OCR code
would restore image/PDF rendering in the web process.
