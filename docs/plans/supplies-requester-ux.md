# Supplies — requester UX plan

Goal: someone who only *requests* supplies sees two things — **Request supplies** and **My requests** —
picks items visually (Foodpanda/Grab style) without being able to ask for more than is available,
and follows each request at a glance until they confirm they received it.

Approvers, custodians, auditors and admins keep today's management screens. They also get the new
request flow when *they* request supplies.

## Decisions (confirmed by the owner, Oct 28 2026)

| Topic | Decision |
|---|---|
| Stock numbers | Requesters see a badge only (**Available / Limited / Out of stock**), never quantities |
| Quantity limit | Requesters **cannot request more than is available to request** (rule R1 below) |
| Categories | Not now |
| Item pictures | Generated automatically from the item name (simple illustrations); no uploads needed |

## User stories (requester)

| # | As a requester I want to… | So that… | Increment |
|---|---|---|---|
| US1 | find an item by picture and name | I don't scroll a long code list | 2.1 |
| US2 | add a quantity and be stopped at what's available | I don't ask for what can't be given | 1.3, 2.1 |
| US3 | review my cart and send it in one tap | requesting takes under a minute | 2.2 |
| US4 | see at a glance where each request is and who has it | I don't have to chase people | 3.1, 3.2 |
| US5 | know when it's ready to pick up | I go to the stockroom once | 1.2, 3.2 |
| US6 | confirm I received it, or report a problem, in one tap | the record closes without paperwork | 3.3 |
| US7 | fix a returned request in the same cart view | corrections are easy | 2.3 |
| US8 | withdraw a request I no longer need | stock isn't held for nothing | 3.2 |
| US9 | repeat a past request | regular orders are quick | 2.3 |
| US10 | print the official request form when asked | I still have the paper copy | 3.2 |

## Page inventory for a requester-only user (checked Oct 28 2026)

Requester-only = no `request_approver` grant, not custodian, not auditor, not replenishment
approver, not admin. All other pages already return 403 for them.

| Page today | Shows | After this plan |
|---|---|---|
| `/supplies` Overview | Role cards, jargon | **Redesign** → Supplies home (3.4) |
| `/supplies/requests/new`, `/{id}/edit` | 20 dropdown lines | **Replace** → picture grid + cart (2.1–2.3) |
| `/supplies/requests` My requests | Table | **Redesign** → cards with progress tracker (3.1) |
| `/supplies/requests/{id}` | 11-column table, timeline | **Redesign** → tracker + "Full details" (3.2) |
| `/supplies/requests/{id}/print` | Official form | **Keep**, linked from tracker |
| `/supplies/issues` Releases | List | **Fold into My requests**; redirect (4.1) |
| `/supplies/issues/{id}` | Release + acknowledgment form | **Simplify** for recipient: two buttons (3.3) |
| `/supplies/awaiting-stock` | Backorder lines | **Fold into tracker** ("Waiting for stock"); redirect (4.1) |
| `/supplies/items`, `/items/{id}` | Stock numbers, thresholds | **Redirect** to the picture grid (4.1) |
| `/supplies/stock-dashboard` (+ `inventory-data`, `inventory-export.csv`, `presentation-data`) | Stock numbers | **Stock readers only** (4.2) |

Requester navigation ends up as: **Home · Request supplies · My requests**.

## Rule R1 — "available to request"

`available` today (`supplies_allocations.availability`) = on hand − reserved for approved requests.
Submitted-but-undecided requests reserve nothing, so on its own it would let two people each claim
the same last units. Use:

```
requestable(item, excluding_request) =
    on_hand − reserved − Σ requested_quantity of OTHER requests in status 'submitted'
    (never below 0)
```

- Enforced **in the service layer** (`supplies_requests.save_draft` and `submit`), so the web form,
  the new grid, and the MCP paths (`mcp_supply_drafts.py`, `mcp_supply_submissions.py`) all obey it.
- Checked again on submit and on resubmitting a returned request; quantities may have changed since save.
- Items with no stock recorded are requestable 0 → "Out of stock".
- It is a request-time limit, not a reservation. Approval and the existing reservation/backorder flow
  are unchanged and still handle edge cases (e.g. a physical-count adjustment after submission).
