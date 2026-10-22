"""Calendar display facts after the caller has checked entry visibility.

No queries, mutations, notification claims or new authority live here.
"""
from datetime import datetime, timedelta


def entry(e, *, now, restore_days, owner="", linked=False, series=None):
    status = e.get("status")
    states = {
        "confirmed": ("Confirmed on the office calendar", "The schedule is marked confirmed. This is not a room approval or an email delivery receipt.",
                      "Check the date, people and location; edit this item if the plan changes."),
        "tentative": ("Tentative — check before making plans", "The date or arrangements are not final.",
                      "Check with the organiser, then update the status when the plan is settled."),
        "postponed": ("Postponed — a new schedule needs checking", "The displayed dates belong to a postponed item; do not assume it will take place then.",
                      "Check the replacement dates with the organiser, then update the schedule and status."),
        "cancelled": ("Cancelled on the office calendar", "This item is hidden from normal calendar views. Its history is kept.",
                      "Review the cancellation and any linked room or activity before restoring."),
    }
    heading, meaning, step = states.get(status, (
        "Check this item's status", "The saved status is not recognised.", "Review the item with the organiser before making plans."))
    restore = False
    if status == "cancelled":
        # Match cal_restore's existing boundary, including legacy undated cancellations.
        stamp = e.get("cancelled_at")
        try:
            restore = not stamp or now - datetime.fromisoformat(stamp) <= timedelta(days=restore_days)
        except (ValueError, TypeError):
            return {"state": "cancelled", "heading": heading, "meaning": meaning,
                    "step": "The restore timing could not be checked. Ask the system administrator to review the cancellation record.",
                    "actor": "The organiser or system administrator", "scope": "Review linked records separately.", "can_restore": False}
        if not restore:
            step = f"The {restore_days}-day restore period has ended. Check with the organiser before adding a replacement."
    scope = "Changes here apply to the whole series." if e.get("rrule") else "Changes here apply to this item."
    if series and series.get("occ") and status != "cancelled":
        scope += " Use Change just this one or Skip this date below to affect only the selected occurrence."
    if linked:
        scope += " The linked CSS activity controls its title, dates and venue. Cancelling this calendar item does not cancel that activity."
    return {"state": status or "unknown", "heading": heading, "meaning": meaning, "step": step,
            "actor": ("Organiser / owning unit: " + owner) if owner else "The organiser or a staff member who can see this item",
            "scope": scope, "can_restore": restore}
