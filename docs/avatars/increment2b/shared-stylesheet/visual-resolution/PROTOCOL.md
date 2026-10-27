# Controlled paint comparison

Normal unchanged-source preview comparisons show different pixels with identical
DOM attributes, selected computed paint/layout styles, bounding rectangles, SVG
bounding boxes, and screen transformation matrices. One raster thread does not
remove the difference. The normal sheet has 5 compositor layers (2 draw content).
A visual-fixture-only `.avcard svg {will-change:transform}` creates 101 layers
(98 draw content); CDP reports WillChangeTransform. This tests whether isolating
paint makes the fixture repeatable. It is not a product change or memory setting.

First complete the isolated unchanged-source preview control across 15 sheets.
Then compare current f700187 to candidate 6960562 across all 30 sheets (2,880 cells),
requiring exact CSSOM, exact selected DOM/style/geometry state, exact pixels and
stable consecutive screenshots. No pixel tolerance, removed artwork, or product
CSS rewrite. Preserve raw uncontrolled failures and intermediate fixture failures.
The exact CSS extraction contract still reconstructs the original template.

The state probe records every main-subtree element's attributes and leaf text;
computed SVG paint/layout properties listed in visual_state.py; DOM rectangles;
SVG getBBox and getScreenCTM. It does not assert every possible computed property
or inspect browser-internal path-cache algorithms. Rendering-layer isolation can
establish a repeatable comparison without identifying the specific Skia routine.

The memory screen remains the previously fixed eight workloads, both orders and
same-source controls. It runs the actual application without this paint hint,
state probe, layer inspection, routing or screenshots added by this diagnostic.
The controlled visual result alone is not 2B acceptance or a production paint fix.
