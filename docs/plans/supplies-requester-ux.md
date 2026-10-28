# Supplies — requester UX plan

Goal: someone who only *requests* supplies should see two things — **Request** and **My requests** —
and be able to pick items visually (Foodpanda/Grab style) and follow their request at a glance.

Approvers, custodians, auditors and admins keep today's screens unchanged.

## Ground rules for every increment

- **One increment = one branch = one PR.** Do them in order; each assumes the previous one is merged.
- **UI only unless the increment says otherwise.** Do not change approval states, stock rules,
  permissions, revision checks or `operation_key` idempotency in `supplies_requests.py`,
  `supplies_approvals.py`, `supplies_stock.py`, `supplies_permissions.py`.
- **Hiding a link is not a permission change.** Direct URLs keep the access they have today.
- **"Requester-only"** means: no `request_approver` grant, not custodian, not auditor, not
  replenishment approver, not admin. Defined once in increment 1.1 and reused.
- Before pushing: `python3 -m pytest tests/test_supplies*.py -q`, then `bash run_tests.sh`.
- Bump `APP_VERSION` and prepend a plain-language entry, following the header of `version.py`.
  The CI release gate (`python scripts/check_release.py release --base <main sha>`) also requires
  the first `CHANGELOG.md` heading and `CACHE_VERSION` in `static/js/sw.js` (`v<version>-a`) to match.
  Merge the latest `main` first so the bump is above whatever version main is on.
- Add or extend tests in the matching `tests/test_supplies_*.py`; reuse the fixtures in
  `tests/test_supplies.py` (`supplies_db`, `setup_catalog`, `create`) and `tests/test_supplies_requests.py`
  (`request_db`, `draft`).
- Mobile first: check every new page at 375px wide (pattern: `tests/test_supplies_grid_browser.py`).
- Keep the existing no-JavaScript fallback working; JS only enhances.

---

## Phase 1 — Simplify for requesters (no database change)

### 1.1 Requester-only navigation
- `supplies_routes.py` `render()`: add `requester_only` to the template context, computed from the
  flags already there (`not (can_approve or can_maintain or can_audit or can_replenish_approve or can_configure)`).
- `templates/supplies/base.html`: when `requester_only`, show only **Home · Request supplies · My requests · My releases**.
- Tests: requester `GET /supplies` has no "Stock dashboard"/"Awaiting stock" links; a custodian still
  sees them; requester `GET /supplies/items` still returns 200 (no permission change).

### 1.2 Plain-language status helper (pure Python)
- New `supplies_status.py` with `requester_stage(entry) -> dict(step, total_steps, label, tone, sentence)`.
- Steps: **Sent → Approved → Ready for pickup → Received**. Exceptions: Not sent yet (draft),
  Needs your changes (returned), Not approved (rejected), Withdrawn (cancelled), Waiting for stock
  (approved, outstanding, nothing reserved).
- Inputs come from what `supplies_dashboard.queue()` / `supplies_requests.get_request()` already
  return (`approval_status`, `reserved_quantity`, `outstanding_quantity`, releases and their
  `acknowledgment_status`). Investigate where release acknowledgment is available on list rows
  before coding; if it is missing, add it to the query in `supplies_dashboard.py` read-only.
- Sentence reuses `next_action` approver names: e.g. "Waiting for Juan Dela Cruz to approve."
- Unit tests for every state in a new `tests/test_supplies_status.py`.

### 1.3 Status stepper component
- New partial `templates/supplies/_status_stepper.html` + CSS in `static/css/supplies.css`
  (horizontal on desktop, compact on phone, colour + text so it is not colour-only).
- Use it on `requests.html` (replace the table with cards for requester-only; keep the table for others)
  and in the recent-requests list on `dashboard.html`.

### 1.4 Requester home
- `dashboard.html`, when `requester_only`: big **Request supplies** button, a **Needs your action**
  banner (drafts, returned requests, releases waiting for acknowledgment — counts already exist in
  `supplies_dashboard.dashboard()`), then recent requests with the stepper. Hide the role cards.

### 1.5 Simpler request detail for the owner
- `request.html`, when the viewer is the owner and cannot decide/issue: top summary card with
  the stepper, the sentence, and one line per item: "Bond paper, A4 · asked 3 · received 2 ream".
