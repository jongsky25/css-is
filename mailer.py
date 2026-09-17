"""
Office Connect mailer — sends account emails (invite + password reset).

Honest by design: if SMTP isn't configured, it does NOT pretend to send. It
records the message to an outbox log and reports sent=False, so the caller can
fall back to showing the link to the admin. Real delivery starts the moment the
SMTP environment variables are set — no code change needed.

Configure with environment variables:
    CSS_SMTP_HOST   (required to enable sending)
    CSS_SMTP_PORT   (default 587)
    CSS_SMTP_USER   (login user; also the default From)
    CSS_SMTP_PASS   (login password)
    CSS_SMTP_FROM   (From address; defaults to CSS_SMTP_USER)
    CSS_SMTP_TLS    ("1"/"0", default "1" = STARTTLS)
"""

from __future__ import annotations
import os
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage

import tzutil as tz

_OUTBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox.log")


def _ipv4_only_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Some hosting sandboxes assign the container an IPv6 address with no
    default IPv6 route, so a connection to a host that resolves to IPv6 (e.g.
    Gmail's SMTP servers) fails instantly with "Network is unreachable" —
    before ever trying the IPv4 address that would actually work. Filtering
    resolution to IPv4-only sidesteps that; the hostname itself is untouched,
    so TLS certificate validation still checks the real domain name."""
    return socket.getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


def email_configured():
    return bool(os.environ.get("CSS_SMTP_HOST"))


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


def send(to, subject, body):
    """Send an email. Returns {'sent': bool, 'detail': str}.
    When SMTP is unconfigured, records to the outbox and reports sent=False."""
    if not email_configured():
        _record(to, subject, body, "NOT SENT - SMTP not configured")
        return {"sent": False, "detail": "Email is not configured on this server."}
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
    orig_getaddrinfo = socket.getaddrinfo
    try:
        socket.getaddrinfo = _ipv4_only_getaddrinfo
        with smtplib.SMTP(host, port, timeout=15) as s:
            if use_tls:
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
        socket.getaddrinfo = orig_getaddrinfo


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
