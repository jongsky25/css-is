"""Birthday rules, pure and database-free (office calendar F2; docs/OFFICE_CALENDAR_PLAN.md §6).

A birthday is a month and a day — never a year. Who may SEE one is the intersection of two
things: the sharing choice its owner made (`share`), and the scope the viewer asked for. A
person always sees their own. Everything here takes plain dicts so it can be tested exhaustively
without a database:

    person  {user_id, month, day, share, section_path, division_path}
    viewer  {user_id, section_path, division_path}
"""
from __future__ import annotations

from datetime import date, timedelta

SHARES = ("none", "section", "division", "bureau")


def occurrence(month, day, year):
    """The date this birthday falls on in `year`. Feb 29 is kept on Feb 28 in a non-leap year."""
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, 2, 28)


def occurrences_between(month, day, start, end):
    """Every date in [start, end] this birthday falls on (a window can span New Year)."""
    out = []
    for year in range(start.year, end.year + 1):
        d = occurrence(month, day, year)
        if start <= d <= end:
            out.append(d)
    return out


def _under(path, root):
    return bool(path and root) and (path == root or path.startswith(root + "/"))


def shared_with(person, viewer):
    """May `viewer` see `person`'s birthday, by the person's own sharing choice?
    Yourself: always. "section" means the same unit, "division" the same division."""
    if person["user_id"] == viewer["user_id"]:
        return True
    share = person.get("share")
    if share == "bureau":
        return True
    if share == "section":
        return bool(person.get("section_path")) and person["section_path"] == viewer.get("section_path")
    if share == "division":
        return bool(person.get("division_path")) and person["division_path"] == viewer.get("division_path")
    return False


def in_scope(scope, person, viewer):
    """Does a VISIBLE birthday fall inside the calendar scope the viewer chose? Mirrors the
    entries' rules: "mine" is yours, the default "blend" adds what is shared bureau-wide, and
    a section / division view is that unit's own people."""
    if scope == "bureau":
        return True
    mine = person["user_id"] == viewer["user_id"]
    if scope == "mine":
        return mine
    if scope == "blend":
        return mine or person.get("share") == "bureau"
    root = viewer.get("section_path") if scope == "section" else viewer.get("division_path")
    return mine or _under(person.get("section_path"), root)


def first_name(display_name, nickname=None, fallback=""):
    """What a greeting calls someone: their nickname if they set one, else their first name
    (directory names are stored "First M. Last" or "LAST, First")."""
    if nickname and nickname.strip():
        return nickname.strip()
    name = (display_name or "").strip()
    if "," in name:
        name = name.split(",", 1)[1].strip()
    return name.split()[0] if name.split() else fallback


def is_today(month, day, today):
    return occurrence(month, day, today.year) == today


def week_label(d, today):
    """'Today', 'Tomorrow' or 'Wed' — and ' (this weekend)' for a Saturday/Sunday seen on a
    weekday, so a Friday glance doesn't miss Saturday's cake."""
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return d.strftime("%a") + (" (weekend)" if d.weekday() >= 5 else "")


# ---- greetings (docs/BIRTHDAY_GREETINGS_PLAN.md) -----------------------------------------
# A greeting comes BEFORE the birthday, never after: the six days leading up to it, plus the day.

GREETING_DAYS_BEFORE = 6


def next_occurrence(month, day, today):
    """The first date on or after `today` this birthday falls on (Feb 29 stays on Feb 28 in a
    non-leap year)."""
    this_year = occurrence(month, day, today.year)
    return this_year if this_year >= today else occurrence(month, day, today.year + 1)


def days_until(month, day, today):
    return (next_occurrence(month, day, today) - today).days


def greeting_phase(month, day, today):
    """'today' on the birthday, 'before' in the six days leading up to it, else 'none'. There is
    deliberately no 'after': a late greeting is worse than none."""
    n = days_until(month, day, today)
    if n == 0:
        return "today"
    return "before" if n <= GREETING_DAYS_BEFORE else "none"


def email_send_date(month, day, year, is_working):
    """When the greeting EMAIL goes out for this year's birthday: the day itself, or the last
    working day before it when it lands on a weekend or holiday (so it is read on a working day
    and is never late). `is_working(date) -> bool`. The result can fall in the previous year."""
    d = occurrence(month, day, year)
    for _ in range(14):                      # a long holiday run still ends; never loop forever
        if is_working(d):
            return d
        d -= timedelta(days=1)
    return d
