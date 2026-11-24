"""Advisory Google Slides files through the documents relay (apps_script/advisory_slides.gs).

Increment 1 of docs/ADVISORY_SLIDES_PLAN.md: the app-side client only. Nothing here touches the
database or sends mail; the advisory workflow calls it in later increments.

- create(): copy the office advisory master, keep one variant slide, fill the {{placeholders}} and
  the QR code, and share it with the section's editors (no "shared with you" emails).
- snapshot(): the reviewed copy (PDF + PNG) with its Drive version and open Slides comments; the
  bytes are checked against the relay's SHA-256 before anything is returned.
- set_access(): exactly who may edit, comment or view (used at submit, return and issue).

Every call goes through gdocs_relay.call (signed, retried once with the same request). Tests pass a
fake `call`. Errors come back as short codes; describe() turns them into plain sentences."""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import re
from dataclasses import dataclass, field

import gdocs_relay

# The placeholders Office Connect fills. Keep in step with ADVISORY_PLACEHOLDERS_ in advisory_slides.gs.
PLACEHOLDERS = ("number", "title", "dates", "venue", "message", "attention", "contact", "link", "qr")
TEXT_PLACEHOLDERS = tuple(k for k in PLACEHOLDERS if k != "qr")
MAX_FIELD = 2000
MAX_PEOPLE = 200
MAX_SNAPSHOT_BYTES = 20 * 1024 * 1024
_SLUG = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_REQUEST = re.compile(r"^[A-Za-z0-9:_-]{1,80}$")
_FILE_ID = re.compile(r"^[-\w]{20,80}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+$")


@dataclass
class Created:
    id: str
    url: str
    name: str
    version: str
    unfilled: list = field(default_factory=list)   # placeholders still on the slide (the template lacks a value)
    qr: str = "none"                               # placed / no_qr_box / bad_image / none


@dataclass
class Comment:
    id: str
    content: str
    author: str
    created_time: str
    quoted: str = ""
    replies: list = field(default_factory=list)


@dataclass
class Snapshot:
    file_id: str
    version: str
    modified_time: str
    pdf: bytes
    pdf_sha256: str
    png: bytes
    png_sha256: str
    comments: list = field(default_factory=list)


@dataclass
class Outcome:
    ok: bool
    value: object = None
    error: str = ""

    @property
    def message(self) -> str:
        return describe(self.error) if not self.ok else ""


def _clean(value) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()[:MAX_FIELD]


def fields(**values) -> dict:
    """The text placeholders to fill. Unknown keys are refused so a typo cannot silently do nothing."""
    unknown = set(values) - set(TEXT_PLACEHOLDERS)
    if unknown:
        raise ValueError(f"Unknown advisory placeholder(s): {', '.join(sorted(unknown))}")
    return {k: _clean(values.get(k)) for k in TEXT_PLACEHOLDERS}


