"""Storage, numbering and defaults for an activity's public advisory (the poster itself is drawn by advisory.py).

An advisory belongs to one activity (link tree). It starts from the activity's own details, so a manager edits a
ready draft instead of typing a poster: the headline and body come from the title, dates and venue; the table comes
from the link tree's resource links and the registration window; the QR code points at the link tree.

The advisory number is `YYYY-MMDD-NNN` (issue date, then the day's running count). It is allocated once, when the
advisory is first saved, and never changes; editing raises the revision. A database unique key on (date, count)
means two managers saving at the same moment cannot receive the same number.

Nothing here reads attendees or any personal data. Who may manage an activity is decided by the routes."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import advisory
import certificate as cert
import storage as st
import tzutil as tz

CONTACT = ("contact_name", "contact_phone", "contact_email")
DEFAULT_EMAIL = "blhsd@doh.gov.ph"
_SETTING = "advisory.default_{}"                       # the last contact used, offered on the next advisory
COLUMNS = ("headline", "attention", "body", "rows_json", "qr_url") + CONTACT


def format_number(day, seq: int) -> str:
    return f"{day.year}-{day.month:02d}{day.day:02d}-{seq:03d}"


def _row(conn, event_id):
    cur = conn.execute("SELECT * FROM event_advisory WHERE event_id=?", (event_id,))
    r = cur.fetchone()
    if not r:
        return None
    out = dict(zip([c[0] for c in cur.description], r))
    try:
        out["rows"] = [tuple(x) for x in json.loads(out.pop("rows_json") or "[]")]
    except ValueError:
        out["rows"] = []
    out["published"] = bool(out["published"])
    return out


def get(conn, event_id):
    """The saved advisory as a dict (rows as (label, value) pairs), or None."""
    return _row(conn, event_id)


def public_summary(conn, event_id):
    """What the public link tree needs, only when the advisory is published: number, headline and revision."""
    a = _row(conn, event_id)
    if not a or not a["published"]:
        return None
    return {"number": a["number"], "headline": a["headline"], "revision": a["revision"]}


def _deadline_text(close_at):
    """'Nov 20, 12:00 NN' from an ISO datetime, or '' when there is none."""
    try:
        d = datetime.fromisoformat(str(close_at).strip()[:19])
    except ValueError:
        return ""
    hour = d.strftime("%I:%M").lstrip("0")
    suffix = "NN" if (d.hour, d.minute) == (12, 0) else d.strftime("%p")
    return f"{d.strftime('%b')} {d.day}, {hour} {suffix}"


def dates_text(ev) -> str:
    return cert._long_date_range(cert._parse_date(ev.get("event_date")), cert._parse_date(ev.get("end_date"))).replace("–", "-")


def defaults(conn, ev, qr_url: str) -> dict:
    """A first draft from the activity's link-tree details. Every field stays editable."""
    title = (ev.get("title") or "").strip()
    when = dates_text(ev)
    venue = (ev.get("venue") or "").strip()
    online = (ev.get("modality") or "f2f") == "online"
    place = f", {'via' if online else 'at'} {venue}" if venue else ""
    headline = f"{title} on {when}" if when else title
    body = (f"We are pleased to announce **{title}**" + (f" happening on **{when}**" if when else "") + place + ". "
            "Please see the important deadlines and links below.")
    rows = []
    if st.get_event_forms(conn, ev["id"]):
        window = st.get_event_window(conn, ev["id"]) or {}
        due = _deadline_text(window.get("close_at"))
        rows.append((f"Registration{f' (Due {due})' if due else ''}", qr_url))
    for link in st.list_event_links(conn, ev["id"]):
        if not link["visible_after_done"] and link["url"]:
            rows.append((link["label"], link["url"]))
    out = {"headline": headline, "attention": "", "body": body, "rows": rows[:advisory.MAX_ROWS], "qr_url": qr_url}
    for key in CONTACT:
        saved = st.get_setting(conn, _SETTING.format(key), "")
        out[key] = saved or (DEFAULT_EMAIL if key == "contact_email" else "")
    return out


def poster_fields(stored: dict, number: str) -> dict:
    """The dict advisory.py draws, from a stored advisory or a form."""
    out = {k: stored.get(k, "") for k in ("headline", "attention", "body", "qr_url") + CONTACT}
    out["rows"] = stored.get("rows") or []
    out["number"] = number
    out["link_text"] = stored.get("qr_url", "")
    return out


def validate(fields: dict, number: str = "2026-0101-001") -> str:
    """'' when the advisory is acceptable, otherwise a plain sentence for the person editing it."""
    clean = advisory.normalise(poster_fields(fields, number))
    if not clean["headline"]:
        return "Add a headline."
    if not clean["contact_name"]:
        return "Add a contact person for queries."
    try:
        advisory.render_png(poster_fields(fields, number), 0.25)
    except advisory.AdvisoryTooLong as e:
        return str(e)
    return ""


def save(conn, ev, fields: dict, user: dict, *, today=None) -> dict:
    """Create the advisory (allocating its number) or update it; returns the saved advisory. The caller has
    already checked permission and `validate`."""
    clean = advisory.normalise(poster_fields(fields, "-"))
    now, who = tz.now_iso(), (user or {}).get("username")
    values = {"headline": clean["headline"], "attention": clean["attention"], "body": clean["body"],
              "rows_json": json.dumps(clean["rows"]), "qr_url": clean["qr_url"],
              **{k: clean[k] for k in CONTACT}}
    existing = _row(conn, ev["id"])
    if existing:
        changed = any(existing.get(k if k != "rows_json" else "rows") != (v if k != "rows_json" else [tuple(r) for r in clean["rows"]])
                      for k, v in values.items())
        if changed:
            conn.execute("UPDATE event_advisory SET " + ", ".join(f"{k}=?" for k in values) +
                         ", revision=revision+1, updated_by=?, updated_at=? WHERE event_id=?",
                         (*values.values(), who, now, ev["id"]))
    else:
        day = today or tz.today_local()
        for _ in range(6):
            seq = conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM event_advisory WHERE seq_date=?",
                               (day.isoformat(),)).fetchone()[0]
            try:
                conn.execute("INSERT INTO event_advisory(event_id, number, seq_date, seq, " + ", ".join(values) +
                             ", created_by, created_at, updated_by, updated_at) VALUES (?,?,?,?," +
                             ",".join("?" * len(values)) + ",?,?,?,?)",
                             (ev["id"], format_number(day, seq), day.isoformat(), seq, *values.values(), who, now, who, now))
                break
            except sqlite3.IntegrityError:                 # another manager took this count a moment ago: take the next
                conn.rollback()
        else:
            raise RuntimeError("Could not allocate an advisory number.")
    for key in CONTACT:                                    # offer the same contact next time
        if clean[key]:
            conn.execute("INSERT INTO app_setting(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (_SETTING.format(key), clean[key]))
    conn.commit()
    return _row(conn, ev["id"])


def set_published(conn, event_id, published: bool) -> bool:
    """Show or withdraw the advisory on the public link tree. False when there is no saved advisory yet."""
    cur = conn.execute("UPDATE event_advisory SET published=?, published_at=CASE WHEN ? THEN ? ELSE published_at END "
                       "WHERE event_id=?", (1 if published else 0, 1 if published else 0, tz.now_iso(), event_id))
    conn.commit()
    return cur.rowcount > 0
