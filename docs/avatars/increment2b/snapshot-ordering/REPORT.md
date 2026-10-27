# Snapshot component ordering — calibration failed its collection-coverage gate

**2B remains blocked.** The bounded current-only diagnostic completed all four
full workloads under frozen harness `f84ef99`. Slot 1 has no recorded app-renderer
MajorGC or CppGC sweep during navigation, so the predeclared coverage gate fails.
No slot was replaced and no source comparison was launched. Product remains
`cf363bf`; cat-gradient candidate `cd94bf3` stays isolated. No 3A, merge or deployment.

## Retained-evidence review before collection

The cat-gradient memory archive reconstructed all 28 logical files. Its independent
re-audit exactly matches the committed assessment: 128 source/probe hashes,
24 cohort files, all 104 metric/checkpoint comparisons and every original failure.
`retained-samples.json` exposes all 40 navigation samples and 32 adjacent intervals,
including renderer PID census, live/total DOM counts and summed status/smaps fields.
Every navigation census is stable within its run. No renderer is excluded or
labelled an application owner merely because it has the largest RSS.

At navigation 5, first-current samples contain 12/24 documents versus 23/23 in the
first candidate cohort. At navigation 10 the counts are 22/34 versus 33/33. This
is inconsistent starting/reclamation state across individual observations, not a
matched native-heap state or proof of an avatar reference leak. Candidate live
nodes stay 1,026 versus current 1,075. The smaller attached page does not resolve
the retained-document/RSS variation.

One candidate run falls from 508.910 to 411.078 MiB between navigations 15 and 20;
its sibling finishes at 524.734 MiB. Native anonymous memory also falls in the former.
The former run is retained in the failed gate, never excluded as an outlier.
Sequential snapshots have no event timestamps, so this is not evidence of which
collection caused that drop. The reader-retention trace already established that
post-GC heap and pending native sweeping can coexist inside a sequential snapshot.
Neither result identifies the former owners of pooled capacity.

A source-supported product intervention was therefore not selected. The exact
new question and falsification gates are frozen in [PROTOCOL.md](PROTOCOL.md):
observe the existing component calls at failing checkpoints 5/10 against natural
GC, without a native dump, polling reader or navigation-10 trace rotation. This
addresses observation ordering only; it does not claim native allocation ownership.

## Fixed calibration result

Exact browser: Chromium 156.0.8078.47; ELF build
`1c5dca8527a61d07372e489142bee26af1bcaf71`. Download/package hashes and runtime setup
are in `setup.json`. Host Chromium 154 was excluded. All four fresh fixture/database/
browser processes used current cf363bf and the unchanged full 30-second workload,
control/probe/probe/control, one sample each. No concurrent heavy analysis ran.

| Slot | Mode | Navigation ms | Observation bound | Largest observation ms | Recorded navigation GC |
|---|---|---:|---:|---:|---|
| 0 | control | 7021.728 | 1.437% | 23.121 | not traced |
| 1 | probe | 7772.796 | 1.915% | 43.498 | no major/sweep event |
| 2 | probe | 6877.750 | 1.797% | 24.039 | 261 selected major/CppGC events |
| 3 | control | 7800.921 | 1.443% | 26.630 | not traced |

Control duration variation is 11.097% (limit 20%). Probe/control ratios are 1.107
and 0.882 (limit 1.20). Entire navigation snapshot work plus trace setup is counted
as a conservative instrumentation-cost bound: every slot stays below 5% and 250ms.
All workloads preserve eight scenario snapshots, five navigation snapshots and
twenty navigations. Both probes preserve the complete expected existing call/read
sequence. Both traces identify one app renderer, record no reported trace loss,
forced-GC or allocator-dump event, and transfer only after sealed navigation 20.
All component brackets at navigation 5 and 10 fall inside conservative trace bounds.

**Calibration still fails:** slot 1 lacks required natural major/sweep coverage.
Absence of a recorded event is not an assertion about unobserved collection before
the trace began. Slot 1 finishes with 48 documents / 19.385 MiB JS heap; slot 2
finishes with 21 documents / 11.222 MiB. These are diagnostic observations, not an
RSS saving or a source comparison: both slots use identical product source.

Slot 2 records one MajorGC between navigation 10 and 15. None of its recorded GC
intervals overlaps a component bracket at checkpoints 5 or 10. The conservative
clock envelope at navigation 20 extends beyond the final trace marker for some
components; this boundary limitation is retained. The protocol requires full
component coverage at failing checkpoints 5/10, not a fabricated exact clock at 20.
One intact probe cannot substitute for the failed four-slot calibration or prove
that historical failing snapshots had the same collection ordering.

## Integrity, audit repair and validation

Audit verifies **128 source hashes and 30 cohort files**. The content-addressed
archive reconstructs **36 logical files / 27 blobs**, including all snapshots,
traces, screenshots, logs, harness and experiment plan. Every reconstructed file
hash verifies; extracted re-audit is identical to `calibration-audit.json`.

The initial auditor raised on missing GC coverage and omitted that slot's timing
summary. `initial-audit.json` preserves that failed audit. A reporting correction
retains the slot's timing/component observations and the explicit coverage failure;
no capture, threshold or qualification predicate changed and no workload reran.
The corrected audit remains calibration_failed. Tests cover this failure alongside
timing failures so reporting cannot hide another failed gate.

Pre-measurement focused tests: **26 passed**. Post-audit checks: **27 passed**, with
the existing Starlette deprecation warning. All four real-HTTP browser workloads
pass their workload assertions; collection coverage is an independent failing gate.
Setup records the initially nonexistent test selection and blocked data-URL smoke;
neither collected application samples or changed browser policy. The localhost
application workloads subsequently completed on the exact browser.

## Next decision

Do not rerun this unchanged calibration to obtain collection events, launch the
source comparison, or infer a product fix from a collection-free slot. Do not
expand shared gradients as a proven memory reduction. All original/current and
current/candidate RSS failures remain unchanged.

The next missing observation remains source-linked native allocation history
through reclamation, including the state carried into navigation from earlier
scenarios. Component timing is now implemented, but a navigation-only trace cannot
recover pre-navigation collection or pooled-page history. Before another capture,
identify a concrete source-ownership discriminant and prove its coverage on a
controlled fixture, then freeze a revised capture window and overhead/coverage
calibration. Merely extending the trace until a GC appears does not establish
ownership. No new product intervention is justified by this result alone.

## Reproduce without browsers

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/snapshot-ordering/evidence.zip \
  --unpack-to /tmp/snapshot-order-evidence
.venv/bin/python -m scripts.avatar_baseline.analyze_snapshot_order \
  /tmp/snapshot-order-evidence/calibration --out /tmp/snapshot-order-audit.json
```

For the archived sample review, reconstruct the cat-gradient archive as documented
in its report, then run `scripts.avatar_baseline.analyze_cat_gradient_samples`
with that extracted memory directory and `--out` pointing to a new JSON file.
