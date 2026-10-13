"""Conference room notices (docs/ROOM_RESERVATION_PLAN.md section 6, R5).

How it works: a state change in rooms.py calls an on_* hook here, which only INSERTS rows
into room_notice (one per person per event, UNIQUE so it can never double up). The bell reads
those rows directly; the scheduler's tick() turns the ones that owe an email into emails
(flush). So a booking never waits on the mail relay and a failed send is retried, not lost.

tick() also raises the time-based notices, each idempotent by its (recipient, kind, reservation,
version) key, so running it every minute is safe: escalation of a request that has waited,
the morning summary of open requests, the afternoon room schedule and the day-before
reminders, and expiring requests whose date has passed."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import quote

import auth
import mailer
import storage as st
import tzutil as tz

REQUESTER_KINDS = ("approved", "declined", "cancelled", "encoded", "expired")
MEAL_KINDS = ("meal_form", "meal_revised", "meal_cancel")
FEATURE = {"new_request": "room_new_request", "received": "room_decided", "approved": "room_decided", "declined": "room_decided",
           "cancelled": "room_decided", "encoded": "room_decided", "expired": "room_decided",
           "reminder": "room_reminder", "escalation": "room_admin_alerts",
           "meal_form": "room_admin_alerts", "meal_revised": "room_admin_alerts", "meal_cancel": "room_admin_alerts",
           "withdrawn_late": "room_admin_alerts", "digest": "room_digest", "tomorrow": "room_digest"}
ESCALATE_AFTER = timedelta(hours=24)       # a request pending this long goes to the Admin Head ...
ESCALATE_WITHIN = timedelta(hours=48)      # ... as does one whose date is this close
MORNING_HOUR, AFTERNOON_HOUR = 8, 16
MAX_ATTEMPTS = 3
RETRY_AFTER = timedelta(minutes=5)
STALE_AFTER = timedelta(days=3)           # an email nobody could send for 3 days is no longer news


# ------------------------------------------------------------ who ---

def approver_accounts(conn):
    """Active accounts who decide room requests: the Administrative Section only.
    Returns [{'id', 'username', 'name', 'head'}]; `head` marks the section's chief."""
    import rooms
    out = {}
    for aid, uname, desig, pos in conn.execute(
            "SELECT a.id, a.username, rp.designation, rp.position FROM admin_user a "
            "JOIN resource_person rp ON rp.id=a.rp_id AND rp.is_internal=1 AND rp.archived_at IS NULL "
            f"JOIN org_unit ou ON ou.id=rp.org_unit_id WHERE a.active=1 AND {rooms._ADMIN_UNIT_SQL}"):
        out[aid] = {"id": aid, "username": uname, "head": st._org_rank(desig, pos) >= 1}
    for a in out.values():
        a["name"] = st._account_display_name(conn, a["id"]) or a["username"]
    return list(out.values())


def admin_heads(conn):
    people = approver_accounts(conn)
    return [p for p in people if p["head"]] or people


# --------------------------------------------------------- inserting ---

def _add(conn, *, kind, reservation_id=0, version=1, user_id=None, email=None, text="", url="",
         bell=False, email_wanted=True):
    """One notice, once. Returns True when it was new."""
    if user_id is None and not (email or "").strip():
        return False
    recipient = f"u:{user_id}" if user_id is not None else f"e:{email.strip().lower()}"
    cur = conn.execute(
        "INSERT OR IGNORE INTO room_notice(recipient, user_id, email, kind, reservation_id, version, text, url, "
        "bell, created_at, email_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (recipient, user_id, None if user_id is not None else email.strip(), kind, reservation_id, version,
         text, url, 1 if bell else 0, tz.now_iso(), None if email_wanted else "skipped_none"))
    conn.commit()
    return cur.rowcount > 0


def _when(conn, res):
    import rooms
    d = rooms._d(res["day"])
    return f"{d:%a} {d.day} {d:%b %Y}, {rooms.hours_text(conn, res)}"


