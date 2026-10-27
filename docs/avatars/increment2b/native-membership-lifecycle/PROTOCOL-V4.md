# Lifecycle v4 — same-origin beacon delivery, independent trace corroboration

Frozen v3 (b676607) fails its two-document CDP-binding transport test: zero received
departure records. No four-slot v3 capture was launched. Full failing pytest output
and source at that commit remain. Do not rerun the unchanged binding or console
transport for favorable delivery.

V4 uses navigator.sendBeacon('/lifecycle', JSON.stringify({index,persisted})) in the
same fixture pagehide listener. The local HTTP fixture accepts only that bounded
payload at a same-origin endpoint and records the host receive timestamp. No staff,
application or external endpoint/data is involved. This ADDS eleven small local
requests per full slot, in BOTH controls and probes; their scheduling/delivery cost
is inside matched stage time. The existing native timeStamp pagehide markers remain
for an independent probe-side count/persisted check. No flags/cache policy, dwell,
fixture size, document count, geometry call or collection behavior is changed.

Freeze before a NEW two-document beacon capability test. Exactly document 0 must
arrive with persisted=false. If it fails, stop. If it passes, run four NEW fixed
control/probe/probe/control slots, same source, retaining capability test output
separately. No favorable substitutions or changed qualification thresholds.

All v1/v2 lifecycle integrity and <=20%/1.20/5%/250ms gates stay. All eleven local
receipts must arrive before measurement sealing, agree with probe trace markers,
and retain separate sequential counter brackets. Original membership qualification,
application_qualified=false and acceptance=false stay independently enforced.
Both failed message transports, v1 setup errors and all v4 results are preserved.
