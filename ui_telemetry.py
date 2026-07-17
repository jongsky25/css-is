"""
CSS-IS UX telemetry — passive interface-friction signal.
=========================================================

Ported from jongsky25/ofis-platform's lib/telemetry.ts (commit 7a7e369, "Add
passive UX-behavior telemetry with a ranked improvement digest") per
docs/UX_TELEMETRY_HANDOFF_PLAN.md. That build's controlled vocabulary and
sanitizers travel here close to verbatim, minus the OFIS-specific TIN masking
(no tax-id-shaped data exists in this app). The aggregation half (buildDigest
et al.) is a follow-up once ui_event actually has data to summarize — this
module is deliberately just the vocabulary + sanitizers the /telemetry ingest
route needs today.

Distinct from Spot Feedback (storage.py's spot_feedback table): that's what a
user bothers to type up. This is what happens passively — dead/rage clicks,
failed searches, client errors — so friction can eventually be ranked without
anyone having to report it.

Everything here is PURE (no DB, no FastAPI import) so it's cheap to unit test
and safe to import from both the /telemetry route and any future digest job.
"""
from __future__ import annotations
import re

# ── Controlled vocabulary (a TEXT column, not a real enum — a new type needs
# no migration). form_abandon has no detector wired yet (matching the OFIS
# reference itself, which declares it but has never shipped detection either)
# — kept in the vocabulary so a future capture-script addition needs no schema
# change.
UI_EVENT_TYPES = {
    "pageview", "dead_click", "rage_click", "search_empty", "client_error", "form_abandon",
}

MAX_TEXT = 160
MAX_SELECTOR = 1000
MAX_BATCH = 50


def sanitize_text(s, max_len=MAX_TEXT):
    """Collapse whitespace, mask any run of 3+ digits (ids/phone numbers/amounts)
    as '###', cap length. Mirrors lib/telemetry.ts's sanitizeText, minus the
    OFIS-specific TIN pattern. Returns None for empty input."""
    if not s:
        return None
    clean = re.sub(r"\s+", " ", str(s)).strip()
    if not clean:
        return None
    clean = re.sub(r"\d{3,}", "###", clean).strip()
    if not clean:
        return None
    return clean if len(clean) <= max_len else clean[:max_len] + "…"


def sanitize_selector(s, max_len=MAX_SELECTOR):
    """Trim + cap a CSS selector path (already built client-side)."""
    if not s:
        return None
    clean = str(s).strip()
    if not clean:
        return None
    return clean if len(clean) <= max_len else clean[:max_len]


_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_HEX_TOKEN_RE = re.compile(r"^[0-9a-f]{6,}$", re.IGNORECASE)
_NUMERIC_ID_RE = re.compile(r"^\d+$")


def mask_route(path):
    """Turn a concrete pathname into a route PATTERN: numeric ids, hex tokens
    (the /r/<token>, /e/<token>, /encode/<token> link shapes), and date segments
    become {id} / {token} / {date}. Query string and fragment are dropped.

    Same curly-brace convention as monitoring.bucket_path — that table is a
    hand-curated per-route map (used for the /ops request-log breakdown); this
    is its generic sibling, a catch-all segment-shape rule so a route not yet
    added there still never carries a raw id/token into ui_event.

    Idempotent: masking an already-masked route (e.g. what the client sent,
    already masked by static/js/telemetry.js) is a no-op, since none of the
    three patterns above match a literal '{id}'/'{token}'/'{date}' segment —
    which is exactly what makes it safe to re-run here as the server-side
    'never trust the client mask alone' pass."""
    if not path:
        return "/"
    p = str(path)
    cut = min((i for i in (p.find("?"), p.find("#")) if i >= 0), default=-1)
    if cut >= 0:
        p = p[:cut]
    p = re.sub(r"^https?://[^/]+", "", p, flags=re.IGNORECASE)
    if not p.startswith("/"):
        p = "/" + p
    segs = []
    for seg in p.split("/"):
        if not seg:
            segs.append(seg)
        elif _DATE_RE.match(seg):
            segs.append("{date}")
        elif _HEX_TOKEN_RE.match(seg):
            segs.append("{token}")
        elif _NUMERIC_ID_RE.match(seg):
            segs.append("{id}")
        else:
            segs.append(seg)
    masked = "/".join(segs)
    if len(masked) > 1 and masked.endswith("/"):
        masked = masked[:-1]
    return masked
