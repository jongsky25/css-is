# Native allocation history — diagnostic passed, 2B still blocked

The fixed four-slot application calibration and all eight planned comparison slots
completed with the frozen harness `1f597dc0401e054928221b22fc7a77fcb2202306`.
Product sources remain original `1c964dc` and candidate `cf363bf`. No product fix,
forced GC, memory waiver or later increment was introduced.

## Validation

All workloads preserve the 13 baseline snapshots, 20 navigations and five navigation
checkpoints. Calibration passes the unchanged timing gates: controls 7,641.50 and
7,856.31ms; probes 7,740.78 and 7,795.08ms. Explicit preparation is below 1% in both
probes. All comparison slots pass capture integrity and per-slot overhead gates;
maximum preparation is 8.169ms and maximum preparation fraction 1.246%.
No recorded drops, agent errors or observed address-lifetime overlaps.

The calibration/comparison audits verify 80 files and 348 source/probe hashes.
Both zipped evidence sets were extracted and independently re-audited, producing
identical assessments (35 and 59 archive members respectively). All 1,160 unique
comparison stack offsets resolve against the exact Chromium debug build. Focused
analysis/retention tests: **33 passed**, one existing Starlette deprecation warning.
Raw data, manifests, audits, symbolized histories and test output accompany this
report. The [protocol](PROTOCOL.md) predates application measurements.

## Findings

These are observed normal-page request counts, not object counts or retained bytes.
“Returned” means a captured request was matched to a pool-return call by the end
of the navigation window. “Shareable” and “SVG” classify the nearest Blink caller
by name; they do not establish avatar ownership.

| Slot | Source | Requests | Returned | ShareableElementData caller | SVG-named caller |
|---|---|---:|---:|---:|---:|
| 0 | Original | 162 | 91 | 6 | 26 |
| 1 | Candidate | 465 | 237 | 39 | 52 |
| 2 | Candidate | 234 | 155 | 27 | 27 |
| 3 | Original | 264 | 152 | 13 | 39 |
| 4 | Candidate | 335 | 250 | 27 | 38 |
| 5 | Original | 113 | 34 | 7 | 26 |
| 6 | Original | 104 | 32 | 5 | 20 |
| 7 | Candidate | 334 | 186 | 25 | 42 |

Candidate-minus-original total requests are +303, -30, +222 and +230 in the fixed
pairs. Same-source variation remains substantial. The histories demonstrate that
many requested pages return to the pool within the measured workload; unmatched
requests are not evidence of a leak, because lifetimes can outlast the capture.

Nearest callers include text creation, logical line containers, paint-chunk
buffers, font fallback tables, computed styles and shared element data. Requests
whose nearest caller names ShareableElementData increase in all four pairs
(+33, +14, +20, +20). SVG-named caller differences are +26, -12, +12, +22.
This supports investigating element-attribute storage as a focused hypothesis;
it does not isolate a particular avatar attribute or establish a byte saving.
The fixture uses the default cat avatar. A plant-only change would not explain it.

## Limits and next action

The instrument observes completed normal-page slow-path calls and their captured
returns. Large pages, allocations fitting existing buffers, unobserved/inlined
entries and unfinished calls at export boundaries remain outside coverage.
Unknown pool returns may predate attachment. A requesting caller does not own all
objects subsequently placed on the page. Address reuse after a pool return does
not prove a pool hit or continuous physical backing: release/unmap is not hooked.
Inclusive stack counts overlap and must not be summed. No whole-heap ownership or
specific application retaining path is established.

The injected agent consumes renderer memory. These runs are diagnostic and cannot
replace the prior memory acceptance comparison. Existing **10/52 source RSS and
16/52 control RSS failures** remain; all prior heap checks passed. 2B remains
blocked and 3A stays paused.

The next bounded step is to compare the rendered cat's element/attribute inventory
and its sharing opportunities against the original, then test one supported
attribute simplification while preserving appearance and SVG ID uniqueness.
ShareableElementData counts alone do not justify replacing UUIDs or claiming a
leak. Any candidate needs visual/functional gates followed by a fixed, uninjected
memory comparison including same-source controls; no unchanged favorable rerun.

Reproduce compact findings from retained symbolized data:

```sh
.venv/bin/python scripts/avatar_baseline/summarize_page_history.py \
  docs/avatars/increment2b/page-history-application
```

`symbolize_page_history.py` re-audits extracted raw evidence before rebuilding
lifetimes and symbols with the matching debug file. `summary.json` retains exact
caller names and pair differences; `symbolized.json.gz` retains individual
observed histories and the symbol-file checksum.
