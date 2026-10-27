# Native element membership — live joins demonstrated, reclamation capability failed

**2B remains blocked. No application collection or product intervention followed.**
Two distinct, frozen four-slot synthetic experiments completed. V2 identifies every
selected native element and its observed normal-page generation within the timing
budgets, but neither experiment observes a labelled page returning to the pool.
The required through-reclamation capability is therefore unqualified. No sample
replacement, forced GC, budget change, 3A, merge or deployment occurred.

## Why this observation was selected

The prior page-history hooks identify page-request callers, not the source of each
object placed on a page. The snapshot-ordering calibration failed and did not close
that ownership gap. Before another application capture, this experiment tests one
concrete discriminant: call a known element's DOM geometry method, intercept its
native receiver, and locate that address within a captured normal-page generation.
Later observed pool returns would bound the generation's end without a heap dump.

Exact-build symbols identify `blink::Element::getClientRects()` at 0x100b1880.
It returns DOMRectList*, with the Element receiver as its first native argument.
Pinned V8 constants specify 128KiB normal-page size/alignment. Existing page request/
return offsets remain 0x5ab0350/0x5ab0550. The hook records addresses/timestamps and
never dereferences element or page memory. Runtime receiver repetition, JS census
counts and disjoint known groups independently check the proposed identity mapping.

The initially considered attribute readers are inlined in this build and do not
supply the required separate hook. getClientRects does not mutate DOM, but can flush
layout and allocates DOMRectList/DOMRect objects. That intrusion is explicit; controls
make identical geometry calls. Injected RSS cannot establish a product improvement.
The debug package checksum matches the previously retained exact-build package.
GNU addr2line resolves function names but emits DWARF file-number errors and unknown
line numbers; no exact source-line claim is made. Pinned source and symbol offsets
are retained under `source/`, with checksums and this limitation in its manifest.

## Frozen v1 result

Harness **3375008**, [protocol](PROTOCOL.md). Twelve synthetic documents per slot,
512 paths in each of two SVG groups. Every element is censused twice per document,
in DOM order. Labels `avatar` and `other` are known fixture labels; neither renders
the production avatar. Both groups use the same element type to expose shared pages.

| Slot | Mode | Measured duration ms | Receiver records | Observed-request joins | Mixed-group generations |
|---|---|---:|---:|---:|---:|
| 0 | control | 3378.142 | — | — | — |
| 1 | probe | 4086.491 | 24576 | 22334 (90.877%) | 10 |
| 2 | probe | 4301.402 | 24576 | 22334 (90.877%) | 10 |
| 3 | control | 3496.096 | — | — | — |

Both probes reproduce exact, distinct and repeatable receiver identities. Unknown
pages remain explicit. However, the first document's four census phases have zero
observed-request membership, so the every-phase gate fails despite aggregate
coverage above 90%. No pool-return call is recorded in either probe, hence no
labelled generation has an observed reclamation boundary. Paired timing ratios
1.20969 and 1.23034 exceed 1.20. Controls vary 3.492%; preparation costs 2.708%/
2.411%, maxima 2.589/0.516ms. All v1 failures remain in `v1-audit.json.gz` and the
independently strengthened `v1-audit-hardened.json.gz`; no v1 workload was replaced.

## Supported fixture correction and frozen v2 result

V1 exposed initial capacity outside attachment and high repeated interception
cost. The separate [v2 protocol](PROTOCOL-V2.md) therefore increases each SVG group
to 4,096 paths while reducing its fixed census to 128 elements: last 128 avatar
paths, first 128 other paths, twice per document. Query results independently
verify all 4,096 elements before selecting the predetermined subset. This changes
synthetic allocation pressure and observation cost, not production source or a
memory budget. It does not claim coverage of unselected elements. No selection
uses memory/event results. Every qualification threshold remains unchanged.

Harness **02f59cb**; twelve documents, fresh control/probe/probe/control slots:

| Slot | Mode | Measured duration ms | Receiver records | Observed-request joins | Mixed-group generations |
|---|---|---:|---:|---:|---:|
| 0 | control | 4157.916 | — | — | — |
| 1 | probe | 4325.586 | 6144 | 6144 (100%) | 12 |
| 2 | probe | 4322.601 | 6144 | 6144 (100%) | 12 |
| 3 | control | 4081.074 | — | — | — |

