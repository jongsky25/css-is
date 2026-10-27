# Visual instability localized to painting; fixture isolated

Unchanged-source comparisons reproduce different pixels despite exact agreement
in DOM attributes/leaf text, selected computed SVG paint/layout styles, bounding
rectangles, SVG bounding boxes, and screen transform matrices. Consecutive
screenshots and state snapshots within each document remain stable.

| Comparison | Sheets | Pixel failures | State failures |
| --- | ---: | ---: | ---: |
| Unchanged source, normal shared painting | 15 | 6 | 0 |
| Unchanged source, one raster thread | 15 | 9 | 0 |
| Unchanged source, isolated avatar painting | 15 | 0 | 0 |

The fixture's `.avcard svg {will-change:transform}` isolates painting: CDP shows
101 compositor layers (98 drawing content), versus 5 (2 drawing content) normally,
and reports the WillChangeTransform reason. A separate toggle check on both
current/candidate documents found exactly 96 computed-style changes, all
`will-change: auto` → `transform` on outer SVGs. No DOM attribute, other measured
style, bounding box, or transformation matrix changed.

This localizes the mismatch to rendering rather than changed artwork/layout and
provides a repeatable controlled paint fixture. It does not identify the precise
browser-internal path-cache/antialiasing routine, claim all computed CSS properties
were measured, or fix normal Chromium rendering itself. Earlier software rendering
and pause/readiness attempts remain failed evidence, not discarded samples.

The initial all-computed-property diagnostic was interrupted because Playwright's
nested-object serialization was excessively expensive; it completed no sheet.
The replacement captures relevant paint/layout properties. Later serialization
uses JSON strings to avoid the transport overhead without changing the state data.
The full normal control completed; it was not replaced by favorable samples.

The first complete current/candidate comparison (`d84cf76`) passed all thirty
pixel and cross-source state comparisons, but the new within-document check
caught 2,880 empty style attributes appearing on hidden volume inputs across the
thirty live-document captures. Playwright's default caret hiding sets and clears
`caret-color`, leaving `style=""`. Its source excerpt/hash and the failed result
are preserved. `caret='initial'` avoids that test-induced mutation; a dedicated
browser regression verifies both stable pixels and unchanged input markup.

The corrected full comparison is run from `1a3844a`, still against unchanged
product references f700187/6960562. Its assessment is archived with all diagnostic
outputs. Exact pixels, CSSOM, and measured state must all pass for
all thirty sheets (2,880 cells); the memory runner enforces that prerequisite.
Forty focused tests pass, including subpixel geometry changes, missing nodes,
paint-style differences, and rejection of equal pixels with unequal state.

**The paint hint and read-only state/layer probes are fixture-only.** They are
absent from the candidate product and the fixed memory screen. Passing this
controlled comparison permits the allocation screen, not 2B acceptance.

Corrected full run: all 30 sheets (2,880 cells) pass exact pixels, CSSOM,
selected DOM/style/geometry equality and within-document stability. The fixed
memory screen may now run; no product or memory-rendering settings changed.