def _series_note(conn, res):
    """' (+5 more dates in this repeating request)' for the first date of a series, else ''. A series is announced once."""
    import rooms
    ss = rooms.series_summary(conn, res) if res.get("series_id") else None
    return f" (+{ss['total'] - 1} more dates in this repeating request)" if ss else ""


def _to_requester(conn, res, kind, text, by=None, bell=True):
    """Notice to whoever the reservation belongs to: an account (bell + email) or a guest (email)."""
    uid = res.get("requester_user_id")
    if uid is not None:
        u = st.get_admin_user_by_id(conn, uid)
        if u and by and u["username"] == by:           # you don't need telling what you just did
            return False
        return _add(conn, kind=kind, reservation_id=res["id"], user_id=uid, text=text, url="/rooms/mine", bell=bell)
    return _add(conn, kind=kind, reservation_id=res["id"], email=res.get("ext_email"), text=text)


# ----------------------------------------------------------- hooks ---

def on_requested(conn, res):
    """A new request: tell the Administrative Section (email; the bell already counts it)."""
    import rooms
    who, unit, _ext = rooms.requester_label(conn, res)
    more = _series_note(conn, res)
    for a in approver_accounts(conn):
        if res.get("requester_user_id") == a["id"]:
            continue
        _add(conn, kind="new_request", reservation_id=res["id"], user_id=a["id"], url="/approvals#rooms",
             text=f"{who}{f' ({unit})' if unit else ''}: {res['title']}, {_when(conn, res)}{more}"
                  + (" · STANDBY: those hours are already taken" if res.get("standby") else ""))


def on_received(conn, res):
    """A guest's request is in: send their reference and tracking link."""
    _to_requester(conn, res, "received", f"We received your request {res['ref_code']}: {res['title']}, {_when(conn, res)}.",
                  bell=False)


def on_meal(conn, kind, form, text=None):
    """Tell the Administrative Section about a meal form: ready to order, revised, or its booking is gone.
    Bell + email, once per form version."""
    res = form["reservation"]
    heading = {"meal_form": "A meal form is ready to order", "meal_revised": "A meal form was changed",
               "meal_cancel": "A meal order needs cancelling"}[kind]
    line = text or f"{res['title']}, {_when(conn, res)}: {len(form['wanted'])} meal(s) for {form['pax'] or '?'} pax."
    for a in approver_accounts(conn):
        _add(conn, kind=kind, reservation_id=res["id"], version=form["version"], user_id=a["id"], bell=True,
             url="/rooms/meals", text=f"{heading}: {line}")


def on_decided(conn, res, by=None):
    verb = {"approved": "approved", "declined": "declined"}.get(res["status"])
    if not verb:
        return
    if res["status"] == "approved":                                   # the form is now something to order from
        import rooms_meals
        f = rooms_meals.get_form(conn, res["id"])
        if f and f["wanted"]:
            on_meal(conn, "meal_form", f)
    extra = f" Reason: {res['decide_note']}" if res["status"] == "declined" and res.get("decide_note") else ""
    _to_requester(conn, res, res["status"], f"Your conference room request was {verb}: {res['title']}, "
                  f"{_when(conn, res)}{_series_note(conn, res)}.{extra}", by=by)


def on_encoded(conn, res, by=None):
    _to_requester(conn, res, "encoded", f"The conference room was booked for you: {res['title']}, {_when(conn, res)}.", by=by)


def on_cancelled(conn, res, by=None):
    _to_requester(conn, res, "cancelled", f"Your conference room booking was cancelled: {res['title']}, "
                  f"{_when(conn, res)}. {res.get('decide_note') or ''} Pick a new time.".replace("  ", " "), by=by)


def on_expired(conn, res):
    _to_requester(conn, res, "expired", f"Your conference room request expired undecided: {res['title']}, {_when(conn, res)}.")


def on_withdrawn(conn, res, late):
    """A booking withdrawn the day before (or sooner): meals and setup may be arranged, so the
    section is told."""
    if not late:
        return
    import rooms
    who, _u, _e = rooms.requester_label(conn, res)
    for a in approver_accounts(conn):
        _add(conn, kind="withdrawn_late", reservation_id=res["id"], user_id=a["id"], bell=True, url="/approvals#rooms",
             text=f"{who} withdrew {res['title']} ({_when(conn, res)}) at short notice.")


