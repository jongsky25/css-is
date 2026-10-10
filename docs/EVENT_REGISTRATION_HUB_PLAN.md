# Event page as a registration hub — implementation spec

**Status:** planned, not started.
**Owner:** avincentpatrick
**Why:** The public activity page (`/e/<token>`) asks people to "Sign in to give
your feedback". It is really a **registration**: the form creates an `attendee`
row. And the page is the participant's home for the whole activity: programme,
resources, feedback and certificate. People treat it as a one-off feedback login.
They don't register ahead of time, and they lose the page afterward.

This spec turns the page into a linktree-style **event hub**:

1. Signing in for the first time *is registering for the event*, and the page says so.
2. Right after registering, the participant gets a **personal link and QR** with
   a clear "save this, it's how you get updates" message.
3. The registered view is ordered like a hub: updates, then info, then
   feedback, then certificate. **Feedback stays hidden until the activity starts.**
4. Organizers can post a **pinned update**, such as a room change or a reminder,
   that registered participants see at the top of their page.

**Decisions taken (by the owner, 2026-10-10):**
- Feedback links are **hidden (locked) until the activity starts**. Server-side
  too, not just in the template.
- The personal link stays valid until **the activity's last day + 30 days**,
  replacing the flat 90-day token age for this link.
- The pinned update ships in **PR-1**, not later.

Ship in **two PRs**, in this order. Each PR runs `bash run_tests.sh` green before
it is pushed. Each PR bumps `APP_VERSION` and adds both changelog entries (see §0).

---

## 0. Facts about the codebase (read before coding)

| What | Where |
|---|---|
| Stack | FastAPI + Jinja2 (autoescape on) + raw `sqlite3`. No ORM. Forms are parsed by hand (`parse_qsl` / `_posted(request)`). |
| Public page template | `templates/link_tree.html`. Three branches: `{% if attendee %}` (registered view, lines ~49-145), `{% elif confirm %}` ("Is this you?", ~147-169), and `{% else %}` (the registration form, ~171-302). |
| Page context builder | `_event_view` (app.py:~8332). **Every** render of the page goes through it, including error re-renders from the POST. |
| GET page | `event_link_tree` (app.py:~8390). Resolves the attendee from `?att=<id>`, falling back to the per-event cookie `_attendee_cookie_name(ev["id"])` (app.py:~8310). |
| Registration POST | `event_consent`, `POST /e/{token}` (app.py:~8493). Validates, dedups by email (`st.register_attendee`), emails the resume link on a *new* registration only, then redirects to `/e/<token>?att=<id>` and sets the cookie (`max_age=30 days`). |
| Resume (magic) link | `event_resume`, `GET /e/{token}/resume?rt=…` (app.py:~8635). It calls `auth.verify_recovery_token(rt)`, sets the cookie and redirects. |
| Recovery token | `auth.make_recovery_token` / `auth.verify_recovery_token` (auth.py:~249-277). Payload `{aid, p, iat}`, HMAC-signed, and **rejected after `_RECOVER_MAX_AGE` = 90 days from `iat`**. Other callers: app.py ~10004, ~10031, ~10158; `send_reminders.py:138`; `calendar_routes.py:918`. **Their behaviour must not change.** |
| Event row | `_EVENT_COLS` / `_event_row` (storage.py:~1690-1720). Has `event_date`, `end_date` (nullable, multi-day), `slug`, `welcome_message`, `ending_message`. `st.get_event` resolves the token **or** the slug. |
| Adding columns | `_add_missing_columns` in storage.py. Model on `welcome_message` / `ending_message` (storage.py:~1040-1046): `if ev_cols and "x" not in ev_cols: ALTER TABLE event ADD COLUMN x TEXT`. |
| Feedback forms of an event | `st.get_event_forms` (storage.py:~1863). It returns `qr_token, survey_type, topic, rp_name, form_instance_id` but **not** `open_at`/`close_at`. |
| Per-form response window | `form_instance.open_at` / `close_at`: naive local ISO `'YYYY-MM-DDTHH:MM'`, NULL = unbounded. `_window_state(ctx)` (app.py:~7908) returns `'open' / 'not_yet' / 'closed'`. String comparison is correct for this format. |
| Rating form route | `rating_form`, `GET /r/{qr_token}` (app.py:~7973). It already renders `closed.html` with `state="not_yet"` when `_window_state` says so. |
| Local "now" | `_now_local()` (app.py:~343). Use it, never `datetime.now()`. |
| QR | `_qr_data_uri(url)` (app.py:~14990) returns a `data:image/png;base64,…` string. `qrcode[pil]` is already in requirements. |
| Clipboard pattern | `static/js/app.js:~960` (clipboard with an `execCommand` fallback, then `window.prompt`), and `monitor_event.html:~255`. Copy that shape. |
| Organizer messages (model for the pinned update) | `set_event_messages` (storage.py:~1722), `activity_messages_save` `POST /activities/{token}/messages` (app.py:~9078), the "Messages to participants" card in `templates/activity_manage.html` (~275-310), `_manage_ctx` (app.py:~8670). The POST pattern is `_posted`, then `st.get_event`, then `_can_manage_event`, then `_audit`, then a 204 for XHR or a redirect. |
| Mail | `mailer.registration_confirmed_message` (mailer.py:~484). `mailer.email_configured()`. `_mail_after_response(...)` sends after the response. `st.log_email_send(...)` logs each send. |
| Rate limits | `ratelimit.py` bucket table (~line 27): `"register": (120, 60)`, `"check": (300, 60)`. Call as `rl.allow("<bucket>", ip)`. |
| i18n | `i18n.py`, `lt_*` keys around lines 366-471, shaped `{"en": …, "fil": …}`. Templates call `t('key', lang)`. **Every new user-facing string needs both EN and FIL.** |
| Existing tests on this page | `tests/test_event_e.py` (asserts `'name="consent"'`, the "consent box" error, and the `att=` redirect), `tests/test_registration_dedup.py`, `tests/test_outside_activity.py`. Their `_make_event` uses `event_date = "2026-06-11"`, which is **in the past**, so the feedback lock won't affect them. New tests that need a future event must pass a future date explicitly. |
| Release convention | Bump `APP_VERSION` in `version.py` and prepend a plain-language entry to its `CHANGELOG` list. Also prepend a developer entry to `CHANGELOG.md`, with the same date and version heading format as the entries already there. |

