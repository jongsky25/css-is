# 2B lifecycle-memory correction — candidate rejected

**2B remains blocked. Candidate 509cd1a is rejected as a memory fix.** Its
real-navigation cleanup behavior passes, but both hosted memory orders fail.
The experiment is preserved separately; the primary verification branch retains
the unchanged f700187 product. Full acceptance was not run because the targeted
gate failed. 3A and later increments remain paused.

The independent audit verified **134 source-file hashes and all 234 comparisons**
across six complete cohorts (30 full samples), with no source, protocol, or
renderer-count errors. Against the original baseline, the candidate fails eight
RSS checks and one JS-heap check:

| Order | Checkpoint | Metric | Median increase (MiB) |
|---|---|---|---:|
| Forward | navigation 5 | RSS | 28.418 |
| Forward | navigation 10 | RSS | 28.738 |
| Forward | navigation 10 | JS heap | 10.063 |
| Forward | navigation 15 | RSS | 26.992 |
| Forward | navigation 20 | RSS | 19.496 |
| Reverse | navigation 5 | RSS | 10.434 |
| Reverse | navigation 10 | RSS | 22.598 |
| Reverse | navigation 15 | RSS | 27.660 |
| Reverse | navigation 20 | RSS | 21.426 |

The limit remains 10 MiB. Against the unchanged current product, the candidate
also fails reverse-order RSS checks at navigations 5, 15 and 20 (+20.789, +15.828,
+13.004 MiB). The local one-sample improvement did not establish a repeatable
memory benefit. No sample was excluded or budget relaxed.

See [independent candidate audit](candidate-hosted/independent-audit.json),
[raw candidate evidence](candidate-hosted/evidence.zip), and
[provenance](candidate-hosted/provenance.json).

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

The rejected candidate completed [40292908517](https://github.com/jongsky25/css-is/actions/runs/40292908517):
original/current/candidate/candidate/current/original, five full samples per
cohort. All original-to-candidate and unchanged-to-candidate pairs and same-source
repeats were retained and recomputed. Its targeted gate failed; no full matrix
or callback/frame acceptance run was started on this rejected source.

## Evidence and continuation

[Local summary](local-probe-summary.json) and [manifest](local-probe-manifest.json)
cover every exploratory variant, including failures and controls. The three
`native-probes-*.zip` files preserve exact renderer allocator events used by the
analysis plus raw scenario records. All 48 packaged files were hash-verified.
Full original traces remain at the paths and SHA-256 values in the manifest.
The local prototype uses an unguarded standalone pagehide listener; hosted
candidate 509cd1a uses the existing initialization guard and is measured separately.

The experimental branch retains its teardown regression. The primary final CI
workflow retains a complete raw-memory audit. It will retain full evidence for 30 days and provide
individually downloadable review parts, preserving trace hashes. It was not
triggered because the targeted candidate gate failed. No deployment or merge
to main has occurred.

## Next discriminating experiment

Do not repeat the rejected candidate or rerun unchanged cohorts hoping for a pass.
The unresolved hypothesis is that differing collection of discarded documents
explains the late-navigation memory delta. Capture natural Blink/V8 collection
events, navigation timestamps, renderer-role/PID history and native allocation
profiles together on original and unchanged current source, in both orders.
Map app/preview and browser-UI renderers for attribution; retain the complete RSS
sum as the gate. The existing target census contains Chromium omnibox UI targets,
and renderer PID sets change after the background probe. Neither observation is
permission to exclude memory or change the budget.

Matching Chromium security-build symbols are now available and verified:
`1c5dca8527a61d07372e489142bee26af1bcaf71`. Native stack sampling resolved 868
Chromium frames in the picker probe and 409 in a full-sequence endpoint probe.
These samples cover target-renderer allocations, not complete RSS or all renderer
lifetimes; they do not establish a source cause. See [native sampling evidence](native-sampling/assessment.json).
Only choose a new product correction after an attributable retained allocation
or lifecycle reference is identified. No forced collection, extra cache flushing,
RSS subtraction, or favourable-sample replacement is permitted.
