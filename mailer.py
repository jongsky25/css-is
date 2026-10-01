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
import html as htmlmod
import os
import re
import smtplib
import socket
from datetime import datetime
from email.message import EmailMessage

import time

import httpx

import tzutil as tz

_OUTBOX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outbox.log")

# The relay does one small POST; Apps Script cold-starts can take a few seconds.
_RELAY_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# A non-JSON 200 usually means a real access misconfiguration (see
# _send_via_relay), but Apps Script is also known to serve a one-off HTML
# interstitial on an infrequently-used deployment (e.g. right after Google's
# own cold-start or cache-warming) even when access is correctly "Anyone" —
# that clears itself a moment later. One short retry tells the two apart
# instead of reporting a permanent-looking failure for a blip.
_RELAY_RETRY_DELAY = 2.0


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


def _post_to_relay(url, payload):
    """One raw POST to the relay. Returns (resp, exc) — exactly one is None."""
    try:
        # follow_redirects is REQUIRED: an Apps Script /exec URL answers with a
        # 302 over to script.googleusercontent.com and only that second
        # response carries the JSON. httpx does not follow redirects by
        # default, so without this every send would read as a failure.
        return httpx.post(url, json=payload, timeout=_RELAY_TIMEOUT, follow_redirects=True), None
    except Exception as e:                   # noqa: BLE001 - report, don't crash a request
        return None, e


def _get_relay_reply(url):
    """Re-fetch a URL with a plain GET — used ONLY to retry reading the
    relay's reply, never to retry the send. Returns (resp, exc)."""
    try:
        return httpx.get(url, timeout=_RELAY_TIMEOUT, follow_redirects=True), None
    except Exception as e:                   # noqa: BLE001 - report, don't crash a request
        return None, e


def _parse_relay_json(resp):
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


# Apps Script's own HTML error pages for a request that never ran doPost() to
# completion — the reference script catches everything inside doPost() and
# answers JSON, so one of these means the script itself couldn't run.
_APPS_SCRIPT_ERROR_RE = re.compile(
    r"(Script function not found: \w+|Authorization is required to perform that action)")


def _relay_not_run_reason(resp):
    """For a 200 reply that isn't JSON: the reason doPost() definitely did NOT
    run, or None when it may well have (the ambiguous echo case below).

    The URL the redirects ended on tells the two apart. doPost() ran → Google
    302s to script.googleusercontent.com/macros/echo to hand back its reply.
    Web-app access not set to "Anyone" (or a Workspace domain that only allows
    "Anyone within <domain>") → Google 302s the anonymous POST to
    accounts.google.com, whose sign-in page answers 200 — the request never
    reached the script, so nothing was sent and nothing can be double-sent."""
    try:
        url = httpx.URL(str(resp.url))
    except Exception:                        # noqa: BLE001 - unparseable: stay ambiguous
        return None
    if url.host == "accounts.google.com" or "ServiceLogin" in url.path:
        return ("the relay answered with a Google sign-in page, so the script "
                "never ran. Its web app access isn't set to \"Anyone\" — "
                "redeploy it with that access (see docs/MAIL_RELAY_SETUP.md)")
    if url.host != "script.googleusercontent.com":
        m = _APPS_SCRIPT_ERROR_RE.search(resp.text or "")
        if m:
            return (f"the relay script couldn't run (Apps Script said "
                    f"\"{m.group(1)}\"). Check its code and redeploy a new "
                    f"version (see docs/MAIL_RELAY_SETUP.md)")
    return None


def _send_via_relay(to, subject, body, html=None):
    """POST the message to the Apps Script web app, which sends it as the
    mailbox the script belongs to. Returns {'sent': bool, 'detail': str}."""
    url = os.environ["CSS_MAIL_RELAY_URL"]
    payload = {"secret": os.environ["CSS_MAIL_RELAY_SECRET"],
               "to": to, "subject": subject, "text": body, "html": html or "",
               "fromName": os.environ.get("CSS_MAIL_RELAY_NAME", "Office Connect")}

    resp, exc = _post_to_relay(url, payload)
    if exc is not None:
        _record(to, subject, body, f"SEND FAILED (relay): {exc}")
        return {"sent": False, "detail": f"Email send failed: mail relay unreachable ({exc})"}

    if resp.status_code != 200:
        # Apps Script returns the login page (HTML) instead of JSON when the
        # web app was deployed without "Anyone" access — a common setup slip
        # worth naming rather than dumping raw markup at the admin.
        _record(to, subject, body, f"SEND FAILED (relay HTTP {resp.status_code})")
        return {"sent": False,
                "detail": f"Email send failed: mail relay returned HTTP {resp.status_code}"}

    data = _parse_relay_json(resp)
    if data is None:
        reason = _relay_not_run_reason(resp)
        if reason:
            _record(to, subject, body, f"SEND FAILED (relay: {reason})")
            return {"sent": False, "detail": f"Email not sent: {reason}."}
    if data is None:
        # Not a sign-in page or script error page: doPost() has almost
        # certainly ALREADY run by the time this POST gets a response — its 302 just points at an "echo" URL Google uses to hand back the
        # JSON doPost() returned, and MailApp.sendEmail() inside doPost() has
        # already fired. A flaky echo step here means the mail still went
        # out; only the confirmation failed to come back as JSON. So the
        # retry MUST be a plain GET on that same (already-redirected-to) URL
        # — the reference relay script defines no doGet, so a GET can never
        # re-trigger doPost() — and must NEVER be another POST, which would
        # re-run doPost() and send the message a second time.
        time.sleep(_RELAY_RETRY_DELAY)
        resp2, exc2 = _get_relay_reply(resp.url)
        data = _parse_relay_json(resp2) if exc2 is None else None

    if data is None:
        # doPost() ran exactly once (during the original POST, above) — the
        # GET retry only re-fetches the same echo URL and never re-invokes
        # it. Both attempts answered with HTTP 200, the one signal that
        # actually distinguishes a real access misconfiguration, where the
        # request never reaches doPost() at all. Real-world testing on this
        # exact deployment (access confirmed "Anyone") showed the mail is
        # reliably delivered in this case; only the echo step's JSON
        # confirmation is unreliable. Reporting this as a FAILURE would
        # invite an admin to click "Resend email" again, which — unlike this
        # GET-only retry — really would send the message a second time. So a
        # 200 with no parseable JSON is reported as sent, with the
        # uncertainty named plainly, never as a failure that prompts a
        # manual resend.
        _record(to, subject, body, "SENT (relay, unconfirmed — 200 with no parseable reply)")
        return {"sent": True, "detail": (
            "Email likely sent — the mail relay answered but didn't confirm "
            "it with the usual reply, which normally means Apps Script already "
            "ran and sent the message before this reply came back. Check the "
            "recipient's inbox to be sure; if it truly didn't arrive, see "
            "docs/MAIL_RELAY_SETUP.md and \"Send test to me\" on Admin → Email.")}
    return _relay_result(to, subject, body, data)


