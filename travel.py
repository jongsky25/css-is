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
                "doc_state", "fmis_ref", "note", "updated_at", "drive_source")


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
                    "drive_url": row.get("drive_url"), "drive_source": row.get("drive_source"),
                    "doc_url": row.get("doc_url"),
                    "doc_state": row.get("doc_state"), "fmis_ref": row.get("fmis_ref") or "",
                    "note": row.get("note") or ""})
    return out


def flags_of(conn, filing_id):
    return _rows(conn, "SELECT * FROM travel_flag WHERE filing_id=? ORDER BY id", (filing_id,))


def sync_flags(conn, filing, specs):
    """Make the filing's flag rows match `specs` (travel_rules.FlagSpec list), keyed by `sig`.
    A flag whose fingerprint is unchanged keeps its decision; a new one opens; one whose fare or
    route changed (so its sig no longer matches) is dropped and its replacement opens."""
    now = tz.now_iso()
    want = {sp.sig: sp for sp in specs}
    have = {r["sig"]: r for r in flags_of(conn, filing["id"])}
    for sig, row in have.items():
        if sig not in want:
            conn.execute("DELETE FROM travel_flag WHERE id=?", (row["id"],))
    for sig, sp in want.items():
        if sig not in have:
            conn.execute("INSERT INTO travel_flag(filing_id, kind, sig, detail, state, created_at) VALUES (?,?,?,?,'open',?)",
                         (filing["id"], sp.kind, sig, sp.detail, now))
    conn.commit()


def set_derived_answers(conn, filing, derived):
    """Store the platform-set drivers (rides_cenrr / rides_rer) and add any checklist rows they bring."""
    ans = answers_of(filing)
    ans.update({k: 1 if v else 0 for k, v in derived.items() if k in ("rides_cenrr", "rides_rer")})
    conn.execute("UPDATE travel_filing SET answers_json=?, updated_at=? WHERE id=?",
                 (json.dumps(ans), tz.now_iso(), filing["id"]))
    sync_items(conn, get_filing(conn, filing["id"]))
    conn.commit()
    return get_filing(conn, filing["id"])


def revision_of(doc_state) -> int:
    """'done:3' / 'pending:3' / 'failed:3' -> 3; anything else (None, 'manual') -> 0."""
    m = re.match(r"^(?:pending|done|failed):(\d+)$", doc_state or "")
    return int(m.group(1)) if m else 0


def start_generation(conn, filing, codes):
    """Mark the chosen generate-items as being made and return {code: revision}. A new revision per
    click keeps the old document in Drive; the relay reuses a revision's document on a transport retry."""
    now, revs = tz.now_iso(), {}
    for code in codes:
        n = revision_of(_saved(conn, filing, code, "doc_state")) + 1
        revs[code] = n
        conn.execute("UPDATE travel_item SET doc_state=?, note=NULL, updated_at=? WHERE filing_id=? AND item_code=?",
                     (f"pending:{n}", now, filing["id"], code))
    conn.execute("UPDATE travel_filing SET gen_state='running', updated_at=? WHERE id=?", (now, filing["id"]))
    conn.commit()
    return revs


def finish_item(conn, filing_id, code, rev, *, url=None, extra=None, error=None):
    now = tz.now_iso()
    if url:
        conn.execute("UPDATE travel_item SET doc_url=?, doc_state=?, state='present', note=?, updated_at=? "
                     "WHERE filing_id=? AND item_code=?", (url, f"done:{rev}", extra or None, now, filing_id, code))
    else:
        conn.execute("UPDATE travel_item SET doc_state=?, note=?, updated_at=? WHERE filing_id=? AND item_code=?",
                     (f"failed:{rev}", (error or "Failed")[:300], now, filing_id, code))
    conn.commit()


def finish_generation(conn, filing_id):
    bad = conn.execute("SELECT 1 FROM travel_item WHERE filing_id=? AND (doc_state LIKE 'failed:%' OR doc_state LIKE 'pending:%') "
                       "LIMIT 1", (filing_id,)).fetchone()
    conn.execute("UPDATE travel_filing SET gen_state=?, updated_at=? WHERE id=?",
                 ("failed" if bad else "done", tz.now_iso(), filing_id))
    conn.commit()


STALE_RUN = timedelta(minutes=10)


