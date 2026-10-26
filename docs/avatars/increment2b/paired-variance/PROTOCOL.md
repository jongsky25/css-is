# Paired memory-variance experiment, version 1

Predeclared before measurement. Diagnostic only; no product correction, gate waiver,
acceptance rerun or replacement of historical evidence.

## Question and fixed sources

Do shorter counterbalanced source blocks and standardized fresh sessions produce
stable same-source controls and a repeatable original/current memory difference?
Original is 1c964dcba2fa19de1eab077b00e0e5748d742554; current is
f700187553bd555dd3a9b638d5aa8e5fb59f3142. No product files are changed. This does
not repeat the rejected observer-disable or SVG-rollback interventions.

## Schedule and workload

Exactly five blocks, with A = original and B = current:

1. A B B A
2. B A A B
3. A B B A
4. B A A B
5. A B B A

Twenty scheduled samples: each block has one original-before-current pair, one
current-before-original pair, and one same-source early/late pair for each source.
Every slot launches a fresh pytest process, fixture database and browser. That
standardizes startup and eliminates cross-sample browser/database reuse. It is
a deliberate session-structure change from historical five-context browser cohorts,
so these measurements cannot replace their acceptance evidence or isolate ordering
from session reuse as separate causes.

The existing 30-second warm-desktop workload, pinned Chromium 156.0.8078.47,
eight scenarios and five navigation checkpoints remain intact. A frozen one-line
fixture adapter selects the original sample ordinal (block 0 through 4), retaining
the screenshot only at ordinal zero. Both same-source repetitions within a block
use that same ordinal. The repository fixture is unchanged. Frozen adapted fixture
bytes and all source hashes are verified against the declared harness commit.
No tracing, native sampling, dumps, forced GC, extra cache flushes, concurrent
analysis on the measurement host, excluded samples, or replacement samples.
All twenty slots remain scheduled after a failed slot, but any invalid/missing slot
makes the whole attribution audit inconclusive.

## Analysis fixed before data

At each of the 13 checkpoints, analyze both total renderer RSS and JS heap.
Renderer counts must be positive and match across all 20 slots for that checkpoint.
Retain all values, source identities, five pairs per order and five negative-control
pairs per source. Source deltas are current minus original. Negative-control deltas
are late minus early for the same source. Preserve raw SHA-256 identities.

The existing budget is 10 MiB (10,485,760 bytes). Report the traditional difference
of source medians for each order, plus the median of the five paired differences.
Neither statistic substitutes for the other or for historical acceptance gates.

A checkpoint/metric has stable negative controls only if **all ten** same-source
pair differences have absolute value at most 10 MiB. A single unstable pair cannot
be averaged away. Only then may a source effect be called repeatable: both the
paired median and difference of medians must exceed +10 MiB (or both be below
-10 MiB) in both orders, with at least four of five paired signs agreeing in each
order. Otherwise classify it as unstable controls or no repeatable effect. These
are conservative diagnostic labels, not statistical proof or new release gates.
Report each checkpoint independently; an unstable control elsewhere cannot hide
its failure, nor erase a separately supported effect. No RSS subtraction.

## Decision boundary

If controls are unstable, preserve the failures and investigate the source of
measurement variation before another product edit. Do not relax budgets or rerun
unchanged until a favourable result appears. If a source increase is repeatable at
a checkpoint, use that checkpoint for the next source-attribution investigation;
this broad original/current comparison does not identify a particular component.
A lack of repeatable increases is not a pass: full original acceptance remains
withdrawn, 2B remains blocked, and 3A/later increments remain paused.
