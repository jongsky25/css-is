"""Travel filing bell rows (docs/TRAVEL_FILING_PLAN.md section 6, T3).

One cheap, per-user query: how many of the person's open filings are due soon or overdue, and how
many submitted cash advances still need a liquidation. Admin Unit members also see the flags
waiting to be verified (the queue itself arrives in T6, so the line only shows once a flag exists).
Never raises into the caller's page: app.py wraps this in try/except as it does rooms_notify."""
from __future__ import annotations
from datetime import timedelta

import rooms
import storage as st
import travel

LEAD_DEFAULT = 2


def _lead_days(conn) -> int:
    """The same knob the reminder email uses (/admin/email Timing), clamped to 1..14."""
    try:
        n = int(st.get_setting(conn, "email_param.travel_filing_lead_days", str(LEAD_DEFAULT)))
    except (TypeError, ValueError):
        n = LEAD_DEFAULT
    return max(1, min(n, 14))


def _plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def bell_rows(conn, user_id, today):
    if not travel.enabled(conn):
        return []
    today_iso = today.isoformat()
    horizon = (today + timedelta(days=_lead_days(conn))).isoformat()
    soon, late, owed = conn.execute(
        """SELECT COALESCE(SUM(status IN ('open','ready') AND deadline_date IS NOT NULL
                                AND deadline_date>=? AND deadline_date<=?), 0),
                  COALESCE(SUM(status IN ('open','ready') AND deadline_date IS NOT NULL
                                AND deadline_date<?), 0),
                  COALESCE(SUM(kind='ca' AND status='submitted' AND act_end<?
                                AND NOT EXISTS (SELECT 1 FROM travel_filing l WHERE l.kind='liquidation'
                                                AND l.ca_filing_id=travel_filing.id AND l.status<>'withdrawn')), 0)
           FROM travel_filing WHERE user_id=?""",
        (today_iso, horizon, today_iso, today_iso, user_id)).fetchone()
    rows = []
    if late:
        rows.append({"text": f"{_plural(late, 'travel claim is', 'travel claims are')} overdue",
                     "url": "/travel", "count": late})
    if soon:
        rows.append({"text": f"{_plural(soon, 'travel claim', 'travel claims')} due soon",
                     "url": "/travel", "count": soon})
    if owed:
        rows.append({"text": "A cash advance still needs a liquidation" if owed == 1
                     else f"{owed} cash advances still need a liquidation",
                     "url": "/travel", "count": owed})
    flags = conn.execute("SELECT COUNT(*) FROM travel_flag WHERE state='open'").fetchone()[0]
    if flags:
        user = st.get_admin_user_by_id(conn, user_id)
        if user and rooms.is_room_admin(conn, user):
            rows.append({"text": f"{_plural(flags, 'travel flag', 'travel flags')} to verify",
                         "url": "/admin/travel", "count": flags})
    return rows
