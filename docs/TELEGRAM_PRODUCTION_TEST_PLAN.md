# Telegram testing in production — November 4, 2026

## Owner direction

The owner cancelled the isolated pilot and explicitly requested testing in
production because the Telegram integration has not been launched. This
supersedes the earlier production deferral and the isolated-pilot prerequisite.
Use the existing production application and **@blhsd_bot**. Do not redirect its
webhook, require a production webhook secret copy in the chat environment,
rotate that secret, publish the isolated target or copy synthetic pilot data into
production. The unlaunched status is owner-reported, not an audited user count.

The requested production testing authorizes the necessary PR #572 code release
through the canonical main workflow after exact-head verification and the normal
backup/version gates. It does not authorize enabling all default-off capabilities.
Start with the owner's account and existing link/discovery/calendar reads;
select subsequent action batches explicitly. No other account consent is granted.
The owner was asked which subsequent batch to exercise and to report `/status`.
Do not claim actual receipt or linking from an HTTP response or database inspection.

## Fresh observations before release

- Local/remote review head: `d7ab3c6ece94efd83d1824380020165afcd17c36`,
  candidate 9.91; actual main `625c60f2fc91ddf98519a9084a5c4217fd1f2e56`.
  Draft PR #572 open/mergeable, auto-merge absent, no submitted reviews or review
  threads. Main ruleset 26274179 active, no bypasses, strict Required checks,
  required PR/resolved threads and deletion/force-push protection.
- That head's avatar, metadata and dependency checks passed. Full normal/shuffled
  CI 41764981234 was still running; aggregate success was not established.
  Any new documentation head needs its own exact-head green checks.
- Production Space `equityinhealth/office-connect`: RUNNING, CPU Basic, Space SHA
  `2e1b84e4009965ba5e1065fb3e59385ae13b6d12`; login version **9.62**,
  `/health` HTTP 200/status ok. `/login` HTTP 200. No new deployment yet.
- Runtime metadata confirms writable bucket `equityinhealth/office-connect-data`
  mounted at `/data`; variables confirm `CSS_PERSIST_DIR=/data`, no CSS_DB
  override and correct canonical CSS_BASE_URL. This establishes current topology,
  not fresh predeploy backup success. The canonical gate must obtain and verify it.
- Existing enabled public variables: inbound, delivery, link and calendar_read.
  Bot/session/webhook secret names exist; values were not retrieved.
  Other public Telegram feature flags are absent. Secret-name inspection cannot
  establish values of secret-backed settings (including Apprise).
- Earlier read-only bot preflight matched @blhsd_bot, the existing production
  webhook, zero pending updates and no last delivery error. Recheck if needed
  before provider changes. No provider registration change is needed for release.

## Execution

1. Save this direction on the review branch. Preserve application 9.91 and all
   released history. Run documentation checks; application code is unchanged.
2. Await complete exact-head normal/shuffled, dependency, metadata, Required
   checks and avatar acceptance. Recheck actual main/head/rules/reviews and any
   concurrent merge/deployment. Resolve real failures without gate bypasses.
3. Merge the reviewed PR only after those gates pass, using the expected head
   guard and ordinary protection. Main triggers the serialized main-only workflow:
   full verification, fresh verified backup, strict-version code-only deployment,
   live-version check and sanitized Operations diagnostics. No alternative upload,
   backup bypass, seed replacement, restore or storage-topology change.
4. Verify actual merged main SHA, Space source/build/version, RUNNING, health,
   backup result and Telegram diagnostics. Keep each state distinct: authorized,
   checked, merged, deployed and personally tested.
5. Existing production read checks can run before the new release: owner sends
   `/status`; if active, `/menu` and `/calendar`. If linking is needed, use
   `/start`, signed-in `/account/telegram` with calendar-read consent, then
   `/status` and its exact `/confirm` in the original private chat. Never copy
   codes from the DB or issue another start while a confirmation is pending.
6. Record actual owner receipt/source parity. Further features need their selected
   independent host flags and fresh explicit consent. Start with test records
   created by the owner through normal production UI for any later write test;
   do not use live business records as development fixtures or run destructive,
   fault, restore, concurrency or foreign-account probes against production.
7. Groups, scheduled reminders, outbound transport and all other unselected
   activation remain out of the initial scope. No full T4.4 or blanket live pass.
   On a defect, preserve evidence and committed/uncertain outcomes, pause the
   affected approved path if necessary and fix/retest on a review branch.
   Rollback cannot recall messages or undo source actions; never replay uncertain
   sends or restore data as an incidental code rollback.

## Remaining evidence

Exact new-head CI, merge, deployed 9.91/source, fresh backup, new diagnostics,
owner receipt/consent and selected subsequent feature scope are still pending.
The isolated target stays unpublished and off; no cleanup/deletion is implied.
No production configuration or business record was changed during preparation.
