# Seasonal 9.60 production release — November 2, 2026

Owner explicitly approved merging and deploying 9.60 after phone design acceptance
and passing release PR checks. [PR #578](https://github.com/jongsky25/css-is/pull/578)
merged as `adb83b41fc87c826cf80ce275c3b5dc48edd2083`.

Before merge, main remained `a7b9b38` (9.59), PR head was unchanged at `a9eda74`,
merge state was clean, and all PR checks were successful. Evidence:
[complete release checks](https://github.com/jongsky25/css-is/actions/runs/41325761392)
and [avatar acceptance](https://github.com/jongsky25/css-is/actions/runs/41325761440).

Production workflow:
[run 41373109822](https://github.com/jongsky25/css-is/actions/runs/41373109822),
source `adb83b41fc87c826cf80ce275c3b5dc48edd2083`. It reruns complete checks on the
merge commit, then uses the existing backup/version/upload/post-deploy gates.
No check or backup is bypassed. Initial state: in progress; deployment is not yet
claimed complete. Record final workflow and live verification below when observed.

This handoff is saved separately on `docs/seasonal-960-release-handoff` so recording
release evidence does not trigger another production deployment. No production
appearance default, event schedule or other feature flag is changed by this release
operation. No Telegram message or outgoing integration test is requested.

Telegram work remains independent. Its next update from main must retain the 9.60
changelog entry and status history, reconcile the version/cache files, and run its
own checks after integration. No Telegram branch is modified here.

Next: observe the complete production workflow, preserve any failed gate, then
verify the live login version and deployed source commit without changing records.
