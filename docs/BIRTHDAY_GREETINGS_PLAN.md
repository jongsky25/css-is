# Birthday greetings — implementation plan

**Status:** plan approved by the owner (decisions in §6). Build follows this plan phase by phase.
**Owner:** avincentpatrick
**Why:** Office Connect already *knows* birthdays (month and day, with consent) and already tells
teammates and coordinators about them. The one person it says nothing warm to is the celebrant.
This plan adds a heartfelt greeting for them: an **email** from BLHSD, a **greeting in the app**
that covers the **week leading up to the birthday** (they may not sign in on the day itself), and
**birthday cards** teammates can send.

**Non-goals:** new birthday capture or sharing rules (done, v5.1–5.3); anything that reveals a
birthday to someone who was not already allowed to see it; showing or computing age.

**Build discipline:** same as the other plans. One phase = one PR = one `APP_VERSION` bump = one
layman `CHANGELOG` entry, `bash run_tests.sh` green first. Merging to `main` deploys to the live
Space, so each phase must be safe to ship alone and is opened as a draft for the owner to merge.

---

## 1. What exists today (verified; leverage, don't rebuild)

| Ingredient | Where | State |
|---|---|---|
| Birthday on the account: `birthday_month/day/share/consent_at/consent_notice` | `admin_user`, `storage.get_birthday` / `set_birthday` | done. Month and day only, never a year |
| Pure date rules: `occurrence()` (Feb 29 → Feb 28), `is_today()`, `shared_with()`, `first_name()` (nickname first) | `birthdays.py` | done. Reuse; add the greeting-window rules here |
| "Happy birthday, <name>! 🎉" heading, **today only** | `office_connect.html:280`, `is_birthday` at `app.py:4962` | done but **one day, text only** |
| Daily job runner, per-job admin toggle, `--dry-run`, `email_log` | `send_reminders.run()`, `JOB_FEATURE`, `mailer.FEATURES` | done. The two coordinator jobs are the template |
| Idempotence via the email log | `_already_sent(conn, feature, to, subject)` | done. Same pattern |
| Branded HTML email shell | `mailer._email_html(...)`; composers return `(subject, body, html)` | done |
| Admin email console that lists, previews and toggles every feature | `/admin/email`, `mailer.FEATURES`, `PREVIEWS` | done. A new job appears by adding dict entries |
| Nav bell with "🎂 Today: …" for teammates | `office_calendar.birthday_bell_row` | done. The celebrant is deliberately excluded from it |
| Working-day helpers | `office_calendar.first_working_day`, `storage.holidays_between` | done. Reuse for weekend birthdays |
| Companion avatar with moods | `_avatars.html`, `profile.avatar_mood` | done. Can celebrate too (a line under it) |

## 2. Design decisions

**D1 — The greeting is mandatory for everyone with a birthday on file; there is no opt-out.** It
tells nobody else, and the notice every person saw says "We use it to greet you and remind your
teammates", so it is covered by the consent already recorded. It applies to every sharing choice,
including "Don't share" (they chose not to tell teammates, not to skip being greeted). The only way
to stop it is the control that already exists: remove the birthday from the profile. The admin
on/off switch every email gets in `/admin/email` stays as an operations kill switch, not a
per-person choice.

**D2 — Bilingual, Tagalog and English together.** Every greeting carries both: a Tagalog line and
an English line in the same message. Subject: "Maligayang kaarawan, Mae! 🎂 Happy birthday!".
The pool holds 12 to 15 messages, picked deterministically by `hash(user_id, year)` so a person
gets a different one each year and a retry never sends a second variant. All are warm and
work-appropriate, use the nickname (`birthdays.first_name`), thank the person for their work, and
**never mention age**. The wording is drafted in code for the owner to read in the `/admin/email`
preview before it ships (the preview shows a sample; the full list is in the PR description).

**D3 — Sender is BLHSD.** Signed "Mula sa lahat ng nasa BLHSD / From all of us at BLHSD".
Sent through the existing mailer, so the From address is whatever the relay is configured with.

**D4 — Greetings come BEFORE the birthday, never after. No "belated".** The greeting window is the
**six days leading up to the birthday, plus the day itself** (seven days ending on the birthday).
Someone who signs in during that week is greeted even if they never sign in on the day. After the
day, the page goes back to normal.

| When | In-app wording |
|---|---|
| 1–6 days before | "Malapit na ang kaarawan mo, Mae! Your birthday is on Saturday 🎂" |
| The day | "Maligayang kaarawan, Mae! Happy birthday! 🎉" |
| After the day | normal "Hi, Mae 👋" |

**D5 — The email goes out on the birthday, or the last working day before it if the birthday falls
on a weekend or holiday** (so it is read on a working day, and still never late). One email per
person per year, enforced by `_already_sent` on a subject that includes the year. If the Space was
asleep and the run is missed, nothing is sent afterwards: a late greeting is worse than none.

**D6 — In-app: one celebratory moment, then quiet.** The first visit in the window shows a full
card (confetti, a line from the companion, the bilingual message). The visit is recorded in
`admin_user.bday_greeted`; after that only the slim greeting heading shows, so a daily user is
not shown confetti every day. × dismisses it. All motion respects `prefers-reduced-motion`.

**D7 — Nothing about it leaks.** The celebrant is still never in their own bell or coordinator
lists. The audit log records "birthday greeting sent", never the date. Subject lines carry no date
or age. The email goes only to the account's own address.

**D8 — Sign-in is the trigger, not a separate login hook.** The greeting is computed at render time
from today's date and the person's birthday, as `is_birthday` already is. The only state stored is
`bday_greeted`.

