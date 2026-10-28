# Hosted full application evidence

Run: https://github.com/jongsky25/css-is/actions/runs/40628692333

Branch snapshot: 559301eed8f1e0e520944edd577d4e7dbd9df141.
GitHub tested temporary PR checkout 23e4a7ad80651a436c9ff35db48c25b5a7e5c540,
whose tree is identical to that branch snapshot. Its parents are accepted 0a91f73
and branch 559301e. This is GitHub's CI checkout, not a merge into any user branch.
Production/measurement files remain identical to frozen fecd276. Only test/CI,
release-packaging and documentation changes follow that product snapshot.

The original ZIP archives retain JUnit, AI evaluation evidence and installed
package inventories. Archive digests and independently checked counts are recorded
in audit.json. The application selection leaves disabled archived experiment
modules uncollected and explicitly deselects one executable Yappi probe; all
7,060 selected cases must have zero failures/errors/skips. This does not count
deselected diagnostics as passes. Dedicated avatar acceptance is separate.

After extracting each archive, JUnit can be checked with scripts/check_release.py
junit. The strict scripts/ai_evaluation.py check command must run from the exact
23e4a7ad checkout because its provenance binds to the Git commit as well as file
hashes. An initial check from the ordinary branch correctly rejected that commit
mismatch; the untouched report passes in a detached read-only checkout of the CI
revision. No report, source signature or acceptance gate was modified.
