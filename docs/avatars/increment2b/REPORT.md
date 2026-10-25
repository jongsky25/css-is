# Increment2B — preference-cache follow-up

**Acceptance remains unresolved.** Product revision `c2f404fa5aa58abebbe0127bbb537b5592993ce5`.
[Assessment](preference-cache-fix/assessment.json).

Avatar input/timer handlers now read an event-updated reduced-motion boolean
instead of querying MediaQueryList.matches each time. The existing preference
listener updates it live, with legacy addListener support. A queued curiosity
frame rechecks the cached preference before writing transforms.

[Eight browser checks](preference-cache-fix/tests.txt) pass. The new regression
confirms zero avatar preference-query reads during pointer input and correct live
reduced-motion on/off behavior. [1,734 SVG comparisons](preference-cache-fix/artwork-equivalence.json)
pass; artwork/CSS remain unchanged apart from JS cache key8.21.

Five counterbalanced fern pairs, mature6/CPU4/30s, produced:

- Current callback maxima: [20.765, 49.782, 210.804, 13.408, 13.204]ms.
- Old-art control callback maxima: [81.97, 6.265, 6.399, 163.949, 158.973]ms.
- Current framep95: [16.8, 33.4, 16.8, 16.8, 16.8]ms.
- Old-art framep95: [16.8, 16.7, 16.8, 99.9, 66.7]ms.

The current210.804ms event is the chase timer. Controls also have large stalls;
this does not isolate the underlying cause or waive any result. No errors or
trace loss. [Every sample and raw trace](preference-cache-fix/traces/fern/summary.json)
and [runner log](preference-cache-fix/trace-tests.txt) are retained. Synthetic
throttle time remains inside measured callback wall duration; none is subtracted.
The user-approved33.3ms frame exception remains accepted. Callback50ms and
uncompleted acceptance checks remain required. Remaining trace species/native
cohorts/full matrix were not started after the failure.3A remains pending.

[Prior verification and frame exception](REPORT-chase-write-fix.md).
No deployment or additional application changes based on an unproven stall cause.
