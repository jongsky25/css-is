# Native element membership v1 — controlled-fixture capability first

This is a new observable, not a replacement run of failed snapshot-order calibration.
Question: can a known source-labelled DOM element's native address be tied to an
observed normal-page generation and its subsequent pool return? Existing page
request stacks cannot establish that membership. No application run or product
change is part of this capability schedule. Previous failures stay unchanged.

Exact Chromium 156.0.8078.47 / ELF 1c5dca8527a61d07372e489142bee26af1bcaf71;
Frida 17.5.1, diagnostic-only. Matching debug package checksum equals the existing
retained native-sampling manifest. Symbol offsets and pinned source are retained.
Element::getClientRects at 0x100b1880 has an ordinary Element receiver in the first
argument and returns DOMRectList*. The hook records only the receiver address and
host CLOCK_MONOTONIC timestamps, not object memory. Existing normal-page request/
return hooks are 0x5ab0350 / 0x5ab0550. V8's pinned api-constants.h fixes normal-page
size/alignment to 2^17 bytes. Do not infer sizes, strong references or page contents
from arbitrary memory reads. No page memory is dereferenced by this hook.

getClientRects is DOM-read-only, but can flush layout and allocates DOMRectList/
DOMRect objects. It is therefore intrusive. Both controls perform identical calls;
paired timing gates account for interceptor overhead. This is membership evidence
only, never an uninjected RSS comparison. Address reuse after a pool return is a
new generation, not continuous identity or proof of a pool hit/physical backing.

Freeze code, protocol and auditor before collection. Exactly four NEW synthetic
slots, control/probe/probe/control, fresh process/browser each. Each slot navigates
twelve fixed documents. Each document contains two SVG blocks, 512 paths labelled
avatar and 512 paths labelled other. Names are known fixture labels, not claims
about production ownership. After an unchanged 220ms wait, census avatar then other,
twice each in identical DOM order, calling getClientRects once per element. Controls
make the same calls without injection. RPC marker costs are inside total stage time.
DOM serialization hashes before/after must match. No application DB or production
data. No GC, memory-pressure notification, cache flush, heap snapshot, native dump,
concurrent heavy analysis, replacement, timeout extension or privilege change.

Probes intercept receivers only during explicitly bounded census phases and record
normal-page requests/returns throughout the twelve documents. Export after sealing
the measured window. A fixed 50,000-record ceiling must not drop events. Every
scheduled slot, file, error and source hash is preserved. No fitting object already
in an allocation buffer, large page, or pre-attachment request is invented.

Capability gates, both probes:
- Exactly 512 distinct native receivers per group/repeat/document, matching JS
  census counts and DOM order. Repeat lists match; disjoint groups stay disjoint.
  Extra, missing, duplicate, out-of-census or ambiguous receiver records fail.
- At least 90% of all receiver observations join uniquely to an observed completed
  normal-page request before the census and before any matched return. Each census
  phase has at least one observed-request membership. Unknown/preexisting pages
  remain explicit, never counted as covered or assigned a fabricated generation.
- At least one labelled page generation subsequently returns to the pool; at least
  one generation has members from both labelled groups. This demonstrates why a
  source-labelled element cannot own an entire page's bytes by inference.
- No drops, agent errors, overlapping page generations, wrong identities/builds,
  changed DOM or incomplete schedule. Source hashes and all evidence files verify.
- Callback preparation <=5% of total measured time and <=250ms individually.
  This understates full hook cost, so paired elapsed checks also apply: probes
  <=120% of their adjacent controls, first/final controls within 20%.

Failure stops application use. Preserve all four slots; do not rerun unchanged to
find a collection or pool return. Success qualifies only this synthetic membership
instrument, not allocation causality, exclusive ownership, a product correction or
2B acceptance. Before application collection, independently audit extracted evidence
and freeze a separate application protocol/calibration accounting for census work
and coverage, including earlier scenarios whose allocations enter navigation.
No 3A, later increment, merge, deployment or memory-budget waiver.
