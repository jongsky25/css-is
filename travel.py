"""Travel filing: database layer (docs/TRAVEL_FILING_PLAN.md). Rules live in travel_rules.py;
routes and templates only call these functions. This increment holds the seed data and the
small readers the rules need."""
from __future__ import annotations
import json

import storage as st
import tzutil as tz

_SEED_KEY = "travel.seeded"
SETTING_DEFAULTS = {
    "travel.enabled": "1",
    "travel.sig.head_name": "",
    "travel.sig.head_title": "OIC-Director",
    "travel.sig.certifier_name": "",
    "travel.sig.certifier_title": "Medical Officer V",
    "travel.sig.station": "",
    "travel.template_admins": "",
    "travel.retention_months": "12",
}

ROUTE_TYPES = (("residence_airport", "Residence ⇄ Airport"), ("residence_venue", "Residence ⇄ Venue"))
CEILINGS = (("rer", "residence_airport", 550), ("rer", "residence_venue", 450),
            ("tnvs", "*", 700), ("taxi", "*", 700), ("cenrr", "*", 300))

# Starter MC 114 wording: generic, with tokens the preview fills in. Template administrators
# edit or replace these in the justification library.
_STARTER = (
    ("Participation in an official activity", "separate",
     "This is to justify the participation of {{traveler_name}} in the official travel for "
     "{{activity_title}} on {{dates}} at {{venue}}.\n\n"
     "The activity required the traveller's participation for the reasons stated below. "
     "This justification is made to support approval of the travel."),
    ("Participation in an official activity (Appendix B)", "appendix_b",
     "The official travel for {{activity_title}} on {{dates}} at {{venue}} was necessary and "
     "was completed as planned."),
)


def ensure_defaults(conn):
    """Seed route types, ceilings, starter justifications and settings once. Keyed in
    app_setting so an administrator who later edits or removes a row never has it put back."""
    for k, v in SETTING_DEFAULTS.items():
        if st.get_setting(conn, k) is None:
            st.set_setting(conn, k, v)
    if st.get_setting(conn, _SEED_KEY) == "1":
        return
    now = tz.now_iso()
    for i, (code, label) in enumerate(ROUTE_TYPES):
        conn.execute("INSERT OR IGNORE INTO travel_route_type(code, label, active, sort) VALUES (?,?,1,?)",
                     (code, label, i))
    for mode, rt, amount in CEILINGS:
        conn.execute("INSERT OR IGNORE INTO travel_ceiling(mode, route_type, amount, updated_by, updated_at) "
                     "VALUES (?,?,?,?,?)", (mode, rt, amount, "system", now))
    for title, fmt, body in _STARTER:
        conn.execute("INSERT INTO travel_justification(title, format, body, active, updated_by, updated_at) "
                     "VALUES (?,?,?,1,'system',?)", (title, fmt, body, now))
    st.set_setting(conn, _SEED_KEY, "1")
    conn.commit()


def enabled(conn) -> bool:
    return st.get_setting(conn, "travel.enabled", "1") != "0"


def ceilings(conn) -> dict:
    """{(mode, route_type): amount} for travel_rules.ride_check, approved routes only."""
    active = {r[0] for r in conn.execute("SELECT code FROM travel_route_type WHERE active=1")}
    return {(m, rt): float(a) for m, rt, a in conn.execute("SELECT mode, route_type, amount FROM travel_ceiling")
            if m != "rer" or rt in active}


