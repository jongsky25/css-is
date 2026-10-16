# P1.7 — Guided administrator readiness

> **Subsequent status, October 16, 2026:** The user explicitly accepted Phase 1 and authorized P2.1. Earlier review notes below are retained as implementation evidence; live integration verification remains a separate rollout requirement.
October 16, 2026. **In review**, version **6.59**, branch `codex/readiness-checklist`. Merged at `17dc12f`; the user subsequently accepted Phase 1. Live deployment success was not independently verified.

## Implementation

A read-only checklist at `/admin/documents/readiness`, linked from Documents setup and Rules and policies, works even while Documents is disabled. Access requires an active system administrator or an active all-unit workflow/permissions administrator; current database authority is rechecked. It grants no document access.

Twelve checklist cards describe prerequisites, what they affect, the responsible owner and next setup action:

- Active, unrevoked permissions, workflow, records and signatory grants, distinguishing scoped grants from all-unit grants without requiring excessive authority.
- Directory chief/OIC/Director authority, explicitly requiring unit-by-unit review.
- Active policy field inventory, without treating field completeness as effective rule coverage or conflict resolution.
- Current and next-year holiday confirmation, using Manila’s current year and directing owners to review other years where needed.
- Separate Drive, extraction, stored-signature and official email checks. Local endpoint validation and secret/sender presence never imply remote verification. Values and secrets are not displayed.

Rollout controls show Documents, Collaborative work and sending independently. GET performs no integration calls or writes. There are no checklist mutation, grant or dispatch controls. Existing setup and destination permissions remain in force. Settings without existing UI are assigned to the deployment maintainer with exact names and the existing setup runbook. No live verification marker is invented; owners must record test evidence during rollout review.

The new service is included in the deployment module allowlist. Version/changelog updated to 6.59.

## Verification

Focused suite: **108 passed**, covering Documents, Workspace operations, setup, routes and collaborative work. Added checks cover read-only inventory, active/revoked/scoped grants, refreshed authorization, missing holiday confirmation, invalid relay endpoints, secret redaction, access while disabled and HTTP rendering. Existing deployment dependency guard passes. Existing Starlette/httpx deprecation warning remains.

Chromium browser check with a synthetic administrator: setup navigation, all 12 cards, desktop 1440px and mobile 390px without horizontal overflow or browser errors. Screenshots and runner are in `/workspace/scratch/work-p17` (local artifacts, not deployment files).

## Remaining acceptance

This increment does not establish live integration health, policy coverage, legal signing authority or staff acceptance. Before Phase 2, review the complete Phase 1 journey with participating units, confirm actual configuration and retain controlled live verification evidence. No live credentials, authority, dispatch switches or production data were changed.
