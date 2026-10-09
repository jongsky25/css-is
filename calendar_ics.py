"""iCalendar (RFC 5545) writer for the office calendar (office calendar G4).

Pure and database-free: it turns plain dicts into text, so it can be tested byte for byte.
Rules it keeps:

* lines end in CRLF and are folded at 75 OCTETS (never in the middle of a UTF-8 character);
* TEXT values escape backslash, semicolon, comma and newlines;
* times are floating-free: timed events carry TZID=Asia/Manila with a VTIMEZONE (the
  Philippines has no daylight saving, so one STANDARD block is the whole truth), all-day events
  are VALUE=DATE with an exclusive DTEND, and DTSTAMP is UTC;
* every event keeps its random UID and its SEQUENCE, so a calendar app UPDATES the event it
  already has instead of duplicating it, and a cancelled one says STATUS:CANCELLED;
* a birthday is a yearly recurring all-day event (a Feb 29 person's rule is "last day of
  February", which is exactly where the app shows them in a non-leap year).

Nothing here reads a year of birth: the birthday helper is given a month and a day.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

CRLF = "\r\n"
PRODID = "-//Office Connect//BLHSD Calendar//EN"
TZID = "Asia/Manila"
_MANILA = timedelta(hours=8)
_STATUS = {"confirmed": "CONFIRMED", "tentative": "TENTATIVE", "postponed": "TENTATIVE",
           "cancelled": "CANCELLED"}


def escape_text(value):
    """RFC 5545 §3.3.11 TEXT escaping."""
    return (str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def fold(line):
    """Fold one logical line at 75 octets, continuing with a single space. Splits only between
    characters, so a multi-byte letter is never cut in half."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur, size, limit = [], [], 0, 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if size + n > limit:
            out.append("".join(cur))
            cur, size = [], 1                          # the continuation's leading space costs one octet
        cur.append(ch)
        size += n
    out.append("".join(cur))
    return (CRLF + " ").join(out)


def _prop(name, value, params=""):
    return fold(f"{name}{params}:{value}")


def _d(iso):
    return iso.replace("-", "")


def _dt(iso_date, hhmm):
    return f"{_d(iso_date)}T{hhmm.replace(':', '')}00"


def utc_stamp(local_iso=None):
    """DTSTAMP in UTC from a naive Asia/Manila ISO string (or now)."""
    try:
        t = datetime.fromisoformat(local_iso) if local_iso else datetime.utcnow() + _MANILA
    except ValueError:
        t = datetime.utcnow() + _MANILA
    return (t - _MANILA).strftime("%Y%m%dT%H%M%SZ")


VTIMEZONE = CRLF.join([
    "BEGIN:VTIMEZONE", f"TZID:{TZID}", "BEGIN:STANDARD", "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0800", "TZOFFSETTO:+0800", "TZNAME:PST", "END:STANDARD", "END:VTIMEZONE"])


def vevent(ev):
    """One VEVENT from a plain dict: uid, sequence, title, status, start, end (inclusive ISO
    dates), start_time / end_time ("HH:MM" or None), venue, url, description, tags, stamp,
    rrule (optional)."""
    start, end = ev["start"], ev.get("end") or ev["start"]
    lines = ["BEGIN:VEVENT", _prop("UID", ev["uid"]), _prop("DTSTAMP", utc_stamp(ev.get("stamp"))),
             _prop("SEQUENCE", int(ev.get("sequence") or 0))]
    st_time, en_time = ev.get("start_time"), ev.get("end_time")
    timed = bool(st_time) and (start == end or bool(en_time))
    if timed:
        lines.append(_prop("DTSTART", _dt(start, st_time), f";TZID={TZID}"))
        if en_time:
            lines.append(_prop("DTEND", _dt(end, en_time), f";TZID={TZID}"))
        else:                                                 # a start with no end: an hour
            t0 = datetime.fromisoformat(f"{start}T{st_time}:00") + timedelta(hours=1)
            lines.append(_prop("DTEND", t0.strftime("%Y%m%dT%H%M%S"), f";TZID={TZID}"))
    else:
        last = date.fromisoformat(end) + timedelta(days=1)    # DTEND of a date is EXCLUSIVE
        lines.append(_prop("DTSTART", _d(start), ";VALUE=DATE"))
        lines.append(_prop("DTEND", last.strftime("%Y%m%d"), ";VALUE=DATE"))
    if ev.get("rrule"):
        lines.append(_prop("RRULE", ev["rrule"]))
    title = ev["title"]
    if ev.get("status") == "postponed":
        title = f"[Postponed] {title}"
    lines.append(_prop("SUMMARY", escape_text(title)))
    lines.append(_prop("STATUS", _STATUS.get(ev.get("status") or "confirmed", "CONFIRMED")))
    if ev.get("venue"):
        lines.append(_prop("LOCATION", escape_text(ev["venue"])))
    if ev.get("url"):
        lines.append(_prop("URL", ev["url"]))
    if ev.get("description"):
        lines.append(_prop("DESCRIPTION", escape_text(ev["description"])))
    tags = [t for t in (ev.get("tags") or []) if t]
    if tags:
        lines.append(_prop("CATEGORIES", ",".join(escape_text(t) for t in tags)))
    lines.append("TRANSP:TRANSPARENT" if ev.get("transparent") else "TRANSP:OPAQUE")
    lines.append("END:VEVENT")
    return CRLF.join(lines)


