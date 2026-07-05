# Non-bureau RP-CSS navigation — implementation spec (recommendations 1 & 2)

**Status:** planned, not started. Deploy held.
**Why:** There is no working one-click path from a non-bureau ("outside" / invited)
activity to its resource-person CSS results. An outside event is **Form-3-only** (RP
reviews, no Form-2 event report), so the per-activity SERVQUAL report (`/reports/activities/{id}`)
404s for it. The only place its RP scores live is the **Resource Persons report**
(`/reports?type=3`) with the **Activity** filter (v1.65) — but nothing links there from
the activity. This spec covers the two small fixes that close that gap:

1. **Deep-link each invited activity to its RP results** from the `/activities/outside`
   page (and the outside Manage page).
2. **Fix the broken "View activity report" link** on the outside Manage page (it points
   at a route that 404s for outside events).

Scope note: recommendation #3 (a dedicated per-outside-activity results view) is OUT OF
SCOPE here — these two reuse the existing RP report.

---

## 1. The key mechanism (shared by both items)

The RP report's Activity filter (`reports(..., activity=...)`, [app.py](app.py)) matches
`activity` against each event's `build_events` id and narrows the atoms to that event's
`instance_ids`. The id it expects is **NOT** `event.id` — `build_events` sets:

    "id": min(all_ids)        # dashboard_insights.py:170 — lowest non-archived form-instance id

(Confirmed live: the June-17 outside event surfaced as `id=11570` = min of its forms.)

So the link target for any outside event is:

    /reports?type=3&activity=<min non-archived form_instance id of the event>

**Current bug:** the outside Manage page sets `report_url = f"/reports/activities/{ev['id']}"`
([app.py:4649](app.py)) — `ev['id']` is the **event-table** id (e.g. `3`), which never
equals a `build_events` id (a form id like `11570`), so the link 404s for **every** outside
event, F2-less or not.

### Shared helper
Add one small storage helper so both call sites compute the same id:

    # storage.py
    def event_rp_results_url(conn, event_id):
        """The Resource Persons report (Type-3) deep-linked to one event's activity,
        or None if the event has no non-archived RP forms with responses yet. The
        activity id is min(non-archived form_instance id) — the same representative id
        build_events assigns, which the report's Activity filter matches."""
        row = conn.execute(
            "SELECT MIN(fi.id) FROM event_form ef "
            "JOIN form_instance fi ON fi.id = ef.form_instance_id "
            "WHERE ef.event_id = ? AND COALESCE(fi.archived,0)=0", (event_id,)).fetchone()
        fid = row[0] if row else None
        return f"/reports?type=3&activity={fid}" if fid else None

Notes:
- Returns None when the event has no live RP forms → the caller hides the link (a
  0-response outside event isn't in `build_events`/`_rp_activity_options` anyway, so the
  filter wouldn't narrow — better to hide than link to an unfiltered report).
- `min(...)` matches `build_events` for the normal case (an event's forms form their own
  date+venue+organizer group). Edge case — if an event's forms were grouped with another
  event's under the same key — is pre-existing build_events behaviour, not introduced here.

---

## 2. Item 1 — deep-link invited activities to their RP results

### a) On the `/activities/outside` list
In `outside_events_index` ([app.py](app.py)), attach the results URL per event:

    for e in events:
        e["responses"] = st.event_response_total(conn, e["id"])
        e["rp_results_url"] = st.event_rp_results_url(conn, e["id"])

In `templates/outside_events.html`, add a third action link (next to Manage / Monitor),
shown only when present and there are responses:

    {% if e.rp_results_url and e.responses %}
      <a href="{{ e.rp_results_url }}">View resource-person results</a>
    {% endif %}

Effect: from the Invited-events page, one click goes from an activity to its RP scorecard —
turning the previously dead-end page into the start of the results path.

### b) On the outside Manage page
Covered by Item 2 below (same link), so the activity's own page also reaches its results.

---

## 3. Item 2 — fix the outside Manage "View activity report" link

In `_outside_manage_ctx` ([app.py:4620](app.py)), replace the 404-ing report_url:

    # was: "report_url": f"/reports/activities/{ev['id']}",
    "report_url": st.event_rp_results_url(conn, ev["id"]),

In `templates/outside_manage.html` (around line 87, the "View activity report →" button
and any other use of `report_url`):
- Relabel to **"View resource-person results →"** (accurate — an outside event has RP
  results, not a Form-2 event report).
- Guard it: `{% if report_url %}...{% endif %}` so a 0-response activity doesn't show a
  link that goes nowhere useful (show a muted "No responses yet" instead).

Effect: the manage page's results link works for the first time on outside events, and
points at the page that actually holds their scores.

---

## 4. Tests

New `tests/test_outside_rp_results_link.py`:
- `event_rp_results_url` returns `/reports?type=3&activity=<min fid>` for an outside event
  with two F3 forms (assert it's the min, and that archived forms are excluded from the min);
  returns None for an event with no live forms.
- `/activities/outside` renders a "resource-person results" link for an outside event that
  has responses, and omits it for one with none.
- Following that link (`GET /reports?type=3&activity=<id>`) returns 200 and the report is
  narrowed to that activity (respondent count matches the activity, not the whole bureau) —
  proves the id actually matches what the filter expects.
- The outside Manage page shows the results link (or the "No responses yet" note) instead of
  a `/reports/activities/<event.id>` URL.

Gate: full `pytest` + `qa_smoke`.

## 5. Rollout
- Build + verify locally, deploy held.
- Ship via `deploy_hf.py` (bump `APP_VERSION` + CHANGELOG, `pull_backup.py` first). No new
  top-level modules; changes are in `app.py`, `storage.py`, two templates, tests.

## 6. Out of scope
- Recommendation #3 — a dedicated per-outside-activity results page (RP scorecard + verbatims
  in one view). Bigger; revisit if the filtered RP report proves insufficient.
- The latent `activity.html` None-gap 500 (separate task `task_030d7c51`).
