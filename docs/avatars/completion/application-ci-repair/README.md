# Bounded application-CI checkout correction

The standard application jobs in run 40620568593 timed out at their existing
45-minute bound after failures; neither is a pass. They uploaded dependency
inventories but no completed JUnit report. The first normal-order failure is
`test_avatar_paired_variance.py::test_full_identity_audit_and_tampering` (ordinal
1,244), an unchanged offline test that reads historical Git trees.

The test passes against the full local history. A depth-one bare clone reproduces
its failure exactly: `git ls-tree` cannot resolve original source 1c964dc. This is
an offline fixture/checkout issue, not a new browser memory measurement. No GC
or instrumentation was run. The remaining broad failures are not yet attributed.

Application CI now fetches full history and stops at its first failure, retaining
the original zero-failure/zero-skip gate. Both test orders are retried. The avatar
workflow ignores CI/report-only edits, so the frozen fecd276 functional/runtime
results and ongoing memory matrix are preserved. Product and measurement code
are unchanged by this correction.
