"""Custom registration questions — the pure rules, no database, no web framework.

An organizer can add their own questions to one activity's public registration
form (food restrictions, arrival details, …). Everything that decides what a
question may look like, and what a posted answer is allowed to become, lives
HERE so it can be unit-tested without HTTP. storage.py persists the rows
(event_question / attendee_answer) and app.py wires the routes and the form.

WHY THE SERVER-SIDE WHITELISTING: the registration endpoint is public. A forged
POST must not be able to store arbitrary text in a choice field, so every
answer is re-checked against the question's own options here — the same rule
the courtesy-title (_HONORIFICS) check follows.

Stored answer values: text/longtext/date/time are the string as given, single
is one of the options, yesno is "Yes" or "No" (the page translates the label,
never the value), and multi is a JSON list in the options' own order.
"""
from __future__ import annotations

import json
import re
from datetime import date, time

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
MAX_ANSWER_SHORT = 200

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

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def parse_options(text: str) -> list[str]:
    """One option per line. Blank lines are dropped, repeats (ignoring case) keep
    their first spelling, each option is cut to MAX_OPTION_LEN and the list to
    MAX_OPTIONS."""
    out, seen = [], set()
    for line in (text or "").splitlines():
        opt = line.strip()[:MAX_OPTION_LEN].strip()
        if not opt or opt.casefold() in seen:
            continue
        seen.add(opt.casefold())
        out.append(opt)
        if len(out) >= MAX_OPTIONS:
            break
    return out


def clean_question(posted: dict) -> tuple[dict | None, str | None]:
    """Validate an organizer's add/edit form. Returns (q, None) or (None, code).
    q = {label, help_text, kind, options (list), required (bool)}. Codes: "label"
    (blank), "kind" (unknown), "options" (a choice kind with fewer than 2
    options). A non-choice kind always ends up with no options."""
    label = (posted.get("label") or "").strip()[:MAX_LABEL].strip()
    if not label:
        return None, "label"
    kind = (posted.get("kind") or "").strip()
    if kind not in KINDS:
        return None, "kind"
    options = parse_options(posted.get("options") or "") if kind in CHOICE_KINDS else []
    if kind in CHOICE_KINDS and len(options) < 2:
        return None, "options"
    return {
        "label": label,
        "help_text": (posted.get("help_text") or "").strip()[:MAX_HELP].strip(),
        "kind": kind,
        "options": options,
        "required": (posted.get("required") or "") in ("on", "1", "true", "yes"),
    }, None


def preset_questions(key: str) -> list[dict]:
    """The cleaned question dicts of one preset, ready for storage.add_event_question.
    An unknown key gives an empty list."""
    out = []
    for p in PRESETS.get(key, []):
        q, _err = clean_question({
            "label": p["label"], "kind": p["kind"], "help_text": p.get("help_text", ""),
            "options": "\n".join(p.get("options", [])),
            "required": "on" if p.get("required") else ""})
        if q:
            out.append(q)
    return out


def field_name(qid: int) -> str:
    """The form field a question's answer is posted under."""
    return f"q_{qid}"


def collect_answers(questions: list[dict], pairs: list[tuple[str, str]]) -> tuple[dict, list[str]]:
    """Turn a posted form into ({qid: stored_value}, errors). `questions` are the
    activity's ACTIVE questions from storage; `pairs` is the raw parse_qsl list,
    because a checkbox group repeats its key and a dict would keep only one.
    Anything that doesn't fit the question (a value outside the options, a bad
    date) counts as blank, and a blank answer to a required question is an error.
    Blank optional answers are left out of the result."""
    values: dict[str, list[str]] = {}
    for k, v in pairs:
        values.setdefault(k, []).append(v)
    answers, errors = {}, []
    for q in questions:
        got = values.get(field_name(q["id"]), [])
        kind = q["kind"]
        val = ""
        if kind == "text":
            val = (got[0] if got else "").strip()[:MAX_ANSWER_SHORT]
        elif kind == "longtext":
            val = (got[0] if got else "").strip()[:MAX_ANSWER]
        elif kind == "single":
            one = (got[0] if got else "").strip()
            val = one if len(got) == 1 and one in q["options"] else ""
        elif kind == "multi":
            posted_set = {g.strip() for g in got}
            keep = [o for o in q["options"] if o in posted_set]
            val = json.dumps(keep) if keep else ""
        elif kind == "yesno":
            one = (got[0] if got else "").strip()
            val = one if one in ("Yes", "No") else ""
        elif kind == "date":
            one = (got[0] if got else "").strip()
            val = one if _DATE_RE.match(one) and _is_date(one) else ""
        elif kind == "time":
            one = (got[0] if got else "").strip()
            val = one if _TIME_RE.match(one) and _is_time(one) else ""
        if val:
            answers[q["id"]] = val
        elif q["required"]:
            errors.append(f'Please answer “{q["label"]}”.')
    return answers, errors


def _is_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _is_time(s: str) -> bool:
    try:
        time.fromisoformat(s)
        return True
    except ValueError:
        return False


def display_value(q: dict, raw: str | None) -> str:
    """A stored answer as people read it (roster, export). A multi answer is its
    JSON list joined with ", " (falling back to the raw text if it isn't one);
    everything else is shown as stored. None or empty gives ""."""
    if not raw:
        return ""
    if q.get("kind") == "multi":
        try:
            vals = json.loads(raw)
            if isinstance(vals, list):
                return ", ".join(str(v) for v in vals)
        except ValueError:
            pass
    return raw