### Known issue to respect, not fix here

`?att=<integer id>` is unsigned, so anyone can guess another attendee's id. This
spec **must not make that worse**. In particular, the signed personal link and
QR (§A3) are shown **only** when the viewer is recognized by the cookie, never
because of `?att=` alone. Removing `?att=` is a separate hardening PR.

---

## PR-1 — reframe as registration, save-your-link panel, pinned update

### A1. Copy changes (i18n.py + link_tree.html)

Reword these existing keys:

| Key | New EN | New FIL |
|---|---|---|
| `lt_sign_in` | Register for this activity | Magparehistro sa aktibidad na ito |
| `lt_consent_submit` | Register | Magparehistro |
| `lt_dupe_notice` | You're already registered with this email. Submitting again takes you back to your registration; it won't create a duplicate. | Nakarehistro ka na gamit ang email na ito. Kapag nagsumite ulit, babalik ka sa iyong rehistro; hindi ito gagawa ng doble. |

Read the current values of `lt_thanks_pre` / `lt_thanks_post` and `lt_shared_email`
first, then reword them so they talk about *registration*, not *signing in*.

Add these keys:

- `lt_reg_intro`. EN: "Register once. You'll get a personal link to come back for the programme, updates, feedback and your certificate." FIL: "Magparehistro nang isang beses. Makakatanggap ka ng personal na link para bumalik sa programa, mga update, feedback at iyong sertipiko."
- `lt_reg_benefit_updates` ("📌 Updates from the organizers"), `lt_reg_benefit_feedback` ("📝 Feedback forms, open once the activity starts"), `lt_reg_benefit_cert` ("🏅 Your certificate, once you've given feedback"). Provide FIL for each.
- `lt_email_help`. EN: "We'll use this to find your registration again." FIL: "Gagamitin namin ito para mahanap muli ang iyong rehistro."

In the `{% else %}` branch of `link_tree.html`:
- Under the `<h2>`, add `<p class="muted">{{ t('lt_reg_intro', lang) }}</p>` and a
  compact `<ul>` of the benefits. Show the cert line only when `ev.certificate_enabled`.
- Under the email input (after `#dupe-notice`), add `lt_email_help` as
  `<p class="muted small">`.
- **Do not** rename any form field names (`name`, `email`, `consent`, …).

### A2. A single source of truth for "is the activity live?"

Add to app.py near `_window_state`:

