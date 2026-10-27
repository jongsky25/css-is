# Absent-attribute receiver — capability and observation-cost screen pass

**The new getter passes its exact native-receiver capability and four-slot cost/
lifecycle screen. 2B remains blocked.** Neither screen probe records natural major
GC, native sweep or labelled page return, so the independent through-reclamation
qualification is still missing. No application comparison or product fix is
qualified; application_qualified and acceptance remain false.

## Source-supported intervention

The previous getClientRects-based lifecycle v6 failed observation cost and controls.
Its retained cost breakdown located the largest work in the geometry census.
Pinned source and symbol inspection identify an alternative:
`Element::getAttributeNodeNS(namespace, local_name)`, offset **0x100cce80** in build
**1c5dca8527a61d07372e489142bee26af1bcaf71**. Disassembly uses rdi as the Element
receiver; pointer return does not introduce a hidden structure-return argument.

For the deliberately absent `urn:css-is:membership:absent` / `absent` query, the
method synchronizes the attribute and searches it, returning nullptr before
EnsureAttr. This path does not invoke geometry/layout or construct DOMRectList.
Synchronization and interning may still allocate. This is not a claim that the
getter is allocation-free or that it solves renderer RSS. Pinned source excerpt,
full-source hash, URL and disassembly are under `source/`.

## Exact receiver capability — passed

Frozen harness **f4ed9d9**; [capability protocol](PROTOCOL.md). One known synthetic
fixture, unchanged 4,096 paths in each of two SVG groups. Last 32 avatar and first
32 other paths are queried twice, in fixed order. A geometry reference hook is
enabled only for this capability, never for the cost screen.

All **128 native getter receiver observations** match **128 geometry reference
observations**, with 32 distinct identities per phase, exact repeats and disjoint
groups. Every getter returns null in both native and JS records. Every query
independently counts all 4,096 fixture elements before selecting the declared 32.
DOM serialization is unchanged, native build/renderer identity matches, no dropped
records or agent errors. All calls stay inside their known host query brackets.
Three source hashes verify; reconstructed capability re-audit is identical.

The geometry reference itself allocates rectangles and may flush layout, so this
run is an identity/ABI capability only, not a performance sample or a control.

## Fixed getter observation-cost screen — passed within declared limits

Frozen harness **3190099**; [screen protocol](SCREEN-PROTOCOL.md). Exactly four fresh
synthetic process/browser slots, control/probe/probe/control; Chromium
156.0.8078.47, exact native build above, Frida 17.5.1. Same v6 twelve documents,
4,096 paths per group, same selected 32/group/repeat, same batched census and
lifecycle/native/GC/counter observations. No additional warm-up, documents, dwell,
GC, cache flush, native dump, policy change or concurrent heavy analysis.

Both controls make the same absent lookups. Native geometry reference hooks are
not enabled in measured slots. JS count flags now mean null lookup results, not
rectangle counts. Versioned observable metadata and every native null return are
independently enforced; a matching/present attribute fails the intended query.
All 48 screen document DOM hashes also match the capability fixture hash.

| Slot | Mode | Duration ms | Conservative observation bound | Largest observation ms |
|---|---|---:|---:|---:|
| 0 | control | 4324.485 | 3.7770% | 19.702 |
| 1 | probe | 4595.138 | **4.9961%** | 14.509 |
| 2 | probe | 4156.761 | **4.9588%** | 14.931 |
| 3 | control | 4346.968 | 4.0742% | 19.795 |

Control duration variation **0.5199%** passes the 20% gate; paired duration ratios
**1.06259 / 0.95624** pass 1.20. All observation bounds pass 5%; all individual
observations pass 250ms. Bound includes entire batch, sequential counter reads,
trace setup and callback preparation, still double-counting preparation inside
batch intervals. No favorable subtraction or rounding decides qualification.

The first probe is only **0.00394 percentage points** below the 5% boundary. This
passes the frozen screen but establishes little headroom. It is not proof of
repeatable cost margin across environments or a causal saving versus historical
geometry runs whose controls failed. Do not rerun the unchanged screen to improve
its margin, and do not drop observations to obtain a more favorable result.

