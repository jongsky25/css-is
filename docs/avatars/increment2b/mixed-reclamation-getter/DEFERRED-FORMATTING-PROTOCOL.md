# Mixed getter v11 — export address strings after sealing measurement

V10 (9188ac1) completes all four fixed slots and both all-mode labelled-reclamation/
MajorGC/sweep checks. All identities, selector counts, controls and paired elapsed
checks pass. Probe 1 still fails 5% observation cost (5.3977%); probe 2 passes at
4.7461%. All data/failure is retained, without subtraction or favourable rerun.

A concrete remaining repeated callback operation is conversion of backend/element/
page pointers into hexadecimal strings. V11 captures argument NativePointer values
at entry, and copies the allocation return pointer using retval.add(0) at exit
because Frida InvocationReturnValue objects are recycled. It does NOT retain the
recycled return wrapper. No native address is dereferenced. It records the same
kind/phase/timestamp/thread/native-null observations at the same call boundaries.

Only representation work moves: RPC result() maps the captured opaque pointer
values to the same hex strings AFTER the host has sealed measurement. It exposes
address_encoding='deferred-native-pointer-v1', required by the auditor. Whole
census timing, existing prep timestamps, all scope/source/overflow/null/identity
and source-labelled generation checks remain. NativePointer values in the injected
agent are addresses, not Blink JS wrappers or a request to pin DOM objects.

Freeze before a NEW exact-type capability with all 384 getter/reference matches,
repeats/disjoint types, native nulls, immutable address stability across later calls
and unchanged DOM. Stable receiver/page-generation joins in the subsequent screen
must reject any recycled/misrecorded pointer. Geometry witness remains capability-
only. If proof fails, do not run the four-slot screen or silently stringify earlier.

Only after proof passes, four NEW fixed control/probe/probe/control slots keep the
identical v10 fixture bytes, source selections, 1,536 getter calls, twelve documents,
220ms waits, local selector reuse, navigation arming, trace/counter/beacon coverage,
5%/250ms/1.20/20% gates and all-mode labelled returns/natural collection in both probes.
No data, timestamp, slow event, GC overlap or actual remaining work is omitted from
an existing bound; address formatting is no longer performed inside that window.
Export latency is retained as post-window diagnostic work, never acceptance RSS.

All previous failures remain. No more documents/dwell, forced GC, pressure, snapshot/
dump, cache/policy/permission change, heavy concurrent analysis, sample replacement,
RSS subtraction or budget waiver. Passing could qualify only a separate application
calibration, not application comparison, a product fix, 2B or a later increment.
