"""Read an uploaded invitation or request letter for a calendar item (Spot Feedback #156).

The file is looked at once and dropped here; the app keeps only the Drive link. What comes back is a SUGGESTION for the
"Another office" form (who invited us, as what, and a few key lines) that the person reads, edits and saves. A wrong or
unreadable letter costs them a few keystrokes, never a wrong DPO. Same Gemini feature, budget and rate limit as the travel
scan, so nothing new needs switching on.

Pure apart from `read()`, which makes the one Gemini call through ai_core."""
from __future__ import annotations
import re

import ai_core
import storage as st

FEATURE = "travel_scan"             # shares the image-reading feature's switch, daily budget and per-account limit
INVITED_AS = ("resource_person", "attendee", "unknown")

SYSTEM = (
    "You read a Philippine government invitation or request letter to an office of the Department of Health: a "
    "request to send a resource person or speaker, or an invitation to attend or participate in an activity. "
    "Report only what is printed on it. Never guess. Do not copy any individual's name, contact number or e-mail "
    "address. If the file is not such a letter or cannot be read, set readable to false."
)
PROMPT = (
    "Read this letter. host is the office or organisation that is holding the activity or sending the letter, as "
    "printed (for example a regional office or a bureau). invited_as is resource_person if the letter asks for a "
    "speaker, lecturer, facilitator or resource person, attendee if it invites people to attend or participate, "
    "and unknown if it is not clear. key_lines is at most three short sentences, in plain words, that say what the "
    "activity is, when and where it is held, and what is asked of the receiving office. Use only what the letter "
    "says. note is one short sentence on anything the person should double-check."
)
SCHEMA = {"type": "OBJECT", "properties": {
    "readable": {"type": "BOOLEAN"},
    "host": {"type": "STRING"},
    "invited_as": {"type": "STRING", "enum": list(INVITED_AS)},
    "key_lines": {"type": "STRING"},
    "note": {"type": "STRING"},
}, "required": ["readable", "host", "invited_as", "key_lines", "note"]}

HOST_MAX, KEY_LINES_MAX = 160, 600


_CONTACT = re.compile(r"(?:https?://|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:\+?\d[\d ()-]{6,}\d))", re.I)


def _text(v, n) -> str:
    if (not isinstance(v, str) or len(v) > n or any(ord(c) < 32 for c in v)
            or any(c in v for c in "<>") or _CONTACT.search(v)):
        raise ai_core.AIBadResponse("Invalid invitation text")
    return re.sub(r"\s+", " ", v).strip()


def clean(parsed) -> dict:
    """Validate the provider reply before it can be shown in the editable form."""
    if not isinstance(parsed, dict) or set(parsed) != set(SCHEMA["required"]):
        raise ai_core.AIBadResponse("Incomplete invitation reading")
    if not isinstance(parsed["readable"], bool) or parsed["invited_as"] not in INVITED_AS:
        raise ai_core.AIBadResponse("Invalid invitation reading")
    host, lines = _text(parsed["host"], HOST_MAX), _text(parsed["key_lines"], KEY_LINES_MAX)
    note = _text(parsed["note"], 200)
    if not parsed["readable"]:
        return {"readable": False, "host": "", "invited_as": "", "key_lines": "", "note": note}
    if not host or not lines:
        raise ai_core.AIBadResponse("Incomplete invitation reading")
    return {"readable": True, "host": host,
            "invited_as": parsed["invited_as"] if parsed["invited_as"] != "unknown" else "",
            "key_lines": lines, "note": note}


async def read(conn, user, ip, raw: bytes, mime: str) -> dict:
    """One Gemini call over the file. Returns clean(); raises ai_core.AIError when AI is off, over budget or failing,
    so the caller can say the lines are to be typed."""
    result, iid = await ai_core.ask_async(
        conn, user, FEATURE, PROMPT, ip=ip, system=SYSTEM, response_schema=SCHEMA,
        temperature=0.0, max_output_tokens=512, timeout=25.0, images=[(mime, raw)])
    try:
        return clean(result.get("parsed"))
    except ai_core.AIBadResponse:
        st.update_ai_interaction_outcome(conn, iid, "rejected_validation")
        raise
