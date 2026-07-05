# Outside (non-bureau) event visibility — implementation spec

**Status:** planned, not started. Deploy held.
**Owner:** avincentpatrick
**Why:** A non-bureau ("outside" / invited) event is findable while it is *upcoming* or
*ongoing*, then falls off every dashboard surface except `/reports/activities` once it
concludes. This is the root cause behind the "missing" June-17 PK reorientation activity
(data was always intact — see the 2026-06-25 investigation) and behind Spot Feedback
**#29** (recent-activities strip misses it) and **#30** (not shown in Monitor).

This is **not** a rebuild: outside events already flow through one canonical lifecycle
classifier (`lifecycle_of`) and a shared `list_events()`. The work is closing four
specific gaps.

---

## 1. The three activity shapes (context)

| Shape | `event_kind` | Has event record? | Forms | Created via |
|-------|--------------|-------------------|-------|-------------|
| Bureau event | `bureau` / NULL | yes | F2 review + N×F3 | link-tree registration flow |
| **Outside / invited event** | `'outside'` | yes | usually F3 only (no F2) | invited/external entry |
| Standalone F3 | — | **no** | F3 only | invited-speaker review |

The visibility logic keys off these differences, which is why outside + standalone fall
through inconsistently.

## 2. Gap analysis (current behaviour, with refs)

| Surface | Code | Rule | Outside event result |
|---------|------|------|----------------------|
| Monitor index | `app.py` `monitor_index` (~5283) → `st.list_events(lifecycles={"upcoming","ongoing"})` (`storage.py` ~1484) | already splits `outside_events` into their own section, **but** lifecycle-filtered | **Disappears once concluded** → #30 |
| Home "Recently concluded" | `app.py` `home()` (~2465), gate `if e.get("f2")` | F2-only | **Excluded** (outside is F3-only) → #29 |
| Home "Your recent activities" | `st.activities_by_creator(since_days=7)` (`storage.py` ~2616) | your account **and** ≤7 days | Catches it only if you made it AND within 7 days |
| Home "Upcoming" | `st.upcoming_events()` (`storage.py` ~2500) | `survey_type=2` only | Never (outside has no F2) |
| `/reports/activities` | `di.build_events()` | full canonical list | **Always present** (this is where it was found) |

**Net:** a concluded outside event has no stable home on the dashboard. The canonical
list (`build_events` / `/reports/activities`) is the only place it reliably lives.

Canonical lifecycle rule already exists — reuse it, don't reinvent:
`storage.py` `lifecycle_of(event_date, close_at, today, now, end_date)` (~2472):
- **upcoming** — start day in the future (registration phase)
- **ongoing** — started and CSS window still open
- **concluded** — past, window closed (blank date ⇒ concluded)

---

## 3. Design

Give outside events a **permanent address** and make the existing recent/concluded feeds
**kind-agnostic**, so the same event shows consistently everywhere instead of being
dropped by per-feed rules.

Three layers, smallest/highest-leverage first. ① stands alone and delivers the core win.

### Layer ① — Dedicated "Invited / outside events" page  *(do first)*

A single page that lists **all** outside events across **every** lifecycle.

**Route:** `GET /activities/outside` (`app.py`)
- Auth: same rule as the monitor/activities pages — admin sees all; section_manager sees
  only `created_by == username`. Reuse the `owner = None if admin else username` pattern
  from `monitor_index`.
- Data: `st.list_events(conn, created_by=owner, lifecycles=None)` (no lifecycle filter),
  then `[e for e in all if e.get("event_kind") == "outside"]`, newest first. Attach
  `responses = st.event_response_total(conn, e["id"])` per row (same as `monitor_index`
  already does for its outside section).
- Each row shows: title, date, venue/modality, lifecycle badge (upcoming/ongoing/
  concluded), response total, and links to **Report** (`/reports/activities/<id>`),
  **Manage** (`/activities/<token>/manage`), and **Monitor** (if upcoming/ongoing).

**Template:** new `templates/outside_events.html` — model on existing
`templates/monitor_outside.html` / `templates/outside_manage.html`. Full-width `.lede`
description (per the page-alignment standing rule).

