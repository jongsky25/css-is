"""
Office Connect mailer — sends account emails (invite + password reset).

Honest by design: if no transport is configured, it does NOT pretend to send.
It records the message to an outbox log and reports sent=False, so the caller
can fall back to showing the link to the admin.

TWO TRANSPORTS, tried in this order:

1. HTTPS relay (preferred on the Hugging Face Space) — the Space's network
   blocks outbound SMTP on every port (587 and 465 both time out; see
   docs/MAIL_RELAY_SETUP.md), while outbound HTTPS works fine, which is how
   ai_core.py reaches Gemini. So mail goes out as an HTTPS POST to a Google
   Apps Script web app bound to the sending mailbox, which calls Gmail on our
   behalf. Sending as that real mailbox also means Google signs the mail, so
   there is no SPF/DKIM/DNS setup to arrange.
       CSS_MAIL_RELAY_URL      (the Apps Script /exec web-app URL)
       CSS_MAIL_RELAY_SECRET   (shared token; the script rejects anything else)
       CSS_MAIL_RELAY_NAME     (optional display name, default "Office Connect")

2. SMTP — kept for networks that actually allow it (e.g. the LAN pilot).
       CSS_SMTP_HOST   (required to enable this transport)
       CSS_SMTP_PORT   (default 587 = STARTTLS; 465 = implicit TLS/SSL from
                        connect, auto-detected — no other config needed)
       CSS_SMTP_USER   (login user; also the default From)
       CSS_SMTP_PASS   (login password)
       CSS_SMTP_FROM   (From address; defaults to CSS_SMTP_USER)
       CSS_SMTP_TLS    ("1"/"0", default "1" = STARTTLS; ignored on port 465,
                        which is always encrypted)
"""

from __future__ import annotations
import os
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage

import httpx

import tzutil as tz

_OUTBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox.log")

# The relay does one small POST; Apps Script cold-starts can take a few seconds.
_RELAY_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


