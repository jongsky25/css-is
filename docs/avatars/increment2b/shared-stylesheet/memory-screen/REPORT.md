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