def generation_status(conn, filing):
    """gen_state plus one entry per generate-item. A run that has not moved for STALE_RUN (the server
    restarted mid-way) is closed as failed so the person can retry."""
    from datetime import datetime
    if filing["gen_state"] == "running":
        try:
            idle = datetime.fromisoformat(tz.now_iso()) - datetime.fromisoformat(filing["updated_at"])
        except (TypeError, ValueError):
            idle = timedelta(0)
        if idle > STALE_RUN:
            conn.execute("UPDATE travel_item SET doc_state=REPLACE(doc_state,'pending:','failed:'), "
                         "note='The run was interrupted. Try again.' WHERE filing_id=? AND doc_state LIKE 'pending:%'",
                         (filing["id"],))
            finish_generation(conn, filing["id"])
            filing = get_filing(conn, filing["id"])
    out = []
    for it in view_items(conn, filing):
        if it["handling"] != "generate":
            continue
        ds = it["doc_state"] or ""
        state = ds.split(":")[0] if ":" in ds else (ds or "idle")
        out.append({"code": it["code"], "label": it["label"], "state": state, "url": it["doc_url"] or "",
                    "error": it["note"] if state == "failed" else ""})
    return {"gen_state": filing["gen_state"], "items": out}


# ================================================================ T7: admin data ===
# Ceilings and routes (Administrative Section), the justification library (template administrators),
# the retention purge and the holiday notice.

MAX_CEILING = 100000
LIB_TOKENS = ("traveler_name", "activity_title", "dates", "venue")
FLAT_CEILINGS = (("tnvs", "TNVS (with receipt)"), ("taxi", "Metered taxi (with receipt)"),
                 ("cenrr", "CENRR, up to (no receipt)"))


def _ceiling_amount(v, label):
    try:
        n = float(str(v).replace(",", "").strip())
    except ValueError:
        raise TravelError(f"{label}: enter an amount as a number.")
    if not (0 < n <= MAX_CEILING):
        raise TravelError(f"{label}: the amount must be more than 0 and at most {MAX_CEILING:,}.")
    return round(n, 2)


def route_types(conn):
    """Every route type with its RER ceiling (None if the ceiling row is missing)."""
    rer = {rt: a for m, rt, a in conn.execute("SELECT mode, route_type, amount FROM travel_ceiling WHERE mode='rer'")}
    return [{"code": c, "label": l, "active": bool(a), "rer": rer.get(c)}
            for c, l, a in conn.execute("SELECT code, label, active FROM travel_route_type ORDER BY sort, code")]


def flat_ceilings(conn):
    got = {m: a for m, rt, a in conn.execute("SELECT mode, route_type, amount FROM travel_ceiling WHERE route_type='*'")}
    return [{"mode": m, "label": l, "amount": got.get(m)} for m, l in FLAT_CEILINGS]


def save_ceilings(conn, by, form):
    """Save every ceiling and route switch posted by the Admin Unit screen. All values are checked
    before anything is written. Returns the number of values that changed."""
    now, writes, active = tz.now_iso(), [], {}
    for r in route_types(conn):
        key = f"rer__{r['code']}"
        if key in form:
            writes.append(("rer", r["code"], _ceiling_amount(form[key], f"RER ceiling for {r['label']}")))
        active[r["code"]] = 1 if form.get(f"active__{r['code']}") == "1" else 0
    for mode, label in FLAT_CEILINGS:
        if mode in form:
            writes.append((mode, "*", _ceiling_amount(form[mode], label)))
    changed = 0
    for mode, rt, amount in writes:
        old = conn.execute("SELECT amount FROM travel_ceiling WHERE mode=? AND route_type=?", (mode, rt)).fetchone()
        if old is None or float(old[0]) != amount:
            conn.execute("INSERT INTO travel_ceiling(mode, route_type, amount, updated_by, updated_at) VALUES (?,?,?,?,?) "
                         "ON CONFLICT(mode, route_type) DO UPDATE SET amount=excluded.amount, "
                         "updated_by=excluded.updated_by, updated_at=excluded.updated_at", (mode, rt, amount, by, now))
            changed += 1
    for code, on in active.items():
        was = conn.execute("SELECT active FROM travel_route_type WHERE code=?", (code,)).fetchone()
        if was is not None and bool(was[0]) != bool(on):
            conn.execute("UPDATE travel_route_type SET active=? WHERE code=?", (on, code))
            changed += 1
    conn.commit()
    return changed