def _relay_result(to, subject, body, data):
    if not data.get("ok"):
        err = str(data.get("error") or "unknown error")
        _record(to, subject, body, f"SEND FAILED (relay: {err})")
        return {"sent": False, "detail": f"Email send failed: mail relay said {err}"}
    _record(to, subject, body, "SENT (relay)")
    return {"sent": True, "detail": "Email sent."}


def send(to, subject, body, html=None):
    """Send an email. `html` is optional — when given, the message is sent as
    text+HTML alternatives (a client shows whichever it supports); when
    omitted, plain text only. Returns {'sent': bool, 'detail': str}.
    With no transport configured, records to the outbox and reports sent=False."""
    if not email_configured():
        _record(to, subject, body, "NOT SENT - no mail transport configured")
        return {"sent": False, "detail": "Email is not configured on this server."}
    if relay_configured():
        return _send_via_relay(to, subject, body, html=html)
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
    if html:
        msg.add_alternative(html, subtype="html")
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


def send_status(result):
    """Classify a mailer.send() result dict into the email_log status
    vocabulary (docs/ADMIN_EMAIL_FEATURES_PLAN.md Phase 6): 'sent', 'failed',
    or 'not_configured'. Never 'skipped_off' — that's decided by the caller
    BEFORE send() is even attempted, since a disabled feature makes no
    attempt at all."""
    if result["sent"]:
        return "sent"
    return "not_configured" if not email_configured() else "failed"


# ---- HTML template (all composers below share this shell) -------------------
#
# Email HTML is a different discipline from web HTML: no <style> block (many
# clients strip it), no flexbox/grid, every rule inline, and layout done with
# <table> so it degrades safely in Outlook's Word rendering engine. Colors
# match the app's light-mode palette (static/css/app.css --accent etc.); the
# header leads with "Office Connect" — that's the product's name now.
#
# `intro` and `extra_html` are pre-built HTML fragments — callers interpolate
# their own dynamic values (names, titles, dates, remarks) through _e() before
# embedding them, since this shell does not escape those two params. Every
# other param (`greeting`, `heading`, `footnote`, and `label`/`text` inside
# _note_box_html) IS escaped internally — pass those as plain, unescaped text.

_ACCENT = "#1040a0"
_INK = "#1b2230"
_SOFT = "#5a6473"
_BORDER = "#e2e8f0"
_BG = "#f4f6fa"


def _e(value):
    """Shorthand HTML-escape for interpolating dynamic data into intro/extra_html."""
    return htmlmod.escape(str(value)) if value is not None else ""


def _button_html(label, link):
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:26px 0;">'
            f'<tr><td style="border-radius:8px; background:{_ACCENT};">'
            f'<a href="{link}" target="_blank" style="display:inline-block; padding:13px 28px; '
            f'font-family:Arial,Helvetica,sans-serif; font-size:15px; font-weight:700; '
            f'color:#ffffff; text-decoration:none; border-radius:8px;">{htmlmod.escape(label)}</a>'
            f'</td></tr></table>')


def _list_html(rows):
    items = "".join(
        f'<li style="margin:0 0 6px; font-family:Arial,Helvetica,sans-serif; '
        f'font-size:14px; color:{_INK};">{htmlmod.escape(r)}</li>' for r in rows)
    return f'<ul style="margin:0 0 18px; padding-left:20px;">{items}</ul>'


def _section_label_html(text):
    return (f'<p style="margin:0 0 6px; font-family:Arial,Helvetica,sans-serif; '
            f'font-size:13px; font-weight:700; color:{_INK};">{htmlmod.escape(text)}</p>')


def _note_box_html(label, text):
    """A shaded callout for an admin remark or a reply quote — e.g. the note
    on a decided wellness/AWA request, or a reply to Spot Feedback."""
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:18px 0;">'
            f'<tr><td style="padding:12px 16px; background:{_BG}; border-left:3px solid {_ACCENT}; border-radius:4px;">'
            f'<p style="margin:0 0 2px; font-family:Arial,Helvetica,sans-serif; font-size:11px; font-weight:700; '
            f'color:{_SOFT}; text-transform:uppercase; letter-spacing:.03em;">{htmlmod.escape(label)}</p>'
            f'<p style="margin:0; font-family:Arial,Helvetica,sans-serif; font-size:14px; line-height:1.5; '
            f'color:{_INK};">{htmlmod.escape(text)}</p></td></tr></table>')


