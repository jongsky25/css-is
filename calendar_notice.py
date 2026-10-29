"""Sending a notice of meeting from a calendar item (the "Send notice of meeting" action).

The Google Docs draft of a notice stays the formal paper. This sends the same facts, plus the agenda the sender types,
by email to the people on the item (and any extra addresses they add, for people from other offices), and keeps a record
of who was sent what and when. Each send is audited. Delivery runs after the page has answered, one email at a time,
and the result of each is kept per recipient, because the mail relay can take seconds per message."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

import mailer
import rooms
import storage as st
import tzutil as tz

AGENDA_MAX = 2000
EXTRA_MAX = 20
RESEND_GAP_SECONDS = 60
_EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
FEATURE = "meeting_notice"


def fingerprint(conn, e) -> str:
    """What the invited people were told: when, where, the link, and the live room booking. A change in any of
    these after a notice went out means the notice is out of date."""
    held = sorted((r["id"], r["day"], r["status"]) for r in rooms.reservations_for_entry(conn, e["id"])
                  if r["status"] in ("requested", "approved"))
    basis = [e["start_date"], e["end_date"], e["start_time"], e["end_time"], e["time_note"], e["venue"],
             e["modality"], e["meeting_url"], e["status"], held]
    return hashlib.sha1(json.dumps(basis, default=str).encode()).hexdigest()[:16]


def can_send(user, e) -> bool:
    """The person who made the item, anyone on it, and section managers or admins. Visibility alone is not enough:
    this emails other people."""
    if not user or e["status"] == "cancelled":
        return False
    if user.get("role") in ("admin", "section_manager"):
        return True
    return user.get("username") == e.get("created_by") or any(p["user_id"] == user["id"] for p in e["people"])


def parse_extra(text):
    """(addresses, error) from one address per line (commas and semicolons also split)."""
    out, seen = [], set()
    for raw in re.split(r"[\n,;]+", str(text or "")):
        a = raw.strip().lower()
        if not a:
            continue
        if not _EMAIL.match(a) or len(a) > 120:
            return [], f"“{raw.strip()[:60]}” is not an email address."
        if a not in seen:
            seen.add(a)
            out.append(a)
    if len(out) > EXTRA_MAX:
        return [], f"Add at most {EXTRA_MAX} extra addresses."
    return out, ""


def clean_agenda(text) -> str:
    return "\n".join(" ".join(l.split()) for l in str(text or "").replace("\r", "").split("\n")
                     if l.strip())[:AGENDA_MAX]


def people_recipients(conn, e):
    """[(user_id, name, email)] for the active accounts on the item, in the order they were added."""
    out = []
    for p in e["people"]:
        acct = st.get_admin_user_by_id(conn, p["user_id"])
        if not acct or not acct.get("active") or not acct.get("username"):
            continue
        name = (st.get_user_profile(conn, p["user_id"]) or {}).get("person_name") or ""
        out.append((p["user_id"], name, acct["username"]))
    return out


def history(conn, entry_id, limit=5):
    """The notices sent for an item, newest first, each with its recipients' results."""
    rows = conn.execute(
        "SELECT id, sent_by, sent_at, agenda, fingerprint FROM calendar_entry_notice WHERE entry_id=? "
        "ORDER BY id DESC LIMIT ?", (entry_id, limit)).fetchall()
    out = []
    for nid, by, at, agenda, fp in rows:
        to = conn.execute("SELECT name, email, status FROM calendar_entry_notice_to WHERE notice_id=? ORDER BY id",
                          (nid,)).fetchall()
        counts = {}
        for _n, _e, s in to:
            counts[s] = counts.get(s, 0) + 1
        out.append({"id": nid, "by": by, "at": at, "agenda": agenda, "fingerprint": fp,
                    "to": [{"name": n, "email": em, "status": s} for n, em, s in to], "counts": counts})
    return out


