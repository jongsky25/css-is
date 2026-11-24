# Advisory rethink: Google Slides and a single "New advisory" flow

Planning session: November 24, 2026, branch `claude/charming-faraday-gxl981`.
Status: **plan only**. Nothing here is built or authorized for release.
Replaces the built-in poster editor described in [ADVISORY_POSTERS.md](ADVISORY_POSTERS.md).
The review/issuance machinery in [ADVISORY_REVIEW.md](ADVISORY_REVIEW.md) and
[ADVISORY_ISSUANCE.md](ADVISORY_ISSUANCE.md) is kept unless noted.

## Why

Users want to edit the advisory freely. Today the app draws the poster from a fixed form
and refuses text that does not fit. The office already designs advisories in Google Slides
([BLHSDTO-Advisory-Template](https://docs.google.com/presentation/d/1T750K6cphrzOo6_-3GlP_9vdEt-fKXLWnZSjCGWbHY4/edit):
one JOAS sample and three variants). The app will create the Slides file and keep the
workflow around it. Advisories also need to exist without an activity.

## Owner decisions (November 24, 2026)

| # | Decision |
|---|---|
| D1 | The output is a Google Slides file made from the office template, not an app-drawn PDF. |
| D2 | No need to keep the old renderer: everything issued so far was a trial. |
| D3 | Advisories can be started from the Advisories module, not only from an activity. |
| D4 | Starting there asks whether the advisory is for an existing activity, a new activity (created together with the advisory), or no activity. |
| D5 | The flow must feel seamless: people should not have to hunt for where to go next. |

## The flow

### Entry points (all open the same flow)

| Where | What happens |
|---|---|
| **Advisories → New advisory** (main button on the register) | Starts at step 1. |
| **Activity → Manage → Advisory** | Step 1 is skipped; the activity is already linked. If the activity already has an advisory, opens it instead. |
| My desk / dashboard shortcut | Same as the register button. |

### Step 1: What is this advisory for?

Three large choice cards (one tap each, readable on a phone):

1. **An activity already in Office Connect.** A search box lists activities the person can
   manage, upcoming ones first (title, date, section). Picking one shows it as a small card
   with **Change**. An activity that already has an advisory says so and links to it, so no
   duplicate is made.
2. **A new activity.** A short form: title, start/end date, venue or online, organizing
   section. On Create, the activity and the advisory are made together in one step. The page
   then says registration, forms and links can be added later from the activity's Manage page,
   with a link to it.
3. **Not about an activity** (general announcement, reminder, notice). Title only.

### Step 2: Details (prefilled, all editable)

- Title (from the activity when linked).
- Owning division (defaults to the person's division; decides Chief/Director routing).
- Audience: internal / external / both, plus external email addresses.
- Template: thumbnails of the three variants, one preselected.
- Contact person (remembers the last one used, as today).
- For activity advisories: dates, venue and link-tree links, ready to drop into the slide.

Going back to step 1 keeps everything typed. Validation keeps entered values on phone forms.

### Step 3: Create

One button: **Create advisory**. The app reserves the number, copies the chosen template
into the advisory folder, fills in the number, title, dates, links, contact and QR code, and
shares the file with the preparer. The page opens on the advisory's home page with a large
**Open in Google Slides** button. If the relay is not set up or fails, the page says so in
plain words and nothing half-made is left behind (same request id = same file on retry).

### The advisory home page (one place for everything)

- A progress bar: **Draft → Chief → Director → Issued**.
- Exactly one main button for the current stage: *Open in Slides*, *Submit for review*,
  *Endorse* / *Approve* / *Return*, *Issue*. Other actions sit in a smaller menu.
- A preview of the current slide, the linked activity card (or "General advisory"), the
  discussion and the history.
- Banners, never dead ends: "Edited after submission: submit again", "Waiting for the
  Chief (name)", "Returned: see comments".

### Review and issue with a live file

- **Submit** takes a snapshot: the app asks the relay for a PDF and PNG of the slide and
  records the Drive file version. Reviewers approve that snapshot, as today they approve an
  exact PDF.
- While under review the preparer's access becomes comment-only, so the file under review
  cannot drift. A return gives edit access back.
- If the Drive version differs from the approved snapshot at issue time, issuing is blocked
  and the advisory goes back to Draft.
- **Issue** emails the approved PDF (never the live file) and, for activity advisories,
  can show the approved image on the activity's link tree. After issue the Slides file is
  made view-only.

## What changes in the code

| Area | Change |
|---|---|
| Relay (`apps_script/`) | Add Slides actions: copy a template, replace `{{placeholders}}`, put the QR image in, export PDF and PNG, set preparer access (edit / comment / view). Reuse the travel/documents relay signing and request-id idempotency. |
| Template | The office template's sample text becomes `{{placeholders}}` (number, title, dates, venue, message, table rows, contact, attention). An owner-side setup step, like the travel templates. |
| Advisory model | `activity_id` is already nullable (design P3). Add kind (activity / general), Slides file id, template variant. Revision artifacts become snapshots exported from Drive. |
| New flow | New-advisory pages (choose → details → create), register button, activity entry reuse. "New activity" reuses `storage.create_event` inside the same transaction. |
| Removed | `advisory.py` renderer, `assets/advisory/` fonts and icons, the old poster editor and its text-fit rules, the old publish route. Trial advisory records are cleared (live data, so only with a backup and an explicit owner instruction at release). |
| Kept | Numbering, Chief → Director review, Work discussion, issuance, frozen recipients, delivery records, register and dashboard counts. |

## Build order (each a separate candidate)

1. **Relay and template:** Slides actions in the relay; placeholder template setup script;
   synthetic tests with a fake relay. Owner deploys the new script version.
2. **New-advisory flow:** the three-choice start, details, create; general advisories;
   create-with-new-activity; activity entry opens the same flow.
3. **Slides-backed drafts:** advisory home page, snapshot on submit, access locking, drift check.
4. **Issue and publish from snapshots;** view-only after issue.
5. **Cleanup:** remove the old renderer/editor/assets; clear trial records under the release gate.

Verification follows `docs/CLOUD_WORKSPACE.md`: synthetic data, fake relay, no outbound mail.
Real Slides behavior (placeholder fill, export look, permission changes) needs a live check
by the owner after the relay is deployed.

## Answers to the open questions (owner, November 24, 2026)

| # | Question | Answer |
|---|---|---|
| D6 | Review stages | Keep Chief → Director. |
| D7 | Editors | All members of the owning section can edit the Slides file (not only the preparer). |
| D8 | What recipients get | PDF attachment by email; the approved image on the activity's link tree. |
| D9 | New activity with an advisory | A real activity is created at once (needed for its link-tree URL and QR code). |
| D10 | General advisories in public | No public page. A QR code only if the preparer gives a link. |
| D11 | Comments | App discussion **and** Slides comments. |
| D12 | Template variants | Offer all three, with thumbnails. |

Consequences for the design:

- **Section editing (D7):** the relay shares the file with every active member of the owning
  section who has a `@doh.gov.ph` address, without notification emails. Membership is read
  at creation and again at each access change (submit, return, issue). During review all
  section editors become commenters; a return gives editing back to the then-current members.
  Edits are attributed in Slides version history, not in the app.
- **Slides comments (D11):** reviewers (Chief, Director) get comment access to the file.
  Slides comments are not part of the app's decision record. At submit, the snapshot step
  also reads the open Slides comments through the relay (Drive comments API) and stores
  them with the reviewed version, so the history shows what was open when each decision
  was made. Returns and approvals are still made only in the app.

## Sending (question 8, still open)

What the app could do when an advisory is issued, from what exists today:

| Option | What it takes | Notes |
|---|---|---|
| Email with PDF (built) | Nothing new | Current behavior; delivery is recorded per recipient. |
| Post to an office Telegram group | Small: the office bot already posts to registered, allowlisted groups and topics (`telegram_groups.py`) | On issue, the preparer ticks which registered group(s) get the approved image, title and link. Recorded like email deliveries. |
| Share button for Viber / Messenger | Small: phone share sheet | The issued page offers a ready caption, the image and the short link; the person shares it into a Viber/Messenger group by hand. No automatic Viber posting: Viber has no free group-posting API for this use. |
| Office Connect notice | Built | "Issued advisories for you" already lists it for internal recipients. |
| Activity calendar entry | Small | Show the issued advisory on the activity's calendar entry. |

Working recommendation: email (built) + Telegram group post + share button.
