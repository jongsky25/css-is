"""
Office Connect auth — minimal, stdlib-only authentication + role-based access control.

What it does:
  * hashes passwords with PBKDF2-HMAC-SHA256 + a per-user salt (no dependencies),
  * issues a tamper-proof session as an HMAC-signed cookie value (no server-side
    session store needed), and
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
    "section_manager": "Encoder + edit data, create activities, response windows, link trees, reports.",
    "admin": "Full access, including the directory, hiding people, managing users, and editing/"
             "archiving individual walk-in (Type 1) entries.",
}

# Capability map. Every gated action checks one of these names.
ROLE_CAPS = {
    "viewer":          {"view"},
    "encoder":         {"view", "encode"},
    "section_manager": {"view", "encode", "edit_data", "create_activity", "manage_event"},
    "admin":           {"view", "encode", "edit_data", "create_activity", "manage_event",
                        "directory", "hide", "manage_users", "wipe", "triage_feedback",
                        "manage_walkin_entries", "merge_activity"},
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
    """Sign a session token for a logged-in user dict."""
    payload = {"uid": user["id"], "u": user["username"], "r": user["role"],
               "iat": int(issued_at if issued_at is not None else time.time())}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    body = _b64e(raw)
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def parse_token(token, now=None):
    """Validate a token's signature + age; return the payload dict or None."""
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
    iat = payload.get("iat", 0)
    if (now if now is not None else time.time()) - iat > _MAX_AGE:
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


def verify_recovery_token(token, now=None):
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
    if payload.get("p") != PURPOSE_RECOVER:
        return None
    if (now if now is not None else time.time()) - payload.get("iat", 0) > _RECOVER_MAX_AGE:
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
