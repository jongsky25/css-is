# Shared cat gradients: appearance preserved, memory screen failed

Implemented candidate **cd94bf35d29b796ca0d6467756221e4b545a40be** on
`codex/avatar-shared-cat-gradients`, based on reader/current-avatar product
`cf363bf`. The two identical illustrated-cat gradients now live once in the
existing page registry. Cat fill attributes use stable references; plant scopes,
SVG geometry, CSS, animation hooks and runtime/backend code are unchanged.
The candidate remains isolated and unpromoted. **2B is still blocked; 3A is paused.**

## Inventory and visual/functional gates

For six identical stage-1 cats, including the once-per-page registry:

| Source | Elements | Attributes | Distinct attribute vectors | Attribute UTF-8 bytes |
|---|---:|---:|---:|---:|
| Original 1c964dc | 422 | 1,234 | 172 | 15,067 |
| Current cf363bf | 512 | 1,516 | 236 | 20,113 |
| Candidate cd94bf3 | 471 | 1,426 | 186 | 19,333 |

This saves 41 elements, 90 attributes and 50 distinct attribute vectors relative
to current. These are rendered-markup counts, not native retained bytes or proof
that all equal vectors share storage. Fixture IDs use deterministic counters;
production UUIDs differ in length. The candidate still exceeds original markup.

All **30 visual sheets / 2,880 cells** pass exact pixels and normalized DOM,
paint-style, geometry and transform comparisons. Coverage: all 16 species and six
stages, five outfits, three backgrounds, live and static preview. Normalization
only removes nonpainting cat defs from the comparison and renames equivalent
gradient references; unique IDs and resolved fills are independently checked.
The previously established isolated-paint fixture and `caret='initial'` are used.
No pixel tolerance. Both consecutive screenshots within each document agree.

The new real-HTTP test passes across Home, profile, Wellness, appearance admin and
return navigation, including removal of one cat while others remain. Eight
applicable existing interaction/geometry/resize/motion/chase/static-preview tests
pass. **32 focused gate tests pass.** Existing Starlette deprecation warning only.

The initial regression selection also included `test_pagehide_cleanup`, which
fails: one avatar animation remains running during nonpersisted pagehide. The
same test on unchanged verification source reproduces exactly the same values.
This was an incorrect selection of an existing failing diagnostic, introduced
by 186feeb; prior lifecycle fixes were not promoted. Both failures remain archived.
The [protocol](PROTOCOL.md) records the correction **before** memory collection.
No teardown fix or complete functional acceptance is claimed.

Visual v1 was intentionally interrupted after five passing sheets because nested
Playwright state transport was slow. Its partial outputs/log are retained. V2
transfers the identical snapshot data as a JSON string and completes all 30 sheets.
No product change, dropped failure, changed comparison or tolerance between them.
Visual v1 harness 1191440; v2 harness 82a8926.

## Fixed uninjected memory screen

Frozen harness **52ed2ea48af397c146c24013f2acea9f2726a77f**; Chromium
156.0.8078.47. All four cohorts in current/candidate/candidate/current order complete,
two full 30-second warm-desktop workloads each (eight workloads). No Frida, CPU
profiler, native sampling, allocator dumps, forced GC or concurrent heavy analysis.
No replacements. Every sample and all 13 RSS/heap checkpoints are preserved.

| Comparison | RSS result | Navigation 10 delta | Navigation 20 delta |
|---|---|---:|---:|
| Forward candidate minus current | Fails at navigation 5 and 10 | +16.301 MiB | -29.289 MiB |
| Reverse candidate minus current | Within source budget | -27.348 MiB | -20.326 MiB |
| Current repeat, later minus earlier | 4 absolute-limit failures | +19.770 MiB | +27.416 MiB |
| Candidate repeat, later minus earlier | 6 absolute-limit failures | -23.879 MiB | +36.379 MiB |

Forward navigation 5 is **+11.699 MiB**. The unchanged source budget is +10 MiB;
repeat controls require absolute deltas <=10 MiB. Both control cohorts are unstable.
All JS-heap checks pass, and renderer counts match. The audit evaluates **104**
metric/checkpoint comparisons: 2/26 source RSS failures and 10/26 absolute control
RSS failures; no heap failures. `memory-assessment.json` contains every sample,
median, count and delta.

Although navigation 20 improves in both source orders, the forward navigation 10
regression and unstable controls prevent qualification. The predeclared >=5 MiB
improvement at navigation 10 and 20 in both orders is not met. This is a failed
allocation screen, not a complete original-versus-candidate 2B acceptance run.
Prior original/current memory failures remain in force. No larger validation,
promotion, merge, deployment or later increment was started.

## Evidence integrity and conclusion

Independent audit: **128 avatar/backend/probe hashes and 24 cohort files** verify;
no identity or completeness errors. The extracted memory archive re-audits to an
identical assessment. Content-addressed archives preserve all logical files while
storing identical files once: memory 28 files / 20 blobs; visual/functional 162
files / 119 blobs. Every reconstructed file hash verifies. Manifests include the
archive hashes and logical-path mapping, including the interrupted visual run,
new test, regression failure and unchanged pagehide control.

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/shared-cat-gradients/memory-evidence.zip \
  --unpack-to /tmp/cat-gradient-evidence
.venv/bin/python -m scripts.avatar_baseline.analyze_cat_gradients \
  /tmp/cat-gradient-evidence/memory --harness-ref 52ed2ea \
  --out /tmp/cat-gradient-audit.json
```

Sharing the cat gradients is a verified markup reduction with preserved appearance,
but this experiment does **not** establish a reliable RSS saving or unblock 2B.
Do not rerun the unchanged candidate until a favorable result appears, expand it
across species as a proven memory fix, or recycle the already-failed lifecycle
candidate without new evidence. The remaining problem includes substantial
same-source native-memory variation; low JS heap or fewer attributes does not
resolve the acceptance failure.