def _email_html(greeting, heading, intro, cta_label, link, footnote="", extra_html=""):
    button = _button_html(cta_label, link)
    footnote_html = (f'<p style="margin:0; font-family:Arial,Helvetica,sans-serif; font-size:13px; '
                      f'line-height:1.6; color:{_SOFT};">{htmlmod.escape(footnote)}</p>') if footnote else ""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0; padding:0; background:{_BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{_BG}; padding:32px 16px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px; background:#ffffff; border:1px solid {_BORDER}; border-radius:12px;">
<tr><td style="padding:26px 32px 18px; border-bottom:1px solid {_BORDER};">
  <div style="font-family:Arial,Helvetica,sans-serif; font-weight:800; font-size:18px; color:{_INK};">Office Connect</div>
  <div style="font-family:Arial,Helvetica,sans-serif; font-size:11px; color:{_SOFT}; letter-spacing:.04em; text-transform:uppercase; margin-top:3px;">Bureau of Local Health Systems Development</div>
</td></tr>
<tr><td style="padding:30px 32px;">
  <p style="margin:0 0 6px; font-family:Arial,Helvetica,sans-serif; font-size:14px; color:{_SOFT};">{htmlmod.escape(greeting)}</p>
  <h1 style="margin:0 0 14px; font-family:Arial,Helvetica,sans-serif; font-size:20px; color:{_INK};">{htmlmod.escape(heading)}</h1>
  <p style="margin:0; font-family:Arial,Helvetica,sans-serif; font-size:15px; line-height:1.6; color:{_INK};">{intro}</p>
  {extra_html}
  {button}
  {footnote_html}
  <p style="margin:22px 0 0; font-family:Arial,Helvetica,sans-serif; font-size:12px; line-height:1.5; color:{_SOFT}; word-break:break-all;">Or paste this link into your browser:<br><a href="{link}" style="color:{_ACCENT};">{link}</a></p>
</td></tr>
<tr><td style="padding:16px 32px; background:{_BG}; border-top:1px solid {_BORDER}; border-radius:0 0 12px 12px;">
  <p style="margin:0; font-family:Arial,Helvetica,sans-serif; font-size:12px; color:{_SOFT};">This is an automated message from Office Connect. Please do not reply to this email.</p>
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""


# ---- message composers ------------------------------------------------------

def invite_message(name, link, inviter=None):
    """Returns (subject, plain_text_body, html_body)."""
    subject = "Your Office Connect account — set your password"
    who = f" by {inviter}" if inviter else ""
    body = (f"Hello {name or 'there'},\n\n"
            f"An account was created for you{who} on Office Connect, the bureau's "
            f"staff system. To finish setting it up, choose your password here:\n\n"
            f"  {link}\n\n"
            f"This link expires in 7 days. If you weren't expecting this, you can "
            f"ignore this message.\n")
    intro = (f"An account was created for you{htmlmod.escape(who)} on Office Connect, the "
             f"bureau's staff system. To finish setting it up, choose your password below.")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Set up your account",
        intro=intro,
        cta_label="Set your password",
        link=link,
        footnote="This link expires in 7 days. If you weren't expecting this, you can safely "
                 "ignore this message.",
    )
    return subject, body, html


def reset_message(name, link):
    """Returns (subject, plain_text_body, html_body)."""
    subject = "Office Connect — reset your password"
    body = (f"Hello {name or 'there'},\n\n"
            f"We received a request to reset your Office Connect password. Set a new one here:\n\n"
            f"  {link}\n\n"
            f"This link expires in 1 hour. If you didn't request this, you can safely "
            f"ignore this message — your password won't change.\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Reset your password",
        intro="We received a request to reset your Office Connect password. Set a new one below.",
        cta_label="Reset your password",
        link=link,
        footnote="This link expires in 1 hour. If you didn't request this, you can safely "
                 "ignore this message — your password won't change.",
    )
    return subject, body, html


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


def css_reminder_message(name, link, event_title, close_label=None):
    """Returns (subject, plain_text_body, html_body). The organizer's one-click
    nudge from Monitor to a registrant who hasn't finished the activity's
    feedback. `link` is their own resume link (same as the recovery email), so
    it lands them back on the forms they still owe."""
    by = f" by {close_label}" if close_label else ""
    subject = f"Reminder — please finish your feedback for {event_title}"
    body = (f"Hello {name or 'there'},\n\n"
            f"Thank you for joining “{event_title}”. Your feedback isn't "
            f"finished yet — please complete it{by}. Your personal link picks "
            f"up where you left off:\n\n"
            f"  {link}\n\n"
            f"Keep this link to yourself — it's tied to your registration.\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Your feedback isn't finished yet",
        intro=(f"Thank you for joining &ldquo;{_e(event_title)}&rdquo;. Please "
               f"complete your feedback{_e(by)} — your personal link picks up "
               f"where you left off."),
        cta_label="Finish my feedback",
        link=link,
        footnote="Keep this link to yourself — it's tied to your registration.",
    )
    return subject, body, html


def registration_confirmed_message(name, link, event_title, event_date=None, venue=None):
    """Returns (subject, plain_text_body, html_body). Sent right after an
    attendee registers (or resumes a lost registration) for an event."""
    when = f" on {event_date}" if event_date else ""
    where = f" at {venue}" if venue else ""
    subject = f"You're registered — {event_title}"
    body = (f"Hello {name or 'there'},\n\n"
            f"You're registered for “{event_title}”{when}{where}. Keep this personal "
            f"link — it's how you get back to your registration and leave feedback:\n\n"
            f"  {link}\n\n"
            f"If you didn't request this, you can ignore this message.\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="You're registered",
        intro=(f"You're registered for &ldquo;{_e(event_title)}&rdquo;{_e(when)}{_e(where)}. "
               f"Keep the link below — it's how you get back to your registration and "
               f"leave feedback."),
        cta_label="View your registration",
        link=link,
        footnote="If you didn't request this, you can safely ignore this message.",
    )
    return subject, body, html


# ---- action-needed notifications --------------------------------------------
# Each returns (subject, plain_text_body, html_body), same shape as invite/reset.

def certificate_ready_message(name, link, event_title):
    """Returns (subject, plain_text_body, html_body). Sent once, the moment an
    attendee finishes every feedback form on an activity that has certificates
    enabled — mirrors the button that already appears on the thanks/link-tree
    pages, for the participant who doesn't come back to click it."""
    subject = f"Your Certificate of Appearance is ready — {event_title}"
    body = (f"Hello {name or 'there'},\n\n"
            f"Thanks for completing your feedback for “{event_title}”. Your "
            f"Certificate of Appearance is ready to download:\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Your certificate is ready",
        intro=(f"Thanks for completing your feedback for &ldquo;{_e(event_title)}&rdquo;. "
               f"Your Certificate of Appearance is ready to download."),
        cta_label="Download your certificate",
        link=link,
    )
    return subject, body, html