- Badge: Out of stock = 0 · Limited = 1 … `critical_level` (or ≤ 20% of `target_level` when critical is 0) · Available otherwise.
- Error text: "Only 4 reams of Bond paper, A4 can be requested right now."

## Ground rules for every increment

- **One increment = one branch = one PR**, in order; each assumes the previous one is merged.
- Only increments that say so may change business rules or permissions (1.3 and 4.2).
  Do not touch approval states, reservations, revision checks or `operation_key` idempotency.
- Run `python3 -m pytest tests/test_supplies*.py tests/test_mcp_supply*.py -q`, then `bash run_tests.sh`.
- Version bump on every PR: `APP_VERSION` + plain-language entry in `version.py` (see its header),
  first heading of `CHANGELOG.md`, and `CACHE_VERSION = "v<version>-a"` in `static/js/sw.js`.
  Merge the latest `main` first. Check with `python scripts/check_release.py release --base <main sha>`.
- Tests reuse fixtures: `supplies_db`, `setup_catalog`, `create` (`tests/test_supplies.py`),
  `request_db`, `draft` (`tests/test_supplies_requests.py`). Log in via `tests.conftest.session_token`.
- Mobile first: check new pages at 375px (pattern: `tests/test_supplies_grid_browser.py`).
- Pages must work without JavaScript; JS only enhances (steppers, sticky cart bar).
- Plain words everywhere a requester looks: no "reserved", "outstanding", "revision", "snapshot", "issuance".

---

## Phase 1 — Foundations (little or no visible change)

### 1.1 Requester-only flag and navigation
- `supplies_routes.py` `render()`: add `requester_only` to the context, computed from the existing flags.
- `templates/supplies/base.html`: when `requester_only`, nav = **Home · Request supplies · My requests**.
- Tests: requester sees exactly those three links; a custodian's nav is unchanged.

### 1.2 Plain-language status helper
- New `supplies_status.py`: `requester_stage(entry) -> {step, label, tone, sentence, action}`.
- Tracker steps: **Sent → Approved → Ready for pickup → Received**.
  Exceptions: Not sent yet (draft) · Needs your changes (returned) · Not approved (rejected) ·
  Withdrawn (cancelled) · Waiting for stock (approved, outstanding, nothing reserved) ·
  Please confirm receipt (released, acknowledgment pending) · Problem reported (disputed).
- Sentence names the next person using the approver names in `supplies_dashboard._next_action`.
- If list rows lack release/acknowledgment data, add it read-only to `supplies_dashboard.queue()`.
- Unit tests for every state: `tests/test_supplies_status.py`.

### 1.3 Rule R1: requestable quantity *(business rule change)*
- `supplies_allocations.py`: `requestable(conn, item_id, exclude_request_id=None)` and
  `badge(requestable, item)`.
- Enforce in `supplies_requests.save_draft` and `submit`. Raise `Invalid` with the plain message.
- Tests: over-limit save/submit rejected; own draft excluded from the pending sum; other pending
  submissions counted; resubmit re-checked; MCP draft/submit paths rejected too; zero-stock item.

### 1.4 Item pictures generated from the name
- `static/img/supplies/` set of ~40 simple flat SVG illustrations in one consistent style:
  bond paper, specialty paper, notebook, sticky notes, envelope, folder, expanding file, ballpen,
  sign pen, pencil, marker, highlighter, whiteboard marker, eraser, correction tape, ruler, scissors,
  cutter, stapler, staple wire, paper clip, binder clip, fastener, puncher, glue, tape, packaging tape,
  rubber band, ink bottle, toner, ink cartridge, battery, USB drive, mouse, calculator, alcohol,
  tissue, hand soap, trash bag, cleaning cloth, plus a generic box.
- `supplies_pictures.py`: `picture_for(description, code) -> static path`, keyword rules (English and
  common local terms, e.g. "ballpen", "bond", "fastener", "tisyu"), first match wins; fallback is a
  coloured tile with the item's initials (colour hashed from the code).