Every selected receiver joins uniquely to an observed completed page request,
with positive coverage in all 48 census phases in each probe. Both repeats retain
identical ordered identities, groups stay disjoint, and DOM serialization hashes
match before/after every census. No drops, agent errors, overlapping generations
or source/renderer mismatches are reported. All twelve documents remain included.

Paired duration ratios **1.04033 / 1.05918** and **1.848%** control variation pass
unchanged limits. Explicit callback preparation is **0.728% / 0.729%**, maximum
**0.221 / 0.096ms**. Paired elapsed checks cover overhead beyond callback preparation.
The two probes record 589/605 normal-page requests, but **zero pool-return calls**.
The through-reclamation gate fails in both; this is not a qualified instrument for
application allocation/reclamation attribution. No application run was launched.

## What the positive evidence does and does not establish

A labelled element address falls inside a page generation whose request was
observed before the census. Mixed-group generations contain sampled members from
both fixture sources, demonstrating why one source label cannot own an entire
page's bytes by inference. Future address reuse must start a new generation after
a recorded return; tests reject ambiguous/overlapping lifetimes and retain gaps.

This is membership at observation time, not allocation-site history for every
object, an exclusive owner, a byte attribution, a strong retaining path, a pool
hit or a decomposition of RSS. Layout/style/text objects and unselected elements
are outside this census. Calls themselves allocate rectangle objects. Zero observed
pool-return calls do not prove that all elements remain reachable or that no
object reclamation/direct page release occurred. Pages can remain partly occupied.
No product reduction is selected from these observations.

## Integrity and validation

Exact Chromium **156.0.8078.47**, build
**1c5dca8527a61d07372e489142bee26af1bcaf71**, Frida **17.5.1**. Eight fresh synthetic
browser/process slots complete. No production database or staff data is accessed.
No concurrent heavy analysis runs during either fixed schedule.

Each archive reconstructs **17 files**. Each strengthened audit verifies **12 source
identities** (four archived harness files plus two runtime probe hashes in each of
four slots) and **12 cohort files**. Independent renderer checks reconcile the
identity trace with capture PID and native-hook ready PID. Both extracted archives
re-audit identically. Hardening adds integrity checks without modifying measurements,
thresholds or either failed decision. V1's initial audit remains separately retained.

Initial focused suite: **26 passed**. Final suite after identity/profile integrity
checks: **28 passed**, existing Starlette deprecation warning only. Tests exercise
repeat/disjoint identity, missing/extra/duplicate/out-of-window receivers, DOM changes,
versioned fixture sizes, wrong renderer identities, unknown pages, generation reuse,
ambiguous lifetimes, missing reclamation and the 90% threshold. Exact source/debug
resolution limits are preserved instead of claiming complete native ownership.

## Next bounded decision

Do not launch application calibration, repeat either unchanged fixture, increase
its duration just to obtain a return, or weaken the reclamation requirement. V2
solves receiver coverage and cost, but supplies no pool boundary. All previous
memory failures and snapshot-order calibration failure remain unchanged.

Before another capture, inspect the pinned browser's ordinary document/history
lifecycle and normal-page release paths. The precise missing discriminant is whether
these synthetic documents are retained by navigation/history state, have not yet
undergone natural collection, or were partly reclaimed while their pages remained
occupied. These captures have neither document-disposition nor natural-GC chronology
to distinguish those cases. A revised, controlled fixture must demonstrate its
intended document lifetime and observe the relevant natural release path before
this method can support application ownership claims. Do not assume adding another
cleanup handler, forcing collection, or expanding gradients solves that gap.

## Reproduce without browser collection

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/native-element-membership/v2-evidence.zip \
  --unpack-to /tmp/element-membership-v2
.venv/bin/python -m scripts.avatar_baseline.analyze_element_membership \
  /tmp/element-membership-v2/calibration --ref 02f59cb \
  --out /tmp/element-membership-v2-audit.json
```

Use v1-evidence.zip and ref 3375008 for the first frozen experiment. Retained audit
JSON is gzip-compressed; compare decoded JSON values to the reconstructed audit.
