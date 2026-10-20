"""
Office Connect auth — minimal, stdlib-only authentication + role-based access control.

What it does:
  * hashes passwords with PBKDF2-HMAC-SHA256 + a per-user salt (no dependencies),
  * signs session cookies whose random IDs are registered/revoked in storage, and
  * defines the four roles and exactly what each one may do (the capability map).

Security notes (on the record):
  * This is intended for an INTERNAL / LAN tool served over plain HTTP, so the
    cookie is not protected in transit. If this is ever exposed beyond the LAN,
    put it behind HTTPS (a reverse proxy) and set the cookie 'Secure'.
  * The cookie is signed (integrity) but not encrypted; it carries only id /
    username / role / issued-at, nothing secret.
"""

from __future__ import annotations
import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time

# ---------------------------------------------------------------------
# Roles + capabilities — the single source of truth for "who may do what".
# ---------------------------------------------------------------------

ROLES = ["viewer", "encoder", "section_manager", "admin"]
ROLE_LABELS = {
    "viewer": "Viewer",
    "encoder": "Encoder",
    "section_manager": "Section Manager",
    "admin": "Administrator",
}
ROLE_BLURB = {
    "viewer": "View everything; cannot create or edit.",
    "encoder": "Viewer + manual/paper data entry.",
    "section_manager": "Encoder + edit data, create activities, response windows, link trees, "
                       "reports, adding external resource persons.",
    "admin": "Full access, including the directory, hiding people, managing users, and editing/"
             "archiving individual walk-in (Type 1) entries.",
}

# Capability map. Every gated action checks one of these names.
ROLE_CAPS = {
    "viewer":          {"view"},
    "encoder":         {"view", "encode"},
    "section_manager": {"view", "encode", "edit_data", "create_activity", "manage_event",
                        "add_external_rp"},
    "admin":           {"view", "encode", "edit_data", "create_activity", "manage_event",
                        "directory", "hide", "manage_users", "wipe", "triage_feedback",
                        "manage_walkin_entries", "merge_activity", "add_external_rp"},
}


def can(role, capability):
    """True if `role` is allowed `capability`."""
    return capability in ROLE_CAPS.get(role or "", set())


def valid_role(role):
    return role in ROLE_CAPS


# ---------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------

_ITERATIONS = 200_000


def hash_password(password, salt=None):
    """Return (pw_hash_hex, salt_hex). Generates a fresh salt if none given."""
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             bytes.fromhex(salt), _ITERATIONS)
    return dk.hex(), salt


def verify_password(password, pw_hash, salt):
    """Constant-time check of a password against a stored hash+salt."""
    calc, _ = hash_password(password, salt)
    return hmac.compare_digest(calc, pw_hash)


# PBKDF2 at _ITERATIONS is deliberately CPU-heavy (~100-150ms/call). Called
# directly from an `async def` handler it blocks the single uvicorn worker's
# event loop for that whole time — and a burst of sign-in attempts (bots hit
# /login constantly) turns that into repeated stalls that fail the load
# balancer's health check and trigger an edge 5xx storm for everyone. The async
# wrappers run the hash off the event loop so login never freezes the worker.

async def hash_password_async(password, salt=None):
    return await asyncio.to_thread(hash_password, password, salt)


async def verify_password_async(password, pw_hash, salt):
    return await asyncio.to_thread(verify_password, password, pw_hash, salt)


# ---------------------------------------------------------------------
# Session cookie — HMAC-signed token: base64(payload).hex(signature)
# ---------------------------------------------------------------------

COOKIE_NAME = "css_session"
_SECRET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".session_secret")
_MAX_AGE = 12 * 3600           # 12 hours


def _secret():
    """Load (or create on first use) the server signing secret.

    Resolution order:
      1. CSS_SESSION_SECRET env var -- set this as a private Space secret in
         production so the secret never lives inside the (possibly public) repo,
         and stays stable across rebuilds (the repo no longer ships
         .session_secret -- see build_hf_upload.ps1 / DEPLOY.md).
      2. the local .session_secret file (local dev convenience).
      3. a freshly generated secret, persisted to that file.
    """
    env = os.environ.get("CSS_SESSION_SECRET", "").strip()
    if env:
        return env.encode("ascii")
    try:
        with open(_SECRET_FILE, "r", encoding="ascii") as f:
            s = f.read().strip()
            if s:
                return s.encode("ascii")
    except FileNotFoundError:
        pass
    s = secrets.token_hex(32)
    with open(_SECRET_FILE, "w", encoding="ascii") as f:
        f.write(s)
    return s.encode("ascii")


