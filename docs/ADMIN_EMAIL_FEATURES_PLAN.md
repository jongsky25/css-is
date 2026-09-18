# Admin email control center — implementation plan

**Status:** planned, not started. Build follows this plan phase by phase.
**Owner:** avincentpatrick
**Why:** Office Connect sends 20+ distinct emails (account/auth, event
lifecycle, wellness, work arrangement, CSM results, Spot Feedback, the
scheduled reminder jobs) from `mailer.py` / `app.py` / `send_reminders.py`,
but there is **no admin surface for any of it**. Every message is
unconditional — the only kill switch is unplugging the transport entirely
(`CSS_MAIL_RELAY_*` / `CSS_SMTP_*` env vars), which silences *everything*,
including account invites and password resets. An admin cannot turn off just
the CSM digest, preview what a message looks like, resend a failed one, or
see why a send failed without SSHing in and reading `outbox.log`. This plan
adds one admin module, `/admin/email`, that makes every email feature
individually visible and controllable, alongside the existing `/admin/ai`,
`/admin/rules`, `/admin/sharing` consoles it's modeled on.

**Non-goal:** rebuilding transport (`mailer.py`'s relay/SMTP logic) or
composing new email types. This is a control layer over what already sends.

---

## 1. What exists today (leverage, don't rebuild)

| Ingredient | Where | State |
|---|---|---|
| Transport (HTTPS relay + SMTP, `send()`, `email_configured()`) | `mailer.py` | done — untouched by this plan |
| 21 message composers (`invite_message`, `wellness_pending_message`, …) | `mailer.py` | done — each returns `(subject, body, html)` |
| Outbox audit trail (every send attempt, success or failure) | `mailer.py` `_record()` → `outbox.log` (flat file, append-only) | done, but unqueryable — no admin can read it in the UI |
| Request-triggered sends (invite, reset, registration, certificate, raffle, event created/section-notify, wellness/AWA pending/decided, feedback update) | `app.py`, ~13 call sites | done — all unconditional |
| Scheduled/batch sends (event reminders, wellness expiry, digest, CSM results ×2, wellness/AWA file nudges) | `send_reminders.py`, 7 jobs, run daily from `app._scheduler_loop` | done — all unconditional, each independently selectable only via CLI flags, not from the UI |
| Tunable settings store (`app_setting` k/v table) | `storage.py` `get_setting`/`set_setting`/`get_settings` | done — exact mechanism to reuse |
| Admin console pattern: nav entry with `cap`, GET (read settings) + POST (write + `_audit` + redirect with `?msg=`) | `/admin/sharing` (`app.py:2614-2639`, `admin_sharing.html`) | done — smallest example to clone |
| Richer admin console pattern: settings + live status + a log/list view + test-connection action | `/admin/ai` (`app.py:3687-3800`, `admin_ai.html`) | done — closest shape to what this module needs |
| Capability gating | `auth.ROLE_CAPS["admin"]` includes `manage_users`; every existing settings console (`ai`, `rules`, `sharing`, `wa_reopen`) gates on that same cap | done — reuse `manage_users`, no new role |
| Audit logging helper | `app._audit(request, conn, action, target_type=, summary=)` | done |
| Nav registration | `NAV_GROUPS` "Administrator" group (`app.py:603-651`) | done — add one entry |

## 2. Design decisions

**D1 — one settings key per email *feature*, not per composer.**
21 composers map to ~14 admin-meaningful *features* (grouping composers that
always fire together for the same event, e.g. `wellness_pending_message` +
`wellness_pending_reminder_message` are both "wellness approval
notifications"). A feature is what an admin thinks in; a composer is an
implementation detail. Each feature gets one boolean setting,
`email_feature.<key>`, default `"1"` (on) — enabling this module ships with
**zero behavior change** until an admin actually flips something.

**D2 — one gate function, called at every existing send site.**
`mailer.feature_enabled(conn, key)` reads `email_feature.<key>` (default on).
Every call site that currently does:

```python
mailer.send(to, subj, body, html=html)
```

becomes:

```python
if mailer.feature_enabled(conn, "wellness_approval"):
    mailer.send(to, subj, body, html=html)
```

This is a **mechanical, low-risk sweep** — no composer logic changes, no
signature changes, just a guard at each of the ~20 call sites in `app.py`
and 7 jobs in `send_reminders.py`. `conn` is already in scope at every site
(it's how the DB got queried in the first place).

**D3 — global kill switch stays orthogonal.**
`mailer.email_configured()` (transport present) and the new per-feature
toggle (admin choice) are independent gates — both must pass. A feature
switch never claims to send when no transport exists; the admin console
surfaces `email_configured()` as a read-only status banner (mirroring
`/admin/ai`'s connection status) so the two concerns aren't confused.

**D4 — three kinds of "features" need three different controls, not one
big on/off grid:**

1. **Transactional** (invite, reset, registration confirmed, certificate
   ready, raffle winner, event created/section notify, wellness/AWA
   pending/decided, feedback update) — per-feature on/off only. These fire
   from user actions; there's nothing to schedule.
2. **Scheduled jobs** (the 7 in `send_reminders.py`) — per-job on/off
   **plus** the existing CLI selectivity now exposed as checkboxes, so an
   admin can, from the browser, do what today requires SSH + flags.
   `send_reminders.run(jobs=...)` already accepts a job subset — the admin
   toggle becomes the source of that subset instead of (only) CLI args, so
   `_scheduler_loop`'s nightly call passes `jobs={k for k in _ALL_JOBS if
   mailer.feature_enabled(conn, JOB_FEATURE_KEY[k])}`.
3. **Never gated:** password reset delivery once a reset is *requested* and
   account invite delivery. These are security/account-recovery critical —
   turning them off would lock an admin out of fixing exactly that. They
   stay always-on, and the console explicitly labels them "not disableable"
   rather than silently omitting the toggle (an admin should never wonder
   why one is missing).

**D5 — preview and resend, not a full email builder.**
Composing new templates from the UI is out of scope (would require a
template language, i18n, and a much bigger surface). What IS in scope and
high-value: **render a preview** of each composer with representative sample
data (reusing the real `mailer.*_message()` functions — guarantees the
preview never drifts from the real output) and a **"send test to myself"**
button per feature, mirroring `/admin/ai`'s "Test connection" pattern
(`app.py:3766-3799`). This lets an admin verify a feature looks right
*before* toggling it on, and gives non-technical admins a way to sanity
check without reading `outbox.log`.

**D6 — the outbox becomes queryable, not just tail-able.**
`_record()` already writes every attempt (sent/failed/not-configured) to
`outbox.log`. Add a thin parser (`mailer.recent_outbox_entries(limit=200)`)
that reads the log's existing `===== timestamp [note] =====` delimiter
format and returns structured rows `{ts, note, to, subject}` for the newest
N entries, newest first. No schema change, no new table — the log is
already the durable record; this just makes it legible in the browser
instead of requiring file access. (If the log grows large, cap the read to
the last ~2 MB, tailed, same trick `csm_report.py`/`audit.html`-style
log viewers in this codebase already use elsewhere — verify against
`admin_audit`'s pattern in Phase 1.)

## 3. Schema (Phase 1)

No new tables. Reuses `app_setting` (already a generic k/v store):

| key | values | default | meaning |
|---|---|---|---|
| `email_feature.event_created` | `"1"`/`"0"` | `1` | creator gets "event created" mail |
| `email_feature.event_section_notify` | `"1"`/`"0"` | `1` | section chief gets "new event under your section" |
| `email_feature.event_reminder` | `"1"`/`"0"` | `1` | day-before reminder (registrants + creator + chief) — **scheduled job** `events` |
| `email_feature.registration_confirmed` | `"1"`/`"0"` | `1` | "you're registered" |
| `email_feature.certificate_ready` | `"1"`/`"0"` | `1` | certificate-ready notice |
| `email_feature.raffle_winner` | `"1"`/`"0"` | `1` | raffle winner notice |
| `email_feature.wellness_approval` | `"1"`/`"0"` | `1` | pending + expiry-reminder to approver — **partly scheduled** (`wellness_expiry` job) |
| `email_feature.wellness_decided` | `"1"`/`"0"` | `1` | approve/deny result to claimant |
| `email_feature.wellness_file_reminder` | `"1"`/`"0"` | `1` | **scheduled job** `wellness_file` |
| `email_feature.awa_approval` | `"1"`/`"0"` | `1` | pending notice to approver |
| `email_feature.awa_decided` | `"1"`/`"0"` | `1` | decision result to requester |
| `email_feature.awa_reopened` | `"1"`/`"0"` | `1` | filing-reopened notice |
| `email_feature.awa_file_reminder` | `"1"`/`"0"` | `1` | **scheduled job** `awa_file` |
| `email_feature.approvals_digest` | `"1"`/`"0"` | `1` | **scheduled job** `digest` |
| `email_feature.csm_results` | `"1"`/`"0"` | `1` | RP + activity CSM-ready mail — **scheduled jobs** `csm_rp` + `csm_activity` |
| `email_feature.feedback_update` | `"1"`/`"0"` | `1` | Spot Feedback reply/status update |

Not represented (always-on, per D4-3): `invite_message`, `reset_message`,
`recovery_message`.

`email_feature.<key>` values are read through `storage.get_settings(conn,
ALL_KEYS)` in one query (already the pattern `/admin/ai` uses for its
multi-setting reads) rather than N round-trips.

## 4. New module surface: `mailer.py` additions

```python
FEATURES = {  # key -> (label, hint, scheduled_job_name | None)
    "event_created": ("Event created", "Creator gets a confirmation when they create an event.", None),
    "event_section_notify": ("New event under your section", "Section chief is notified.", None),
    "event_reminder": ("Day-before event reminder", "Registrants + creator + chief.", "events"),
    "registration_confirmed": ("Registration confirmed", "Attendee gets their personal link.", None),
    "certificate_ready": ("Certificate ready", "Sent once feedback is complete.", None),
    "raffle_winner": ("Raffle winner", "Winner notice with a link on file.", None),
    "wellness_approval": ("Wellness approval needed", "Approver gets pending + expiry reminders.", "wellness_expiry"),
    "wellness_decided": ("Wellness decision result", "Claimant gets the approve/deny outcome.", None),
    "wellness_file_reminder": ("Wellness filing nudge", "Weekly nudge to unused-entitlement staff.", "wellness_file"),
    "awa_approval": ("Work arrangement approval needed", "Approver gets the pending notice.", None),
    "awa_decided": ("Work arrangement decision result", "Requester gets the outcome.", None),
    "awa_reopened": ("Filing reopened", "Staff notified when an admin reopens a missed period.", None),
    "awa_file_reminder": ("Work arrangement filing nudge", "Day-before-deadline nudge.", "awa_file"),
    "approvals_digest": ("Pending approvals digest", "Weekly Monday bundle per approver.", "digest"),
    "csm_results": ("CSM results ready", "RP + activity creator/chief notices.", "csm_rp+csm_activity"),
    "feedback_update": ("Spot Feedback update", "Submitter told of a status/reply.", None),
}
ALWAYS_ON = {"invite": "Account invite", "reset": "Password reset",
             "recovery": "Registration recovery link"}

def feature_enabled(conn, key: str) -> bool: ...
def set_feature_enabled(conn, key: str, on: bool) -> None: ...
def recent_outbox_entries(limit: int = 200) -> list[dict]: ...
```

`app.py` and `send_reminders.py` sites are swept to call
`mailer.feature_enabled(conn, "<key>")` before `mailer.send(...)`. In
`send_reminders.py`, jobs backed by a feature also get gated at the `run()`
job-selection level (D4-2) — the per-recipient guard inside the loop stays
too, since a mid-run toggle shouldn't need a process restart to take effect,
and a scheduled-job feature can be flipped off exactly like a transactional
one.

## 5. Routes & templates (Phase 2)

| Route | Method | What |
|---|---|---|
| `/admin/email` | GET | Status banner (`mailer.email_configured()` + which transport), grouped feature toggles (Transactional / Scheduled jobs / Always-on, per D4), recent outbox entries (last 50, `mailer.recent_outbox_entries`) |
| `/admin/email/toggle` | POST | `key`, `on` — `set_feature_enabled` + `_audit("email_feature_toggle", target_type="setting", summary=f"{label} turned {ON/OFF}")` → redirect `?msg=Saved.` |
| `/admin/email/preview/{key}` | GET | Renders the feature's HTML composer output with sample data in an `<iframe srcdoc>` (same trick as viewing any transactional HTML safely — no live data touched) |
| `/admin/email/test` | POST | `key` — composes the sample message and `mailer.send()`s it to the requesting admin's own `username`; reuses `/admin/ai`'s try/except → `?msg=`/`?err=` pattern (`app.py:3766-3780`) |

One template, `admin_email.html`, following `admin_ai.html`'s layout
(status card at top, grouped settings form, a log/list table at the bottom)
rather than `admin_sharing.html`'s single-toggle simplicity — this page has
more moving parts.

Nav: one entry in the `Administrator` group, `cap: "manage_users"`, placed
by usage once real data exists (start it near `sharing`/`ai` since it's a
sibling console):

```python
{"key": "email", "url": "/admin/email", "label": "Email",
 "hint": "Turn email features on/off, preview & resend",
 "kw": "email mail notifications toggle preview outbox resend transactional "
       "reminders digest csm wellness awa feedback",
 "cap": "manage_users"},
```

## 6. Sample-data providers for preview/test (the fiddly part)

Every composer takes real IDs/names/links pulled from the DB at send time.
For preview and "send test to myself" to work with zero live data
dependency, each `FEATURES` entry needs a small sample-args lambda, e.g.:

```python
"wellness_approval": lambda: mailer.wellness_pending_message(
    "Jane Dela Cruz", "Juan Santos", "2026-10-02", "10:00 AM", 2,
    "https://example.invalid/wellness/approvals",
    approve_link="https://example.invalid/wellness/decide/1?token=sample&action=approve",
    deny_link="https://example.invalid/wellness/decide/1?token=sample&action=deny"),
```

These live beside `FEATURES` in `mailer.py` (co-located with the composer
they preview) rather than in `app.py`, keeping `app.py`'s route thin: `GET
/admin/email/preview/{key}` just calls `mailer.render_preview(key)` →
`(subject, html)`.

## 7. Build order

1. **Schema + gate function** — `FEATURES`/`ALWAYS_ON` constants,
   `feature_enabled`/`set_feature_enabled`, `recent_outbox_entries`. Tests:
   default-on behavior, toggle round-trip, unknown key defaults safe-on
   (never silently drop a real send because of a typo'd key).
   *No visible change yet; every existing test still passes untouched.*
2. **Call-site sweep** — gate all ~20 `app.py` send sites +
   `send_reminders.py`'s per-recipient sends + job-level `run()` selection.
   Tests: one per feature key confirming `send()` is skipped when off and
   fires when on (extends `tests/test_notifications.py` /
   `tests/test_send_reminders.py` patterns already in place).
3. **Console UI** — `admin_email.html`, GET/POST toggle route, nav entry,
   audit logging. Tests: RBAC (non-admin 403, mirrors `test_auth_rbac.py`
   coverage of `/admin/ai`/`/admin/sharing`), toggle persists, always-on
   features render as non-interactive.
4. **Preview + test-send** — sample-data lambdas for all 16 gated features
   (+3 always-on, previewable but not toggleable), preview route, test-send
   route with the same `email_configured()`-false messaging `/admin/ai`
   uses for its own "not configured" case.
5. **Outbox view** — `recent_outbox_entries` wired into the template,
   newest-first, with the send/fail/not-configured status visually
   distinguished (color dot, same idiom as `/ops` health states).
6. **Ship** — `version.py`/`CHANGELOG.md` entry, `docs/QA_PLAYBOOK.md`
   pass covering "toggle a feature off → trigger it → confirm no send,
   `outbox.log` still doesn't grow", i18n review on new UI strings.

## 8. Out of scope (explicitly)

* No per-user/per-recipient email preferences (e.g. "let staff opt out of
  reminders") — this module is an *admin* control, not an end-user one.
* No template editor — subject/body wording changes still require editing
  `mailer.py`'s composers directly.
* No new transport options — HTTPS relay and SMTP as configured today.
* No changes to `invite_message`/`reset_message`/`recovery_message`
  delivery (see D4-3) — account-recovery mail is never admin-disableable.
* No retry/queue system for failed sends — `outbox.log` remains the record
  of what failed; resending is the explicit "send test" action, not an
  automatic retry.
