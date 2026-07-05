"""Suggested message drafts for the managed-activity link tree.

Two slots — "welcome" (shown to a registered participant once they have
consented) and "ending" (shown once they have finished ALL the activity's
feedback) — each offered in five editable tones. `render_drafts` weaves the
activity's own details into every draft so the organizer starts from something
specific, then edits freely before saving.

The literal token ``{name}`` is intentionally LEFT in the text: it is replaced
with the participant's first name at view time (see ``personalize`` / the
templates), since the name is only known when a real participant is reading.
"""

NAME_TOKEN = "{name}"

# Tone keys, in the order the picker shows them.
TONES = ("personal", "warm", "professional", "heartfelt", "concise")

TONE_LABELS = {
    "personal": "Personal",
    "warm": "Warm",
    "professional": "Professional",
    "heartfelt": "Heartfelt",
    "concise": "Concise",
}


def _details(ev):
    """Reusable, gracefully-degrading detail fragments from an event dict."""
    title = (ev.get("title") or "this activity").strip()
    date = (ev.get("event_date") or "").strip()
    venue = (ev.get("venue") or "").strip()
    organizer = (ev.get("organizer") or ev.get("lead_name") or "").strip()
    when = f" on {date}" if date else ""
    at_venue = f" at {venue}" if venue else ""
    by_org = f"{organizer} " if organizer else ""
    return title, date, venue, organizer, when, at_venue, by_org


def _welcome_drafts(ev):
    title, date, venue, organizer, when, at_venue, by_org = _details(ev)
    sign = f"\n\n— {organizer}" if organizer else ""
    return {
        "personal":
            f"Hi {NAME_TOKEN}! So glad you could make it to {title}{when}. "
            f"Everything you need for today is right here on this page — have a great session!{sign}",
        "warm":
            f"Welcome, {NAME_TOKEN}! We're delighted you're joining us for {title}"
            f"{when}{at_venue}. Settle in — your programme, materials, and feedback "
            f"forms are all on this page.{sign}",
        "professional":
            f"Good day, {NAME_TOKEN}. Welcome to {title}"
            f"{(' (' + date + ')') if date else ''}. "
            f"This page is your hub for the session: the programme, resource materials, "
            f"and the feedback forms. Thank you for your participation.{sign}",
        "heartfelt":
            f"Welcome, {NAME_TOKEN} — we're truly happy you're here for {title}{when}. "
            f"Your presence makes this gathering meaningful, and we hope today is time "
            f"well spent for you. 💚{sign}",
        "concise":
            f"Welcome, {NAME_TOKEN}. {title}{when}. Programme, materials, and feedback "
            f"forms are below.",
    }


def _ending_drafts(ev):
    title, date, venue, organizer, when, at_venue, by_org = _details(ev)
    sign = f"\n\n— {organizer}" if organizer else ""
    return {
        "personal":
            f"You're all done, {NAME_TOKEN} — thank you! Hearing what you thought of "
            f"{title} is the best part of our work. Take care, and until the next one!{sign}",
        "warm":
            f"Thank you so much, {NAME_TOKEN}! Your feedback on {title} is in good hands "
            f"and helps us make the next one even better. We hope to see you again soon.{sign}",
        "professional":
            f"Thank you, {NAME_TOKEN}. Your responses for {title} have been recorded and "
            f"will inform how we plan and deliver future activities. We appreciate your time.{sign}",
        "heartfelt":
            f"Thank you, {NAME_TOKEN}. Your thoughts on {title} mean a great deal to us — "
            f"they directly shape how we serve you better next time. We hope to see you "
            f"again soon. 💚{sign}",
        "concise":
            f"All done — thank you, {NAME_TOKEN}! Your feedback on {title} has been recorded.",
    }


def render_drafts(slot, ev):
    """Return {tone: draft_text} for a slot ("welcome" | "ending"), with the
    activity's details woven in. ``{name}`` is left for view-time substitution."""
    if slot == "welcome":
        return _welcome_drafts(ev)
    if slot == "ending":
        return _ending_drafts(ev)
    return {}


def all_drafts(ev):
    """Both slots' drafts, ready to hand to the manage-page picker as JSON."""
    return {"welcome": render_drafts("welcome", ev),
            "ending": render_drafts("ending", ev)}


def personalize(text, name=None):
    """Substitute the {name} token with a participant's first name (or a gentle
    fallback). Used when rendering a saved message to a real participant."""
    if not text:
        return text
    first = (name or "").strip().split()[0] if (name or "").strip() else "there"
    return text.replace(NAME_TOKEN, first)
