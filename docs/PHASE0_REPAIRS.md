# Phase 0 repair release — Office Connect 7.23

**Continuation, 20 October 2026:** live verification is now deferred at the user's direction. Local work continues in candidate 7.24; see [Phase 1 progress](PHASE1_LOCAL_PROGRESS.md). The results and hashes below describe the earlier 7.23 candidate.

Branch: `fix/phase-0-authority-persistence-sessions`, based on `3a45851`.
Prepared on 19 October 2026. This is a local repair release candidate; no production deployment or live data change has been performed.

## Scope and status

This implements the three immediate code repairs identified in [the audit](audits/2026-10-19/README.md): A01/F01 authority containment, A02/F02 persistence correctness and A03/F03 session revocation. A00 production discovery remains blocked by the execution environment's enforced network policy: the production host is not an allowed destination and no hosting identity is configured. The supplied login has not been used.

Production settings, deployed dependencies, authority assignments and actual backup recovery remain unverified. The broader managed-authority redesign, CSRF/rate-limit hardening, safe service-worker retries, analytics repairs and release automation remain in the [phased roadmap](audits/2026-10-19/ROADMAP.md).

## Behavior changes

### Profile authority containment

- A linked staff member's directory designation is read-only on the profile page. Forged or stale profile submissions cannot modify that directory field, including clearing it. Administrators maintain it through directory administration.
- Unlinked accounts can still edit their display designation; a display title does not create a directory leadership assignment.
- Photo, signature, companion, nickname, birthday and notification preferences remain editable under their existing rules.
- Existing directory-based leadership remains in place. Review existing leadership titles/assignments before release; this patch cannot determine whether previously saved titles were legitimate. The full managed-assignment model is A04.

### Revocable sign-ins

- New sign-ins receive a random session ID in the signed cookie and a corresponding `login_session` record. A signed cookie alone is insufficient.
- Each authenticated request resolves the active account and current role from that record. Cookie role claims are not authorization authority.
- Logout removes that session record. Other devices stay signed in.
- Changes to username, password/hash/salt, role, active status or forced-reset state revoke all sessions for that account through database triggers. Direct maintenance SQL is covered too. Deleting/recreating an account ID cannot revive the deleted account's sessions.
- Issuance holds a database transaction and checks that the verified password hash still matches, preventing a password change between verification and session registration from reviving access.
- Old cookies require fresh login on upgrade. Restoring a database also clears sessions so a backup cannot revive a previously revoked cookie. Other domain permissions continue to resolve their existing live grants/scopes.
- Malformed, expired, future-dated and unregistered tokens fail authentication safely. Protected GETs redirect to login and protected writes return 401.

### Periodic snapshots and recovery

- When `CSS_PERSIST_DIR` is configured, take a snapshot every `CSS_PERSIST_TICK` (default 60 seconds). The faulty comparison of `PRAGMA data_version` across fresh connections has been removed.
- A failed or stale save marks durability health unhealthy. An idle database still requires a recent successful snapshot.
- A timed-out worker remains tracked. Later ticks wait for the same attempt; they do not accumulate overlapping snapshot threads. Shutdown drains an outstanding attempt before requesting a final save, subject to the timeout.
- The high-water marker is measured from the completed snapshot rather than a potentially newer live database.
- The intentional tradeoff is additional snapshot I/O on idle databases. Measure actual copy duration and bucket cost before tuning the interval or reintroducing change tracking.
- A Python thread cannot kill a stuck filesystem operation. The timeout bounds the application's wait and prevents worker accumulation; it is not a hard I/O/process cancellation guarantee. A persistent mount failure still requires operations recovery. Saved snapshots are in the configured bucket's failure domain; verify an independent recovery copy if required.

## Database migration and compatibility

`storage.init_db()` adds one table (`login_session`), two indexes and two revocation triggers. Existing business tables/data are preserved. Re-running initialization is idempotent. Expired session records are pruned during new session registration.

The normal startup/schema path applies the migration. The application restore route now discards the cached schema-ready flag and reinitializes the restored database, including when a snapshot predates this migration. Automatic bootstrap copies and explicit restores clear restored session records.

All HTTP test fixtures now register sessions through the same application issuer. Pure token-integrity tests still exercise `auth.make_token()` directly. This fixture change is necessary because unregistered cookies are intentionally rejected; no test-only authentication bypass was introduced.

## Verification

Primary tests are `tests/test_phase0_security.py` and `tests/test_phase0_persistence.py`, plus existing profile/authentication/cookie/persistence/backup suites. Tests use temporary SQLite databases, actual login requests and local snapshot files; no production/provider calls are needed.

