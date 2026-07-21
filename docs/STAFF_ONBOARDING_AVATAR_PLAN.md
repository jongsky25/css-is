# Staff onboarding, avatar companion & two-card landing — implementation spec

**Status:** planned, not started. Build follows this plan phase by phase.
**Owner:** avincentpatrick
**Why:** After the wellness module (v2.25) the app is no longer *only* the CSS
dashboard — it is two things a staff member might sign in for. The sign-in
experience should reflect that: land on a simple "what do you want to do?"
chooser (Wellness | CSS), give every account a one-time onboarding where they
complete their profile (incl. photo) and adopt a named, animated avatar
companion, and route plain **viewer** accounts into *their own* results
(person profile + section profile) instead of the manager-shaped hub.

This is **not** a rebuild. Almost every ingredient already exists; the work is
one new chooser page, one onboarding flow, three columns, and wiring.

---

## 1. The requested flow (restated as acceptance criteria)

1. Staff signs in → sees a **new home page**: greeting + profile picture +
   their avatar pet, and two cards — **Wellness** and **CSS**.
2. On the **first sign-in** (for existing accounts: first sign-in after this
   update), the staff member goes through onboarding first:
   * update their profile — display name check + **profile picture upload**;
   * **choose an avatar** from an interactive, animated set (animals *and*
     plants) and **give the pet a name**.
3. Their profile picture shows on **their own person page** (already true via
   `/photo/<rp_id>` once the photo exists — onboarding is what finally gets
   photos *into* the directory).
4. The **CSS card** goes to the original CSS hub, still limited by role — but
   a **viewer** account is routed first to their **own people profile**, with
   their **section's profile** one tap away.
5. The wellness **"Planned activity" selector is visual / image-based** —
   illustrated cards that invoke a sense of wellness — instead of the current
   plain-text radio list.
6. Wellness approvals **escalate by rank**: staff → section chief (as today),
   a **section chief's own claim → their division chief**, and a **division
   chief's claim → the Director**.

---

## 2. What already exists (leverage, don't rebuild)

| Ingredient | Where | State |
|---|---|---|
| Roles viewer/encoder/section_manager/admin + capability map | `auth.py` `ROLE_CAPS` | done — unchanged by this work |
| Login flow, temp-password force-reset | `app.py` `login_submit` (~1517) | done — onboarding hooks in here |
| Account → directory person link | `admin_user.rp_id` → `resource_person` (`storage.py` ~362) | done |
| Profile photo storage + serving | `resource_person.photo` BLOB, `set_rp_photo` (~3008), `GET /photo/{rp_id}` (~5159) | done — but almost no photos are uploaded; person page falls back to initials (`person.html` ~177) |
| "What would you like to do?" hub (role-filtered module cards + stats) | `GET /` `home()` (~3505), `home.html` | done — becomes the **CSS side** of the fork |
| Animated SVG companion with 6 growth stages | `wellness_hub.html` (plant, `plant-sway` keyframes, `prefers-reduced-motion` guard) | done for one species — generalize into a catalog |
| Wellness gamification (points/level/stage/streak/badges, derived) | `storage.py` `wellness_stats` (~4738) | done — stage number drives the avatar's growth |
| Person profile page | `GET /dashboard/people/{rp_id}` (~9880) | done — viewer redirect target |
| Section profile page | `GET /dashboard/teams/{org_path}` (~10182) | done — second viewer target |
| Guarded ALTER TABLE migration pattern | `storage.py` `_migrate` (~340) | pattern to reuse |
| Greeting name helper | `_account_first_name` (~3484) | reused on the chooser |
| `/start` AI landing opt-in | `ai_landing_default` setting, `login_submit` | interacts — see §7 |

## 3. Design decisions

**D1 — `/` becomes the chooser; the current hub moves to `/css`.**
The existing `home()` is exactly "the original CSS dashboard entry, limited by
user level" — keep it intact, just re-address it. The new `/` is a small,
calm page: greeting, photo, pet, two cards. Every deep link (`/dashboard/…`,
`/reports/…`) keeps working; only links that pointed at the hub *as a page*
(`href="/"` in nav brand, `nav_groups_for`, search palette, tests) get swept
to `/css` or to the chooser as appropriate (§8, Phase 3).

**D2 — one avatar system, not two.**
The wellness module already has a companion with 6 derived growth stages. The
chosen avatar **is** the wellness companion: `avatar_kind` picks the species
(animal or plant), `avatar_name` is the pet's name, and the existing
`wellness_stats` stage (1–6) renders that species at the right growth stage.
No parallel avatar state, no drift — the fun layer stays derived, exactly as
the wellness module's design comment promises. Accounts that somehow have no
choice yet default to the current plant, so `wellness_hub.html` never breaks.