def add_route(conn, by, label, rer_amount):
    """A new approved route. It always gets its RER ceiling, because a route counts as approved only
    when it has one (see `ceilings`)."""
    label = " ".join((label or "").split())[:80]
    if not label:
        raise TravelError("Give the route a name, for example \"Residence \u21c4 Terminal 3\".")
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:40]
    if not slug:
        raise TravelError("Use letters or numbers in the route name.")
    amount = _ceiling_amount(rer_amount, "RER ceiling")
    if conn.execute("SELECT 1 FROM travel_route_type WHERE code=? OR lower(label)=lower(?)", (slug, label)).fetchone():
        raise TravelError("There is already a route with that name.")
    order = conn.execute("SELECT COALESCE(MAX(sort), -1) + 1 FROM travel_route_type").fetchone()[0]
    now = tz.now_iso()
    conn.execute("INSERT INTO travel_route_type(code, label, active, sort) VALUES (?,?,1,?)", (slug, label, order))
    conn.execute("INSERT INTO travel_ceiling(mode, route_type, amount, updated_by, updated_at) VALUES ('rer',?,?,?,?)",
                 (slug, amount, by, now))
    conn.commit()
    return slug


def is_template_admin(conn, user) -> bool:
    names = {n.strip().lower() for n in st.get_setting(conn, "travel.template_admins", "").split(",") if n.strip()}
    return bool(user and (user.get("username") or "").lower() in names)


def justifications(conn):
    return _rows(conn, "SELECT * FROM travel_justification ORDER BY format, id")


def save_justification(conn, by, jid, title, fmt, body, active=True):
    """Add (jid empty) or change a library row. Only the four tokens are allowed, so a generated
    document never carries a raw {{placeholder}}."""
    title, body = " ".join((title or "").split())[:120], (body or "").replace("\r", "").strip()
    if not title:
        raise TravelError("Give the text a title.")
    if fmt not in ("separate", "appendix_b"):
        raise TravelError("Choose where the text is used.")
    if not body or len(body) > 6000:
        raise TravelError("The text must be between 1 and 6,000 characters.")
    bad = sorted(set(re.findall(r"\{\{([^}]*)\}\}", body)) - set(LIB_TOKENS))
    if bad:
        raise TravelError("Unknown placeholder {{%s}}. Use only %s." % (bad[0], ", ".join("{{%s}}" % t for t in LIB_TOKENS)))
    now = tz.now_iso()
    if jid:
        if not conn.execute("SELECT 1 FROM travel_justification WHERE id=?", (jid,)).fetchone():
            raise TravelError("That text no longer exists.")
        conn.execute("UPDATE travel_justification SET title=?, format=?, body=?, active=?, updated_by=?, updated_at=? WHERE id=?",
                     (title, fmt, body, 1 if active else 0, by, now, jid))
    else:
        jid = conn.execute("INSERT INTO travel_justification(title, format, body, active, updated_by, updated_at) "
                           "VALUES (?,?,?,?,?,?)", (title, fmt, body, 1 if active else 0, by, now)).lastrowid
    conn.commit()
    return jid


def holiday_notice(conn, today=None):
    """A sentence for the admin pages when next year's holidays are not loaded, else ''."""
    today = _d(today or tz.today_local())
    year = today.year + 1
    if st.holidays_between(conn, date(year, 1, 1), date(year, 12, 31)):
        return ""
    return (f"No holidays are loaded for {year}. A deadline that lands in {year} can fall on a holiday "
            f"until they are added (Administration, Holidays).")