Coverage includes profile escalation attempts, explicit restricted-document protection, legitimate directory authority, logout replay across devices, account change/deletion/recreation, malformed/legacy tokens, expiry, migration idempotence, database restore, commits and updates after the first snapshot, failure recovery, stalled-worker reuse and high-water accuracy. The broader suite checks effects across existing business workflows.

Run from a disposable checkout without live data or provider credentials:

```bash
CSS_NO_SCHEDULER=1 python -m pytest -q tests/test_phase0_security.py tests/test_phase0_persistence.py tests/test_profile_edit.py tests/test_persist_health.py tests/test_auth_rbac.py tests/test_secure_cookies.py tests/test_backups.py
CSS_NO_SCHEDULER=1 python -m pytest -q
```

The audit's baseline has known failures; compare failure names/causes rather than treating the whole existing suite as green. Final local results are recorded below after verification.

## Production discovery and promotion gate

1. Confirm the actual deployment revision and the effective `CSS_DB`, `CSS_PERSIST_DIR`, tick/timeout/retention settings, bucket mount and backup location. Do not infer these from old documentation. Inspect settings names/status without publishing secret values.
2. Download or otherwise obtain a current consistent backup through the authorized administration path. Restore it in isolation, check SQLite integrity, and reconcile representative users, directory assignments, responses, documents/work and required attachments/configuration. Verify no outbound jobs/providers run in that environment.
3. Review director/chief/delegate assignments with the owner, including recent designation edits. Correct unauthorized assignments through trusted administration before enabling integrations or relying on approvals.
4. Build/test the exact intended runtime (Docker currently targets Python 3.11; local audit/repair tests use 3.12). Run the focused regressions and classify remaining baseline failures. Verify environment parity before promotion.
5. Notify staff that the release requires signing in again. Stage the migration against a restored copy and test login, self-profile edits, legitimate approvals, restricted-document denial and logout/account-change revocation.
6. During a controlled production release, capture a pre-release snapshot, promote the reviewed artifact and verify version 7.23. Observe successive saves after separate committed changes, induced failure reporting in staging, and a restore from the resulting snapshot. Confirm actual recovery point/time against the agreed objectives.
7. Monitor denied/failed sign-ins, 5xx responses, snapshot age/duration and operator reports. A successful health request is not proof of successful durable recovery.

Merging to `main` currently triggers production deployment. Keep this repair on its review branch until production access, backup verification and the release decision are complete.

## Rollback and recovery

- Prefer a forward repair that retains the authority and session boundaries. Reverting to 7.22 reintroduces the demonstrated defects.
- The session schema is additive and can remain during a code rollback, but old code ignores it. If a rollback is unavoidable, restrict service access while preparing a compatible secure patch; do not treat schema compatibility as security compatibility.
- Do not restore an older database merely to undo a code change: it can discard subsequent business writes. Preserve a current consistent copy and reconcile any required data recovery explicitly.
- Run restores in a maintenance window with incoming writes/jobs stopped. Use the supplied restore path (which clears sessions); for an external/manual restore, clear `login_session` if present before serving traffic, then restart/reapply schema initialization. Verify integrity and business totals and require fresh sign-in.
- A timeout with a still-running snapshot worker is not permission to start more writers. Diagnose the mount/process and preserve known-good snapshots before restarting. Retain the stale-lineage guard.

## Local verification results

- **Final focused suite:** 173 passed, no failures or skips (approximately 11 seconds), including the later regression for restoring a database without the new session schema.
- **Broader regression run:** 4,020 passed, 36 failed, 16 skipped (4,072 collected; approximately 205 seconds). This run preceded the final additional legacy-restore test; the final focused run covers that change.
- **Failure comparison:** 35 failures match the original audit baseline. The one additional date-display failure was reproduced on an isolated, unchanged `3a45851` checkout: the test expects the UTC date while the page uses the local date. Twelve earlier calendar/lead-time failures no longer occurred at this run's time; these repairs are not credited with fixing them. The signature test now checks missing-signature behavior before deleting its account.
- **Preflight:** zero failures, one warning because no `_backups` directory was available for the size comparison.
- **Production connection:** user authorized host access, but the actual proxy still rejected CONNECT with HTTP 403 and the current enforced allowlist excludes the host. No login or production operation was attempted beyond an unauthenticated health connection.
- **Runtime parity:** Python 3.12.14 was available locally; the deployed Python 3.11 runtime remains a promotion gate.

[Machine-readable verification and source hashes](phase0/verification.json) preserve the measured results and failure names. The full suite remains non-green because the unrelated baseline issues have not been folded into this repair release.
