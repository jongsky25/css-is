# Original failed GC audit: retention after collection, disposal evidence missing

Offline audit completed 2026-10-28. **Zero new browser measurements.** Original
[run 40532187252](https://github.com/jongsky25/css-is/actions/runs/40532187252),
harness 9e47c14. Read-only re-analysis preserves the failed native prerequisite;
the application workload was never launched. No supported correction is established.

## What the failed and passing probes actually show

| Original measurement | Failed slot 1 | Passing slot 2 |
| --- | ---: | ---: |
| Exact observed-request receiver joins | 1,536 | 1,536 |
| Natural major collections recorded | 1 | 2 |
| First-major marked JS global proxies | 11 | 3 |
| First-major used heap after collection, bytes | 2,501,964 | 756,936 |
| Stage 6 documents / nodes | 9 / 45,063 | 1 / 9,007 |
| Source-labelled generations returned in window | 0 | 10 |
| Labelled returns before second major | n/a | 5 |

The failing native instrument has complete receiver joins and passes its timing,
clock/storage and cost checks. Its missing prerequisite is **source-labelled page
reclamation**, not missing receivers. The original coarse error string remains
unchanged in the assessment; it must not be read as a failed receiver-coverage test.

The failed trace contains a natural major collection, ephemeron/weak-global-handle
processing, CppGC atomic weakness callbacks and observed sweeping. It is not a
capture that simply never ran GC. The passing probe returns five labelled page
generations before its second major collection, covering DOM/SVG/style. Thus a
universal requirement for a second major is not supported. Some of its other
labelled pages do return later; this is not a guarantee about every generation.

## Chronology before first marking

Both probes have **21 completed native Document::shutdown calls**, **six pagehide
markers** and **six server beacon receipts** definitely before the first observed
CppGC incremental-marking start. The three navigation 6 shutdown calls return at
least 49.822ms before marking in the failed probe and 36.332ms before marking in the
passing probe, using conservative clock envelopes. No midpoint clock is assumed.

The first-major V8 statistics are paired by enclosing trace interval AND thread,
not by matching heap values (the passing probe reports the same heap size twice).
All pairings are unique. Weak processing and sweeping occur in the first CppGC
epoch in both probes. The failed trace's extra reported documents/nodes persist
after that observed collection; no retaining path or object death is recorded.

Important limits: shutdown pointers identify Documents, while getter receivers
identify Elements. The capture cannot map them to exclusive ownership. Trace
phase scopes are not proof that whole sweeping finished, and a page not returning
to the pool does not show that every selected object on that page remains live.
Counter totals and eight extra marked proxies are not eight identified context IDs.

## What the pinned source resolves

Chromium 156.0.8078.47 / V8 revision 392e44423f46d75904da712fadea4c7d5d97967f:

- Navigation requests LocalWindowProxy::DisposeContext with global-object-detached
  and frame-reused status. Its initialized path calls embedder/debugger release,
  detaches the global, disposes ScriptState data, then notifies V8. Other lifecycle
  branches can return early. Document shutdown is not evidence that those steps ran.
- ScriptState disposal and V8 context-disposal notification are absent as call
  records in the OLD capture. V8.GCNotifyContextDisposed is only emitted on a
  conditional dependent-context/idle-GC branch; zero such trace events cannot
  establish that notification was skipped for a main frame.
- Linux context-disposal notification resets allocation/garbage heuristics; it does
  not promise an immediate collection. The explicit memory-pressure collection in
  Blink's helper is Android-only and is not a proposed fix for this Linux runner.
- The detached-context diagnostic list holds weak references. Its existence does
  not establish a strong retaining root.
- mark.js_global_proxies increments during proxy visitation; it is a visited-object
  count, not a root count or a retaining-edge report. Both traces also contain a
  conservative-stack-scanning scope despite the NVP stack field being false. Neither
  a boolean nor an empty phase payload identifies/rules out actual stack roots.
- Map-retention processing is present in both traces. Source ShouldRetainMap first
  requires its constructor already to be marked/live. Phase presence alone is not
  grounds to blame retained maps or disable an engine flag to improve the result.

Pinned URLs, full-source hashes, excerpts, debug symbols and entry disassembly are
preserved under [source/](source/manifest.json). No engine/runtime setting changed.

## Integrity and repeatability

The original ZIP SHA256 remains
`5e066d46a033ae2fdc8f68ea3d06f6c37e1bf248e8f29185f4bfb8f235df5b6b`.
All **145** internal hashes verify. The independently executed original native audit
is exactly identical, including its failure; its canonical result SHA256 is
`963ed948badbaf94dd99d4fb0c4e7eb61711776912fd03da8377bba0d1735a50`.
**36 focused tests pass**, including conservative time-order boundaries, unique
GC-statistic pairing, duplicate/missing/wrong-thread rejection and existing
membership analysis. [Full assessment](assessment.json) includes all four original
cohorts, native joins/returns, phases, counters, markers and uncertainty.

Reproduce without launching a browser:

```
.venv/bin/python -m scripts.avatar_baseline.audit_original_gc \
  --out /tmp/original-gc-audit.json
```

No failed sample is rescued. Native/application qualification and 2B acceptance
remain false. Product cf363bf and isolated candidate cd94bf3 are unchanged.

## Next bounded work

[Prepared minimal disposal-witness design](NEXT_PROBE.md) targets the actual missing
transition: proxy lifecycle/reuse arguments and nested ScriptState disposal/V8
notification before natural GC. Four low-rate C callback sites replace broad
handle tracing; no object-field reads, snapshots or Runtime subscription. It must
be implemented, ABI-validated and frozen before capture. No new collector or run
was launched in this audit. No cleanup patch is justified unless the failed state
is captured with a demonstrated missing/incorrect transition; successful disposal
would instead direct investigation to retaining edges.

No unchanged retries, forced collection, cache flush, threshold waiver, candidate
promotion, later increment, merge or deployment. Original full product-memory
acceptance remains outstanding.
