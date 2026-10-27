# Application observer calibration: blocked at fresh native qualification

[Latest cloud run](https://github.com/jongsky25/css-is/actions/runs/40532187252)
and [setup PR #519](https://github.com/jongsky25/css-is/pull/519).
Harness **9e47c14dbf1dea37b70fc19fc0f8925c2199bca1**, workflow
**3563eb20bf929eb7f9d3cddfd04a4689a072916f**. No active measurement remains.

The run completed the full fresh native control/probe/probe/control prerequisite.
One probe failed source-labelled natural page reclamation. The application receiver
proof and four application slots were correctly **not launched**. The new lossless
transport therefore has **no application cost result**. Application attribution
qualification and 2B memory acceptance remain false. Product cf363bf and isolated
candidate cd94bf3 remain unchanged; no merge, deployment or candidate promotion.

## Latest native prerequisite

| Slot | Mode | Duration ms | Observation bound | Result |
| --- | --- | ---: | ---: | --- |
| 0 | control | 3599.790 | 2.3850% | pass |
| 1 | probe | 3602.512 | 2.7131% | fail: labelled page returns absent |
| 2 | probe | 3669.911 | 2.8728% | pass |
| 3 | control | 3570.716 | 2.3243% | pass |

Both probes retain all 1,536 exact receiver joins. Slot 1 observes 590 native pool
returns, one natural MajorGC and sweep events, but **zero returned page generations
carrying the selected source labels**, including each required DOM/SVG/style mode.
Slot 2 observes 1,143 pool returns and two natural MajorGCs and passes. Pool activity
and GC presence alone cannot replace the labelled reclamation prerequisite. Timing,
cost, controls and paired gates pass. The maximum observation is 11.464ms.

Runner: standard GitHub Ubuntu 24.04, AMD EPYC 7763, four affinity CPUs, no container
CPU quota, Python 3.12.14, pinned Chromium 156.0.8078.47 and exact ELF build ID,
Playwright 1.62.0 / Frida 17.5.1. SYS_PTRACE is scoped to the job container.
No physical exclusivity claim or resource changes.

Artifact **12745987930** is retained byte-for-byte as
[attempt-v5-failure-evidence.zip](attempt-v5-failure-evidence.zip), SHA256
`5e066d46a033ae2fdc8f68ea3d06f6c37e1bf248e8f29185f4bfb8f235df5b6b`.
All **145** internal manifest hashes verify. An independent native audit exactly
matches the captured failure; [full assessment](attempt-v5-assessment.json).
**80 local/cloud preflight and 102 expanded local analysis tests pass.**

## Complete attempt history

1. Run40516585623 stops before application work because the controller incorrectly
   requires the previous job's CPU model. Preserve its archive; actual failed model
   was not saved. Corrected by full fresh native qualification in the same job.
2. Run40518161854 passes native qualification but fails the application receiver
   proof: 128 getters, zero reference records. Corrected getBoundingClientRect to
   the qualified getClientRects API. The complete failed proof workload is retained.
3. Run40521460498 passes actual-app proof and completes all four full workloads.
   Body-suffix HTML selection shifts when asynchronous offline-badge chrome is
   appended. All four source-type audits fail. Additional offline cost arithmetic
   also exceeds 5%; it does not rescue qualification. Corrected structural scope
   to main#maincontent HTML div/span/a outside avatar wrappers.
4. Run40527921415 passes native qualification, real-app proof, stable source types,
   100% coverage of both groups in both probes, natural source-labelled returns
   and all duration gates. Both application probes exceed the 5% cost gate:
   **5.6545% / 5.3103%**; controls **4.9052% / 4.9544%**. All four full workloads,
   13 snapshots and 20 navigations each are retained. All **196** hashes verify;
   independent audits agree. [Assessment](attempt-v4-assessment.json).
5. The current frozen revision changes only diagnostic transport: unsigned masks
   encode all actual boolean vectors, uniform namespaces and identical attribute
   strings are losslessly shared, and every value is reconstructed inside the
   charged interval. Every DOM read, 32-node group, 128 getters per mount and
   2,560 getters per probe remains. Round-trip/mutation checks pass. Fresh native
   qualification fails as described above, so application effectiveness is unknown.

Each archive and original assessment remains committed. Superseded PRs515–518 are
closed without merge; PR519 remains reviewable. Its opened-only trigger prevents
documentation updates from repeating measurements. Default-branch manual button
registration remains subject to the existing release-version policy.

## Next bounded work

Inspect the retained native generations and trace to establish why selected pages
have no natural labelled return in slot 1, while slot 2 passes. Any new measurement
requires a concrete supported change and separately frozen protocol preserving
all gates. Do not rerun this unchanged build for a favorable GC outcome, force GC,
flush caches, add waits to pad the budget, relax coverage, or substitute prior native
success for qualification of this job. Once this prerequisite passes, measure the
already-frozen lossless application transport before attribution or candidate work.
Earlier memory failures and complete original-baseline acceptance remain unresolved.
