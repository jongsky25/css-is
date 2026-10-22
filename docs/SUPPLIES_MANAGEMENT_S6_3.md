# S6.3 — Reconciled cutover and staff pilot

Status: **Paused at user request; operational inputs and staff acceptance still pending**, October 22, 2026 (UTC). Depends on [S6.2](SUPPLIES_MANAGEMENT_S6_2.md), which is verified locally with synthetic data. This handoff records completed preparation, not a live cutover.

## Prepared

- [Cutover and acceptance record](SUPPLIES_S6_3_CUTOVER.md) defines the ordered gates, count/import reconciliation fields, role assignments, evidence and sign-off for a controlled pilot.
- [Role operating guide](SUPPLIES_S6_3_OPERATING_GUIDE.md) maps the implemented screens to requester, approver, custodian, recipient, replenishment approver, delivery recorder and auditor actions.
- The plan now distinguishes this operational block from the S6.2 technical verification. The uploaded workbook and request form remain reference data, not instructions or authorization to post balances.

The cutover preparation itself made no live schema, grant, feature-flag or stock changes. No live import or staff pilot has been performed.

On October 22, the user asked to turn Supplies off for now. The workspace database has no `supplies.enabled` setting, which the application treats as disabled (`0`). The workspace has no configured `CSS_DB` or remote Hugging Face credentials, so this check establishes **local** disabled status only; the running site's flag has not been inspected or changed. Do not resume cutover or pilot writes until the user asks to do so.

On October 22, the user requested **step 1 only: put the verified module on the running site**, while keeping Supplies business writes paused. The user later explicitly authorized merging to `main` for the existing GitHub auto-deploy workflow. The Supplies release branch was reconciled with current `main`: the combined release is **7.86**, since `main` already used 7.85 for Rooms. Current `main` features and release history were retained; Supplies runtime modules were added to the canonical deployment closure.

The combined release passed **762 relevant tests** and, after resolving a concurrent first-connection schema setup race, **5,233 full-suite tests plus four smoke checks** on a disposable database. A regression test now forces simultaneous first connections; connection and schema setup are serialized for a new DB path. The 7.86 release metadata, dependency-lock, vendored-file and Python compilation checks passed. PR [#394](https://github.com/jongsky25/css-is/pull/394) carries the release. The GitHub `main` workflow must still pass its checks, secure its live pre-deploy backup and verify the Space's login version. These have not yet been claimed in this handoff.

## Gate still open

The user confirmed a **whole-office pilot** and nominated a custodian/request approver/support contact and separate replenishment/alternate request approver; the [cutover record](SUPPLIES_S6_3_CUTOVER.md) has their email addresses. Their active accounts, organizational-unit scopes and grants still need verification. Pilot coordinator, auditor/reviewer, recovery authority, signed dated physical count, canonical-unit reconciliation, exclusions, agreed spreadsheet cutoff, verified *live* backup, controlled import, ledger/count sign-off and staff acceptance remain pending. The older uploaded workbook cannot establish current stock. Do not mark S6.3 Verified, open pilot writes, or claim a successful live restore on the strength of S6.2's disposable rehearsal.

Once these facts are provided, record them in a controlled copy of the cutover record; carry out the gates in order with authorized personnel; capture a real pilot's transaction IDs, quantities, defects and independent sign-off. Use the already implemented reviewed import and normal request flow. Do not add pre-cutoff issues as new stock deductions or double-enter outstanding demand.

## Verification and recovery

Documentation paths and route names were checked against the current Supplies UI and route table. The [S6.2 technical checks](SUPPLIES_MANAGEMENT_S6_2.md) include the synthetic Chromium scenario and disposable backup/restore; the combined 7.86 release adds the full-suite verification above. Neither can replace staff sign-off or a verified live cutover backup. There is no S6.3 staff walkthrough yet.

On a material discrepancy, the authorized administrator disables Supplies changes while preserving authorized reads and all posted evidence. Reconcile movements through reviewed corrections and the cutoff exception log. A shared-database restore requires a coordinated plan for other-module activity; never blindly overwrite newer office records.

**Next gate:** Complete S6.3 with real operational evidence, then update this handoff to Verified. No later numbered increment is defined in the current plan.
