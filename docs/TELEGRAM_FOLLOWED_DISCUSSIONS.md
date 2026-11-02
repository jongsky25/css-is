# My followed discussions in private Telegram

Draft PR #572, candidate 9.82. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

## Commands and separate read permission

`/my_follows` lists your own saved discussion follows. `/my_follows all`,
`/my_follows work` and `/my_follows tasks` select all saved rows, work-wide rows
or task-specific rows. Work-wide coverage does not create extra task rows in this
list. Task rows separately show whether your work-wide follow also covers them.
Work-wide follows include work-level and every task discussion in that work;
task unfollow does not remove work-wide coverage, and work unfollow retains saved
task-specific follows. See [native follow management](TELEGRAM_DISCUSSION_FOLLOWING.md).

Independent `work.follows.read` consent and default-off
`CSS_TELEGRAM_WORK_FOLLOWS_READ_ENABLED` require separate `work.read` consent and
pilot, current work/every-linked-document access and the source modules. The
existing follow-write, inbox, read-acknowledgement and comment permissions do not
grant this list automatically. List consent grants no follow change, unread
acknowledgement, other-account access or source membership.

Only the linked account's explicit saved rows are selected. Current native source
visibility is rechecked on every page. Task references must still belong to the
same work; inaccessible, missing or inconsistent rows are omitted without names
or hidden counts. Terminal discussions remain readable when current source rules
allow them. Current work/task titles, IDs, exact discussion links and own coverage
metadata are shown. Other followers, discussion/author text, notices, read markers,
task submissions and expected outputs are not read or projected. A SQLite
authorizer on the actual renderer connection enforces those column/table boundaries.

## Paging and current state

Results use descending **work ID, task ID** order; this is not creation-time order.
A work-wide saved row uses task ID **0** in a cursor. Continue using the exact
command printed in the reply, for example `/my_follows all 42:0` or
`/my_follows tasks 42:7`. `/my_follows 42:7` uses the all filter. IDs are canonical
ASCII SQLite-positive integers; task 0 is only a work-wide seek sentinel.

The native composite follow key avoids a new identifier or rowid dependency.
Own account/category/source visibility filters precede a bounded 200-candidate
native scan in batches of 50. Five displayed rows plus lookahead, bounded titles
and a UTF-16 reply budget preserve seek continuation when long Unicode or control
links reduce page size. Scan-bound continuation does not claim a globally empty
list. Pages expose no other-account follows or hidden totals. Each page refreshes
source titles, saved rows and work-wide coverage; nothing is cached as a private
projection. Changes between pages follow normal seek behavior.

## Source and follow-control links

Every displayed row links to its exact current work/task discussion. When separate
`work.follow` consent and pilot are current, it also links to the existing signed-in
follow form with only **case_id/task_id** prefilled. No choice, private origin,
token, draft or operation is embedded in that link. To use controls, first send
`/discussion_follow` in the original private chat. Without a current private origin,
the form explains that a request is needed. Opening a follow-control link creates no origin or operation and changes no follow,
notice or read status. The source discussion retains its normal Office Connect
read-management behavior.

The user must choose Follow/Unfollow, prepare a preview, then confirm privately
before expiry. The existing writer rechecks current consent, actor/source/context
and selected/work-wide state. Revoking or pausing its write capability removes
control links on the next list; old URLs grant no authority. Read-only users keep
their permitted source links without write controls. Unknown URL fields cannot
prefill a choice or bypass the normal strict form/CSRF checks.

## Private delivery and verification

Link/account/bot/generation/private sender/topic/context, current grants/pilots,
source modules, origin and webhook mode are checked. Disconnect, restore, revoked
access and paused pilots prevent stale reads. Unsupported callbacks are ignored
before any private action routing; callbacks without chat IDs cannot raise the old
numeric-comparison error. Duplicate webhook update IDs reply once. Queries remain
ephemeral; retained update/delivery metadata contains no query, source titles or
private projection. Rendering requires the existing intake transaction.

Listing performs no source mutation, read marking, follow change, origin/draft/
operation creation, delivery preference change or scheduler/provider activation.
No source or Telegram schema migration is introduced.

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_followed_discussions.py` and
`tests/test_telegram_followed_discussions_browser.py`. Service checks cover own
rows/current visibility, filters/coverage, strict composite paging and SQLite bounds,
Unicode/control-link budgets, bounded SQL/native scans, no writes/no cached query,
real-connection SQL minimization, refresh, current context/consents and independent
linking. Two 390×844 JavaScript-disabled phone cases cover read-only source links
and separately enabled controls: no implicit private request, source-only prefill,
no preselected change, explicit existing preview/confirmation and refreshed saved
rows. Four existing follow-writer phone flows are rechecked alongside them. All
data and provider transports are synthetic/blocked. See [evidence](SETUP_STATUS.md)
and [pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
