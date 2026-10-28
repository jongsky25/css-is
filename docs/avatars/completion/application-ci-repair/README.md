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

## Shared test-reader isolation

Retry 40625923083 now gets past historical identity. Its shuffled order stops
at test_ai_evaluation.py::test_existing_ai_scenario[facts-count-difference]
with `SQLiteReader is shutdown` (42 passed). A two-test sequence reproduces the
same failure on both current source and accepted 0a91f73: run the unhandled-500
browser-security lifespan test, then bulk-actions export. The first test shuts
down the global application reader; the next client does not start a lifespan.
This is inherited test-state leakage, not a measured avatar regression.

The app_mod fixture now installs and closes its own reader alongside its own
synthetic DB. It closes both the fixture reader and any startup replacement.
The production reader, database-read paths, cache and shutdown behavior are
unchanged. The two-test reproducer now passes. Original failed reproductions
are retained here. Full normal/shuffled integration checks remain required.

All 49 browser-security, bulk-actions and wardrobe integration cases pass with
the isolated fixture. Commit b370f86 changes only that fixture; this documentation
commit launches fresh standard CI without restarting frozen product measurements.