def raffle_winner_message(name, event_title, prize, link):
    """Returns (subject, plain_text_body, html_body). Sent to a raffle winner who
    left an email on file (registered attendees only — anonymous/walk-in
    commenters are still announced on the draw screen, just not emailed)."""
    prize_text = prize or "a prize"
    subject = f"You won the raffle — {event_title}!"
    body = (f"Hello {name or 'there'},\n\n"
            f"Congratulations — you won {prize_text} in the raffle for "
            f"“{event_title}”! Get in touch with the organizer to claim it.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="You won the raffle!",
        intro=(f"Congratulations — you won {_e(prize_text)} in the raffle for "
               f"&ldquo;{_e(event_title)}&rdquo;! Get in touch with the organizer "
               f"to claim it."),
        cta_label="View the activity",
        link=link,
    )
    return subject, body, html


def event_reminder_message(name, title, event_date, venue, link):
    """Returns (subject, plain_text_body, html_body). Sent the day before an
    activity to a registrant, its creator, or its section chief — `link` is
    whichever page fits the recipient (their registration, or the monitor)."""
    when = f" tomorrow, {event_date}" if event_date else " tomorrow"
    where = f" at {venue}" if venue else ""
    subject = f"Reminder — {title} is tomorrow"
    body = (f"Hello {name or 'there'},\n\n"
            f"“{title}” is happening{when}{where}.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Your activity is tomorrow",
        intro=f"&ldquo;{_e(title)}&rdquo; is happening{_e(when)}{_e(where)}.",
        cta_label="View details",
        link=link,
    )
    return subject, body, html


def csm_rp_results_message(rp_name, topic, event_title, link):
    """Returns (subject, plain_text_body, html_body). Sent once to a resource
    person (speaker) with a login, after their own Type-3 CSM ratings for a
    session have concluded — the results view requires signing in, so this
    only goes to an RP with an admin_user account."""
    subject = f"Your CSM results are ready — {topic}"
    body = (f"Hello {rp_name or 'there'},\n\n"
            f"The Client Satisfaction Measurement results for your session "
            f"“{topic}” at “{event_title}” are ready to view.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {rp_name or 'there'},",
        heading="Your CSM results are ready",
        intro=(f"The Client Satisfaction Measurement results for your session "
               f"&ldquo;{_e(topic)}&rdquo; at &ldquo;{_e(event_title)}&rdquo; are "
               f"ready to view."),
        cta_label="View your results",
        link=link,
    )
    return subject, body, html


def csm_activity_results_message(name, title, link):
    """Returns (subject, plain_text_body, html_body). Sent once to an
    activity's creator/section chief after its overall CSM/feedback picture
    has concluded — enough responses are in and the response window (or a
    grace period past the activity's end) has passed."""
    subject = f"CSM results are ready — {title}"
    body = (f"Hello {name or 'there'},\n\n"
            f"The Client Satisfaction Measurement results for “{title}” are "
            f"ready to view.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="CSM results are ready",
        intro=(f"The Client Satisfaction Measurement results for "
               f"&ldquo;{_e(title)}&rdquo; are ready to view."),
        cta_label="View results",
        link=link,
    )
    return subject, body, html


def event_created_message(creator_name, title, event_date, link):
    subject = f"Event created — {title}"
    body = (f"Hello {creator_name or 'there'},\n\n"
            f"Your event “{title}” on {event_date} was created. "
            f"Manage it here:\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {creator_name or 'there'},",
        heading="Event created",
        intro=f"Your event &ldquo;{_e(title)}&rdquo; on {_e(event_date)} was created.",
        cta_label="Manage event",
        link=link,
    )
    return subject, body, html


def event_section_notify_message(chief_name, creator_name, title, event_date, link):
    subject = f"New event under your section — {title}"
    body = (f"Hello {chief_name or 'there'},\n\n"
            f"{creator_name} created a new event under your section: "
            f"“{title}” on {event_date}.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {chief_name or 'there'},",
        heading="New event under your section",
        intro=(f"{_e(creator_name)} created a new event under your section: "
               f"&ldquo;{_e(title)}&rdquo; on {_e(event_date)}."),
        cta_label="View event",
        link=link,
    )
    return subject, body, html


def wellness_pending_message(approver_name, claimant_name, break_date, start_time, hours, link,
                              approve_link=None, deny_link=None):
    """`approve_link`/`deny_link` are optional one-click decide-by-email links
    (see auth.make_wellness_decide_token) that open a confirm page and require
    no login; `link` is always included as the dashboard fallback."""
    subject = f"Wellness break needs your approval — {claimant_name}"
    action_block = ""
    if approve_link and deny_link:
        action_block = (f"Approve:\n  {approve_link}\n\n"
                        f"Deny:\n  {deny_link}\n\n"
                        f"(These links expire in 14 days and ask you to confirm before "
                        f"deciding anything.)\n\n")
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"{claimant_name} requested a {hours}-hour wellness break on "
            f"{break_date} at {start_time}. It's waiting on your decision.\n\n"
            f"{action_block}"
            f"Or review it in the dashboard:\n  {link}\n")
    extra_html = ""
    if approve_link and deny_link:
        extra_html = (
            _button_html("Approve", approve_link) + _button_html("Deny", deny_link)
            + f'<p style="margin:0 0 4px; font-family:Arial,Helvetica,sans-serif; font-size:12px; '
              f'color:{_SOFT};">These links expire in 14 days and ask you to confirm before deciding anything.</p>'
        )
    html = _email_html(
        greeting=f"Hi {approver_name or 'there'},",
        heading="Wellness break needs your approval",
        intro=(f"{_e(claimant_name)} requested a {_e(hours)}-hour wellness break on "
               f"{_e(break_date)} at {_e(start_time)}. It's waiting on your decision."),
        cta_label="Review in the dashboard" if extra_html else "Review request",
        link=link,
        extra_html=extra_html,
    )
    return subject, body, html


