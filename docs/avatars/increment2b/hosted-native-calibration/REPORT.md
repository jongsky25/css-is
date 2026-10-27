# Hosted native recorder: full calibration passed

**The native recorder is qualified for a separately frozen application calibration
on this hosted condition.**
[Successful cloud run](https://github.com/jongsky25/css-is/actions/runs/40508949824),
[phone-readable summary](CLOUD_SUMMARY.md), [setup PR #513](https://github.com/jongsky25/css-is/pull/513).
Both fresh native prerequisites and the complete fixed control/probe/probe/control
schedule pass; independent offline audits reproduce identically. **This is not
application memory qualification, a product fix, or 2B acceptance.**

Frozen harness **0af68b8**, workflow **d7e2d31**, lifecycle v12. This is the first
actual hosted native calibration attempt; it has no replacement samples. Prior
failed local v12 and all older observations remain unchanged.

## Fresh prerequisites on the actual host

The native selftest passes: exact 72-byte ABI, CLOCK_MONOTONIC within twenty host
brackets, owned-buffer canary, four threads and 1,024 immutable records; overflow
stores exactly 32 and reports all 36 dropped test records. Selftest mode installs
no target hooks and cannot reset a live capture.

The subsequent live DOM/SVG/style receiver proof passes **384/384** independent
geometry references and native null returns, exact element types/query brackets
and unchanged fixture hashes. Both raw proofs and their independent audits travel
with the calibration; exact agent/source continuity is verified through the nested
preflight, receiver proof and both instrumented slots.

## Complete four-slot result

| Slot | Mode | Duration ms | Conservative observation bound | Maximum observation ms |
| --- | --- | ---: | ---: | ---: |
| 0 | control | 3599.443 | 2.3480% | 8.307 |
| 1 | probe | 3651.360 | **2.7115%** | 8.575 |
| 2 | probe | 3719.274 | **2.9615%** | 13.004 |
| 3 | control | 3665.607 | 2.3989% | 8.278 |

Both probes pass **<=5%** and **<=250ms**. Costs include census, heap/DOM counters,
trace setup and native record preparation; preparation within census intervals is
conservatively counted again. Preparation totals **2.4126/1.8573ms**. No cost was
subtracted, deferred beyond its actual bracket, ignored or waived.

Controls vary **1.8382%**, passing <=20%. Paired probe/control duration ratios
**1.01442/1.01464** pass <=1.20. All four fresh slots are present with valid source,
process, fixture and lifecycle identity. No extra per-phase diagnostic telemetry
was added to the qualification window. The control-only v2 deadline helper is not
active in ordinary lifecycle v12.

Both probes retain **1,536/1,536 receiver joins**, repeat identity, group separation,
fixed sample/query schedule and original 3,000-element mixed fixture hashes.
Ten labelled generations return in each measured window: **DOM4/SVG3/style3** per
probe. All twenty overlap native sweeping; natural MajorGC is present. Total pool
returns are **1,118/1,078**. All captured native events fall within measurement;
no late return rescues a gate. These are source memberships, not exclusive object
ownership or attributed allocation bytes.

The complete audit has **zero errors** and sets only
`instrument_qualified_for_application_calibration:true`. Both
`application_qualified` and `acceptance` stay **false**.

## Declared hosted condition

Standard GitHub ubuntu-24.04 on Azure/Microsoft virtualization, AMD EPYC 7763,
four visible CPUs (0–3), container CPU quota `max 100000`. Python **3.12.14** uses
the verified immutable trixie image from the successful control diagnostic;
Playwright **1.62.0**, Frida **17.5.1**, Chromium **156.0.8078.47**, native ELF
**1c5dca8527a61d07372e489142bee26af1bcaf71**. Actual resource and run/ref provenance
are in the raw artifact. No physical-host CPU exclusivity is claimed.

Only container-scoped **SYS_PTRACE** is added for Frida's own synthetic renderer;
the helper verifies its effective bit before proofs. No privileged mode, host PID
namespace, resource adjustment, load admission, app secret or product workload.
Repository contents permission is read-only. Dependency/browser mismatch stops;
no alternate build is substituted. Native and control-only runs use distinct jobs.
No cross-host absolute timing comparison establishes a product improvement.

## Controller mistakes and complete retention

Initial setup branch 32c5797 put Docker options at job level; the invalid YAML is
retained as workflow-initial-invalid.yml. GitHub launched no native job from that
invalid definition. Correct nested container schema and all bash blocks were
validated before the actual attempt.

Updating PR #511 also unintentionally retriggered the old control diagnostic due
to GitHub's cumulative PR path filtering. Incidental run **40508311821**, artifact
**12735104203**, is retained separately and independently re-audits identically.
It replaces no sample and is not used in native qualification. The connected
GitHub tools expose no cancel endpoint; no bypass or artificial workload failure
was used to suppress it. PR #511 now guards its completed automatic control run
to its original validated SHA, preventing additional automatic measurements.

The native workflow is instead proposed in separate main-based PR **#513**, only
its YAML and phone guide. An **opened-only** PR trigger starts the one prescribed
attempt; later documentation pushes cannot repeat it. Both PRs are unmerged;
manual-dispatch registration still requires resolving main's existing release
policy for configuration-only changes. No release gate/version metadata or deploy
policy was changed or bypassed. No merge or deployment occurred.

## Independent integrity and tests

Downloaded native artifact **12736566674**, ZIP SHA256
`2c1de48749d1eefeb04782e2034879bf7392ce137bddb1b3a16f734159b25a0d`,
preserved as calibration-v1-evidence.zip. All **57 internal manifest entries** and
the upload digest verify. Independent native proof, receiver proof, full calibration
audit and native-period summary match the cloud outputs identically.

The calibration audit verifies **16 source/runtime hashes**, **14 cohort files**,
**five receiver-proof source hashes** and **four nested proof files**. Assessment
JSON contains exact numerical results and provenance; native-periods.json.gz retains
all generations, unknowns, event-period distinctions and trace bounds. The incidental
control archive's complete manifest also verifies and its audit reproduces.

**104 focused tests pass locally; all 60 cloud preflight tests pass.** Product
sources remain byte-identical to cf363bf, and isolated candidate cd94bf3 remains
unpromoted. No app DB/user data or application comparison was used.

## Next bounded work

Freeze an **application-observer calibration** for this hosted condition before
collecting app data. Establish the actual application's receiver selection and
observable integrity, exact application/workload source identity and complete
control/probe schedule. Carry the qualified native proof/agent source continuity,
all cost and stability gates, and all raw failure retention into that protocol.
Do not assume the synthetic fixture alone proves application attribution or cost.

Only after that application-specific instrumentation prerequisite passes may the
memory attribution/comparison proceed. Existing candidate memory budget failures,
same-source repeat instability and full original-baseline acceptance obligations
remain. No favorable old-sample replacement, forced collection, cache flushing,
byte-ownership inference, budget waiver, 2B acceptance or later increment follows.
