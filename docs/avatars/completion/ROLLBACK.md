# Avatar review candidate — rollback and validation

This branch is a review candidate. Production deployment and merging to main need
separate user authorization. The provisional 2B memory decision stays unchanged.
Later increments have no memory exception. Release acceptance remains pending any
unpassed functional/performance gates identified in the current report.

Revert the product commits in reverse order: shared motion, customization UI,
wardrobe model, 3B artwork, then recovered 3A artwork. Prefer normal `git revert`
commits on the release branch so unrelated reader/application changes are retained.
The two additive admin_user columns can remain unused after rollback; do not drop
them or clear users' saved equipment, account identity, growth or care records.
Bump version.py, changed script query versions and the service-worker cache version
for a rollback release, using the repository conventions. No production commands
have been run for this candidate.

Reproduction uses locked requirements-test.txt in a Python virtual environment.
Run focused unit/integration tests and opt-in browser tests with
CSS_AVATAR_BASELINE=1. Use a synthetic DB through tests/conftest.py. Render all six
stages through the actual macros; personal preview GETs must never save. Keep
performance runs separate from screenshots and other heavy work. Report the exact
browser, source hashes, viewport and CPU throttle; desktop emulation is not a
physical phone. Preserve failing samples and do not restart archived GC research.

Release packaging now includes companion_wardrobe.py and the baseline's existing
sqlite_reader.py. If wardrobe is reverted, remove only its import/list entry after
all callers are reverted. Keep sqlite_reader.py in the release payload while the
baseline application imports it. Do not revert that packaging repair as a side
effect of an avatar rollback. Test-fixture isolation and historical checkout fixes
are independent of the avatar product and do not need product rollback.