**Discoverability:**
- Add a nav entry in `NAV_GROUPS` (`app.py`) — single source for the nav menu **and** the
  Ctrl-K search index, so the page becomes searchable for free (role-filtered).
- Add a card/link on the Monitor index: "View all invited events →".

**Effect:** every non-bureau event has one stable place regardless of age. Solves the core
"I can't find it" on its own. Touches no existing feed logic ⇒ lowest risk.

### Layer ② — Fold outside/F3 into home "Recently concluded"

In `home()` (`app.py` ~2465), the `concluded` list comprehension gates on `e.get("f2")`.
Relax it so outside events and standalone F3 activities also qualify when they have
responses in the window.

- Change the predicate from `if e.get("f2")` to include outside/F3 rows (they already
  carry `respondents` from `build_events`). Keep the 90-day window + client-side
  7/30/90 slice.
- Render: reuse the existing concluded-card markup; show response count (no registration
  funnel for outside).

**Effect:** a recently concluded outside event appears on the home strip like any bureau
event. Fixes #29.

### Layer ③ — Don't let them vanish from Monitor at conclusion

In `monitor_index` (`app.py` ~5300), concluded outside events drop because of the
`lifecycles={"upcoming","ongoing"}` filter. Two options (pick one):
- **3a (preferred):** keep the strict upcoming/ongoing roster, but add a footer link on
  the outside section — "Concluded invited events → /activities/outside" — so they hand
  off cleanly to Layer ①.
- **3b:** include outside events concluded within a short window (e.g. 14 days) in the
  monitor's outside section, flagged "concluded".

**Effect:** outside events stop silently disappearing from Monitor. Fixes #30.

### Consistency fix — align the "recent" window

"Your recent activities" uses **7 days** (`since_days=7`) while "Recently concluded" uses
**90**. Seven days is too short for invited events processed later. Align both on one
window — **suggest 30 days** as the default, keeping the existing 7/30/90 client-side
toggle. (One-line change to the `since_days` arg in `home()`.)

### Optional polish — "Invited event" badge

Ensure an **"Invited event"** badge renders wherever outside rows appear (home feeds,
monitor, the new page), mirroring the existing **"Online"** badge pattern (see the
modality-badge convention). Makes non-bureau events visually distinct from bureau ones.

---

## 4. Build order & scope

1. **Layer ①** — new route + template + nav entry. Self-contained; ship-ready alone.
2. **Layer ②** — home concluded predicate + window alignment.
3. **Layer ③** — monitor hand-off link (3a).
4. Badge polish — when touched.

Each layer is independently deployable. ① is the recommended first (and possibly only)
deploy if you want the minimal change.

## 5. Testing

- **Unit:** none of the lifecycle math changes (reusing `lifecycle_of`), so no new pure-fn
  tests required. Add a route test for `/activities/outside`: an outside event in each
  lifecycle (upcoming/ongoing/concluded) all appear; a bureau event does **not**; auth —
  a section_manager sees only their own.
- **Layer ② test:** a concluded outside event within the window appears in the home
  `concluded` payload; outside the window it does not.
- **Manual (local, forged admin cookie via `auth.make_token`):** create/seed one outside
  event per lifecycle, confirm each is reachable from the new page, home strip, monitor,
  and search palette.
- Gate before declaring done: full `pytest` + `qa_smoke` (rerun `test_registration_dedup`
  before blaming a change — it is flaky).

## 6. Rollout

- Build + verify locally with the **deploy held** (per the current batched/held posture).
- When ready: `python deploy_hf.py` (HF-only), bump `APP_VERSION` + prepend a plain-language
  CHANGELOG entry (the deploy script enforces this). Back up first (`pull_backup.py`).
- New top-level modules (none expected here) would need adding to `RUNTIME_PY` in
  `deploy_hf.py` — not applicable if this stays within `app.py` / `storage.py` / templates.

## 7. Out of scope (explicitly)

- The broader recent/upcoming/ongoing *delineation* rework across all four home feeds
  (the bigger structural item). This spec deliberately targets **outside-event visibility**
  only; the consistency fix above is the one piece of delineation worth doing alongside it.
- Mobile activities-list fix (#35) — related symptom, separate change.
