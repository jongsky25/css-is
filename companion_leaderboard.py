"""The companion leaderboard (spot feedback #196): every pet, ranked, to encourage the wellness break.

Read-only and derived on every call from the wellness claims, reflections, badges and care streaks, like the rest of the
gamification layer, so nothing here can drift from the record. People appear by their pet's name only. The viewer picks
who is compared (their section, division or the whole bureau) and over what period (this month, this quarter, all time).

Points follow the formula the pet's own growth uses: a completed break +10, a reflection +5, a week with the full two
hours +5. The all-time board adds the current wellness-streak bonus (+2 a week), so it matches the points on the hub; a
month or quarter is what was earned inside it, with no streak bonus, since a streak is a current state, not a period's.
Ties on points are broken by the companion care streak, then by badges."""
from __future__ import annotations
from datetime import date, timedelta

import storage as st
import tzutil as tz

PERIODS = (("month", "This month"), ("quarter", "This quarter"), ("all", "All time"))
SCOPES = (("section", "My section"), ("division", "My division"), ("bureau", "Whole bureau"))
DEFAULT_PERIOD, DEFAULT_SCOPE = "month", "bureau"


def period_range(period, today=None):
    """(start, end) ISO dates of the period, or (None, None) for all time. An unknown period is the default one."""
    today = today or tz.today_local()
    if period == "all":
        return None, None
    if period == "quarter":
        first_month = 3 * ((today.month - 1) // 3) + 1
        start = date(today.year, first_month, 1)
        end = date(today.year + (first_month == 10), (first_month + 3 - 1) % 12 + 1, 1) - timedelta(days=1)
    else:
        start = date(today.year, today.month, 1)
        end = date(today.year + (today.month == 12), today.month % 12 + 1, 1) - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def clean_choice(value, options, default):
    return value if value in {k for k, _ in options} else default


def scope_prefix(org_path, scope):
    """The directory path a person must sit under to be compared with the viewer ('' means everyone)."""
    parts = [p for p in (org_path or "").split("/") if p]
    if scope == "section" and len(parts) >= 3:
        return "/".join(parts)
    if scope == "division" and len(parts) >= 2:
        return "/".join(parts[:2])
    return ""


def _in_scope(path, prefix):
    return not prefix or (path or "") == prefix or (path or "").startswith(prefix + "/")


def _streak(weeks, this_week):
    """Consecutive weeks with a completed break, counted back from this week (an unfinished week does not break it)."""
    cur = date.fromisoformat(this_week)
    if cur.isoformat() not in weeks:
        cur -= timedelta(days=7)
    n = 0
    while cur.isoformat() in weeks:
        n += 1
        cur -= timedelta(days=7)
    return n


def _by_user(conn, sql, params=()):
    return {r[0]: r[1:] for r in conn.execute(sql, params)}


def board(conn, viewer, period=DEFAULT_PERIOD, scope=DEFAULT_SCOPE, today=None):
    """{rows, me, period, scope, ...}: one row per active person in the directory within the scope, best first.

    A row: rank, pet (name), species label, stage and its name, points, breaks, week streak, care streak, badges, is_me.
    Ranks are shared on a tie (1, 2, 2, 4)."""
    today = today or tz.today_local()
    period = clean_choice(period, PERIODS, DEFAULT_PERIOD)
    scope = clean_choice(scope, SCOPES, DEFAULT_SCOPE)
    start, end = period_range(period, today)
    me = (st.get_user_profile(conn, viewer["id"]) or {}) if viewer else {}
    prefix = scope_prefix(me.get("org_path"), scope)
    if scope != "bureau" and not prefix:                 # no section or division on file: fall back to everyone
        scope = "bureau"

    people = conn.execute(
        "SELECT a.id, a.avatar_kind, a.avatar_name, a.avatar_care_streak, ou.path "
        "FROM admin_user a JOIN resource_person rp ON rp.id=a.rp_id LEFT JOIN org_unit ou ON ou.id=rp.org_unit_id "
        "WHERE a.active=1").fetchall()
    people = [p for p in people if _in_scope(p[4], prefix)]

    window, wp = ("", ())
    if start:
        window, wp = " AND c.break_date BETWEEN ? AND ?", (start, end)
    done = _by_user(conn, "SELECT c.user_id, COUNT(*) FROM wellness_claim c WHERE c.status='completed'" + window
                    + " GROUP BY c.user_id", wp)
    refl = _by_user(conn, "SELECT c.user_id, COUNT(*) FROM wellness_reflection r JOIN wellness_claim c ON c.id=r.claim_id "
                          "WHERE 1=1" + window + " GROUP BY c.user_id", wp)
    full = _by_user(conn, "SELECT user_id, COUNT(*) FROM (SELECT c.user_id, c.week_start FROM wellness_claim c "
                          "WHERE c.status='completed'" + window + " GROUP BY c.user_id, c.week_start HAVING SUM(c.hours) >= ?) "
                          "GROUP BY user_id", wp + (st.WELLNESS_WEEKLY_HOURS,))
    badges = _by_user(conn, "SELECT user_id, COUNT(*) FROM wellness_badge GROUP BY user_id")
    # all-time facts for the stage and the streak, whatever the period shown
    weeks, all_points = {}, {}
    for uid, wk in conn.execute("SELECT DISTINCT user_id, week_start FROM wellness_claim WHERE status='completed'"):
        weeks.setdefault(uid, set()).add(wk)
    for uid, n in conn.execute("SELECT user_id, COUNT(*) FROM wellness_claim WHERE status='completed' GROUP BY user_id"):
        all_points[uid] = n * st.WELLNESS_PTS_BREAK
    for uid, n in conn.execute("SELECT c.user_id, COUNT(*) FROM wellness_reflection r JOIN wellness_claim c ON c.id=r.claim_id "
                               "GROUP BY c.user_id"):
        all_points[uid] = all_points.get(uid, 0) + n * st.WELLNESS_PTS_REFLECTION
    for uid, n in conn.execute("SELECT user_id, COUNT(*) FROM (SELECT user_id, week_start FROM wellness_claim "
                               "WHERE status='completed' GROUP BY user_id, week_start HAVING SUM(hours) >= ?) GROUP BY user_id",
                               (st.WELLNESS_WEEKLY_HOURS,)):
        all_points[uid] = all_points.get(uid, 0) + n * st.WELLNESS_PTS_FULL_WEEK
    this_week = st.wellness_week_start(today)

    rows = []
    for uid, kind, name, care, _path in people:
        kind = kind if kind in st.AVATAR_KEYS else st.AVATAR_DEFAULT
        streak = _streak(weeks.get(uid, set()), this_week)
        total = all_points.get(uid, 0) + streak * st.WELLNESS_PTS_STREAK_WEEK
        stage = min(sum(1 for t in st.WELLNESS_LEVELS if total >= t), len(st.WELLNESS_STAGE_NAMES))
        if period == "all":
            points = total
        else:
            points = ((done.get(uid) or (0,))[0] * st.WELLNESS_PTS_BREAK + (refl.get(uid) or (0,))[0] * st.WELLNESS_PTS_REFLECTION
                      + (full.get(uid) or (0,))[0] * st.WELLNESS_PTS_FULL_WEEK)
        species = next((a["label"] for a in st.AVATAR_CATALOG if a["key"] == kind), "Companion")
        rows.append({"user_id": uid, "kind": kind, "pet": (name or "").strip() or species, "species": species,
                     "stage": stage, "stage_name": st.avatar_stage_name(kind, stage), "points": points,
                     "breaks": (done.get(uid) or (0,))[0], "streak": streak, "care": care or 0,
                     "badges": (badges.get(uid) or (0,))[0], "is_me": uid == (viewer or {}).get("id")})
    rows.sort(key=lambda r: (-r["points"], -r["care"], -r["badges"], r["pet"].lower(), r["user_id"]))
    prev, prev_rank = None, 0
    for i, r in enumerate(rows, 1):
        key = (r["points"], r["care"], r["badges"])
        r["rank"] = prev_rank if key == prev else i
        prev, prev_rank = key, r["rank"]
    return {"rows": rows, "me": next((r for r in rows if r["is_me"]), None), "period": period, "scope": scope,
            "period_label": dict(PERIODS)[period], "scope_label": dict(SCOPES)[scope], "start": start, "end": end,
            "scope_options": [(k, v) for k, v in SCOPES if k == "bureau" or scope_prefix(me.get("org_path"), k)]}


TOP_CHOICES = (("5", "Top 5"), ("10", "Top 10"), ("all", "Everyone"))
DEFAULT_TOP = "5"


def clean_top(value):
    """How many rows the home card shows: '5', '10' or 'all' (anything else is the default)."""
    return value if value in {k for k, _ in TOP_CHOICES} else DEFAULT_TOP


def home_card(conn, viewer, today=None, top=5, period=DEFAULT_PERIOD, scope=DEFAULT_SCOPE):
    """What the home page shows: the top few (5 by default, or 10 or everyone), and the viewer's own row even if outside them.
    The period and group can be changed from the card (spot feedback #196); the full page has the same choices."""
    b = board(conn, viewer, period, scope, today)
    top = str(top)
    n = None if top == "all" else (int(top) if top.isdigit() and 0 < int(top) <= 500 else int(DEFAULT_TOP))
    shown = b["rows"] if n is None else b["rows"][:n]
    if b["me"] and b["me"] not in shown:
        shown = shown + [b["me"]]
    return {**b, "shown": shown, "total": len(b["rows"]), "top": "all" if n is None else str(n),
            "top_options": TOP_CHOICES, "more": n is not None and len(b["rows"]) > n}
