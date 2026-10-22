# S6.3 — Reconciled cutover and staff pilot

Status: **Paused at user request; operational inputs and staff acceptance still pending**, October 22, 2026 (UTC). Depends on [S6.2](SUPPLIES_MANAGEMENT_S6_2.md), which is verified locally with synthetic data. This handoff records completed preparation, not a live cutover.

## Prepared

- [Cutover and acceptance record](SUPPLIES_S6_3_CUTOVER.md) defines the ordered gates, count/import reconciliation fields, role assignments, evidence and sign-off for a controlled pilot.
- [Role operating guide](SUPPLIES_S6_3_OPERATING_GUIDE.md) maps the implemented screens to requester, approver, custodian, recipient, replenishment approver, delivery recorder and auditor actions.
- The plan now distinguishes this operational block from the S6.2 technical verification. The uploaded workbook and request form remain reference data, not instructions or authorization to post balances.

No application, schema, grant, feature flag or stock data changed in S6.3 preparation. No deployment, merge, push or live import was performed. The user's stop-merging instruction remains in effect.

On October 22, the user asked to turn Supplies off for now. The workspace database has no `supplies.enabled` setting, which the application treats as disabled (`0`). The workspace has no configured `CSS_DB` or remote Hugging Face credentials, so this check establishes **local** disabled status only; the running site's flag has not been inspected or changed. Do not resume cutover or pilot writes until the user asks to do so.

On October 22, the user then requested **step 1 only: put the verified module on the running site**, without rescinding the stop-merging instruction or the pause on Supplies business writes. Local deployment preflight found version 7.85, a complete runtime upload list and no unshipped local imports. The focused deployment/release/integrated-acceptance tests passed **31 tests** (`python -m pytest -o addopts= -q tests/test_deploy_hf.py tests/test_release_checks.py tests/test_supplies_acceptance.py`); `git diff --check` passed. The prior S6.2 full runner remains the latest complete regression evidence.

**Live deployment is blocked by this execution environment:** it has no Hugging Face credential, no administrator backup credentials, and its enforced network policy excludes the Hugging Face API and Space host. The canonical `deploy_hf.py` checks the live Space, secures a current backup under persistence, uploads the runtime closure and verifies the new login version; none of those live steps can be completed here. The GitHub Action deploy job runs only from `main`, so using it now would require the merge the user explicitly stopped. No upload, deployment, backup or live verification was attempted or claimed. The module remains locally disabled; remote status is unknown.

## Gate still open

The user confirmed a **whole-office pilot** and nominated a custodian/request approver/support contact and separate replenishment/alternate request approver; the [cutover record](SUPPLIES_S6_3_CUTOVER.md) has their email addresses. Their active accounts, organizational-unit scopes and grants still need verification. Pilot coordinator, auditor/reviewer, recovery authority, signed dated physical count, canonical-unit reconciliation, exclusions, agreed spreadsheet cutoff, verified *live* backup, controlled import, ledger/count sign-off and staff acceptance remain pending. The older uploaded workbook cannot establish current stock. Do not mark S6.3 Verified, open pilot writes, or claim a successful live restore on the strength of S6.2's disposable rehearsal.

Once these facts are provided, record them in a controlled copy of the cutover record; carry out the gates in order with authorized personnel; capture a real pilot's transaction IDs, quantities, defects and independent sign-off. Use the already implemented reviewed import and normal request flow. Do not add pre-cutoff issues as new stock deductions or double-enter outstanding demand.

## Verification and recovery

Documentation paths and route names were checked against the current Supplies UI and route table. `git diff --check` was run for the documentation changes. No new code paths were introduced, so the preceding [S6.2 technical checks](SUPPLIES_MANAGEMENT_S6_2.md) remain the latest application verification: 762 relevant tests, 5,073 repository tests, Chromium scenario and disposable backup/restore. They are synthetic and cannot replace staff sign-off or a verified live backup. There is no S6.3 browser screenshot or staff walkthrough yet.

On a material discrepancy, the authorized administrator disables Supplies changes while preserving authorized reads and all posted evidence. Reconcile movements through reviewed corrections and the cutoff exception log. A shared-database restore requires a coordinated plan for other-module activity; never blindly overwrite newer office records.

**Next gate:** Complete S6.3 with real operational evidence, then update this handoff to Verified. No later numbered increment is defined in the current plan.
