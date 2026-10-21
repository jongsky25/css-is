"""Read an uploaded invitation or request letter for a calendar item (Spot Feedback #156).

The file is looked at once and dropped here; the app keeps only the Drive link. What comes back is a SUGGESTION for the
"Another office" form (who invited us, as what, and a few key lines) that the person reads, edits and saves. A wrong or
unreadable letter costs them a few keystrokes, never a wrong DPO. Same Gemini feature, budget and rate limit as the travel
scan, so nothing new needs switching on.

Pure apart from `read()`, which makes the one Gemini call through ai_core."""
from __future__ import annotations
import re

import ai_core

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


def _text(v, n) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean(parsed) -> dict:
    """The model's answer as the form may show it. Nothing raises; anything odd becomes empty."""
    p = parsed if isinstance(parsed, dict) else {}
    host, lines = _text(p.get("host"), HOST_MAX), _text(p.get("key_lines"), KEY_LINES_MAX)
    invited = p.get("invited_as") if p.get("invited_as") in INVITED_AS else "unknown"
    return {"readable": bool(p.get("readable")) and bool(host or lines), "host": host,
            "invited_as": invited if invited != "unknown" else "", "key_lines": lines,
            "note": _text(p.get("note"), 200)}


async def read(conn, user, ip, raw: bytes, mime: str) -> dict:
    """One Gemini call over the file. Returns clean(); raises ai_core.AIError when AI is off, over budget or failing,
    so the caller can say the lines are to be typed."""
    result, _iid = await ai_core.ask_async(
        conn, user, FEATURE, PROMPT, ip=ip, system=SYSTEM, response_schema=SCHEMA,
        temperature=0.0, max_output_tokens=512, timeout=25.0, images=[(mime, raw)])
    return clean(result.get("parsed"))
