# Request-to-work journey measurement (Documents phase 2)

Synthetic, read-only measurement of what #606 (10.15) changed, using
`tests/measure_request_work_journey.py` (opt-in, not collected by the suite).
The same file ran unchanged on the shipped baseline `a21044a` (before 10.15) and on
`a695bb1` (10.15). Raw results: [JSON evidence](request-work-journey-2026-11-10.json).
No staff, real data, provider, notification or browser was used.

**Method.** One reviewed request, one proposed work item, and a simulated person who
only follows links and submits forms present in the returned HTML, with no browser
history or back button. "Clicks" is the minimum found by breadth-first search over
same-origin GET links (up to 4 clicks and 120 pages; 2 clicks for the other screens).
`not found` means not found within those bounds, not proof of unreachability.

## Results

| From | Goal | Before 10.15 | After 10.15 |
| --- | --- | --- | --- |
| Receipt, open existing work | Work item | 1 click | 1 click |
| Work item | Request receipt (any) | 1 click | 1 click |
| Work item | Receipt with the same return context | not found (bounded search hit its 120-page cap) | 1 click |
| Work item | Same filtered My next steps queue | not found (cap hit) | 1 click |
| Work item page links | Links carrying the queue filter / exact receipt context | 0 / 0 (of 64 links) | 1 / 2 (of 66 links) |
| After saving a contribution update | Lands with request context | no | yes |
| After saving | Receipt with context / filtered queue | not found | 1 click / 1 click |
| Discussion, handoff and completion screens | Receipt with context / filtered queue | not found; receipt only in 2 clicks and without context; 0 context links | identical (not covered by 10.15) |

## What this does and does not show

- 10.15 gave the person a one-click way back to the same request and the same filtered
  queue, and kept that context through a contribution save. Before, the work page already
  linked to the receipt, but the context was lost and no link carried the filter.
- This is not a reduction in click count: the earlier flow had no equivalent path to
  count, so the honest comparison is a direct path versus none found in the bounded
  search. The deterministic companion check (no link on the earlier work page carried the
  filter) supports that, but a person could still re-apply a filter manually.
- The screens 10.15 left out (discussion, handoff, completion) behave exactly as before:
  context is lost there. That is the measured case for extending the same context.
- Nothing here measures time, errors, comprehension or satisfaction. It is a synthetic
  link-structure measurement, not a usability result; any claim about staff benefit
  needs the separate, explicitly authorized phase 3 study.

## Next decision

Whether to extend the context to those three screens (read-only, low risk, needs its
own return-URL, access and stale-revision tests), and then to design reconciliation
writes (separate design and authorization first, per the handoff).
