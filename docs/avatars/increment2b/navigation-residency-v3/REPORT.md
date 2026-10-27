# V3 calibration failed the overhead gate

All four fixed current-source slots completed. Exact audit verifies 116 source/probe
hashes and 34 files. Ten trace segments (eight navigation, two endpoint) have no
trace loss. Raw measurements match sealed snapshots. Twenty-three focused tests
pass. Extracted archive re-audit is identical.

| Slot | Mode | Navigation ms | Explicit pause fraction | Maximum pause ms |
| --- | --- | ---: | ---: | ---: |
| 0 | control | 8589.557 | <0.001% | 0.001 |
| 1 | trace | 8904.602 | 4.871% | 140.984 |
| 2 | trace | 9057.049 | **5.408%** | 183.293 |
| 3 | control | 8411.225 | <0.001% | 0.002 |

Slot 2 exceeds the predeclared 5% explicit-pause limit. This is a failed calibration,
not a partial pass; no v3 source comparison was launched. All slots remain included.
The 250ms pause and 20% duration checks pass. Four five-navigation segments retain
roughly 3,200–4,500 events each; compressed navigation traces are 93–118KiB each.
The remaining overhead is dominated by trace stop/drain/start at three checkpoints.

Next revision: two ten-navigation segments, eliminating two of those pauses.
Keep the same 64MiB requested buffer, categories, endpoint-only dump and all gates.
This is a changed instrument requiring a NEW fixed calibration; no v3 sample may
be reused or replaced. The small segment sizes justify testing this bounded change,
not assuming integrity. Product remains unchanged and 2B remains blocked.
