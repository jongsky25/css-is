# Lifecycle v6 — fixed smaller membership sample, unchanged document lifecycle

V5 (97bd66c) preserves all four complete slots. It fails 5% observation bounds in
both probes and final control; controls vary over 20%, and the first probe/control
ratio exceeds 1.20. No favorable rerun or reinterpretation follows. Its retained
cost breakdown identifies census work as dominant: 294/444ms in probes, versus
47/103ms for sequential counters and 49/64ms native preparation (double-counted
inside census where applicable). Dropping counters would not close the main cost.

V6 changes only the PREDECLARED membership sample size: last 32 avatar and first
32 other paths, twice, instead of 128. All 4,096 paths per SVG group and all twelve
documents still render. No document, wait, GC event or measured memory sample is
removed. It observes 1,536 receiver calls per probe, not 6,144, and cannot claim
membership coverage of the unselected elements. The source labels still straddle
the two same-type SVG groups' boundary to test mixed membership.

One batch and two phase RPCs per document remain. Native ordinal blocks now have
32 receivers; overflow, missing, duplicate, shifted and mismatched repeats must
fail. The versioned membership profile validates exactly 32 selected elements and
4,096 fixture elements per group. All-selected observed-request coverage >=90%,
positive coverage in every phase, exact repeats/disjoint identity, mixed pages,
no source/DOM/renderer ambiguity and no drops remain. The original within-window
reclamation requirement remains independently failed if no labelled return occurs.

Freeze before four NEW fresh control/probe/probe/control slots. Every other v5
lifecycle, beacon, native hook, full trace and counter bracket remains. Same 5%,
250ms, 1.20 and 20% thresholds. Every earlier failure remains. No larger fixture,
longer dwell, forced GC, changed cache or browser policy, application collection,
RSS subtraction or product correction. This is a smaller explicit diagnostic
sample, never a change to 2B's memory budget or complete acceptance matrix.
