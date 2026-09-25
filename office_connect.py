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
`storage.team_scope_for_user`: the team is the org unit the DIRECTORY puts you
in, and an account with no directory link resolves to "none" rather than to the
bureau. `_org_scope_for_user` answers None for that unlinked case, and
`_path_in_scope(path, None)` is True for everything, so using it directly here
would show an unlinked account every wellness and work-arrangement filing in the
bureau. When kind == "none" the team builders are not called at all and every
panel's "team" is None.

An `admin` role buys nothing here. Bureau-wide (kind == "bureau") is reached two
ways, neither of them a role: being recorded at the bureau-level org unit, whose
subtree is everyone, or holding an explicit 'all' grant on the account
(storage.BUREAU_ACCESS_LEVELS). A work-arrangement-only grant deliberately does
NOT widen this page — it spans all three modules, wellness included.
"""
from __future__ import annotations

from datetime import date, timedelta

import css_is_engine as eng
import dashboard_insights as di
import storage as st
import tzutil as tz

# How far back "recent activity" looks. Matches the 90-day cut the /css
# "recently concluded" strip already uses, so the two agree.
WINDOW_DAYS = 90
RECENT_N = 6
UPCOMING_N = 5

# The ACTIVITY INSIGHTS read the same window as the list, deliberately bound to
# it rather than restated. The card carries ONE window claim in its header, and a
# deck that quietly covered a different period than the rows above it made that
# header a lie on four slides out of five.
INSIGHT_DAYS = WINDOW_DAYS

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

    by_event, by_rp, by_creator, recent, order = {}, {}, {}, [], []
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
            # Per-speaker scores, kept so the PERSONAL deck can read your own
            # rating instead of the event's Form-2 overall. Crediting you with
            # the whole activity's score is the misleading claim to avoid: the
            # event review rates the event, not the person who spoke at it.
            "speakers_by_rp": {s["rp_id"]: {"name": s["name"], "value": s["value"],
                                            "shown": s["shown"], "band": s["band"]}
                               for s in speakers if s.get("rp_id")},
            "rp_ids": rp_ids, "creators": creators, "lead_paths": paths,
        }
        by_event[e["id"]] = row
        order.append(e["id"])
        for rp in rp_ids:
            by_rp.setdefault(rp, []).append(e["id"])
        for u in creators:
            by_creator.setdefault(u, []).append(e["id"])
        if row["date"] >= cut:
            recent.append(e["id"])
    # build_events is already newest-first; keep that order.
    return {"by_event": by_event, "by_rp": by_rp, "by_creator": by_creator,
            "recent": recent,
            # Every event id, newest-first. `recent` is the 90-day head of this;
            # the insights walk the whole list and cut it themselves, which is
            # what lets the deck span a year without a second pass over events.
            "order": order,
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

def _css_roles(ev, *, rp_ids, users, scope, personal):
    """Which links tie this activity to the viewer, or to the viewer's team.

    THE PREDICATE IS THE WHOLE DESIGN HERE. There is no staff->activity
    attendance relation in this schema: `attendee` rows are external registrants
    keyed by event + email with no admin_user link. A staff member is tied to an
    activity only as SPEAKER (form_instance.rp_id), CREATOR (created_by, a
    username) or via the ORGANISING UNIT (lead_org_id).

    CREATING AN ACTIVITY NEVER QUALIFIES IT. `created_by` records who filled in
    the form, which is a fact about the app, not about whose work the activity
    was: an administrator sets activities up for sections all over the bureau,
    and every one of them used to land on that administrator's own card and on
    their section's. What the organising unit says is what counts, and this page
    has no route guard behind which to hide getting that wrong.

    So:
      * PERSONAL is speaker-only. "I ran the form" is not "I was involved", and
        neither is "my section ran it" — the personal view is the one place a
        claim is about YOU, so it stays the narrowest of the three.
      * TEAM is the organising unit's subtree, plus anything one of the team
        actually spoke at (a section head wants their people's engagements at
        another section's event, which is real work done by real teammates).

    "ran" survives only as a CHIP on a row that already qualified — worth saying
    out loud, never a reason to be in the list.
    """
    if personal:
        return {"spoke"} if ev["rp_ids"] & rp_ids else set()
    roles = set()
    if any(st._path_in_scope(p, scope) for p in ev["lead_paths"]):
        roles.add("unit")
    if ev["rp_ids"] & rp_ids:
        roles.add("spoke")
    if not roles:
        return roles
    if ev["creators"] & users:
        roles.add("ran")
    return roles


def _css_panel(conn, index, *, me, roll_rows, scope, kind, today):
    """Activities, personal and team. See `_css_roles` for the predicate."""
    by_event = index["by_event"]

    def _row(eid, roles):
        r = dict(by_event[eid])
        r.pop("rp_ids", None), r.pop("creators", None), r.pop("lead_paths", None)
        r.pop("speakers_by_rp", None)
        r["roles"] = sorted(roles)
        return r

    # ---- personal -------------------------------------------------------
    my_rp = {me["rp_id"]} if me.get("rp_id") else set()
    my_ids = [eid for eid in index["order"]
              if _css_roles(by_event[eid], rp_ids=my_rp, users=set(),
                            scope=scope, personal=True)]
    personal_rows = [_row(eid, {"spoke"}) for eid in my_ids
                     if eid in set(index["recent"])]

    personal = {
        "rows": personal_rows[:RECENT_N],
        "total": len(personal_rows),
        "linked": bool(me.get("rp_id")),
        "window_days": WINDOW_DAYS,
        "insights": _css_insights(index, my_ids, today, rp_ids=my_rp, names={},
                                  personal=True),
    }

    # ---- team -----------------------------------------------------------
    team = None
    if kind != "none":
        team_rp_ids = {r["rp_id"] for r in roll_rows if r.get("rp_id")}
        team_users = {r["username"] for r in roll_rows if r.get("username")}
        names = {r["rp_id"]: r["name"] for r in roll_rows if r.get("rp_id")}
        team_ids, team_rows = [], []
        recent = set(index["recent"])
        for eid in index["order"]:
            ev = by_event[eid]
            roles = _css_roles(ev, rp_ids=team_rp_ids, users=team_users,
                               scope=scope, personal=False)
            if not roles:
                continue
            team_ids.append(eid)
            if eid not in recent:
                continue
            row = _row(eid, roles)
            row["who"] = sorted(names[r] for r in ev["rp_ids"] & team_rp_ids
                                if r in names)
            team_rows.append(row)
        team = {"rows": team_rows[:RECENT_N], "total": len(team_rows),
                "window_days": WINDOW_DAYS,
                "insights": _css_insights(index, team_ids, today,
                                          rp_ids=team_rp_ids, names=names,
                                          personal=False)}
    return {"team": team, "personal": personal}


# The seven-point bands, worst last, as `band7` names them. Kept in rank order
# rather than sorted by count so a reader can see the shape of the distribution
# at a glance instead of re-reading the labels every time it changes.
_CSS_BANDS = ["Excellent", "Good", "Fair", "Poor"]
_CSS_TOO_FEW = "Too few responses to read"
_CSS_UNRATED = "No ratings yet"
# How many people the "who spoke most" slide ranks before it stops. Past this the
# bars are a hairline each and the slide has stopped answering its own question.
_CSS_TOP_SPEAKERS = 8


def _month_span(cut, today):
    """Every calendar month the window touches, oldest first, as
    ((year, month), whole) pairs.

    `whole` says the window covers that month end to end. A 90-day window starts
    and ends mid-month, so its first and last buckets count part of a month
    against months counted in full — which is fine to DRAW (the bar is a true
    count of what happened in the window) but not fine to rank. See the
    "busiest" guard in _css_insights.
    """
    out, y, m = [], cut.year, cut.month
    while (y, m) <= (today.year, today.month):
        first = date(y, m, 1)
        last = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
        out.append(((y, m), cut <= first and today >= last))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _month_label(key):
    return f"{_MON[key[1] - 1]} {key[0]}"


def _css_insights(index, ids, today, *, rp_ids, names, personal):
    """The Activities card's later slides.

    Every number comes off the index already in hand — the same discipline as
    `_awa_insights`, and the reason this deck costs no extra query. `ids` is the
    already-scoped, newest-first list of event ids the caller's own predicate
    let through, so the deck can never disagree with the list above it about
    which activities count.

    Returns None when there is nothing to draw. An empty chart reads as "the
    data is broken" rather than "nothing has happened yet", which is what the
    slide's own empty state says properly.
    """
    by_event = index["by_event"]
    cut_date = today - timedelta(days=INSIGHT_DAYS)
    cut = cut_date.isoformat()
    rows = [by_event[eid] for eid in ids if by_event[eid]["date"] >= cut]
    if not rows:
        return None
    total = len(rows)

    # ---- how many, month by month ---------------------------------------
    span = _month_span(cut_date, today)
    keys = [k for k, _whole in span]
    whole = {k for k, w in span if w}
    per_month = {k: 0 for k in keys}
    for r in rows:
        try:
            d = date.fromisoformat(r["date"])
        except ValueError:
            continue
        k = (d.year, d.month)
        if k in per_month:
            per_month[k] += 1
    volume = di.count_bars_geom(
        [{"name": _month_label(k), "short": _MON[k[1] - 1], "n": per_month[k]}
         for k in keys],
        caption=("Activities you spoke at, by month" if personal
                 else "Activities by month"),
        key_header="Month", value_header="Activities")

    # ---- how they were rated --------------------------------------------
    # For the personal deck the band is YOUR speaker rating, never the event's
    # Form-2 overall: the event review rates the event, and handing you its
    # score because you happened to speak there is the claim to avoid.
    counts = {b: 0 for b in _CSS_BANDS}
    too_few = unrated = 0
    for r in rows:
        if personal:
            mine = next((r["speakers_by_rp"][rp] for rp in rp_ids
                         if rp in r["speakers_by_rp"]), None)
            band = (mine or {}).get("band")
        else:
            band = r["band"]
        if not band:
            unrated += 1
        elif r["low_n"]:
            too_few += 1
        elif band in counts:
            counts[band] += 1
        else:
            unrated += 1
    mix_rows = [{"label": b, "long": f"Rated {b.lower()}", "n": counts[b]}
                for b in _CSS_BANDS]
    if too_few:
        mix_rows.append({"label": _CSS_TOO_FEW,
                         "long": f"Fewer than {eng.N_MIN} responses",
                         "n": too_few})
    if unrated:
        mix_rows.append({"label": _CSS_UNRATED,
                         "long": "Nobody has rated these yet", "n": unrated})
    rated = sum(counts.values())
    mix = [{**m, "pct": round(m["n"] * 100 / total)} for m in mix_rows]

    # ---- who spoke most --------------------------------------------------
    # Only the team's own people are ranked. An outside resource person topping
    # your section's list is true but useless — the slide is asking who among us
    # is carrying the speaking, and `names` is exactly the roster.
    speakers = None
    if not personal and names:
        roster, tally = set(names), {}
        for r in rows:
            for rp in r["rp_ids"] & roster:
                tally[rp] = tally.get(rp, 0) + 1
        ranked = sorted(tally.items(), key=lambda kv: (-kv[1], names[kv[0]]))
        if ranked:
            top_n = ranked[0][1]
            speakers = [{"label": names[rp], "long": f"{n} of {total} activities",
                         "n": n, "pct": round(n * 100 / top_n)}
                        for rp, n in ranked[:_CSS_TOP_SPEAKERS]]

    # ---- reach ------------------------------------------------------------
    responses = sum(r["respondents"] for r in rows)
    thin = sum(1 for r in rows if r["low_n"])
    biggest = max(r["respondents"] for r in rows)
    reach = {"responses": responses, "activities": total,
             "avg": round(responses / total) if total else 0,
             "thin": thin, "n_min": eng.N_MIN, "biggest": biggest,
             # Pre-grouped for the tiles. A four-figure count set as "1240" is
             # read as a year before it is read as a number.
             "responses_shown": f"{responses:,}", "biggest_shown": f"{biggest:,}"}

    # "Busiest" only when ONE month holds the top AND the window covers that
    # month end to end. On a tie the superlative is simply false, and picking
    # whichever month sorted first is how a chart ends up disagreeing with the
    # sentence printed under it. A PARTIAL month leading is not a fact about a
    # month at all — a 90-day window ends mid-month, so August could "win" on
    # sixteen days against July's thirty-one.
    peaks = [b for b in volume["bars"] if b["n"] and b["n"] == volume["ymax"]]
    busiest = (peaks[0] if len(peaks) == 1
               and keys[volume["bars"].index(peaks[0])] in whole else None)
    top_band = max((m for m in mix if m["label"] in counts), key=lambda m: m["n"],
                   default=None)
    return {
        "window_days": INSIGHT_DAYS, "months": len(keys),
        "total": total, "since": _short_date(cut),
        "volume": volume,
        "mix": mix,
        "mix_table": {"caption": ("How your activities were rated" if personal
                                 else "How the team's activities were rated"),
                      "headers": ["Rating", "Activities"],
                      "rows": [[m["label"], str(m["n"])] for m in mix]},
        "speakers": speakers,
        "speakers_table": ({"caption": "Activities spoken at, by person",
                            "headers": ["Person", "Activities"],
                            "rows": [[s["label"], str(s["n"])] for s in speakers]}
                           if speakers else None),
        "reach": reach,
        "said": {
            "volume": (f"{total} activit{'y' if total == 1 else 'ies'} since "
                       f"{_short_date(cut)}"
                       + (f" — {busiest['name']} was the busiest with "
                          f"{busiest['n']}." if busiest else ".")),
            "mix": (f"{top_band['label']} is the most common rating — "
                    f"{top_band['n']} of the {rated} with enough responses."
                    if top_band and top_band["n"] and rated else None),
            "speakers": (f"{speakers[0]['label']} spoke at the most — "
                         f"{speakers[0]['n']} of the {total}."
                         if speakers else None),
            "reach": (f"{reach['responses_shown']} "
                      f"response{'' if responses == 1 else 's'} "
                      f"across {total} activit{'y' if total == 1 else 'ies'}"
                      + (f" · {thin} still below the {eng.N_MIN}-response mark."
                         if thin else ".")
                      if responses else None),
        },
    }


def _wellness_panel(conn, *, me, user, roll, week_start, kind):
    """This week's break hours — a wall of faces, not a table of names — plus the
    eight-week habit behind it, which is what the card's later slides read."""
    weekly = st.WELLNESS_WEEKLY_HOURS
    try:
        stats = st.wellness_stats(conn, me["user_id"])
    except Exception:
        stats = None

    personal = {
        "week_start": week_start, "weekly_hours": weekly,
        "stats": stats,
        "used": 0, "left": weekly, "ring": di.ring_geom(0), "state": "none",
        "insights": _wellness_insights(
            st.wellness_pattern(conn, week_start, only_user_id=me["user_id"]),
            whose="you"),
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
            "insights": _wellness_insights(
                st.wellness_pattern(conn, week_start, user), whose="the team"),
        }
    return {"team": team, "personal": personal}


_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _short_date(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{_MON[d.month - 1]} {d.day}"


def _wellness_insights(pat, *, whose):
    """The wellness card's later slides: geometry + one plain sentence each.

    Returns None when there is nothing to draw. An empty chart is worse than no
    chart — it reads as "the data is broken" rather than "nobody has filed yet",
    which is what the slide's own empty state says properly."""
    if not pat or not pat["claims"]:
        return None
    yours = whose == "you"
    day_names = [d["name"] for d in pat["by_day"]]
    slot_names = [s["label"] for s in pat["by_slot"]]

    when = di.heat_geom(pat["grid"], day_names, slot_names,
                        caption="Wellness breaks by day and start time")
    days = di.count_bars_geom(pat["by_day"],
                              caption="Wellness breaks by weekday",
                              key_header="Weekday", value_header="Breaks")
    weeks = di.count_bars_geom(
        [{"name": _short_date(w["week_start"]), "short": _short_date(w["week_start"]),
          "n": w["people"]} for w in pat["by_week"]],
        caption=("Weeks you took a break" if yours
                 else "People taking a break each week"),
        key_header="Week of", value_header=("Breaks" if yours else "People"))

    total = sum(a["n"] for a in pat["by_activity"]) or 1
    activity = [{**a, "pct": round(a["n"] * 100 / total)}
                for a in pat["by_activity"]]
    activity_table = {
        "caption": "What people did on their wellness break",
        "headers": ["Activity", "Breaks"],
        "rows": [[a["label"], str(a["n"])] for a in activity],
    }

    peak, mood = when["peak"], pat["mood"]
    said = {
        "when": ((f"You take yours {peak['row']}, {peak['col'].lower()}."
                  if yours else
                  f"Most breaks land {peak['row']}, {peak['col'].lower()}.")
                 if peak else None),
        "days": (f"{pat['peak_day']['name']} is the most protected day — "
                 f"{pat['peak_day']['n']} of {pat['claims']} breaks."
                 if pat["peak_day"] and pat["peak_day"]["n"] else None),
        "weeks": (f"{pat['people']} {'week' if yours else 'people'} "
                  f"{'with a break' if yours else 'took a break'} over "
                  f"{pat['weeks']} weeks." if not yours else
                  f"{pat['claims']} breaks over the last {pat['weeks']} weeks."),
        "mood": _mood_sentence(mood, yours=yours),
    }
    return {"weeks_back": pat["weeks"], "claims": pat["claims"],
            "hours": pat["hours"], "people": pat["people"],
            "since": _short_date(pat["first_week"]),
            "when": when, "days": days, "week_trend": weeks,
            "activity": activity, "activity_table": activity_table,
            "mood": mood, "said": said}


def _mood_sentence(mood, *, yours):
    """How the break landed, said only as far as the answers support.

    Two separate questions with two separate denominators, so they get two
    separate clauses — and no clause at all when nobody has filled that part of
    the reflection in."""
    who = "you" if yours else "people"
    parts = []
    if mood.get("delta") is not None and mood.get("moods"):
        if mood["delta"] > 0:
            parts.append(f"{who} finish {mood['delta']} points better than "
                         f"{'you' if yours else 'they'} started")
        elif mood["delta"] == 0:
            parts.append(f"{who} finish about where {'you' if yours else 'they'} started")
        else:
            parts.append(f"{who} finish {abs(mood['delta'])} points lower than "
                         f"{'you' if yours else 'they'} started")
    if mood.get("refreshed_pct") is not None:
        parts.append(f"{mood['refreshed_pct']}% felt refreshed "
                     f"({mood['answered']} answered)")
    if not parts:
        return None
    return (" · ".join(parts)).capitalize() + "."


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
        # The second line of the hover/focus name popup. Built here, not in the
        # template, so the wall and the chart_table fallback say the same thing.
        out["tip"] = f"{used} of {weekly} h · {label}"
    else:
        out["name"], out["section"] = row["name"], row.get("section", "")
    return out


_WA_TONE = {"approved": "green", "pending": "amber", "noawa": "accent", "": "soft"}


def _awa_team_block(conn, user, me, period_start, *, settled, summary=None):
    """The team half of the AWA card for ONE period: the roster as faces, the
    on-site-by-weekday bars, and the slides derived from them.

    `settled` says this period's filing closed long ago — it is being worked,
    not chased — which is what the unfiled rows get called."""
    if summary is None:
        summary = st.work_arrangement_period_summary(conn, period_start, user)
    headcount = summary["headcount"]
    faces = [{**_face(r, me_id=me["user_id"]),
              "arrangement_label": r["arrangement_label"],
              "weekday_name": _weekday_name(r["weekday"]),
              "status": r["status"], "filed": r["filed"],
              "noawa": r.get("noawa", False),
              "tone": ("accent" if r.get("noawa")
                       else _WA_TONE.get(r["status"], "soft")),
              "tip": (f"{r['arrangement_label'] or 'Not filed yet'}"
                      f"{' · ' + r['status'] if r['status'] else ''}"),
              "aria": (f"{r['name']} — "
                       f"{r['arrangement_label'] or 'nothing filed'}"
                       f"{', ' + r['status'] if r['status'] else ''}.")}
             for r in summary["roster"]]
    pct = round(summary["filed"] * 100 / headcount) if headcount else 0
    return {
        "period_start": summary["period_start"],
        "period_label": summary["period_label"],
        "headcount": headcount, "filed": summary["filed"],
        "approved": summary["approved"], "pending": summary["pending"],
        "unfiled": summary["unfiled"], "noawa": summary["noawa"],
        "pct": pct, "ring": di.ring_geom(pct), "faces": faces,
        "coverage": di.bars_geom(summary["totals"], headcount),
        "insights": _awa_insights(summary, settled=settled),
    }


def _awa_panel_build(conn, *, me, user, today, kind):
    open_ps = st.work_arrangement_open_periods()
    ps_file = open_ps[0] if open_ps else None
    ps_now = st.work_arrangement_schedule_period()

    try:
        cur = st.my_work_arrangement_for(conn, me["user_id"], ps_now)
    except Exception:
        cur = None
    in_force = {"period_label": st.work_arrangement_period_label(ps_now),
                "arrangement_label": (cur or {}).get("arrangement_label"),
                "weekday_name": _weekday_name((cur or {}).get("weekday")),
                "status": (cur or {}).get("status"), "filed": bool(cur)}

    # The fortnight being WORKED — who is on-site on Tuesday. This is the
    # operational question and the card leads with it; it is never the period
    # open for filing, whose deadline falls before it even starts, so it needs
    # its own summary rather than a slice of the filing one.
    now = None
    day = None
    if kind != "none":
        now = _awa_team_block(conn, user, me, ps_now, settled=True)
        # ...and the single day, which is what someone opening the page at 9am
        # actually wants. On a weekend nobody is scheduled, so show the Monday
        # rather than an empty card nobody can act on.
        d = today
        if d.weekday() >= 5:
            d = st.work_arrangement_day_step(d, 1)
        day = st.work_arrangement_day(conn, d, user)
        day["is_today"] = (d == today)
        day["faces"] = [_face(r, me_id=me["user_id"])
                        for r in day["groups"]["onsite"]]

    if not ps_file:
        return {"now": now, "day": day, "team": None,
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
        team = {**_awa_team_block(conn, user, me, ps_file, settled=False,
                                  summary=summary),
                "state": state, "deadline_label": summary["deadline_label"],
                "days_left": days_left}
    return {"now": now, "day": day, "team": team, "personal": personal}


def _awa_insights(summary, *, settled=False):
    """The AWA card's later slides, all derived from the period summary already
    in hand — no extra query for any of them.

    Three questions the filing bar cannot answer: what people chose, which day
    the office empties out, and which section is still chasing.

    `settled` is a period already being worked rather than one still being
    filed for, so the rows are counted the same way but named for a fortnight
    whose deadline is long past."""
    roster = summary["roster"]
    filed = [r for r in roster if r["filed"] and not r.get("noawa")]

    # ---- what people chose ---------------------------------------------
    # `choice` marks the rows that are an actual arrangement someone picked.
    # The two that are not — "No AWA" and the unfiled — are counted in the mix
    # but must stay out of "most common", or a barely-filed period reports
    # "Not filed yet is the most common arrangement", which is not one at all.
    counts = {}
    for r in filed:
        counts[r["arrangement"]] = counts.get(r["arrangement"], 0) + 1
    noawa = sum(1 for r in roster if r.get("noawa"))
    unfiled = sum(1 for r in roster if not r["filed"] and not r.get("noawa"))
    mix_rows = [{"label": st.WORK_ARRANGEMENT_LABELS.get(code, code),
                 "long": long, "n": counts.get(code, 0), "choice": True}
                for code, _short, long in st.WORK_ARRANGEMENT_TYPES]
    mix_rows.append({"label": st.WORK_ARRANGEMENT_NOAWA, "choice": False,
                     "long": "Out of the schedule this period", "n": noawa})
    mix_rows.append({"label": "Nothing filed" if settled else "Not filed yet",
                     "long": ("No arrangement on record for this period"
                              if settled else "Still to file"),
                     "n": unfiled, "choice": False})
    mix_total = sum(m["n"] for m in mix_rows) or 1
    mix = [{**m, "pct": round(m["n"] * 100 / mix_total)}
           for m in mix_rows if m["n"] or m["label"] != st.WORK_ARRANGEMENT_NOAWA]

    # ---- which day people are away -------------------------------------
    # The stored weekday is the day OFF (CWW) or the day at home (WFH); either
    # way it is the day that person is not at their desk, which is the whole
    # question a section chief has about the fortnight.
    away = {idx: 0 for idx, _n in st.WORK_ARRANGEMENT_WEEKDAYS}
    for r in filed:
        if r.get("weekday") is not None:
            away[r["weekday"]] = away.get(r["weekday"], 0) + 1
    day_off = di.count_bars_geom(
        [{"name": name, "short": name[:3], "n": away.get(idx, 0)}
         for idx, name in st.WORK_ARRANGEMENT_WEEKDAYS],
        caption="People away from their desk, by weekday",
        key_header="Weekday", value_header="People away")

    # ---- who is still chasing ------------------------------------------
    sections = {}
    for r in roster:
        if r.get("noawa"):
            continue
        s = sections.setdefault(r["section"] or "—",
                                {"section": r["section"] or "—",
                                 "people": 0, "filed": 0})
        s["people"] += 1
        s["filed"] += 1 if r["filed"] else 0
    by_section = sorted(
        ({**s, "pct": round(s["filed"] * 100 / s["people"]) if s["people"] else 0}
         for s in sections.values()),
        key=lambda s: (s["pct"], s["section"]))

    chosen = [m for m in mix if m["choice"]]
    top = max(chosen, key=lambda m: m["n"]) if chosen else None
    filed_n = sum(m["n"] for m in chosen)
    busiest = max(day_off["bars"], key=lambda b: b["n"]) if day_off["bars"] else None
    behind = by_section[0] if len(by_section) > 1 else None
    return {
        "mix": mix, "day_off": day_off, "by_section": by_section,
        "mix_table": {"caption": ("Arrangements in force this period" if settled
                                  else "Arrangements filed for this period"),
                      "headers": ["Arrangement", "People"],
                      "rows": [[m["label"], str(m["n"])] for m in mix]},
        "section_table": {"caption": "Filing progress by section",
                          "headers": ["Section", "Filed", "People"],
                          "rows": [[s["section"], str(s["filed"]),
                                    str(s["people"])] for s in by_section]},
        "said": {
            "mix": (f"{top['label']} is the most common choice — {top['n']} of "
                    f"the {filed_n} "
                    f"{'on an arrangement' if settled else 'filed so far'}."
                    if top and top["n"] else None),
            "day_off": (f"{busiest['name']} is the emptiest day — "
                        f"{busiest['n']} away." if busiest and busiest["n"] else None),
            "sections": (f"{behind['section']} is furthest behind — "
                         f"{behind['filed']} of {behind['people']} filed."
                         if behind and behind["pct"] < 100 else None),
        },
    }


def _scope_label(conn, scope_path, rows):
    """What to call the team on the scope line.

    The unit's OWN name, looked up on org_unit.path (UNIQUE, so one indexed
    row). Naming it after the first roster row's section was fine while a scope
    was always one section, but a division — or the bureau-level unit, which is
    now the only route to a bureau-wide view — spans several, and the first one
    alphabetically is not what the viewer is looking at."""
    if not scope_path:
        return "your team"
    row = conn.execute(
        "SELECT short_name, name FROM org_unit WHERE path=? LIMIT 1",
        (scope_path,)).fetchone()
    if row and (row[0] or row[1]):
        return row[0] or row[1]
    return rows[0]["section"] if rows else "your team"


def _weekday_name(idx):
    if idx is None:
        return None
    return dict(st.WORK_ARRANGEMENT_WEEKDAYS).get(idx)


# --------------------------------------------------------------------------
# the payload
# --------------------------------------------------------------------------

def _approvals_waiting(conn, user):
    """Requests waiting on THIS approver's decision, across the wellness and
    work-arrangement queues — the two share one chief gate
    (storage.user_is_approving_chief / its user_is_wellness_chief alias), so
    an AWA approver and a wellness approver are the same person here. None
    when both queues are empty (including for anyone who isn't an approving
    chief), so callers can treat "nothing to show" as a single falsy check.

    storage.pending_approval_counts is the single source of truth here — the
    nav bell (app.py's auth middleware) calls the same function, so the two
    can never disagree about what's waiting."""
    counts = st.pending_approval_counts(conn, user)
    wellness, awa = counts["wellness"], counts["awa"]
    if not (wellness or awa):
        return None
    return {"wellness": wellness, "awa": awa, "total": wellness + awa}


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

    # Approvals waiting on YOU — surfaced before any click into either queue,
    # so a chief who approves both wellness and AWA doesn't have to open each
    # one blind just to find out whether there's anything to decide.
    approvals = _approvals_waiting(conn, user)
    if approvals:
        if approvals["wellness"]:
            n = approvals["wellness"]
            notes.append({
                "key": "wellness_approvals", "tone": "amber",
                "text": f"{n} wellness break{'' if n == 1 else 's'} waiting on your decision.",
                "url": "/approvals#wellness", "cta": "Review",
            })
        if approvals["awa"]:
            n = approvals["awa"]
            notes.append({
                "key": "awa_approvals", "tone": "amber",
                "text": f"{n} work arrangement request{'' if n == 1 else 's'} waiting on your decision.",
                "url": "/approvals#awa", "cta": "Review",
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
                   else _scope_label(conn, scope_path, roll["rows"])
                   if kind == "unit" else None)

    return {
        "me": me,
        "scope": {"path": scope_path, "kind": kind, "label": scope_label,
                  "size": len(roll["rows"])},
        "panels": {
            "wellness": _wellness_panel(conn, me=me, user=user, roll=roll,
                                        week_start=week_start, kind=kind),
            "awa": _awa_panel_build(conn, me=me, user=user, today=today, kind=kind),
            "css": {**_css_panel(conn, index, me=me, roll_rows=roll["rows"],
                                 scope=scope_path, kind=kind, today=today),
                    "upcoming": _upcoming(conn, index, scope_path, kind)},
        },
        "notes": notes,
        "approvals": approvals,
    }
