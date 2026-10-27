# Phone-accessible hosted runner: workflow verified end to end

**The standard GitHub Linux x64 diagnostic now runs successfully.**
[Open the successful run from a phone](https://github.com/jongsky25/css-is/actions/runs/40503804962).
All four controls complete; artifacts and a plain-language job summary are
available without a local computer or SSH. [Setup PR #511](https://github.com/jongsky25/css-is/pull/511)
adds only the workflow and phone instructions to main; it remains unmerged.

The user's acceptance of a standard hosted runner supersedes the earlier
reserved-runner-only requirement. Physical reservation was not proved necessary.
This new runner condition is evaluated explicitly, not presented as guaranteed
CPU isolation or a passing application/instrument qualification.

## What is ready and what still requires registration

The PR's path-restricted trigger validates this workflow before merge. That hosted
execution is complete and viewable now. For the **Actions → Avatar cloud runner
diagnostic → Run workflow** button, GitHub requires default-branch registration.
The [phone guide](README.md) gives exact steps and artifact instructions.

The existing repository release check rejects configuration-only changes without
an app version increase (main and setup PR both 8.98). Local reproduction fails
with `Version 8.98 must increase from 8.98`. No app release metadata, release gate,
auto-deploy policy, or product code was changed or bypassed. We have not merged,
deployed or registered the workflow on main. This is the remaining manual-button
registration issue, separate from a fully verified cloud diagnostic execution.

PR head **3bb633c** differs from current main dd0e4e8 by only:

- `.github/workflows/avatar-runner-diagnostic.yml`
- `docs/AVATAR_RUNNER_PHONE.md`

The workflow checks out frozen diagnostic **92b8428** from the verification history,
not PR-head product changes. Read-only contents permission, no retained checkout
credentials, no secrets, standard ubuntu-24.04, no paid/larger-runner configuration,
20-minute timeout, no automatic retries, and always-on failure artifact upload.

## All hosted attempts retained

| Run | Workflow / harness | Result |
| --- | --- | --- |
| 40502688708 | 3664c4a / c76ae40 | Pinned inherited image actually contains Python 3.12.15; runtime check stops before measurement; 33 tests pass |
| 40503234347 | ab479b9 / c76ae40 | Verified Python 3.12.14 image; four controls captured; three API timers return 0.03–0.37ms early and strict wait-floor audit rejects them |
| 40503804962 | 3bb633c / 92b8428 | Diagnostic v2 enforces the declared 220ms host-monotonic minimum; all four controls and audit complete; 35 cloud preflight tests pass |

Each correction was frozen before its PR-triggered attempt. No unchanged job was
rerun and no failed sample was removed. Initial image mismatch is retained in
hosted-v1-failure.zip; all four rejected timer captures are in hosted-v2-failure.zip.
The raw success is hosted-v3-evidence.zip. Their assessment JSON files record exact
upload digests, artifact IDs, Git identities and independent verification.

The Python repair pins
`python:3.12.14-trixie@sha256:4d1caded1f729ae443eb803f26ffde7b61e696aeaef62f099abb6dd6b14257c7`;
an offline container command independently verifies 3.12.14/x86_64. The wait repair
keeps the original browser wait then sleeps only any positive remainder of its
host-monotonic deadline. It retains the >=220ms checker floor and records padding.
Historical v1 audits preserve their failing results. Ordinary v12 behavior remains
unchanged when the separate diagnostic timing object is absent.

## Successful new-runner controls

| Control | Duration ms | Telemetry ms | Reported aggregate CPU steal | Quota throttle ms |
| --- | ---: | ---: | ---: | ---: |
| 1 | 3900.752 | 139.683 | 0% | 0 |
| 2 | 3818.159 | 144.103 | 0% | 0 |
| 3 | 3845.508 | 138.397 | 0% | 0 |
| 4 | 3893.634 | 140.776 | 0% | 0 |

The diagnostic duration range is about **2.16%**. No reported CPU-steal or quota
throttle increments occur in sampled operations. This is promising new-environment
evidence, not a conversion of diagnostic timings into qualification. It does not
prove exclusive host CPUs or establish why every earlier slow operation occurred.

Actual runner: Azure/Microsoft virtualization, AMD EPYC 7763, four guest-visible
CPUs (0–3), cgroup CPU quota `max 100000`, read-only guest CPU controls and no
exclusive cpuset claim. This differs from the original managed KVM/Xeon runner's
five visible CPUs/four-CPU quota. Absolute timings across these different conditions
cannot establish a product performance correction. All captures retain actual
resource provenance and the same fixture/browser identities.

The workflow preserves exact Chromium **156.0.8078.47** / ELF
**1c5dca8527a61d07372e489142bee26af1bcaf71**, Python 3.12.14, locked Playwright 1.62.0
and separate SHA-locked Frida 17.5.1. It does not force collection, reduce the
receiver sample, filter host load, subtract telemetry or launch an app comparison.

## Verification and scope

All three artifact upload digests and internal manifests verify. The complete
successful diagnostic independently re-audits identically: five frozen sources,
twelve cohort files, 35 artifact-internal hash entries. Its CPU-context summary
reproduces identically. The failed timer diagnostic also independently re-audits
to the identical three errors; first setup failure contains no measured control.

**101 focused tests pass locally**, including preserved historical protocol handling,
early/completed timer behavior, snapshot/identity checks and phone summary cases.
Workflow trigger/permissions/pinned-checkout checks and every bash block validate.
Hosted setup, all 35 preflight tests, capture, audit, summary and upload succeed.
The final reviewed workflow bytes and setup provenance are retained alongside
this report. Product files remain byte-identical to cf363bf; main is untouched.

2B is still blocked. C recorder v12's old 20.7568% control failure remains failed;
no application calibration or acceptance is established here. Next measurement,
if pursued, must be a **newly frozen full native-recorder calibration on this
hosted runner condition**, preserving the complete control/probe/probe/control
schedule, prior proofs and unchanged cost/integrity/reclamation/stability gates.
Do not silently add that work to the manual control workflow, call a successful
control diagnostic acceptance, or dispatch a full product matrix prematurely.

Registration remains a separate maintainer policy decision under the existing
main release checks. No merge, version bump, deployment or later increment follows
from this successful diagnostic.