def wellness_pending_reminder_message(approver_name, claimant_name, break_date, start_time,
                                      hours, link, approve_link=None, deny_link=None):
    """Returns (subject, plain_text_body, html_body). A follow-up to
    wellness_pending_message for a claim that's still undecided as its
    one-click decide link nears expiry — the links here are freshly minted
    (a new 14-day window), not the original ones."""
    subject = f"Reminder: wellness break still needs your approval — {claimant_name}"
    action_block = ""
    if approve_link and deny_link:
        action_block = (f"Approve:\n  {approve_link}\n\n"
                        f"Deny:\n  {deny_link}\n\n")
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"{claimant_name}'s {hours}-hour wellness break on {break_date} at "
            f"{start_time} is still waiting on your decision.\n\n"
            f"{action_block}"
            f"Or review it in the dashboard:\n  {link}\n")
    extra_html = ""
    if approve_link and deny_link:
        extra_html = _button_html("Approve", approve_link) + _button_html("Deny", deny_link)
    html = _email_html(
        greeting=f"Hi {approver_name or 'there'},",
        heading="Still waiting on your decision",
        intro=(f"{_e(claimant_name)}'s {_e(hours)}-hour wellness break on "
               f"{_e(break_date)} at {_e(start_time)} is still waiting on your decision."),
        cta_label="Review in the dashboard" if extra_html else "Review request",
        link=link,
        extra_html=extra_html,
    )
    return subject, body, html


def wellness_decided_message(claimant_name, action, break_date, note, link):
    subject = f"Your wellness break was {action} — {break_date}"
    note_line = f"\nNote: {note}\n" if note else ""
    body = (f"Hello {claimant_name or 'there'},\n\n"
            f"Your wellness break on {break_date} was {action}.\n{note_line}\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {claimant_name or 'there'},",
        heading=f"Your wellness break was {action}",
        intro=f"Your wellness break on {_e(break_date)} was {_e(action)}.",
        cta_label="View details",
        link=link,
        extra_html=_note_box_html("Note", note) if note else "",
    )
    return subject, body, html


def wellness_cancelled_message(approver_name, claimant_name, break_date, start_time,
                               hours, reason, link):
    """Returns (subject, plain_text_body, html_body). Sent to the approver when
    a claimant withdraws their own break — the pending decider if it hadn't
    been decided yet, or whoever approved it if it had (Spot Feedback #75:
    "how will I know if the approver was notified of my cancellation?")."""
    subject = f"Wellness break withdrawn — {claimant_name}"
    reason_line = f"\nReason given: {reason}\n" if reason else ""
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"{claimant_name} withdrew their {hours}-hour wellness break on "
            f"{break_date} at {start_time}. No action is needed from you.\n"
            f"{reason_line}\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {approver_name or 'there'},",
        heading="Wellness break withdrawn",
        intro=(f"{_e(claimant_name)} withdrew their {_e(hours)}-hour wellness break on "
               f"{_e(break_date)} at {_e(start_time)}. No action is needed from you."),
        cta_label="View in the dashboard",
        link=link,
        extra_html=_note_box_html("Reason given", reason) if reason else "",
    )
    return subject, body, html


def work_arrangement_reopened_message(name, period_label, link, note=None):
    """Returns (subject, plain_text_body, html_body). Sent to staff who missed
    the period's own filing deadline, once an admin temporarily reopens it."""
    subject = f"Work arrangement filing reopened — {period_label}"
    note_line = f"\nNote from admin: {note}\n" if note else ""
    body = (f"Hello {name or 'there'},\n\n"
            f"You didn't file a work arrangement for {period_label} before its "
            f"deadline. An admin has temporarily reopened it, so you can still "
            f"file now.\n{note_line}\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Filing reopened",
        intro=(f"You didn't file a work arrangement for {_e(period_label)} before "
               f"its deadline. An admin has temporarily reopened it, so you can "
               f"still file now."),
        cta_label="File your work arrangement",
        link=link,
        extra_html=_note_box_html("Note from admin", note) if note else "",
    )
    return subject, body, html


def wellness_file_reminder_message(name, deadline_label, link):
    """Returns (subject, plain_text_body, html_body). A nudge, timed the day
    before the Mon-Fri window closes, for someone who hasn't used any of this
    week's wellness entitlement yet — unused hours don't carry over."""
    subject = "Reminder: file your wellness break this week"
    body = (f"Hello {name or 'there'},\n\n"
            f"You haven't used this week's wellness break entitlement yet. "
            f"Breaks can only be scheduled Monday through Friday, so any hours "
            f"left unused by {deadline_label} won't carry over.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Your wellness break is still unused",
        intro=(f"You haven't used this week's wellness break entitlement yet. "
               f"Breaks can only be scheduled Monday through Friday, so any "
               f"hours left unused by {_e(deadline_label)} won't carry over."),
        cta_label="File a wellness break",
        link=link,
    )
    return subject, body, html


def work_arrangement_file_reminder_message(name, period_label, deadline_label, link):
    """Returns (subject, plain_text_body, html_body). A nudge, timed the day
    before a filing period's own Friday deadline, for someone with no work
    arrangement on file for it yet."""
    subject = f"Reminder: file your work arrangement — {period_label}"
    body = (f"Hello {name or 'there'},\n\n"
            f"You haven't filed a work arrangement for {period_label} yet. "
            f"The deadline is {deadline_label}.\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Work arrangement not yet filed",
        intro=(f"You haven't filed a work arrangement for {_e(period_label)} yet. "
               f"The deadline is {_e(deadline_label)}."),
        cta_label="File your work arrangement",
        link=link,
    )
    return subject, body, html


