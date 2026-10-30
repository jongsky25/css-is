"""Documents an office activity needs (Spot Feedback #136): a DPO and an invitation.

The app suggests which documents an activity needs from facts it already holds (people travelling, who it is
open to, its kind); the person can overrule each suggestion. A needed document can then be drafted as a Google
Doc from the entry's details through the same signed relay the travel forms use. Only the choice and the link
to the draft are stored; the content of a draft is built when it is asked for and dropped.

`suggest`, `describe_people` and `payload` are pure; the rest touch the database or the relay."""
from __future__ import annotations
import logging
import re
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
    "invitation_external": {"label": "Invitation (external letter)",
                            "blurb": "A letter inviting a named outside office or partner to the activity."},
    "concept_note": {"label": "Concept note",
                     "blurb": "Explains why the activity is held, who takes part and what it costs, with the program of activities."},
    "program_flow": {"label": "Program flow",
                     "blurb": "The day-by-day schedule: when, what, and who is responsible."},
    "notice_of_meeting": {"label": "Notice of meeting",
                          "blurb": "Tells the invited people what the meeting is, when and where it is held, and who is invited."},
    "executive_briefer": {"label": "Executive briefer",
                          "blurb": "A short brief of the activity, requested action and key details for the approving official."},
    "minutes": {"label": "Minutes of the meeting",
                "blurb": "The record of a meeting: who attended, what was discussed and decided, and the action points."},
}
KEYS = tuple(DOCS)
INVITE_KINDS = ("training",)           # a training or workshop is announced to the people it is for
BLANK = "__________"
SIGNATORY_UNIT = "Bureau of Local Health Systems Development"   # the signatory block of every DPO (spot feedback #160)
BUREAU = "the Bureau of Local Health Systems Development (BLHSD)"
# Cited as the DPO's source of funds (spot feedback #179); the template adds " funds." after it.
DPO_FUNDING = "BLHSD - Local Health Systems Development Assistance"
# The usual asks in a memorandum to a regional office (Area, Requested assistance). Starting wording only.
ASSISTANCE = (
    ("Participants", "Identify and designate the personnel who will participate in the activity."),
    ("Venue", "Provide a suitable venue, preferably with stable internet connectivity."),
    ("Meals", "Provide meals for the participants during the activity."),
    ("Coordination", "Facilitate the coordination and attendance of the identified participants."),
)                  # left for the person to fill in by hand on the draft

# Who reviews a DPO's file copy (spot feedback #186): the section of the traveller decides. Names are the office's own.
REVIEWERS = (
    (("S4", "S5"), "MARIA LOURDES GAJITOS, MD, MPH", "Medical Officer V"),
    (("S1", "S2", "S3"), "KATHRINE JOYCE FLORES, MD, MPM", "Medical Officer V"),
)
VISITORS_MAX = 1000


def get_visitors(conn, entry_id) -> str:
    """Who is expected from other offices (spot feedback #188), or ''."""
    r = conn.execute("SELECT text FROM calendar_entry_visitors WHERE entry_id=?", (entry_id,)).fetchone()
    return (r[0] or "") if r else ""


def clean_visitors(text) -> str:
    """The person's list with each line trimmed and blank lines dropped, so it reads as a list in a document."""
    lines = [" ".join(l.split()) for l in str(text or "").replace("\r", "").split("\n")]
    return "\n".join(l for l in lines if l)[:VISITORS_MAX]


def set_visitors(conn, entry_id, text, by, *, commit=True) -> None:
    """Keep the expected participants from other offices (one per line; empty clears it)."""
    text = clean_visitors(text)
    if not text:
        conn.execute("DELETE FROM calendar_entry_visitors WHERE entry_id=?", (entry_id,))
    else:
        conn.execute("INSERT INTO calendar_entry_visitors(entry_id, text, updated_by, updated_at) VALUES (?,?,?,?) "
                     "ON CONFLICT(entry_id) DO UPDATE SET text=excluded.text, updated_by=excluded.updated_by, "
                     "updated_at=excluded.updated_at", (entry_id, text, by, tz.now_iso()))
    if commit:
        conn.commit()


_VENUE_LABEL = re.compile(r"\bvenue\s*(?:is|will be|:|-|\u2013)\s*(?:at\s+)?([^\n.;]+)", re.I)
_NAME = r"[A-Z][\w&'\u2019\-]*(?:\.[\w&'\u2019\-]+)*"
_VENUE_AT = re.compile(r"\bat\s+((?:the\s+)?" + _NAME + r"(?:\s+(?:of|de|del|and|&|" + _NAME + r"))*"
                       r"(?:,\s*" + _NAME + r"(?:\s+" + _NAME + r"){0,3}){0,2})")


