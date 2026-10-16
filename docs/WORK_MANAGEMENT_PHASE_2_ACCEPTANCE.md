# Phase 2 acceptance review

October 16, 2026 (Asia/Manila). Reviewed release **6.69**, merged to main at `0dbfdb8`. P2.5 implementation originated at `be2967f`; the merge preserves main's short-link, calendar claim navigation and public registration changes.

## Recommendation

**Technical acceptance: pass. Recommend accepting Phase 2.** No blocking defect was found in the reviewed Phase 2 criteria. The user subsequently authorized P3.1 after this recommendation, accepting the Phase 2 gate. This does not record staff trial acceptance or live deployment success.

## Acceptance matrix

| Increment | Result | Evidence |
|---|---|---|
| P2.1 Discussion and replies | Pass | Two contributors, scoped replies, author-only edits and retained revisions; discussion leaves task revisions and official document state unchanged. See [P2.1](WORK_MANAGEMENT_P2_1.md). |
| P2.2 Mentions, following and unread state | Pass | Targeted durable notices, duplicate suppression, observed-revision read markers, follow/unfollow, and current access checks on reads and delivery. Mentions do not grant access. See [P2.2](WORK_MANAGEMENT_P2_2.md). |
| P2.3 Blockers and dependencies | Pass | Named blocker follow-up, cycle/concurrent-cycle rejection, upstream acceptance gates, explicit resolution, and unchanged official deadlines. See [P2.3](WORK_MANAGEMENT_P2_3.md). |
| P2.4 Sourced tasks and decisions | Pass | Message-derived proposals retain original text; confirmation remains explicit; authorized changed decisions preserve accepted outputs and require reconciliation. Work decisions do not provide formal document approval. See [P2.4](WORK_MANAGEMENT_P2_4.md). |
| P2.5 Draft handoffs | Pass for application scope | Current draft is identifiable; canonical Google links, historical draft/file references and task snapshots remain available. Stale handoffs and unauthorized changes are rejected. Actual Google access remains dependent on Drive permissions. See [P2.5](WORK_MANAGEMENT_P2_5.md). |

## Demonstrated phase scenario

The automated `test_phase2_question_dependency_decision_and_handoff_journey` uses two contributors and a scoped records officer with a linked official document:

1. A contributor asks for validated regional totals; the message becomes a proposed contribution with retained source text.
2. The officer confirms the second contributor's ownership. A downstream contribution depends on this input.
3. The second contributor replies and mentions the follower; only one targeted notice is produced.
4. Premature downstream submission is rejected. The upstream owner records and resolves a blocker, submits totals, and the officer accepts them.
5. The officer records changed direction from the reply and explicitly reconciles the downstream contribution.
6. Contributors select a working draft, attach supporting evidence and record a handoff snapshot. Downstream submission and acceptance then succeed.
7. The complete official document row remains unchanged throughout, including its formal state and dates.

The fixture explicitly grants linked-document access before assigning the second contributor. The initial fixture attempt without that grant was correctly rejected; the production access rule was retained.

## Verification and integrity

**240 tests passed**, zero failures, errors or skips, on the merged release plus the new integrated acceptance test. The run covers shared work, Documents, setup, HTTP routes, Workspace operations, notifications, Meet, short links and travel pages. One existing Starlette/httpx deprecation warning remains.

Reproduce:

```sh
MPLCONFIGDIR=/workspace/.cache/matplotlib XDG_CACHE_HOME=/workspace/.cache \
/workspace/.venv/bin/python -m pytest -q \
 tests/test_work.py tests/test_documents_setup.py tests/test_documents_routes.py \
 tests/test_documents.py tests/test_documents_workspace.py tests/test_notifications.py \
 tests/test_meet_relay.py tests/test_short_links.py tests/test_travel_pages.py \
 --junitxml=/tmp/phase2-acceptance-tests.xml
```

The suite checks revoked access, cross-item references, CSRF, escaped content, stale/concurrent writes, immutable history, transactional audit rollback, repeated schema installation, disabled-write/read-history behavior and deployment module inclusion. Restricting a linked document applies across collaboration surfaces; following and linking files do not bypass it.

Existing increment browser evidence was reviewed, rather than represented as a new live trial: P2.1–P2.5 each have multi-user Chromium journeys, 1440px desktop and 390px mobile screenshots, and no reported horizontal overflow or browser errors. P2.1 includes keyboard operation. Local evidence lives under `/workspace/scratch/work-p21` through `work-p25`; these scratch artifacts are not durable repository attachments. The integrated phase scenario above is a service-level test, not a new combined browser journey.

## Remaining boundaries and next step

- Live deployment health has not been independently verified. Main's push triggers the configured deployment workflow; that alone does not establish completion.
- Google URLs were inspected without opening live files. Actual Drive access, file availability, signing, OCR and mail acceptance remain P4.1 checks.
- Draft links identify mutable working files; they are not frozen approved versions. Formal review, signing and dispatch remain in Documents.
- Notifications are in-app. Preferences/digests are P3.4; follow-up dates do not send automated reminders.
- Browser evidence is functional coverage, not a comprehensive accessibility audit or a staff usability trial. Operational acceptance and recovery rehearsal remain Phase 4.

After user acceptance, the next increment is **P3.1 — Shared team views**: team filters and list/board views over the existing task service, consistent updates across My work/detail/views, permission enforcement and equivalent keyboard actions.
