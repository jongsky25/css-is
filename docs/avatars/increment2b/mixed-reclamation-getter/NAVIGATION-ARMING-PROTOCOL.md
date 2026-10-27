# Mixed getter v9 — remove phase RPCs without ignoring unexpected receiver calls

V8 (010d089) completes all four fixed slots and BOTH through-reclamation checks,
including returned labelled generations for DOM/SVG/style and natural major/sweep
history. It fails only the conservative 5% bound: 6.1434/5.6021% in probes. Controls,
paired elapsed, identity and lifecycle gates pass. Full v8 data/failure remains.
Retained cost breakdown: probe census 159.663/154.875ms, heap 27.373/14.772ms, DOM
20.530/12.454ms, setup 8.725/7.491ms, callback prep 27.207/25.817ms. Do not waive
or subtract those costs or rerun v8 unchanged for a favorable margin.

The new cost correction removes two synchronous census phase RPCs per document.
The EXISTING navigation:i RPC now resets/arms the ordinal getter counter before
navigation, assigning first 32/second 32/third 32/fourth 32 receiver observations
to the same avatar0/avatar1/other0/other1 census labels. Every later call receives
an explicit overflow label until the next navigation; NOTHING is silently gated
out after the expected 128. Any getter before or after the declared query bracket,
extra/shifted call, wrong null result or changed identities must fail existing exact
coverage, overflow and host-bracket checks. Native nonreceiver phase labels remain
navigation:i, preserving per-navigation shutdown validation. No application use.

Because the native capture policy changes, freeze and run a NEW exact-type mixed
capability using this same hook before the new four-slot screen. All three document
bytes, 32/group/repeat, element types, null returns and reference identities stay.
Reference geometry hook remains capability-only. If any unexpected call breaks
identity/bracket/count integrity, stop rather than filtering it away.

Only if capability passes, freeze v9 four-slot control/probe/probe/control screen
with unchanged twelve DOM/SVG/style documents, 220ms waits, selected elements, native
history, trace, counters, beacon and effective launch flag. Whole batch timing now
brackets the actual JS census call (no removed RPC remains to measure); all other
cost terms and double-counted native prep remain. This removes actual observer work,
not an accounting component still performed. No new nodes, smaller sample, longer
dwell or pressure to get collection.

Keep every v8 gate, including all-mode labelled returns and MajorGC/native sweep in
BOTH probes plus <=5%/250ms/1.20/20%. Retain every scheduled result with no replacement,
forced GC, dump/snapshot, cache/policy/permission change, concurrent heavy analysis,
RSS adjustment or favorable rerun. Passing could qualify only a separately frozen
application calibration, not an application comparison, 2B, later increment or
product fix. All earlier failures remain.
