# Custom registration questions — implementation spec

**Status:** planned, not started.
**Owner:** avincentpatrick
**Why:** The public pre-registration form (`/e/<token>`) asks only fixed questions:
title, name, email, contact, sex, affiliation and consent. Organizers need to add
their own questions to an activity, such as food restrictions or arrival details,
and then read the answers on the roster and in the export.

**Decisions taken:**
- Questions belong to one activity. There are no reusable question sets yet; one-click presets cover the common cases.
- Questions are configured on the **manage page** only (`/activities/<token>/manage`), not on `/create`.
- There are no file uploads.
- Outside ("invited") activities have no registration, so they get nothing. Their manage page is `outside_manage.html`, which this spec does not touch.

Ship in **two PRs**, in this order. Each PR runs `bash run_tests.sh` green before it is pushed.

---

## 0. Facts about the codebase (read before coding)

| What | Where |
|---|---|
| Stack | FastAPI + Jinja2 + raw `sqlite3`. No ORM. Forms are parsed by hand with `parse_qsl`. |
| Schema | `storage.init_db` (storage.py:55) calls `_add_missing_columns` (storage.py:548). New tables go there as `CREATE TABLE IF NOT EXISTS`, next to `event_link` (~storage.py:852). |
| Foreign keys | **`PRAGMA foreign_keys = ON`** (storage.py:42). Deleting an `attendee` that still has `attendee_answer` rows **will fail**. See §PR-B 4. |
| Registration submit | `event_consent`, `POST /e/{token}` (app.py:~7884). It builds `posted = {k: v for k, v in pairs}`, which **collapses repeated keys**, so multi-select needs `pairs`. |
| Registration storage | `add_attendee` / `update_attendee` / `register_attendee` (storage.py:1924-2008) |
| Public page render | `_event_view` (app.py:~7729), template `templates/link_tree.html`. The form is at lines ~172-226, and the "Is this you?" confirm form with hidden fields is at ~150-165. |
| Consent text | `CONSENT_TEXT` (app.py:417) and `i18n.CONSENT_TMPL_FIL` (app.py:426). It currently says "We collect your name, email, and (optionally) contact number only…". |
| Client validation | `static/js/app.js:277`. Any `input[type=checkbox][required]` must be ticked, so **never put `required` on multi-select checkboxes**. |
| Manage page | `activity_manage` (app.py:8145), `_manage_ctx` (app.py:8051), `templates/activity_manage.html`. Cards are `<div class="mcard" id="...">`, and "Activity dates" (~line 469) is a good model. |
| Manage POST pattern | `activity_messages_save` (app.py:8278): `_posted(request)`, then `st.get_event`, then `_can_manage_event(request.state.user, ev)`, then `_audit(...)`, then a redirect |
| Roster | `monitor_event` (app.py:9073), `templates/monitor_event.html` (the row loop is at ~153), `st.event_attendees_status` (storage.py:2161) |
| Export | `_build_monitor_xlsx` (app.py:~9490). **`end_column=8` and `"ABCDEFGH"` are hardcoded** in several places. |
| Attendee delete | `st.delete_attendee_entry` (storage.py:2094) |
| Retention purge | `st.purge_expired_attendees` (storage.py:2124), called by `retention.py` |
| Duplicate merge script | `merge_duplicate_attendees.py:58-65` deletes attendee rows |
| Tests | Model new tests on `tests/test_registration_dedup.py`: storage tests on `tmp_path` via `_fresh()`/`_event()`, and route tests with the `client` / `manager` / `db_path` fixtures and `_make_event()`. |
| Release convention | Bump `APP_VERSION` in `version.py` and add a plain-language entry at the top of its `CHANGELOG` list. Also add a developer entry at the top of `CHANGELOG.md` with the same date and version format as existing entries. |

---

## PR-A — schema, manage card, public form, saving answers

### A1. New module `reg_questions.py` (pure logic, no DB, no FastAPI)

Keep every rule here so it can be unit-tested without HTTP.