def purge_filings(conn, months=None, today=None, dry_run=False, relay=None):
    """Retention: months after a filing was submitted (or withdrawn), trash the files the office stored for
    it in Drive, blank the personal links and notes on it and its flags, and clear its saved answers. The
    row, its status and its dates stay. A filing whose Drive files cannot be trashed is left for the next
    run, so no file outlives its record. Returns the number of filings (that would be) purged."""
    months = int(months or st.get_setting(conn, "travel.retention_months", "12") or 12)
    today = _d(today or tz.today_local())
    y, m = today.year, today.month - months
    while m <= 0:
        m += 12
        y -= 1
    cutoff = date(y, m, min(today.day, 28)).isoformat() + "T00:00:00"
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM travel_filing WHERE purged_at IS NULL AND ((status='submitted' AND submitted_at < ?) "
        "OR (status='withdrawn' AND withdrawn_at < ?))", (cutoff, cutoff))]
    if dry_run or not ids:
        return len(ids)
    ids = [i for i in ids if _trash_uploads(conn, i, relay)]
    if not ids:
        return 0
    qs, now = ",".join("?" * len(ids)), tz.now_iso()
    conn.execute(f"UPDATE travel_item SET drive_url=NULL, drive_file_id=NULL, drive_source=NULL, doc_url=NULL, fmis_ref=NULL, note=NULL, "
                 f"updated_at=? WHERE filing_id IN ({qs})", (now, *ids))
    conn.execute(f"UPDATE travel_flag SET detail=NULL, note=NULL WHERE filing_id IN ({qs})", ids)
    conn.execute(f"DELETE FROM travel_reading WHERE filing_id IN ({qs})", ids)
    conn.execute(f"UPDATE travel_filing SET answers_json='{{}}', purged_at=?, updated_at=? WHERE id IN ({qs})", (now, now, *ids))
    conn.commit()
    st.audit(conn, "system", "travel_purge", target_type="travel_filing", target_id=ids[0],
             summary=f"Removed links, notes and stored files from {len(ids)} travel filing(s) older than {months} months")
    return len(ids)


def _trash_uploads(conn, filing_id, relay=None):
    """Trash the Drive folders the office stored for one filing. True when there is nothing left to trash."""
    folders = [r[0] for r in conn.execute(
        "SELECT DISTINCT drive_file_id FROM travel_item WHERE filing_id=? AND drive_source='upload' "
        "AND drive_file_id IS NOT NULL", (filing_id,))]
    if not folders:
        return True
    import gdocs_relay
    if relay is None:
        if not gdocs_relay.configured():
            return False
        relay = gdocs_relay.get_relay()
    return all(relay.trash_file(fid).ok for fid in folders)


FLAG_OUTCOMES = ("verified", "rejected")


def flag_queue(conn, state="open", limit=200):
    """Flags for the Admin Unit, with the filing and person they belong to. Flags on filings that are
    withdrawn or already submitted are not listed. state: 'open' or 'decided'."""
    where = "g.state='open'" if state == "open" else "g.state IN ('verified','rejected')"
    order = "g.created_at, g.id" if state == "open" else "g.decided_at DESC, g.id DESC"
    return _rows(conn, f"""SELECT g.*, f.ref_code, f.kind AS filing_kind, f.act_title, f.act_start, f.act_end,
                                  f.status AS filing_status, f.user_id,
                                  COALESCE(NULLIF(rp.name,''), a.username) AS who
                           FROM travel_flag g JOIN travel_filing f ON f.id=g.filing_id
                           JOIN admin_user a ON a.id=f.user_id LEFT JOIN resource_person rp ON rp.id=a.rp_id
                           WHERE {where} AND f.status IN ('open','ready') ORDER BY {order} LIMIT ?""", (limit,))


def get_flag(conn, flag_id):
    r = _rows(conn, "SELECT * FROM travel_flag WHERE id=?", (flag_id,))
    return r[0] if r else None


def decide_flag(conn, flag, decided_by, outcome, note="", supervisor_confirmed=False):
    """Record the Admin Unit's outcome on a flag. The decision is theirs, made outside this site;
    this only records it. A rejection needs a note, and a participant-only trip is verified only with
    the supervisor's confirmation that the travel was necessary."""
    filing = get_filing(conn, flag["filing_id"])
    if not filing or filing["status"] not in ("open", "ready"):
        raise TravelError("This filing is no longer open, so its flags cannot be decided.")
    if outcome not in FLAG_OUTCOMES:
        raise TravelError("Choose verified or rejected.")
    note = " ".join((note or "").split())[:500]
    if outcome == "rejected" and not note:
        raise TravelError("Say why in the note when you reject a flag.")
    if outcome == "verified" and flag["kind"] == "participant_only" and not supervisor_confirmed:
        raise TravelError("Confirm that the supervisor said this travel was necessary.")
    now = tz.now_iso()
    conn.execute("UPDATE travel_flag SET state=?, note=?, supervisor_confirmed=?, decided_by=?, decided_at=? WHERE id=?",
                 (outcome, note or None, 1 if supervisor_confirmed else 0, decided_by, now, flag["id"]))
    if outcome == "rejected":
        _touch_open(conn, filing, now)                       # a ready filing goes back to be fixed
    conn.execute("UPDATE travel_filing SET updated_at=? WHERE id=?", (now, filing["id"]))
    conn.commit()
    return get_flag(conn, flag["id"])