def whereabouts_week_message(name, week_label, days, link):
    """Returns (subject, plain_text_body, html_body). The Monday "where will you
    be this week?" email. `days` is a list of (day_label, plotted_label) for
    Monday-Friday — already plotted from the person's filed work arrangement, so
    the email reads as a confirmation: change only what is different."""
    subject = f"Where will you be this week? {week_label}"
    lines = "\n".join(f"  {d}: {w}" for d, w in days)
    body = (f"Hello {name or 'there'},\n\n"
            f"Here is where we have you for {week_label}, from your work arrangement:\n\n"
            f"{lines}\n\n"
            f"If anything is different (in the field, on leave, or in the office), "
            f"change it here — one tap, no login:\n\n  {link}\n")
    rows = "".join(
        f'<tr><td style="padding:6px 12px 6px 0; font-family:Arial,Helvetica,sans-serif; '
        f'font-size:14px; color:{_SOFT};">{_e(d)}</td>'
        f'<td style="padding:6px 0; font-family:Arial,Helvetica,sans-serif; font-size:14px; '
        f'font-weight:700; color:{_INK};">{_e(w)}</td></tr>' for d, w in days)
    table = (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
             f'style="margin:16px 0 4px;">{rows}</table>')
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading=f"Where will you be this week?",
        intro=(f"Here is where we have you for {_e(week_label)}, plotted from your work "
               f"arrangement. If anything is different, change it — Office, Field or Leave."),
        extra_html=table,
        cta_label="Confirm or change my week",
        link=link,
        footnote="No login needed. Colleagues see this on the Who's in page.",
    )
    return subject, body, html


def whereabouts_nudge_message(name, week_label, link):
    """Returns (subject, plain_text_body, html_body). The Tuesday nudge to
    someone who hasn't answered the Monday whereabouts email."""
    subject = f"Reminder: confirm where you'll be — {week_label}"
    body = (f"Hello {name or 'there'},\n\n"
            f"We haven't heard where you'll be for {week_label}. It takes one tap "
            f"(your work arrangement is already filled in):\n\n  {link}\n")
    html = _email_html(
        greeting=f"Hi {name or 'there'},",
        heading="Where will you be this week?",
        intro=(f"We haven't heard from you for {_e(week_label)} yet. Your week is already "
               f"plotted from your work arrangement — confirm it, or change a day to "
               f"Office, Field or Leave."),
        cta_label="Confirm or change my week",
        link=link,
        footnote="No login needed.",
    )
    return subject, body, html


def whereabouts_rollup_message(chief_name, week_label, missing, total, link):
    """Returns (subject, plain_text_body, html_body). The chief's mid-week list
    of who in their area still hasn't reported where they'll be."""
    n = len(missing)
    subject = f"{n} still to report their week — {week_label}"
    body = (f"Hello {chief_name or 'there'},\n\n"
            f"{total - n} of {total} in your area have reported where they'll be for "
            f"{week_label}. Still undeclared ({n}):\n\n"
            + "\n".join(f"  - {m}" for m in missing)
            + f"\n\nSee who's in: {link}\n")
    html = _email_html(
        greeting=f"Hi {chief_name or 'there'},",
        heading="Whereabouts not yet reported",
        intro=(f"{total - n} of {total} in your area have reported where they'll be for "
               f"{_e(week_label)}. Still undeclared ({n}):"),
        extra_html=_list_html(missing),
        cta_label="See who's in",
        link=link,
    )
    return subject, body, html


def awa_pending_message(approver_name, requester_name, period_label, arrangement, link):
    subject = f"Work arrangement needs your approval — {requester_name}"
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"{requester_name} filed a {arrangement} work arrangement for "
            f"{period_label}. It's waiting on your decision:\n\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {approver_name or 'there'},",
        heading="Work arrangement needs your approval",
        intro=(f"{_e(requester_name)} filed a {_e(arrangement)} work arrangement for "
               f"{_e(period_label)}. It's waiting on your decision."),
        cta_label="Review request",
        link=link,
    )
    return subject, body, html


def awa_decided_message(requester_name, action, period_label, note, link):
    subject = f"Your work arrangement was {action} — {period_label}"
    note_line = f"\nNote: {note}\n" if note else ""
    body = (f"Hello {requester_name or 'there'},\n\n"
            f"Your work arrangement for {period_label} was {action}.\n{note_line}\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {requester_name or 'there'},",
        heading=f"Your work arrangement was {action}",
        intro=f"Your work arrangement for {_e(period_label)} was {_e(action)}.",
        cta_label="View details",
        link=link,
        extra_html=_note_box_html("Note", note) if note else "",
    )
    return subject, body, html


def approvals_digest_message(approver_name, wellness_lines, awa_lines, wellness_link, awa_link):
    """Returns (subject, plain_text_body, html_body). A catch-all bundling
    EVERY wellness break and work arrangement still awaiting this approver's
    decision — in case an individual notification for one of them was missed
    or lost. `wellness_lines`/`awa_lines` are already-formatted one-line
    summaries, oldest-request-first; either may be empty (never both, or the
    caller shouldn't have sent this)."""
    subject = "Your pending approvals"
    txt_parts = []
    if wellness_lines:
        txt_parts.append("Wellness breaks awaiting your decision:\n"
                         + "\n".join(f"  - {l}" for l in wellness_lines))
    if awa_lines:
        txt_parts.append("Work arrangements awaiting your decision:\n"
                         + "\n".join(f"  - {l}" for l in awa_lines))
    body = (f"Hello {approver_name or 'there'},\n\n"
            f"You have requests still waiting on your decision.\n\n"
            + "\n\n".join(txt_parts) + "\n\n"
            + (f"Wellness approvals: {wellness_link}\n" if wellness_lines else "")
            + (f"Work arrangement approvals: {awa_link}\n" if awa_lines else ""))

    extra_html = ""
    if wellness_lines:
        extra_html += _section_label_html(
            f"Wellness breaks ({len(wellness_lines)})") + _list_html(wellness_lines)
    if awa_lines:
        extra_html += _section_label_html(
            f"Work arrangements ({len(awa_lines)})") + _list_html(awa_lines)
    if wellness_lines and awa_lines:
        extra_html += _button_html("Review work arrangement approvals", awa_link)
        cta_label, link = "Review wellness approvals", wellness_link
    elif wellness_lines:
        cta_label, link = "Review wellness approvals", wellness_link
    else:
        cta_label, link = "Review work arrangement approvals", awa_link

    html = _email_html(
        greeting=f"Hi {approver_name or 'there'},",
        heading="Your pending approvals",
        intro="You have requests still waiting on your decision.",
        cta_label=cta_label,
        link=link,
        extra_html=extra_html,
    )
    return subject, body, html