```python
KINDS = {            # kind -> admin-facing label
    "text": "Short answer",
    "longtext": "Paragraph",
    "single": "Choose one",
    "multi": "Choose any (checkboxes)",
    "yesno": "Yes / No",
    "date": "Date",
    "time": "Time",
}
CHOICE_KINDS = {"single", "multi"}
MAX_QUESTIONS = 20
MAX_LABEL = 200
MAX_HELP = 300
MAX_OPTIONS = 30
MAX_OPTION_LEN = 120
MAX_ANSWER = 1000   # longtext; 200 for text

PRESETS = {  # key -> list of question dicts (label, kind, options, required, help_text)
    "food": [
        {"label": "Food restrictions", "kind": "multi",
         "options": ["None", "Vegetarian", "Vegan", "Halal", "No pork", "No seafood", "Food allergy"],
         "required": True},
        {"label": "If you have a food allergy or other restriction, please specify",
         "kind": "text", "required": False},
    ],
    "arrival": [
        {"label": "Arrival date", "kind": "date", "required": False},
        {"label": "Estimated arrival time", "kind": "time", "required": False},
        {"label": "Mode of travel", "kind": "single",
         "options": ["Air", "Land", "Sea", "Already in the area"], "required": False},
    ],
    "accommodation": [
        {"label": "Do you need accommodation?", "kind": "yesno", "required": True},
    ],
    "shirt": [
        {"label": "Shirt size", "kind": "single",
         "options": ["XS", "S", "M", "L", "XL", "2XL", "3XL"], "required": False},
    ],
    "emergency": [
        {"label": "Emergency contact person and number", "kind": "text", "required": False},
    ],
}
PRESET_LABELS = {"food": "Food restrictions", "arrival": "Arrival details",
                 "accommodation": "Accommodation", "shirt": "Shirt size",
                 "emergency": "Emergency contact"}

def parse_options(text: str) -> list[str]
    # One option per line. Strip and drop blanks, dedupe case-insensitively while
    # keeping the first spelling, cap at MAX_OPTIONS, and truncate each to MAX_OPTION_LEN.

def clean_question(posted: dict) -> tuple[dict | None, str | None]
    # Returns (q, None) or (None, error_code).
    # q = {label, help_text, kind, options(list), required(bool)}.
    # Errors: "label" (blank), "kind" (not in KINDS), "options" (a choice kind with
    # fewer than 2 options). Non-choice kinds always get options = [].

def field_name(qid: int) -> str: return f"q_{qid}"

def collect_answers(questions: list[dict], pairs: list[tuple[str, str]]) -> tuple[dict, list[str]]
    # questions are the active questions from storage. Returns ({qid: stored_value}, errors).
    # For each q, gather all values posted under field_name(q["id"]):
    #   text/longtext: first value, stripped, truncated (200 / MAX_ANSWER)
    #   single: must be exactly one of q["options"], else treat as blank
    #   multi:  keep only values that are in q["options"], in options order;
    #           store as json.dumps(list), or blank if none
    #   yesno:  "Yes" or "No" only
    #   date:   must match ^\d{4}-\d{2}-\d{2}$ and parse with date.fromisoformat
    #   time:   must match ^\d{2}:\d{2}$
    # If q["required"] and the result is blank, append f'Please answer “{q["label"]}”.'
    # Blank optional answers are omitted from the dict.

def display_value(q: dict, raw: str | None) -> str
    # For the roster and export. multi: json.loads, then ", ".join, falling back to raw
    # on error. date/time/others: raw. None or "" -> "".

def tally(questions, answers_by_attendee) -> list[dict]
    # PR-B only: per single/multi/yesno question, [{"label", "counts": [(option, n), ...]}].
```

**Why server-side whitelisting:** the endpoint is public. A forged POST must not
be able to store arbitrary text in a choice field. The existing `_HONORIFICS`
check follows the same rule.

### A2. Schema (`storage._add_missing_columns`, next to `event_link`)

```sql
CREATE TABLE IF NOT EXISTS event_question (
    id           INTEGER PRIMARY KEY,
    event_id     INTEGER NOT NULL REFERENCES event(id),
    label        TEXT NOT NULL,
    help_text    TEXT,
    kind         TEXT NOT NULL,          -- reg_questions.KINDS
    options_json TEXT,                   -- JSON list for single/multi, else NULL
    required     INTEGER NOT NULL DEFAULT 0,
    ordinal      INTEGER NOT NULL DEFAULT 0,
    archived_at  TEXT,                   -- set instead of deleting once answered
    created_by   TEXT,
    created_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_question_event ON event_question(event_id);

CREATE TABLE IF NOT EXISTS attendee_answer (
    id          INTEGER PRIMARY KEY,
    attendee_id INTEGER NOT NULL REFERENCES attendee(id),
    question_id INTEGER NOT NULL REFERENCES event_question(id),
    value       TEXT,                    -- PII-adjacent (health/diet); deleted on purge
    updated_at  TEXT,
    UNIQUE(attendee_id, question_id)
);
```