def set_dpo_date(conn, filing, iso_date):
    """Put a DPO date on a filing that has none (read off the uploaded DPO). A date already there is never replaced."""
    d = _iso_or_none(iso_date)
    if not d:
        return
    conn.execute("UPDATE travel_filing SET dpo_date=?, updated_at=? WHERE id=? AND dpo_date IS NULL",
                 (d, tz.now_iso(), filing["id"]))
    conn.commit()


def _division_path(conn, org_path):
    """The org path of the division a unit sits in: the unit itself when it is a division, its parent when it is a
    section, None for a bureau-level or unknown unit."""
    row = conn.execute("SELECT level FROM org_unit WHERE path=?", (org_path or "",)).fetchone()
    if not row:
        return None
    if row[0] == "division":
        return org_path
    return org_path.rsplit("/", 1)[0] if row[0] == "section" and "/" in org_path else None


def directory_signers(conn, user_id, settings) -> dict:
    """The head of office and certifying officer for a filer, so they need not be typed on every filing.
    Head of office: the names set under Travel filing settings if given (an acting head, say), otherwise the
    Director in the directory. Certifying officer: the head of the filer's own division in the directory
    (never the filer), falling back to the names set under Travel filing settings. `settings` is the
    travel.sig.* dict; the result has the same keys with blanks filled where the directory knows."""
    out = dict(settings)
    if not (settings.get("head_name") or "").strip():
        director = st.org_seat_holder(conn, 3)
        if director:
            out["head_name"], out["head_title"] = director[0], director[1] or "Director"
    profile = st.get_user_profile(conn, user_id) or {}
    division = _division_path(conn, profile.get("org_path"))
    chief = st.org_seat_holder(conn, 2, org_path=division, exclude_rp_id=profile.get("rp_id")) if division else None
    if chief:
        out["certifier_name"], out["certifier_title"] = chief[0], chief[1] or "Division Chief"
    return out


def missing_for(conn, filing):
    return tr.completeness(filing, view_items(conn, filing), flags_of(conn, filing["id"]))


def next_action(filing, items, flags, missing):
    """The next useful action, using the same readiness rules as the checklist."""
    base = f"/travel/f/{filing['ref_code']}"
    if filing["status"] == "submitted":
        return {"url": base + "/ready", "label": "View print list"}
    if filing["status"] not in ("open", "ready"):
        return None
    if not missing:
        return {"url": base + "/ready", "label": "Print list and submit" if filing["status"] == "ready" else "Review and mark ready"}
    for it in items:
        if it["requirement"] != "required" or it["state"] == "na" or it["handling"] == "fmis":
            continue
        if it["handling"] == "generate" and not it.get("doc_url"):
            return {"url": base + "/prepare", "label": "Prepare the missing forms"}
        if it["handling"] in ("upload", "carry") and not it.get("drive_url"):
            if it["handling"] == "carry" and it.get("note"):
                continue
            return {"url": "#item-" + it["code"], "label": "Add " + it["label"]}
    if any(fl["state"] in ("open", "rejected") for fl in flags):
        return {"url": "#travel-flags", "label": "Review items with the Admin Unit"}
    return {"url": "#travel-answers", "label": "Complete claim details"}


def forms_ready_to_draft(items) -> list:
    """Labels of the Appendix A / B forms that can now be drafted: every document the person has to upload or carry
    over is in (or marked not applicable) and the appendix itself has not been made. [] while anything is still to
    upload, or when there is nothing left to make."""
    def waiting(it):
        if it["requirement"] != "required" or it["state"] == "na" or it["handling"] not in ("upload", "carry"):
            return False
        return not it.get("drive_url") and not (it["handling"] == "carry" and it.get("note"))
    if any(waiting(it) for it in items):
        return []
    return [it["label"] for it in items if it["code"] in ("appendix_a", "appendix_b")
            and it["requirement"] == "required" and it["state"] != "na" and not it.get("doc_url")]


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
    if not (dpo_no or "").strip():
        raise TravelError("Enter the Department Personnel Order (DPO) number. Every travel filing needs one.")
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
    carry_from_ca(conn, get_filing(conn, fid))
    return get_filing(conn, fid)


