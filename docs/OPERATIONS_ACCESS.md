# Operations access and recovery — setup step 5

Read-only observations on 2026-10-31. Step 5 remains **incomplete**: a public
storage finding needs resolution, current durability needs admin verification,
and an isolated recovery exercise has not been performed.

## Verified hosting and code

- Production Space `equityinhealth/office-connect`: public Docker, RUNNING on
  CPU Basic, Space commit `7b63b7c78b2651cb7a53fd0ddb700d6c9ab5e81e`.
- Deployed `build_info.json`: version 9.54, source
  `aaef9d3da0ac5289ca79b1e458c249a404292ddf`, matching current main.
  Deployed Dockerfile, app.py and backups.py match the checked-out source.
- Production [/health](https://equityinhealth-office-connect.hf.space/health)
  returned HTTP 200/status ok. This proves liveness, not durable recovery.
- Private preview remains RUNNING on CPU Basic, commit
  `5ac1982785c0298e0e9203c084a465f6d1ead53d`. It has no configured application
  variables and one preview password secret; its data is deliberately disposable.
- Latest [production deploy run](https://github.com/jongsky25/css-is/actions/runs/41206532759)
  completed successfully at source aaef9d3. Job/step metadata is readable. The
  combined log command returned no text; the direct job-log request failed.
  Workflow success alone is not evidence that a current backup is recoverable.

## Storage finding — resolve before closing step 5

The account bucket `equityinhealth/office-connect-data` reports `private: false`.
Both authenticated and explicitly anonymous SDK requests can read bucket metadata
and enumerate `_backups/scheduled/`: 128 metadata entries, including 25 `.db`
snapshot entries, were observed. Database contents were **not** requested or
saved. This establishes public visibility and anonymous backup enumeration;
actual snapshot download authorization was not tested.

This bucket's directory matches the runtime's backup path. The exact Space-to-
bucket mount mapping was not returned by the metadata API, so confirm it in the
production Space settings before changing access. Do not treat the absence of
legacy Space persistent-disk metadata as absence of bucket-backed persistence.

Recommended next change: make this bucket private after confirming the live
Space's mount identity will retain access, then verify anonymous metadata/listing
is denied and the application continues to save snapshots. This read-only setup
session did not change visibility, mounts, tokens, hardware, or production state.
A separate change authorization is needed because it affects live storage access.
If exposure is confirmed, the owner should assess access history and affected
backup contents without posting those contents or credentials in chat.

## Verified storage configuration and remaining limits

- Production variable `CSS_PERSIST_DIR=/data` is configured. No CSS_DB override
  appears among variable or secret names.
- Runtime startup logs explicitly report restoring
  `css_is_20261031_224808_auto.db` from `/data/_backups/scheduled` and starting
  snapshots from `css_is.db` to that directory every 60 seconds, keeping 24.
  This is startup evidence, not a current successful-save timestamp.
- The deployed Dockerfile sets HOME=/home/user and WORKDIR=$HOME/app. The expected
  live database path is therefore `/home/user/app/css_is.db`; it is on local
  container storage, with snapshots under the configured durable mount.
- No variable/secret overrides were found for CSS_PERSIST_KEEP_DAILY,
  CSS_PERSIST_BOOT_WAIT, CSS_PERSIST_OP_TIMEOUT or CSS_PERSIST_STALL_TICKS.
  Source defaults are respectively 14 days, 60 seconds, 30 seconds and 5 ticks.
  These defaults are source-derived, not independently measured runtime values.
- Production and preview build log endpoints returned HTTP 200. Bounded runtime
  stream samples were readable; the idle streams then timed out. Production
  samples contained the restore/saver-start messages and no matching snapshot
  failure message. This is not a complete log audit or proof of current durability.
  Raw logs were not published or saved in this inspection.

## Credentials and access locations

- Cloud environment HF_TOKEN is ready; its value was not printed. It can read
  production variables/secret names, logs and bucket metadata as well as preview
  resources. Its effective read access is broader than the intended preview-only
  access. Production write permission was not tested. Use a preview-scoped token
  for normal preview work; do not revoke this token without checking dependencies.
- Hosting secrets live in each Space's Settings → Variables and secrets.
  Production has 16 secret names, including CSS_SESSION_SECRET. Values were not
  read. Preview has OFFICE_PREVIEW_PASSWORD only.
- GitHub deployment workflow references repository secrets HF_TOKEN,
  CSS_ADMIN_USER and CSS_ADMIN_PASS. Listing Actions secret names returned 403;
  their current configured presence was not independently verified. Secret
  values cannot be read back from Actions.
- CSS_ADMIN_USER and CSS_ADMIN_PASS are absent from this cloud environment.
  HF authorization is not an app administrator login. Production /ops and
  /admin/backups redirect an unauthenticated visitor to login.

## Complete the operational verification

1. Resolve the bucket visibility finding and confirm the actual mount mapping.
2. With the owner's existing production admin account, open
   [Operations](https://equityinhealth-office-connect.hf.space/ops) and
   [Backups](https://equityinhealth-office-connect.hf.space/admin/backups).
   Record only durability verdict, latest successful-save time, backup age and
   schedule/retention; exclude staff records, cookies and credentials.
3. Confirm an independently retained recovery copy and agreed recovery point/time
   objectives. Existence of bucket files alone does not prove integrity or recovery.
4. Plan a separate isolated restore exercise. Keep the recovered database outside
   the workspace/preview deployment bundle, disable all outbound integrations,
   and check integrity and application compatibility in approved private storage.
   No production database download/restore exercise was performed here.
5. Keep the existing deployment backup/version/release gates. Never run the
   default pull_backup.py command merely to inspect backups: it requests a fresh
   snapshot by default. Its --list is metadata-only after admin login;
   --no-fresh downloads a production database and requires explicit data scope.

No app admin login, snapshot creation, database download, restore, restart,
production deployment or configuration write was performed in step 5.