Add a comment in the house style above the block explaining what the tables are
for and that answers are deleted by the retention purge.

### A3. Storage functions (storage.py, new section after `register_attendee`)

All writes `conn.commit()`, as the neighbouring functions do. Rows are returned as dicts.

- `list_event_questions(conn, event_id, include_archived=False)`
  - Returns `[{id, label, help_text, kind, options (list), required (bool), ordinal, archived_at, n_answers}]`, ordered by `ordinal, id`.
  - `n_answers` is a `COUNT` from `attendee_answer`. The manage page uses it to lock the kind.
- `get_event_question(conn, event_id, qid)`
  - Returns the dict, or None when `qid` is not **this event's**. This is the IDOR guard; every route uses it.
- `add_event_question(conn, event_id, q, created_by=None)`
  - `ordinal = COALESCE(MAX(ordinal), 0) + 1`.
  - Returns the new id, or None if the event already has `MAX_QUESTIONS` active questions.
- `update_event_question(conn, qid, q)`
  - Updates label, help_text, required and options.
  - Changes `kind` **only if `n_answers == 0`**. Otherwise it keeps the stored kind.
- `remove_event_question(conn, qid)`
  - Hard `DELETE` if `n_answers == 0`; otherwise sets `archived_at = now`.
  - Returns `"deleted"` or `"archived"`.
- `move_event_question(conn, event_id, qid, direction)`
  - `direction` is `"up"` or `"down"`. Swap `ordinal` with the neighbouring active question; do nothing at either end.
- `save_attendee_answers(conn, attendee_id, values: dict)`
  - Upsert with `INSERT ... ON CONFLICT(attendee_id, question_id) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at`.
  - Only the keys present in `values` are written. Blank answers are not in the dict, so a resubmission never wipes an earlier answer, matching `update_attendee`.
- `get_attendee_answers(conn, attendee_id) -> {qid: value}`
- `event_answers(conn, event_id) -> {attendee_id: {qid: value}}`. One query joining `attendee`, filtered by `event_id`. This is for PR-B, but add it now.

### A4. Manage page card (`templates/activity_manage.html` + routes)

**Context:** in `_manage_ctx` add the following:
- `"questions": st.list_event_questions(conn, ev["id"])`
- `"q_kinds": rq.KINDS`
- `"q_presets": rq.PRESET_LABELS`
- `"q_max": rq.MAX_QUESTIONS`

Also pass `qok` / `qerr` query params through `activity_manage` into ctx, as `dateok` / `err` already are.

**Card:** add a new `<div class="mcard" id="questions">` titled **"Registration questions"**, placed directly after "The participant page" card (~line 112). It contains:
1. **Hint text:** "Extra questions participants answer when they register, e.g. food restrictions or arrival. The standard questions (name, email, sex, affiliation) are always asked."
2. **Preset buttons:** one small `<form method="post" action="/activities/{{token}}/questions/preset">` per preset, with `name="preset"` holding the key. Hide a preset button if a question with the same first label already exists.
3. **List of existing questions:** for each one, show the label, kind label, "Required"/"Optional" badge, the options joined by " · ", and the answer count. Each row has:
   - ↑ / ↓ buttons: tiny forms posting to `/questions/{id}/move` with `direction`.
   - An "Edit" toggle using `<details>`. It contains a form with the same fields as the add form, posting to `/questions/{id}`. When `n_answers > 0`, render the kind `<select disabled>` with the note "Type is locked because people have answered."
   - A "Remove" form posting to `/questions/{id}/remove`, with `onsubmit="return confirm(...)"`. If `n_answers > 0`, the confirm text says the question will be hidden from the form but existing answers are kept.
4. **Add form:** posts to `/activities/{{token}}/questions` with these fields:
   - `label` (text, required)
   - `help_text` (text, optional)
   - `kind` (`<select>` of `q_kinds`)
   - `options` (`<textarea>`, "One choice per line", shown only for single/multi through a 5-line inline script toggling `hidden`)
   - `required` (checkbox)
5. **Flash messages:** `qok` and `qerr` (codes: `label`, `kind`, `options`, `max`, `notfound`), shown with the existing `<div class="flash ok|warn">` markup.

Escape everything with Jinja autoescape; **do not** use `|safe` on organizer text.

**Routes (app.py, next to the other `/activities/{event_token}/...` POSTs):**