def carry_from_ca(conn, filing) -> bool:
    """A liquidation's "Appendix A of the cash advance" row is the form already made for that cash advance, so take its
    link instead of asking for it again. Only an untouched row is filled: one the person added, marked not applicable
    or removed is left as they set it. True when the row was filled."""
    if filing["kind"] != "liquidation" or not filing["ca_filing_id"] or filing["status"] not in ("open", "ready"):
        return False
    sync_items(conn, filing)
    row = conn.execute("SELECT state, drive_source FROM travel_item WHERE filing_id=? AND item_code='prev_appendix_a'",
                       (filing["id"],)).fetchone()
    if not row or row[0] != "missing" or row[1] is not None:
        return False
    ca = conn.execute("SELECT f.ref_code, i.doc_url FROM travel_filing f JOIN travel_item i ON i.filing_id=f.id "
                      "WHERE f.id=? AND i.item_code='appendix_a' AND i.doc_url IS NOT NULL", (filing["ca_filing_id"],)).fetchone()
    link = valid_drive_link(ca[1]) if ca else ""
    if not link:
        return False
    now = tz.now_iso()
    conn.execute("UPDATE travel_item SET drive_url=?, drive_file_id=NULL, drive_source='carried', state='present', "
                 "note=COALESCE(NULLIF(note,''), ?), updated_at=? WHERE filing_id=? AND item_code='prev_appendix_a'",
                 (link, f"Taken from cash advance {ca[0]}.", now, filing["id"]))
    conn.commit()
    return True


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
        if not dpo_no.strip():
            raise TravelError("Enter the Department Personnel Order (DPO) number. Every travel filing needs one.")
        sets["dpo_no"] = dpo_no.strip()[:60]
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
                sets.update(drive_url=link, drive_file_id=None, drive_source="link", state="present")
        else:
            sets.update(doc_url=None, doc_state=None, state="missing") if manual else \
                sets.update(drive_url=None, drive_file_id=None, state="missing",
                            drive_source="removed" if spec.handling == "carry" else None)   # a removed carry row is not filled in again
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
    if drive_url is not None or na:                    # the files the readings came from are gone or not needed
        conn.execute("DELETE FROM travel_reading WHERE filing_id=? AND item_code=?", (filing["id"], code))
    conn.execute("UPDATE travel_item SET %s WHERE filing_id=? AND item_code=?" % ", ".join(f"{k}=?" for k in sets),
                 (*sets.values(), filing["id"], code))
    _touch_open(conn, filing, sets["updated_at"])
    _stamp(conn, filing["id"], sets["updated_at"])
    conn.commit()


def uploaded_folder(conn, filing, code):
    """The Drive folder id the office made for this row's uploaded files, or None (nothing, or a pasted link)."""
    r = conn.execute("SELECT drive_file_id FROM travel_item WHERE filing_id=? AND item_code=? AND drive_source='upload'",
                     (filing["id"], code)).fetchone()
    return (r[0] or None) if r else None


def save_upload(conn, filing, code, folder_id, folder_url):
    """The relay confirmed a file in the row's folder: the row now links to that folder. Only the link and
    the folder id are kept, never the file."""
    _editable(filing)
    spec = _item_spec(filing, code)
    if spec.handling not in ("upload", "carry"):
        raise TravelError("This document does not take an uploaded file.")
    link = valid_drive_link(folder_url)
    if not link or not folder_id:
        raise TravelError("The upload was not confirmed. Try again.")
    sync_items(conn, filing)
    now = tz.now_iso()
    conn.execute("UPDATE travel_item SET drive_url=?, drive_file_id=?, drive_source='upload', state='present', "
                 "updated_at=? WHERE filing_id=? AND item_code=?", (link, folder_id, now, filing["id"], code))
    _touch_open(conn, filing, now)
    _stamp(conn, filing["id"], now)
    conn.commit()


def clear_upload(conn, filing, code):
    """Forget a row's uploaded folder (after it was trashed in Drive): the row goes back to missing."""
    _editable(filing)
    now = tz.now_iso()
    conn.execute("UPDATE travel_item SET drive_url=NULL, drive_file_id=NULL, drive_source=NULL, state='missing', "
                 "updated_at=? WHERE filing_id=? AND item_code=? AND drive_source='upload'", (now, filing["id"], code))
    conn.execute("DELETE FROM travel_reading WHERE filing_id=? AND item_code=?", (filing["id"], code))
    _touch_open(conn, filing, now)
    _stamp(conn, filing["id"], now)
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
    if filing["gen_state"] == "running":
        raise TravelError("The documents are still being made. Try again in a minute.")
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
