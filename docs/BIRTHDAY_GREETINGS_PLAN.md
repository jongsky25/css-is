# Birthday greetings — implementation plan

**Status:** planned, not started. Build follows this plan phase by phase.
**Owner:** avincentpatrick
**Why:** Office Connect already *knows* birthdays (month and day, with consent) and already tells
teammates and coordinators about them. The one person it says nothing warm to is the celebrant.
This plan adds a heartfelt greeting for them: an **email** on the day, and a **greeting in the app**
that survives the person not signing in on the day, by covering their **birth week**.

**Non-goals:** new birthday capture or sharing rules (done, v5.1–5.3); anything that reveals a
birthday to someone who was not already allowed to see it; showing or computing age.

**Build discipline:** same as the other plans. One phase = one PR = one `APP_VERSION` bump = one
layman `CHANGELOG` entry, `bash run_tests.sh` green first. Merging to `main` deploys to the live
Space, so each phase must be safe to ship alone.

---

## 1. What exists today (verified; leverage, don't rebuild)

| Ingredient | Where | State |
|---|---|---|
| Birthday on the account: `birthday_month/day/share/consent_at/consent_notice` | `admin_user`, `storage.get_birthday` / `set_birthday` | done. Month and day only, never a year |
| Pure date rules: `occurrence()` (Feb 29 → Feb 28), `is_today()`, `first_name()` (nickname first) | `birthdays.py` | done. Reuse; add `birth_week()` here |
| "Happy birthday, <name>! 🎉" heading, **today only** | `office_connect.html:280`, `is_birthday` at `app.py:4962` | done but **one day, text only**: miss the day and it is gone |
| Daily job runner, per-job admin toggle, `--dry-run`, `email_log` | `send_reminders.run()`, `JOB_FEATURE`, `mailer.FEATURES` | done. The two coordinator jobs are the template |
| Idempotence + catch-up if the Space was asleep | `_already_sent(conn, feature, to, subject)` and the "through the 7th" rule in `send_birthday_month` | done. Same pattern |
| Branded HTML email shell | `mailer._email_html(...)`, composers return `(subject, body, html)` | done |
| Admin email console that lists, previews and toggles every feature | `/admin/email`, `mailer.FEATURES`, `PREVIEWS` (`mailer.py:~1385`) | done. A new job appears there by adding two dict entries |
| Nav bell | `office_calendar.birthday_bell_row` | done (for teammates; the celebrant is deliberately excluded) |
| Companion avatar with moods | `_avatars.html`, `profile.avatar_mood` | done. Can wear a party hat |
| Daily scheduler | `app._scheduler_loop` → `send_reminders.run` once per local day | done |

## 2. Design decisions

**D1 — Greeting the person is covered by the consent they already gave.** The notice they saw says
"We use it to greet you and remind your teammates." So the greeting works for *every* birthday on
file, including `share = none` (they chose not to tell teammates, not to be greeted). It tells
nobody else, so it needs no new sharing scope.

**D2 — …but admin-entered birthdays and personal preference still get a way out.** Add one opt-out,
`admin_user.bday_greet` (NULL = on, 0 = off), a checkbox on `/me` next to the existing
"teammates' birthdays" one. The admin-entered notice already says the person may change or remove
it. A person who turns greetings off gets neither the email nor the in-app card.

**D3 — "Birth week" = the Monday–Sunday week that contains the birthday, plus a short grace.**
Defined once in `birthdays.birth_week(month, day, today)` and used by both email and app, so they
can never disagree:

| When | Wording | Why |
|---|---|---|
| Birthday itself | "Happy birthday, Mae!" | the main event |
| Earlier in the same week, birthday on a weekend | "Your birthday is this Saturday 🎂" | the existing Friday "this weekend" convention; warm, not a belated apology |
| 1–6 days after | "Belated happy birthday, Mae!" | they missed the day |
| Otherwise | normal "Hi, Mae 👋" | |

Recommendation: window is **birthday day through 6 days after**, plus the weekend-lead-in above.
Simple to explain ("we'll keep it up for a week") and stops before it feels stale. Needs your call;
see §6.

**D4 — Email goes out on the day itself, even on a weekend or holiday.** The scheduler already runs
daily, and a card that arrives on the real day feels right. If the Space was asleep and missed it,
a **catch-up** sends it through day +3 with "belated" wording. After that nothing is sent (an
email a week late feels like a system notice, not a greeting). One email per person per year,
enforced by `_already_sent` on a subject that includes the year.

**D5 — The greeting must not feel like a mail merge.** A pool of 12 to 15 short heartfelt
messages, picked deterministically by `hash(user_id, year)` so a person gets a different one each
year but a retry never sends a second variant. All are warm, work-appropriate, and **never mention
age**. Each uses the nickname (`birthdays.first_name`), a line of gratitude for the person's work,
and a sign-off from the office ("From all of us at BLHSD"). Draft messages go to you for approval
before Phase 1 ships (§5).

**D6 — In-app: one celebratory moment, then quiet.** First visit in the window shows a full
card (confetti, the companion in a party hat, the message). The visit is recorded in
`admin_user.bday_greeted_year`; after that the page shows only the slim "Happy birthday" heading,
so a daily user is not shown confetti five times. A × dismisses it for the window. All motion
respects `prefers-reduced-motion`.

