# P1.1 — Shared work item and document links

Date: October 16, 2026. Status: **In review**. Implementation owner: Codex; staff acceptance owner remains to be designated. Branch: `codex/collaborative-work-foundation`. Prepared version: **6.50**. No deployment or merge is recorded for this increment.

## Delivered workflow

- Create an outcome with a title, expected output, concerned unit, optional proposed lead, and optional planning target.
- Start from an existing permitted document, or from Office → Shared work.
- Have the concerned officer confirm or replace the accountable lead with a reason. A suggestion alone grants no access or authority.
- Link multiple existing IN/OUT records as references. Navigate between a permitted document and its permitted work items.
- Read the ownership and append-only work history, including confirmation reasons.

Document numbers, assignments, approval states, signing/release authority, and external Drive permissions are unchanged. Planning targets do not extend official document deadlines. These boundaries preserve the existing Documents authority, visibility, deadline, approval, signing, dispatch, and closure obligations described in the phased plan.

## Access and consistency

A reader must be the creator, confirmed lead, or current scoped officer, and must also have access to every linked document. Technical administrators have no implicit bypass. Losing source access hides the whole work item, including reverse links. A proposed lead is not a reader by virtue of that proposal.

The creator and confirmed lead must already have access before a document can be linked. Lead confirmation checks source access; reassignment removes the old lead's ownership-based access. Current active-account and officer authority are reloaded for writes. Session-bound CSRF protects forms. Revision checks reject stale ownership/link writes, and audit failures roll back the transaction.

Merged records resolve to their current canonical record, with current permissions and metadata. Duplicate references are idempotent, including references through merged aliases. Reverse navigation also follows aliases.

## Setup and recovery

Normal application database initialization installs the additive `work_case`, `work_document`, and `work_event` tables and inserts `work.enabled=0` only if absent. Repeated initialization preserves settings and records.

For evaluation, use a disposable database with fictional accounts and documents. Initialize it through the normal storage setup, then use `storage.set_setting(conn, 'documents.enabled', '1')` and `storage.set_setting(conn, 'work.enabled', '1')` on that evaluation connection. Run the app with `CSS_DB` pointing to that database. Existing document role setup is still required. Do not run the destructive sample database setup against operational data.

Both switches must be enabled for work writes. Disabling `work.enabled` blocks new changes and preserves permitted reads. Retain the additive tables and audit history when disabling the feature; no document assignment rollback or data deletion is needed. Sending settings and relays are not changed. The ordinary local database remains disabled; browser verification used a separate disposable database.

## Verification evidence

All checks ran locally against synthetic data on October 16, 2026:

- **68 passed:** `tests/test_work.py`, `tests/test_documents.py`, `tests/test_documents_routes.py`, `tests/test_documents_workspace.py`, and `tests/test_documents_setup.py`. Includes access revocation, scoped authority, stale revisions, transaction rollback, immutable history, canonical document merging, feature switches, pagination, and full HTTP form flows.
- **5 passed:** existing navigation/search-index tests covering role filtering, index/navigation alignment, Office placement, rendered sections, and module metadata.
- Actual application browser workflow passed in system Chromium through Playwright: create from an incoming record, confirm lead as officer, search/link an outgoing record, reverse navigation, confirmed-lead access, and anonymous redirect to login.
- Desktop and 390px mobile screenshots were visually reviewed. No horizontal overflow or browser script errors occurred.
- `git diff --check` passed. Tests report the existing Starlette/httpx deprecation warning.

Local supporting artifacts: `/tmp/work-p11-tests.xml` and `/workspace/scratch/work-p11/` (`check_browser.py`, synthetic setup, and desktop/mobile screenshots). These are workspace evidence, not production data or committed test dependencies. The repeatable service/HTTP checks are committed-source candidates in `tests/test_work.py`.

## Remaining boundaries and next increment

P1.1 provides creation/read, lead confirmation, and reference linking. Contribution tasks, discussion, followers, notifications, title/outcome correction, unlinking, legacy assignment migration, and primary preparation/release ownership are not implemented here. Document search examines a bounded recent matching set; users can refine the query for older correspondence.

Staff walkthroughs and live relay/integration readiness remain unverified. The user's instruction to continue authorized implementation against the proposed Phase 0 contract; it did not mark the contract accepted. Operational activation remains subject to the plan's readiness gates.

Next: **P1.2 — Contribution task lifecycle**, including independent contributions, scoped assignment confirmation and acceptance, return/resubmit, and optimistic concurrency. Resolve the documented legacy lead-acceptance mismatch as part of that increment before compatibility cutover in P1.3.