```python
def _activity_start(ev):
    """'YYYY-MM-DDT00:00' local for the activity's first day, or None."""

def _activity_last_day(ev):
    """date of the activity's last day: end_date if set, else event_date; None if neither."""

def _feedback_state(ev, form, now=None):
    """'open' | 'not_yet' | 'closed' for one form of an event's link tree.
    - If the form has its own open_at/close_at, defer to _window_state(form).
    - Else if the activity has a start and now < start → 'not_yet'.
    - Else 'open'.
    """
```

`event_date` / `end_date` are stored as `'YYYY-MM-DD'`. Parse them defensively.
A malformed or empty date means "no gate" (return `None`), never an exception.

Extend `st.get_event_forms` to also select `fi.open_at, fi.close_at` and return
them as `open_at` / `close_at`. Callers that ignore extra keys are unaffected;
grep the callers to confirm.

### A3. Lock feedback until the activity starts

**Template.** In `_event_view`, give each `links[i]` a `state` from `_feedback_state`.
Also pass `feedback_opens` (a human date, through the existing `humandaterange`
filter or `_humandt`) and `any_open = any(l.state == "open" for l in links)`.
In the registered branch:

- `state == "not_yet"`: render the tile as a **non-link** `<div class="tile lg locked">`
  with 🔒 and "Opens {{ feedback_opens }}". Above the list, show one line:
  `lt_feedback_locked`, EN "Feedback opens when the activity starts — {date}. Come back to this page then." Provide FIL.
- `state == "closed"`: a non-link tile with "Closed". Don't send people to the closed page.
- `state == "open"`: unchanged.
- Add a `.tile.locked` style next to `.tile.done` in the `<style>` block (muted, `cursor:default`).

**Server.** In `rating_form` (`GET /r/{qr_token}`): when the form belongs to an event
(`st.event_for_form_instance(conn, ctx["id"])`) **and** the form has no `open_at`
**and** `_feedback_state(ev, ctx) == "not_yet"`, render `closed.html` with
`state="not_yet"` and `opens=` the activity's start, with status 403. This is
the same path the existing window check uses. Forms with their own `open_at`
already go through the existing `_window_state` branch, so leave that untouched.
Also check the POST handler for `/r/{qr_token}` and apply the same gate, or a
crafted POST can still submit. Find it with `grep -n '@app.post("/r/' app.py`.

Standalone forms (not attached to an event) and events with no date: **no change.**

### A4. Personal-link validity = last day + 30 days

`auth.py`: add an optional `expires_at` (epoch seconds) parameter to
`verify_recovery_token(token, now=None, expires_at=None)`. When `expires_at` is
given, check `now <= expires_at` **instead of** the `_RECOVER_MAX_AGE` age check.
Signature and purpose checks are unchanged. The default call path is
byte-for-byte the same behaviour, so the other five callers are unaffected.

app.py: add `_personal_link_expiry(ev)`. It returns an epoch for 23:59:59 local
on `_activity_last_day(ev) + 30 days`, or `None` when the activity has no date
(the caller then keeps the 90-day rule).

- `event_resume`: call `auth.verify_recovery_token(rt, expires_at=_personal_link_expiry(ev))`.
  This needs `ev` first, so reorder the code to load the event before verifying.
- The cookie in **both** `event_consent` and `event_resume`: set `max_age` to
  `max(30 days, seconds until _personal_link_expiry(ev))` through a small helper
  `_attendee_cookie_max_age(ev)`. Someone who registers two months early
  stays recognized on that device through the event.
- An expired or invalid link still redirects to `/e/<token>`, but add `?expired=1`.
  `event_link_tree` then passes `link_expired=True` and the form branch shows a
  one-line notice (`lt_link_expired`, EN "That personal link has expired. Register again with the same email to get back in."; provide FIL).
  Re-registering with the same email already resumes the row, so this is all the recovery needed.

### A5. The "Save your link" panel

In `_event_view`, add `recognized: bool`. It is True only when the request's
attendee cookie equals `attendee["id"]`. Thread the request cookies through:
`_event_view` already has `request`. When `recognized`:

```python
token = auth.make_recovery_token(attendee["id"])
personal_link = f"{_base_url(request)}/e/{ev['slug'] or ev['event_token']}/resume?rt={quote(token)}"
personal_qr = _qr_data_uri(personal_link)
```

Pass `personal_link`, `personal_qr`, `can_email_link = bool(attendee.get("email")) and mailer.email_configured()`,
and `just_registered = request.query_params.get("new") == "1"`.

`event_consent`: change the redirect to `/e/<token>?att=<id>&new=1` **only** when
`registered_now` is True. Keep `att=` so `tests/test_event_e.py` still finds it.

Template: in the registered branch, **replace** the current green `flash ok` +
"Not you?" block with:

