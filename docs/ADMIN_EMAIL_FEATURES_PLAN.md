# Admin email control center — implementation plan

**Status:** Phase 1 done (v2.88). Phase 2 done (v2.89). Phase 3 done (v2.90).
Build follows this plan phase by phase.
**Owner:** avincentpatrick
**Why:** Office Connect now sends 21 distinct emails (account/auth, event
lifecycle, wellness, work arrangement, CSM results, Spot Feedback, and the
seven scheduled reminder jobs added in v2.86), but there is **no admin
surface for any of it**. Every message is unconditional — the only kill
switch is unplugging the transport entirely (`CSS_MAIL_RELAY_*` /
`CSS_SMTP_*`), which silences *everything*, including account invites and
password resets. An admin cannot turn off just the weekly digest, see what a
message looks like before it goes out, or find out why a send failed without
shell access to read `outbox.log`.

This plan adds one admin module, `/admin/email`, that makes every email
feature individually visible and controllable — a sibling to the existing
`/admin/ai`, `/admin/rules` and `/admin/sharing` consoles, built from the
same parts.

**Non-goal:** rebuilding transport (`mailer.py`'s relay/SMTP logic) or
writing new message types. This is a control layer over what already sends.

**Build discipline:** one phase = one PR = one `APP_VERSION` bump = one
layman `CHANGELOG` entry, with `bash run_tests.sh` green before the PR
opens. Phases are ordered so each de-risks the next, and each is
independently safe to deploy (see §2, D7 — merging to `main` ships to the
live Space immediately). Do not build ahead of the current phase.

---

## 1. What exists today (verified — leverage, don't rebuild)

| Ingredient | Where | State |
|---|---|---|
| Transport: HTTPS relay + SMTP, `send()`, `email_configured()` | `mailer.py` | done — **untouched by this plan** |
| 21 message composers, each returning `(subject, body, html)` | `mailer.py` | done — reused verbatim for previews (§7) |
| Outbox file record of every attempt | `mailer.py` `_record()` → `outbox.log` | done — but ephemeral on the Space (see D6) |
| **`_notify_account(conn, account_id, subject, body, html=)`** | `app.py:2013` | done — the funnel for staff-account sends (6 call sites) |
| **`_notify_email(email, subject, body, html=)`** | `app.py:2025` | done — the funnel for known-address sends (2 call sites) |
| **`_mail_after_response(email, subject, body, html=)`** → `BackgroundTask` | `app.py:2034` | done — the funnel for participant-facing sends (3 call sites), deferred so a slow relay never slows a page |
| 7 scheduled jobs, independently selectable, `--dry-run` aware | `send_reminders.py` (`_ALL_JOBS`:135, `run()`:378) | done — run daily from `app._scheduler_loop`:3971 |
| Settings store (`app_setting` k/v) | `storage.py` `get_setting`:1126 / `set_setting`:1131 / `get_settings`:1139 | done — the mechanism this plan reuses |
| Console pattern: `_forbid` on **every** handler, GET reads settings, POST writes + `_audit` + redirect `?msg=` | `/admin/rules` (`app.py:3824+`) | done — **copy this one** (see D8) |
| Richer console: status card + settings + log table + a "test" action | `/admin/ai` (`app.py:3687-3800`, `admin_ai.html`) | done — closest shape to this module |
| DB-backed log table + index + retention purge | `ai_interaction` (`storage.py:862-894`), `retention.purge_stale_ai_log`:130 | done — the precedent for the send log (Phase 6) |
| Capability gate | `auth.ROLE_CAPS["admin"]` holds `manage_users` | done — reuse it, no new role |
| Nav registration | `NAV_GROUPS` "Administrator" group (`app.py:603-651`) | done — add one entry |

### 1a. The complete send map (this is the whole surface)

Every send in the app, and how it is reached:

| # | Feature | Composer | Reached via | Site |
|---|---|---|---|---|
| 1 | Event created | `event_created_message` | `_notify_email` | `app.py:5491` |
| 2 | New event under your section | `event_section_notify_message` | `_notify_account` | `app.py:5498` |
| 3 | Registration confirmed | `registration_confirmed_message` | `_mail_after_response` | `app.py:7525` |
| 4 | Certificate ready | `certificate_ready_message` | `_mail_after_response` | `app.py:7118` |
| 5 | Raffle winner | `raffle_winner_message` | `_mail_after_response` | `app.py:8186` |
| 6 | Wellness approval needed | `wellness_pending_message` | `_notify_account` | `app.py:13708` |
| 7 | Wellness decision result | `wellness_decided_message` | `_notify_account` | `app.py:13757` |
| 8 | Work arrangement approval needed | `awa_pending_message` | `_notify_account` | `app.py:14292`, `14352` |
| 9 | Work arrangement decision result | `awa_decided_message` | `_notify_account` | `app.py:14424` |
| 10 | Filing reopened | `work_arrangement_reopened_message` | **direct `mailer.send`** | `app.py:14501` |
| 11 | Spot Feedback update | `feedback_update_message` | `_notify_email` | `app.py:2875` |
| J1 | Day-before event reminder | `event_reminder_message` | job `events` | `send_reminders.py:94,111,125` |
| J2 | Wellness decide-link expiry | `wellness_pending_reminder_message` | job `wellness_expiry` | `:165` |
| J3 | Pending approvals digest | `approvals_digest_message` | job `digest` | `:367` |
| J4 | CSM results → resource person | `csm_rp_results_message` | job `csm_rp` | `:214` |
| J5 | CSM results → activity | `csm_activity_results_message` | job `csm_activity` | `:241,258` |
| J6 | Wellness filing nudge | `wellness_file_reminder_message` | job `wellness_file` | `:290` |
| J7 | Work arrangement filing nudge | `work_arrangement_file_reminder_message` | job `awa_file` | `:316` |
| A1 | Account invite | `invite_message` | direct `mailer.send` | `app.py:2313` |
| A2 | Password reset (self-service) | `reset_message` | direct `mailer.send` | `app.py:2366` |
| A3 | Password reset (admin-sent) | `reset_message` | direct `mailer.send` | `app.py:2486` |
| A4 | Registration link re-send | `recovery_message` | direct `mailer.send` | `app.py:8748` |

**The shape this reveals:** the app does *not* have 20 scattered send sites
to guard. It has **three funnels plus one stray** (#10), and the four
remaining direct `mailer.send` calls are exactly the account/recovery mail
that must never be disableable. That makes the sweep small and the rule
memorable (D2).

## 2. Design decisions

**D1 — one key per send, and every key belongs to exactly one world.**
A key is either **transactional** (fires from a user action, 11 of them) or
**scheduled** (one of the 7 jobs, 1:1 with `_ALL_JOBS`). No key spans both.
This keeps the scheduled gate a trivial dict lookup and avoids the trap of
one switch silently killing both a notice and its follow-up nag — e.g.
wellness approval notices (#6) and the decide-link expiry reminder (J2) are
*separate* keys, because an admin may well want the first without the
second. 18 keys total, each `email_feature.<key>` in `app_setting`,
**default `"1"` (on)** — so shipping Phases 1–3 changes no behavior at all
until an admin flips something.

**D2 — gate the funnels, not the call sites; state the invariant.**
`_notify_account` / `_notify_email` / `_mail_after_response` each take a new
`feature` argument and check it themselves. Only #10 needs moving: route it
through `_notify_email` too. The result is an invariant worth writing into
`app.py` as a comment above the three helpers:

> Every gateable email goes through one of these three helpers. A direct
> `mailer.send()` in `app.py` means account/recovery mail, which is never
> admin-disableable (§D3).

Four gated funnels instead of eleven guarded call sites means a future
feature cannot forget the gate by accident — it gets one for free by using
the helper everything else uses.

**D3 — account-recovery mail is never disableable.**
A1–A4 stay always-on. Turning off invites or password resets would lock an
admin out of fixing exactly that, and #A4 is the participant's only way back
into a lost registration. The console **lists them anyway**, greyed, labeled
"always on — account access", with preview available: an admin who cannot
find the invite toggle should learn *why* from the page, not wonder whether
it is a bug.

**D4 — the toggle and the transport are independent gates.**
`mailer.email_configured()` (is there a transport?) and the feature flag (is
this wanted?) are different questions; both must pass. The console shows
transport state as a read-only banner (which transport is live, or a
"no transport configured" warning), mirroring `/admin/ai`'s connection card.
A feature toggled on with no transport still doesn't send — and the banner
is what explains that, instead of an admin toggling switches at a dead relay.

**D5 — the reader lives in `storage.py`; the catalog lives in `mailer.py`.**
`storage.py` owns `app_setting` and every other settings reader, so
`email_feature_enabled(conn, key)` belongs there. `mailer.py` deliberately
has **no DB dependency** (it is imported standalone by `tests/test_mailer.py`
and holds only transport + composers) and this plan keeps it that way — it
gains the `FEATURES` catalog and the preview samples, neither of which
touches a database. Adding an email later is then one file's worth of edits:
composer + catalog entry + sample, all in `mailer.py`.

**D6 — the send log is a DB table, not a parse of `outbox.log`.**
The tempting cheap version — parse `outbox.log`'s `===== ts [note] =====`
records — is wrong here: that file sits next to the app
(`mailer.py:44`), and on the Hugging Face Space only the DB is persisted to
the bucket. The Space restarts often (`mailer.py` says so in its own
docstring), so the log an admin opens after a restart would be empty, and an
empty log reads as "nothing was sent" rather than "the file went away". A
small `email_log` table follows the `ai_interaction` precedent exactly
(`storage.py:862`), survives restarts with the rest of the data, and can be
filtered by feature. `outbox.log` stays as it is — belt and braces, and it
still catches sends that happen before the DB is reachable.
Recipient addresses are personal data, so the table is retention-capped
(90 days) through `retention.py`, next to `purge_stale_ai_log`.

**D7 — every phase ships on its own, and every phase bumps the version.**
`.github/workflows/deploy-hf.yml` deploys **on every push to `main`** and
runs with `CSS_DEPLOY_STRICT_VERSION=1`, which **hard-aborts the deploy if
`APP_VERSION` wasn't bumped**. So a phase-PR that forgets `version.py` does
not merge quietly — it breaks the deploy. Every phase below therefore
includes: `APP_VERSION` + 0.01, a new `version.py` `CHANGELOG[0]` entry in
layman terms with a spelled-out date, and a developer-facing `CHANGELOG.md`
entry. There is **no test CI** on this repo (the only workflow is the
deploy), so `bash run_tests.sh` green **locally** is the gate — a red suite
reaches production if nobody runs it.

**D8 — copy `/admin/rules`' gating, not `/admin/sharing`'s.**
`/admin/sharing` (`app.py:2614`, `2628`) omits the per-handler
`_forbid(request, "manage_users")` and leans on its nav entry's `cap` alone.
`/admin/rules` does it properly, on every handler, with a comment saying why
("defensively"). Every route in this module — GET, POST, preview, test —
starts with `if (r := _forbid(request, "manage_users")): return r`. The
preview route especially: it renders real message shells and must not be
open to a viewer.

**D9 — preview and test-send, not a template editor.**
Composing new templates from the UI would need a template language, an
escaping story and i18n — out of scope (§9). What IS in scope: render each
composer's real HTML with representative sample data (reusing the actual
`mailer.*_message()` functions, so a preview can never drift from what
sends), and a "send this one to me" button per feature, mirroring
`/admin/ai`'s Test-connection action (`app.py:3766-3799`). That is what lets
a non-technical admin check a message *before* turning it on.

**D10 — admin console strings are plain English.**
`admin_ai.html`, `admin_rules.html` and `admin_sharing.html` contain **zero**
`i18n` calls — the translated surface is the respondent-facing side, not the
admin back office. No i18n pass is needed for this module; don't add one.

## 3. The 18 keys

All are `email_feature.<key>` in `app_setting`, `"1"`/`"0"`, default `"1"`.

**Transactional** (gated in the three helpers):

| key | Label | Site |
|---|---|---|
| `event_created` | Event created | #1 |
| `event_section_notify` | New event under your section | #2 |
| `registration_confirmed` | Registration confirmed | #3 |
| `certificate_ready` | Certificate ready | #4 |
| `raffle_winner` | Raffle winner | #5 |
| `wellness_approval` | Wellness approval needed | #6 |
| `wellness_decided` | Wellness decision result | #7 |
| `awa_approval` | Work arrangement approval needed | #8 (both sites) |
| `awa_decided` | Work arrangement decision result | #9 |
| `awa_reopened` | Filing reopened | #10 |
| `feedback_update` | Spot Feedback update | #11 |

**Scheduled** (1:1 with `send_reminders._ALL_JOBS`, gated in `run()`):

| key | Label | Job |
|---|---|---|
| `job_events` | Day-before activity reminder | `events` |
| `job_wellness_expiry` | Wellness decide-link expiry reminder | `wellness_expiry` |
| `job_digest` | Weekly pending-approvals digest | `digest` |
| `job_csm_rp` | CSM results to the resource person | `csm_rp` |
| `job_csm_activity` | CSM results to the activity's organizer | `csm_activity` |
| `job_wellness_file` | Wellness filing nudge | `wellness_file` |
| `job_awa_file` | Work arrangement filing nudge | `awa_file` |

**Always on** (no key; listed in the console, previewable, not toggleable):
`invite`, `reset`, `recovery` (A1–A4).

## 4. Phase 1 — settings + gate function

*No behavior change. Nothing calls the gate yet.*

**`storage.py`** (beside `get_setting`, ~line 1126):

```python
def email_feature_enabled(conn, key):
    """True unless an admin has turned this email feature off. Unknown keys
    read as ON: a typo must never silently swallow a real send."""
    return get_setting(conn, f"email_feature.{key}", "1") != "0"


def set_email_feature(conn, key, on):
    set_setting(conn, f"email_feature.{key}", "1" if on else "0")
```

**`mailer.py`** (catalog only — no DB import, per D5):

```python
# key -> (label, hint, group)  group: "transactional" | "scheduled"
FEATURES = {
    "event_created": ("Event created",
                      "The organizer gets a confirmation with the monitor link.",
                      "transactional"),
    ...  # all 18 from §3
}

# Always-on account mail: shown in the console, never disableable (see the
# admin email plan, D3). key -> (label, why)
ALWAYS_ON = {
    "invite": ("Account invite", "A new account cannot be set up without it."),
    "reset": ("Password reset", "Disabling it would lock people out for good."),
    "recovery": ("Registration link re-send",
                 "A participant's only way back into a lost registration."),
}
```

**Tests** — new `tests/test_email_admin.py`: a feature with no row reads
enabled; `set_email_feature(False)` then `email_feature_enabled` is False;
round-trip back to True; an unknown key reads enabled; every `FEATURES` key
is unique and every `group` is one of the two valid values.

**Also:** `APP_VERSION` → 2.87, `version.py` CHANGELOG entry, `CHANGELOG.md`
entry. **Done when:** `bash run_tests.sh` green.

## 5. Phase 2 — wire the gate into the three funnels

**`app.py`, the three helpers** gain a `feature` argument and check it. Note
the ordering rule for `_mail_after_response`: **check at call time, not
inside the background task** — the task runs after the request handler's
`finally: conn.close()`, so a check deferred into the task would touch a
closed connection.

```python
def _notify_account(conn, account_id, subject, body, html=None, feature=None):
    try:
        if feature and not st.email_feature_enabled(conn, feature):
            return
        ...

def _notify_email(conn, email, subject, body, html=None, feature=None):   # conn is new
    ...

def _mail_after_response(conn, email, subject, body, html=None, feature=None):
    """Returns None when the feature is off — callers already initialize their
    `*_mail` variable to None and assign it to `resp.background`, which
    accepts None."""
    if feature and not st.email_feature_enabled(conn, feature):
        return None
    return BackgroundTask(mailer.send, email, subject, body, html=html)
```

**Call sites** (11): pass `feature="<key>"` at each site in §1a rows #1–#11.
`_notify_email`'s two existing callers (`:2875`, `:5491`) and
`_mail_after_response`'s three (`:7118`, `:7525`, `:8186`) also gain `conn`
as their first argument — `conn` is open and in scope at all five.

**Row #10** (`app.py:14501`) moves off its direct `mailer.send` onto
`_notify_email(conn, staffer["username"], subj, body, html=html,
feature="awa_reopened")`, completing the invariant in D2. Add that invariant
as a comment above the helper trio.

**Tests** — extend `tests/test_notifications.py` (its `notif_org` fixture and
its `monkeypatch.setattr(mailer, "email_configured", lambda: True)` pattern
already do the setup): for at least #6 wellness approval, #3 registration
confirmed (a `_mail_after_response` path — assert the returned background
task is None) and #11 feedback update, assert a send happens with the
feature on and no send happens with it off. Assert the four always-on sends
are unaffected by any flag.

**Also:** version 2.88 + both changelogs. **Done when:** `run_tests.sh`
green, and the existing notification tests still pass untouched (they should
— defaults are on).

## 6. Phase 3 — gate the seven scheduled jobs

**`send_reminders.py`**: one map beside `_ALL_JOBS`, and a filter in `run()`.

```python
# job name -> the admin toggle that can switch it off (see /admin/email)
JOB_FEATURE = {
    "events": "job_events",
    "wellness_expiry": "job_wellness_expiry",
    "digest": "job_digest",
    "csm_rp": "job_csm_rp",
    "csm_activity": "job_csm_activity",
    "wellness_file": "job_wellness_file",
    "awa_file": "job_awa_file",
}
```

In `run()`, after `jobs` is resolved and the connection is open, drop the
disabled ones. **The rule: CLI flags choose which jobs to consider; the admin
toggle can only subtract.** A job switched off reports nothing rather than
`0`, so the report distinguishes "ran, sent none" from "didn't run":

```python
jobs = set(jobs) if jobs else set(_ALL_JOBS)
disabled = {j for j in jobs if not st.email_feature_enabled(conn, JOB_FEATURE[j])}
jobs -= disabled
if dry_run:
    for j in sorted(disabled):
        print(f"{j}: skipped (turned off in /admin/email)")
```

`app._scheduler_loop`:3995 needs **no change** — it calls `send_reminders.run(DB)`
with no job list, which now means "every job the admin still wants".

**Tests** — extend `tests/test_send_reminders.py`: with `job_digest` off,
`run(jobs={"digest"})` returns no `digest` key and sends nothing; with it on,
the existing behavior is unchanged; a disabled job is named in `--dry-run`
output.

**Also:** version 2.89 + both changelogs. **Done when:** `run_tests.sh` green.

*At the end of Phase 3 every email in the app is controllable — but only by
editing `app_setting` directly. Phases 4–6 are the human interface.*

## 7. Phase 4 — the console

**`app.py`**, modeled on `/admin/rules` (gating) and `/admin/ai` (layout):

| Route | Method | What |
|---|---|---|
| `/admin/email` | GET | transport banner (`mailer.email_configured()` + which transport is live), then three groups of rows — Transactional, Scheduled, Always-on — each with its label, hint and current state |
| `/admin/email/toggle` | POST | `key` + `on`; rejects a key not in `mailer.FEATURES` (never let a POST write an arbitrary `app_setting`); `st.set_email_feature`; `_audit(request, conn, "email_feature_toggle", target_type="setting", summary=f"{label} email turned {'ON' if on else 'OFF'}")`; redirect `?msg=Saved.` |

Read all 18 states in **one** query with `st.get_settings(conn, keys)`
(`storage.py:1139`), not 18 round trips.

**`templates/admin_email.html`** — extends `dash_layout.html`, imports
`page_header` from `_components.html`, inline `<style>` in `{% block head %}`,
and reuses `admin_sharing.html`'s existing idiom verbatim: `.acard` sections,
the `.state.on` / `.state.off` pills, `.flash.ok`, and the theme variables
(`--surface`, `--line`, `--soft`, `--green-bg`, `--amber-bg`). One small form
per row posting to `/admin/email/toggle` keeps it dependency-free and works
without JavaScript, like every other console here. Always-on rows render as a
disabled control plus the "why" string from `ALWAYS_ON`.

**Nav** — one entry in the `Administrator` group (`app.py:603-651`), beside
`sharing`:

```python
{"key": "email", "url": "/admin/email", "label": "Email",
 "hint": "Turn email notifications on or off",
 "kw": "email mail notifications toggle switch off preview test outbox "
       "reminders digest csm wellness awa feedback invite reset",
 "cap": "manage_users"},
```

**Tests** — RBAC comes almost free: add
`("/admin/email", "get", "manage_users")` and
`("/admin/email/toggle", "post", "manage_users")` to the `GATED` table in
`tests/test_auth_rbac.py:14`, which is already parametrized across all four
roles and asserts a 403 for the denied ones. Then in
`tests/test_email_admin.py`: an admin sees all 18 rows; a POST flips the
setting and writes an audit row; a POST with an unknown key changes nothing.

**Also:** version 2.90 + both changelogs.

## 8. Phase 5 — preview and test-send

**`mailer.py`** — one sample per key, beside the composer it previews:

```python
_SAMPLE_LINK = "https://example.invalid/sample"

def preview(key):
    """(subject, html) for `key`, built by calling the REAL composer with
    sample data — a preview can never drift from what actually sends."""
```

e.g. `"wellness_approval": lambda: wellness_pending_message("Jane Dela Cruz",
"Juan Santos", "2026-10-02", "10:00 AM", 2, _SAMPLE_LINK, approve_link=...,
deny_link=...)`. Cover all 18 keys plus the 3 always-on ones.

**`app.py`**:

| Route | Method | What |
|---|---|---|
| `/admin/email/preview/{key}` | GET | `_forbid` first (D8); unknown key → 404; returns the composed HTML for display in an `<iframe srcdoc>` on the console. Add it to the `GATED` table too |
| `/admin/email/test` | POST | composes the sample and sends it to the **requesting admin's own** `username` — never an address from the form, so this can't be turned into a relay; `?msg=`/`?err=` per `/admin/ai`'s test action; when `email_configured()` is False, says so instead of pretending |

**Tests** — every key in `FEATURES` and `ALWAYS_ON` has a working sample
(loop over them, assert `preview(key)` returns a non-empty subject and HTML
containing the sample link). This one test is what stops a future composer
from being added to the catalog without a preview. Plus: preview 404s on an
unknown key, and `_forbid`s a viewer.

**Also:** version 2.91 + both changelogs.

## 9. Phase 6 — the send log

**`storage.py`** — following `ai_interaction` (`:862-894`):

```sql
CREATE TABLE IF NOT EXISTS email_log (
  id INTEGER PRIMARY KEY, created_at TEXT, feature TEXT,
  recipient TEXT, subject TEXT, status TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS email_log_created_idx ON email_log(created_at);
```

`status` is `sent` / `failed` / `not_configured` / `skipped_off`. Helpers:
`log_email_send(conn, feature, recipient, subject, result)` and
`recent_email_sends(conn, limit=50)`.

**Write sites** — the three helpers from Phase 2 (one line each, where the
result is already in hand), the four always-on sends, and a small local
`_send(conn, feature, to, subj, body, html)` wrapper in `send_reminders.py`
replacing its nine bare `mailer.send` calls.

**`retention.py`** — `purge_stale_email_log(db_path, days=90, dry_run=False)`
beside `purge_stale_ai_log`:130, wired in the same way. Recipient addresses
are personal data; 90 days is enough to debug a delivery complaint and no
longer.

**`/admin/email`** — render the newest 50 at the bottom of the console, with
the status shown the way `/ops` shows health states (a colored dot, not just
a word).

**Tests** — a send writes a row with the right feature and status; a
disabled feature writes `skipped_off`; `purge_stale_email_log` removes rows
past the cutoff and keeps the rest.

**Also:** version 2.92 + both changelogs, and a `docs/QA_PLAYBOOK.md` pass:
turn a feature off → trigger it → confirm no mail, an `email_log` row of
`skipped_off`, and the feature back on afterwards.

## 10. Risks and the answers to them

| Risk | Answer |
|---|---|
| A toggle silently stops mail people depend on, and nobody notices | Every toggle is audited (`_audit`), the console shows state at a glance, and Phase 6's log distinguishes `skipped_off` from `failed` — "why didn't I get it?" has an answer on one screen |
| An admin turns off something load-bearing | Account/recovery mail cannot be turned off at all (D3). Everything else is genuinely optional by design |
| A future email forgets its gate | It gets one free by using the funnels (D2); the invariant is a comment above them, and Phase 5's catalog test fails a key added without a sample |
| `_mail_after_response`'s deferred send touches a closed connection | Gate at call time, not in the task (Phase 2) — called out explicitly because it is the one non-obvious edit in the sweep |
| A phase merges without a version bump | The deploy hard-aborts (D7) — loud, not silent. Every phase lists its bump |
| Preview/test becomes an open relay or a leak | Test-send only ever goes to the signed-in admin's own address; every route `_forbid`s on `manage_users` (D8) |

## 11. Out of scope (explicitly)

* **No per-user preferences** — this is an *admin* control, not an end-user
  opt-out. A "let staff mute their own reminders" feature is a different
  design (it needs a per-account table and an unsubscribe token) and should
  not be smuggled in here.
* **No template/wording editor** — subject and body changes stay code
  changes in `mailer.py`'s composers.
* **No new transports** — relay and SMTP as configured today.
* **No retry queue** — a failed send stays failed; Phase 5's test-send is
  the manual retry, and Phase 6's log is the record. Automatic retry needs a
  queue and a scheduler slot, and would want its own plan.
* **No changes to the composers themselves** — every message keeps its
  current wording, so nothing in this plan alters what a recipient reads.
