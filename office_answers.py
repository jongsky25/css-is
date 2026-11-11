"""Office answers for the assistant (docs/HOME_SEARCH_ASSISTANT_PLAN.md Phase 6).

Same shape and the same safety rule as calendar_answers: the model only ever chooses ONE OF THESE
KEYS; the server then writes the sentence from the ASKER's own data, so names and records never reach
the model and nothing the model says becomes output. Nothing is stored or learned from an answer.

Each slot is {label, kw, user_render(conn, user, today) -> str}, shaped like app.AI_ANSWER_SLOTS plus
the user-aware renderer. Colleague status goes through storage.colleague_status_for, so it honours the
admin's bureau/team switch, and only the basic state is ever used: no note, place or reason exists in
what is rendered here.
"""
from __future__ import annotations

from datetime import timedelta

import birthdays as bd
import calendar_people as cp
import re
import office_connect as oconn
import rooms
import storage as st

MAX_LINES = 6          # items listed in one answer
MAX_NAMES = 6          # names per status group


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _more(shown_of, total, cap):
    return f" …and {total - cap} more" if total > cap else ""


# ── to-do, approvals, wellness, AWA ──────────────────────────────────────────

def _todo(conn, user, today):
    tasks = oconn.home_tasks(conn, user, today)
    if not tasks:
        return "You have nothing on your to-do."
    titles = [t["title"] for t in tasks]
    return "On your to-do: " + "; ".join(titles[:MAX_LINES]) + _more(None, len(titles), MAX_LINES) + "."


def _approvals(conn, user, today):
    c = st.pending_approval_counts(conn, user)
    bits = []
    if c["wellness"]:
        bits.append(_plural(c["wellness"], "wellness break"))
    if c["awa"]:
        bits.append(_plural(c["awa"], "work arrangement"))
    return ("Waiting for your decision: " + " and ".join(bits) + ".") if bits else "No approvals are waiting on you."


def _wellness(conn, user, today):
    weekly = st.WELLNESS_WEEKLY_HOURS
    used = st.wellness_hours_used(conn, user["id"], st.wellness_week_start(today))
    left = max(0, weekly - used)
    fmt = lambda n: int(n) if float(n).is_integer() else n                       # noqa: E731
    text = f"You have {_plural(fmt(left), 'hour')} of wellness break left this week ({fmt(used)} of {fmt(weekly)} used)."
    nxt = [c for c in st.list_my_wellness_claims(conn, user["id"])
           if c["status"] == "approved" and c["break_date"] >= today.isoformat()]
    if nxt:
        c = min(nxt, key=lambda c: (c["break_date"], c["start_time"]))
        d = _date(c["break_date"])
        text += f" Your next approved break: {d:%a} {d:%b} {d.day} at {c['start_time']}."
    return text


def _date(iso):
    from datetime import date
    return date.fromisoformat(iso)


def _awa(conn, user, today):
    open_ps = st.work_arrangement_open_periods()
    task = oconn._task_awa(conn, user, today)
    if not open_ps:
        return "No work arrangement filing is open right now."
    ps = open_ps[0]
    deadline = f" The deadline is {st.work_arrangement_deadline_label(ps)}."
    if not task:
        return f"Nothing to file for {st.work_arrangement_period_label(ps)}.{deadline}"
    text = task["title"] + (f" ({task['detail']})" if task.get("detail") else "") + "."
    return text + deadline


# ── who is in the office ─────────────────────────────────────────────────────

_GROUPS = (("onsite", "In the office"), ("wfh", "Working from home"),
           ("field", "In the field"), ("leave", "On leave"))


def _names(conn, ids):
    people = {p["user_id"]: bd.first_name(p["name"], p["nickname"], p["name"])
              for p in st.colleague_directory(conn)}
    return sorted((people[i] for i in ids if i in people), key=str.lower)


def _status_text(conn, user, today, wanted):
    status = st.colleague_status_for(conn, user, today)
    if not status:
        if st.colleague_status_scope(conn) == "team":
            return "Colleague status isn't shared with your account, so I can't say."
        return "I don't have anyone's status to show today."
    if set(status.values()) == {"off"}:
        return "Today is not a working day."
    parts = []
    for key, label in _GROUPS:
        if key not in wanted:
            continue
        ids = [u for u, s in status.items() if s == key]
        if not ids:
            continue
        names = _names(conn, ids)
        shown = ", ".join(names[:MAX_NAMES]) + _more(None, len(names), MAX_NAMES)
        parts.append(f"{label} ({len(names)}): {shown}")
    if not parts:
        return "Nobody is reported " + ("working from home" if wanted == ("wfh",) else "in the office") + " today."
    return "; ".join(parts) + "."


