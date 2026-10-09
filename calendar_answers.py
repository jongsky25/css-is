"""Calendar answers for the assistant and the read API (office calendar H3).

The assistant never sees calendar data. The model only ever chooses ONE OF THESE KEYS from a
fixed list of labels and keywords (exactly like the survey-statistics answers); the server then
renders the answer here, from the ASKER's own view of the calendar — `office_calendar.items_between`,
the same function behind /calendar, so a person can never be told about something the calendar
would not show them. Nothing is stored or learned from the answer, there is no free text from the
model in it, and no note, meeting link or leave reason exists in what is rendered.

Each slot is {label, kw, user_render(conn, user, today) -> str}, shaped like app.AI_ANSWER_SLOTS
plus the user-aware renderer.
"""
from __future__ import annotations

from datetime import date, timedelta

import office_calendar as oc

MAX_LINES = 6


def _fmt(d):
    return f"{d:%a} {d.day}"


def _span(a, b):
    return f"{a:%b} {a.day}" if a == b else (f"{a:%b} {a.day}–{b.day}" if a.month == b.month else f"{a:%b} {a.day} – {b:%b} {b.day}")


def _live(items):
    return [i for i in items if i["kind"] != "banner" and i["status"] not in ("cancelled", "postponed")]


def _line(i, day_first=True):
    a = date.fromisoformat(i["start"])
    b = date.fromisoformat(i["end"])
    when = _fmt(a) + (f"–{_fmt(b)}" if b != a else "")
    t = f" at {i['start_time']}" if i["start_time"] else ""
    tent = " (tentative)" if i["status"] == "tentative" else ""
    return f"{when}: {i['title']}{t}{tent}"


def _list(prefix_one, prefix_many, items, none_text):
    if not items:
        return none_text
    shown = [_line(i) for i in items[:MAX_LINES]]
    more = f" …and {len(items) - MAX_LINES} more." if len(items) > MAX_LINES else ""
    head = prefix_one if len(items) == 1 else prefix_many.format(n=len(items))
    return head + " " + "; ".join(shown) + "." + more


def _mine(conn, user, a, b):
    return _live(oc.items_between(conn, user, a, b, scope="blend", layers=["entries", "activities"]))


def _week(today, offset):
    monday = today - timedelta(days=today.weekday()) + timedelta(days=7 * offset)
    return (max(monday, today) if offset == 0 else monday), monday + timedelta(days=6)


def _today(conn, user, today):
    return _list("You have one thing today:", "You have {n} things today:", _mine(conn, user, today, today),
                 "Nothing on your calendar today.")


def _tomorrow(conn, user, today):
    d = today + timedelta(days=1)
    return _list("You have one thing tomorrow:", "You have {n} things tomorrow:", _mine(conn, user, d, d),
                 "Nothing on your calendar tomorrow.")


def _this_week(conn, user, today):
    a, b = _week(today, 0)
    return _list(f"For the rest of this week ({_span(a, b)}) you have one thing:",
                 f"For the rest of this week ({_span(a, b)}) you have {{n}} things:", _mine(conn, user, a, b),
                 f"Nothing else on your calendar this week ({_span(a, b)}).")


def _next_week(conn, user, today):
    a, b = _week(today, 1)
    return _list(f"Next week ({_span(a, b)}) you have one thing:", f"Next week ({_span(a, b)}) you have {{n}} things:",
                 _mine(conn, user, a, b), f"Nothing on your calendar next week ({_span(a, b)}).")


def _next_item(conn, user, today):
    items = [i for i in _mine(conn, user, today, today + timedelta(days=90)) if i["end"] >= today.isoformat()]
    if not items:
        return "Nothing coming up on your calendar in the next three months."
    return "Your next item: " + _line(items[0]) + "."


