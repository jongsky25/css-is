"""Persistent Short.io outbox for public survey URLs; never shorten participant tokens."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

import httpx

log = logging.getLogger(__name__)
INTERVAL = 25  # Conservative pacing shared across workers using this database
TOKEN = r"[A-Za-z0-9_-]+"


def enabled():
    return os.environ.get("CSS_SHORT_LINKS", "0") == "1"


def short_domain():
    domain = os.environ.get("SHORT_IO_DOMAIN", "blhsd.s.gy").strip().lower()
    return domain if re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}", domain) else ""


def configuration_error():
    if not os.environ.get("SHORT_IO_API_KEY", "").strip():
        return "Short links need the SHORT_IO_API_KEY Space secret. Use the original link."
    if not short_domain():
        return "Short links need a valid SHORT_IO_DOMAIN hostname. Use the original link."
    return None


def origin():
    base = os.environ.get("CSS_BASE_URL", "").rstrip("/")
    try:
        p = urlsplit(base)
        host = p.hostname or ""
        if (p.scheme != "https" or not host or p.username or p.password or
                p.port not in (None, 443) or p.path or p.query or p.fragment or
                "." not in host or host.endswith((".localhost", ".local", ".test", ".invalid"))):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            pass
        return base
    except ValueError:
        return ""


def eligible(url):
    base = origin()
    if not base or not isinstance(url, str) or len(url) > 5000:
        return False
    try:
        p = urlsplit(url)
    except ValueError:
        return False
    if f"{p.scheme}://{p.netloc}" != base or p.fragment:
        return False
    if re.fullmatch(r"/(e|r)/" + TOKEN, p.path):
        return not p.query
    if p.path == "/seq":
        q = parse_qs(p.query, keep_blank_values=True)
        return (set(q) == {"tokens"} and len(q["tokens"]) == 1 and
                bool(re.fullmatch(TOKEN + r"(?:," + TOKEN + r")*", q["tokens"][0])))
    return False


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS short_links (
            original_url TEXT PRIMARY KEY,
            short_url TEXT,
            provider TEXT NOT NULL DEFAULT 'short.io',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt REAL NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS short_link_rate (
            id INTEGER PRIMARY KEY CHECK(id=1), next_call REAL NOT NULL
        );
        INSERT OR IGNORE INTO short_link_rate VALUES(1,0);
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(short_links)")}
    if "requested" not in columns:
        conn.execute("ALTER TABLE short_links ADD COLUMN requested INTEGER NOT NULL DEFAULT 0")
    # Preserve completed mappings. Move only unsuccessful legacy jobs to Short.io.
    migrated = conn.execute("UPDATE short_links SET provider='short.io',status='pending',attempts=0,"
                            "next_attempt=0,last_error=NULL,updated_at=? "
                            "WHERE provider='is.gd' AND short_url IS NULL", (time.time(),)).rowcount
    if migrated:
        conn.execute("UPDATE short_link_rate SET next_call=0 WHERE id=1")
    conn.commit()


def enqueue(conn, url):
    """Explicit request; preserve active retries and completed mappings."""
    if enabled() and eligible(url):
        now = time.time()
        conn.execute("INSERT OR IGNORE INTO short_links(original_url,created_at,updated_at,provider,requested) VALUES(?,?,?,'short.io',1)",
                     (url, now, now))
        conn.execute("UPDATE short_links SET requested=1,provider='short.io',status='pending',"
                     "attempts=0,next_attempt=0,last_error=NULL WHERE original_url=? "
                     "AND short_url IS NULL AND (requested=0 OR status='failed')", (url,))


def lookup(conn, url):
    if not enabled() or not eligible(url):
        return url
    row = conn.execute("SELECT short_url FROM short_links WHERE original_url=? AND status='ready'",
                       (url,)).fetchone()
    return row[0] if row else url


def status(conn, url, *, now=None):
    """Safe display status: never expose raw upstream responses or destination tokens."""
    if not enabled():
        return {"done": True, "state": "disabled", "message": "Short links are not enabled. Use the original link."}
    if not eligible(url):
        return {"done": True, "state": "ineligible", "message": "A short link is not available for this address. Use the original link."}
    row = conn.execute("SELECT status,short_url,last_error,next_attempt,requested FROM short_links WHERE original_url=?",
                       (url,)).fetchone()
    if not row or (not row[4] and row[0] != "ready"):
        return {"done": True, "state": "missing", "message": "Create a short link only when you need one. Each new link uses your Short.io allowance."}
    state, short, error, retry_at, requested = row
    result = {"done": state in ("ready", "failed"), "state": state}
    if state == "ready":
        result.update(url=short, message="Short link ready.")
    elif configuration_error():
        result.update(done=True, state="configuration", message=configuration_error())
    elif state == "failed":
        result["message"] = "This link could not be shortened. Use the original link."
    elif error:
        result["state"] = "retrying"
        result["message"] = {
            "Rate limited": "The short-link service has reached its request limit. Use the original link while we wait to retry.",
            "Provider credentials rejected": "Short.io rejected the API key or domain access. Check the Space secret and domain permissions.",
            "Provider quota reached": "Short.io reports a plan or quota restriction. Check the Short.io account; use the original link meanwhile.",
        }.get(error, "The short-link service is unavailable. Use the original link while we retry automatically.")
        rate = conn.execute("SELECT next_call FROM short_link_rate WHERE id=1").fetchone()
        result["retry_after_seconds"] = max(0, int(max(retry_at, rate[0] if rate else 0) -
                                                  (time.time() if now is None else now)))
    else:
        result["message"] = "Preparing a short link. You can use the original link now."
    return result


def _connect(db):
    conn = sqlite3.connect(db, timeout=5)
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def share(db, url):
    """No network in page rendering. Fail open even if the database is busy."""
    if not enabled() or not eligible(url):
        return url
    try:
        conn = _connect(db)
        try:
            result = lookup(conn, url)
            conn.commit()
            return result
        finally:
            conn.close()
    except sqlite3.Error:
        log.warning("Short-link cache unavailable; using original link")
        return url


def process_one(db, *, now=None, post=None):
    """Claim with a lease and global rate slot, release DB lock before HTTP."""
    if not enabled() or not origin() or configuration_error():
        return False
    now = time.time() if now is None else now
    conn = _connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        next_call = conn.execute("SELECT next_call FROM short_link_rate WHERE id=1").fetchone()[0]
        row = conn.execute("SELECT original_url,attempts FROM short_links WHERE "
                           "requested=1 AND provider='short.io' AND status IN ('pending','processing') AND next_attempt<=? "
                           "ORDER BY created_at LIMIT 1", (now,)).fetchone()
        if now < next_call or not row:
            conn.rollback()
            return False
        url, attempts = row
        if not eligible(url):
            conn.execute("UPDATE short_links SET status='failed',last_error='Destination no longer eligible' "
                         "WHERE original_url=?", (url,))
            conn.commit()
            return False
        conn.execute("UPDATE short_link_rate SET next_call=? WHERE id=1", (now + INTERVAL,))
        conn.execute("UPDATE short_links SET status='processing',attempts=attempts+1,next_attempt=?,"
                     "updated_at=? WHERE original_url=?", (now + 60, now, url))
        conn.commit()
        short, error, status, delay = None, None, "pending", min(86400, 60 * 2 ** min(attempts, 10))
        try:
            response = (post or httpx.post)(
                "https://api.short.io/links",
                headers={"Authorization": os.environ["SHORT_IO_API_KEY"].strip()},
                json={"domain": short_domain(), "originalURL": url, "allowDuplicates": False},
                timeout=8, follow_redirects=False)
            if response.status_code == 429:
                error = "Rate limited"
                try:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                except ValueError:
                    retry_after = 60
                delay = max(delay, min(86400, max(60, retry_after)))
            elif response.status_code in (401, 403):
                error, delay = "Provider credentials rejected", 3600
            elif response.status_code == 402:
                error, delay = "Provider quota reached", 3600
            elif response.status_code in (400, 404, 409, 422):
                error, status = "Provider rejected destination or domain", "failed"
            else:
                response.raise_for_status()
                data = response.json()
                candidate = data.get("secureShortURL", "")
                parsed = urlsplit(candidate)
                if (parsed.scheme != "https" or parsed.netloc != short_domain() or
                        not re.fullmatch(r"/[A-Za-z0-9_-]+", parsed.path) or parsed.query or parsed.fragment):
                    raise ValueError("Invalid short URL")
                short, status = candidate, "ready"
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            # Never persist/log raw responses or exceptions that may contain credentials.
            error = "Shortening request failed"
        conn.execute("UPDATE short_links SET short_url=?,status=?,next_attempt=?,updated_at=?,last_error=? "
                     "WHERE original_url=?", (short, status, now + delay, now, error, url))
        if error in ("Rate limited", "Provider credentials rejected", "Provider quota reached"):
            conn.execute("UPDATE short_link_rate SET next_call=MAX(next_call,?) WHERE id=1", (now + delay,))
        conn.commit()
        return True
    finally:
        conn.close()


async def worker(db):
    while True:
        pending = asyncio.create_task(asyncio.to_thread(process_one, db))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            # Finish the bounded HTTP request before shutdown takes its DB snapshot.
            await pending
            raise
        except Exception:
            log.exception("Short-link worker will retry")
        await asyncio.sleep(5)
