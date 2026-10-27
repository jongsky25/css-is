# Absent-attribute native receiver — capability before measurement

Prior lifecycle v6 fails overhead/control stability despite selected source-labelled
reclamation in one probe. Do not rerun it unchanged. Next supported intervention is
a different receiver observable, not a product fix or relaxed memory gate.

Pinned Element::getAttributeNodeNS(namespace,local_name) returns Attr*. At exact-build
symbol offset 0x100cce80, entry uses rdi as Element* (the first ordinary native
argument; pointer result has no hidden structure-return argument). Existing pinned
source under native-element-membership/source/element.cc constructs QualifiedName,
synchronizes the queried attribute, looks it up, and returns nullptr when absent,
before EnsureAttr. It does not call geometry/layout or construct DOMRectList.
Attribute synchronization/interning may still allocate; do not call it allocation-
free or assume low overhead. Source excerpt/hash and disassembly accompany this plan.

Freeze before ONE synthetic capability run on Chromium 156.0.8078.47 / ELF
1c5dca8527a61d07372e489142bee26af1bcaf71 / Frida 17.5.1. Load the known empty identity
fixture, attach before the unchanged 4,096+4,096 path fixture. For the last 32 avatar
and first 32 other paths, twice each, compare getClientRects receivers against
getAttributeNodeNS('urn:css-is:membership:absent','absent') receivers in exact DOM
order. The geometry reference hook is enabled only in this capability, never a
claimed performance/control slot. Keep all outputs and failures; no replacement.

Required: 128 native getter observations match 128 geometry reference observations;
32 distinct receivers per phase, exact repeats and disjoint groups, native null
return AND JS null result for every lookup, all 4,096 fixture nodes independently
counted, unchanged DOM hash, exact native build/renderer/source identities, no agent
error or drop. All native calls must lie inside their known query brackets. No
native pointer dereference, forced GC, heap snapshot, memory dump, pressure event,
cache flush, browser-policy change, application DB, user data or external endpoint.
The native geometry reference allocates rectangles, so this run is NOT an overhead
measurement, memory comparison or qualification for application collection.

Failure stops before any four-slot measurement. A passed exact-receiver capability
would permit freezing the four-slot observation-cost screen with the same v6 full
fixture, twelve documents, selected 32 paths/groups/repeats, native lifecycle/beacon
and GC/counter coverage, unchanged 5%/250ms/1.20/20% gates. It does not itself launch
that screen, accept 2B, waive missing reclamation, or justify a product change.
No later increment, merge or deployment. Retain every prior failed experiment.
