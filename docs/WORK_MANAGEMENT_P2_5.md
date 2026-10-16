# P2.5 — Collaborative draft handoff

October 16, 2026 (Asia/Manila). **In review**, version **6.66**, branch `codex/draft-handoff`. P2.4 was merged at `855b7bb` before development. P2.5 was subsequently merged to main at `0dbfdb8` as version **6.69**, preserving intervening releases. Live deployment success has not been independently verified.

## Delivered

- One clearly labelled working Google Docs or Sheets draft on the work-item page, with an external open action. The creator, accountable lead or concerned officer selects, replaces or clears it with a reason. Each selection is retained in immutable history; competing selections check the current pointer before saving.
- A dedicated Draft and handoffs screen with named supporting Google files. Permitted participants can add links; their author or a work coordinator can remove a listing with a reason. Removing a listing never deletes a Google file or an earlier handoff reference. Duplicate active file identities are rejected; removed links remain in history.
- Contribution handoff notes from the confirmed owner, accountable lead or authorized officer, retaining the actual actor. Each note records the exact selected draft reference, optional supporting-file reference and contribution snapshot reviewed by the author. Stale draft or task state is rejected, and unsaved form text is retained.
- Notes are append-only; corrections use a new note. The contribution card links to its filtered handoff history. Earlier selections remain visibly labelled when the current draft changes. Handoffs can explicitly record that no working draft was selected.
- Draft history, removed-link history and handoff history have independent pagination. No handoff changes task state, assignment, case revisions, official deadlines, approvals, signatures or release evidence.

## Access and Google boundaries

Every screen and write rechecks current active account, work membership and visibility of all linked correspondence. Following, file links and handoffs do not create membership or grants. Existing enabled/open-work gates apply; authorized read access remains available with changes disabled.

Links require HTTPS and a supported Google file identity, reject credentials/untrusted hosts, and are normalized to known Google URLs. Valid Drive resource keys are preserved; unrelated query strings are removed. Working drafts must be Google Docs or Sheets; supporting links can also identify other Drive files. External links use `noopener noreferrer`.

The UI explicitly distinguishes app access from Google permissions. Saving a pointer performs no network inspection, sharing change, copy, upload, extraction or modification. A named link is not proof of access, file availability, actual file type or frozen contents. Formal exact-version review, signatures and release remain in Documents. Live Drive access is not certified by this increment.

## Storage and deployment

Additive draft-selection, supporting-file, link-retirement and handoff tables/indexes retain existing data. Historical references and task snapshots are immutable. Changes and audit events commit atomically. `work_handoff.py` is included in the deployment module allowlist. Version/changelog is 6.66.

## Verification

**184 passed** across shared work, Documents, setup, HTTP routes, Workspace operations, notifications and Google Meet. Only the existing Starlette/httpx deprecation warning. New checks cover URL validation/canonicalization and resource keys, exact historical draft/file/task references, unchanged task/document/case state, coordinator/owner authority, cross-item rejection, revoked access, stale draft/task forms, removed links, disabled writes with readable history, duplicate supporting files, simultaneous draft selection, audit rollback, repeated installation, immutable history, pagination, HTTP CSRF and escaped names.

Chromium journey: coordinator selects a draft; contributor adds evidence and a handoff; coordinator replaces the draft and removes the supporting listing; another contributor sees the current draft alongside the earlier handoff's retained draft/file references. Contribution filtering and unchanged task status were verified. Desktop 1440px and mobile 390px passed without horizontal overflow or browser errors. Google link destinations were inspected without opening external files. Local artifacts: `/workspace/scratch/work-p25`; test report: `/tmp/work-p25-tests.xml`.

## Next

The [Phase 2 acceptance review](WORK_MANAGEMENT_PHASE_2_ACCEPTANCE.md) passes technical criteria and recommends user acceptance. After acceptance, P3.1 introduces shared team list/board views. Live integration and operational rollout checks remain separate.