- No database change. Later, a custodian override can be added if wanted.
- Tests: sample names map to the expected picture; unknown names fall back.
- Tune keywords against the real catalog: the owner exports the item list (Supply catalog → CSV)
  and the keywords are adjusted so most items get a real picture.

## Phase 2 — Requesting

### 2.1 Picture grid ("shop")
- `GET /supplies/requests/new` renders a grid for **everyone** who can request
  (classic form kept at `?view=list` for one release, then removed).
- Card: picture, description, unit, badge, quantity input `qty_<item_id>` with
  `max = requestable` and disabled when Out of stock. Search box (`q`) on top.
- `static/js/supplies-shop.js`: +/− stepper, sticky bottom bar "3 items · Review".
- Server still enforces R1 (the `max` attribute is only a convenience).

### 2.2 Cart review and one-step send
- POST grid → review page: thumbnails, editable quantities, purpose (placeholder example),
  date needed, **Send request** (primary) and **Save for later** (secondary).
- Send = `save_draft` then `submit` in one POST with **two** operation keys
  (`operation_key`, `submit_operation_key`). Check how `supply_operation` records keys first.
- If submit fails after save, show the draft with the error; nothing is lost.
- Map `qty_<id>` to the existing `lines` shape; respect `MAX_LINES` (20).
- Tests: send → submitted with control number; double POST idempotent; R1 error shown on the cart.

### 2.3 Edit, fix and repeat in the cart
- Drafts and returned requests open in the cart view with the approver's reason shown on top.
- **Request again** on any past request opens a cart with the same items, capped to what is
  requestable now and dropping inactive items with a note.

## Phase 3 — Monitoring

### 3.1 My requests
- Cards: control number, first item names with pictures, progress tracker, one sentence, date.
- **Needs your action** section first: drafts, returned, waiting for your receipt confirmation.
- Filters reduced to: Active · Completed · All.

### 3.2 Request tracker (owner view of `/supplies/requests/{id}`)
- Top: tracker, sentence ("Waiting for Maria Santos to approve"), items as
  "Bond paper, A4 · asked 3 · approved 3 · received 2 reams".
- Actions in context only: Fix and resend (returned) · Withdraw (before approval) ·
  Confirm receipt (released) · Print form · Request again.
- **Full details** `<details>`: the existing table, revisions, timeline (all event names in plain words).
- Approver/custodian view of the same URL: unchanged (assert in a test).

### 3.3 One-tap receipt confirmation
- On the tracker and on `/supplies/issues/{id}` for the recipient: **Yes, I received it** and
  **Report a problem** (opens a note box). Reuse the existing acknowledge endpoint and fields.
- Custodian controls on the release page stay as they are.

### 3.4 Supplies home
- Big **Request supplies** button, **Needs your action**, the three latest requests with trackers,
  link to My requests. Role cards remain for management users only.

## Phase 4 — Close the side doors

### 4.1 Redirect requester-only users from management pages
- `/supplies/items` and `/supplies/items/{id}` → picture grid (search term carried over).
- `/supplies/issues` → My requests. `/supplies/awaiting-stock` → My requests (filter Active).
- Release detail links from emails keep working (3.3).

### 4.2 Stock numbers for stock readers only *(permission change)*
- `/supplies/stock-dashboard`, `/supplies/inventory-data`, `/supplies/inventory-export.csv`,
  `/supplies/stock-dashboard/presentation-data`: require custodian/auditor (or approver if the
  owner wants approvers to keep it). Requesters get 403 or a redirect to the grid.
- Check emails, MCP reads (`mcp_read.py`) and tours for links or data that expose quantities to requesters.

## Phase 5 — Polish
- Playwright screenshots at 375px and 1280px: home, grid, cart, my requests, tracker, receipt.
- Keyboard and screen-reader pass (stepper buttons labelled, tracker readable as text).
- Optional first-time tour in `tours.py`.

## Still to confirm before 4.2
- Should approvers keep the stock dashboard? Default: yes (they need it to decide), requesters no.
