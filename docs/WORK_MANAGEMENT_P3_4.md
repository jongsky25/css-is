# P3.4 — Notification preferences and digests

October 17, 2026 (Asia/Manila). **In review**, version **6.75**, branch `codex/work-digests`, based on merged P3.3 (`516ad91`). This increment is not merged or deployed. Phase 3 acceptance remains open.

## Delivered

- Discussion updates has separate **All discussion updates**, **Mentions and replies**, and **Following** views, with permission-aware pagination and links to My work and Reviews and approvals.
- Each active account can choose whether routine follower updates appear in its notification bell. The default preserves existing behavior. Hiding routine alerts neither unfollows discussions nor marks messages read. Mentions and replies remain eligible for the bell. A later explicit mention promotes an existing routine notice without creating a second notice or replaying its original read/delivery state.
- Required task actions, reviews, document deadline and workflow notices keep their existing providers and controls. Personal discussion preferences cannot disable them.
- Personal email digests are **off by default**, with daily and weekly (Monday) choices. They include eligible unread discussion notices across all three categories, independently of the routine bell setting. Preferences remain editable when shared-work writes are disabled; digest delivery requires shared work to be enabled.
- Digests run through the existing daily reminder sweep (first run at or after 07:00 Philippine time), with a separate **Shared work — discussion digests** toggle, sample preview and send log in the admin email console. The normal scheduler needs the configured public base URL and mail transport. No new worker or cron process is required.
- Recent digest attempt status is visible to the recipient. Sent means transport acceptance, not confirmed inbox delivery or message acknowledgment. Opening a digest never marks discussion messages read.

## Access and duplicate prevention

An email contains a generic unread-discussion notice and a link to `/work/updates`. It contains no case titles, discussion excerpts, author names, attachment links or item counts. Authorized details are rendered in the app using current permissions.

Creation and delivery check active account status, work membership and every linked source. Read and inaccessible notices are excluded before claiming, then checked again immediately before transport. Items read or revoked after claiming are removed from that batch. Opt-out, deactivation or loss of all eligible updates cancels an unstarted send. In-app reads always recheck current access, including when access changes after an email has left the server.

A serialized transaction claims a recipient/date/period and its notice IDs before external I/O. Unique constraints prevent competing workers, repeated sweeps and cadence changes from creating duplicate attempts. A notice appears in at most one attempted digest; previous unread notices stay readable in the app without repeated emails. New unread notices can enter a later eligible digest. A known pre-send cancellation releases notice claims for future eligibility, while preserving its batch history.

A crash after claiming leaves **Attempt started; delivery not confirmed**; exceptions and non-confirming transport responses leave **Delivery uncertain**. Neither state is automatically retried, even on a later day or after a cadence change. There is no resend control in this increment. Users can read all current updates in the app. A missed Monday is not caught up on Tuesday; the weekly sweep next runs on Monday. These choices avoid duplicate notifications during interrupted sweeps.

The application makes one transport call per batch; the existing mail transport retains its own behavior. No claim of end-to-end exactly-once email delivery is made.

## Storage and deployment

Additive personal preferences, digest batch and notice-claim tables; repeated schema installation preserves preferences and history. Preferences use current account identity, session-bound CSRF and optimistic revisions to reject stale forms. Submitted user IDs cannot change someone else’s preferences. Category values are allowlisted, and filtering happens before paginated access checks.

`work_digests.py` is included in the explicit HF deployment allowlist. `send_reminders.py` registers `work_updates` and its `job_work_updates` admin toggle. Existing official document sending switches remain scoped to the Documents sender. Optional discussion mail uses its own job toggle and personal opt-in.

## Verification

**298 passed**, zero failures, errors or skips, across shared work, Documents, setup, routes, Workspace operations, notifications, admin email and scheduled reminders. The only warning is the existing Starlette/httpx deprecation. JUnit evidence: `/tmp/work-p34-tests.xml`.

New coverage includes defaults, personal ownership, stale forms, invalid values, CSRF, disabled-work preference editing, routine/direct filters, promotion after an explicit mention, unread preservation, required task/review alerts, dry runs, cadence and date deduplication, competing connections, crash/exception/uncertain delivery, feature and transport switches, inactive accounts, source revocation, opt-out after claim, read-state changes before send, atomic rollback and scheduler registration. All transport tests use synthetic recipients and a stubbed mailer.

Chromium checks passed at 1440px desktop and 390px mobile: category navigation, initial opt-out, weekly selection, keyboard save, persisted values and opt-out, and honest unavailable-delivery messaging. No horizontal overflow or browser errors. Artifacts are in `/workspace/scratch/work-p34`. No real emails were sent. Live transport, deployment and operational acceptance remain Phase 4 checks.

## Next

Review and merge P3.4, then **P3.5 — Manager support overview**: unassigned work, blockers, review waits and outcomes at risk, each linked to matching authorized records with clear count and date semantics.
