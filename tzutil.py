"""
tzutil — single source of truth for the app's local wall-clock.
================================================================

Every persisted timestamp ("logged at", "submitted at", the audit-trail `ts`,
backup filenames…) and every "is the survey open right now?" comparison uses
local Philippine time (Asia/Manila, UTC+8). Times are stored as *naive* ISO
strings so they text-compare with the other naive strings already in the DB.

The catch: the server may run in UTC (e.g. a Hugging Face Space). A bare
`datetime.now()` returns the SERVER's wall clock, so on a UTC host every stamp
lands ~8 h behind local — which makes the audit trail and every time log read a
day behind whenever the action happens after PH midnight (UTC afternoon). That
is exactly the "it still says June 16 but I edited it just now" bug.

So nothing in the app calls `datetime.now()` directly for a current-moment
read — it all goes through here. Override the offset (hours east of UTC) with
the CSS_TZ_OFFSET env var (default 8 for Asia/Manila).
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone

# Hours east of UTC. 8 = Asia/Manila. Read once at import.
LOCAL_TZ = timezone(timedelta(hours=int(os.environ.get("CSS_TZ_OFFSET", "8"))))


def now_local() -> datetime:
    """Current local wall-clock as a *naive* datetime (tzinfo stripped so it
    compares with the naive ISO strings stored in the DB)."""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def now_iso() -> str:
    """Current local wall-clock as an ISO string, seconds precision — the
    canonical stamp written into every time-log column."""
    return now_local().isoformat(timespec="seconds")


def today_local():
    """Today's date in local time."""
    return now_local().date()