def _b64e(b):
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user, issued_at=None):
    """Sign a token; callers must register its ID before it grants a session.

    Role/name claims are informational; requests resolve current account state.
    Old cookies without registered IDs deliberately require a fresh login.
    """
    payload = {"uid": user["id"], "u": user["username"], "r": user["role"],
               "iat": int(issued_at if issued_at is not None else time.time()),
               "v": 2, "sid": secrets.token_hex(32)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = _b64e(raw)
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token, now=None):
    """Validate signature, shape and lifetime; storage checks revocation."""
    if not isinstance(token, str) or len(token) > 4096 or "." not in token:
        return None
    try:
        body, sig = token.rsplit(".", 1)
        if not re.fullmatch(r"[0-9a-f]{64}", sig):
            return None
        expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_b64d(body))
    except (ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if (payload.get("v") != 2 or type(payload.get("uid")) is not int
            or payload["uid"] <= 0 or type(payload.get("iat")) is not int
            or not isinstance(payload.get("u"), str) or not payload["u"]
            or not isinstance(payload.get("r"), str) or not valid_role(payload["r"])
            or not isinstance(payload.get("sid"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", payload["sid"])):
        return None
    age = (now if now is not None else time.time()) - payload["iat"]
    if age >= _MAX_AGE or age < -60:
        return None
    return payload


# ---------------------------------------------------------------------
# Action tokens — for the invite ("set your password") and "forgot password"
# links. Signed with the user's CURRENT password hash, so a token stops working
# the moment the password changes: invites and resets are single-use by design,
# with no server-side token store to manage.
# ---------------------------------------------------------------------

PURPOSE_INVITE = "invite"        # first-time password set (pending account)
PURPOSE_RESET = "reset"          # forgot-password
_ACTION_MAX_AGE = {PURPOSE_INVITE: 7 * 24 * 3600, PURPOSE_RESET: 60 * 60}

# Legacy pilot password: new accounts are no longer provisioned with this (they
# get an emailed invite link instead — see app._provision_account). Kept so any
# account still carrying it (must_change=True) continues to force a reset on
# sign-in rather than being locked out.
DEFAULT_PASSWORD = "12345678"


def make_action_token(uid, purpose, pw_hash, issued_at=None):
    """Signed link token. `pw_hash` is the account's current hash ('' if pending)."""
    payload = {"uid": uid, "p": purpose,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), f"{body}|{pw_hash or ''}".encode("utf-8"),
                   hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def peek_action_uid(token):
    """Read the uid from a token WITHOUT verifying (so the caller can load the
    user and its current pw_hash). Returns (uid, purpose) or (None, None)."""
    if not token or "." not in token:
        return None, None
    body = token.rsplit(".", 1)[0]
    try:
        payload = json.loads(_b64d(body))
        return payload.get("uid"), payload.get("p")
    except (ValueError, json.JSONDecodeError):
        return None, None


def verify_action_token(token, pw_hash, purpose, now=None):
    """Validate signature (against pw_hash), purpose, and age. Returns the uid or None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), f"{body}|{pw_hash or ''}".encode("utf-8"),
                      hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("p") != purpose:
        return None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _ACTION_MAX_AGE.get(purpose, 3600):
        return None
    return payload.get("uid")


# ---------------------------------------------------------------------
# Attendee recovery tokens — a "magic link" so a participant who lost their
# ?att= link can be sent back into their existing registration from ANY device
# (not just the one holding the cookie). Unlike the user action tokens above,
# these are NOT tied to a password — an attendee has no account — so they are
# signed with the server secret directly. The link only resumes a registration
# (sets the recognition cookie); it grants nothing an organizer can't already do.
# ---------------------------------------------------------------------

PURPOSE_RECOVER = "recover"
_RECOVER_MAX_AGE = 90 * 24 * 3600        # links stay valid through the activity's life


def make_recovery_token(attendee_id, issued_at=None):
    """Signed, time-limited token that resolves to one attendee id."""
    payload = {"aid": int(attendee_id), "p": PURPOSE_RECOVER,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


# Attendee SESSION token — what `?att=`, the per-event cookie, the rating form's
# hidden field and certificate links carry. A bare attendee id is guessable, so it
# is never accepted as an identity; this signed token is. A different purpose from
# the emailed "resume" link above, so one can't stand in for the other, and its
# lifetime is independent of the activity's dates (re-registering with the same
# email always mints a fresh one, so nobody is locked out of their own certificate).
PURPOSE_ATTENDEE = "att"
_ATTENDEE_MAX_AGE = 400 * 24 * 3600


def make_attendee_token(attendee_id, issued_at=None):
    payload = {"aid": int(attendee_id), "p": PURPOSE_ATTENDEE,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_attendee_token(token, now=None):
    """Validate signature + purpose + age; return the attendee id or None."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("p") != PURPOSE_ATTENDEE:
        return None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _ATTENDEE_MAX_AGE:
        return None
    return payload.get("aid")


def verify_recovery_token(token, now=None, expires_at=None):
    """Validate signature + purpose + age; return the attendee id or None.

    `expires_at` (epoch seconds) lets a caller that knows the activity's dates
    keep the link alive until then INSTEAD of the flat _RECOVER_MAX_AGE rule."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("p") != PURPOSE_RECOVER:
        return None
    cur = now if now is not None else time.time()
    if expires_at is not None:
        if cur > expires_at:
            return None
    elif cur - payload.get("iat", 0) > _RECOVER_MAX_AGE:
        return None
    return payload.get("aid")


# ---------------------------------------------------------------------
# Wellness decide-by-email tokens — lets a chief approve/deny a pending break
# request straight from the notification email, without logging in. Signed
# with the server secret directly (like the recovery tokens above, not tied
# to a password hash). Reuse after the fact is naturally capped: once the
# claim is no longer pending, decide_wellness_claim() refuses it regardless
# of how a still-unexpired token is presented.
# ---------------------------------------------------------------------

PURPOSE_WELLNESS_DECIDE = "wellness_decide"
_WELLNESS_DECIDE_MAX_AGE = 14 * 24 * 3600   # generous; the claim itself is long-decided by then


def make_wellness_decide_token(claim_id, approver_uid, issued_at=None):
    """Signed token letting `approver_uid` decide wellness claim `claim_id` by link."""
    payload = {"cid": int(claim_id), "uid": int(approver_uid), "p": PURPOSE_WELLNESS_DECIDE,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_wellness_decide_token(token, now=None):
    """Validate signature + purpose + age; return (claim_id, approver_uid) or (None, None)."""
    if not token or "." not in token:
        return None, None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None, None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None, None
    if payload.get("p") != PURPOSE_WELLNESS_DECIDE:
        return None, None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _WELLNESS_DECIDE_MAX_AGE:
        return None, None
    return payload.get("cid"), payload.get("uid")


# ---------------------------------------------------------------------
# Conference room decide-by-email link (docs/ROOM_RESERVATION_PLAN.md section 6)
#
# Same shape as the wellness one: the token names ONE reservation and ONE
# approver, opens a confirm page (never a state change on GET), and lapses after
# 14 days. rooms.approve / rooms.decline still refuse a reservation that is no
# longer open, and the route re-checks the approver is still a room approver.
# ---------------------------------------------------------------------

PURPOSE_ROOM_DECIDE = "room_decide"
_ROOM_DECIDE_MAX_AGE = 14 * 24 * 3600


def make_room_decide_token(reservation_id, approver_uid, issued_at=None):
    payload = {"rid": int(reservation_id), "uid": int(approver_uid), "p": PURPOSE_ROOM_DECIDE,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_room_decide_token(token, now=None):
    """(reservation_id, approver_uid) or (None, None) when bad, forged, wrong purpose or expired."""
    if not token or "." not in token:
        return None, None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None, None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None, None
    if payload.get("p") != PURPOSE_ROOM_DECIDE:
        return None, None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _ROOM_DECIDE_MAX_AGE:
        return None, None
    return payload.get("rid"), payload.get("uid")


# ---------------------------------------------------------------------
# Conference room tracking link for guests (R6)
#
# A guest has no account, so the signed link IS their access: it names one
# reservation and lets whoever holds it see its status, withdraw it, or take a
# suggested new time. It lapses after 150 days (a request is made at most 60 days
# ahead), and the page still checks the reservation really is a guest's.
# ---------------------------------------------------------------------

PURPOSE_ROOM_TRACK = "room_track"
_ROOM_TRACK_MAX_AGE = 150 * 24 * 3600


def make_room_track_token(reservation_id, issued_at=None):
    payload = {"rid": int(reservation_id), "p": PURPOSE_ROOM_TRACK,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_room_track_token(token, now=None):
    """The reservation id, or None when the token is bad, forged, the wrong purpose or expired."""
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("p") != PURPOSE_ROOM_TRACK:
        return None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _ROOM_TRACK_MAX_AGE:
        return None
    return payload.get("rid")


# ---------------------------------------------------------------------
# Weekly whereabouts link
#
# The Monday "where will you be this week?" email opens the week form with no
# login, so a phone tap is enough. The token names one person and one week
# (the Monday); it can only ever read/write THAT person's whereabouts for THAT
# week. It lapses after 10 days — long enough for the week plus a weekend, so
# an old email can't be used to rewrite a later week.
# ---------------------------------------------------------------------

PURPOSE_WHEREABOUTS = "whereabouts"
_WHEREABOUTS_MAX_AGE = 10 * 24 * 3600


def make_whereabouts_token(uid, week_start, issued_at=None):
    """Signed token letting `uid` report whereabouts for the week starting
    `week_start` (an ISO Monday) by link."""
    payload = {"uid": int(uid), "wk": str(week_start), "p": PURPOSE_WHEREABOUTS,
               "iat": int(issued_at if issued_at is not None else time.time())}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_whereabouts_token(token, now=None):
    """Validate signature + purpose + age; return (uid, week_start) or (None, None)."""
    if not token or "." not in token:
        return None, None
    body, sig = token.rsplit(".", 1)
    expect = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expect):
        return None, None
    try:
        payload = json.loads(_b64d(body))
    except (ValueError, json.JSONDecodeError):
        return None, None
    if payload.get("p") != PURPOSE_WHEREABOUTS:
        return None, None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _WHEREABOUTS_MAX_AGE:
        return None, None
    return payload.get("uid"), payload.get("wk")


# ---------------------------------------------------------------------
# Email + password helpers
# ---------------------------------------------------------------------

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    return bool(_EMAIL_RE.match((email or "").strip()))


def password_problem(pw):
    """Return a human reason a password is unacceptable, or None if it's fine."""
    if not pw or len(pw) < 8:
        return "Password must be at least 8 characters."
    return None