def _office_today(conn, user, today):
    return _status_text(conn, user, today, ("onsite", "wfh", "field", "leave"))


def _wfh_today(conn, user, today):
    return _status_text(conn, user, today, ("wfh",))


# ── the conference room ──────────────────────────────────────────────────────

def _windows(slots):
    """[(first_slot, last_slot)] runs of consecutive hours, in order."""
    runs, cur = [], []
    for s in slots:
        if cur and cur[-1]["sort"] + 1 != s["sort"] and cur[-1]["end_time"] != s["start_time"]:
            runs.append(cur)
            cur = []
        cur.append(s)
    if cur:
        runs.append(cur)
    return runs


def _room(conn, user, today, offset):
    day = today + timedelta(days=offset)
    word = "today" if offset == 0 else "tomorrow"
    if not rooms.is_working_day(conn, day):
        return f"The conference room is closed {word} (not a working day)."
    free = [v["slot"] for v in rooms.slot_states(conn, day).values() if v["state"] == "free"]
    if not free:
        return f"The conference room is fully booked {word}."
    free.sort(key=lambda s: (s["sort"], s["id"]))
    wins = ", ".join(f"{rooms.hour_label(r[0]['start_time'])}–{rooms.hour_label(r[-1]['end_time'])}"
                     for r in _windows(free))
    return f"The conference room is free {word}: {wins}."


def _my_rooms(conn, user, today):
    mine = rooms.list_for_user(conn, user["id"], upcoming_only=True, today=today)
    if not mine:
        return "You have no upcoming conference room bookings."
    mine = sorted(mine, key=lambda r: (r["day"], r["id"]))
    lines = []
    for r in mine[:MAX_LINES]:
        d = _date(r["day"])
        lines.append(f"{d:%a} {d:%b} {d.day}: {r['title'] or 'Conference room'}"
                     + (" (waiting for approval)" if r["status"] == "requested" else ""))
    return "Your conference room bookings: " + "; ".join(lines) + _more(None, len(mine), MAX_LINES) + "."


# ── one colleague, by name ───────────────────────────────────────────────────
#
# "Where is Mimi today?" The model returns the slot key AND the name as the person typed it. The
# name is an untrusted argument: it is cleaned, checked against the question itself, and resolved
# against the directory by the server. What is rendered is the DIRECTORY's name and the basic
# status from storage.colleague_status_for (so the admin's bureau/team switch applies) — never
# anything the model wrote.

_NAME_OK = re.compile(r"^[A-Za-zÀ-ÿñÑ][A-Za-zÀ-ÿñÑ .'\-]{1,39}$")


def clean_person_name(raw, query):
    """The name the model proposed, or None. Plain letters, spaces and . ' - only, 2-40 characters,
    and every word of it must literally appear in what the person typed: the model cannot
    introduce a name the question never contained."""
    if not isinstance(raw, str):
        return None
    name = " ".join(raw.split())
    if not _NAME_OK.match(name):
        return None
    q = " ".join((query or "").lower().split())
    words = [w for w in cp._words(name)]
    if not words or any(w not in cp._words(q) for w in words):
        return None
    return name


def resolve_person(conn, name):
    """([user_id, ...], exact) — the colleagues this name could be. `exact` is True only when
    one person fits at a level calendar_people trusts enough to pre-select (an admin alias, the
    bureau's name guide, or a single nickname / full name / first-name match)."""
    key = cp.clean(name)
    if not key:
        return [], False
    live = {p["user_id"] for p in st.colleague_directory(conn)}
    m = cp.match(key[0], cp.load_directory(conn))
    cands = [u for u in m["candidates"] if u in live]
    exact = m["status"] in ("alias", "guided", "suggested") and len(cands) == 1
    return cands, exact


_STATE_PHRASE = {"onsite": "is in the office today", "wfh": "is working from home today",
                 "field": "is in the field today", "leave": "is on leave today", "off": "is off today"}