def feedback_update_message(submitter_name, status, reply, link):
    subject = f"Update on your Spot Feedback — {status}"
    reply_line = f"\n“{reply}”\n" if (reply or "").strip() else ""
    body = (f"Hello {submitter_name or 'there'},\n\n"
            f"There's an update on the feedback you sent. Status: {status}.\n"
            f"{reply_line}\n"
            f"  {link}\n")
    html = _email_html(
        greeting=f"Hi {submitter_name or 'there'},",
        heading="Update on your Spot Feedback",
        intro=f"There's an update on the feedback you sent. Status: {_e(status)}.",
        cta_label="View feedback",
        link=link,
        extra_html=_note_box_html("Their reply", reply) if (reply or "").strip() else "",
    )
    return subject, body, html


# ---- Admin email control center (docs/ADMIN_EMAIL_FEATURES_PLAN.md) --------
#
# The catalog of every gateable email feature, keyed the same as the
# `email_feature.<key>` app_setting rows storage.py reads/writes. This module
# stays DB-free by design (tests/test_mailer.py imports it standalone), so it
# only holds the catalog — never the setting itself. `group` is
# "transactional" (fires from a user action) or "scheduled" (one of
# send_reminders._ALL_JOBS, 1:1 with the "job_*" keys below).
#
# key -> (label, hint, group)
FEATURES = {
    "event_created": (
        "Event created",
        "The organizer gets a confirmation with the monitor link.",
        "transactional"),
    "event_section_notify": (
        "New event under your section",
        "The section chief is told when someone creates an event under them.",
        "transactional"),
    "registration_confirmed": (
        "Registration confirmed",
        "A registrant gets their personal link back to the activity.",
        "transactional"),
    "certificate_ready": (
        "Certificate ready",
        "Sent the moment a participant finishes an activity's feedback.",
        "transactional"),
    "raffle_winner": (
        "Raffle winner",
        "A winner who registered with an email is told they won.",
        "transactional"),
    "wellness_approval": (
        "Wellness approval needed",
        "The approver is told a wellness break is waiting on their decision.",
        "transactional"),
    "wellness_decided": (
        "Wellness decision result",
        "The claimant is told their wellness break was approved or denied.",
        "transactional"),
    "wellness_cancelled": (
        "Wellness break withdrawn",
        "The approver is told when a claimant withdraws their own request.",
        "transactional"),
    "awa_approval": (
        "Work arrangement approval needed",
        "The approver is told a work arrangement is waiting on their decision.",
        "transactional"),
    "awa_decided": (
        "Work arrangement decision result",
        "The requester is told their work arrangement was approved or denied.",
        "transactional"),
    "awa_reopened": (
        "Filing reopened",
        "Staff who missed a deadline are told an admin reopened it.",
        "transactional"),
    "feedback_update": (
        "Spot Feedback update",
        "The submitter is told about a status change or reply.",
        "transactional"),
    "css_reminder": (
        "Monitor — remind unfinished registrants",
        "An organizer's one-click reminder, from Monitor, to every registrant "
        "who hasn't finished an activity's feedback.",
        "transactional"),
    "job_events": (
        "Day-before activity reminder",
        "Registrants, the organizer, and the section chief are reminded the "
        "day before an activity.",
        "scheduled"),
    "job_wellness_expiry": (
        "Wellness decide-link expiry reminder",
        "Re-notifies an approver whose one-click decide link is about to expire.",
        "scheduled"),
    "job_digest": (
        "Weekly pending-approvals digest",
        "A Monday bundle of everything still awaiting each approver's decision.",
        "scheduled"),
    "job_csm_rp": (
        "CSM results — resource person",
        "A resource person is emailed their own CSM results once concluded.",
        "scheduled"),
    "job_csm_activity": (
        "CSM results — activity",
        "An activity's organizer and chief get its overall CSM results.",
        "scheduled"),
    "job_wellness_file": (
        "Wellness filing nudge",
        "Nudges staff who haven't used this week's wellness entitlement yet.",
        "scheduled"),
    "job_awa_file": (
        "Work arrangement filing nudge",
        "Nudges staff with no work arrangement filed before the deadline.",
        "scheduled"),
    "job_whereabouts_nudge": (
        "Weekly whereabouts — Tuesday nudge",
        "Nudges staff who haven't answered the Monday whereabouts email.",
        "scheduled"),
    "job_whereabouts_rollup": (
        "Weekly whereabouts — chief roll-up",
        "Each chief is told who in their area still hasn't reported their week.",
        "scheduled"),
    "job_whereabouts": (
        "Weekly whereabouts",
        "A Monday email to each staff member with their week plotted from their "
        "work arrangement, to confirm or change to Office, Field or Leave.",
        "scheduled"),
}

# Account/recovery mail: never admin-disableable (see the admin email plan,
# D3) — turning any of these off could lock someone out of their own account
# recovery. Listed in the console anyway, greyed, so an admin who goes
# looking for the toggle learns why it isn't there instead of wondering if
# it's a bug. key -> (label, why)
ALWAYS_ON = {
    "invite": (
        "Account invite",
        "A new account cannot be set up without it."),
    "reset": (
        "Password reset",
        "Disabling it would lock people out of their account for good."),
    "recovery": (
        "Registration link re-send",
        "A participant's only way back into a lost registration."),
}


# ---- Preview samples (Phase 5) ----------------------------------------------
#
# One sample per key, each a zero-arg callable that calls the REAL composer
# above with representative sample data — a preview can never drift from what
# actually sends, because it IS what sends. Covers every FEATURES key plus
# every ALWAYS_ON key (tests/test_email_admin.py loops over both catalogs and
# asserts a sample exists for each one).

_SAMPLE_LINK = "https://example.invalid/sample"

