# Personalized private Telegram menu

Draft PR #572, candidate 9.58. Deployment, activation and real-user testing remain
deferred. This addition changes discovery/guidance, not permissions or records.

- `/menu` aliases the existing private `/help` path. Both show the same current
  account-specific menu, grouped Calendar, Tasks and work, Documents and Requests.
- Only enabled, explicitly consented features with their source modules,
  prerequisite grants and required reply transport available appear as commands.
- `/status` explains available features and why other features are unavailable:
  paused host/source controls, unsupported delivery mode or exact missing consent.
  It names no unavailable feature commands. An account being linked still gets
  its original private confirmation flow; `/menu` directs it to `/status` instead
  of replacing its pending challenge with another start command.
- Examples cover date/calendar lookup, task filters and number/subject search.
  ID/reference placeholders must be replaced with the values in the user's own
  results; an example never supplies an operation/confirmation credential.

Menus read current account/link/bot/grant/settings state on every rendering.
They query no source business records and cache no feature entitlement. A menu
is a discovery aid: individual records, ownership, revisions, current modules and
workflow rules are still checked by every command. Write features in a menu are
not permission to mutate an arbitrary record or skip confirmation. A future
change can invalidate an earlier displayed menu; issue a fresh `/menu` or `/status`.

Unlinked help stays neutral and does not advertise business commands. Group/topic
messages cannot obtain this private menu. Direct transport retains supported
calendar/room/work and existing guided-action discovery but hides webhook-only
features. Whole inbound/delivery pauses can prevent any bot reply; use the
signed-in account page/Operations for those global conditions. A command menu
cannot repair an offline provider or change host settings.

## Result guidance

Lists now include their own detail command with the actual record ID/reference;
detail views supply a back command. Existing paging/source links remain intact.
Task detail and task receipts offer acknowledgement/submission only when the
current owner, separate write grant/switch, read grant, source module, reply
transport, open-work and task/blocker rules permit that action. The offered
command still prepares a preview; it cannot commit without confirmation.

Meeting/room guides keep the source form link last, previews keep their exact
confirmation/recovery instructions, and receipts name the matching recovery
command and `/menu`. No hint silently starts another action or causes a retry.
Calendar/room reads retain their existing paging and signed-in source navigation.
No inaccessible titles, counts, people, queued messages or credentials are used
to build menu examples or availability explanations.

There is no Telegram global BotFather command registration, shared command list,
inline callback keyboard, new endpoint, schema, scope or external provider call.
Type `/menu` in the existing private chat. This avoids globally advertising
features or requiring a working outgoing setup call. The signed-in connection
page now points staff to the menu and status commands.

Automated tests cover limited/all/no-grant menus, size limits, current revocation,
source/host pauses, direct-mode restrictions, pending linking, private-only alias
handling, and task-specific write hints. Real phone-width no-script consent/read
flows also exercise the menu/status before disconnect. All records/providers are
synthetic and outgoing Telegram is forbidden. Later live acceptance uses the
[pending private pilot checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
