# Fixed shared-stylesheet memory screen — failed

All eight scheduled workloads completed: current/candidate/candidate/current,
two full warm-desktop samples per cohort, from frozen harness `b521760`.
Current product is f700187; candidate is 6960562. Chromium 156.0.8078.47,
30-second primary scenarios, all eight scenario checkpoints and five navigation
checkpoints. No replacements, exclusions, forced GC, traces, or concurrent
analysis/browser workloads. The visual-only paint hint/probes were absent.

The independent auditor verifies 114 source/fixture hashes and 20 cohort files,
valid sample protocols and matched renderer counts. A separate calculation from
raw samples reproduces all 104 comparison records. Re-auditing an independently
extracted archive produces the identical assessment.

## Result

Candidate minus current median renderer RSS, in MiB:

| Order | Navigation 10 | Navigation 20 |
| --- | ---: | ---: |
| Forward | -20.291016 | -34.609375 |
| Reverse | -27.261719 | **+12.863281** |

The criterion required at least 5 MiB improvement at BOTH checkpoints in BOTH
orders, with no RSS or JS-heap checkpoint worsening more than 10 MiB. Reverse
navigation 20 fails both requirements. It is the only candidate/current >10 MiB
budget violation in this screen; all records, including decreases, are retained.

Both same-source controls also fail the absolute 10 MiB stability requirement:

| Control | Checkpoint | RSS repeat delta, MiB |
| --- | --- | ---: |
| Current | Navigation 15 | -34.691406 |
| Current | Navigation 20 | -57.037109 |
| Candidate | Home idle | +10.605469 |
| Candidate | Navigation 10 | -10.328125 |

Negative differences count against control stability too. The large unchanged-
source swings prevent attributing the order-dependent result to this CSS change.
The forward improvement alone is not a confirmed fix, and the reverse failure
alone does not establish that CSS externalization caused a regression.

**Status: screen_failed; acceptance: false.** The candidate does not qualify for
five-sample original/current/candidate validation. Do not rerun it unchanged for
favorable samples or promote it. This screen did not include the original 1c964dc
acceptance baseline, mobile/cold variants, or full responsiveness acceptance.
It does not establish that users would feel a slowdown.

## Evidence and next step

`evidence.zip` contains the complete raw run, adapted workload fixtures, frozen
experiment plan and passing visual assessment. The per-member manifest, extraction
re-audit, full assessment and direct arithmetic are adjacent. All functional and
visual results remain valid; they do not override this memory failure.

Primary product remains f700187, candidate branch is preserved, 2B and later
increments remain blocked. No measurement is active. The next investigation should
use the archived same-source controls to understand the large late-navigation
RSS swing before selecting another bounded product hypothesis. The visual fixture
is now repeatable under documented isolated painting; do not ship that fixture
hint as a presumed memory optimization.

## Offline per-renderer residency review — 2026-10-27

`analyze_stylesheet_residency.py` verifies the unchanged archive SHA and all 25
members, then analyzes every sample and all 40 navigation observations. It tracks
the largest renderer at navigation 1 by the same PID thereafter, rather than
silently following whichever renderer becomes largest. No explicit page-to-PID
binding exists in this archive, so this is a tracked dominant renderer, not a
proven attribution to a particular frame. All renderer PID sets stay stable.

At navigation 20, the unchanged-current repeat difference decomposes as follows
(MiB; later cohort median minus earlier, two samples each):

| Observation | Delta |
| --- | ---: |
| Gate summed RSS | -57.037109 |
| Summed status anonymous RSS | -53.556641 |
| Summed status file-backed RSS | +0.375000 |
| Summed status shared-memory RSS | -3.855469 |
| Tracked renderer RSS | -58.289062 |
| Other renderers combined RSS | +1.251953 |
| JS heap, separately observed | -0.426353 |

Separate smaps measurements show -54.503906 MiB summed Private_Dirty and
-57.230469 MiB PSS. These overlap the status categories and must NOT be added to
or subtracted from RSS. No recorded status shows swap. The dominant change is
anonymous/private residency, not file-backed/shared-clean accounting, JS heap
alone, or renderer replacement.

The four current navigation-20 samples are 505.960938, 529.125000, 420.140625 and
500.871094 MiB. The especially low third value is retained, not excluded. In that
sample, PID 14033 drops 51.605469 MiB RSS from navigation 15 to 20, including
51.730469 MiB anonymous RSS, while JS heap falls only 0.571938 MiB. Navigation 20
also records LCP 696 ms and four long tasks totaling 555 ms; its navigation-15 LCP
is 952 ms. These are observed coincident behaviors, not a claim that GC caused the
long tasks or that lower RSS necessarily means worse performance. Other current
navigation-20 samples report LCP 144–160 ms and no long tasks.

The gate RSS and later status reads are sequential. All navigation-20 residuals
are zero here, but the maximum discrepancy across all checkpoints is 3,022,848
bytes; the analyzer retains it rather than forcing atomic agreement. All 40
original navigation RSS/heap comparison deltas are independently matched back
to the unchanged acceptance-screen assessment. Seventeen focused tests pass,
including changed renderer rank, disappearing/duplicate PID, inconsistent status
components, count mismatches, and nonzero sequential-read residuals.

Earlier allocator recordings separately show Blink heap capacity remaining above
allocated-object size after documents are reclaimed in both original/current
sources. That is consistent with residency/reclamation as a lead, but those are
different runs and cannot reconstruct PID 14033's allocator state. Historical
sampled SVG/layout and inspector-buffer allocation stacks cannot account exactly
for these 53 MiB. No new product patch is justified by this accounting alone.

The remaining attribution gap is the specific native allocator/pages released
during the slow navigation interval. Existing screen data has status/smaps totals,
not allocation maps or time-aligned allocator/GC events for that interval. A next
bounded diagnostic would correlate natural allocator reclamation and per-renderer
RSS during navigation; it must remain separate from acceptance and introduce no
forced GC. No such run was launched in this review. No sample filtering, memory
subtraction, waiver, or change to 2B's blocked status.
