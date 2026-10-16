"""Client for the Google Meet relay (an Apps Script run by the shared organizer mailbox, see
docs/MEET_RELAY_SETUP.md). Same signed envelope as gdocs_relay. Nothing here raises into a route:
every call returns a RelayResult, and a calendar item must save whether or not a link could be made.

The entry's `uid` is the request id, so a retry finds the event already made and edits and cancels
find the same event without the app storing an event id."""
from __future__ import annotations
import os
import re

import httpx

import gdocs_relay as gr
import mailer
from gdocs_relay import RelayResult

TIMEOUT = httpx.Timeout(25.0, connect=10.0)     # a person is waiting on the save
ENV_URL, ENV_SECRET = "CSS_MEET_RELAY_URL", "CSS_MEET_RELAY_SECRET"
MEET_RE = re.compile(r"^https://meet\.google\.com/[a-z0-9-]+$", re.I)


def configured() -> bool:
    return bool(os.environ.get(ENV_URL) and os.environ.get(ENV_SECRET))


def _post(url, env):
    try:
        return httpx.post(url, json=env, timeout=TIMEOUT, follow_redirects=True), None
    except Exception as e:                                   # noqa: BLE001
        return None, e


def call(action: str, **fields) -> RelayResult:
    if not configured():
        return RelayResult(False, error="not_configured")
    url, secret = os.environ[ENV_URL], os.environ[ENV_SECRET]
    request = {"action": action, **fields}
    resp, exc = _post(url, gr.envelope(request, secret))
    if exc is not None:
        resp, exc = _post(url, gr.envelope(request, secret))
    if exc is not None:
        return RelayResult(False, error="unreachable")
    if resp.status_code != 200:
        return RelayResult(False, error=f"http_{resp.status_code}")
    data = mailer._parse_relay_json(resp)
    if data is None:
        return RelayResult(False, error="script_not_run" if mailer._relay_not_run_reason(resp) else "unconfirmed")
    if not isinstance(data, dict) or not data.get("ok"):
        return RelayResult(False, error=str((data or {}).get("error") or "unknown_error")[:80])
    return RelayResult(True, data=data)


def describe(error: str) -> str:
    return {
        "not_configured": "Google Meet links are not set up yet.",
        "unreachable": "The Meet relay could not be reached.",
        "script_not_run": "The Meet relay script did not run. Check that its web app access is set to Anyone and redeploy.",
        "unconfirmed": "The Meet relay answered but did not confirm.",
        "unauthorized": "The Meet relay rejected the signature. The secrets differ or the clocks are more than 5 minutes apart.",
        "no_meet_link": "Google made the event but no Meet link.",
        "not_found": "The Meet event could not be found.",
    }.get(error, f"The Meet relay said: {error}." if error and not error.startswith("http_")
          else f"The Meet relay answered with an error ({error})." if error else "The Meet relay failed.")


def _emails(conn, entry: dict) -> list:
    """The login emails of the people on the item (a staff account's username IS their email)."""
    ids = [int(p["user_id"]) for p in entry.get("people", [])]
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT username FROM admin_user WHERE active=1 AND id IN ({q})", ids).fetchall()
    return sorted({r[0].strip().lower() for r in rows if r[0] and "@" in r[0]})


def _fields(entry: dict) -> dict:
    return {"attendees": entry.get("_emails") or [], "request_id": entry["uid"], "title": entry["title"], "start_date": entry["start_date"],
            "end_date": entry.get("end_date") or "", "start_time": entry.get("start_time") or "",
            "end_time": entry.get("end_time") or "", "note": ""}


class Relay:
    """The interface routes depend on; tests replace `get_relay`."""

    def create(self, entry: dict) -> RelayResult:
        return call("create_meet", **_fields(entry))

    def update(self, entry: dict) -> RelayResult:
        return call("update_meet", **_fields(entry))

    def delete(self, entry: dict) -> RelayResult:
        return call("delete_meet", request_id=entry["uid"])


def get_relay() -> Relay:
    return Relay()


def wants_link(entry: dict) -> bool:
    return (entry.get("modality") in ("online", "hybrid") and not entry.get("meeting_url")
            and entry.get("status") != "cancelled")


def is_ours(entry: dict) -> bool:
    return bool(MEET_RE.match(entry.get("meeting_url") or ""))


def sync(conn, entry_id: int, *, by=None) -> str:
    """Make, refresh or remove the Meet link for one saved entry. Returns a short sentence for the
    "Saved." banner ('' when there was nothing to do or the relay is not set up). Never raises."""
    import storage as st
    if not configured():
        return ""
    try:
        e = st.cal_get(conn, entry_id)
        if e is None:
            return ""
        e["_emails"] = _emails(conn, e)
        relay = get_relay()
        if e["status"] == "cancelled":
            if is_ours(e):
                relay.delete(e)
            return ""
        if wants_link(e):
            r = relay.create(e)
            if not r.ok:
                return " No Meet link was made: " + describe(r.error) + " Add one by editing the item."
            url = r.data.get("meet_url") or ""
            if not MEET_RE.match(url):
                return " No Meet link was made: " + describe("no_meet_link")
            st.cal_update(conn, entry_id, by=by, meeting_url=url)
            return " A Google Meet link was added."
        if is_ours(e) and e["modality"] in ("online", "hybrid"):
            r = relay.update(e)
            if not r.ok and r.error == "not_found":          # e.g. restored after a cancel deleted the event
                r = relay.create(e)
                if r.ok and MEET_RE.match(r.data.get("meet_url") or ""):
                    st.cal_update(conn, entry_id, by=by, meeting_url=r.data["meet_url"])
            return "" if r.ok else " The Meet event was not updated: " + describe(r.error)
        return ""
    except Exception:                                   # noqa: BLE001 - a link must never break a save
        return " No Meet link was made because of a problem. Add one by editing the item."