# ----------------------------------------------------------- bell ---

def bell_rows(conn, user_id):
    """Bell lines for this account: updates on its own reservations, and (for the section)
    short-notice withdrawals. Cleared by visiting My reservations / Approvals."""
    rows = conn.execute("SELECT kind, text FROM room_notice WHERE user_id=? AND bell=1 AND seen_at IS NULL ORDER BY id",
                        (user_id,)).fetchall()
    mine = [r for r in rows if r[0] in REQUESTER_KINDS]
    late = [r for r in rows if r[0] == "withdrawn_late"]
    meals = [r for r in rows if r[0] in MEAL_KINDS]
    out = []
    if meals:
        out.append({"text": meals[0][1] if len(meals) == 1 else f"{len(meals)} meal order updates", "url": "/rooms/meals",
                    "count": len(meals)})
    if len(mine) == 1:
        out.append({"text": mine[0][1], "url": "/rooms/mine", "count": 1})
    elif mine:
        out.append({"text": f"{len(mine)} updates on your conference room reservations", "url": "/rooms/mine",
                    "count": len(mine)})
    if late:
        out.append({"text": f"{len(late)} conference room booking{'' if len(late) == 1 else 's'} withdrawn at short notice",
                    "url": "/approvals#rooms", "count": len(late)})
    return out


def mark_seen(conn, user_id, kinds):
    qs = ",".join("?" * len(kinds))
    conn.execute(f"UPDATE room_notice SET seen_at=? WHERE user_id=? AND seen_at IS NULL AND kind IN ({qs})",
                 (tz.now_iso(), user_id, *kinds))
    conn.commit()


# -------------------------------------------------------- time-based ---

def expire_past_requests(conn, today):
    """A request nobody decided before its date can't be approved any more: mark it expired."""
    import rooms
    n = 0
    for (rid,) in conn.execute("SELECT id FROM room_reservation WHERE status='requested' AND day<?",
                               (today.isoformat(),)).fetchall():
        conn.execute("UPDATE room_reservation SET status='expired', updated_at=? WHERE id=? AND status='requested'",
                     (tz.now_iso(), rid))
        conn.commit()
        res = rooms.get_reservation(conn, rid)
        st.audit(conn, "system", "room_expire", target_type="room_reservation", target_id=rid,
                 summary=f"{res['title']} on {res['day']} expired undecided", before="requested", after="expired")
        rooms._meals_over(conn, rid, "The room request expired undecided.")
        on_expired(conn, res)
        n += 1
    return n


def queue_escalations(conn, now):
    """Requests that have waited a day, or whose date is within two days, go to the Admin Head once."""
    import rooms
    n = 0
    heads = admin_heads(conn)
    for res in rooms.list_pending(conn):
        created = datetime.fromisoformat(res["created_at"]) if res["created_at"] else now
        start = datetime.fromisoformat(f"{res['day']}T00:00:00")
        if not (now - created >= ESCALATE_AFTER or start - now <= ESCALATE_WITHIN):
            continue
        who, _u, _e = rooms.requester_label(conn, res)
        for h in heads:
            if _add(conn, kind="escalation", reservation_id=res["id"], user_id=h["id"], url="/approvals#rooms",
                    text=f"{res['title']} ({_when(conn, res)}) from {who} is still waiting for a decision."):
                n += 1
    return n


def queue_morning_digest(conn, now):
    import rooms
    if not rooms.pending_count(conn):
        return 0
    return sum(_add(conn, kind="digest", version=now.date().toordinal(), user_id=a["id"], url="/approvals#rooms")
               for a in approver_accounts(conn))


