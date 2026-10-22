"""Admin review of a travel claim's papers before they go to paper submission (spot feedback #174).

Once every required form and attachment is in, the traveller picks a reviewer from the Administrative Section and asks
for a review. The reviewer looks at the generated and uploaded documents, notes what is missing or wrong, and either
sends that back to the traveller or approves. The traveller fixes the notes and asks again. Only an approved claim can be
marked ready (and so submitted). Approval here records that the papers are complete; it is not approval or payment of the
claim itself.

review_state on the filing: ''  nothing asked yet
                            'requested'  waiting on the reviewer
                            'changes'    the reviewer sent notes back
                            'approved'   the papers are complete"""
from __future__ import annotations

import storage as st
import tzutil as tz
import travel
import travel_rules as tr

NOTE_KINDS = (("missing", "Missing"), ("incorrect", "Incorrect"), ("other", "Other"))
NOTE_MAX = 600
LABELS = {"": "Not yet reviewed", "requested": "Waiting for the reviewer", "changes": "Changes needed",
          "approved": "Approved"}
SETTING = "travel.review_required"


def required(conn) -> bool:
    """On unless an administrator switched it off (app setting travel.review_required = 0)."""
    return st.get_setting(conn, SETTING, "1") != "0"


def gate(conn, filing):
    """The sentence that stops 'mark ready', or None when the review is done (or not required)."""
    if not required(conn) or filing.get("review_state") == "approved":
        return None
    if filing.get("review_state") == "changes":
        return "The reviewer sent notes back. Fix them, then ask for the review again."
    if filing.get("review_state") == "requested":
        return "Waiting for the reviewer to check your papers."
    return "Ask an Administrative Section reviewer to check your papers before marking this ready."


def reviewers(conn, exclude_user_id=None) -> list:
    """Active Administrative Section accounts, by name: [{'id', 'username', 'name', 'head'}]."""
    import rooms_notify
    out = [a for a in rooms_notify.approver_accounts(conn) if a["id"] != exclude_user_id]
    return sorted(out, key=lambda a: (a["name"] or "").lower())


def reviewer_of(conn, filing):
    """The chosen reviewer's account row, or None."""
    return st.get_admin_user_by_id(conn, filing["reviewer_id"]) if filing.get("reviewer_id") else None


def is_reviewer(user, filing) -> bool:
    return bool(user and filing and filing.get("reviewer_id") and filing["reviewer_id"] == user["id"])


def can_review(conn, user, filing) -> bool:
    """The chosen reviewer, as long as they are still in the Administrative Section."""
    import rooms
    return is_reviewer(user, filing) and rooms.is_room_admin(conn, user)


def _get(conn, filing_id):
    return travel.get_filing(conn, filing_id)


def _need_state(filing, *states, why):
    if not filing or filing["status"] != "open" or filing.get("review_state", "") not in states:
        raise travel.TravelError(why)


def notes_of(conn, filing_id, states=None) -> list:
    sql, args = "SELECT * FROM travel_review_note WHERE filing_id=?", [filing_id]
    if states:
        sql += " AND state IN (%s)" % ",".join("?" * len(states))
        args += list(states)
    return travel._rows(conn, sql + " ORDER BY id", tuple(args))


def request_review(conn, filing, reviewer_id, by):
    """The traveller asks (or asks again after fixing notes). Needs a complete claim and a reviewer from the section."""
    filing = _get(conn, filing["id"])
    _need_state(filing, "", "changes", why="This claim cannot be sent for review right now.")
    missing = tr.readiness(filing, travel.view_items(conn, filing), travel.flags_of(conn, filing["id"]))
    if missing:
        raise travel.TravelError("Finish the claim first: " + missing[0]
                                 + (f" (and {len(missing) - 1} more)" if len(missing) > 1 else ""))
    try:
        reviewer_id = int(reviewer_id)
    except (TypeError, ValueError):
        raise travel.TravelError("Choose who should review your papers.")
    if reviewer_id not in {a["id"] for a in reviewers(conn, exclude_user_id=filing["user_id"])}:
        raise travel.TravelError("Choose a reviewer from the Administrative Section (not yourself).")
    now = tz.now_iso()
    conn.execute("UPDATE travel_review_note SET state='resolved', resolved_at=? WHERE filing_id=? AND state='sent'",
                 (now, filing["id"]))
    conn.execute("UPDATE travel_filing SET review_state='requested', reviewer_id=?, review_round=review_round+1, "
                 "review_requested_at=?, review_decided_at=NULL, updated_at=? WHERE id=?",
                 (reviewer_id, now, now, filing["id"]))
    conn.commit()
    return _get(conn, filing["id"])