| Route | Does |
|---|---|
| `POST /activities/{event_token}/questions` | `rq.clean_question(posted)`, then `st.add_event_question`. Audit action `event_question_add`. |
| `POST /activities/{event_token}/questions/preset` | Add each question of `rq.PRESETS[posted["preset"]]`, stopping at the max. Unknown key → `qerr=kind`. Audit action `event_question_add`. |
| `POST /activities/{event_token}/questions/{qid}` | `get_event_question` (else `qerr=notfound`), `clean_question`, `update_event_question`. Audit action `event_question_edit`. |
| `POST /activities/{event_token}/questions/{qid}/remove` | `remove_event_question`. Audit action `event_question_remove`, with the summary saying deleted or archived. |
| `POST /activities/{event_token}/questions/{qid}/move` | `move_event_question`. No audit, because this is noise. |

Every route follows `activity_messages_save` exactly:
- `posted = await _posted(request)`
- `ev = st.get_event(...)`; if missing, redirect to `/`
- `if not _can_manage_event(...)`, redirect to `/e/{token}`
- If `ev.get("event_kind") == "outside"`, redirect to the manage page (no questions for outside events)
- On success, redirect `303` to `/activities/{token}/manage?qok=1#questions`
- On error, redirect `303` to `/activities/{token}/manage?qerr=<code>#questions`

Register these route ids so a route is never matched as `{qid}`: declare `/questions/preset` **before** `/questions/{qid}`, and type `qid: int`.

The auth middleware's capability map (app.py:~1877) does **not** list `/activities`, so these routes only require being logged in. That is the same as every other manage-page POST, and `_can_manage_event` is the real guard (creator or admin). **Do not skip that check in any route.**

### A5. Public form (`event_consent`, `_event_view`, `link_tree.html`)

**`_event_view`:**
- Load `questions = st.list_event_questions(conn, ev["id"])` and pass it to the template.
- Build `posted_multi`: `{qid: [values]}` for re-rendering after an error. The caller supplies it (see below), so add a `posted_multi=None` kwarg to `_event_view`.
- **Consent text:** when `questions` is non-empty, append the sentence below to the displayed consent text. Add both strings to `i18n.py` as key `consent_extra_answers`, with `en` and `fil` values:
  > "We also collect your answers to this activity's additional registration questions, used only to prepare for the activity; they are deleted together with your personal details."

  `event_consent` must store the same combined text as `consent_text` when it saves the attendee.
  - Add a small helper `_consent_text_for(lang, has_questions)` and use it in both places.
  - Note that `event_consent` currently always stores the English `CONSENT_TEXT`. Keep that behaviour and only append the English extra sentence there.

**`event_consent`:**
1. Directly after `posted = {...}`, also keep the raw `pairs` and load `questions = st.list_event_questions(conn, ev["id"])`.
2. After the existing field validation, call `answers, q_errors = rq.collect_answers(questions, pairs)` and `errors.extend(q_errors)`.
3. Every `_event_view(... posted=posted ...)` call in this function (the errors return, the 429 return, the confirm interstitial) must also pass `posted_multi=_multi_from_pairs(pairs)`. This is a tiny helper returning `{key: [values]}` for keys starting with `q_`.
4. After `attendee_id` is known (both the `resolve == "new"` branch and the `register_attendee` branch), call `st.save_attendee_answers(conn, attendee_id, answers)` if `answers` is non-empty.

**`link_tree.html`, main form:** insert the block after the affiliation `.field` and **before** the consent panel.

```jinja
{% if questions %}
<h3 style="margin:1.2rem 0 .4rem;">{{ t('lt_more_details', lang) }}</h3>
{% for q in questions %}{% set fid = 'q_' ~ q.id %}{% set pv = posted_multi.get(fid, []) %}
<div class="field">
  <label for="{{ fid }}">{{ q.label }}{% if not q.required %} <span class="opt">{{ t('optional', lang) }}</span>{% endif %}</label>
  {# one branch per kind:
     text     -> <input type="text" id=fid name=fid maxlength=200 value=pv[0] {required}>
     longtext -> <textarea id=fid name=fid maxlength=1000 rows=3 {required}>pv[0]</textarea>
     single   -> <select id=fid name=fid {required}> blank "Select" option + q.options, selected if in pv
     yesno    -> same as single with options [Yes, No]; labels via t('yes')/t('no') but VALUES stay "Yes"/"No"
     multi    -> <fieldset> of <label><input type="checkbox" name=fid value=opt {checked if opt in pv}> opt</label>
                 NO `required` attribute on the checkboxes (see app.js:277)
     date     -> <input type="date" ...>
     time     -> <input type="time" ...> #}
  {% if q.help_text %}<p class="muted small" style="margin:.3rem 0 0;">{{ q.help_text }}</p>{% endif %}
</div>
{% endfor %}
{% endif %}
```

