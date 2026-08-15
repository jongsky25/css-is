"""Office Connect landing page — the Team View payload.

ONE function, `team_view_data`, assembles everything `/` renders: three panels
(Wellness, AWA, CSS), each with a TEAM view and a PERSONAL view, plus the
greeting and the scope label. Pure assembly over storage + dashboard_insights;
no HTML, no routes.

Why a separate module:
  * `dashboard_insights` is deliberately conn-free and pure — it imports only
    the stdlib, numpy/pandas and css_is_engine. A conn-taking, three-subsystem
    assembler does not belong there.
  * `app.py` is already ~13.8k lines, and this is how it got there.
  * `storage.py` has the conn but knows nothing about the atoms cache.

The cache primitives (`get_atoms`, `view_memo`) live in app.py and are INJECTED
rather than imported, which keeps this module free of a circular import and lets
tests pass a no-op memo.

SCOPE IS THE SAFETY-CRITICAL PART. This page has no chief-only route guard —
every signed-in user sees their own team by design — so it resolves scope with
`storage.team_scope_for_user`, which distinguishes "no team" (an account with no
directory link) from "the whole bureau" (an admin). `_org_scope_for_user`
collapses both onto None, and `_path_in_scope(path, None)` is True for
everything, so using it directly here would show an unlinked account every
wellness and work-arrangement filing in the bureau. When kind == "none" the team
builders are not called at all and every panel's "team" is None.
"""
from __future__ import annotations

from datetime import timedelta

import css_is_engine as eng
import dashboard_insights as di
import storage as st
import tzutil as tz

# How far back "recent activity" looks. Matches the 90-day cut the /css
# "recently concluded" strip already uses, so the two agree.
WINDOW_DAYS = 90
RECENT_N = 6
UPCOMING_N = 5

# Score band -> semantic tone token. band7() returns a bare label string, so the
# mapping is ours to own. Never a colour: the template resolves tone -> var(--x).
_BAND_TONE = {"Excellent": "green", "Good": "green", "Fair": "amber", "Poor": "red"}


def _tone_for_band(band):
    return _BAND_TONE.get(band or "", "soft")


# --------------------------------------------------------------------------
# people
# --------------------------------------------------------------------------