Both probes preserve all **1,536/1,536** selected receiver-to-page-generation joins,
positive per-phase coverage, exact repeat/disjoint identities and **12 mixed-group
generations**. All selected queries return null natively and in JS; DOM stays
unchanged. Eleven nonpersisted fixture departures arrive via the bounded local
beacon in every arm and match probe trace markers. Runtime BFCache flag remains
disabled. Both probes capture 36 native shutdown entries and corresponding trace
activity; auxiliary/internal documents are not assigned to main-page owners.
No reported loss, forced-GC/dump event, agent error or overflow. Sequential counter
brackets and conservative trace-edge uncertainty remain intact.

## Reclamation remains an independent failed prerequisite

Neither probe records natural major GC, native sweep or normal-page pool return
inside OR outside its captured native history. Both finish at **28 observed
documents**, with **5.882MiB** JS heap each (separate sequential reads). Native
normal-page request counts are 598/601. Absence of a recorded collection does not
prove a persistent leak, a strong retaining path or that every document is live.

The audit therefore reports `complete_lifecycle_diagnostic` with no cost/integrity
errors, while BOTH `membership_status` fields remain `capability_failed` with
`No labelled page generation observed returning to pool`. Those statuses are
preserved separately, not waived or silently converted into application qualification.
The prior geometry v6's ten labelled returns in one probe do not substitute for
this getter's missing through-reclamation evidence in both controlled probes.

Mixed pages contain elements from both fixture labels; membership never assigns
all page bytes to one group. The getter screen is not an original-versus-product
RSS/heap acceptance matrix and cannot clear any earlier 2B failure.

## Integrity and verification

The screen archive reconstructs **23 files**, including frozen harness, every
sample/trace/log and its copied receiver-capability proof. Core audit verifies
**14 source hashes and 14 cohort files**; capability audit adds **three source
hashes and two proof files**, with exact source-byte continuity from proof to
screen. Independent renderer/ready PIDs, null results and capability-fixture DOM
equivalence are checked. Extracted archive re-audit is identical, including the
stricter fixture-equivalence check added after collection; no measurement reran.
The prior geometry v6 re-audit also remains identical under the versioned checker.

**46 focused tests pass**, with the existing Starlette deprecation warning only.
They cover wrong namespace/name, native non-null returns, missing/extra/duplicate/
wrong/out-of-window receivers, mismatched reference/repeat identities, wrong build/
PID, DOM/fixture changes, lifecycle/trace integrity, batch cost and measured versus
post-window reclamation. Frozen pre-screen suite: 45 passed. Product sources
remain byte-identical to cf363bf; no 3A, merge or deployment.

## Next bounded work

Do not repeat this unchanged screen hoping for GC, qualify an application comparison,
expand the production gradients, or relax the memory/reclamation limits. The cheaper
native receiver is now established for live selected SVG elements and passes this
cost screen, with a narrow margin. The remaining instrument prerequisite is a
controlled, source-linked natural-reclamation observation with intact controls.

Use retained evidence to choose that fixture before collection. The earlier
page-history capability (`3f06fd5` / synthetic calibration `d732b70`) already used
fixed DOM/SVG/style documents and observed normal-page returns; inspect its exact
fixture and complete captures as a concrete starting point. The path-only lifecycle
fixture here supplies no collection in either probe. A separately frozen, representative
mixed fixture could test the getter through ordinary collection without forcing GC
or adding dwell until an event appears. It must prove the selected element types'
receiver identity and live/history coverage, preserve all declared samples, and pass
unchanged controls/overhead gates before any application attribution. No next product
fix is established by this instrument result alone.

## Reproduce without browsers

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/absent-attribute-receiver/screen-evidence.zip \
  --unpack-to /tmp/absent-attribute-screen
.venv/bin/python -m scripts.avatar_baseline.analyze_membership_lifecycle \
  /tmp/absent-attribute-screen/screen --ref 3190099 \
  --out /tmp/absent-attribute-audit.json
.venv/bin/python -m scripts.avatar_baseline.summarize_membership_lifecycle \
  /tmp/absent-attribute-screen/screen --ref 3190099 \
  --out /tmp/absent-attribute-periods.json.gz
```

The copied capability is independently re-audited by the screen auditor. Its
standalone archive/assessment/manifests also remain in this report directory.
