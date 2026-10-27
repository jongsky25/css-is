# Cloud runner access from a phone

Follow-up: the [full hosted native calibration](../hosted-native-calibration/REPORT.md)
now passes in separate PR #513. Its artifact is avatar-native-calibration, distinct
from the original control-only artifact documented below. Automatic control PR
validation is guarded against further repeated measurements. This remains separate
from default-branch registration and 2B acceptance.


Setup PR: https://github.com/jongsky25/css-is/pull/511

A standard GitHub Linux x64 runner can be used without a local computer or SSH.
The user explicitly accepted evaluating this different environment. Physical CPU
reservation was not proved necessary by the prior diagnostic; the earlier
reserved-runner-only handoff is superseded. No isolation guarantee is inferred.

The setup PR adds only `.github/workflows/avatar-runner-diagnostic.yml` and
`docs/AVATAR_RUNNER_PHONE.md` to current main, not the avatar verification branch.
Its path-limited PR trigger runs once before merge, allowing the cloud setup to be
verified now. After registration on the default branch, use a phone browser:

1. GitHub repository → Actions → Avatar cloud runner diagnostic.
2. Run workflow → main → Run workflow.
3. Open the run summary, then download avatar-runner-diagnostic under Artifacts.

Desktop-site mode may be needed to show controls on a phone. The app itself can
hide controls available in the browser. Each manual run is a new experiment;
do not press Re-run jobs to replace a bad result. Keep failed artifacts.

## Exact workflow behavior

Workflow checks out harness 92b842826b60b8741e3032f252c09b6e350af66d and fetches its
history for source verification. It uses standard ubuntu-24.04 with a Python
3.12.14 trixie image pinned by digest, exact Debian Chromium 156.0.8078.47 and ELF
1c5dca8527a61d07372e489142bee26af1bcaf71, locked Playwright 1.62.0 and diagnostic
Frida 17.5.1 (separate wheel SHA lock). Runtime mismatch/unavailable versions fail
rather than substitute. Dependency/setup logs remain in the artifact.

The hosted helper records source hashes, allowed GitHub provenance, actual runner
CPU inventory, four complete controls, raw identity/phase/CPU snapshots, independent
audit and friendly summary. A 20-minute job limit bounds the run; repository
permissions are read-only, checkout credentials are removed, no secrets or paid
runner allocation are requested, and failure artifact upload runs always.

This is a control diagnostic, never automatic recorder qualification, an application
comparison, 2B acceptance, or deployment. The earlier failed samples remain failed.
The workflow does not waive 5%/250ms cost, 20% control or 1.20 paired limits for any
future calibration. Browser/fixture/receiver and no-forced-GC constraints stand.

## Registration constraint

GitHub exposes workflow_dispatch through its default branch. PR #511 has not been
merged. Its initial PR trigger provides an actual hosted diagnostic without that
merge. Recurring phone-button access requires default-branch registration.

The existing repository release gate rejects configuration-only changes without
an application version bump: current main/PR are both 8.98. We did not modify
product metadata, waive this gate, or merge/deploy anything. This is a separate
registration-policy issue for the maintainer; opening the cloud run and downloading
its artifact do not require merge. Existing normal release checks still apply.
