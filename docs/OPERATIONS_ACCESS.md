# Operations access and recovery — setup step 5

Inspected on 2026-10-31; the owner subsequently authorized a bucket privacy
change. The bucket is now private and anonymous metadata/listing returns 401.
A database-level isolated recovery exercise now passes. Step 5 remains
**incomplete** for owner admin/mount verification, independent recovery retention
and agreed recovery objectives. Historical third-party backup access is unknown.

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

## Storage finding — original read-only evidence

During the original inspection, `equityinhealth/office-connect-data` reported
`private: false`.
Both authenticated and explicitly anonymous SDK requests can read bucket metadata
and enumerate `_backups/scheduled/`: 128 metadata entries, including 25 `.db`
snapshot entries, were observed. Database contents were **not** requested or
saved. This establishes public visibility and anonymous backup enumeration;
actual snapshot download authorization was not tested.

This bucket's directory matches the runtime's backup path. The exact Space-to-
bucket mount mapping was not returned by the metadata API, so confirm it in the
production Space settings before changing access. Do not treat the absence of
legacy Space persistent-disk metadata as absence of bucket-backed persistence.

The owner subsequently approved making the bucket private. The visibility
change is recorded below; mount configuration was not modified. The original
inspection itself did not change production state.
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

1. Bucket privacy is corrected; retain the private setting. Confirm the exact
   mount identity/configuration through the owner’s hosting settings.
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

The initial inspection performed no production writes. The subsequently
authorized change modified only bucket visibility. No app admin login, forced
snapshot creation, database download, restore, restart or production deployment
was performed.

## Authorized privacy change — 2026-10-31, verified 15:59 UTC

- Owner explicitly approved making the bucket private. Updated only
  `equityinhealth/office-connect-data` using the SDK's bucket settings operation.
  Authenticated metadata confirms `private: true`.
- Explicitly anonymous bucket metadata and backup-list requests now both return
  HTTP 401. Authenticated listing still succeeds and retained snapshot entries
  remain available. No snapshot contents were downloaded.
- Production remained RUNNING before the operation; health requests throughout
  verification returned HTTP 200/status ok.
- A new periodic snapshot, `css_is_20261031_235908_auto.db`, appeared in this
  bucket after the visibility change. Observed at 2026-10-31 15:59:23 UTC.
  This establishes continued snapshot writes after the change; it does not prove
  database integrity, independent retention, or a successful recovery drill.
- Hosting settings HTML redirected the API-token request to browser login; the
  exact mount identity was not available there. Existing runtime evidence and
  matching bucket paths were checked; mounts and credentials were left intact.
  Continued snapshot creation supplies operational evidence that the current
  running saver retained access. A future cold-start/mount remount was not tested.
- No restart, deployment, mount edit, token change, database download or forced
  backup was performed. The scheduled application snapshot was observed only.
- Remaining: owner admin durability review, mount identity confirmation, exposure
  assessment for the previously public bucket, and approved isolated recovery
  evidence. Do not reopen public access as a troubleshooting shortcut.

## Authorized isolated recovery and exposure review — 2026-10-31, 16:06 UTC

Owner authorized the recovery/exposure follow-up. See the sanitized
[recovery evidence](operations/recovery-2026-10-31.json). An authenticated download
of one existing automatic snapshot was performed into a mode-0700 temporary
directory outside the repository. No new production snapshot was requested.
SDK data caches were directed into the same temporary directory.

Snapshot `css_is_20261101_000512_auto.db` was 49,143,808 bytes and uploaded at
16:05:15 UTC. Download size matched metadata, and SQLite integrity_check passed.
A separate Python 3.11 process received an allowlist environment with no inherited
provider credentials and used the preview's outbound socket guard. No application
server was started. It exercised the actual backups.restore_backup routine against
a temporary destination containing a synthetic probe. The probe disappeared after
restore; the generated pre-restore safety copy retained it. Restored integrity
passed, no browser sessions remained, and integration revocation/disabled digest
postconditions passed. The source snapshot's checksum was unchanged.

The source already contained no browser sessions, so this is not a challenge
case for session removal. Credential reset checks do not prove the source had
active credentials. This is database-level recovery evidence, not a test of full
application startup, production rollback, or a cold-start bucket remount.
Download plus drill took 16.2 seconds; local restore/check took 0.83 seconds.
These are observed timings, not agreed production recovery objectives.

All temporary database copies, generated snapshots and download caches were
removed after verification. No production database rows were printed or committed.
Production health remained HTTP 200/status ok; an anonymous HEAD request to the
selected snapshot returned 401. No live restore, restart or deployment occurred.

### Exposure review outcome

The inspected snapshot has populated account, integration credential and document
record tables. Source code stores integration read credentials as secret hashes;
a credential table's presence does not establish plaintext token exposure. Password
hashes and personal/document records still warrant treating the prior public bucket
as a potential data exposure. The absence of browser sessions in this one snapshot
does not establish their absence in older snapshots.

Current access cannot establish whether third parties downloaded snapshots, the
public visibility start date, or any retained copies. Bucket creation on
2026-06-18 is not proof that visibility was public since that date. No historical
bucket download/audit trail is available through the connected tools. Hosting
application request logs do not measure direct bucket downloads. The privacy fix
cannot withdraw copies previously obtained.

Owner follow-up: obtain available historical access/audit evidence from the hosting
account/provider, assess the affected retained snapshots, and decide account/key
reset scope with the service owner. No production credential/session reset or
external report/message was sent during this review. Provider/account evidence
and any consequential remediation remain separate from the completed privacy fix.

Remaining operational acceptance: owner review of /ops and /admin/backups,
confirmation of the configured mount identity, an independently retained recovery
copy and agreed RPO/RTO. Do not mark these complete from this temporary drill.

## Owner Operations evidence and audit warning — 2026-10-31

The owner supplied a production Operations screenshot confirming that live data
is being saved to permanent storage (last saved display: 2026-11-01 00:09:16,
application local time), daily backups are enabled, and 25 saved backups total
about 1.1 GB. The next scheduled backup displays 2026-11-01 02:00; the last daily
backup status is OK. The periodic durability saver and daily maintenance backup
schedule are separate mechanisms; their timestamps need not match.

This confirms the previously pending owner admin Operations view. The same
screenshot reports an audit-record gap at entry #8949. A separate read-only
inspection of existing snapshot css_is_20261101_001016_auto.db reproduces the
first failure at #8949: its previous link matches entry #8948, but its content
hash does not match the stored fields. Two later entries have link mismatches
while their content hashes validate against their own stored parent hashes.
Three mismatches were found in total. See the sanitized
[audit evidence](operations/audit-2026-10-31.json).

The first mismatch is not merely a missing sequential ID. Possible causes include
changed data or inconsistent hash inputs at write time; no cause or actor has been
established. Database integrity_check and recovery success are distinct from
application audit authenticity. Do not label this proof of malicious tampering,
and do not rehash/delete/rewrite the chain to suppress the warning. Investigate
writer serialization, historical maintenance and available earlier backups while
preserving history. No audit repair or application change was made.

The audit snapshot was downloaded into restricted temporary storage, opened in
SQLite read-only mode, and deleted with its download caches afterward. No actors,
record text, document details or credential values were printed or committed.

Remaining: audit mismatch investigation, historical exposure assessment, mount
identity/cold-start evidence, independent recovery retention and agreed objectives.
The owner admin durability view is now verified and no longer a missing check.