def answers_of(filing) -> dict:
    try:
        v = json.loads(filing.get("answers_json") or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


# ===================================================================== T2 ===
# Filing lifecycle. Every state change goes through here so the rules live in one place.

import re
import sqlite3
from datetime import date, timedelta
from urllib.parse import urlparse

import office_calendar as oc
import rooms
import travel_checklist as tc
import travel_rules as tr

KINDS = ("ca", "liquidation", "reimbursement")
KIND_LABELS = {"ca": "Cash advance", "liquidation": "Liquidation", "reimbursement": "Reimbursement"}
STATUS_LABELS = {"open": "In progress", "ready": "Ready to sign", "submitted": "Submitted",
                 "withdrawn": "Withdrawn"}
MC114_FORMATS = (("none", "No MC 114 justification needed"), ("separate", "A separate justification sheet"),
                 ("appendix_b", "Inside Appendix B"))
ROLE_CODES = tuple(c for c, _ in tc.ROLES)
CHOICE_BACK_DAYS, CHOICE_AHEAD_DAYS = 120, 365
_GOOGLE_HOSTS = ("drive.google.com", "docs.google.com")
_ITEM_FIELDS = ("filing_id", "item_code", "handling", "state", "drive_url", "drive_file_id", "doc_url",
                "doc_state", "fmis_ref", "note", "updated_at")


class TravelError(Exception):
    """A request the rules refuse. The message is safe to show the user."""


class Unliquidated(TravelError):
    """Starting a cash advance while an earlier one has no liquidation: warn first."""
    def __init__(self, filings):
        super().__init__("You have a cash advance that has not been liquidated.")
        self.filings = filings


def _rows(conn, sql, args=()):
    cur = conn.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _iso_or_none(s):
    try:
        return date.fromisoformat((s or "").strip()).isoformat()
    except ValueError:
        return None


# ------------------------------------------------------------------ reads ---

def get_filing(conn, filing_id):
    r = _rows(conn, "SELECT * FROM travel_filing WHERE id=?", (filing_id,))
    return r[0] if r else None


def get_by_ref(conn, ref):
    r = _rows(conn, "SELECT * FROM travel_filing WHERE ref_code=?", (ref,))
    return r[0] if r else None


def can_view(conn, user, filing) -> bool:
    """The owner, or an Admin Unit member (who may look and decide flags, never edit)."""
    return bool(filing and user and (filing["user_id"] == user["id"] or rooms.is_room_admin(conn, user)))


def is_owner(user, filing) -> bool:
    return bool(filing and user and filing["user_id"] == user["id"])


def list_for_user(conn, user_id):
    return _rows(conn, "SELECT * FROM travel_filing WHERE user_id=? "
                       "ORDER BY (status='withdrawn'), act_end DESC, id DESC", (user_id,))


def live_ca(conn, user_id, entry_id, event_id):
    """The user's non-withdrawn cash advance for this activity, or None."""
    if not entry_id and not event_id:
        return None
    r = _rows(conn, "SELECT * FROM travel_filing WHERE user_id=? AND kind='ca' AND status<>'withdrawn' "
                    "AND COALESCE(entry_id,-1)=? AND COALESCE(event_id,-1)=?",
              (user_id, entry_id or -1, event_id or -1))
    return r[0] if r else None


def liquidations_of(conn, ca_id):
    return _rows(conn, "SELECT * FROM travel_filing WHERE kind='liquidation' AND ca_filing_id=? "
                       "AND status<>'withdrawn'", (ca_id,))


def unliquidated_cas(conn, user_id, today):
    """Submitted cash advances whose activity is over and that have no live liquidation."""
    today = _d(today).isoformat()
    return _rows(conn, """SELECT f.* FROM travel_filing f
                          WHERE f.user_id=? AND f.kind='ca' AND f.status='submitted' AND f.act_end < ?
                            AND NOT EXISTS (SELECT 1 FROM travel_filing l WHERE l.kind='liquidation'
                                            AND l.ca_filing_id=f.id AND l.status<>'withdrawn')
                          ORDER BY f.act_end""", (user_id, today))


def view_items(conn, filing):
    """The filing's checklist: each applicable row with its saved state, in checklist order."""
    saved = {r["item_code"]: r for r in _rows(conn, "SELECT * FROM travel_item WHERE filing_id=?",
                                              (filing["id"],))}
    out = []
    for spec in tr.build_checklist(filing["kind"], effective_answers(filing)):
        row = saved.get(spec.code, {})
        out.append({"code": spec.code, "label": spec.label, "handling": spec.handling,
                    "requirement": spec.requirement, "copies": spec.copies, "wet_sign": spec.wet_sign,
                    "note_hint": spec.note, "state": row.get("state") or "missing",
                    "drive_url": row.get("drive_url"), "doc_url": row.get("doc_url"),
                    "doc_state": row.get("doc_state"), "fmis_ref": row.get("fmis_ref") or "",
                    "note": row.get("note") or ""})
    return out


def flags_of(conn, filing_id):
    return _rows(conn, "SELECT * FROM travel_flag WHERE filing_id=? ORDER BY id", (filing_id,))


def missing_for(conn, filing):
    return tr.completeness(filing, view_items(conn, filing), flags_of(conn, filing["id"]))


def effective_answers(filing) -> dict:
    """The checklist drivers plus the filing columns the rules read."""
    a = dict(answers_of(filing))
    a["mc114_format"] = filing.get("mc114_format") or "none"
    return a


# ----------------------------------------------------------------- choices ---

def activity_choices(conn, user, today):
    """Activities this person is attached to, 120 days back to 365 ahead, each once:
    [{entry_id, event_id, title, start, end, venue}]. An overlay entry and its CSS activity
    appear once, as the activity."""
    today = _d(today)
    items = oc.items_between(conn, user, today - timedelta(days=CHOICE_BACK_DAYS),
                             today + timedelta(days=CHOICE_AHEAD_DAYS), scope="mine",
                             layers=["entries", "activities"])
    out, seen = [], set()
    for i in items:
        if i["layer"] == "activities" and i.get("css"):
            ident = (None, i["css"]["event_id"], i["start"])
        elif i["layer"] == "entries" and i["key"].startswith("entry:"):
            ident = (int(i["key"].split(":")[1]), None, i["start"])
        else:
            continue
        if ident in seen:
            continue
        seen.add(ident)
        out.append({"entry_id": ident[0], "event_id": ident[1], "title": i["title"], "start": i["start"],
                    "end": i["end"], "venue": i.get("venue") or ""})
    return out


def find_choice(choices, entry_id=None, event_id=None, on=None):
    """The choice for this activity; for a repeating item, the occurrence starting on `on`
    (else the first one)."""
    hits = [c for c in choices if (entry_id and c["entry_id"] == entry_id)
            or (event_id and c["event_id"] == event_id)]
    if on:
        hits = [c for c in hits if c["start"] == on] or hits
    return hits[0] if hits else None


def resolve_source(conn, user, today, entry_id=None, event_id=None, on=None):
    """Authorise and snapshot an activity for a new filing. Returns a dict with source_kind,
    entry_id, event_id, title, start, end, venue. Raises TravelError when the person may not
    file against it (an entry they cannot see, an activity they are not attached to)."""
    if entry_id:
        e = oc.viewable_entry(conn, user, entry_id)
        if e is None:
            raise TravelError("That calendar item was not found.")
        if e.get("event_id"):                 # an overlay on a CSS activity: file against the activity
            entry_id, event_id = None, e["event_id"]
        else:
            start, end = e["start_date"], e["end_date"] or e["start_date"]
            if e.get("rrule"):
                ch = find_choice(activity_choices(conn, user, today), entry_id=entry_id, on=on)
                if ch:
                    start, end = ch["start"], ch["end"]
            return {"source_kind": "entry", "entry_id": entry_id, "event_id": None, "title": e["title"],
                    "start": start, "end": end, "venue": e.get("venue") or ""}
    if event_id:
        ch = find_choice(activity_choices(conn, user, today), event_id=event_id)
        if ch is None:
            raise TravelError("You can only file travel for activities you are part of.")
        return {"source_kind": "css_event", "entry_id": None, "event_id": event_id, "title": ch["title"],
                "start": ch["start"], "end": ch["end"], "venue": ch["venue"]}
    return {"source_kind": "blank", "entry_id": None, "event_id": None, "title": "", "start": "",
            "end": "", "venue": ""}


# ------------------------------------------------------------------ writes ---

def clean_answers(raw, kind=None) -> dict:
    """Keep only the checklist drivers (and the role); store booleans as 1/0. With `kind`,
    drivers that do not apply to that kind are dropped."""
    out = {}
    for key, _label, kinds in tc.ANSWER_KEYS:
        if kind is not None:
            if kind in kinds:                       # an unticked box is an answer too
                out[key] = 1 if tc.truthy(raw.get(key)) else 0
        elif key in raw:
            out[key] = 1 if tc.truthy(raw[key]) else 0
    role = (raw.get("role") or "").strip()
    if role in ROLE_CODES:
        out["role"] = role
    return out


def _stamp(conn, filing_id, now):
    conn.execute("UPDATE travel_filing SET updated_at=? WHERE id=?", (now, filing_id))


def sync_items(conn, filing):
    """Make sure a row exists for every applicable checklist item. Rows that stop applying are
    kept (their links come back if the answer is switched back)."""
    have = {r[0] for r in conn.execute("SELECT item_code FROM travel_item WHERE filing_id=?", (filing["id"],))}
    for spec in tr.build_checklist(filing["kind"], effective_answers(filing)):
        if spec.code not in have:
            conn.execute("INSERT INTO travel_item(filing_id, item_code, handling, state, updated_at) "
                         "VALUES (?,?,?,'missing',?)", (filing["id"], spec.code, spec.handling, tz.now_iso()))


def create_filing(conn, user, *, kind, source, answers, mc114_format="none", role="", dpo_no="", dpo_date="",
                  ca_filing_id=None, advance_amount=None, today, acknowledged=False):
    """Open a filing. Raises TravelError (message safe to show) or Unliquidated (warn first)."""
    today = _d(today)
    if kind not in KINDS:
        raise TravelError("Choose what you are filing.")
    title = " ".join((source.get("title") or "").split())[:200]
    start, end = _iso_or_none(source.get("start")), _iso_or_none(source.get("end"))
    if source["source_kind"] == "blank" and not (title and start and end):
        raise TravelError("Enter the activity name, the first day and the last day.")
    if not (title and start and end):
        raise TravelError("That activity has no usable dates.")
    if end < start:
        raise TravelError("The last day is before the first day.")
    if mc114_format not in ("none", "separate", "appendix_b"):
        mc114_format = "none"
    ans = clean_answers({**answers, "role": role}, kind)
    if "role" not in ans:
        raise TravelError("Choose your role in this activity.")
    entry_id, event_id = source.get("entry_id"), source.get("event_id")
    live = live_ca(conn, user["id"], entry_id, event_id)
    if kind == "ca":
        msg = tr.ca_lead_error(start, today)
        if msg:
            raise TravelError(msg)
        if live:
            raise TravelError("You already have a cash advance for this activity.")
        old = unliquidated_cas(conn, user["id"], today)
        if old and not acknowledged:
            raise Unliquidated(old)
    elif kind == "reimbursement" and live:
        raise TravelError("You have a cash advance for this activity, so file a liquidation instead.")
    ca_id, amount = None, None
    if kind == "liquidation":
        if ca_filing_id:
            ca = get_filing(conn, ca_filing_id)
            if not ca or ca["user_id"] != user["id"] or ca["kind"] != "ca" or ca["status"] == "withdrawn":
                raise TravelError("Choose one of your own cash advances to liquidate.")
            if ca["status"] != "submitted":
                raise TravelError("Mark that cash advance as submitted before liquidating it.")
            ca_id, amount = ca["id"], ca["advance_amount"]
        else:
            try:
                amount = float(str(advance_amount or "").replace(",", ""))
            except ValueError:
                amount = 0
            if amount <= 0:
                raise TravelError("Choose the cash advance you are liquidating, or enter the amount "
                                  "you received for one filed outside this platform.")
    elif kind == "ca" and advance_amount not in (None, ""):
        try:
            amount = float(str(advance_amount).replace(",", ""))
        except ValueError:
            raise TravelError("Enter the cash advance amount as a number.")
        if amount < 0:
            raise TravelError("The amount cannot be negative.")
    deadline, rule = tr.deadline_for(conn, kind, end, today)
    now = tz.now_iso()
    try:
        cur = conn.execute(
            "INSERT INTO travel_filing(user_id, kind, source_kind, entry_id, event_id, act_title, act_start, "
            "act_end, act_venue, dpo_no, dpo_date, answers_json, advance_amount, ca_filing_id, mc114_format, "
            "deadline_date, deadline_rule, status, gen_state, opened_at, created_by, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'open','idle',?,?,?)",
            (user["id"], kind, source["source_kind"], entry_id, event_id, title, start, end,
             (source.get("venue") or "").strip()[:200] or None, (dpo_no or "").strip()[:60] or None,
             _iso_or_none(dpo_date), json.dumps(ans), amount, ca_id, mc114_format, deadline, rule,
             now, user["username"], now))
    except sqlite3.IntegrityError:
        conn.rollback()
        raise TravelError("You already have a cash advance for this activity.")
    fid = cur.lastrowid
    conn.execute("UPDATE travel_filing SET ref_code=? WHERE id=?", (f"TF-{today:%y%m}-{fid:04d}", fid))
    filing = get_filing(conn, fid)
    sync_items(conn, filing)
    conn.commit()
    return get_filing(conn, fid)


def _touch_open(conn, filing, now):
    """An edit to a filing that was ready sends it back to 'open' so it is checked again."""
    if filing["status"] == "ready":
        conn.execute("UPDATE travel_filing SET status='open', ready_at=NULL WHERE id=?", (filing["id"],))


def _editable(filing):
    if filing["status"] not in ("open", "ready"):
        raise TravelError("This filing is %s and can no longer be changed." % STATUS_LABELS[filing["status"]].lower())


def update_answers(conn, filing, answers, *, mc114_format=None, role=None, dpo_no=None, dpo_date=None,
                   advance_amount=None):
    """Change the checklist drivers and rebuild the checklist, keeping existing links."""
    _editable(filing)
    ans = answers_of(filing)
    new = clean_answers({**answers, "role": role if role is not None else ans.get("role", "")})
    keep = {k: v for k, v in ans.items() if k not in {a[0] for a in tc.ANSWER_KEYS}}
    merged = {**keep, **{k: new.get(k, 0) for k, _l, kinds in tc.ANSWER_KEYS if filing["kind"] in kinds},
              **({"role": new["role"]} if "role" in new else {})}
    fmt = mc114_format if mc114_format in ("none", "separate", "appendix_b") else filing["mc114_format"]
    now = tz.now_iso()
    sets = {"answers_json": json.dumps(merged), "mc114_format": fmt, "updated_at": now}
    if dpo_no is not None:
        sets["dpo_no"] = dpo_no.strip()[:60] or None
    if dpo_date is not None:
        sets["dpo_date"] = _iso_or_none(dpo_date)
    if advance_amount is not None and filing["kind"] in ("ca", "liquidation") and not filing["ca_filing_id"]:
        try:
            sets["advance_amount"] = float(str(advance_amount).replace(",", "")) if str(advance_amount).strip() else None
        except ValueError:
            raise TravelError("Enter the amount as a number.")
    conn.execute("UPDATE travel_filing SET %s WHERE id=?" % ", ".join(f"{k}=?" for k in sets),
                 (*sets.values(), filing["id"]))
    _touch_open(conn, filing, now)
    sync_items(conn, get_filing(conn, filing["id"]))
    conn.commit()
    return get_filing(conn, filing["id"])


def _item_spec(filing, code):
    for spec in tr.build_checklist(filing["kind"], effective_answers(filing)):
        if spec.code == code:
            return spec
    raise TravelError("That document is not on this checklist.")


def valid_drive_link(url) -> str:
    """A Google Drive / Docs link we are willing to store, else ''."""
    url = (url or "").strip()
    try:
        p = urlparse(url)
    except ValueError:
        return ""
    ok = p.scheme == "https" and (p.hostname or "") in _GOOGLE_HOSTS and len(url) <= 500
    return url if ok else ""


def save_item(conn, filing, code, *, drive_url=None, na=None, fmis_ref=None, note=None):
    """Save what the person entered for one checklist row. Only the fields passed are changed."""
    _editable(filing)
    spec = _item_spec(filing, code)
    sync_items(conn, filing)
    sets = {}
    if drive_url is not None:
        if spec.handling not in ("upload", "carry", "generate"):
            raise TravelError("This document does not take a Drive link.")
        manual = spec.handling == "generate"        # a form you made yourself instead of generating it
        if drive_url.strip():
            link = valid_drive_link(drive_url)
            if not link:
                raise TravelError("Paste a Google Drive link (it starts with https://drive.google.com/).")
            sets.update(doc_url=link, doc_state="manual", state="present") if manual else \
                sets.update(drive_url=link, state="present")
        else:
            sets.update(doc_url=None, doc_state=None, state="missing") if manual else \
                sets.update(drive_url=None, drive_file_id=None, state="missing")
    if na is not None:
        if spec.handling not in ("upload", "carry"):
            raise TravelError("Only uploaded documents can be marked as not applicable.")
        if na:
            sets.update(state="na")
        elif "state" not in sets:
            sets["state"] = "present" if (sets.get("drive_url") or _saved(conn, filing, code, "drive_url")) else "missing"
    if fmis_ref is not None:
        if spec.handling != "fmis":
            raise TravelError("Only FMIS documents take an FMIS reference.")
        sets["fmis_ref"] = " ".join(fmis_ref.split())[:120] or None
    if note is not None:
        sets["note"] = " ".join(note.split())[:300] or None
        if spec.handling == "carry" and sets["note"] and "state" not in sets \
                and _saved(conn, filing, code, "state") == "missing":
            sets["state"] = "present"
    if not sets:
        return
    sets["updated_at"] = tz.now_iso()
    conn.execute("UPDATE travel_item SET %s WHERE filing_id=? AND item_code=?" % ", ".join(f"{k}=?" for k in sets),
                 (*sets.values(), filing["id"], code))
    _touch_open(conn, filing, sets["updated_at"])
    _stamp(conn, filing["id"], sets["updated_at"])
    conn.commit()


def set_drive_file_id(conn, filing, code, file_id):
    """Remember the Drive file id the relay confirmed for an item's link."""
    conn.execute("UPDATE travel_item SET drive_file_id=?, updated_at=? WHERE filing_id=? AND item_code=?",
                 (file_id, tz.now_iso(), filing["id"], code))
    conn.commit()


def _saved(conn, filing, code, col):
    r = conn.execute(f"SELECT {col} FROM travel_item WHERE filing_id=? AND item_code=?", (filing["id"], code)).fetchone()
    return r[0] if r else None


def mark_ready(conn, filing):
    if filing["status"] == "ready":
        return filing
    if filing["status"] != "open":
        raise TravelError("Only a filing in progress can be marked ready.")
    missing = missing_for(conn, filing)
    if missing:
        raise TravelError("Not ready yet: " + missing[0] + (f" (and {len(missing) - 1} more)" if len(missing) > 1 else ""))
    now = tz.now_iso()
    conn.execute("UPDATE travel_filing SET status='ready', ready_at=?, updated_at=? WHERE id=?", (now, now, filing["id"]))
    conn.commit()
    return get_filing(conn, filing["id"])


def mark_submitted(conn, filing):
    if filing["status"] != "ready":
        raise TravelError("Mark the filing ready before marking it submitted.")
    now = tz.now_iso()
    conn.execute("UPDATE travel_filing SET status='submitted', submitted_at=?, updated_at=? WHERE id=?",
                 (now, now, filing["id"]))
    conn.commit()
    return get_filing(conn, filing["id"])


def withdraw(conn, filing):
    if filing["status"] in ("submitted", "withdrawn"):
        raise TravelError("A %s filing cannot be withdrawn." % STATUS_LABELS[filing["status"]].lower())
    if filing["kind"] == "ca":
        libs = liquidations_of(conn, filing["id"])
        if libs:
            raise TravelError("This cash advance is being liquidated (%s). Withdraw that liquidation first."
                              % libs[0]["ref_code"])
    now = tz.now_iso()
    conn.execute("UPDATE travel_filing SET status='withdrawn', withdrawn_at=?, updated_at=? WHERE id=?",
                 (now, now, filing["id"]))
    conn.commit()
    return get_filing(conn, filing["id"])


def refresh_deadline(conn, filing):
    """While a filing is still open, follow the linked activity if its dates moved. Frozen after
    'ready'. Never raises: a missing activity just keeps the snapshot."""
    if filing["status"] != "open":
        return filing
    try:
        if filing["entry_id"]:
            import storage
            e = storage.cal_get(conn, filing["entry_id"])
            cur = (e["start_date"], e["end_date"] or e["start_date"]) if e and not e.get("rrule") else None
        elif filing["event_id"]:
            r = conn.execute("SELECT event_date, end_date FROM event WHERE id=?", (filing["event_id"],)).fetchone()
            cur = ((r[0] or "")[:10], (r[1] or r[0] or "")[:10]) if r and r[0] else None
        else:
            cur = None
        if not cur or (cur[0], cur[1]) == (filing["act_start"], filing["act_end"]) or cur[1] < cur[0]:
            return filing
        rule_day = filing["opened_at"][:10]
        deadline, rule = tr.deadline_for(conn, filing["kind"], cur[1], rule_day)
        conn.execute("UPDATE travel_filing SET act_start=?, act_end=?, deadline_date=?, deadline_rule=?, updated_at=? "
                     "WHERE id=?", (cur[0], cur[1], deadline, rule, tz.now_iso(), filing["id"]))
        conn.commit()
        return get_filing(conn, filing["id"])
    except Exception:                                       # noqa: BLE001
        conn.rollback()
        return filing


# ------------------------------------------------------------ summaries ---

def deadline_words(filing, today):
    """('Due in 3 days' | 'Due today' | 'Overdue', tone) for a filing with a deadline, else (None, None)."""
    if not filing.get("deadline_date"):
        return None, None
    n = (_d(filing["deadline_date"]) - _d(today)).days
    if n < 0:
        return "Overdue", "late"
    if n == 0:
        return "Due today", "warn"
    return f"Due in {n} day{'s' if n != 1 else ''}", ("warn" if n <= 2 else "ok")


_STAGE = {"open": 1, "ready": 2, "submitted": 3}
_KIND_RANK = {"ca": 1, "reimbursement": 2, "liquidation": 2}


def _summary(conn, filings, today):
    """One chip for the best filing among those attached to an activity."""
    best = max(filings, key=lambda f: (_KIND_RANK[f["kind"]] if f["status"] == "submitted" else 0,
                                       _STAGE[f["status"]], f["id"]))
    url = f"/travel/f/{best['ref_code']}"
    if best["status"] == "submitted":
        if best["kind"] == "ca":
            due, _rule = tr.deadline_for(conn, "liquidation", best["act_end"], today)
            return {"label": f"CA filed, liquidation due {_d(due):%b} {_d(due).day}", "tone": "warn", "url": url}
        return {"label": "Filed", "tone": "ok", "url": url}
    if best["status"] == "ready":
        return {"label": "Ready to sign", "tone": "ok", "url": url}
    words, tone = deadline_words(best, today)
    return {"label": words or "In progress", "tone": tone or "none", "url": url}


def filing_summaries(conn, user_id, entry_ids, event_ids, today=None):
    """{("entry"|"event", id): {label, tone, url}} for the activities this person has filed
    against. ONE query per 500 ids; withdrawn filings are ignored."""
    today = today or tz.today_local()
    by_key = {}
    for kind, ids, col in (("entry", list(dict.fromkeys(entry_ids)), "entry_id"),
                           ("event", list(dict.fromkeys(event_ids)), "event_id")):
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            for f in _rows(conn, f"SELECT * FROM travel_filing WHERE user_id=? AND status<>'withdrawn' "
                                 f"AND {col} IN ({','.join('?' * len(chunk))})", (user_id, *chunk)):
                by_key.setdefault((kind, f[col]), []).append(f)
    return {k: _summary(conn, v, today) for k, v in by_key.items()}


# --------------------------------------------------------- calendar hooks ---

def calendar_chips(conn, user_id, entry_ids, event_ids, today=None):
    """The calendar's per-item filing chips for one viewer, or None when travel filing is off
    (or failed). The calendar must never break because of travel filing."""
    try:
        if not enabled(conn):
            return None
        return filing_summaries(conn, user_id, entry_ids, event_ids, today)
    except Exception:                                       # noqa: BLE001
        return None


def not_filed_chip(entry_id, event_id, start, end, today):
    """'Not filed' for an activity the viewer is part of that is current, coming up, or ended
    in the last 60 days; None otherwise (older items stay quiet)."""
    today = _d(today)
    if _d(end) < today - timedelta(days=60) or _d(start) > today + timedelta(days=365):
        return None
    q = f"event={event_id}" if event_id else f"entry={entry_id}&date={start}"
    return {"label": "Not filed", "tone": "none", "url": f"/travel/new?{q}"}


def event_url_for(conn, user, event_id):
    """'/travel/new?event=ID' when this person is part of the CSS activity (creator, on its calendar
    overlay, or a speaker on it) and travel filing is on; else None. A few indexed lookups, no
    calendar scan, because it runs on every activity page view."""
    if not user or not enabled(conn):
        return None
    uid = user["id"]
    hit = (
        conn.execute("SELECT 1 FROM event WHERE id=? AND created_by=?", (event_id, user.get("username"))).fetchone()
        or conn.execute("SELECT 1 FROM calendar_entry_person p JOIN calendar_entry c ON c.id=p.entry_id "
                        "WHERE c.event_id=? AND p.user_id=?", (event_id, uid)).fetchone()
        or conn.execute("SELECT 1 FROM event_form ef JOIN form_instance fi ON fi.id=ef.form_instance_id AND fi.survey_type=3 "
                        "JOIN admin_user a ON a.rp_id=fi.rp_id WHERE ef.event_id=? AND a.id=?", (event_id, uid)).fetchone())
    return f"/travel/new?event={event_id}" if hit else None