def person_status(conn, user, today, name):
    """{"text", "links"} for one named colleague. A name that does not resolve to exactly one
    colleague gets "I couldn't tell who you mean", with links to whoever it could be."""
    cands, exact = resolve_person(conn, name) if name else ([], False)
    if not exact:
        people = {p["user_id"]: p for p in st.colleague_directory(conn)}
        links = [{"label": people[u]["name"], "url": f"/people/{u}"} for u in cands[:5] if u in people]
        return {"text": "I couldn't tell who you mean." + (" Did you mean one of these?" if links else
                " Try their full name."), "links": links}
    p = next(x for x in st.colleague_directory(conn) if x["user_id"] == cands[0])
    state = st.colleague_status_for(conn, user, today).get(p["user_id"])
    if state in _STATE_PHRASE:
        text = f"{p['name']} {_STATE_PHRASE[state]}."
    elif st.colleague_status_scope(conn) == "team":
        text = f"Colleague status isn't shared with your account for {p['name']}."
    else:
        text = f"I don't have a status for {p['name']} today."
    return {"text": text, "links": [{"label": "Open card →", "url": f"/people/{p['user_id']}"}]}


def _person_status_text(conn, user, today, name=None):
    """The slot's plain-text render (the FAQ-rule path, which has no name to give)."""
    if not name:
        return "Tell me whose status you want, for example “where is Mimi today?”."
    return person_status(conn, user, today, name)["text"]


SLOTS = {
    "todo_summary": {
        "label": "My to-do list", "kw": "to do todo to-do list tasks what do i need to do pending reminders",
        "user_render": _todo},
    "approvals_waiting": {
        "label": "Approvals waiting on me", "kw": "approvals waiting pending approve requests for my approval decide",
        "user_render": _approvals},
    "wellness_left": {
        "label": "Wellness hours left", "kw": "wellness break hours left remaining how many wellness oras",
        "user_render": _wellness},
    "awa_status": {
        "label": "My work arrangement filing", "kw": "awa work arrangement filed file deadline filing",
        "user_render": _awa},
    "office_today": {
        "label": "Who is in the office today", "kw": "who is in the office today onsite on site present nasa opisina",
        "user_render": _office_today},
    "wfh_today": {
        "label": "Who is working from home today", "kw": "who is working from home today wfh work from home",
        "user_render": _wfh_today},
    "room_today": {
        "label": "Conference room — today", "kw": "conference room free available today booking",
        "user_render": lambda conn, user, today: _room(conn, user, today, 0)},
    "room_tomorrow": {
        "label": "Conference room — tomorrow", "kw": "conference room free available tomorrow bukas booking",
        "user_render": lambda conn, user, today: _room(conn, user, today, 1)},
    "my_room_bookings": {
        "label": "My conference room bookings", "kw": "my room bookings conference room reservations booked",
        "user_render": _my_rooms},
    # Takes the colleague's name from the question (see clean_person_name); not offered as a seed rule.
    "person_status": {
        "label": "Where a colleague is today", "kw": "where is who is is in the office today in the field on leave wfh "
                                                      "working from home nasaan si colleague name",
        "user_render": _person_status_text, "takes_name": True},
}

# Questions people ask in their own words, mapped to a slot, so the FAQ layer answers them with no model
# call at all (and while the assistant is switched off). (kind, key, canonical question, alternate phrasings)
SEED_RULES = [
    ("answer", "todo_summary", "what is on my to do", ["what do i need to do", "my to do list", "my tasks"]),
    ("answer", "approvals_waiting", "do i have approvals", ["any approvals waiting", "what is waiting for my approval"]),
    ("answer", "wellness_left", "how many wellness hours do i have left",
     ["how much wellness break do i have left", "ilan oras wellness ko", "ilang oras na lang wellness ko"]),
    ("answer", "awa_status", "did i file my awa",
     ["when is the awa deadline", "have i filed my work arrangement", "naka file na ba ako ng awa"]),
    ("answer", "office_today", "who is in the office today",
     ["who is in the office", "sino ang nasa opisina", "sino ang nasa opisina ngayon"]),
    ("answer", "wfh_today", "who is working from home today",
     ["who is wfh today", "sino ang naka wfh ngayon"]),
    ("answer", "room_today", "is the conference room free today",
     ["is the conference room available today", "free ba ang conference room ngayon"]),
    ("answer", "room_tomorrow", "is the conference room free tomorrow",
     ["is the conference room available tomorrow", "free ba ang conference room bukas"]),
    ("answer", "my_room_bookings", "my room bookings",
     ["my conference room bookings", "what room bookings do i have"]),
]