**`link_tree.html`, confirm interstitial (~line 156):** after the existing hidden inputs, re-emit every posted custom answer, or the answers are lost when someone clicks "Yes, that's me".

```jinja
{% for k, vals in (confirm.posted_multi or {}).items() %}{% for v in vals %}
<input type="hidden" name="{{ k }}" value="{{ v }}">
{% endfor %}{% endfor %}
```

For this to work, the `confirm={...}` dict in `event_consent` gets `"posted_multi": _multi_from_pairs(pairs)`.

**i18n.py:** add `lt_more_details` ("A few more details" / "Ilang karagdagang detalye"), `yes` ("Yes" / "Oo"), `no` ("No" / "Hindi") (none of these exist yet), and `consent_extra_answers`.

**Out of scope (say so in the PR body):**
- A participant cannot edit their answers after registering. The form is hidden once registered, but re-submitting the same email updates them.
- People who registered before a question was added simply have no answer; they show as "—".

### A6. Tests — `tests/test_registration_questions.py`

**Storage and pure tests** (tmp DB, copying `_fresh` and `_event` from `test_registration_dedup.py`):
- `parse_options`: strips blanks, dedupes, caps at 30.
- `clean_question`:
  - blank label → `"label"`
  - bad kind → `"kind"`
  - single with 1 option → `"options"`
  - text with options → options dropped
- `collect_answers`:
  - required blank → error containing the label
  - a forged single value not in options → treated as blank (and errors if required)
  - multi keeps only valid options, in options order, stored as JSON
  - bad date or time rejected
  - text truncated to 200
- `add_event_question` stops at `MAX_QUESTIONS`.
- `move_event_question`: swaps; at the top, "up" is a no-op.
- `remove_event_question`: `"deleted"` with no answers, `"archived"` with answers. An archived question is not in the default list.
- `update_event_question`: the kind change is ignored once answered.
- `save_attendee_answers`: upsert overwrites, and a key absent from the dict keeps the old value.
- `get_event_question` returns None for another event's question id.

**Route tests** (`client`, `manager`, `db_path`, `_make_event`):
- The manager adds a question → 303 to `?qok=1`. The manage page shows the label, and `/e/<tok>` shows the label.
- The "food" preset adds 2 questions.
- A **viewer** POSTing to `/activities/<tok>/questions` is not able to add (assert the count is unchanged).
- A question id from event B used under event A's token → `qerr=notfound`, and nothing changes.
- Register with a required question unanswered → 200 with the error text, and no attendee row created.
- Register with valid answers, including two checkbox values for a multi question (`data=[("q_5","Vegan"),("q_5","Halal"), ...]`, a list of tuples so the key repeats) → the answers are stored.
- Confirm interstitial: a different name on the same email with answers → the response HTML contains the hidden `q_<id>` inputs. Then posting `resolve=new` stores the answers on the new attendee.
- An activity with **no** questions: the registration flow is unchanged (the existing tests in `test_registration_dedup.py` and `test_event_e.py` still pass), and the consent text has no extra sentence.

### A7. Release bookkeeping
- Set `version.py` to `APP_VERSION = "3.42"` and add a layman `CHANGELOG` entry, e.g. "Organizers can now add their own questions to an activity's registration form, like food restrictions or arrival time."
- Add a `CHANGELOG.md` entry at the top, in the existing format: `## <date> (v3.42 — custom registration questions)`, bullets naming the new module, tables and routes, and `Tests: tests/test_registration_questions.py.`

---

## PR-B — roster, export, summary, privacy plumbing

### B1. Roster (`monitor_event` + `monitor_event.html`)
- In `monitor_event`, load `questions = st.list_event_questions(conn, ev["id"], include_archived=True)` and `answers = st.event_answers(conn, ev["id"])`. Pass both, plus a `rq.display_value` helper or precomputed strings.
- Precompute in Python, not Jinja: for each person `p`, set `p["extra"] = [(q["label"], rq.display_value(q, answers.get(p["id"], {}).get(q["id"])))]`, skipping empty values.
- In the Participant cell, under the email, if `p.extra and not p.purged`, render `<details><summary>Registration answers</summary><dl>…</dl></details>`. This avoids adding a column, so the mobile `data-label` layout is unchanged.

