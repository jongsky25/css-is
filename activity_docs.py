"""Documents an office activity needs (Spot Feedback #136): a DPO and an invitation.

The app suggests which documents an activity needs from facts it already holds (people travelling, who it is
open to, its kind); the person can overrule each suggestion. A needed document can then be drafted as a Google
Doc from the entry's details through the same signed relay the travel forms use. Only the choice and the link
to the draft are stored; the content of a draft is built when it is asked for and dropped.

`suggest`, `describe_people` and `payload` are pure; the rest touch the database or the relay."""
from __future__ import annotations
from typing import Optional

import gdocs_relay
import storage as st
import travel_docs as td
import tzutil as tz

DOCS = {
    "dpo": {"label": "Department Personnel Order (DPO)",
            "blurb": "Authorises the personnel to attend or travel for the activity."},
    "invitation": {"label": "Invitation (memorandum)",
                   "blurb": "A memorandum asking the recipient's office for its help, with what, when and where."},
    "concept_note": {"label": "Concept note",
                     "blurb": "Explains why the activity is held, who takes part and what it costs, with the program of activities."},
    "program_flow": {"label": "Program flow",
                     "blurb": "The day-by-day schedule: when, what, and who is responsible."},
}
KEYS = tuple(DOCS)
INVITE_KINDS = ("training",)           # a training or workshop is announced to the people it is for
BLANK = "__________"
# The usual asks in a memorandum to a regional office (Area, Requested assistance). Starting wording only.
ASSISTANCE = (
    ("Participants", "Identify and designate the personnel who will participate in the activity."),
    ("Venue", "Provide a suitable venue, preferably with stable internet connectivity."),
    ("Meals", "Provide meals for the participants during the activity."),
    ("Coordination", "Facilitate the coordination and attendance of the identified participants."),
)                  # left for the person to fill in by hand on the draft


def suggest(entry, kind_label="") -> dict:
    """{key: (needed, reason)} from what the entry already says. A suggestion only: the person decides."""
    travelling = [p for p in entry.get("people") or [] if p.get("role") == "travel"]
    out = {}
    if travelling:
        n = len(travelling)
        out["dpo"] = (True, f"{n} {'person is' if n == 1 else 'people are'} travelling for this activity.")
    elif entry.get("kind") == "travel":
        out["dpo"] = (True, "It is a trip or field work.")
    else:
        out["dpo"] = (False, "Nobody is marked as travelling.")
    if entry.get("audience") == "bureau":
        out["invitation"] = (True, "It is open to everyone in the bureau.")
    elif entry.get("kind") in INVITE_KINDS:
        out["invitation"] = (True, f"A {(kind_label or entry.get('kind') or 'training').lower()} is usually announced with an invitation.")
    else:
        out["invitation"] = (False, "It is for the people you listed or your own unit.")
    multi_day = bool(entry.get("end_date")) and entry["end_date"] != entry.get("start_date")
    if entry.get("kind") in INVITE_KINDS:
        out["concept_note"] = (True, f"A {(kind_label or 'training').lower()} is usually prepared with a concept note.")
    elif travelling or multi_day:
        out["concept_note"] = (True, "An activity with travel or lasting several days usually needs a concept note.")
    else:
        out["concept_note"] = (False, "A short internal item rarely needs one.")
    if multi_day or entry.get("kind") in INVITE_KINDS:
        out["program_flow"] = (True, "A training or an activity lasting several days needs a program.")
    else:
        out["program_flow"] = (False, "A single short item rarely needs a program.")
    return out


def get_rows(conn, entry_id) -> dict:
    cur = conn.execute("SELECT doc_key, needed, doc_url, doc_state, note, rev FROM calendar_entry_doc WHERE entry_id=?",
                       (entry_id,))
    return {r[0]: {"needed": r[1], "doc_url": r[2] or "", "doc_state": r[3] or "", "note": r[4] or "", "rev": r[5] or 0}
            for r in cur.fetchall()}