def add_note(conn, filing, item_code, kind, note, by):
    filing = _get(conn, filing["id"])
    _need_state(filing, "requested", why="This claim is not waiting for a review.")
    note = " ".join(str(note or "").split())[:NOTE_MAX]
    if not note:
        raise travel.TravelError("Say what is missing or wrong.")
    if kind not in {k for k, _ in NOTE_KINDS}:
        raise travel.TravelError("Choose whether it is missing, incorrect or something else.")
    code = (item_code or "").strip() or None
    if code and code not in {it["code"] for it in travel.view_items(conn, filing)}:
        raise travel.TravelError("That document is not on this claim's checklist.")
    conn.execute("INSERT INTO travel_review_note(filing_id, round, item_code, kind, note, state, created_by, created_at) "
                 "VALUES (?,?,?,?,?,'draft',?,?)",
                 (filing["id"], filing["review_round"], code, kind, note, by, tz.now_iso()))
    conn.commit()


def delete_note(conn, filing, note_id):
    filing = _get(conn, filing["id"])
    _need_state(filing, "requested", why="This claim is not waiting for a review.")
    conn.execute("DELETE FROM travel_review_note WHERE id=? AND filing_id=? AND state='draft'", (note_id, filing["id"]))
    conn.commit()


def send_feedback(conn, filing, by):
    """Send the drafted notes back to the traveller."""
    filing = _get(conn, filing["id"])
    _need_state(filing, "requested", why="This claim is not waiting for a review.")
    drafts = notes_of(conn, filing["id"], ("draft",))
    if not drafts:
        raise travel.TravelError("Add at least one note about what is missing or wrong, or approve the papers.")
    now = tz.now_iso()
    conn.execute("UPDATE travel_review_note SET state='sent' WHERE filing_id=? AND state='draft'", (filing["id"],))
    conn.execute("UPDATE travel_filing SET review_state='changes', review_decided_at=?, updated_at=? WHERE id=?",
                 (now, now, filing["id"]))
    conn.commit()
    return _get(conn, filing["id"]), drafts


def approve(conn, filing, by):
    filing = _get(conn, filing["id"])
    _need_state(filing, "requested", why="This claim is not waiting for a review.")
    if notes_of(conn, filing["id"], ("draft",)):
        raise travel.TravelError("You have unsent notes. Send them back to the traveller, or delete them before approving.")
    now = tz.now_iso()
    conn.execute("UPDATE travel_filing SET review_state='approved', review_decided_at=?, updated_at=? WHERE id=?",
                 (now, now, filing["id"]))
    conn.commit()
    return _get(conn, filing["id"])


def queue(conn, reviewer_id) -> list:
    """Claims waiting on this reviewer, oldest request first."""
    return travel._rows(
        conn, "SELECT f.*, u.username AS who FROM travel_filing f JOIN admin_user u ON u.id=f.user_id "
              "WHERE f.review_state='requested' AND f.reviewer_id=? AND f.status='open' "
              "ORDER BY f.review_requested_at, f.id", (reviewer_id,))


def counts(conn, user_id) -> tuple:
    """(claims waiting on this person as reviewer, their own open claims with notes sent back)."""
    waiting = conn.execute("SELECT COUNT(*) FROM travel_filing WHERE review_state='requested' AND reviewer_id=? "
                           "AND status='open'", (user_id,)).fetchone()[0]
    back = conn.execute("SELECT COUNT(*) FROM travel_filing WHERE review_state='changes' AND user_id=? "
                        "AND status='open'", (user_id,)).fetchone()[0]
    return waiting, back
