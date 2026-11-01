# Private daily work brief

Draft PR #572, candidate 9.61. Deployment, activation and live acceptance remain
deferred. `/brief` is an on-demand private webhook reply, with no arguments.
It creates no meeting, request, approval, task transition or scheduled delivery.

## Included information

- Calendar: the signed-in calendar's `mine` scope, calendar entries only, today
  through six days ahead in Asia/Manila. Show the first two entries and the total
  in that range; the full date-range command retrieves the remaining results.
  This includes all-day entries and earlier entries on the current day; it is a
  dated calendar overview, not a claim that every entry is still upcoming.
- Work: the existing current-permission summary of own overdue/upcoming/review
  tasks and accessible work awaiting review. Linked restricted documents continue
  to suppress work and task counts through the source RegistryScope.
- Requests: own room requests in the same seven-day range; supplies needing
  requester action through the canonical dashboard policy; newest two own travel,
  standalone meals, room-linked meals and arrangement filings, with actual source
  statuses and matching detail/list commands. Recent filings include all statuses;
  they are not presented as a count of pending requests or an active schedule.

Each section requires its existing read consent, source module, host pilot and
transport support. There is no new umbrella grant. A paused/revoked source is
omitted before querying business records. If no chosen section is available, the
brief explains this and points to `/status`. Documents are not part of this
brief. Task outputs, notes, amounts, people and meal dietary fields are excluded.

The same active account, sender/private chat, bot identity/fingerprint and link
generation fences apply. Group/topic, direct transport and unlinked requests
cannot retrieve a brief. The response is built in the existing intake transaction
from current source records. It uses the existing deduplication/rate limit and
uncertain-response receipt; no business text is queued for later replay. Entire
sections fit within a bounded UTF-16 message budget; `/menu` leads to full results.

## Saved choices, with delivery deferred

The existing signed-in notification page (`/account/telegram/notifications`) has
an independent daily-brief form. It works at phone width without JavaScript:

- Calendar, work and requests sections default selected for on-demand use.
  At least one section must remain selected. Selection never grants permission.
- The future reminder preference defaults off, with preferred time 08:00 Manila.
  A user may save an explicit preference and time now. The page and save result
  explicitly state that scheduled daily brief delivery is not active.
- A separate revision prevents stale overwrites. The current account/session,
  CSRF, allowlisted fields, time validation, bounded body and rate limit are
  checked. Preference changes and their audit record share one transaction.

`telegram_brief_preference` is installed idempotently and stores only these
choices. Existing calendar/room reminder settings, email channel choices, quiet
hours, grants and host switches are unchanged. Restore preserves choices while
the existing restore procedure invalidates connections/sessions/grants. There
is deliberately no worker, enqueue path, cron, scheduler hook, delivery flag or
automatic activation consuming the future reminder preference. A later delivery
implementation must define consent renewal, quiet hours, deduplication, current
source checks, expiry and rollback before any separately authorized live pilot.

Synthetic tests cover restricted sources, own-only projections even for admins,
scope/host revocation, identity/transport/privacy fences, duplicate updates,
invalid arguments, Unicode budgets, staged preferences, atomic audit failure,
restore and a real 390×844 script-free browser save with stale/CSRF/session denials.
Use the [later live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md); all live
cases are still Pending.