def state_for(conn, entry, kind_label="") -> list:
    """One dict per document: the suggestion, the person's choice, the effective answer and the draft so far."""
    sug, rows, out = suggest(entry, kind_label), get_rows(conn, entry["id"]), []
    for key in KEYS:
        row = rows.get(key, {"needed": None, "doc_url": "", "doc_state": "", "note": "", "rev": 0})
        suggested, reason = sug[key]
        needed = suggested if row["needed"] is None else bool(row["needed"])
        out.append({"key": key, **DOCS[key], "suggested": suggested, "reason": reason, "choice": row["needed"],
                    "needed": needed, "doc_url": row["doc_url"], "doc_state": row["doc_state"], "note": row["note"],
                    "rev": row["rev"]})
    return out


def set_needed(conn, entry_id, key, value: Optional[bool], by) -> None:
    """value: True (needed), False (not needed) or None (follow the suggestion again)."""
    if key not in DOCS:
        raise ValueError("Unknown document.")
    v = None if value is None else int(bool(value))
    conn.execute("INSERT INTO calendar_entry_doc(entry_id, doc_key, needed, updated_by, updated_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(entry_id, doc_key) DO UPDATE SET needed=excluded.needed, updated_by=excluded.updated_by, "
                 "updated_at=excluded.updated_at", (entry_id, key, v, by, tz.now_iso()))
    conn.commit()


def when_text(entry) -> str:
    """The entry's date and time as one line for a document."""
    a, b = entry["start_date"], entry.get("end_date") or entry["start_date"]
    days = td.date_range(a, b) if b != a else td.long_date(a)
    if entry.get("start_time"):
        t = entry["start_time"] + (f" to {entry['end_time']}" if entry.get("end_time") else "")
        return f"{days}, {t}"
    return f"{days}, {entry['time_note']}" if entry.get("time_note") else days


def days_text(entry) -> str:
    """Just the dates, for an order that does not carry the time of day."""
    a, b = entry["start_date"], entry.get("end_date") or entry["start_date"]
    return td.date_range(a, b)


def where_text(entry) -> str:
    mod = {"f2f": "face to face", "online": "online", "hybrid": "hybrid"}.get(entry.get("modality") or "", "")
    venue = (entry.get("venue") or "").strip()
    if venue and mod and entry.get("modality") != "f2f":
        return f"{venue} ({mod})"
    return venue or (mod.capitalize() if mod else "To be announced")


def describe_people(conn, entry, role=None, positions=True) -> list:
    """[(name, designation)] for the people on the entry, optionally only one role, in the order they were added.
    With positions=False the designation is left empty: a position is only written when the person asked for it."""
    out = []
    for p in entry.get("people") or []:
        if role and p.get("role") != role:
            continue
        prof = st.get_user_profile(conn, p["user_id"]) or {}
        name = prof.get("person_name") or prof.get("username") or ""
        if name:
            out.append((name, (prof.get("designation") or "") if positions else ""))
    return out


def _line(i, name, desig):
    return f"{i}. {name}" + (f", {desig}" if desig else "")


