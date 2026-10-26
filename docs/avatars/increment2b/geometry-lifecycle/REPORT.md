# Geometry lifecycle candidate — not promoted

The counterbalanced source screen identifies geometry observation as a lead:
disabling only observer registrations improves navigation-10/20 RSS in both
orders by approximately 15–29 MiB, without a >10 MiB worsening elsewhere.
See [screen](../source-isolation/REPORT.md). This does not establish acceptance.

The candidate replaces per-wrapper observer closures with one shared geometry
observer, observing the body, wrappers and play containers. Its callback measures
currently connected wrappers after layout. On non-persisted pagehide it disconnects
the observer and cancels a pending geometry RAF; persisted pages keep their state.
Artwork, avatar CSS, audio and search are byte-identical to f700187. The only
template change is the runtime cache version.

Nine real-browser checks pass. The first four cover: resize/scroll/drag/chase, transition geometry,
unused plant-head reads, and shared observation with real navigation teardown.
The existing repeated-runtime-evaluation check confirms stable listener counts.
The additional motion-preference, chase-write, pointer, static-preview and search-boot checks also pass. The new shared-observer regression fails on unchanged f700187 (two wrapper observer owners) and passes on candidate (one).
44 focused accounting checks pass. These are functional results, not memory proof.

The hosted gate requested five full warm-desktop samples for each arm in
original/current/candidate/candidate/current/original order on pinned Chromium
156.0.8078.47. The independent raw/source audit covers every checkpoint and both
orders. The gate did not pass. Full acceptance and later increments remain paused.

Hosted run: [40315985656](https://github.com/jongsky25/css-is/actions/runs/40315985656), source `cccf843825b5705df5f04242cd25f23fb755280f`. Functional and accounting steps passed. The reverse unchanged-current cohort timed out during its third sample while waiting for the Halloween seasonal preview; only two of its five samples completed. All other cohorts completed five samples. The workflow failed; its on-success audit step was skipped. The raw artifact was downloaded and independently audited locally.


## Final independent audit

Overall status is **inconclusive**, with one invalid current-control cohort;
106 source hashes and 156 comparisons from the valid cohorts were recomputed.
The complete forward candidate/original pair has six RSS budget failures:

| Checkpoint | RSS increase MiB |
|---|---:|
| background | 11.996 |
| navigation 1 | 10.984 |
| navigation 5 | 19.824 |
| navigation 10 | 48.000 |
| navigation 15 | 41.219 |
| navigation 20 | 49.984 |

The unchanged limit is 10 MiB. The complete reverse candidate/original pair
passes, but that does not erase the forward failures. Against unchanged current
in the valid forward pair, candidate also worsens navigation 10 by 12.848 MiB
and navigation 20 by 14.688 MiB. The reverse current comparison is unavailable;
its two completed samples are retained, never substituted for a five-sample cohort.
The original same-source repeat also exceeds 10 MiB at four checkpoints (up to
24.719 MiB), demonstrating variability without providing a budget waiver.

See [independent audit](hosted/independent-audit.json), [full raw artifact](hosted/evidence.zip),
[producer assessment](hosted/producer-assessment.json) and [source job log](hosted/source-job.log).
All 27 complete samples and the failed-control log are preserved. The artifact
SHA-256 matches GitHub's digest; no sample or failed pair was discarded.

Candidate cccf843 remains on its experimental branch and its workflow is paused.
The primary verification branch retains f700187 product, plus the screen and
candidate evidence. No full acceptance run, merge to main or deployment occurred.
The local observer-disable screen did not establish that sharing/disconnecting
observers would fix memory; the implemented correction failed that test.
The SVG source screen remains only a lead, not an acceptable visual rollback.
Before another product change, validate the exact isolated intervention with
five samples in both orders and investigate the preview timeout separately;
do not rerun this candidate hoping for a favourable collection schedule.