### B2. Summary panel (monitor page)
- `rq.tally(questions, answers)` covers single/multi/yesno questions that are not archived.
- Render a small card above the roster titled "Registration answers at a glance". It has one line per question, e.g. "Food restrictions: Vegetarian 12 · Halal 3 · Food allergy 2". Skip the card when there are no choice questions.

### B3. Export (`monitor_event_export` + `_build_monitor_xlsx`)
- Load the questions (including archived) and `event_answers` in `monitor_event_export`. Pass them to `_build_monitor_xlsx(ev, people, summ, org_name, questions=(), answers=None)`, keeping the defaults so other callers don't break (grep for callers).
- Use `headers = [...8 existing...] + [q["label"] for q in questions]`. Archived questions get the suffix " (removed)".
- **Replace every hardcoded `8` / `"ABCDEFGH"`** with `ncol = len(headers)` and `openpyxl.utils.get_column_letter`:
  - the letterhead merge (`end_column=8`)
  - the "No one has registered" merge
  - the width loop: existing widths, then 24 for each extra column
- For purged rows, write `""` for answer cells. In practice the answers are already deleted.
- Add one About-sheet note line: "Columns after “CSS status” are this activity's own registration questions."

### B4. Privacy and data integrity
- **`st.delete_attendee_entry`:** run `DELETE FROM attendee_answer WHERE attendee_id=?` *before* deleting the attendee. Foreign keys are ON, so otherwise this raises `IntegrityError`.
- **`st.purge_expired_attendees`:** before the `UPDATE`, run:
  ```sql
  DELETE FROM attendee_answer WHERE attendee_id IN
    (SELECT id FROM attendee WHERE consent_at < ? AND purged_at IS NULL)
  ```
  with the same `cutoff_iso`. Update its docstring and the `retention.py` audit summary text to say "name/email/contact and registration answers".
- **`merge_duplicate_attendees.py`:** before `DELETE FROM attendee WHERE id=?`, move the duplicate's answers to the survivor without clobbering the survivor's own:
  ```sql
  UPDATE OR IGNORE attendee_answer SET attendee_id=? WHERE attendee_id=?;  -- survivor, dup
  DELETE FROM attendee_answer WHERE attendee_id=?;                          -- dup leftovers
  ```
  Also update the comment at line ~20 ("response is the only table that references attendee").
- Grep for any other `DELETE FROM attendee` and patch it the same way. At planning time, storage.py and merge_duplicate_attendees.py were the only places.
- Confirm that answers never reach reports, AI prompts or public pages. They are only read through `event_answers` / `get_attendee_answers`, which are called only from the creator/admin-gated monitor routes.

### B5. Tests (extend `tests/test_registration_questions.py`)
- The roster HTML shows "Registration answers" and a value for a registrant with answers.
- The export: open the bytes with `openpyxl.load_workbook(io.BytesIO(r.content))`. Row 6 holds the question label after "CSS status", and the registrant's row holds the display value. Multi values are joined with ", ".
- `delete_attendee_entry` succeeds for an attendee who has answers, and leaves their answers gone.
- `purge_expired_attendees` deletes answers for purged attendees only.
- The merge script repoints answers, and the survivor's existing answer wins.
- `tally` counts correctly for multi and yesno.

### B6. Release bookkeeping
- Bump to `3.43`, with entries in both changelogs.

---

## Implementation notes / pitfalls (checklist)

- [ ] Multi-select: read from `pairs`, never from the collapsed `posted` dict.
- [ ] Multi checkboxes have **no** `required` attribute. Required-ness is enforced server-side.
- [ ] Every route checks that `qid` belongs to `ev["id"]` (`get_event_question`).
- [ ] Declare `/questions/preset` before `/questions/{qid}`.
- [ ] The confirm interstitial re-posts the `q_*` answers.
- [ ] The consent text gains the extra sentence only when the activity has questions, and the stored `consent_text` matches what was shown.
- [ ] Foreign keys are ON: delete answers before attendees (delete, purge, merge).
- [ ] No `|safe` on organizer-entered labels, help text or options.
- [ ] An activity without questions renders and behaves byte-for-byte as before. Run the existing `tests/test_event_e.py`, `tests/test_registration_dedup.py` and `tests/test_monitor.py`.
- [ ] `bash run_tests.sh` is green before each push. If it is slow, run `python3 -m pytest tests/test_registration_questions.py tests/test_registration_dedup.py tests/test_event_e.py tests/test_monitor.py -q` while iterating.
