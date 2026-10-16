# P2.2 — Mentions, followers and unread state

October 16, 2026. **In review**, version **6.61**, branch `codex/work-updates`. P2.1 was merged at `9622870` before this increment. P2.2 was subsequently merged at `4a44fc0` on the user’s instruction. Live deployment success has not been independently verified.

## Delivered

- Mention picker for new messages, replies and edits, limited to people with current work-item and linked-source access. Mentioning someone never changes authority or access. Plain `@name` text does not silently resolve accounts.
- Follow/unfollow a contribution discussion or a whole work item. Work-item following covers all its discussions; contribution following covers that thread only. Existing unread alerts remain after unfollowing; explicit mentions and replies can still notify the recipient.
- Durable in-app alerts for selected mentions, direct replies and new messages in followed discussions. All reasons converge on one unique recipient/message alert, with mention taking priority for a newly created alert. Self-alerts are suppressed. Editing does not repeat an existing alert; newly mentioned people can receive their first alert.
- Discussion updates inbox linked from Shared work navigation and the existing notification bell. The bell indicates an unread discussion group, rather than claiming a total unread-message count. Inbox pages scan at most 250 candidates to return up to 25 currently permitted notices, with continuation through inaccessible rows. The bell continues through those pages until it finds a permitted alert or exhausts them.
- Revision-aware unread badges and an explicit “Mark displayed messages read” action. GET does not change read state. Only the displayed revisions are acknowledged; a concurrent edit remains unread in the thread. Read state moves forward monotonically. Authors have read their own saved version.
- Mention lists are retained with each edit for visible history. Discussion, task and approval revision boundaries stay separate.

## Permission and delivery rules

Creation validates every mentioned account and atomically saves the message, mention history, targeted alerts and author read state. If an account loses access or any insert fails, the whole write rolls back. Followers and reply recipients are checked for current access when creating alerts. Every inbox/bell delivery and message/history read checks active account status, work membership and every linked document again. Revoked access hides historical alerts and prevents subsequent delivery. Saved follow rows do not grant access.

These are in-app notifications only; this increment does not send email or modify official dispatch settings. Email preferences/digests remain P3.4. Existing work feature switches gate content/follow changes; permitted history and marking it read remain available while writes are disabled.

## Storage and deployment

Additive follow, mention, per-message read and targeted notice tables. Unique indexes suppress duplicate following and alerts. Mention history is append-only. Existing data is preserved by repeated schema installation. The new `work_updates.py` module is included in the deployment allowlist. Version/changelog is 6.61.

## Verification

**145 passed** across shared work, Documents, setup, routes, Workspace operations and existing notification tests. Only the existing Starlette/httpx deprecation warning. New coverage includes mention/follower/reply deduplication, scope and unfollow, edit-time mentions, no self-alert, atomic notice failure, read-revision races, cross-thread mark-read rejection, inactive/revoked access, disabled writes, persistent notices, permission-aware paging beyond 250 hidden updates, HTTP CSRF, and no GET read-state mutation. Existing document/task independence and deployment dependency checks also pass.

Chromium journey: two confirmed contributors; follow, mention selection, one alert for overlapping reasons, unread/read transitions, unfollow and later direct mention. Desktop 1440px and mobile 390px checks passed without horizontal overflow or browser errors. Local artifacts: `/workspace/scratch/work-p22`. Test report: `/tmp/work-p22-tests.xml`.

## Next

Review and merge P2.2, then P2.3 — blockers, follow-up owner/date and task dependencies, including cycle rejection and preserving official deadlines. Phase 2 acceptance and live deployment verification remain separate.