```
<section class="panel save-link" aria-labelledby="save-h">
  <h2 id="save-h">{{ just_registered ? "You're registered 🎉" : "Your personal link" }}</h2>
  <p>{{ lt_save_body }}</p>                       # "Save this link or screenshot the QR. It's how you get back here for updates, feedback and your certificate — on any device."
  <img src="{{ personal_qr }}" alt="QR code of your personal link" width="180" height="180">
  <div class="save-actions">
    <button type="button" class="btn" data-copy="{{ personal_link }}">Copy link</button>
    <button type="button" class="btn ghost" data-share="{{ personal_link }}" hidden>Share…</button>
    <a class="btn ghost" href="{{ personal_qr }}" download="{{ (ev.slug or ev.event_token) }}-my-link.png">Download QR</a>
  </div>
  {% if can_email_link %}<form method="post" action="/e/{{ ev.event_token }}/email-link"> … "Email me this link" … </form>{% endif %}
  <p class="muted small">Valid until {{ link_valid_until }}.</p>   # only if _personal_link_expiry(ev) is not None
</section>
```

Pseudo-syntax above: write proper Jinja with `t()` keys and FIL strings.

- When `just_registered` is True, show the panel expanded. Otherwise render it
  as a `<details>` with the summary "📎 Your personal link & QR", collapsed, so
  returning visitors aren't nagged.
- When **not** `recognized` (e.g. reached via a bare `?att=`), don't render the
  panel or the link at all.
- Keep the "Not you? Start fresh on this device →" line, moved below the panel.
- JS (inline in the template, like the existing dupe-check script): `[data-copy]`
  uses the clipboard pattern from app.js:~960 and shows "Copied ✓" in the button
  for 2s. `[data-share]` is un-hidden only when `navigator.share` exists; it calls
  `navigator.share({title: document.title, url})` and ignores an `AbortError`.
- Make sure the QR `<img>` is centered and `max-width:100%` at phone width.

### A6. "Email me this link"

New route `POST /e/{event_token}/email-link`:
- Resolve the attendee **from the cookie only** (not `?att=`). If there's none,
  redirect to `/e/<token>`.
- Add a `ratelimit.py` bucket `"email_link": (5, 3600)` per IP. Also apply a
  per-attendee cooldown of one send per 15 minutes. Implement it with
  `st.log_email_send` history: add a small storage helper that returns the last
  send time for `(feature="registration_link", recipient)`. `st.log_email_send(conn, feature, recipient, …)`
  is at storage.py:~1602; read its table schema first.
- Send `mailer.registration_confirmed_message(...)` (reworded in A8) with the
  personal link, through `_mail_after_response`, with `feature="registration_link"`.
- Redirect to `/e/<token>?att=<id>&emailed=1`. The page shows "Sent to a•••@example.com" (masked) or the cooldown message.
- Never reveal the email beyond the masked form, and never accept an address from the form body.

### A7. Pinned update (organizer → registered participants)

**Schema** (`_add_missing_columns`): `event.announcement TEXT`, `event.announcement_at TEXT`
(local ISO `'YYYY-MM-DDTHH:MM'`). Add both to `_EVENT_COLS` and `_event_row` **at
the end** of the select list (indices 21, 22), so the existing indices don't shift.

**Storage:** `set_event_announcement(conn, event_id, text, now_iso)`. Blank becomes
NULL for both columns. Text is stripped and capped at 1000 chars.
`announcement_at` updates only when the text actually changes.

**Route:** `POST /activities/{event_token}/announcement`. Copy `activity_messages_save`
exactly: `_posted`, `get_event`, `_can_manage_event`, cap, save, `_audit(..., "event_announcement_set", …)`, 204 for XHR, else redirect to manage.

