# Read-only CModule storage diagnosis

Frozen v1 6e7a8f1 compiles and records 20 clock samples, then run_test fails with an
access violation before concurrency results. No hooks/workload or calibration ran.
Before changing the recorder, perform ONE read-only inspection of the old module's
own snapshot buffer range via Process.findRangeByAddress, using the frozen old
agent plus a storageinfo RPC. Never write to or change that range's protection.
Only record size/protection/module-owned address metadata, source hashes, errors
and exact renderer/build identity are read. This is a precondition diagnosis, not
performance/acceptance data or a repeated unchanged concurrency test.