**D9 — Birthday cards from teammates.** People who are allowed to see a birthday (inside the
celebrant's sharing scope, via `birthdays.shared_with`) can send a card during the same window
(six days before through the day). A card is a chosen design plus a short bilingual-friendly
message, signed with the sender's name; one per sender per year. Cards are **held until the
birthday** and revealed to the celebrant that morning (a surprise), then stay viewable on their
profile for the year. A celebrant who chose "Don't share" receives no cards, because nobody else
is allowed to know their birthday. Details in Phase 3.

## 3. Phases

### Phase 1 — the email
- `birthdays.greeting_window()` / `greeting_phase()` (pure, tested like the rest of
  `birthdays.py`): `before | today | none`, given a month, day and today. `email_send_date()` gives
  the birthday or the working day before it.
- `mailer.birthday_greeting_message(name, variant)` → `(subject, body, html)`, plain text
  alongside the HTML, bilingual pool, BLHSD sign-off.
- `send_reminders.send_birthday_greetings(conn, base, dry_run)`: active accounts with a birthday on
  file and a deliverable address whose send date is today; skipped if `_already_sent`. Registered
  as the `birthday_greeting` job in `_ALL_JOBS`, `JOB_FEATURE`, `run()`, `mailer.FEATURES`,
  `PREVIEWS` (shows in `/admin/email` with a sample preview and an off switch).
- Tests: right person, right day, weekend and holiday roll back to the working day, once per year,
  no catch-up after the day, inactive/archived skipped, no age or date in the text, dry-run sends
  nothing, admin switch off sends nothing, Feb 29, New Year boundary.

### Phase 2 — the greeting when they sign in
- `_birthday_greeting(profile, today)` next to `is_birthday`, returning
  `{phase, message, first_visit}`. Replaces the boolean.
- `office_connect.html`: celebration card on first visit in the window, slim heading afterwards,
  per D4 wording. A line under the companion says it is celebrating too ("🎉 Pip is celebrating with you!"). A hat drawn over the artwork would not sit right on every species, and the name tag only shows on tap, so neither was used.
- `admin_user.bday_greeted` (guarded `ALTER TABLE`; `year*10 + 1` for the lead-in, `+ 2` for the
  day), set when the card first renders, so each phase shows one card. × hides the card in the
  browser; nothing is stored for it.
- Only the landing page `/` greets: it is the page everyone passes through after signing in.
- Tests: card shows in the window and not outside it, first visit only, "before" vs "today"
  wording, never "belated", no greeting without a birthday, reduced-motion CSS present.

### Phase 3 — birthday cards from teammates
- Table `birthday_card (id, to_user_id, from_user_id, year, design, message, created_at, hidden)`,
  unique on `(to_user_id, from_user_id, year)`.
- Eligibility, enforced server-side: sender is signed in, is not the celebrant, passes
  `birthdays.shared_with(celebrant, sender)`, and today is inside the celebrant's window.
- Sending: the nav bell's existing "🎂 Today: …" row is extended to the week ("🎂 Mae's birthday is
  Saturday — send a card"), linking to `/birthday/card/<user>`. A small form: pick one of ~6
  designs, write up to 280 characters (starter lines in Tagalog and English to tap), preview, send.
- Revealing: held until the birthday morning. On the day the celebrant sees "May N card(s) para sa
  iyo / N cards for you" in the greeting card and at `/me/cards`; the Phase 1 email is not changed.
- Safety: message length cap, plain text only (HTML-escaped on output), rate limit with the
  existing `ratelimit.py`, an admin can hide a card (`hidden`) from the Users page, audit entry
  records "card sent" with no message content.
- Tests: eligibility matrix (own scope, other section, "none", self, outside window), one per
  sender per year, held until the day, escaping, rate limit, hidden cards not shown, "none" gets
  none.

## 4. Edge cases to pin in tests
- **Feb 29** birthdays are treated as Feb 28 in non-leap years (reuse `occurrence`).
- **New Year boundary:** a Jan 2 birthday has a window that starts in the previous December.
- **Weekend / holiday birthday:** email on the last working day before; in-app card all week.
- **Space asleep on the send day:** nothing is sent afterwards (D5). Documented, not silently lost.
- **Birthday added or changed today:** no retroactive email the minute someone saves it; the in-app
  card still appears.
- **Re-saving a changed date after being greeted:** `_already_sent` is keyed on year, so no second
  email the same year.
- **Resigned, archived, deactivated, or no email on file:** nothing sent, no error.
- **Email relay not configured:** logged as `not_configured` like every other job.
- **Timezone:** `tzutil.today_local()` everywhere, never `date.today()`.

## 5. Needs the owner's eyes before it ships
The greeting wording (Tagalog and English). The first draft ships in Phase 1 as a **draft PR** with
the wording listed in the PR description; nothing reaches staff until the owner merges.

## 6. Decisions (settled)
| # | Question | Decision |
|---|---|---|
| 1 | Language | Tagalog and English together, in every message |
| 2 | Sender / sign-off | BLHSD |
| 3 | Greeting window | Before the birthday and the day itself, never after |
| 4 | Opt-out | None. Mandatory for everyone with a birthday on file |
| 5 | Teammate cards | In scope, Phase 3, held until the day |

## 7. Risks
- **A wrong or sensitive greeting is worse than none.** Mitigations: preview in `/admin/email`,
  admin kill switch, `--dry-run` first, no age, nothing sent late.
- **Cards are user-written content about a person.** Mitigations: scope limited to people already
  allowed to see the birthday, length cap, escaping, rate limit, admin hide, nothing for "Don't share".
- **Duplicate sends** if the scheduler double-fires: covered by `_already_sent` plus the daily
  claim in `_reminders_due`.
- **Confetti on a tired Monday:** one celebratory moment, then quiet (D6); reduced-motion safe.
