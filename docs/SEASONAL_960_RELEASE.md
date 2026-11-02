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

## Completed release evidence

Production run 41373109822 completed **successfully**. Both complete test orders,
dependency/container audit, metadata and aggregate gate passed on merge commit
`adb83b41fc87c826cf80ce275c3b5dc48edd2083`. Deployment and the existing read-only
Operations/Telegram worker diagnostics jobs also passed. No gate was bypassed.

The deployment job log confirms a fresh verified pre-deploy snapshot:
`css_is_20261102_101224_manual.db` (integrity OK, 49.2 MB). It then stamped 9.60 /
`adb83b4`, uploaded Space commit `f982f2786c48a0b97abfb86123ebafc47d0113a5`,
and recorded `Live /login version check: OK (expected v9.60)`.
No snapshot contents or credentials are included in this handoff.

Independent authorized/read-only verification after deploy:

- Production Space runtime: RUNNING.
- Revision-pinned remote build_info.json: version 9.60, full source commit
  `adb83b41fc87c826cf80ce275c3b5dc48edd2083`.
- Public live login: HTTP 200 and version 9.60.
- SHA-256 comparisons against the merged source passed for all six assets:
  seasonal-celebrations.css, newyear-countdown.js, both parol scenes, Christmas
  garland and New Year bunting.

Live app: <https://equityinhealth-office-connect.hf.space>.
No live business forms were submitted or appearance settings changed for these
checks. The owner can choose Christmas/New Year and enable illustrated scenery
in Appearance; no schedule or default was installed by the release operation.

Next: use 9.60 normally. Any further design feedback is a new change. Telegram work
must update from current main before its later release and retain 9.60 history;
no Telegram branch was modified or merged here. The handoff remains on
`docs/seasonal-960-release-handoff` and is linked from PR #578 rather than pushing
documentation directly to production-connected main.