_real_getaddrinfo = socket.getaddrinfo   # captured before send() ever patches it


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Some hosting sandboxes assign the container an IPv6 address with no
    default IPv6 route, so a connection to a host that resolves to IPv6 (e.g.
    Gmail's SMTP servers) fails instantly with "Network is unreachable" —
    before ever trying the IPv4 address that would actually work. Filtering
    resolution to IPv4-only sidesteps that; the hostname itself is untouched,
    so TLS certificate validation still checks the real domain name.

    Calls _real_getaddrinfo, NOT socket.getaddrinfo — send() reassigns the
    latter to this very function while connecting, so looking it up by that
    name here would recurse into itself forever."""
    return _real_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


def relay_configured():
    return bool(os.environ.get("CSS_MAIL_RELAY_URL") and os.environ.get("CSS_MAIL_RELAY_SECRET"))


def smtp_configured():
    return bool(os.environ.get("CSS_SMTP_HOST"))


def email_configured():
    """True when ANY transport can actually send."""
    return relay_configured() or smtp_configured()


def _from_addr():
    return os.environ.get("CSS_SMTP_FROM") or os.environ.get("CSS_SMTP_USER") or "css-is@localhost"


def _record(to, subject, body, note):
    """Append the message to the outbox log so an undelivered link is never lost."""
    try:
        with open(_OUTBOX, "a", encoding="utf-8") as f:
            f.write(f"\n===== {tz.now_iso()} [{note}] =====\n")
            f.write(f"To: {to}\nSubject: {subject}\n\n{body}\n")
    except OSError:
        pass


def _send_via_relay(to, subject, body):
    """POST the message to the Apps Script web app, which sends it as the
    mailbox the script belongs to. Returns {'sent': bool, 'detail': str}."""
    url = os.environ["CSS_MAIL_RELAY_URL"]
    payload = {"secret": os.environ["CSS_MAIL_RELAY_SECRET"],
               "to": to, "subject": subject, "text": body,
               "fromName": os.environ.get("CSS_MAIL_RELAY_NAME", "Office Connect")}
    try:
        # follow_redirects is REQUIRED: an Apps Script /exec URL answers with a
        # 302 over to script.googleusercontent.com and only that second
        # response carries the JSON. httpx does not follow redirects by
        # default, so without this every send would read as a failure.
        resp = httpx.post(url, json=payload, timeout=_RELAY_TIMEOUT, follow_redirects=True)
    except Exception as e:                   # noqa: BLE001 - report, don't crash a request
        _record(to, subject, body, f"SEND FAILED (relay): {e}")
        return {"sent": False, "detail": f"Email send failed: mail relay unreachable ({e})"}

    if resp.status_code != 200:
        # Apps Script returns the login page (HTML) instead of JSON when the
        # web app was deployed without "Anyone" access — a common setup slip
        # worth naming rather than dumping raw markup at the admin.
        _record(to, subject, body, f"SEND FAILED (relay HTTP {resp.status_code})")
        return {"sent": False,
                "detail": f"Email send failed: mail relay returned HTTP {resp.status_code}"}
    try:
        data = resp.json()
    except ValueError:
        _record(to, subject, body, "SEND FAILED (relay: non-JSON reply)")
        return {"sent": False, "detail": ("Email send failed: mail relay did not return JSON "
                                          "(check the web app is deployed with access set to "
                                          "\"Anyone\")")}
    if not data.get("ok"):
        err = str(data.get("error") or "unknown error")
        _record(to, subject, body, f"SEND FAILED (relay: {err})")
        return {"sent": False, "detail": f"Email send failed: mail relay said {err}"}
    _record(to, subject, body, "SENT (relay)")
    return {"sent": True, "detail": "Email sent."}


def send(to, subject, body):
    """Send an email. Returns {'sent': bool, 'detail': str}.
    With no transport configured, records to the outbox and reports sent=False."""
    if not email_configured():
        _record(to, subject, body, "NOT SENT - no mail transport configured")
        return {"sent": False, "detail": "Email is not configured on this server."}
    if relay_configured():
        return _send_via_relay(to, subject, body)
    host = os.environ["CSS_SMTP_HOST"]
    port = int(os.environ.get("CSS_SMTP_PORT", "587"))
    use_tls = os.environ.get("CSS_SMTP_TLS", "1") != "0"
    user = os.environ.get("CSS_SMTP_USER")
    pw = os.environ.get("CSS_SMTP_PASS")

    msg = EmailMessage()
    msg["From"] = _from_addr()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        socket.getaddrinfo = _ipv4_only_getaddrinfo
        # Port 465 is implicit TLS from the first byte (SMTP_SSL); STARTTLS
        # (port 587 and friends) upgrades a plain connection after EHLO.
        # Mixing them up talks the wrong protocol to the server.
        smtp_cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with smtp_cls(host, port, timeout=15) as s:
            if use_tls and port != 465:
                s.starttls()
            if user and pw:
                s.login(user, pw)
            s.send_message(msg)
        _record(to, subject, body, "SENT")
        return {"sent": True, "detail": "Email sent."}
    except Exception as e:                       # noqa: BLE001 - report, don't crash a request
        _record(to, subject, body, f"SEND FAILED: {e}")
        return {"sent": False, "detail": f"Email send failed: {e}"}
    finally:
        socket.getaddrinfo = _real_getaddrinfo


# ---- message composers ------------------------------------------------------

def invite_message(name, link, inviter=None):
    subject = "Your Office Connect account — set your password"
    who = f" by {inviter}" if inviter else ""
    body = (f"Hello {name or 'there'},\n\n"
            f"An account was created for you{who} on Office Connect, the bureau's "
            f"staff system. To finish setting it up, choose your password here:\n\n"
            f"  {link}\n\n"
            f"This link expires in 7 days. If you weren't expecting this, you can "
            f"ignore this message.\n")
    return subject, body


def reset_message(name, link):
    subject = "Office Connect — reset your password"
    body = (f"Hello {name or 'there'},\n\n"
            f"We received a request to reset your Office Connect password. Set a new one here:\n\n"
            f"  {link}\n\n"
            f"This link expires in 1 hour. If you didn't request this, you can safely "
            f"ignore this message — your password won't change.\n")
    return subject, body


def recovery_message(name, link, event_title=None):
    where = f" for {event_title}" if event_title else ""
    subject = f"Your registration link{where}"
    body = (f"Hello {name or 'there'},\n\n"
            f"Here is your personal link back to your registration{where}. "
            f"Open it on any device to pick up where you left off and give your "
            f"feedback:\n\n"
            f"  {link}\n\n"
            f"Keep this link to yourself — it's tied to your registration.\n")
    return subject, body


# ---- action-needed notifications --------------------------------------------

def event_created_message(creator_name, title, event_date, link):
    subject = f"Event created — {title}"
    body = (f"Hello {creator_name or 'there'},\n\n"
            f"Your event “{title}” on {event_date} was created. "
            f"Manage it here:\n\n"
            f"  {link}\n")
    return subject, body


def event_section_notify_message(chief_name, creator_name, title, event_date, link):
    subject = f"New event under your section — {title}"
    body = (f"Hello {chief_name or 'there'},\n\n"
            f"{creator_name} created a new event under your section: "
            f"“{title}” on {event_date}.\n\n"
            f"  {link}\n")
    return subject, body


def wellness_pending_message(approver_name, claimant_name, break_date, start_time, hours, link):
    subject = f"Wellness break needs your approval — {claimant_name}"
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"{claimant_name} requested a {hours}-hour wellness break on "
            f"{break_date} at {start_time}. It's waiting on your decision:\n\n"
            f"  {link}\n")
    return subject, body


def wellness_decided_message(claimant_name, action, break_date, note, link):
    subject = f"Your wellness break was {action} — {break_date}"
    note_line = f"\nNote: {note}\n" if note else ""
    body = (f"Hello {claimant_name or 'there'},\n\n"
            f"Your wellness break on {break_date} was {action}.\n{note_line}\n"
            f"  {link}\n")
    return subject, body


def awa_pending_message(approver_name, requester_name, period_label, arrangement, link):
    subject = f"Work arrangement needs your approval — {requester_name}"
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"{requester_name} filed a {arrangement} work arrangement for "
            f"{period_label}. It's waiting on your decision:\n\n"
            f"  {link}\n")
    return subject, body


def awa_decided_message(requester_name, action, period_label, note, link):
    subject = f"Your work arrangement was {action} — {period_label}"
    note_line = f"\nNote: {note}\n" if note else ""
    body = (f"Hello {requester_name or 'there'},\n\n"
            f"Your work arrangement for {period_label} was {action}.\n{note_line}\n"
            f"  {link}\n")
    return subject, body


def feedback_update_message(submitter_name, status, reply, link):
    subject = f"Update on your Spot Feedback — {status}"
    reply_line = f"\n“{reply}”\n" if (reply or "").strip() else ""
    body = (f"Hello {submitter_name or 'there'},\n\n"
            f"There's an update on the feedback you sent. Status: {status}.\n"
            f"{reply_line}\n"
            f"  {link}\n")
    return subject, body