**Manage page:** a new `mcard` **above** "Messages to participants", titled
"📌 Pinned update". It has a hint ("Shown at the top of every registered
participant's page. Use it for room changes, schedule shifts, reminders. Clear it
to remove."), a textarea (`maxlength=1000`), and an explicit **Post update**
button. Don't auto-save it: a half-typed announcement must not go live. When
one is posted, also show "Posted {{ announcement_at|humandt }}" and a
**Remove** button that posts an empty value. Add `announcement` /
`announcement_at` to `_manage_ctx`.

**Participant page:** in the registered branch, directly under the save-link
panel, show `<div class="panel tint-amber" role="status">📌 <strong>Update</strong> · <span class="muted small">{{ posted time }}</span><div style="white-space:pre-wrap">{{ announcement }}</div></div>`
when set. Plain text with autoescape; no HTML and no `{name}` personalization.
**Do not** show it on the pre-registration form; the update is part of what registering unlocks.

**Out of scope:** emailing registrants when an update is posted. The relay
quota is ~1500/day (docs/MAIL_RELAY_SETUP.md). Note it as a follow-up in the PR body.

### A8. Registered-view order + email copy

The final order of the `{% if attendee %}` branch:
1. Save-link panel (A5)
2. Pinned update (A7)
3. "Not you? Start fresh" line
4. Welcome message
5. Resource persons
6. Programme & resources (`resources_now`)
7. **Feedback** ("Rate this activity" with the A3 states)
8. Ending message, certificate, unlocked resources (unchanged logic, moved after feedback)
9. The locked-resources notice

In `mailer.registration_confirmed_message`, change the wording to the save-this-link
framing: subject "You're registered — {title}". In the body, add "Save this email
or bookmark the link. It's how you get event updates, the feedback forms (open
once the activity starts) and your certificate." The CTA becomes "Open my event page".
Keep the signature unchanged so the other callers still work.

### A9. Tests — new file `tests/test_event_hub.py`

Model it on `tests/test_event_e.py` (`client`, `manager`, `db_path` fixtures, and
its `_make_event`). Add a variant `_make_event(manager, db_path, event_date=...)`
for future dates (use a date > today + 30 so the test never goes stale; build
it with `datetime.date.today()`).

Must cover:
1. The form page says "Register for this activity" and still posts `name="consent"`.
2. After registering for a **future** activity: the page has no `/r/` links, shows the locked text, and `GET /r/<form token>` returns 403 with the not-yet page. The POST is rejected too.
3. After registering for a **past or today** activity: the `/r/` links are present (no regression).
4. A form with its own explicit `open_at` keeps its own behaviour (set it with `st.set_response_window`).
5. The save-link panel appears after registration (the redirect carries `new=1`; follow it with the same client so the cookie applies) and contains `/resume?rt=` plus `data:image/png;base64`.
6. The panel is **absent** when the same page is fetched by a fresh client with only `?att=<id>` (no cookie).
7. `verify_recovery_token(t, expires_at=...)`: valid before expiry, None after. A token older than 90 days is still valid when `expires_at` is in the future. The default call path still enforces 90 days.
8. `event_resume` with an expired token redirects with `expired=1`.
9. Pinned update: a manager posts it, a registered participant sees it, the pre-registration form doesn't show it, a non-manager POST is refused, a blank post removes it, and `announcement_at` doesn't change on a re-save of the same text.
10. Email-link: no cookie means a redirect with no send. With email unconfigured, the button is hidden. Assert the rate limit or cooldown branch (monkeypatch `mailer.email_configured` and the sender, the way existing mail tests do; grep `tests/` for `email_configured`).

Then run `bash run_tests.sh` and fix any existing tests that asserted old copy
("Sign in to give your feedback" and similar). Update their assertions; don't
delete the tests.

### A10. Release

`version.py`: bump the minor version. Plain-language entry, e.g. "The activity
page now works as event registration. After registering you get a personal link
and QR to save; feedback opens when the activity starts; organizers can pin an
update for participants." Add a matching developer entry at the top of `CHANGELOG.md`.

### A11. Manual check before pushing

Use `run` / `LOCAL_RUN.md`. At 390px width:
- The form page.
- Register for a future activity: panel expanded, QR visible, copy works, feedback locked.
- Reload: the panel is collapsed.
- Open the personal link in a private window: it is recognized.
- Post an update from manage: it shows for the participant.

Check both EN and FIL, and both light and dark themes if the page supports them.

---

## PR-2 — organizer side of the hub (small, optional)

- On the manage page's "Public link" card (activity_manage.html ~135-160), add
  the **event QR** (`_qr_data_uri` of `{base}/e/{slug or token}`) with a
  "Download QR for posters" link, plus a line: "Participants who register get
  their own personal link; this one is for everyone."
- On the Monitor roster, show "Personal link valid until …" next to the existing
  copy/resend actions (uses `_personal_link_expiry`).
- Follow-up candidate, **not** in this spec: "Email this update to all
  registrants", with a cooldown like the reminder batch (app.py ~10049).

---

## Non-goals

- Removing or signing `?att=` (separate hardening PR).
- Accounts or passwords for participants. The personal link is the identity.
- Push notifications or SMS.
- Changing outside ("invited") activities. They have no public page (`event_link_tree` 404s them).