def _away(conn, user, today, offset):
    a, b = _week(today, offset)
    items = oc.items_between(conn, user, a, b, scope="bureau", layers=["entries", "leave"])
    seen, lines = set(), []
    for i in items:
        if i["status"] in ("cancelled", "postponed", "tentative") or i["kind"] not in ("travel", "leave"):
            continue
        for p in i["people"]:
            name = p.get("name") or "Someone"
            key = (name, i["kind"], i["start"])
            if key in seen:
                continue
            seen.add(key)
            what = "on leave" if i["kind"] == "leave" else f"away ({i['title']})"
            lines.append(f"{name} {what} {_span(date.fromisoformat(i['start']), date.fromisoformat(i['end']))}")
    label = "this week" if offset == 0 else "next week"
    if not lines:
        return f"Nobody you can see is away {label} ({_span(a, b)})."
    more = f" …and {len(lines) - MAX_LINES} more." if len(lines) > MAX_LINES else ""
    return f"Away {label} ({_span(a, b)}): " + "; ".join(lines[:MAX_LINES]) + "." + more


def _birthdays(conn, user, today):
    a, b = today, today + timedelta(days=6)
    items = oc.items_between(conn, user, a, b, scope="bureau", layers=["birthdays"])
    names = [(date.fromisoformat(i["start"]), i["title"].replace("🎂 ", "")) for i in items
             if not any(p["user_id"] == user["id"] for p in i["people"])]
    if not names:
        return "No shared birthdays in the next seven days."
    return "Birthdays this week: " + ", ".join(f"{n} ({'today' if d == today else _fmt(d)})" for d, n in names[:MAX_LINES]) + "."


SLOTS = {
    "calendar_today": {
        "label": "My calendar — today", "kw": "calendar today what do i have today on my schedule today agenda",
        "user_render": _today},
    "calendar_tomorrow": {
        "label": "My calendar — tomorrow", "kw": "calendar tomorrow what do i have tomorrow schedule tomorrow",
        "user_render": _tomorrow},
    "calendar_this_week": {
        "label": "My calendar — rest of this week", "kw": "calendar this week what is on this week schedule this week meetings",
        "user_render": _this_week},
    "calendar_next_week": {
        "label": "My calendar — next week", "kw": "calendar next week what is on next week schedule next week meetings",
        "user_render": _next_week},
    "calendar_next_item": {
        "label": "My next calendar item", "kw": "next meeting next event what is my next what is coming up",
        "user_render": _next_item},
    "calendar_away_this_week": {
        "label": "Who is away — this week", "kw": "who is away this week who is out on leave trip travelling this week",
        "user_render": lambda conn, user, today: _away(conn, user, today, 0)},
    "calendar_away_next_week": {
        "label": "Who is away — next week", "kw": "who is away next week who is out on leave trip travelling next week",
        "user_render": lambda conn, user, today: _away(conn, user, today, 1)},
    "calendar_birthdays": {
        "label": "Birthdays this week", "kw": "birthdays this week whose birthday celebrants celebrating",
        "user_render": _birthdays},
}

# Questions people ask in their own words, mapped to a slot, so the FAQ layer answers them with no model
# call at all (and while the assistant is switched off). (kind, key, canonical question, alternate phrasings)
SEED_RULES = [
    ("answer", "calendar_today", "what do i have today", ["what is on my calendar today", "my schedule today"]),
    ("answer", "calendar_tomorrow", "what do i have tomorrow", ["what is on my calendar tomorrow", "my schedule tomorrow"]),
    ("answer", "calendar_this_week", "what is on this week", ["what is on my calendar this week", "my schedule this week"]),
    ("answer", "calendar_next_week", "what is on next week", ["what is on my calendar next week", "my schedule next week"]),
    ("answer", "calendar_next_item", "what is my next meeting", ["what is my next event", "what is coming up"]),
    ("answer", "calendar_away_this_week", "who is away this week", ["who is on leave this week", "who is out this week"]),
    ("answer", "calendar_away_next_week", "who is away next week", ["who is on leave next week", "who is out next week"]),
    ("answer", "calendar_birthdays", "whose birthday is this week", ["birthdays this week", "who is celebrating this week"]),
]