**D7 — Nothing about it leaks.** The celebrant is still never in their own bell or coordinator
lists. The audit log records "birthday greeting sent", never the date. Subject lines carry no date
or age. The email goes only to the account's own address.

**D8 — Sign-in is the trigger, not a separate login hook.** The greeting is computed at render time
from today's date and the person's birthday, the same way `is_birthday` already is. No login-event
plumbing, nothing that can get stuck. The *only* state stored is `bday_greeted_year`.

## 3. Phases

### Phase 1 — the email (smallest useful slice)
- `birthdays.birth_week()` and `greeting_phase()` returning `today | lead_in | belated | none`;
  tested exhaustively like the rest of `birthdays.py` (Feb 29, New Year boundary, weekends).
- `mailer.birthday_greeting_message(name, phase, variant)` → `(subject, body, html)`, plain text
  alongside the HTML. A `_GREETINGS` pool, `variant` chosen by `hash(user_id, year) % len`.
- `send_reminders.send_birthday_greetings(conn, base, dry_run)`: active accounts with a birthday on
  file, `bday_greet` on, address deliverable, in phase `today` (or `belated` for the catch-up days);
  skipped if `_already_sent`. Register `birthday_greeting` in `_ALL_JOBS`, `JOB_FEATURE` and
  `run()`, plus `mailer.FEATURES` and `PREVIEWS` so it shows in `/admin/email` with a preview and
  an off switch.
- Migration: guarded `ALTER TABLE` for `bday_greet`.
- Tests: right person, right day, once per year, catch-up window, opt-out, inactive/archived
  skipped, no age/date in text, dry-run sends nothing, admin toggle off sends nothing.

### Phase 2 — the greeting when they sign in
- `_birthday_greeting(profile, today)` helper next to `is_birthday`; replaces the boolean with
  `{phase, message, first_visit}`.
- `office_connect.html`: celebration card on first visit, slim heading after, "belated" and
  "this Saturday" wording per D3. Companion wears the party hat (new avatar `mood="party"`).
- Mark `bday_greeted_year` when the card is first rendered; × dismiss route (`POST
  /me/birthday-greeting/dismiss`).
- Same slim greeting on the `/css` chooser and Wellness hub header so it follows them wherever
  they land.
- Tests: card shows in window, first visit only, belated/lead-in wording, hidden when opted out,
  reduced-motion CSS present, no greeting for people without a birthday.

### Phase 3 — polish and control
- `/me`: "Send me a birthday greeting" checkbox (D2).
- `/admin/email`: editable sign-off line and an on/off for the in-app card (settings
  `birthday.signoff`, `birthday.card_on`), following the `/admin/rules` pattern.
- Admin preview that renders all pool messages so nothing unreviewed goes out.
- Update `HELP`/`tours.py` text and `CHANGELOG`.

### Phase 4 — optional, only if you want it
- **Wishes from teammates:** people inside the celebrant's sharing scope can leave a short wish on
  a "card"; the celebrant reads them on the day. Needs moderation and a length cap, and it is the
  one idea here that creates user-written content about a person, so it is deliberately last and
  separate. Everything above works without it.
- A one-line note to the celebrant's section chief is *not* proposed: coordinators already cover it.

## 4. Edge cases to pin in tests
- **Feb 29** birthdays greet on Feb 28 in non-leap years (reuse `occurrence`).
- **New Year boundary:** a Dec 30 birthday greeted on Jan 2.
- **Weekend / holiday birthday:** email on the real day; in-app lead-in the Friday before.
- **Space asleep on the day:** catch-up sends once, with belated wording, never twice.
- **Birthday added or changed today:** an entry made *after* that morning's run is greeted by the
  in-app card but not retroactively emailed; avoids a surprise email the minute someone saves it.
- **Changed to a different date after being greeted:** `_already_sent` is keyed on year, so a
  re-save cannot trigger a second email in the same year.
- **Resigned, archived, deactivated, or no email on file:** nothing sent, no error.
- **Shared mailbox / email relay not configured:** logged as `not_configured` like every other job.
- **Timezone:** `tzutil.today_local()` everywhere, never `date.today()`.

## 5. Needs your input before Phase 1 ships
1. The greeting wording. I will draft the pool of 12 to 15 messages in English (a Filipino/Tagalog
   variant is possible via `i18n.py` if wanted) for you to edit or approve.
2. Who the email appears to come from and the sign-off ("From all of us at BLHSD" vs. the
   Director's name).

## 6. Decisions for you
| # | Question | My recommendation |
|---|---|---|
| 1 | Length of "birth week" | The day through 6 days after, plus a weekend lead-in |
| 2 | Greet people who chose "Don't share"? | Yes (D1), with a personal opt-out |
| 3 | Greet admin-entered birthdays? | Yes, with the opt-out; the person can also remove the date |
| 4 | Email catch-up if missed | Through day +3, then stop |
| 5 | Teammate wishes (Phase 4) | Not now; revisit after the first month of use |

## 7. Risks
- **A wrong or sensitive greeting is worse than none.** Mitigations: preview in `/admin/email`,
  global off switch, per-person opt-out, `--dry-run` first, no age.
- **Duplicate sends** if the scheduler double-fires: covered by `_already_sent` plus the daily
  claim in `_reminders_due`.
- **Email volume** is at most the number of birthdays that day; negligible for the relay.
- **Confetti on a tired Monday:** one celebratory moment, then quiet (D6); fully reduced-motion safe.