def qr_png(url: str) -> bytes:
    """A plain black-on-white QR code PNG for the advisory's link."""
    import qrcode
    q = qrcode.QRCode(border=2, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(url)
    q.make(fit=True)
    buf = io.BytesIO()
    q.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
    return buf.getvalue()


def _people(emails, domain: str) -> list:
    out = []
    for e in emails or []:
        e = str(e or "").strip().lower()
        if not _EMAIL.match(e) or not e.endswith("@" + domain):
            continue                                  # never send the relay an address it would refuse
        if e not in out:
            out.append(e)
    if len(out) > MAX_PEOPLE:
        raise ValueError("Too many people to share one advisory with.")
    return out


def _b64(data: str) -> bytes:
    try:
        return base64.b64decode(data or "", validate=True)
    except (binascii.Error, ValueError):
        return b""


def info(*, thumbnails: bool = False, call=None) -> Outcome:
    call = call or gdocs_relay.call
    r = call("advisory_info", thumbnails=True) if thumbnails else call("advisory_info")
    if not r.ok:
        return Outcome(False, error=r.error)
    variants = []
    for v in r.data.get("variants") or []:
        try:
            number = int(v.get("variant"))
        except (TypeError, ValueError):
            continue
        png = _b64(v.get("png_b64")) if thumbnails else b""
        variants.append({"variant": number, "slide_id": str(v.get("slide_id") or ""),
                         "placeholders": [str(x) for x in (v.get("placeholders") or [])],
                         "png": png if png.startswith(b"\x89PNG") else b""})
    return Outcome(True, value=variants)


def create(*, request_id: str, folder_key: str, variant: int, title: str, values: dict,
           link: str = "", editors=(), domain: str = "doh.gov.ph", call=None) -> Outcome:
    """Make the advisory's Slides file. Safe to repeat: the same request_id returns the same file."""
    call = call or gdocs_relay.call
    if not _REQUEST.match(request_id or "") or not _SLUG.match(folder_key or ""):
        raise ValueError("request_id and folder_key must be plain identifiers.")
    if not isinstance(variant, int) or not 1 <= variant <= 20:
        raise ValueError("variant must be a slide number from 1.")
    payload = {"request_id": request_id, "folder_key": folder_key, "variant": variant,
               "title": _clean(title)[:120] or "Advisory", "fields": dict(values),
               "editors": _people(editors, domain)}
    if link:
        payload["qr_png_b64"] = base64.b64encode(qr_png(link)).decode("ascii")
    r = call("advisory_create", **payload)
    if not r.ok:
        return Outcome(False, error=r.error)
    d = r.data
    if not _FILE_ID.match(str(d.get("id") or "")):
        return Outcome(False, error="unconfirmed")
    return Outcome(True, value=Created(id=d["id"], url=str(d.get("url") or ""), name=str(d.get("name") or ""),
                                       version=str(d.get("version") or ""), unfilled=list(d.get("unfilled") or []),
                                       qr=str(d.get("qr") or "none")))


def snapshot(file_id: str, *, call=None) -> Outcome:
    """The copy reviewers approve. Refuses bytes that do not match the relay's own digest."""
    call = call or gdocs_relay.call
    if not _FILE_ID.match(file_id or ""):
        raise ValueError("Not a Drive file id.")
    r = call("advisory_snapshot", file_id=file_id)
    if not r.ok:
        return Outcome(False, error=r.error)
    d = r.data
    pdf, png = _b64(d.get("pdf_b64")), _b64(d.get("png_b64"))
    if not pdf.startswith(b"%PDF") or not png.startswith(b"\x89PNG"):
        return Outcome(False, error="bad_snapshot")
    if len(pdf) + len(png) > MAX_SNAPSHOT_BYTES:
        return Outcome(False, error="snapshot_too_large")
    pdf_sha, png_sha = hashlib.sha256(pdf).hexdigest(), hashlib.sha256(png).hexdigest()
    if pdf_sha != d.get("pdf_sha256") or png_sha != d.get("png_sha256") or d.get("id") != file_id \
            or not str(d.get("version") or ""):
        return Outcome(False, error="bad_snapshot")
    comments = [Comment(id=str(c.get("id") or ""), content=str(c.get("content") or ""),
                        author=str(c.get("author") or ""), created_time=str(c.get("created_time") or ""),
                        quoted=str(c.get("quoted") or ""),
                        replies=[{"content": str(x.get("content") or ""), "author": str(x.get("author") or ""),
                                  "created_time": str(x.get("created_time") or "")} for x in (c.get("replies") or [])])
                for c in (d.get("comments") or [])]
    return Outcome(True, value=Snapshot(file_id=file_id, version=str(d["version"]),
                                        modified_time=str(d.get("modified_time") or ""), pdf=pdf, pdf_sha256=pdf_sha,
                                        png=png, png_sha256=png_sha, comments=comments))


def set_access(file_id: str, *, editors=(), commenters=(), readers=(), domain: str = "doh.gov.ph",
               call=None) -> Outcome:
    """Make the file's people exactly these lists (the strongest role wins if someone is listed twice)."""
    call = call or gdocs_relay.call
    if not _FILE_ID.match(file_id or ""):
        raise ValueError("Not a Drive file id.")
    r = call("advisory_access", file_id=file_id, editors=_people(editors, domain),
             commenters=_people(commenters, domain), readers=_people(readers, domain))
    if not r.ok:
        return Outcome(False, error=r.error)
    return Outcome(True, value=list(r.data.get("changed") or []))


def version(file_id: str, *, call=None) -> Outcome:
    """The file's current Drive version, to tell whether it changed since it was approved."""
    call = call or gdocs_relay.call
    if not _FILE_ID.match(file_id or ""):
        raise ValueError("Not a Drive file id.")
    r = call("advisory_version", file_id=file_id)
    if not r.ok:
        return Outcome(False, error=r.error)
    if r.data.get("id") != file_id or not str(r.data.get("version") or ""):
        return Outcome(False, error="unconfirmed")
    return Outcome(True, value=str(r.data["version"]))


_MESSAGES = {
    "not_configured": "Making advisories in Google Slides is not switched on yet. Ask the system administrator.",
    "advisory_not_installed": "The Google Slides part of the office relay is not installed yet. Ask the system administrator.",
    "template_not_set": "The advisory template is not set up yet. Ask the system administrator.",
    "unreachable": "Google Slides could not be reached just now. Try again in a minute; nothing was lost.",
    "busy": "Google Slides is busy with another advisory. Try again in a minute; nothing was lost.",
    "changed_during_snapshot": "Someone was editing the slide while it was being saved. Try again once they finish.",
    "export_failed": "Google Slides did not give back a picture of the slide. Try again in a minute.",
    "bad_snapshot": "The saved copy from Google Slides did not check out, so it was not used. Try again.",
    "snapshot_too_large": "The slide is too large to save as a review copy. Use smaller pictures in the slide.",
    "not_allowed": "Office Connect can only work with advisory files it created.",
    "bad_variant": "That template choice is no longer available. Pick another one.",
    "bad_people": "One of the people to share with does not have an office email address.",
    "unauthorized": "The office relay refused the request. Ask the system administrator to check its setup.",
    "script_not_run": "The office relay did not run. Ask the system administrator to check its setup.",
    "unconfirmed": "Google Slides answered but did not confirm. Nothing was changed; try again.",
}


def describe(error: str) -> str:
    """A plain sentence for a person, saying what happened and what to do. Never a code or secret."""
    return _MESSAGES.get(error, "Something went wrong with Google Slides. Try again; if it keeps happening, "
                                "tell the system administrator.")