def queue_afternoon(conn, now):
    """Tomorrow's room schedule for the section, and a reminder to each person who has it."""
    import rooms
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM room_reservation WHERE status='approved' AND day=? ORDER BY id", (tomorrow,))]
    n = 0
    if ids:
        for a in approver_accounts(conn):
            n += _add(conn, kind="tomorrow", version=now.date().toordinal() + 1, user_id=a["id"], url="/approvals#rooms")
        for rid in ids:
            res = rooms.get_reservation(conn, rid)
            n += _to_requester(conn, res, "reminder",
                               f"Tomorrow: {res['title']}, {_when(conn, res)}.", bell=False)
    return n


# ------------------------------------------------------------ flush ---

def _decide_links(base, rid, uid):
    t = quote(auth.make_room_decide_token(rid, uid))
    url = f"{base}/rooms/decide/{rid}?token={t}"
    return f"{url}&action=approve", f"{url}&action=decline"


def _build(conn, n, base, name, send_to_account):
    """(feature, subject, body, html, attachments) for one notice row, or None when its
    reservation vanished."""
    import rooms
    import calendar_ics as cics
    kind, rid = n["kind"], n["reservation_id"]
    feature = FEATURE[kind]
    inbox = f"{base}/approvals#rooms"
    mine = f"{base}/rooms/mine"
    if not n["user_id"] and rid:                      # a guest has no account: their signed link is the way back
        mine = f"{base}/room/t/{quote(auth.make_room_track_token(rid))}"
    if kind in ("digest", "tomorrow"):
        open_lines = [f"{q['when']}, {q['hours']}: {q['title']} ({q['requester_name']})" for q in rooms.queue(conn)] \
            if kind == "digest" else []
        tom = []
        if kind == "tomorrow":
            tomorrow = datetime.fromordinal(n["version"]).date().isoformat()
            for (r_id,) in conn.execute("SELECT id FROM room_reservation WHERE status='approved' AND day=? ORDER BY id",
                                        (tomorrow,)):
                r = rooms.get_reservation(conn, r_id)
                who, _u, _e = rooms.requester_label(conn, r)
                tom.append(f"{rooms.hours_text(conn, r)}: {r['title']} ({who})"
                           + (f", {r['attendees']} attending" if r["attendees"] else "")
                           + (", meals requested" if r["meals_requested"] else ""))
        if not open_lines and not tom:
            return None
        return (feature, *mailer.room_digest_message(name, open_lines, tom, inbox), None)
    res = rooms.get_reservation(conn, rid)
    if res is None:
        return None
    when = _when(conn, res) + (_series_note(conn, res) if kind in ("new_request", "approved", "declined", "received") else "")
    who, unit, _ext = rooms.requester_label(conn, res)
    if kind in ("new_request", "escalation"):
        if res["status"] != "requested":                 # decided in the meantime: nothing to ask
            return None
        ap, de = _decide_links(base, rid, n["user_id"]) if n["user_id"] else (None, None)
        if kind == "new_request":
            bits = [x for x in (f"{res['attendees']} attending" if res["attendees"] else "",
                                "meals requested" if res["meals_requested"] else "", res["purpose"] or "") if x]
            return (feature, *mailer.room_request_message(name, f"{who}{f' ({unit})' if unit else ''}", when, res["title"],
                                                          " · ".join(bits), inbox, ap, de), None)
        return (feature, *mailer.room_alert_message(name, "a request is still waiting", n["text"], inbox, ap, de), None)
    if kind == "withdrawn_late":
        return (feature, *mailer.room_alert_message(name, "a booking was withdrawn at short notice", n["text"], inbox), None)
    if kind in MEAL_KINDS:
        return (feature, *mailer.room_alert_message(name, {"meal_form": "a meal form is ready to order", "meal_revised": "a meal form was changed",
                                                           "meal_cancel": "a meal order needs cancelling"}[kind], n["text"],
                                                    f"{base}/rooms/meals"), None)
    if kind == "reminder":
        if res["status"] != "approved":
            return None
        return (feature, *mailer.room_reminder_message(name, res["title"], when, res["ref_code"], mine), None)
    if kind in ("cancelled", "declined"):
        sugg = [s["label"] for s in rooms.suggestions_for(conn, res, n=3)]
    else:
        sugg = []
    att = None
    if kind in ("approved", "encoded") and res["slot_ids"]:
        by = {s["id"]: s for s in rooms.list_slots(conn, active_only=False)}
        first, last = by[res["slot_ids"][0]], by[res["slot_ids"][-1]]
        import office_calendar as oc
        att = [cics.attachment([oc.room_event(res, (first["start_time"], last["end_time"]), base)],
                               name="conference-room.ics")]
    return (feature, *mailer.room_decided_message(name, kind, res["title"], when, res["ref_code"], res["decide_note"],
                                                  mine, sugg or None), att)