def venue_from_text(*texts) -> str:
    """The venue an invitation names (spot feedback #184), or ''. Looks for "Venue: X" first, then "at the X" where X is a
    capitalised name such as a hotel. A suggestion read from words the person pasted: it is never kept on the item."""
    for text in texts:
        text = " ".join(str(text or "").split())
        m = _VENUE_LABEL.search(text) or _VENUE_AT.search(text)
        if m:
            venue = m.group(1).strip(" ,;:-")
            venue = venue[4:] if venue.lower().startswith("the ") else venue
            if len(venue) >= 4:
                return venue[:120]
    return ""


# Keywords and the laws usually cited with them, read from the invitation for the DPO's file copy (spot feedback #185).
_KEYWORDS = (
    (r"barangay health workers?|\bBHWs?\b", "Barangay Health Workers (BHWs)", "RA 7883"),
    (r"universal health care|\bUHC\b", "Universal Health Care (UHC)", "RA 11223"),
    (r"rural health units?|\bRHUs?\b", "Rural Health Units (RHUs)", ""),
    (r"local health systems?|\bLHS\b", "Local Health Systems", ""),
    (r"health promotion", "Health Promotion", ""),
    (r"province-?wide health systems?|\bPWHS\b", "Province-wide Health Systems", ""),
)
_ISSUANCE = re.compile(r"\b(?:(R\.?A\.?|Republic Act)|(A\.?O\.?|Administrative Order)|(D\.?O\.?|Department Order)|"
                       r"(D\.?M\.?|Department Memorandum)|(E\.?O\.?|Executive Order))\s*(?:No\.?\s*)?(\d[\d\-]*\d|\d)", re.I)
_ISSUANCE_NAME = ("RA", "AO", "DO", "DM", "EO")


def suggest_file_copy(*texts) -> tuple:
    """(keywords, issuances) as two one-line strings read from the invitation's words (spot feedback #185). Only what the
    words say or a law the keyword is known by; both may be ''. The person edits them on the draft."""
    text = " ".join(" ".join(str(t or "").split()) for t in texts)
    words, laws = [], []
    for pattern, label, law in _KEYWORDS:
        if re.search(pattern, text, re.I):
            words.append(label)
            if law:
                laws.append(law)
    for m in _ISSUANCE.finditer(text):
        i = next(n for n in range(1, 6) if m.group(n))
        laws.insert(0, f"{_ISSUANCE_NAME[i - 1]} {m.group(6)}")
    seen, uniq = set(), []
    for l in laws:
        if l not in seen:
            seen.add(l)
            uniq.append(l)
    return ", ".join(words), ", ".join(uniq)


def file_copy_reviewer(conn, entry, people_ids) -> tuple:
    """(name, title) the DPO's file copy goes to (spot feedback #186), from the section of the travellers: S4 and S5 to one
    reviewer, S1 to S3 to the other. ('', '') when a traveller has no section or they belong to different reviewers."""
    found = set()
    for uid in people_ids:
        path = (st.get_user_profile(conn, uid) or {}).get("org_path") or ""
        section = path.split("/")[-1].strip().upper()
        match = next((r for r in REVIEWERS if section in r[0]), None)
        if not match:
            return "", ""
        found.add(match[1:])
    return next(iter(found)) if len(found) == 1 else ("", "")


def suggest(entry, kind_label="", outside=None, visitors="") -> dict:
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
    host = ((outside or {}).get("host") or "").strip()
    has_visitors = any(line.strip() and line.strip().lower() != "none" for line in str(visitors or "").splitlines())
    out["invitation_external"] = (
        bool(host or has_visitors),
        "An outside office or visitor is listed; use a letter if inviting them." if host or has_visitors
        else "No outside office or visitor is listed."
    )
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
    if entry.get("kind") == "meeting":
        out["notice_of_meeting"] = (True, "A meeting is usually announced with a notice.")
        out["minutes"] = (True, "A meeting is usually followed by minutes.")
    else:
        out["notice_of_meeting"] = (False, "Only a meeting usually needs a notice.")
        out["minutes"] = (False, "Only a meeting usually needs minutes.")
    out["executive_briefer"] = (False, "Choose a briefer when an executive summary or decision is needed.")
    return out


