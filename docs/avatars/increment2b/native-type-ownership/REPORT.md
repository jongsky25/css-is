# Native object types recovered from the existing raw dumps

**All eight endpoint inventories reconcile exactly. No new browser run or product
change. 2B remains blocked.** The earlier allocator summary filtered out the
`blink_objects/blink_gc/main/*` view. The raw archives retained it, including type
names, allocated bytes and object counts. This analysis recovers that evidence
without taking another snapshot or triggering collection.

The 82-member archive is hash-verified and independently re-audited against frozen
sources/harness. Every type's global bytes/count equal its sum across pages; the
sum of global type bytes equals the heap's allocated-object bytes in all eight
slots. Page/global/suballocation views overlap and are NOT added together. Type
IDs vary between processes, so comparisons use full type names, merge duplicate
names, and retain original labels. Thirty-three focused tests pass.

## What accounts for the largest same-source endpoint difference

Candidate slots 4 and 7, at the dump **after navigation 20**:

| Measure | Slot 4 MiB | Slot 7 MiB | Difference MiB |
| --- | ---: | ---: | ---: |
| Blink heap reported size | 85.375 | 52.750 | 32.625 |
| Pooled memory | 40.875 | 17.250 | 23.625 |
| Allocated objects | 20.517 | 11.386 | 9.131 |
| Subset: type name contains `SVG` | 2.484 | 1.241 | 1.243 |

Pooled memory is included in heap size; allocated objects occupy heap pages.
These rows are not independent RSS components. The small residual between pool
plus object differences and heap-size difference reflects other page capacity;
no RSS subtraction or acceptance adjustment is made. In particular, this later
32.625MiB heap difference is NOT a decomposition of the earlier 60.488MiB RSS gap.

Largest individual type increases in slot 4 versus slot 7:

| Type | Additional allocated bytes | Additional objects |
| --- | ---: | ---: |
| LogicalLineItems | 656640 | 360 |
| ComputedStyle | 619416 | 8603 |
| CachedMatchedProperties | 354280 | 2605 |
| Text | 336080 | 4201 |
| ImmutableCSSPropertyValueSet | 220080 | 2709 |
| FontDescription → FontFallbackList backing table | 199744 | 8 |
| ComputedStyleBase::StyleSVGData | 194640 | 2433 |
| UniqueElementData | 191520 | 1710 |
| LayoutResult | 191280 | 2391 |

This is broad document/style/layout allocation, with SVG types as a subset.
A class name is not a component owner: SVG also covers icons and image documents,
and avatar work can allocate general style/layout classes. Neither the 1.243MiB
SVG-name subset nor its absence from another class proves an avatar's total cost.

Slots 4/7 contain 11/5 HTMLDocument objects and one XMLDocument each at this
endpoint. Counts of Text, LayoutSVGPath and style objects rise along with the
extra documents. These are allocated objects, potentially including garbage;
they are not a graph of strongly reachable references or a proven persistent leak.

## Every slot, including opposite-direction source results

| Slot | Source | Allocated MiB | SVG-name subset MiB | HTML / XML documents | Pooled MiB |
| --- | --- | ---: | ---: | --- | ---: |
| 0 | original | 22.611 | 2.658 | 13 / 1 | 1.500 |
| 1 | candidate | 9.932 | 1.226 | 5 / 1 | 38.250 |
| 2 | candidate | 7.283 | 0.826 | 3 / 1 | 33.000 |
| 3 | original | 6.711 | 0.757 | 3 / 1 | 14.875 |
| 4 | candidate | 20.517 | 2.484 | 11 / 1 | 40.875 |
| 5 | original | 50.015 | 6.345 | 31 / 1 | 0 |
| 6 | original | 38.944 | 4.560 | 23 / 1 | 16.500 |
| 7 | candidate | 11.386 | 1.241 | 5 / 1 | 17.250 |

All four source pairs and four repeat-control pairs have complete type differences
in `analysis.json.gz`. Candidate endpoint allocated/SVG-name bytes are lower in
three source pairs and higher in one. Original and candidate both retain multiple
whole-document inventories. No consistent source-specific owner follows from these
endpoints, especially with the preserved unstable RSS controls.

## Exact-browser source reveals two important limits

Pinned Chromium `156.0.8078.47`, V8 `392e44423f46d75904da712fadea4c7d5d97967f`:

1. `BlinkGCMemoryDumpProvider::OnMemoryDump` emits per-page type statistics and
   `blink_objects` global type totals. That is the previously unexamined raw view.
   The family filter in the earlier summary did not retain it; the raw capture
   did. There was no trace-data loss and the old RSS arithmetic is unchanged.
2. `CppHeap::CollectStatistics → HeapBase::CollectStatistics(kDetailed)` calls
   **`sweeper_.FinishIfRunning()`**, then resets linear allocation buffers before
   traversing the heap. `determinism: none` avoids the explicit forced-GC branch,
   but does NOT mean detailed statistics preserve pending-sweep state. Existing
   dumps occurred after sealed measurements; those measurements remain unchanged.
   The older in-workload dump experiment was already classified as intrusive.
3. `HeapStatisticsCollector` adds pooled memory to heap committed/resident-size
   statistics. The header defines the pool as memory not directly used by the
   heap. Pool pages contain no current allocated objects to enumerate by class.
   A post-hoc type histogram therefore cannot assign their historical owner.
4. `DOM.getDetachedDomNodes` is also unsuitable for preserving the transient state:
   it calls `GetDetachedJSWrapperObjects`, which begins with
   **`CollectAllAvailableGarbage`**. This API was inspected in source, not invoked.

All fetched files, exact URLs and SHA-256 hashes are retained under `source/`.
The initial three cppgc path lookups returned 404; BUILD.gn revealed the moved
`cppgc-internal` paths. Corrected files are pinned to the same V8 revision; discovery
failures are retained in the manifest. No collection exception was requested or used.

## Fix decision

The task now identifies the object classes in the available endpoint inventory:
layout/line data, computed styles, cached CSS properties, text/DOM and SVG types.
It also establishes why that inventory cannot identify an owner for the larger
unused pool. Do not repeat a detailed dump hoping to preserve an unswept state,
or add avatar teardown based only on these class names.

The remaining causal question is **which navigation allocations grow the page
pool before those objects are reclaimed**. That requires allocation history tied
to page/source, not another endpoint object inventory. The prior native malloc
samples and post-GC snapshots did not provide that history. Any new probe must
first demonstrate that coverage on a controlled fixture; another unchanged
acceptance run would not answer it. Per-component observation timing is still
needed if a future capture compares GC ordering inside snapshots.

No product reduction is selected without that causal evidence. The shared-avatar-
stylesheet candidate's earlier failed memory screen remains failed. The 10 source
RSS failures and 16 repeat-control failures remain; no waiver, later increment,
merge, deployment or active measurement. This report supersedes earlier language
suggesting the raw dumps lacked type inventories, not the earlier acceptance gates.

## Reproduce

```sh
.venv/bin/python -m scripts.avatar_baseline.analyze_blink_types \
  docs/avatars/increment2b/sqlite-reader \
  --out docs/avatars/increment2b/native-type-ownership/analysis.json.gz
.venv/bin/python docs/avatars/increment2b/native-type-ownership/summarize.py
```

The analyzer first re-audits the existing comparison, then selects each identified,
bounded app-renderer dump. Tests reject missing/mismatched type totals, invalid
units/hex values, duplicate fragments and wrong dump identities, and prevent false
differences from process-local type IDs or double-counted page/global views.