def flush(conn, base_url, now=None, send=None):
    """Email every notice that owes one. Safe to run every minute: sent rows are never picked
    up again, a failed one is retried up to three times five minutes apart, and a feature an
    admin switched off is logged as skipped. Returns {status: count}."""
    if send is None:
        if not mailer.email_configured():                  # nothing to send with: keep them waiting (the bell still works)
            return {}
        send = mailer.send
    now = now or tz.now_local()
    cutoff = (now - RETRY_AFTER).isoformat(timespec="seconds")
    stale = (now - STALE_AFTER).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, user_id, email, kind, reservation_id, version, text, attempts, created_at FROM room_notice "
        "WHERE email_status IS NULL OR (email_status='failed' AND attempts<? AND emailed_at<=?) ORDER BY id",
        (MAX_ATTEMPTS, cutoff)).fetchall()
    tally = {}
    for rid_, user_id, email, kind, res_id, version, text, attempts, created in rows:
        n = {"user_id": user_id, "kind": kind, "reservation_id": res_id, "version": version, "text": text}
        feature = FEATURE.get(kind)

        def done(status, detail=None, to=None, subj=None):
            conn.execute("UPDATE room_notice SET email_status=?, emailed_at=?, attempts=attempts+? WHERE id=?",
                         (status, now.isoformat(timespec="seconds"), 1 if status in ("failed", "sent", "not_configured") else 0, rid_))
            conn.commit()
            if to and status not in ("skipped_none",):
                st.log_email_send(conn, feature, to, subj or kind, status, detail)
            tally[status] = tally.get(status, 0) + 1

        to, name = email, None
        if user_id is not None:
            u = st.get_admin_user_by_id(conn, user_id)
            to = u["username"] if u and u.get("username") and "@" in u["username"] else None
            name = st._account_display_name(conn, user_id) if u else None
        if not to or feature is None or (created or "") < stale:    # no address, or too old to still be news
            done("skipped_none"); continue
        if not st.email_feature_enabled(conn, feature):
            done("skipped_off", to=to); continue
        if not base_url:                                   # links need a public origin: wait for it
            continue
        built = _build(conn, n, base_url.rstrip("/"), name or "there", bool(user_id))
        if built is None:
            done("skipped_none"); continue
        _feat, subject, body, html, att = built
        try:
            result = send(to, subject, body, html=html, attachments=att) if att else send(to, subject, body, html=html)
        except Exception as e:                             # noqa: BLE001 - a bad send must not stop the queue
            result = {"sent": False, "detail": f"{type(e).__name__}: {e}"}
        done(mailer.send_status(result), result.get("detail"), to, subject)
    return tally


def tick(conn, base_url, now=None, send=None):
    """The scheduler's once-a-minute call: raise what is due, then send what is owed."""
    now = now or tz.now_local()
    if st.get_setting(conn, "room_guest_purge_on") != now.date().isoformat():     # the privacy rule can't depend on a cron
        import rooms
        st.set_setting(conn, "room_guest_purge_on", now.date().isoformat())
        rooms.purge_guest_details(conn, now.date())
    expire_past_requests(conn, now.date())
    queue_escalations(conn, now)
    if now.hour >= MORNING_HOUR:
        queue_morning_digest(conn, now)
    if now.hour >= AFTERNOON_HOUR:
        queue_afternoon(conn, now)
    return flush(conn, base_url, now=now, send=send)
