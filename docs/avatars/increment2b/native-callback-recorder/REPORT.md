# Native callback recorder: cost passed, control stability failed

The C buffer recorder removes the remaining recording-cost failure in this fixed
mixed-fixture screen. **The instrument still does not qualify for application
calibration:** controls differ by **20.7568%**, above the unchanged 20% limit.
2B remains blocked. No product change, acceptance, merge, deployment or later increment.

## Native preflight and exact receiver proof

The native agent uses internal-toolchain C callbacks, externally allocated mutable
state, mutex-protected immutable integer records and an immutable export snapshot.
JS formats events after measurement. It preserves existing offsets, monotonic
clocks, thread identity, phases and overflow accounting; it never dereferences
sampled object pointers. Storage uses a two-way JS/C canary. Nullable Frida range
metadata is inconclusive and is not treated as proof of missing/read-only memory.

All implementation attempts are retained:

| Frozen harness | Observation | Disposition |
| --- | --- | --- |
| 6e7a8f1 | CModule loaded and 20 clock samples completed; native test hit an access violation | Failed, retained v1 capture/error |
| 9edef02 | Storage inspection returned null range metadata | Inconclusive; no writable-storage claim |
| 51a1b3b | External mutable state permitted concurrency work; export failed reading nullable range metadata | Failed, retained v2 capture/error; no completed proof claim |
| b2bf252 | Two-way owned-buffer canary and optional range metadata | Preflight passed: 20 clocks, four native threads, 1,024 immutable records; overflow retains 32 and reports all 36 drops |
| f676f7a | Live C callbacks on DOM/SVG/style | 384/384 receiver identities equal independent geometry references; all 384 native null returns; exact tags, query brackets, unchanged DOM |

The selftest runs separately with no live target hooks. Test reset is unavailable
in live mode. Both nested preflight files travel with the live receiver proof;
the screen checker verifies exact agent continuity through both proofs. Native
snapshot export must lie in its host monotonic bracket after measurement, with
zero pending/dropped records, valid ABI/clock/canary and no synthetic test events.

## Fixed four-slot calibration

Frozen harness **04ca993**, lifecycle **v12**. Same twelve 3,000-element DOM/SVG/
style documents, 32 receivers per group, repeated/disjoint selections, selector
reuse, navigation arming, beacon disposition and natural GC as v11. One fresh
process per slot, control/probe/probe/control; no replacements.

| Slot | Duration ms | Conservative observation bound | Maximum observation ms | Result |
| --- | ---: | ---: | ---: | --- |
| 0 control | 3702.241 | 2.7687% | 8.936 | Valid control |
| 1 probe | 3723.927 | 2.9486% | 9.117 | Individual gates pass |
| 2 probe | 3803.770 | 3.7522% | 13.052 | Individual gates pass |
| 3 control | 4470.708 | 3.8500% | 28.493 | Valid control; pair stability fails |

Both probes pass <=5% and <=250ms. Paired duration ratios **1.00586/0.85082** pass
<=1.20. Native preparation totals **1.0593/1.0708 ms**. The bound retains census,
counter, trace-setup and native preparation costs, including conservative double
counting inside the census; no work was subtracted or waived.

Both preserve **1,536/1,536 receiver joins**, repeated identity, group disjointness,
fixture hashes and eleven non-persisted pagehide events. Ten labelled generations
return inside each window: DOM4/SVG3/style3 in each probe; all twenty overlap native
sweeping with natural MajorGC present. There are 1,139/1,065 total pool returns.
All recorded native events lie inside measurement; no post-window return rescues
a gate. Three unknown pool generations per probe remain unknown. Membership does
not establish exclusive ownership or attributed bytes.

The complete audit's sole error is **Controls vary more than 20%**. Both application
qualification and acceptance remain false. A passing cost measurement alone does
not qualify this instrument.

## Control variation and next bounded work

[Retained interval analysis](control-variation.json) compares both uninjected
controls. The final one is **768.4669 ms** slower. Census/counter intervals account
for **69.6195 ms** of that difference; **698.8474 ms** remains outside those brackets.
The delay spans multiple stages (including the first three), rather than one long
native recorder callback: neither control installs the recorder/full trace.

Existing stage intervals combine navigation, the fixed 220ms wait, and DOM
serialization. They cannot distinguish browser work from host scheduling. Do not
assign a cause, subtract residual time, relax 20%, or repeat v12 unchanged for a
favorable control pair.

Next prepare a **separate control timing diagnostic**, with explicit host brackets
for navigation, fixed wait, each DOM serialization, census and counters, plus
bounded browser/host CPU scheduling context. Freeze its capture policy before
running it. Keep timing instrumentation separate from qualification and retain
all observations. Establish a concrete explanation/intervention for the control
variation before a new fixed calibration. No application comparison or product
correction follows from this screen.

## Integrity and reproduction

[Archive recheck](archive-recheck.json) reconstructs and independently re-audits
all three completed archives identically. Screen archive: **28 logical files**,
**16 harness/runtime hash checks**, **14 cohort files**, five receiver-capability
source hashes and four nested proof files. Selftest/receiver archives reconstruct
two/four files respectively. Earlier failed artifacts remain alongside them.
Large audit/period JSON is compressed without discarding any events or errors.

**81 focused tests pass**, existing Starlette deprecation warning only. Coverage
includes negative clock, ABI, canary, snapshot, pending, overflow, fake-event,
phase/cursor and historical-source checks. Product files remain byte-identical to
cf363bf. No application DB, user data or product workload was used.

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/native-callback-recorder/screen-v1-evidence.zip \
  --unpack-to /tmp/native-recorder-evidence
.venv/bin/python -m scripts.avatar_baseline.analyze_membership_lifecycle \
  /tmp/native-recorder-evidence/screen-v1 --ref 04ca993 --out /tmp/native-recorder-audit.json
```

Compare with decoded screen-v1-audit.json.gz. The period summary and all source
identities are retained; use latest branch HEAD for documentation, not a reset to
a harness commit.
