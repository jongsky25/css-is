# A18 — survey guidance and recovery (7.90)

This is the first A18 increment: public Type 1 CSM, Type 2 activity, Type 3 speaker and combined-speaker forms. Reporting scope, dates, sample sizes, exports and reconciliation against the corrected analytics reference dataset remain the next increment.

## What changes

- Touch controls for ratings, N/A, notes, comment chips, skip controls and question navigation have larger targets. Citizen's Charter groups and comments have explicit accessible labels; chips expose their selected state.
- A focused correction summary links to the actual invalid control, including a question hidden in one-question mode. Current answers remain in place. Question navigation moves focus deliberately and rating selection no longer advances automatically.
- Device draft messages distinguish a local copy from a server-confirmed response. Storage failures explain that the page must remain open; they do not display a new successful-save message. English and Filipino messages and answer progress are supported.
- A registered attendee's validated credential scopes the device draft separately from another attendee using the same survey. Anonymous draft keys retain the existing format and resume stays an explicit choice.
- A submit event flushes the current draft instead of deleting it. The thanks page removes only the matching key and revision; an older confirmation cannot erase newer edits. Window-closed pages and unsuccessful combined completion pages can expose a read-only local copy for copying.
- Duplicate clicks are blocked while the current page is submitting or saving offline. Returning through browser history restores the controls and explains that the prior request may already have been recorded.
- A named speaker skip control is honoured by the server as well as by JavaScript. A combined result reports the actual number recorded, distinguishes zero and unavailable forms, and warns against resending an entire partially processed set.
- A registered attendee sees “all done” only when the existing activity-completion check passes. One recorded form does not imply all activity feedback is finished. Existing certificate/ending-message gates remain in force.

## Offline confirmation and saved copies

The page and Background Sync request a JSON receipt. A queued request is removed only after the response says `ok: true` and echoes that request's existing `submission_id`. A 200 HTML page, malformed JSON, mismatched identifier, network failure or 5xx keeps the request pending. A 4xx retains its payload for review and no longer assumes that every refusal means a closed survey.

Confirmed partial/zero combined results are kept for review. The existing ledger stores only an identifier and timestamp, so a replayed combined request cannot reconstruct the original per-form outcome; its saved copy is retained with a review message. Neither queue consumer invents a successful per-speaker count. Failed/review payloads expose an escaped, readable copy and an explicit discard action; credentials and transport fields are omitted from the displayed copy. The badge is scrollable and its controls have usable touch targets.

The existing queue database/version, submission identifiers and server replay checks are retained. These changes do not make the existing response writes and submission ledger one atomic cross-process transaction. Crash recovery, concurrent multi-worker reconciliation and durable per-form receipts remain later operations work. Ordinary online anonymous submissions still carry no queue identifier, so a deliberate new response on a shared device remains possible; this increment does not claim global exactly-once submission.

Background Sync notifies open pages to clear a matching local draft. With all pages closed, a successfully sent draft copy may remain until the person returns. Resume therefore does not claim that the copy is unsent and asks the person to check whether the feedback was already submitted. Draft expiry is checked on access after seven days, rather than promising deletion while the browser is closed. Queue copies remain until confirmation or explicit discard. Device storage is not an encrypted private vault; the form explains that others using the device may see drafts.

## Boundaries

Official wording, rating values, N/A handling, optional CSM demographics, Citizen's Charter skip mapping and server sanitization/scoring remain unchanged. The client uses the existing control constraints; it does not introduce a new server policy rejecting sparse/incomplete ratings. Existing feature, window, signed-attendee, same-origin, report-access and registration gates remain independent of the new guidance. Successful native online submissions retain their rich thanks/certificate flow; JSON receipts are negotiated by queue consumers. No schema migration, new provider, dependency or runtime module is added.

## Verification

- Broad local survey/registration regression: **186 passed with no skips**, before one additional activity-completion test.
- Final focused server/browser/worker/CSM journeys: **33 passed with no skips**. Covers local HTTP/native POST/SQLite writes, closed-during-completion copies, uncertain native results, actual IndexedDB queueing/replay, unavailable storage, duplicate clicks, retained corrections, keyboard focus, English/Filipino combined skip/counts and native submission without JavaScript.
- The service-worker harness executes the actual `flushQueue` function with deterministic IDB/network seams, covering matching and mismatched receipts, HTML/network/server failures, refused requests and uncertain combined outcomes.
- Pinned axe-core **4.14.0** and Chromium **154.0.8037.57** sample **64 states**: CSM, correction summary, one-question mode, activity, speaker, combined, server confirmation and queued-on-device views; English/Filipino, light/dark and 390px/1440px. **0 detected violations, 0 horizontal overflows**; **64 incomplete checks** retained in [the evidence](audits/2026-10-19/A18_SURVEY_AUTOMATED_EVIDENCE.json). A Filipino mobile view was inspected locally.

Reproduce the explicit scan outside ordinary collection:

```sh
npm install --prefix /tmp/a18-audit --ignore-scripts --no-audit --no-fund axe-core@4.14.0
A18_AXE_PATH=/tmp/a18-audit/node_modules/axe-core/axe.min.js \
A18_REPORT=/tmp/a18-survey-report.json CSS_TEST_NOW=2026-10-20T06:00:00 \
python -m pytest -q tests/browser/a18_survey_probe.py
```

No production survey was submitted and no real provider-outage or staff/screen-reader session was performed. Manual accessibility, other-browser/device checks and staff observations remain open; sampled automation does not certify the whole system.

## Release and rollback

7.90 increments main 7.89 with aligned changelogs, service-worker cache and changed shared/survey asset references. New static assets use the existing deployment inventory. Roll back by reverting this increment and publishing a new application/cache version through the release workflow. Existing draft keys and queue rows remain readable; a background-confirmed device draft may still be offered for explicit review, as described above.
