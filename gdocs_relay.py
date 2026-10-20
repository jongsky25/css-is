"""Client for the travel documents relay (a second Apps Script, see docs/TRAVEL_DOCS_RELAY_SETUP.md).

Every call is a signed envelope {ts, payload, sig}: sig = HMAC-SHA256(secret, f"{ts}.{payload}") in
hex, ts in milliseconds. The script rejects a bad signature or a ts more than 5 minutes off.
Nothing here raises into a route: every call returns a RelayResult.

Unlike the mail relay, an unconfirmed 200 is NEVER treated as success here: a document that was not
confirmed is not a document the person can put on a checklist. Retrying is safe because
`generate_doc` is idempotent on `request_id` (the script finds the copy it already made).

Routes get the relay through `get_relay()`, which tests replace with a fake."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field

import httpx

import mailer

TIMEOUT = httpx.Timeout(90.0, connect=10.0)
ENV_URL, ENV_SECRET = "CSS_DOCS_RELAY_URL", "CSS_DOCS_RELAY_SECRET"


@dataclass
class RelayResult:
    ok: bool
    data: dict = field(default_factory=dict)
    error: str = ""             # short code or sentence for the person: never the secret, never raw HTML


def configured() -> bool:
    return bool(os.environ.get(ENV_URL) and os.environ.get(ENV_SECRET))


def sign(ts, payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), f"{ts}.{payload}".encode("utf-8"), hashlib.sha256).hexdigest()


def envelope(request: dict, secret: str, now_ms=None) -> dict:
    ts = int(time.time() * 1000) if now_ms is None else int(now_ms)
    # ASCII only (non-ASCII becomes \uXXXX escapes): the script re-signs the payload text it receives, and a
    # form with a checkbox glyph or a pasted curly quote must sign the same whatever encoding either end assumes.
    payload = json.dumps(request, separators=(",", ":"), ensure_ascii=True, sort_keys=True)
    return {"ts": ts, "payload": payload, "sig": sign(ts, payload, secret)}


def _post(url, env):
    try:
        # follow_redirects is required: an Apps Script /exec URL answers 302 and only the second
        # response carries the JSON (same as the mail relay).
        return httpx.post(url, json=env, timeout=TIMEOUT, follow_redirects=True), None
    except Exception as e:                                   # noqa: BLE001 - report, never crash a request
        return None, e


def call(action: str, **fields) -> RelayResult:
    """One signed request. Retries once, with the same request_id, when the transport fails."""
    if not configured():
        return RelayResult(False, error="not_configured")
    url, secret = os.environ[ENV_URL], os.environ[ENV_SECRET]
    request = {"action": action, **fields}
    resp, exc = _post(url, envelope(request, secret))
    if exc is not None:
        resp, exc = _post(url, envelope(request, secret))       # new ts, identical request_id
    if exc is not None:
        return RelayResult(False, error="unreachable")
    if resp.status_code != 200:
        return RelayResult(False, error=f"http_{resp.status_code}")
    data = mailer._parse_relay_json(resp)
    if data is None:
        reason = mailer._relay_not_run_reason(resp)
        return RelayResult(False, error="script_not_run" if reason else "unconfirmed")
    if not isinstance(data, dict) or not data.get("ok"):
        return RelayResult(False, error=str((data or {}).get("error") or "unknown_error")[:80])
    return RelayResult(True, data=data)


def describe(error: str) -> str:
    """A plain sentence for an error code."""
    return {
        "not_configured": "The documents relay is not set up yet.",
        "unreachable": "The documents relay could not be reached.",
        "script_not_run": "The relay script did not run. Check that its web app access is set to Anyone and redeploy.",
        "unconfirmed": "The relay answered but did not confirm. Nothing was recorded; try again.",
        "unauthorized": "The relay rejected the signature. The secret on the Space and in the script differ, or the clocks are more than 5 minutes apart.",
        "bad_link": "That does not look like a Google Drive link.",
        "not_accessible": "The relay mailbox cannot open that file. Share it with the office mailbox and try again.",
        "template_not_set": "That document's template is not set in the relay.",
        "bad_type": "Use a photo (JPG, PNG, WebP) or a PDF.",
        "bad_size": "That file is empty or too large. Use one under 6 MB.",
        "not_allowed": "The relay would not touch that file.",
    }.get(error, f"The relay said: {error}." if error and not error.startswith("http_")
          else f"The relay answered with an error ({error})." if error else "The relay failed.")


_ASK_ADMIN = " Press Make the forms to try again. If it fails again, tell the Admin Unit."


def describe_for_filer(error: str) -> str:
    """What a person making their forms is told when one fails: what happened in plain words and what to do.
    The technical reason (secrets, scripts, templates) stays in describe() for administrators."""
    if error == "unreachable":
        return "The form service could not be reached just now. This is not caused by what you entered." + _ASK_ADMIN
    if error == "template_not_set":
        return "This form has not been set up yet. Nothing you entered is wrong. Tell the Admin Unit which form it is."
    if error == "not_configured":
        return "Making forms automatically is not switched on yet. Make the form yourself and paste its link on the filing page."
    return "The form service refused this request. This is a setup problem, not something you entered wrong." + _ASK_ADMIN


class Relay:
    """The interface routes depend on."""

    def ping(self) -> RelayResult:
        return call("ping")

    def check_link(self, url: str) -> RelayResult:
        return call("check_link", url=url)

    def generate_doc(self, *, request_id, template_key, folder_key, title, fields=None, blocks=None,
                     rows=None, share_with=None) -> RelayResult:
        return call("generate_doc", request_id=request_id, template_key=template_key, folder_key=folder_key,
                    title=title, fields=fields or {}, blocks=blocks or {}, rows=rows or {},
                    share_with=share_with or [])

    def upload_file(self, *, request_id, folder_key, item_key, name, mime, data, share_with=None) -> RelayResult:
        """Put one file in the filing's Drive folder for a checklist row. `data` is the raw bytes."""
        return call("upload_file", request_id=request_id, folder_key=folder_key, item_key=item_key, name=name,
                    mime=mime, data_b64=base64.b64encode(data).decode("ascii"), share_with=share_with or [])

    def trash_file(self, file_id: str) -> RelayResult:
        """Trash an uploaded file or folder (the relay refuses anything outside its root folder)."""
        return call("trash_file", id=file_id)


UPLOAD_VERSION = 2      # the relay script version that has upload_file and trash_file


def get_relay() -> Relay:
    return Relay()