- Move the 11-column table, revision history and timeline into a **Full details** `<details>`.
- Rename timeline actions that still print raw names (fallback `{{ event.action }}`) to plain words.
- Approver and custodian view: unchanged (assert in a test).

## Phase 2 — Faster requesting (no database change)

### 2.1 One-step "Send request"
- Form gets two buttons: primary **Send request** and secondary **Save as draft**.
- Send = existing `save_draft` then `submit` in one POST. Investigate how `operation_key` is
  validated and recorded in `supply_operation` first: each operation needs its own key — post two
  hidden keys (`operation_key`, `submit_operation_key`), do not reuse one.
- If save succeeds but submit fails, redirect to the draft with the error shown (draft is not lost).
- Tests: send creates a submitted request with a control number; double-post is idempotent;
  submit failure leaves a draft.

### 2.2 Reorder and rewrite the classic form
- Items first, then purpose and date needed. Purpose placeholder with examples
  ("For the Oct 30 training, 25 participants").
- Replace jargon sentences with plain ones; keep labels accessible.

### 2.3 "Request again"
- On a past request (any final state), a **Request again** link opens a new draft form pre-filled with
  the same items and quantities (inactive items dropped with a note). No new service function needed:
  pre-fill via `form_values` in `request_form()`.

## Phase 3 — Visual catalog with photos (database change)

### 3.1 Item photos (storage + custodian upload)
- `supplies_storage.py` schema setup: add `photo BLOB` and `photo_mime TEXT` to `supply_item` using
  the existing `PRAGMA table_info` + `ALTER TABLE` pattern (see lines ~248, ~608).
- **Never `SELECT *` from `supply_item` in list/report/export queries after this** — audit
  `supplies_reports.py`, `supplies_import*.py`, `supplies_grid.py`, `supplies_stock_dashboard.py`,
  `mcp_*supply*` and backups for `SELECT *` or `item.*` and list columns explicitly.
- `GET /supplies/items/{id}/photo` (signed-in users only, `Cache-Control` with revision-based ETag).
- Custodian upload/remove on `item.html`: PNG/JPEG/WebP, ≤512 KB, verify magic bytes, bump item
  `revision` and record a `supply_event` like other item edits. Follow `_decode_photo` in `app.py`
  and `storage.set_user_photo`.
- Tests: upload, wrong type, too large, non-custodian denied, list queries don't load blobs.

### 3.2 Availability badge for requesters
- Pure function: **Available / Limited / Out of stock** from the existing availability warning data
  (`item.warning`). Requesters see the badge only, never on-hand numbers *(default — see open decisions)*.

### 3.3 Browse grid (works without JS)
- `GET /supplies/requests/new` for requester-only renders a card grid: photo (or generic icon),
  description, unit, badge, quantity input named `qty_<item_id>`. Search box reuses the catalog `q`.
  Classic form stays reachable via "Use list form".
- JS enhancement (`static/js/supplies-shop.js`): +/− stepper, sticky bottom bar
  "3 items · Review request". No JS → plain number inputs and a submit button.

### 3.4 Cart review and send
- POST grid → review page: chosen items (thumbnails, editable quantities), purpose, date needed,
  **Send request** (reuses 2.1) and **Save as draft**. Map `qty_<id>` to the existing `lines` shape;
  enforce `MAX_LINES` (20) with a friendly message.

### 3.5 Categories (only if approved — see open decisions)
- `category TEXT` on `supply_item`, custodian field, filter chips on the grid; workbook import column.

## Phase 4 — Polish
- Playwright screenshots at 375px and 1280px for home, grid, review, list, detail; fix overflow.
- Keyboard/screen-reader pass on the stepper and the quantity stepper.
- Optional: a short guided tour in `tours.py` for first-time requesters.

---

## Open decisions (owner to confirm before the affected increment)

| Decision | Default if not answered | Blocks |
|---|---|---|
| Can requesters see stock numbers? | No — badge only | 3.2 |
| Add item categories? | Not yet | 3.5 |
| Who uploads photos? | Custodians | 3.1 |