def get_rows(conn, entry_id) -> dict:
    cur = conn.execute("SELECT doc_key, needed, doc_url, doc_state, note, rev FROM calendar_entry_doc WHERE entry_id=?",
                       (entry_id,))
    return {r[0]: {"needed": r[1], "doc_url": r[2] or "", "doc_state": r[3] or "", "note": r[4] or "", "rev": r[5] or 0}
            for r in cur.fetchall()}


INVITED_AS = {"resource_person": "as resource person", "attendee": "as participant"}
HOST_MAX, INVITATION_MAX = 160, 600


def get_outside(conn, entry_id) -> Optional[dict]:
    """The outside-activity details, or None when BLHSD conducts the activity."""
    r = conn.execute("SELECT host, invited_as, invitation, invitation_url, invitation_name FROM calendar_entry_outside "
                     "WHERE entry_id=?", (entry_id,)).fetchone()
    return {"host": r[0] or "", "invited_as": r[1] or "attendee", "invitation": r[2] or "",
            "file_url": r[3] or "", "file_name": r[4] or ""} if r else None


def set_outside(conn, entry_id, host, invited_as, invitation, by) -> None:
    """Mark the activity as run by another office. The invitation text is the person's own paste, kept on one line."""
    host = " ".join(str(host or "").split())[:HOST_MAX]
    if not host:
        raise ValueError("Say which office is holding the activity.")
    if invited_as not in INVITED_AS:
        raise ValueError("Choose how you were invited.")
    invitation = " ".join(str(invitation or "").split())[:INVITATION_MAX]
    conn.execute("INSERT INTO calendar_entry_outside(entry_id, host, invited_as, invitation, updated_by, updated_at) "
                 "VALUES (?,?,?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET host=excluded.host, invited_as=excluded.invited_as, "
                 "invitation=excluded.invitation, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                 (entry_id, host, invited_as, invitation, by, tz.now_iso()))
    conn.commit()


def set_invitation_file(conn, entry_id, url, name, by, *, commit=True) -> None:
    """Keep the link to the uploaded letter (or clear it with an empty url). Needs the activity marked as another office's."""
    url = str(url or "").strip()
    if url and not url.startswith("https://"):
        raise ValueError("That is not a link the app can keep.")
    cur = conn.execute("UPDATE calendar_entry_outside SET invitation_url=?, invitation_name=?, updated_by=?, updated_at=? "
                       "WHERE entry_id=?", (url, (str(name or "").strip()[:100] if url else ""), by, tz.now_iso(), entry_id))
    if cur.rowcount == 0:
        raise ValueError("Choose \u201cAnother office\u201d and save it first, then add the letter.")
    if commit:
        conn.commit()


CITES_MAX = 1000


def get_dpo_cites(conn, entry_id) -> str:
    """What the person typed under "DPO cites" for this activity, or ''."""
    r = conn.execute("SELECT text FROM calendar_entry_dpo_cites WHERE entry_id=?", (entry_id,)).fetchone()
    return (r[0] or "") if r else ""


def set_dpo_cites(conn, entry_id, text, by) -> None:
    """Keep what the DPO cites as the reason for the activity (one line; empty clears it)."""
    text = " ".join(str(text or "").split())[:CITES_MAX]
    if not text:
        conn.execute("DELETE FROM calendar_entry_dpo_cites WHERE entry_id=?", (entry_id,))
    else:
        conn.execute("INSERT INTO calendar_entry_dpo_cites(entry_id, text, updated_by, updated_at) VALUES (?,?,?,?) "
                     "ON CONFLICT(entry_id) DO UPDATE SET text=excluded.text, updated_by=excluded.updated_by, "
                     "updated_at=excluded.updated_at", (entry_id, text, by, tz.now_iso()))
    conn.commit()


def clear_outside(conn, entry_id) -> None:
    conn.execute("DELETE FROM calendar_entry_outside WHERE entry_id=?", (entry_id,))
    conn.commit()


def state_for(conn, entry, kind_label="") -> list:
    """One dict per document: the suggestion, the person's choice, the effective answer and the draft so far."""
    sug = suggest(entry, kind_label, get_outside(conn, entry["id"]), get_visitors(conn, entry["id"]))
    rows, out = get_rows(conn, entry["id"]), []
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


def describe_people(conn, entry, role=None, positions=True, designations=None) -> list:
    """[(name, designation)] for the people on the entry, optionally only one role, in the order they were added.
    With positions=False the designation is left empty: a position is only written when the person asked for it.
    `designations` ({user_id: text}) holds designations typed on the draft form (spot feedback #178); a typed one wins."""
    out = []
    for p in entry.get("people") or []:
        if role and p.get("role") != role:
            continue
        prof = st.get_user_profile(conn, p["user_id"]) or {}
        name = prof.get("person_name") or prof.get("username") or ""
        if name:
            typed = ((designations or {}).get(p["user_id"]) or "").strip()
            out.append((name, typed or ((prof.get("designation") or "") if positions else "")))
    return out


def dpo_travellers(conn, entry) -> list:
    """[{user_id, name}] of the people a DPO will name (the travellers, else everyone on the item), for the designation fields."""
    out = []
    for role in ("travel", None):
        for p in entry.get("people") or []:
            if role and p.get("role") != role:
                continue
            prof = st.get_user_profile(conn, p["user_id"]) or {}
            name = prof.get("person_name") or prof.get("username") or ""
            if name:
                out.append({"user_id": p["user_id"], "name": name})
        if out:
            break
    return out


def _line(i, name, desig):
    return f"{i}. {name}" + (f", {desig}" if desig else "")


def _names(text, host) -> bool:
    """Whether `text` already names `host`, ignoring case, spacing and a leading "the"."""
    squash = lambda v: " ".join(str(v).lower().split())
    h = squash(host)
    h = h[4:] if h.startswith("the ") else h
    return bool(h) and h in squash(text)


def head_of_office(conn) -> tuple:
    """(name, title) of the signatory. The names set under Travel filing settings win (an acting head or OIC); with no name
    there, the Director in the directory, the same rule the travel forms follow (spot feedback #157)."""
    name = st.get_setting(conn, "travel.sig.head_name", "")
    title = st.get_setting(conn, "travel.sig.head_title", "")
    if not (name or "").strip():
        director = st.org_seat_holder(conn, 3)
        if director:
            name, title = director[0], director[1] or "Director"
    return name, title


def payload(conn, entry, key, user, owner_label="", positions=False, designations=None) -> td.DocPayload:
    """The relay request for one document. Placeholders left for the person to complete are filled with a blank line,
    so the draft never carries a guess for a number, a source of funds or a signature. Positions (designations) from
    saved profiles are written only when `positions` is True (spot feedback #154: ask first, do not fill them on their own)."""
    profile = st.get_user_profile(conn, user["id"]) or {}
    me = profile.get("person_name") or user.get("username") or ""
    title = entry["title"]
    head_name, head_title = head_of_office(conn)
    if key == "dpo":
        people = (describe_people(conn, entry, "travel", positions, designations)
                  or describe_people(conn, entry, None, positions, designations)
                  or [(me, ((designations or {}).get(user["id"]) or "").strip()
                       or ((profile.get("designation") or "") if positions else ""))])
        days = days_text(entry)
        # Spot feedback #178: the venue is always in the subject and the body; with none on the item it is a blank to fill.
        outside = get_outside(conn, entry["id"])
        # Spot feedback #184/#187: with no venue on the item, the venue the invitation names is used before a blank.
        place = (entry.get("venue") or "").strip() or venue_from_text(
            (outside or {}).get("invitation"), get_dpo_cites(conn, entry["id"])) or BLANK
        in_place = f" in {place}"
        unit = owner_label.strip()
        the_title = title if title.lower().startswith("the ") else f"the {title}"
        place_part = f", in {place}"
        # The wording follows the office's sample DPO (spot feedback #170): the first paragraph gives the rationale taken from
        # the invitation's key lines, if there are any, then says who conducts the activity, when and where; the subject names
        # the select bureau personnel and what they are authorised to do.
        if outside and outside["host"]:
            host = outside["host"]
            conductor = host if host.lower().startswith("the ") else f"the {host}"
        else:
            conductor = f"the DOH, through {BUREAU},"
        sentence = f"{conductor} will conduct {the_title} on {days}{place_part}."
        # What the person typed under "DPO cites" comes first; for another office's activity the invitation's key lines
        # stand in when that is empty. Nothing is invented when both are.
        rationale = get_dpo_cites(conn, entry["id"]).strip() or (outside or {}).get("invitation", "").strip()
        if rationale:
            background = rationale if rationale[-1] in ".!?" else rationale + "."
            # The invitation's own lines may already say who holds the activity; do not say it again.
            if not (outside and outside["host"] and _names(rationale, outside["host"])):
                background += " In support of this, " + sentence
        else:
            background = sentence[0].upper() + sentence[1:]
        if outside and outside["invited_as"] == "resource_person":
            role, subject_role = "to serve as resource person in", "Serve as Resource Person in"
        elif outside:
            role, subject_role = "to participate in", "Participate in"
        else:
            role, subject_role = "to conduct", "Conduct"
        intro = f"Authority is hereby given to the following select BLHSD personnel {role} {the_title} on {days}{place_part}:"
        subject = (f"Authority for Select {BUREAU.removeprefix('the ')} Personnel to {subject_role} {the_title} "
                   f"on {days}{place_part}")
        single = len(people) == 1
        if single:
            # One person (spot feedback #157): the subject and the body name them, with no list and no table.
            name, desig = people[0]
            role = "Resource Speaker" if outside and outside["invited_as"] == "resource_person" else "Participant"
            who_one = f"{name}, {desig or BLANK} of {BUREAU}"
            subject = f"Authority for {who_one} to Attend as {role} in the {title}{in_place} on {days}"
            intro = f"Authority is hereby given to {who_one} to attend as {role} in the {title}{in_place} on {days}."
        fields = {"dpo_year": str(td._d(entry["start_date"]).year), "dpo_no": BLANK, "dpo_date": BLANK,
                  "subject": subject,
                  "background": background, "intro": intro,
                  "title": title, "purpose": f"attend {title}", "dates": days, "venue": where_text(entry),
                  "funding_source": DPO_FUNDING, "unit_name": SIGNATORY_UNIT, "head_name": head_name.upper(), "head_title": head_title,
                  "prepared_by": me}
        if place != BLANK and not (entry.get("venue") or "").strip():
            fields["venue"] = place                      # the venue read from the invitation
        # The personnel go in as a table (Name | Position) and, for a template that still has a {{personnel}} line, as
        # numbered lines too. Whichever the template carries is filled; the other is skipped.
        rows = {"personnel": {"marker": "p_name", "fit": True,           # fit: widths follow the text (spot feedback #181)
                              "data": [{"p_name": f"{i}. {n}", "p_position": d} for i, (n, d) in enumerate(people, 1)]}}
        blocks = {"personnel": [_line(i, n, d) for i, (n, d) in enumerate(people, 1)]}
        if single:
            # "remove" asks the relay to drop the whole Name | Position table; a relay without it leaves one blank row.
            rows["personnel"] = {"marker": "p_name", "data": [{"p_name": "", "p_position": ""}], "remove": True}
            blocks = {"personnel": [""]}
        # Spot feedback #158: after the order, a second page without the letterhead, with the routing tables.
        # The file copy's tables come pre-filled where the app can tell (spot feedback #185/#186): who reviews it, from the
        # travellers' section, and keywords and issuances read from the invitation. Empty ones are left out of the request.
        ids = [t["user_id"] for t in dpo_travellers(conn, entry)] or [user["id"]]
        reviewer = file_copy_reviewer(conn, entry, ids)
        keywords, issuances = suggest_file_copy((outside or {}).get("invitation"), get_dpo_cites(conn, entry["id"]))
        extras = {"file_copy": True}
        if reviewer[0]:
            extras["reviewer"] = {"name": reviewer[0], "title": reviewer[1]}
        if keywords:
            extras["keywords"] = keywords
        if issuances:
            extras["issuances"] = issuances
        return td.DocPayload("dpo", "dpo", f"DPO - {title}"[:120], fields, blocks=blocks, rows=rows, extras=extras)
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
        # The office memo uses prose and bullets. Keep legacy table data for an old-template rollback.
        rows = {"assistance": {"marker": "a_area", "data": [{"a_area": a, "a_request": r} for a, r in ASSISTANCE]}}
        blocks = {
            "reiteration": [fields["opening"]],
            "rationale": ["[Rationale of invitation: explain why the office's participation is requested.]"],
            "details": lines,
            "representatives": [f"{area}: {request}" for area, request in ASSISTANCE],
            "contact_details": [f"For coordination, please contact {me} at {user.get('username') or BLANK}; telephone {BLANK}."],
        }
        reviewer = file_copy_reviewer(conn, entry, [user["id"]])
        extras = {"file_copy": True, "boxes": ["slip"],
                  "addressees": [{"for_name": BLANK, "for_title": BLANK, "for_office": BLANK}]}
        if reviewer[0]:
            extras["reviewer"] = {"name": reviewer[0], "title": reviewer[1]}
        # FROM belongs to the head's bureau, not the drafter's section.
        fields["unit_name"] = SIGNATORY_UNIT
        return td.DocPayload("invitation", "invitation", f"Memorandum - {title}"[:120], fields,
                             blocks=blocks, rows=rows, extras=extras)
    if key == "invitation_external":
        return _invitation_external(conn, entry, title, me, head_name, head_title, user["id"])
    if key == "concept_note":
        return _concept_note(conn, entry, title, me, profile, head_name, head_title, owner_label.strip(), positions)
    if key == "program_flow":
        return _program_flow(entry, title)
    if key == "notice_of_meeting":
        return _notice_of_meeting(conn, entry, title, me, profile, head_name, head_title, owner_label.strip(), positions)
    if key == "executive_briefer":
        return _executive_briefer(conn, entry, title, me, profile, head_name, head_title, user["id"], positions)
    if key == "minutes":
        return _minutes(conn, entry, title, me, profile, head_name, owner_label.strip(), positions)
    raise ValueError("Unknown document.")


def _executive_briefer(conn, entry, title, me, profile, head_name, head_title, drafter_id, positions=False) -> td.DocPayload:
    reviewer = file_copy_reviewer(conn, entry, [drafter_id])
    fields = {"subject": title, "prepared_by": me,
              "prepared_title": (profile.get("designation") or "") if positions else "",
              "noted_by_name": reviewer[0] or BLANK, "noted_by_title": reviewer[1] or BLANK,
              "head_name": head_name.upper() if head_name else BLANK, "head_title": head_title or BLANK,
              "approved_unit": SIGNATORY_UNIT}
    people = describe_people(conn, entry, None, positions)
    participants = [_line(i, name, designation) for i, (name, designation) in enumerate(people, 1)]
    visitors = [line for line in get_visitors(conn, entry["id"]).splitlines() if line.strip() and line.strip().lower() != "none"]
    participants += [f"{len(people) + i}. {line}" for i, line in enumerate(visitors, 1)]
    references = get_dpo_cites(conn, entry["id"]).strip()
    details = [f"Date: {days_text(entry)}", f"Venue: {where_text(entry)}",
               f"References: {references or '[Add the relevant issuances or reference documents.]'}"]
    if entry.get("meeting_url"):
        details.append(f"Online meeting: {entry['meeting_url']}")
    blocks = {"requested_action": ["[State the decision, approval or other action requested.]"],
              "background": ["[Explain the background, rationale and legal basis of the activity.]"],
              "outputs": list(CONCEPT_PROMPTS["outputs"]),
              "participants": participants or ["[List participants and key stakeholders.]"],
              "date_venue_references": details}
    return td.DocPayload("executive_briefer", "executive_briefer", f"Executive Briefer - {title}"[:120], fields, blocks=blocks)


def _invitation_external(conn, entry, title, me, head_name, head_title, drafter_id) -> td.DocPayload:
    """The stored host names an office, not its head/address; do not infer personal addressees."""
    outside = get_outside(conn, entry["id"]) or {}
    fields = {"date": td.long_date(tz.today_local()), "addressee_name": BLANK,
              "addressee_title": BLANK, "addressee_agency": outside.get("host") or BLANK,
              "addressee_address": BLANK, "salutation_name": BLANK,
              "subject": f"Invitation to {title}", "head_name": head_name.upper() if head_name else BLANK,
              "head_title": head_title or BLANK}
    details = [f"Activity: {title}", f"When: {when_text(entry)}", f"Venue: {where_text(entry)}",
               "[Specify the requested representatives and their role.]"]
    if entry.get("meeting_url"):
        details.append(f"Online meeting: {entry['meeting_url']}")
    blocks = {"letter_opening": [f"We respectfully invite your office to participate in {title}."],
              "activity_purpose": ["[Explain the activity's purpose and why this office's participation is requested.]"],
              "letter_details": details,
              "contact_details": [f"For coordination, please contact {me} at {BLANK}; telephone {BLANK}."]}
    # Contact email is supplied by the caller's account only; no contact is taken from source wording.
    account = st.get_admin_user_by_id(conn, drafter_id) or {}
    if account.get("username"):
        blocks["contact_details"] = [f"For coordination, please contact {me} at {account['username']}; telephone {BLANK}."]
    extras = {"file_copy": True, "boxes": ["slip"]}
    reviewer = file_copy_reviewer(conn, entry, [drafter_id])
    if reviewer[0]:
        extras["reviewer"] = {"name": reviewer[0], "title": reviewer[1]}
    return td.DocPayload("invitation_external", "invitation_external", f"External Invitation - {title}"[:120],
                         fields, blocks=blocks, extras=extras)


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
    supervisor = st.org_seat_holder(conn, 1, org_path=profile["org_path"], exclude_rp_id=profile.get("rp_id")) if profile.get("org_path") else None
    if supervisor:
        fields["noted_by_name"], fields["noted_by_title"] = supervisor
    fields.update(recommended_name=head_name.upper() if head_name else BLANK,
                  recommended_unit=SIGNATORY_UNIT, approved_name=BLANK, approved_title=BLANK, approved_unit=BLANK)
    blocks = {**CONCEPT_PROMPTS, "participants": participants,
              "participants_note": ["[Confirm participant groups and counts; add any people not yet listed.]"]}
    rows = {"program": {"marker": "pd_day", "data": [{"pd_day": _day_label(i, d), "pd_text": "[Activities for this day]", "pd_am": "", "pd_pm": ""}
                                                     for i, d in enumerate(days, 1)]}}
    rows["participants"] = {"marker": "pt_group", "data": [
        {"pt_group": n + (f", {d}" if d else ""), "pt_count": "1"} for n, d in people
    ] or [{"pt_group": "[Participant group]", "pt_count": BLANK}]}
    return td.DocPayload("concept_note", "concept_note", f"Concept Note - {title}"[:120], fields, blocks=blocks, rows=rows)


def _notice_of_meeting(conn, entry, title, me, profile, head_name, head_title, unit, positions=False) -> td.DocPayload:
    """Notice of meeting (spot feedback #189/#192). The app knows the date, time, place, link and who is invited, so those
    are filled; the agenda is the person's to write. Expected participants from other offices come from the item."""
    people = describe_people(conn, entry, None, positions)
    # Retain the legacy block for the old drawn template during rollout/rollback.
    invited = [_line(i, n, d) for i, (n, d) in enumerate(people, 1)]
    rows = []
    for person in entry.get("people") or []:
        prof = st.get_user_profile(conn, person["user_id"]) or {}
        name = prof.get("person_name") or prof.get("username") or ""
        if not name:
            continue
        office = conn.execute("SELECT name FROM org_unit WHERE id=?", (prof.get("org_unit_id"),)).fetchone()
        rows.append({"inv_name": name, "inv_office": office[0] if office else ""})
    others = [line for line in get_visitors(conn, entry["id"]).split("\n") if line.strip()]
    invited += [f"{len(people) + i}. {line}" for i, line in enumerate(others, 1)]
    # Free-text visitors are not split at commas: names and credentials may contain them.
    rows += [{"inv_name": line, "inv_office": ""} for line in others]
    link = (entry.get("meeting_url") or "").strip()
    start, end = entry.get("start_time"), entry.get("end_time")
    time = entry.get("time_note") or BLANK
    if start:
        time = td.clock_text(start) + (f" to {td.clock_text(end)}" if end else "")
    fields = {"date": td.long_date(tz.today_local()), "title": title, "subject": title, "unit_name": SIGNATORY_UNIT,
              "meeting_date": days_text(entry), "meeting_time": time,
              "meeting_when": when_text(entry), "venue": where_text(entry), "meeting_link": link,
              "prepared_by": me, "prepared_title": (profile.get("designation") or "") if positions else "",
              "head_name": head_name.upper() if head_name else BLANK, "head_title": head_title}
    blocks = {"invited": invited or ["[List who is invited.]"],
              "agenda": ["[First agenda item]", "[Second agenda item]"]}
    table = {"invitees": {"marker": "inv_name", "data": rows or [{"inv_name": BLANK, "inv_office": ""}]}}
    return td.DocPayload("notice_of_meeting", "notice_of_meeting", f"Notice of Meeting - {title}"[:120], fields,
                         blocks=blocks, rows=table, extras={"file_copy": True, "boxes": []})


MINUTES_PROMPTS = {
    "agenda": ["1. [first agenda item]", "2. [second agenda item]"],
    "discussion": ["[What was discussed under each agenda item, and what was decided.]"],
    "next_steps": ["[When and where the next meeting is, if one is set.]"],
}


def _minutes(conn, entry, title, me, profile, head_name, unit, positions=False) -> td.DocPayload:
    """Minutes of the meeting (spot feedback #177). The app knows the date, place and who was invited; what was said,
    decided and assigned is the person's to write, so those parts are prompts and an empty action table."""
    people = describe_people(conn, entry, None, positions)
    attendees = [_line(i, n, d) for i, (n, d) in enumerate(people, 1)] or ["[List who attended.]"]
    fields = {"title": title, "unit_name": unit, "meeting_when": when_text(entry), "venue": where_text(entry),
              "prepared_by": me, "prepared_title": (profile.get("designation") or "") if positions else "",
              "approved_by": head_name.upper() if head_name else BLANK}
    blocks = {**MINUTES_PROMPTS, "attendees": attendees}
    rows = {"actions": {"marker": "m_action", "data": [{"m_action": "", "m_who": "", "m_due": ""} for _ in range(3)]}}
    return td.DocPayload("minutes", "minutes", f"Minutes - {title}"[:120], fields, blocks=blocks, rows=rows)


def _program_flow(entry, title) -> td.DocPayload:
    """A heading row for each day and two empty rows under it: the schedule itself is the person's to write."""
    days = td.trip_days(entry["start_date"], entry.get("end_date") or entry["start_date"])
    data = []
    for i, d in enumerate(days, 1):
        data.append({"pf_time": _day_label(i, d), "pf_topic": "", "pf_person": ""})
        data += [{"pf_time": "", "pf_topic": "", "pf_person": ""} for _ in range(2)]
    return td.DocPayload("program_flow", "program_flow", f"Program Flow - {title}"[:120], {"title": title},
                         rows={"flow": {"marker": "pf_time", "data": data}})


# What to tell the person when the order was made but its extra page was not (the relay's "extras" result).
EXTRAS_WARNINGS = {
    "docs_service_off": "The extra file-copy page was not added: the Google Docs service is not switched on in the relay script. "
                        "An administrator can enable it (see ACTIVITY_DOCS_SETUP.md).",
    "failed": "The extra file-copy page could not be added this time. The order itself is complete; try Draft again, or add the page by hand.",
}

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


def prepare(conn, entry, key, user, owner_label="", relay=None, positions=False, designations=None) -> Prepared:
    """Build the relay request for a new revision of one document (reads the database)."""
    pl = payload(conn, entry, key, user, owner_label, positions, designations)
    rev = int((get_rows(conn, entry["id"]).get(key) or {"rev": 0})["rev"]) + 1
    relay = relay or gdocs_relay.get_relay()
    share = [user["username"]] if user.get("username") else []
    return Prepared(entry["id"], key, rev, lambda: relay.generate_doc(
        request_id=f"act{entry['id']}:{key}:{rev}", template_key=pl.template_key, folder_key=f"act-{entry['id']}",
        title=pl.title, fields=pl.fields, blocks=pl.blocks, rows=pl.rows, share_with=share, extras=pl.extras or None))


def record(conn, prep, res, user) -> dict:
    """Store the link (or why it failed) and return {"ok": bool, "url": str, "error": str}. A new draft is a new
    revision, so it never overwrites the earlier one, and a failure keeps the last good link."""
    url = (res.data or {}).get("url") if res.ok else ""
    err = "" if url else PLAIN_ERRORS.get(res.error, GENERIC_ERROR)
    if not url:                      # the person sees a plain sentence; the relay's own code goes only to the log
        logging.getLogger(__name__).warning("Activity document draft failed: entry=%s doc=%s rev=%s relay_error=%s",
                                            prep.entry_id, prep.key, prep.rev, res.error or "no_url")
    if prep.key in ("invitation_external", "executive_briefer") and res.error == "template_not_set":
        label = "external invitation" if prep.key == "invitation_external" else "executive briefer"
        err = f"The {label} template has not been set up yet. Ask an administrator to complete its setup."
    conn.execute("INSERT INTO calendar_entry_doc(entry_id, doc_key, doc_url, doc_state, note, rev, updated_by, updated_at) "
                 "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(entry_id, doc_key) DO UPDATE SET doc_url=CASE WHEN excluded.doc_url<>'' "
                 "THEN excluded.doc_url ELSE calendar_entry_doc.doc_url END, doc_state=excluded.doc_state, note=excluded.note, "
                 "rev=excluded.rev, updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                 (prep.entry_id, prep.key, url or "", "done" if url else "failed", err, prep.rev, user.get("username"), tz.now_iso()))
    conn.commit()
    extras = (res.data or {}).get("extras") if res.ok else ""
    warning = EXTRAS_WARNINGS.get(extras, "") if url else ""
    return {"ok": bool(url), "url": url or "", "error": err, "warning": warning}


def draft(conn, entry, key, user, owner_label="", relay=None, positions=False, designations=None) -> dict:
    """Prepare, send and record in one step (for callers that are not on an event loop)."""
    prep = prepare(conn, entry, key, user, owner_label, relay, positions, designations)
    return record(conn, prep, prep.call(), user)