def queue(conn, e, user, agenda, extra, base_url):
    """Record one notice and its recipients as 'queued', audit it, and return its id (or raise ValueError with a
    sentence for the person). Nothing is sent here: `deliver` does that."""
    last = conn.execute("SELECT sent_at FROM calendar_entry_notice WHERE entry_id=? AND sent_by=? ORDER BY id DESC LIMIT 1",
                        (e["id"], user["username"])).fetchone()
    if last and (tz.now_local() - datetime.fromisoformat(last[0])).total_seconds() < RESEND_GAP_SECONDS:
        raise ValueError("A notice was just sent for this item. Wait a minute before sending another.")
    people = people_recipients(conn, e)
    mine = {em.lower() for _u, _n, em in people}
    extra = [a for a in extra if a not in mine]
    if not people and not extra:
        raise ValueError("Nobody to send it to: add people to the item, or add an email address below.")
    now = tz.now_iso()
    cur = conn.execute(
        "INSERT INTO calendar_entry_notice(entry_id, sent_by, sent_at, agenda, fingerprint, base_url) VALUES (?,?,?,?,?,?)",
        (e["id"], user["username"], now, agenda, fingerprint(conn, e), base_url))
    nid = cur.lastrowid
    for uid, name, em in people:
        conn.execute("INSERT INTO calendar_entry_notice_to(notice_id, user_id, name, email, status) VALUES (?,?,?,?,'queued')",
                     (nid, uid, name, em))
    for em in extra:
        conn.execute("INSERT INTO calendar_entry_notice_to(notice_id, user_id, name, email, status) VALUES (?,NULL,'',?,'queued')",
                     (nid, em))
    st.audit(conn, user["username"], "meeting_notice_sent", target_type="calendar_entry", target_id=e["id"],
             summary=f"Notice of meeting “{e['title'][:80]}” sent to {len(people)} on the item and {len(extra)} extra address(es).",
             after=json.dumps({"notice_id": nid, "to": [em for _u, _n, em in people] + extra}), commit=False)
    conn.commit()
    return nid


def deliver(get_conn, notice_id, send=None):
    """Send each queued recipient their email and record the result. Runs after the response, on its own connection.
    Never raises: a failure is recorded against the recipient."""
    send = send or mailer.send
    conn = get_conn()
    try:
        n = conn.execute("SELECT entry_id, sent_by, agenda, base_url FROM calendar_entry_notice WHERE id=?",
                         (notice_id,)).fetchone()
        e = st.cal_get(conn, n[0]) if n else None
        if e is None:
            return
        import activity_docs
        when, where = activity_docs.when_text(e), activity_docs.where_text(e)
        link = f"{n[3]}/calendar/entries/{e['id']}"
        sender = (conn.execute("SELECT rp.name FROM admin_user a LEFT JOIN resource_person rp ON rp.id=a.rp_id "
                               "WHERE a.username=?", (n[1],)).fetchone() or [None])[0] or n[1]
        others = [l for l in activity_docs.get_visitors(conn, e["id"]).split("\n") if l and l.lower() != "none"]
        for rid, name, email in conn.execute(
                "SELECT id, name, email FROM calendar_entry_notice_to WHERE notice_id=? AND status='queued' ORDER BY id",
                (notice_id,)).fetchall():
            try:
                if not st.email_feature_enabled(conn, FEATURE):
                    status, detail = "skipped_off", None
                else:
                    subj, body, html = mailer.meeting_notice_message(
                        name.split()[0] if name else "", e["title"], when, where, (e.get("meeting_url") or "").strip(),
                        n[2], others, sender, link)
                    result = send(email, subj, body, html=html)
                    status, detail = mailer.send_status(result), result.get("detail")
                    st.log_email_send(conn, FEATURE, email, subj, status, detail)
            except Exception as ex:                          # noqa: BLE001 - recorded, never raised
                status, detail = "failed", str(ex)[:200]
            conn.execute("UPDATE calendar_entry_notice_to SET status=?, detail=?, done_at=? WHERE id=?",
                         (status, detail, tz.now_iso(), rid))
            conn.commit()
    finally:
        conn.close()