**D3 — onboarding is detected by a column, triggered at login, guarded at `/`.**
`admin_user.onboarded_at TEXT` (NULL = hasn't onboarded). Backfill is *no
backfill*: existing accounts are NULL, so everyone gets the onboarding once
after the update — which is what "first time log in" means for a live system.
Redirect order in `login_submit`: temp-password reset **first** (unchanged),
then NULL `onboarded_at` → `/welcome`, else the normal landing. The `/`
route also guards (cheap — it reads the account row anyway for the greeting),
so a half-finished onboarding can't be skipped by typing a URL. Deep links
stay usable regardless — onboarding is encouraged, not a jail.

**D4 — profile step writes to the directory, not a new store.**
Photo upload calls the existing `set_rp_photo` on the account's linked
`rp_id`, so `/photo/<rp_id>` and the person page (`person.html` avatar block)
pick it up with zero new plumbing — this *is* requirement 3. Accounts with no
`rp_id` (rare, e.g. the first-run admin) see the avatar step only, with a
note that an admin can link their directory record.

**D5 — viewer routing is done by the card, not by locking `/css`.**
A helper `_css_entry_for(user, conn)` resolves the CSS card's href:
* viewer **with** a linked, non-hidden directory person → their
  `/dashboard/people/<rp_id>`; the person page grows a small "your section →
  `/dashboard/teams/<org_path>`" banner shown when you're viewing *yourself*;
* viewer without a usable person record (no `rp_id`, or `hidden_public` and
  they're not admin — that page would bounce them, see ~9893) → `/css`;
* everyone else → `/css`.
`/css` itself stays reachable by viewers (they hold the `view` capability;
the hub is already role-filtered) — the requirement is about where they land
*first*, not about walling off the dashboard.

**D6 — chosen once, editable later.**
A small `/me` profile page (photo, display name, avatar species + pet name)
so onboarding is never a one-shot trap. Linked from the chooser and the
wellness hub ("rename your pet").

## 4. Schema (Phase 1)

Three guarded columns on `admin_user`, same pattern as the `rp_id` migration:

```sql
ALTER TABLE admin_user ADD COLUMN avatar_kind  TEXT;   -- species key, e.g. 'cat'
ALTER TABLE admin_user ADD COLUMN avatar_name  TEXT;   -- the pet's given name
ALTER TABLE admin_user ADD COLUMN onboarded_at TEXT;   -- NULL = show /welcome
```

Storage helpers: `get_user_profile(conn, user_id)` (account + rp name/photo
flag + org path in one read), `set_user_avatar(conn, user_id, kind, name)`
(validates kind against the catalog, trims/limits the pet name),
`mark_onboarded(conn, user_id)`. All audited via the existing `_audit` path
(`profile_update`, `avatar_choose`).

## 5. Avatar catalog & animation spec (Phase 2)

One Jinja macro file `templates/_avatars.html`:
`render_avatar(kind, stage, name, size)` → inline SVG (no external assets —
same constraint the plant honors, and it keeps the PWA offline-safe).

Catalog v1 — 6 species, three animals + three plants:

| key | label | family | stage flavor (1 → 6) |
|---|---|---|---|
| `plant`     | Blossom plant | plant  | existing Seed → Flourishing art, reused as-is |
| `cactus`    | Cactus        | plant  | nub → flowering saguaro |
| `bonsai`    | Bonsai        | plant  | shoot → sculpted canopy |
| `cat`       | Cat           | animal | kitten → majestic cat |
| `bird`      | Bird          | animal | hatchling → full plumage |
| `turtle`    | Turtle        | animal | hatchling → wise elder |

Interactivity ("make the avatar interactive and moving"):
* **idle motion** — per-family CSS keyframes (plants sway like today's
  `plant-sway`; animals get a slow breathe/blink loop);
* **reaction** — tap/click adds a short `.happy` class (bounce + sparkle),
  removed on `animationend`; hover shows the pet's name in a speech bubble.
  ~20 lines of vanilla JS in the template, no dependency;
* **`prefers-reduced-motion: reduce`** disables all of it (pattern already in
  `wellness_hub.html` line 13 — extend, don't fork);
* stage names generalize: per-family name arrays (plants keep Seed…Flourishing;
  animals get Hatchling/Kitten…Flourishing equivalents) replacing the single
  `WELLNESS_STAGE_NAMES` list, keyed by the catalog entry.

The **picker** on `/welcome` renders every species live (at stage 2, so they
look alive but leave room to grow), radio-button semantics, keyboard
navigable, with the name field ("name your pet") required, ≤ 24 chars.

## 6. Routes & templates

| Route | Method | What |
|---|---|---|
| `/welcome` | GET | onboarding page: step 1 profile (photo upload + name confirm, only when `rp_id` linked), step 2 avatar picker + pet name. One template `welcome.html`, one submit |
| `/welcome` | POST | validate, `set_rp_photo` (optional), `set_user_avatar`, `mark_onboarded`, audit, → `/` |
| `/` | GET | **new** `choose.html`: greeting (`_account_first_name`), photo (or initials fallback, same as `person.html`), the pet (idle animation, tappable), two cards: **Wellness** → `/wellness` (with points/streak teaser from `wellness_stats`), **CSS** → `_css_entry_for(...)` (role-aware blurb from `ROLE_BLURB`) |
| `/css` | GET | the current `home()` verbatim, re-addressed; `/`'s old query behaviors move with it |
| `/me` | GET/POST | edit photo / avatar species / pet name; reuses the same form partials as `/welcome` |

Nav sweep: `dash_layout.html` brand link stays `href="/"` (brand → chooser is
correct now); `nav_groups_for` gets a "Home hub" entry pointing at `/css` and
a "My profile" (`/me`) entry; the search palette inherits both from
`nav_groups_for` automatically (`/search` reuses it).

## 7. Interactions with existing flows (the sharp edges)

* **Temp-password reset** happens *before* onboarding — `login_submit` already
  short-circuits to `/reset-password` without issuing a session; the
  onboarding check runs only on the session-issuing path. After the reset's
  own sign-in, the NULL `onboarded_at` catches them.
* **`/start` AI landing** (admin opt-in): an explicit admin decision, so it
  keeps precedence *after* onboarding: order is reset → `/welcome` →
  (`ai_landing_default == "start"` → `/start`) → `/`. `/start` links
  "Classic home" — that link joins the sweep and points at `/css`.
* **`?next=` deep links** keep winning over the chooser (unchanged behavior),
  but *not* over `/welcome` on a first sign-in — onboarding runs once, deep
  link honored right after.
* **Hidden person edge**: `/dashboard/people/<rp_id>` bounces non-admins off
  `hidden_public` people (~9893). `_css_entry_for` checks this and falls back
  to `/css` rather than routing a viewer into a redirect loop.
* **Service worker / PWA**: `sw.js` and `manifest.webmanifest` reference `/`;
  verify the offline shell still resolves and add `/css` to any precache list.
* **Wellness hub**: swaps its hard-coded plant SVG for
  `render_avatar(user.avatar_kind or 'plant', stats.stage, user.avatar_name, …)`;
  everything else (points, badges, claims) untouched.
* **i18n**: all new strings through the existing `i18n.py` mechanism; run
  `tools/i18n_review.py`.

## 7a. Wellness refinements (added in review)

### 7a.1 — Visual activity selector on `/wellness/apply`

The apply form's "Planned activity" field (`wellness_apply.html` ~39) is a
bare radio list of the four `WELLNESS_ACTIVITIES`. Replace it with a grid of
**illustrated activity cards** — each card an inline SVG scene (same
no-external-assets rule as the avatars, PWA/offline-safe) over the label:

| key | scene sketch | palette cue |
|---|---|---|
| `exercise`      | figure mid-stride, sun arc          | energizing warm |
| `meditation`    | seated figure, lotus/ripple rings   | calm blue-green |
| `mental_health` | head silhouette with leafy growth   | soft teal |
| `hobby`         | brush + strings + book cluster      | creative violet |

Mechanics: each card is a `<label>` wrapping the **same** hidden
`<input type="radio" name="activity">` it has today — the POST payload,
validation (`create_wellness_claim` allowed-keys check) and storage are
untouched; this is purely presentational. Selected card gets a lifted/ringed
state; cards are keyboard-operable (radios stay focusable), have full text
labels (never image-only, for a11y and i18n), and a gentle hover float that
`prefers-reduced-motion` disables. The SVG set lives in a
`templates/_wellness_icons.html` macro so the hub and reflection pages can
reuse the same iconography beside claim rows.

### 7a.2 — Approval escalation chain (rank-aware approvers)

Today `get_wellness_approvers` (~4564) resolves approvers as *any
section/division chief in the claimant's own org unit*, and a chief's own
claim falls through to the **admin fallback**. The requested rule is a proper
chain of command:

| claimant is… | approver |
|---|---|
| regular staff (no chief designation) | their **section chief** — current same-unit behavior, unchanged |
| a **section chief / section head** | the **division chief** of the parent division |
| a **division chief** | the **Director** |
| the Director | admin fallback (unchanged — top of the chain) |

Everything needed already exists in the schema:

* **Rank** comes from `resource_person.designation` — the vocabulary is
  already canonical (`_WELLNESS_CHIEF_DESIGNATIONS`, and `_SIGNATORY_RANK`
  ~2055 already knows `director` > `division chief` > `section head/chief`).
  Introduce one shared rank map in `storage.py` rather than a third copy.
* **"Up" traversal** uses `org_unit.path` (`'BLHSD/HSMED/Equity'` —
  bureau/division/section) exactly as the rollups do: the parent division of
  a section is the `level='division'` unit whose path is the section's path
  prefix; the Director sits in the `level='office'` directorate (see the
  organogram builder ~1959).

Rewrite `get_wellness_approvers` to: (1) rank the claimant by designation;
(2) resolve the approver *unit* one rank up (staff → own unit's chiefs;
section chief → parent division; division chief → the directorate/Director by
designation); (3) return active accounts of matching-designation people in
that unit, never self. Empty chain → the existing admin fallback in
`is_wellness_approver` — no behavior change for unlinked accounts.

Consequential updates (all in the wellness module, nothing outside it):

* `list_wellness_approvals` (~4609) currently scopes a chief's queue to
  *same `org_unit_id`* — it must become chain-aware, or a division chief
  never sees their section chiefs' claims. Since the pending set is small,
  the honest implementation is: fetch pending claims, keep those where
  `user.id ∈ get_wellness_approvers(claim.user_id)` (admins keep seeing all).
* `user_is_wellness_chief` (~4595) gates queue visibility by designation —
  extend its designation set with `director` so the Director gets the
  approvals nav/queue at all.
* `wellness_hub`'s "your request goes to your section chief" copy becomes
  rank-aware ("…to your division chief" / "…to the Director").
* Tests: one per chain link (staff→section chief, section chief→division
  chief, division chief→director, director→admin fallback), plus
  cross-section isolation (a division chief sees *their* division's section
  chiefs only) and the no-directory-link fallback (existing tests keep
  passing).



1. **Schema + storage** — the three columns (guarded ALTERs), profile/avatar
   helpers, species catalog constants + per-family stage names in
   `storage.py`. Tests: migration idempotence, avatar validation, stage-name
   resolution. *No visible change yet.*
2. **Avatar catalog + `/welcome`** — `_avatars.html` macro (6 species × 6
   stages + animations), `welcome.html`, GET/POST, login-redirect hook,
   audit. Tests: first-login redirect, reset-then-onboard ordering, POST
   validation, no-rp_id degradation.
3. **The fork** — `choose.html` at `/`, hub re-addressed to `/css`, link
   sweep (`dash_layout.html`, `nav_groups_for`, `start.html`, any
   `RedirectResponse("/")` that meant "the hub", tests, sw precache).
   Tests: chooser renders per role, legacy hub reachable at `/css`, `/start`
   precedence preserved.
4. **Viewer routing** — `_css_entry_for`, section banner on own person page.
   Tests: viewer-with-rp lands on person profile, hidden/no-rp fallbacks,
   non-viewers unaffected.
5. **Unify + edit** — wellness hub renders the chosen companion; `/me` page.
   Tests: default-plant fallback, rename flows.
6. **Wellness refinements** (§7a — independent of 1–5, can land in either
   order):
   * **6a** visual activity selector — `_wellness_icons.html` + apply-form
     card grid; POST contract unchanged, so only template tests move.
   * **6b** approval escalation — shared rank map, chain-aware
     `get_wellness_approvers` / `list_wellness_approvals` /
     `user_is_wellness_chief`, rank-aware hub copy, chain-link tests.
7. **Ship** — i18n review, `version.py` changelog entry (v2.26), QA playbook
   pass, `CHANGELOG.md`.

## 9. Out of scope (explicitly)

* No role/capability changes — viewer stays read-only everywhere. (The
  approval escalation in §7a.2 is *designation*-driven through the directory,
  exactly like today's chief resolution — it touches no `ROLE_CAPS`.)
* No new avatar *earning* mechanics beyond the existing wellness points; the
  species choice is cosmetic, growth stays derived.
* No photo moderation/cropping pipeline — same raw upload path the directory
  edit form already uses.
* Email/invite flow changes (pilot temp-password mode) — untouched.
