"""Recurring calendar items (office calendar H1), pure and database-free.

A series is ONE calendar entry that carries an RFC 5545 RRULE and a list of skipped dates
(EXDATE). Only the shapes people actually use are accepted, so a hand-edited or imported rule
can never explode into thousands of rows or surprise the calendar:

    weekdays      every working day                     FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR
    weekly        every week on the start's weekday     FREQ=WEEKLY;BYDAY=TU
    biweekly      every 2 weeks                         FREQ=WEEKLY;INTERVAL=2;BYDAY=TU
    monthly_date  the same date each month              FREQ=MONTHLY;BYMONTHDAY=14
    monthly_nth   the same weekday each month           FREQ=MONTHLY;BYDAY=2TU   (5th -> last)

Every rule MUST end (UNTIL=YYYYMMDD, at most two years out): an open-ended series would otherwise
fill the calendar, the feed and every reminder forever. The start date is always the first
occurrence. "Change just this one" is an EXDATE on the series plus a separate ordinary entry.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from dateutil.rrule import rrulestr

REPEATS = {
    "none": "Doesn't repeat",
    "weekdays": "Every weekday",
    "weekly": "Every week",
    "biweekly": "Every 2 weeks",
    "monthly_date": "Every month, same date",
    "monthly_nth": "Every month, same weekday (e.g. 2nd Tuesday)",
}
MAX_YEARS = 2
MAX_OCCURRENCES = 800                    # a hard stop on any one expansion
_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_BYDAY = re.compile(r"^([+-]?[1-5])?(MO|TU|WE|TH|FR|SA|SU)$")


def _iso(d):
    return d.isoformat() if isinstance(d, date) else str(d)


def last_allowed(start):
    """The latest UNTIL a series starting on `start` may have."""
    try:
        return start.replace(year=start.year + MAX_YEARS)
    except ValueError:                    # Feb 29
        return start.replace(year=start.year + MAX_YEARS, day=28)


def build(repeat, start, until):
    """The RRULE text for a form choice, or None for "doesn't repeat". Raises ValueError with a
    sentence a person can read."""
    if repeat in (None, "", "none"):
        return None
    if repeat not in REPEATS:
        raise ValueError("Pick how often it repeats from the list.")
    if not until:
        raise ValueError("Choose the last date it repeats, so the series has an end.")
    if until < start:
        raise ValueError("The last date can't be before the first.")
    if until > last_allowed(start):
        raise ValueError(f"A series can run for {MAX_YEARS} years at most. Choose an earlier last date.")
    day = _DAYS[start.weekday()]
    if repeat == "weekdays":
        core = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
    elif repeat == "weekly":
        core = f"FREQ=WEEKLY;BYDAY={day}"
    elif repeat == "biweekly":
        core = f"FREQ=WEEKLY;INTERVAL=2;BYDAY={day}"
    elif repeat == "monthly_date":
        core = f"FREQ=MONTHLY;BYMONTHDAY={start.day}"
    else:
        n = (start.day - 1) // 7 + 1
        core = f"FREQ=MONTHLY;BYDAY={'-1' if n == 5 else n}{day}"
    return f"{core};UNTIL={until:%Y%m%d}"


def parse(rrule):
    """{freq, interval, byday[list], bymonthday, until(date)} for an accepted rule, else ValueError."""
    if not rrule or not isinstance(rrule, str):
        raise ValueError("Not a repeat rule.")
    parts = {}
    for chunk in rrule.strip().split(";"):
        k, _, v = chunk.partition("=")
        if not k or not v or k in parts or k not in {"FREQ", "INTERVAL", "BYDAY", "BYMONTHDAY", "UNTIL"}:
            raise ValueError("That repeat rule isn't supported.")
        parts[k] = v
    freq = parts.get("FREQ")
    if freq not in ("WEEKLY", "MONTHLY"):
        raise ValueError("That repeat rule isn't supported.")
    try:
        interval = int(parts.get("INTERVAL", "1"))
        until = datetime.strptime(parts["UNTIL"], "%Y%m%d").date()
        bymd = int(parts["BYMONTHDAY"]) if "BYMONTHDAY" in parts else None
    except (KeyError, ValueError):
        raise ValueError("A repeat rule needs a valid last date.") from None
    byday = parts["BYDAY"].split(",") if "BYDAY" in parts else []
    if not 1 <= interval <= 4 or (bymd is not None and not 1 <= bymd <= 31) or len(byday) > 7:
        raise ValueError("That repeat rule isn't supported.")
    for b in byday:
        m = _BYDAY.match(b)
        if not m or (m.group(1) and freq != "MONTHLY"):
            raise ValueError("That repeat rule isn't supported.")
    if freq == "WEEKLY" and (bymd is not None or not byday):
        raise ValueError("That repeat rule isn't supported.")
    if freq == "MONTHLY" and (bool(bymd) == bool(byday) or interval != 1 or len(byday) > 1):
        raise ValueError("That repeat rule isn't supported.")
    return {"freq": freq, "interval": interval, "byday": byday, "bymonthday": bymd, "until": until}


def validate(rrule, start):
    """The rule as stored, or ValueError. The first occurrence must be the start date itself
    (a rule whose pattern misses it would silently start later), and the end must be in range."""
    p = parse(rrule)
    if p["until"] < start:
        raise ValueError("The last date can't be before the first.")
    if p["until"] > last_allowed(start):
        raise ValueError(f"A series can run for {MAX_YEARS} years at most. Choose an earlier last date.")
    if start not in _expand(rrule, start, start, start):
        raise ValueError("The first date doesn't fit the repeat pattern.")
    return rrule.strip()


def until_of(rrule):
    """The last date of a stored rule, or None if it cannot be read."""
    try:
        return parse(rrule)["until"]
    except ValueError:
        return None


def kind_of(rrule, start):
    """(repeat key, until date) for a stored rule — what the edit form pre-selects."""
    try:
        p = parse(rrule)
    except ValueError:
        return "none", None
    if p["freq"] == "MONTHLY":
        return ("monthly_date" if p["bymonthday"] else "monthly_nth"), p["until"]
    if len(p["byday"]) == 5:
        return "weekdays", p["until"]
    return ("biweekly" if p["interval"] == 2 else "weekly"), p["until"]


def describe(rrule, start):
    """'Every Tuesday until Dec 29, 2026' for a stored rule."""
    try:
        p = parse(rrule)
    except ValueError:
        return ""
    key, until = kind_of(rrule, start)
    day = _NAMES[start.weekday()]
    what = {"weekdays": "Every weekday", "weekly": f"Every {day}", "biweekly": f"Every other {day}",
            "monthly_date": f"Monthly on the {_ordinal(start.day)}",
            "monthly_nth": f"Monthly on the {_nth_word(start)} {day}"}.get(key, "Repeats")
    return f"{what} until {until:%b} {until.day}, {until.year}"


def _ordinal(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _nth_word(start):
    n = (start.day - 1) // 7 + 1
    return "last" if n == 5 else _ordinal(n)


def _expand(rrule, start, a, b):
    until = parse(rrule)["until"]
    rule = rrulestr(rrule.replace(f"UNTIL={until:%Y%m%d}", f"UNTIL={until:%Y%m%dT235959}"),
                    dtstart=datetime.combine(start, time()))
    out = []
    for dt in rule.between(datetime.combine(a, time()), datetime.combine(b, time(23, 59, 59)), inc=True):
        out.append(dt.date())
        if len(out) >= MAX_OCCURRENCES:
            break
    return out


def parse_exdates(text):
    """Sorted unique dates from a stored 'YYYY-MM-DD,YYYY-MM-DD' string; unreadable pieces are dropped."""
    out = set()
    for piece in (text or "").split(","):
        try:
            out.add(date.fromisoformat(piece.strip()))
        except ValueError:
            continue
    return sorted(out)


def join_exdates(dates):
    return ",".join(d.isoformat() for d in sorted(set(dates))) or None


def occurrences(start, rrule, exdates, window_start, window_end, span_days=0):
    """Start dates of every occurrence that OVERLAPS [window_start, window_end] (an occurrence that
    began earlier and runs `span_days` into the window counts), skipped dates removed. No rule is
    just the start date."""
    skip = set(parse_exdates(exdates)) if isinstance(exdates, (str, type(None))) else set(exdates)
    if not rrule:
        starts = [start] if start <= window_end and start + timedelta(days=span_days) >= window_start else []
    else:
        try:
            starts = _expand(rrule, start, window_start - timedelta(days=span_days), window_end)
        except ValueError:
            starts = [start] if start <= window_end and start + timedelta(days=span_days) >= window_start else []
    return [d for d in starts if d not in skip]