def _initials(name):
    parts = [p for p in (name or "").replace(",", " ").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def _face(row, *, me_id=None):
    """The uniform person-mark every panel draws.

    Picture precedence: the DIRECTORY photo (/photo/{rp_id}), then the person's
    companion avatar, then initials. A teammate's *account* photo is
    deliberately unreachable — /me/photo is own-photo-only by design ("no id in
    the URL to enumerate", app.py) — so the companion is the fallback for
    everyone else, which conveniently puts the avatar people are growing in
    front of the team that shares it.
    """
    name = row.get("name") or row.get("username") or "—"
    rp_id = row.get("rp_id")
    return {
        "user_id": row.get("user_id"),
        "name": name,
        "initials": _initials(name),
        "section": row.get("section") or "",
        "photo_url": f"/photo/{rp_id}" if (rp_id and row.get("has_photo")) else None,
        "avatar_kind": row.get("avatar_kind") or st.AVATAR_DEFAULT,
        "is_me": row.get("user_id") == me_id,
    }


# --------------------------------------------------------------------------
# the activity index — memoised, bureau-wide, viewer-INDEPENDENT
# --------------------------------------------------------------------------

def _activity_index(conn, atoms, view_memo, today):
    """A flat lookup over every scored activity, built once per atoms key.

    Deliberately scope-free. Filtering happens per-request in Python against the
    viewer's own resolved scope, so there is no per-team cache entry to mis-key
    — which is what makes a cache bug here incapable of leaking one section's
    data to another.

    `build_events` carries no org path and no creator (it groups atoms, not
    rows), so both are joined back on from list_activity_instances.
    """
    insts = st.list_activity_instances(conn)
    events = view_memo("events", ("", "all"),
                       lambda: di.build_events(atoms, insts))
    lead = {i["id"]: i.get("lead_path") for i in insts}
    made = {i["id"]: i.get("created_by") for i in insts}

    by_event, by_rp, by_creator, recent = {}, {}, {}, []
    cut = (today - timedelta(days=WINDOW_DAYS)).isoformat()
    for e in events:
        ids = e.get("instance_ids") or []
        rp_ids = {s["rp_id"] for s in e.get("speakers") or [] if s.get("rp_id")}
        creators = {made[i] for i in ids if made.get(i)}
        paths = {lead[i] for i in ids if lead.get(i)}
        f2 = e.get("f2")
        speakers = [s for s in (e.get("speakers") or []) if not s.get("hidden")]
        top = speakers[0] if speakers else None
        if f2:
            score, shown, band, kind = (f2["overall"], f2["overall_shown"],
                                        f2["band"], "activity")
        elif top:
            score, shown, band, kind = (top["value"], top["shown"],
                                        top["band"], "speaker")
        else:
            score, shown, band, kind = None, None, None, None
        row = {
            "id": e["id"], "name": e["name"], "date": str(e["date"])[:10],
            "venue": e.get("venue") or "", "organizer": e.get("organizer") or "",
            "respondents": e.get("respondents", 0),
            # build_events sets no low-n flag on its f2 block, so derive it here.
            # Shown-but-muted, never hidden: hiding is how people conclude the
            # system lost their activity.
            "low_n": e.get("respondents", 0) < eng.N_MIN,
            "score": score, "shown": shown, "band": band,
            "tone": _tone_for_band(band), "score_kind": kind,
            # An f3-only activity has no Form-2 report and /reports/activities/{id}
            # 404s on it — the same fallback /css already uses.
            "url": (f"/reports/activities/{e['id']}" if f2
                    else f"/reports?type=3&activity={e['id']}"),
            "f3_only": not f2,
            "speaker_names": [s["name"] for s in speakers],
            "rp_ids": rp_ids, "creators": creators, "lead_paths": paths,
        }
        by_event[e["id"]] = row
        for rp in rp_ids:
            by_rp.setdefault(rp, []).append(e["id"])
        for u in creators:
            by_creator.setdefault(u, []).append(e["id"])
        if row["date"] >= cut:
            recent.append(e["id"])
    # build_events is already newest-first; keep that order.
    return {"by_event": by_event, "by_rp": by_rp, "by_creator": by_creator,
            "recent": recent,
            # instance_id -> org path, kept so the upcoming feed (which cannot
            # come from build_events — see _upcoming) can scope-filter without
            # re-running the instances query.
            "lead": lead}


def _upcoming(conn, index, scope, kind, *, limit=UPCOMING_N):
    """Activities still ahead of us, scope-filtered.

    NOT from the index: build_events drops any event with zero respondents, and
    an activity that hasn't happened yet has none by definition. upcoming_events
    returns form_instance ids, so the org path is joined back on the same way.
    """
    rows = st.upcoming_events(conn, limit=limit * 4)
    if not rows:
        return []
    lead = index["lead"]
    out = []
    for r in rows:
        path = lead.get(r["id"])
        if kind == "unit" and not st._path_in_scope(path, scope):
            continue
        out.append({"id": r["id"], "name": r.get("topic") or "Untitled activity",
                    "date": str(r.get("event_date"))[:10],
                    "venue": r.get("venue") or "",
                    "registered": r.get("n_registered", 0),
                    "speakers": r.get("speakers") or [],
                    "url": (f"/monitor/{r['event_token']}" if r.get("event_token")
                            else "/monitor")})
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------
# panels
# --------------------------------------------------------------------------

def _css_panel(conn, index, *, me, roll_rows, scope, kind):
    """Activities, personal and team.

    THE PREDICATE IS THE WHOLE DESIGN HERE. There is no staff->activity
    attendance relation in this schema: `attendee` rows are external registrants
    keyed by event + email with no admin_user link. A staff member is tied to an
    activity only as SPEAKER (form_instance.rp_id), CREATOR (created_by, a
    username) or via the ORGANISING UNIT (lead_org_id).

    So personal = spoke OR created. Organiser-unit is deliberately excluded from
    the personal view: "my section ran it" is not "I was involved", and blurring
    the two is exactly the misleading claim to avoid. The team view adds it,
    because there it means precisely what it says.
    """
    by_event = index["by_event"]

    def _row(eid, roles):
        r = dict(by_event[eid])
        r.pop("rp_ids", None), r.pop("creators", None), r.pop("lead_paths", None)
        r["roles"] = sorted(roles)
        return r

    # ---- personal -------------------------------------------------------
    mine = {}
    for eid in index["by_rp"].get(me.get("rp_id"), []) if me.get("rp_id") else []:
        mine.setdefault(eid, set()).add("spoke")
    for eid in index["by_creator"].get(me.get("username"), []):
        mine.setdefault(eid, set()).add("ran")
    personal_rows = [_row(eid, roles) for eid, roles in mine.items()
                     if eid in index["recent"]]
    personal_rows.sort(key=lambda r: r["date"], reverse=True)

    personal = {
        "rows": personal_rows[:RECENT_N],
        "total": len(personal_rows),
        "linked": bool(me.get("rp_id")),
        "window_days": WINDOW_DAYS,
    }

    # ---- team -----------------------------------------------------------
    team = None
    if kind != "none":
        team_rp_ids = {r["rp_id"] for r in roll_rows if r.get("rp_id")}
        team_users = {r["username"] for r in roll_rows if r.get("username")}
        names = {r["rp_id"]: r["name"] for r in roll_rows if r.get("rp_id")}
        team_rows = []
        for eid in index["recent"]:
            ev = by_event[eid]
            roles = set()
            if kind == "bureau" or any(st._path_in_scope(p, scope)
                                       for p in ev["lead_paths"]):
                roles.add("unit")
            spoke = ev["rp_ids"] & team_rp_ids
            if spoke:
                roles.add("spoke")
            if ev["creators"] & team_users:
                roles.add("ran")
            if not roles:
                continue
            row = _row(eid, roles)
            row["who"] = sorted(names[r] for r in spoke if r in names)
            team_rows.append(row)
        team = {"rows": team_rows[:RECENT_N], "total": len(team_rows),
                "window_days": WINDOW_DAYS}
    return {"team": team, "personal": personal}


def _wellness_panel(conn, *, me, roll, week_start, kind):
    """This week's break hours — a wall of faces, not a table of names."""
    weekly = st.WELLNESS_WEEKLY_HOURS
    try:
        stats = st.wellness_stats(conn, me["user_id"])
    except Exception:
        stats = None

    personal = {
        "week_start": week_start, "weekly_hours": weekly,
        "stats": stats,
        "used": 0, "left": weekly, "ring": di.ring_geom(0), "state": "none",
    }
    my_row = next((r for r in roll["rows"] if r["user_id"] == me["user_id"]), None)
    if my_row:
        personal.update(_cell(my_row, weekly, me["user_id"]))

    team = None
    if kind != "none":
        cells = [_cell(r, weekly, me["user_id"], face=True) for r in roll["rows"]]
        filed = sum(1 for c in cells if c["state"] != "none")
        team = {
            "week_start": week_start, "weekly_hours": weekly,
            "cells": cells, "people": len(cells), "filed": filed,
            "used": roll["week_used"], "entitled": roll["week_entitled"],
            "pct": roll["week_pct"], "ring": di.ring_geom(roll["week_pct"]),
            "sections": roll["sections"],
            "legend": [{"key": "completed", "label": "Break taken", "tone": "green"},
                       {"key": "approved", "label": "Approved, not yet taken",
                        "tone": "accent"},
                       {"key": "pending", "label": "Waiting on approval",
                        "tone": "amber"},
                       {"key": "none", "label": "Nothing filed", "tone": "soft"}],
            "aria_label": (f"Wellness hours for {len(cells)} people this week: "
                           f"{roll['week_used']} of {roll['week_entitled']}, "
                           f"{roll['week_pct']} percent."),
            "table": {
                "caption": "Wellness break hours this week, by person",
                "headers": ["Person", "Section", "Hours used", "Hours left",
                            "Status"],
                "rows": [[c["name"], c["section"], str(c["used"]),
                          str(c["left"]), c["status_label"]] for c in cells],
            },
        }
    return {"team": team, "personal": personal}


_WELL_STATE = {
    "completed": ("green", "Break taken"),
    "approved": ("accent", "Approved, not yet taken"),
    "pending": ("amber", "Waiting on approval"),
    "none": ("soft", "Nothing filed"),
}


def _cell(row, weekly, me_id, *, face=False):
    """One person's week: hours, state, tone and the ring geometry."""
    used = row["used"]
    if row["completed"]:
        state = "completed"
    elif row["approved"]:
        state = "approved"
    elif row["pending"]:
        state = "pending"
    else:
        state = "none"
    tone, label = _WELL_STATE[state]
    pct = round(used * 100 / weekly) if weekly else 0
    out = {
        "used": used, "left": row["left"], "pending": row["pending"],
        "approved": row["approved"], "completed": row["completed"],
        "reflections": row["reflections"],
        "state": state, "tone": tone, "status_label": label,
        "pct": pct, "ring": di.ring_geom(pct),
        "aria": (f"{row['name']}: {used} of {weekly} hours used — "
                 f"{label.lower()}."),
    }
    if face:
        out.update(_face(row, me_id=me_id))
    else:
        out["name"], out["section"] = row["name"], row.get("section", "")
    return out


_WA_TONE = {"approved": "green", "pending": "amber", "noawa": "accent", "": "soft"}


def _awa_panel_build(conn, *, me, user, today, kind):
    open_ps = st.work_arrangement_open_periods()
    ps_file = open_ps[0] if open_ps else None
    ps_now = st.work_arrangement_period()

    try:
        cur = st.my_work_arrangement_for(conn, me["user_id"], ps_now)
    except Exception:
        cur = None
    in_force = {"period_label": st.work_arrangement_period_label(ps_now),
                "arrangement_label": (cur or {}).get("arrangement_label"),
                "weekday_name": _weekday_name((cur or {}).get("weekday")),
                "status": (cur or {}).get("status"), "filed": bool(cur)}

    if not ps_file:
        return {"team": None,
                "personal": {"state": "none_open", "in_force": in_force,
                             "period_label": None}}

    summary = st.work_arrangement_period_summary(conn, ps_file, user)
    deadline = summary["deadline"]
    days_left = (deadline - today).days
    state = ("closing_today" if days_left == 0
             else "open" if days_left > 0 else "closed")

    mine = next((r for r in summary["roster"] if r["user_id"] == me["user_id"]), None)
    personal = {
        "state": state, "period_label": summary["period_label"],
        "deadline_label": summary["deadline_label"], "days_left": days_left,
        "in_force": in_force,
        "filed": bool(mine and mine["filed"]),
        "noawa": bool(mine and mine.get("noawa")),
        "arrangement_label": (mine or {}).get("arrangement_label"),
        "weekday_name": _weekday_name((mine or {}).get("weekday")),
        "status": (mine or {}).get("status"),
        # Only offer the CTA when there is something to do AND the window is open.
        "can_file": bool(state in ("open", "closing_today")
                         and mine and not mine["filed"] and not mine.get("noawa")),
    }

    team = None
    if kind != "none":
        headcount = summary["headcount"]
        faces = [{**_face(r, me_id=me["user_id"]),
                  "arrangement_label": r["arrangement_label"],
                  "weekday_name": _weekday_name(r["weekday"]),
                  "status": r["status"], "filed": r["filed"],
                  "noawa": r.get("noawa", False),
                  "tone": ("accent" if r.get("noawa")
                           else _WA_TONE.get(r["status"], "soft")),
                  "aria": (f"{r['name']} — "
                           f"{r['arrangement_label'] or 'nothing filed'}"
                           f"{', ' + r['status'] if r['status'] else ''}.")}
                 for r in summary["roster"]]
        pct = round(summary["filed"] * 100 / headcount) if headcount else 0
        team = {
            "state": state, "period_label": summary["period_label"],
            "deadline_label": summary["deadline_label"], "days_left": days_left,
            "headcount": headcount, "filed": summary["filed"],
            "approved": summary["approved"], "pending": summary["pending"],
            "unfiled": summary["unfiled"], "noawa": summary["noawa"],
            "pct": pct, "ring": di.ring_geom(pct), "faces": faces,
            # Bureau-wide, the per-section coverage fan-out is one extra query
            # per section; the counts alone carry the panel and the full weekday
            # chart stays one click away on /work-arrangement/schedule.
            "coverage": (di.bars_geom(summary["totals"], headcount)
                         if kind == "unit" else None),
        }
    return {"team": team, "personal": personal}


def _weekday_name(idx):
    if idx is None:
        return None
    return dict(st.WORK_ARRANGEMENT_WEEKDAYS).get(idx)


# --------------------------------------------------------------------------
# the payload
# --------------------------------------------------------------------------

def team_view_data(conn, user, *, get_atoms, view_memo,
                   today=None, week_start=None):
    """Everything the Office Connect landing page renders, in one pass."""
    today = today or tz.today_local()
    week_start = week_start or st.wellness_week_start(today)

    scope_path, kind = st.team_scope_for_user(conn, user)
    profile = st.get_user_profile(conn, user["id"]) or {}
    me = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user.get("role"),
        "name": profile.get("person_name") or user["username"],
        "rp_id": profile.get("rp_id"),
        "photo_url": profile.get("photo_url"),
        "avatar_kind": profile.get("avatar_kind") or st.AVATAR_DEFAULT,
        "avatar_name": profile.get("avatar_name"),
        "avatar_mood": profile.get("avatar_mood"),
        "initials": _initials(profile.get("person_name") or user["username"]),
    }

    notes = []
    if kind == "none":
        notes.append({
            "key": "unlinked",
            "text": ("Your account isn't linked to a directory record yet, so we "
                     "can't show your team or match you to activities you spoke at."),
            "url": "/me", "cta": "Complete your profile",
        })

    # The team roster, fresh (never memoised — its only sane key is the scope
    # path, which is exactly the hazard, and view_memo's key tracks the atoms,
    # which do not count admin_user: a new hire would go unnoticed).
    roll = ({"rows": [], "sections": [], "week_used": 0, "week_entitled": 0,
             "week_pct": 0, "scope_path": None} if kind == "none"
            else st.wellness_week_rollup(conn, week_start, user))

    atoms = get_atoms(conn)
    index = view_memo("oc_activity_index", (),
                      lambda: _activity_index(conn, atoms, view_memo, today))

    scope_label = ("the whole bureau" if kind == "bureau"
                   else (roll["rows"][0]["section"] if roll["rows"] else "your team")
                   if kind == "unit" else None)

    return {
        "me": me,
        "scope": {"path": scope_path, "kind": kind, "label": scope_label,
                  "size": len(roll["rows"])},
        "panels": {
            "wellness": _wellness_panel(conn, me=me, roll=roll,
                                        week_start=week_start, kind=kind),
            "awa": _awa_panel_build(conn, me=me, user=user, today=today, kind=kind),
            "css": {**_css_panel(conn, index, me=me, roll_rows=roll["rows"],
                                 scope=scope_path, kind=kind),
                    "upcoming": _upcoming(conn, index, scope_path, kind)},
        },
        "notes": notes,
    }