def vcalendar(events, *, name=None, method=None):
    """A complete VCALENDAR. `method="PUBLISH"` marks an emailed attachment; a subscription feed
    leaves it out. Always ends with a CRLF."""
    head = ["BEGIN:VCALENDAR", "VERSION:2.0", _prop("PRODID", PRODID), "CALSCALE:GREGORIAN"]
    if method:
        head.append(f"METHOD:{method}")
    if name:
        head.append(_prop("X-WR-CALNAME", escape_text(name)))
    head.append(_prop("X-WR-TIMEZONE", TZID))
    return CRLF.join(head + [VTIMEZONE] + [vevent(e) for e in events] + ["END:VCALENDAR"]) + CRLF


def entry_event(entry, base_url=""):
    """The VEVENT dict for a calendar entry (storage.cal_get's dict)."""
    link = f"{base_url}/calendar/entries/{entry['id']}" if base_url else ""
    desc = "\n".join(x for x in (entry.get("note"), link) if x)
    return {"uid": entry["uid"], "sequence": entry.get("sequence") or 0, "title": entry["title"],
            "status": entry["status"], "start": entry["start_date"], "end": entry.get("end_date"),
            "start_time": entry.get("start_time"), "end_time": entry.get("end_time"),
            "venue": entry.get("venue"), "url": entry.get("meeting_url") or link or None,
            "description": desc, "tags": entry.get("tags") or [], "stamp": entry.get("updated_at")}


def activity_event(item, base_url=""):
    """The VEVENT dict for a CSS activity shown on the calendar (an office_calendar item)."""
    eid = (item.get("css") or {}).get("event_id")
    return {"uid": f"css-activity-{eid}@officeconnect", "sequence": 0, "title": item["title"],
            "status": "confirmed", "start": item["start"], "end": item["end"], "start_time": None,
            "end_time": None, "venue": item.get("venue"), "url": None,
            "description": f"CSS activity · {item['css']['chip']}" if item.get("css") else "", "tags": []}


def birthday_event(user_id, name, month, day, year):
    """A yearly all-day event. `year` only picks the first occurrence shown; no birth year exists.
    Feb 29 repeats on the last day of February (the 28th in a common year), as the app does."""
    if (month, day) == (2, 29):
        first = date(year, 2, 28) if year % 4 else date(year, 2, 29)
        rule = "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=-1"
    else:
        first = date(year, month, day)
        rule = "FREQ=YEARLY"
    return {"uid": f"birthday-{user_id}@officeconnect", "sequence": 0, "title": f"🎂 {name}",
            "status": "confirmed", "start": first.isoformat(), "end": first.isoformat(),
            "rrule": rule, "transparent": True}


def attachment(events, name="calendar.ics"):
    """(filename, mime, bytes) for mailer.send(attachments=[...])."""
    return (name, "text/calendar; method=PUBLISH; charset=utf-8",
            vcalendar(events, method="PUBLISH").encode("utf-8"))