def payload(conn, entry, key, user, owner_label="", positions=False) -> td.DocPayload:
    """The relay request for one document. Placeholders left for the person to complete are filled with a blank line,
    so the draft never carries a guess for a number, a source of funds or a signature. Positions (designations) from
    saved profiles are written only when `positions` is True (spot feedback #154: ask first, do not fill them on their own)."""
    profile = st.get_user_profile(conn, user["id"]) or {}
    me = profile.get("person_name") or user.get("username") or ""
    title = entry["title"]
    head_name = st.get_setting(conn, "travel.sig.head_name", "")
    head_title = st.get_setting(conn, "travel.sig.head_title", "")
    if key == "dpo":
        people = (describe_people(conn, entry, "travel", positions) or describe_people(conn, entry, None, positions)
                  or [(me, (profile.get("designation") or "") if positions else "")])
        days = days_text(entry)
        place = (entry.get("venue") or "").strip()
        in_place = f" in {place}" if place else ""
        unit = owner_label.strip()
        who = f"Select {unit} Personnel" if unit else "Select Personnel"
        fields = {"dpo_year": str(td._d(entry["start_date"]).year), "dpo_no": BLANK, "dpo_date": BLANK,
                  "subject": f"Authority for {who} to Participate in {title}, {days}{in_place}",
                  "background": (f"The {unit} will conduct {title} on {days}{in_place}." if unit
                                 else f"{title} will be held on {days}{in_place}."),
                  "intro": f"Authority is hereby given to the following select {unit + ' ' if unit else ''}personnel to participate in "
                           f"{title} on {days}{in_place}:",
                  "title": title, "purpose": f"attend {title}", "dates": days, "venue": where_text(entry),
                  "funding_source": BLANK, "unit_name": unit, "head_name": head_name.upper(), "head_title": head_title,
                  "prepared_by": me}
        # The personnel go in as a table (Name | Position) and, for a template that still has a {{personnel}} line, as
        # numbered lines too. Whichever the template carries is filled; the other is skipped.
        rows = {"personnel": {"marker": "p_name", "data": [{"p_name": f"{i}. {n}", "p_position": d} for i, (n, d) in enumerate(people, 1)]}}
        blocks = {"personnel": [_line(i, n, d) for i, (n, d) in enumerate(people, 1)]}
        return td.DocPayload("dpo", "dpo", f"DPO - {title}"[:120], fields, blocks=blocks, rows=rows)
    if key == "invitation":
        if entry.get("audience") == "bureau":
            invited = "All personnel of the bureau"
        elif owner_label:
            invited = f"All personnel of {owner_label}" if entry.get("audience") == "unit" else f"Selected personnel of {owner_label}"
        else:
            invited = "Selected personnel"
        link = (entry.get("meeting_url") or "").strip()
        lines = [f"What: {title}", f"When: {when_text(entry)}", f"Where: {where_text(entry)}"]
        if link:
            lines.append(f"Join online: {link}")
        days = days_text(entry)
        place = (entry.get("venue") or "").strip()
        in_place = f" in {place}" if place else ""
        unit = owner_label.strip()
        fields = {"date": td.long_date(tz.today_local()), "title": title, "invited": invited,
                  "sender_name": me, "sender_title": (profile.get("designation") or "") if positions else "",
                  "contact": user.get("username") or "", "head_name": head_name, "head_title": head_title,
                  # the DOH memorandum to the regions: FOR / FROM / SUBJECT, the request, the contact line
                  "for_name": BLANK, "for_title": BLANK, "for_office": BLANK,
                  "from_name": head_name.upper(), "from_title": head_title, "unit_name": unit,
                  "subject": f"Request for Assistance in the Conduct of {title}",
                  "opening": (f"The {unit} respectfully requests" if unit else "We respectfully request")
                             + f" your office\u2019s assistance in the conduct of {title} on {days}{in_place}.",
                  "contact_name": me, "contact_email": user.get("username") or "", "contact_phone": BLANK}
        # what the request asks of the office: one row each, the person edits the wording
        rows = {"assistance": {"marker": "a_area", "data": [{"a_area": a, "a_request": r} for a, r in ASSISTANCE]}}
        return td.DocPayload("invitation", "invitation", f"Memorandum - {title}"[:120], fields,
                             blocks={"details": lines}, rows=rows)
    if key == "concept_note":
        return _concept_note(conn, entry, title, me, profile, head_name, head_title, owner_label.strip(), positions)
    if key == "program_flow":
        return _program_flow(entry, title)
    raise ValueError("Unknown document.")


# Prompts the person replaces. Square brackets mark text that is theirs to write: the app only knows dates, places and people.
CONCEPT_PROMPTS = {
    "background": ["[Why this activity is held: the mandate or policy it supports, what has been done so far, and the need it answers.]"],
    "objectives": ["The activity aims to [state the general objective].", "Specifically, it seeks to:",
                   "1. [first specific objective]", "2. [second specific objective]"],
    "outputs": ["The activity is expected to produce the following:", "- [first expected output]", "- [second expected output]"],
    "methodology": ["[How the activity will be conducted: the approach, the sessions and how participants take part.]"],
}


def _day_label(i, d) -> str:
    return f"Day {i} \u2013 {td.long_date(d)}"


