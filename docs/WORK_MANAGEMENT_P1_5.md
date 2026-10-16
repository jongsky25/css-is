# P1.5 — Simplified intake and curated scenarios

October 16, 2026. Status **In review**; implementation owner Codex. Branch `codex/simplified-intake`; prepared version **6.57**. P1.4 was first merged at `53f1fb4` as release 6.55, preserving newer main registration-layout/deployment fixes. Packaging correction `ff100fe` (6.56) then added the personal inbox module to the deployment allowlist. P1.5 was subsequently merged at `72495348c5cf5941f4ab07e661ee91af27dfbac5` on the user’s instruction. The main push triggers the configured deployment workflow; live deployment success was not verified.

## Guided intake

`/documents/new` now groups intake into three decisions: choose the work, check correspondence, and confirm registration.

- **Reference only:** register correspondence without creating a work item, contribution, preliminary assignment, or implied lead. This is the default and remains available when Shared work is disabled.
- **Start new shared work:** explicitly enter the expected outcome and concerned unit, optionally suggest a lead, and choose whether to propose the scenario's displayed steps. Proposed steps have no confirmed owner or internal date. Officers confirm ownership/assignments through the existing workflow.
- **Link existing shared work:** choose a current permitted work item. The selected case revision is checked, and its creator, lead, and assigned contributors must already have source access. Linking never grants document access. The picker shows up to 25 recent permitted cases; older cases can launch intake from their own “Register new correspondence” link.

A new pending-verification document may not yet be readable by an existing work item's participants. In that situation the transaction refuses the link. The form explains the supported path: register as reference-only, arrange the document's access under existing authority, then link it. No visibility is silently expanded.

The curated scenarios are **Prepare a response**, **Provide inputs or data**, **Attend or organize an activity**, and **For information or reference**. Each shows concrete guidance. Action scenarios offer an editable expected outcome and optional contribution proposals; existing-work intake links correspondence without adding another set of tasks. No scenario creates a formal review assignment, signature, release, calendar booking, travel claim, or invented deadline.

Guided intake suppresses automatic preliminary document assignments so reference-only intake produces no artificial obligations and shared scenarios use their explicit proposed contributions. Existing routing policy/matches and deadline rules remain recorded. Ordinary service/API registration retains its prior routing behavior for compatibility. Formal document ownership/approval remains separate from suggested shared-work leadership; these links are references, not a new release-authority mapping.

## Extraction before registration

“Read source suggestions” uses the configured Workspace adapter's source inspection and transient extraction with its existing file-size/URL limits. No document, number sequence, database job, excerpts, or suggestions are saved by this preview. Suggestions are allowlisted to descriptive fields; lead/approval instructions are discarded.

The form displays source excerpts, warnings, and suggestions alongside the user's unchanged inputs. A user chooses individual suggestions to use, can correct them manually, and must confirm the source/fields/destination before registration. Suggested dates are not silently applied. Template escaping and DOM value assignment keep source text from becoming executable markup.

If inspection/extraction fails, the form retains manual fields, direction, priority, unit, and selected work destination and offers manual entry or retry. Extraction never becomes a prerequisite for registration. Confirmation is cleared after preview, including failure, so the user checks the final fields again.

## Atomicity and deployment

Registration, permanent numbering, receipt/reference creation, work creation/linking, optional proposals, and audit events run in one transaction. A stale work revision, source permission failure, invalid input, or failed contribution write rolls back all of them, including the sequence increment. Existing registration uses its same transaction implementation; internal transactional variants permit composition without nested commits.

The runtime allowlist includes both `work_inbox.py` and `work_intake.py`; templates/static files use the existing packaged directories. A regression check inspects local work-module imports from packaged runtime files and fails if one is omitted. No live deployment was performed.

## Verification

**98 tests passed** across work, Documents service/HTTP, Workspace, and setup suites, including the new deployment dependency check. New coverage verifies:

- Reference-only behavior even when existing rules would propose assignments, while retaining formal policy.
- All three action scenarios, optional proposal counts, unresolved owners, and no invented approval authority.
- Existing-work linking, stale revisions, source access failures, and complete rollback of document numbering/history on downstream failure.
- Confirmation and feature-switch requirements, transient extraction, allowlisted fields, URL rejection, escaping, and manual fallback with preserved inputs.
- No automatic application of preview suggestions and no exposure of inaccessible existing work.

Actual Chromium/Playwright workflow passed with a **synthetic extraction adapter**: preview → explicitly apply suggestions → new work with proposed contribution; existing-work intake adds a second document; failed preview preserves manual fields and reference-only registration creates no task. Narrow 390px layout had no horizontal overflow or script errors. Mobile capture was visually reviewed.

Workspace evidence: `/tmp/work-p15-tests.xml` and `/workspace/scratch/work-p15/` (synthetic database/server adapter, browser checker, screenshots). Existing Starlette/httpx deprecation warning remains. `git diff --check` passed. **Live Drive extraction was not verified.** No operational records, settings, or external deliveries were changed.

## Recovery and remaining gates

No schema migration or new feature switch is introduced. Existing Documents/Shared work controls still apply. A rollback to P1.4 removes the guided presentation while preserving all registered documents, work, tasks, and prior migration protections; retain the work-module packaging correction. Do not replace the database to undo intake.

Representative staff walkthroughs and live adapter acceptance remain open. Registration retains the existing form-resubmission behavior; this increment does not add a persistent intake-draft or submission-idempotency store. It also does not auto-group records, infer officers, or change release gates.

Next: **P1.6 — Contextual work item interface**, refining named task actions, people selectors, readable history, and clear next steps across the two-division contribution journey.
