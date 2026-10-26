# 2B lifecycle-memory correction — candidate under measurement

**2B remains blocked.** No memory budget or callback limit has changed, and 3A
remains paused. Candidate `509cd1a` has a verified lifecycle behavior change but
has not yet established a memory correction or passed final acceptance.

## Unchanged-source reproduction

Pinned hosted run [40287821303](https://github.com/jongsky25/css-is/actions/runs/40287821303)
retained five complete warm-desktop samples per cohort in original/current/current/original
order. Independent audit covers 52 memory comparisons (13 checkpoints × two
metrics × two orders), with valid renderer counts and no application errors.

The forward pair passes all checkpoints. The reverse pair fails seasonal-preview
RSS at **+10.797 MiB**, exceeding the unchanged 10 MiB limit. Repeated measurements
of the same current source differ by +32.195 MiB at navigation 10. This variability
is retained, not subtracted from the budget. The original eleven failures remain
in the preceding final-verification evidence.

See [independent audit](unchanged-hosted/independent-audit.json), [raw archive](unchanged-hosted/evidence.zip),
and [job log](unchanged-hosted/source-job.log). The successful diagnostic workflow
means measurements completed; it does not mean acceptance passed.

## Attribution and candidate

Nine local detailed-allocation probes used Chromium 156.0.8078.47 and the full
warm-desktop sequence. They preserve native allocator events, renderer smaps,
DOM/heap counts, screenshots and source hashes. Allocator categories overlap and
are not substitutes for RSS. Early exploratory variants overlapped parsing of a
preceding trace during startup and cannot establish causal comparisons. The final
original/current/prototype probes were serialized without concurrent analysis.
All are one-sample, instrumented diagnostics, never acceptance cohorts.

The snapshots show varying collection of obsolete document memory. Neither low
JS heap nor fewer current DOM nodes establishes a renderer-memory pass. Individual
runtime/art/search reversals did not provide a reliable root-cause attribution;
restoring the original audio/observer feedback loop is not a viable fix.

The candidate ends avatar-owned animation effects during non-persisted pagehide.
It preserves effects for pages cached for back/forward navigation and leaves
unrelated animations alone. The real-navigation regression check fails on
unchanged source (one owned animation remains running at pagehide), then passes
on candidate (zero). Repeated runtime initialization does not multiply its
pagehide listener. This establishes cleanup behavior, not a memory benefit.

Validation so far: 189 unit/integration/audit checks and nine browser checks pass.
Artwork, SVG markup, avatar CSS, audio and search are byte-identical to f700187;
the avatar template only changes the JS cache version. The runtime adds 146 gzip
bytes. See [validation evidence](candidate-validation/source-equivalence.json)
and [navigation behavior](teardown-functional/candidate.json).

The fixed candidate runs in [40292908517](https://github.com/jongsky25/css-is/actions/runs/40292908517):
original/current/candidate/candidate/current/original, five full samples per
cohort. Review both original-to-candidate pairs, both unchanged-to-candidate
pairs, and same-source repeats. Only a validated candidate may proceed to the
full desktop/mobile, cold/warm acceptance matrix and native callback/frame gates.

## Evidence and continuation

[Local summary](local-probe-summary.json) and [manifest](local-probe-manifest.json)
cover every exploratory variant, including failures and controls. The three
`native-probes-*.zip` files preserve exact renderer allocator events used by the
analysis plus raw scenario records. All 48 packaged files were hash-verified.
Full original traces remain at the paths and SHA-256 values in the manifest.
The local prototype uses an unguarded standalone pagehide listener; hosted
candidate 509cd1a uses the existing initialization guard and is measured separately.

The final CI workflow is prepared to include the teardown regression and a
complete raw-memory audit. It will retain full evidence for 30 days and provide
individually downloadable review parts, preserving trace hashes. It has not been
triggered while the targeted candidate gate is pending. No deployment or merge
to main has occurred.