def _concept_note(conn, entry, title, me, profile, head_name, head_title, unit, positions=False) -> td.DocPayload:
    days = td.trip_days(entry["start_date"], entry.get("end_date") or entry["start_date"])
    people = describe_people(conn, entry, None, positions)
    participants = [_line(i, n, d) for i, (n, d) in enumerate(people, 1)] or ["[List who takes part, by group, and how many.]"]
    fields = {"title": title, "unit_name": unit, "date_duration": days_text(entry),
              "venue": (entry.get("venue") or "").strip() or "To be determined",
              "participant_count": str(len(people)) if people else BLANK,
              "facilitators": unit or BLANK, "budget": BLANK,
              "prepared_by": me, "prepared_title": (profile.get("designation") or "") if positions else "",
              "noted_by_name": BLANK, "noted_by_title": BLANK,
              "recommended_name": head_name.upper(), "recommended_title": head_title}
    blocks = {**CONCEPT_PROMPTS, "participants": participants}
    rows = {"program": {"marker": "pd_day", "data": [{"pd_day": _day_label(i, d), "pd_am": "", "pd_pm": ""}
                                                     for i, d in enumerate(days, 1)]}}
    return td.DocPayload("concept_note", "concept_note", f"Concept Note - {title}"[:120], fields, blocks=blocks, rows=rows)


def _program_flow(entry, title) -> td.DocPayload:
    """A heading row for each day and two empty rows under it: the schedule itself is the person's to write."""
    days = td.trip_days(entry["start_date"], entry.get("end_date") or entry["start_date"])
    data = []
    for i, d in enumerate(days, 1):
        data.append({"pf_time": _day_label(i, d), "pf_topic": "", "pf_person": ""})
        data += [{"pf_time": "", "pf_topic": "", "pf_person": ""} for _ in range(2)]
    return td.DocPayload("program_flow", "program_flow", f"Program Flow - {title}"[:120], {"title": title},
                         rows={"flow": {"marker": "pf_time", "data": data}})


PLAIN_ERRORS = {
    "template_not_set": "The template for this document has not been set up in Google Docs yet. Ask an administrator to run makeActivityTemplates in the relay script.",
    "not_configured": "Drafting in Google Docs is not switched on yet.",
    "unreachable": "The document service could not be reached just now. Try again in a minute.",
}
GENERIC_ERROR = "The document service refused this request. This is a setup problem, not something wrong with the activity. Try again, and if it fails again tell an administrator."


class Prepared:
    """A drafted request ready to send. `call()` touches no database, so it can run on a worker thread while the
    connection stays with the thread that opened it."""

    def __init__(self, entry_id, key, rev, call):
        self.entry_id, self.key, self.rev, self.call = entry_id, key, rev, call


def prepare(conn, entry, key, user, owner_label="", relay=None, positions=False) -> Prepared:
    """Build the relay request for a new revision of one document (reads the database)."""
    pl = payload(conn, entry, key, user, owner_label, positions)
    rev = int((get_rows(conn, entry["id"]).get(key) or {"rev": 0})["rev"]) + 1
    relay = relay or gdocs_relay.get_relay()
    share = [user["username"]] if user.get("username") else []
    return Prepared(entry["id"], key, rev, lambda: relay.generate_doc(
        request_id=f"act{entry['id']}:{key}:{rev}", template_key=pl.template_key, folder_key=f"act-{entry['id']}",
        title=pl.title, fields=pl.fields, blocks=pl.blocks, rows=pl.rows, share_with=share))


def record(conn, prep, res, user) -> dict:
    """Store the link (or why it failed) and return {"ok": bool, "url": str, "error": str}. A new draft is a new
    revision, so it never overwrites the earlier one, and a failure keeps the last good link."""
    url = (res.data or {}).get("url") if res.ok else ""
    err = "" if url else PLAIN_ERRORS.get(res.error, GENERIC_ERROR)
    conn.execute("INSERT INTO calendar_entry_doc(entry_id, doc_key, doc_url, doc_state, note, rev, updated_by, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(entry_id, doc_key) DO UPDATE SET doc_url=CASE WHEN excluded.doc_url<>'' "
                 "THEN excluded.doc_url ELSE calendar_entry_doc.doc_url END, doc_state=excluded.doc_state, note=excluded.note, "
                 "rev=excluded.rev, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                 (prep.entry_id, prep.key, url or "", "done" if url else "failed", err, prep.rev, user.get("username"), tz.now_iso()))
    conn.commit()
    return {"ok": bool(url), "url": url or "", "error": err}


def draft(conn, entry, key, user, owner_label="", relay=None, positions=False) -> dict:
    """Prepare, send and record in one step (for callers that are not on an event loop)."""
    prep = prepare(conn, entry, key, user, owner_label, relay, positions)
    return record(conn, prep, prep.call(), user)