_PREVIEWS = {
    "event_created": lambda: event_created_message(
        "Jane Dela Cruz", "Basic Life Support Training", "October 2, 2026", _SAMPLE_LINK),
    "event_section_notify": lambda: event_section_notify_message(
        "Maria Santos", "Jane Dela Cruz", "Basic Life Support Training",
        "October 2, 2026", _SAMPLE_LINK),
    "registration_confirmed": lambda: registration_confirmed_message(
        "Juan Reyes", _SAMPLE_LINK, "Basic Life Support Training",
        event_date="October 2, 2026", venue="DOH Conference Room"),
    "certificate_ready": lambda: certificate_ready_message(
        "Juan Reyes", _SAMPLE_LINK, "Basic Life Support Training"),
    "raffle_winner": lambda: raffle_winner_message(
        "Juan Reyes", "Basic Life Support Training", "a tumbler", _SAMPLE_LINK),
    "wellness_approval": lambda: wellness_pending_message(
        "Maria Santos", "Juan Reyes", "October 2, 2026", "10:00 AM", 2, _SAMPLE_LINK,
        approve_link=_SAMPLE_LINK, deny_link=_SAMPLE_LINK),
    "wellness_decided": lambda: wellness_decided_message(
        "Juan Reyes", "approved", "October 2, 2026", None, _SAMPLE_LINK),
    "wellness_cancelled": lambda: wellness_cancelled_message(
        "Maria Santos", "Juan Reyes", "October 2, 2026", "10:00 AM", 1,
        "urgent office matter", _SAMPLE_LINK),
    "awa_approval": lambda: awa_pending_message(
        "Maria Santos", "Juan Reyes", "October 1-15, 2026", "work-from-home", _SAMPLE_LINK),
    "awa_decided": lambda: awa_decided_message(
        "Juan Reyes", "approved", "October 1-15, 2026", None, _SAMPLE_LINK),
    "awa_reopened": lambda: work_arrangement_reopened_message(
        "Juan Reyes", "October 1-15, 2026", _SAMPLE_LINK),
    "feedback_update": lambda: feedback_update_message(
        "Juan Reyes", "resolved", "Thanks for flagging this — fixed.", _SAMPLE_LINK),
    "css_reminder": lambda: css_reminder_message(
        "Juan Reyes", _SAMPLE_LINK, "Basic Life Support Training",
        close_label="October 9, 2026, 5:00 PM"),
    "job_events": lambda: event_reminder_message(
        "Juan Reyes", "Basic Life Support Training", "October 2, 2026",
        "DOH Conference Room", _SAMPLE_LINK),
    "job_wellness_expiry": lambda: wellness_pending_reminder_message(
        "Maria Santos", "Juan Reyes", "October 2, 2026", "10:00 AM", 2, _SAMPLE_LINK,
        approve_link=_SAMPLE_LINK, deny_link=_SAMPLE_LINK),
    "job_digest": lambda: approvals_digest_message(
        "Maria Santos", ["Juan Reyes — 2h, October 2, 2026"],
        ["Juan Reyes — work-from-home, October 1-15, 2026"], _SAMPLE_LINK, _SAMPLE_LINK),
    "job_csm_rp": lambda: csm_rp_results_message(
        "Dr. Ana Lopez", "Infection Control 101", "Basic Life Support Training", _SAMPLE_LINK),
    "job_csm_activity": lambda: csm_activity_results_message(
        "Jane Dela Cruz", "Basic Life Support Training", _SAMPLE_LINK),
    "job_wellness_file": lambda: wellness_file_reminder_message(
        "Juan Reyes", "Friday", _SAMPLE_LINK),
    "job_awa_file": lambda: work_arrangement_file_reminder_message(
        "Juan Reyes", "October 1-15, 2026", "Friday", _SAMPLE_LINK),
    "job_whereabouts_nudge": lambda: whereabouts_nudge_message(
        "Juan Reyes", "October 5-9, 2026", _SAMPLE_LINK),
    "job_whereabouts_rollup": lambda: whereabouts_rollup_message(
        "Maria Santos", "October 5-9, 2026", ["Juan Reyes", "Ana Lopez"], 6, _SAMPLE_LINK),
    "job_whereabouts": lambda: whereabouts_week_message(
        "Juan Reyes", "October 5-9, 2026",
        [("Monday, October 5", "Office"), ("Tuesday, October 6", "Office"),
         ("Wednesday, October 7", "Work from home (AWA)"),
         ("Thursday, October 8", "Office"), ("Friday, October 9", "Office")],
        _SAMPLE_LINK),
    # Always-on (ALWAYS_ON keys, not FEATURES — never toggleable, but still
    # previewable so an admin can see what they're not allowed to turn off).
    "invite": lambda: invite_message("Juan Reyes", _SAMPLE_LINK, inviter="Maria Santos"),
    "reset": lambda: reset_message("Juan Reyes", _SAMPLE_LINK),
    "recovery": lambda: recovery_message(
        "Juan Reyes", _SAMPLE_LINK, "Basic Life Support Training"),
}


def sample_message(key):
    """(subject, plain_text_body, html_or_None) for `key`, built by calling
    the REAL composer with sample data — a preview or test-send can never
    drift from what actually sends, because it IS what sends. None for a key
    with no sample. `html` is None for a plain-text-only composer
    (`recovery_message` — see app.py's registration-link re-send, which calls
    mailer.send with no html= at all)."""
    fn = _PREVIEWS.get(key)
    if fn is None:
        return None
    result = fn()
    if len(result) == 3:
        return result
    subject, body = result
    return subject, body, None


def preview(key):
    """(subject, html) for `key` — see sample_message(). A plain-text-only
    composer's body is wrapped in a minimal HTML shell so every key still
    previews as a renderable page."""
    sample = sample_message(key)
    if sample is None:
        return None
    subject, body, html = sample
    if html is None:
        html = (f'<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
                f'<body style="font-family:Arial,Helvetica,sans-serif; white-space:pre-wrap;">'
                f'{htmlmod.escape(body)}</body></html>')
    return subject, html
