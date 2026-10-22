# A17 — travel guidance, review and recovery (7.89)

## Workflow meaning

Travel filing records checklist readiness and the traveller's paper handover. The Administrative Section records decisions on fare/route/role flags. Those decisions are not final claim approval, receipt confirmation, payment or an email delivery receipt. No financial approval workflow was added.

The filing page keeps the activity/deadline and recorded status visible, then explains who acts next and links to the existing useful action:

- **In progress:** add missing required attachments, prepare the missing forms, correct claim details, or review flags. Attachment work comes before form preparation. Optional and FMIS rows do not block readiness; a carried document may use the existing paper note option.
- **Forms running:** check form progress. A prior form link may remain while a replacement is being made.
- **Failed form attempt:** read the latest failure reason and check any earlier linked copy before choosing to make another copy. The earlier URL is retained and labelled as an earlier form, not a completed replacement. Existing checklist rules still accept a valid earlier/manual form link.
- **Open flags:** the Administrative Section acts next. Current section members may open the existing verify queue; travellers can read the waiting flags. A rejected flag points to its reason and the traveller's corrections. The existing supervisor-confirmation rule remains in force for participant-only travel.
- **Ready:** print the listed copies, sign where indicated, and hand in the papers. Mark submitted records the traveller's handover only; it does not send documents or email.
- **Submitted / withdrawn:** explain the recorded handover or closed filing. Administrative Section readers keep their existing read-only checklist view; only current authorised section members may record flag decisions.

My filings gives a brief actor/step reminder without per-row checklist/flag queries. Detail and print-list guidance reuse current applicable checklist rows and flags. The existing deadline refresh and cash-advance carry-over behavior on detail reads is retained; this is not a claim that every existing detail GET has no database effects.

## Readiness and external-file protection

`travel_rules.readiness` supplies the same blocker facts to display and ready/submitted services. Those writes reload the filing and check current documents, generation state and flags. A stale ready object cannot bypass a later edit, running generation or newly opened flag. The existing status transitions, current-account ownership, feature switch, same-origin checks and directory membership remain independent of the guidance.

Checklist input validation now happens before replacing/trashing uploaded Drive files and before database item changes. Invalid links, disallowed row inputs and closed filings are refused before the external trash call. This protects existing files on a rejected edit; it does not make provider calls and database commits one cross-system transaction.

## Corrections and recovery

Invalid checklist links/notes and answer edits return a focused server-rendered form response with entered values. The saved checklist stays authoritative; draft answers do not silently change the saved answers summary. A filing closed during editing shows unsaved details read-only. A row removed from the applicable checklist shows the unsaved input for copying instead of discarding it. These browser form errors use HTTP 400/409 instead of redirecting away; successful writes retain their existing 303 redirects.

Flag-review errors retain the note and confirmation checkbox on the authorised review page. A disappeared flag returns a 404 with the unsaved note. Current membership is checked before showing the queue or applying any decision.

Fragment links open the actual checklist details/answer section and move keyboard focus without submitting a form. Native summary controls retain their tab order. Core checklist, ready and handover forms remain usable without JavaScript; the preparation editor retains its existing JavaScript requirement and manual-form link fallback.

Preparation first reads uncached current progress. A failed read stops polling with an explicit **Check form progress** GET retry and keeps the browser draft. Generation clicks disable both whole-filing and per-form buttons; superseded read responses are ignored. If the POST response is lost, the UI checks saved form status without replaying the make request or claiming that a specific unconfirmed attempt succeeded. The user reviews existing links before explicitly requesting another copy. Browser-local draft behavior, per-document revision IDs, document formats and relay contracts are unchanged. Durable worker receipts and interrupted external-operation reconciliation remain later operations work.

Browser uploads send one request per selected file. An uncertain network/server/non-JSON result stops the remaining batch and offers **Check saved files** (a page reload/GET). There is no automatic upload POST retry, including after earlier files in the batch were confirmed saved. This does not claim exactly-once behavior inside the provider.

## Evidence

- `tests/test_travel_guidance.py`: lifecycle/actor/blocker agreement, fresh readiness guards, current membership and read-only views, failed replacements with earlier links, retained/escaped input and validation before external trash.
- `tests/test_travel_guidance_browser.py`: actual application HTTP responses, native POST/303 flows and SQLite effects via the shared local HTTP adapter. External hosts are blocked and document/upload providers use recording fakes. Covers focus, corrections, flag review, lost generation/upload responses, partial batches, explicit read retry, duplicate make clicks, immutable filings and no-script ready/handover.
- Existing travel UX tests use the shared installed-Chromium fixture, so they execute locally instead of being skipped when only system Chromium is present.
- Broad local travel regression run: **451 passed, no skips** before three additional recovery/file-protection cases. The final targeted guidance/flag/browser run passed **56 cases**, including partial upload batches and interrupted response-body reads.
- Pinned axe-core **4.14.0** / Chromium **154.0.8037.57** samples **52 states**: index, missing checklist, retained answer error, running/failed replacement, preparation/progress-read recovery, waiting/rejected flags, supervisor-confirmation recovery, ready, submitted and withdrawn; each at 1440px/390px in light/dark. There were **0 detected violations and 0 horizontal overflows**. [Evidence](audits/2026-10-19/A17_TRAVEL_AUTOMATED_EVIDENCE.json) retains **130 incomplete checks** for manual review. Mobile layout was visually reviewed locally. Move up/down accessible names include the visible wording.

Reproduce the explicit scan outside ordinary collection:

```sh
npm install --prefix /tmp/a17-audit --ignore-scripts --no-audit --no-fund axe-core@4.14.0
A17_AXE_PATH=/tmp/a17-audit/node_modules/axe-core/axe.min.js \
A17_REPORT=/tmp/a17-travel-report.json CSS_TEST_NOW=2026-10-20T06:00:00 \
python -m pytest -q tests/browser/a17_travel_probe.py
```

No live production workflow, real provider outage or manual screen-reader session was performed. Staff observations, incomplete-check review, real zoom/mobile/forced-color and other-browser sessions remain open. The room/calendar/travel engineering increments are delivered; the A17 staff/manual pilot gate remains open. A18 survey/reporting improvements follow.

## Release and rollback

7.89 increments current main 7.88, with aligned changelogs, service-worker cache and travel asset references. `travel_guidance.py` is included in deployment inventory. No schema migration or new dependency is needed. Roll back by reverting this increment and publishing a new application/cache version through the existing release workflow; no external files are deleted by rollback.
