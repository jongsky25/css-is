"""Versioned webhook verification and atomic local receipts; standard library only.

An HTTP receiver must bound its request body, reject duplicate signing headers,
and call accept() before returning 2xx. Its apply callback must use the supplied
SQLite transaction; remote side effects need their own idempotency contract.
"""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def validate_notice(notice):
    fields = {'id', 'schema_version', 'type', 'resource_id', 'work_item_id',
              'revision', 'recorded_at', 'resource_url'}
    if not isinstance(notice, dict) or set(notice) != fields:
        raise ValueError('Invalid change notice.')
    def identifier(value):
        return (isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,18}', value)
                and int(value) <= 9223372036854775807)
    kind, rid, parent = notice['type'], notice['resource_id'], notice['work_item_id']
    if (notice['schema_version'] != '1' or not isinstance(notice['id'], str)
            or not re.fullmatch(r'[0-9a-f]{32}', notice['id']) or not identifier(rid)
            or type(notice['revision']) is not int or not 1 <= notice['revision'] < 9223372036854775807):
        raise ValueError('Invalid change notice.')
    if kind == 'document.changed' and parent is None:
        target = f'/api/v1/documents/{rid}'
    elif kind == 'work_item.changed' and parent == rid:
        target = f'/api/v1/work-items/{rid}'
    elif kind == 'task.changed' and identifier(parent):
        target = f'/api/v1/work-items/{parent}/tasks/{rid}'
    else:
        raise ValueError('Invalid change notice.')
    stamp = notice['recorded_at']
    try:
        valid_stamp = isinstance(stamp, str) and len(stamp) <= 64 and datetime.fromisoformat(stamp).utcoffset() is not None
    except ValueError:
        valid_stamp = False
    if not valid_stamp or notice['resource_url'] != target:
        raise ValueError('Invalid change notice.')
    return notice


def signing_key(key_id, secret):
    if (not isinstance(key_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', key_id)
            or not isinstance(secret, str) or not re.fullmatch(r'[0-9a-f]{64}', secret)):
        raise ValueError('Use a key ID and a random 32-byte hexadecimal signing secret.')
    return bytes.fromhex(secret)


@dataclass(frozen=True)
class Receiver:
    url: str
    key_id: str
    secret: str = field(repr=False)
    allow_loopback_http: bool = False

    def __post_init__(self):
        signing_key(self.key_id, self.secret)
        if not isinstance(self.url, str):
            raise ValueError('Use a fixed HTTPS receiver URL.')
        parsed = urlsplit(self.url)
        local = self.allow_loopback_http and parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')
        if (len(self.url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in self.url)
                or '\\' in self.url or not parsed.hostname or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or (parsed.scheme != 'https' and not local)):
            raise ValueError('Use a fixed HTTPS receiver URL without user information, query or fragment.')
        parsed.port  # Reject malformed ports before opening a connection.

    def headers(self, body, now=None):
        stamp = str(int(time.time() if now is None else now))
        digest = hmac.new(signing_key(self.key_id, self.secret),
                          b'v1.' + self.key_id.encode() + b'.' + stamp.encode() + b'.' + body,
                          hashlib.sha256).hexdigest()
        return {'Content-Type': 'application/json', 'X-OfficeConnect-Key-Id': self.key_id,
                'X-OfficeConnect-Timestamp': stamp, 'X-OfficeConnect-Signature': 'v1=' + digest}


def verify(body, headers, *, key_id, secret, now=None):
    """Authenticate exact bytes and a timestamp within five minutes; no receipt yet."""
    key = signing_key(key_id, secret)
    names = ('X-OfficeConnect-Key-Id', 'X-OfficeConnect-Timestamp', 'X-OfficeConnect-Signature')
    if hasattr(headers, 'get_all') and any(len(headers.get_all(name, [])) != 1 for name in names):
        raise ValueError('Invalid webhook authentication.')
    lowered = {k.lower(): v for k, v in headers.items()}
    if any(sum(k.lower() == name.lower() for k in headers) != 1 for name in names):
        raise ValueError('Invalid webhook authentication.')
    kid, stamp, signature = (lowered.get(name.lower(), '') for name in names)
    if (not isinstance(body, bytes) or len(body) > 16384 or kid != key_id
            or not all(isinstance(v, str) for v in (kid, stamp, signature))
            or not re.fullmatch(r'[0-9]{1,12}', stamp) or not re.fullmatch(r'v1=[0-9a-f]{64}', signature)
            or abs((time.time() if now is None else now) - int(stamp)) > 300):
        raise ValueError('Invalid webhook authentication.')
    expected = hmac.new(key, b'v1.' + kid.encode() + b'.' + stamp.encode() + b'.' + body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature[3:], expected):
        raise ValueError('Invalid webhook authentication.')
    try:
        value = json.loads(body)
        if (set(value) != {'schema_version', 'delivery_id', 'event'} or value['schema_version'] != '1'
                or not re.fullmatch(r'[0-9a-f]{64}', value['delivery_id'])):
            raise ValueError
        validate_notice(value['event'])
        if canonical(value) != body:
            raise ValueError
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError('Invalid webhook envelope.') from None
    return value


def accept(conn, body, headers, *, key_id, secret, apply, now=None):
    """Commit one local effect and receipt together; return False for a duplicate.

    Use a dedicated, private, durable SQLite connection. apply(conn, event) may
    write local rows but must not commit, start another transaction, or call a
    remote service. A lost HTTP response can then be retried harmlessly.
    """
    value = verify(body, headers, key_id=key_id, secret=secret, now=now)
    if conn.in_transaction:
        raise ValueError('The receiver requires its own transaction.')
    digest = hashlib.sha256(body).hexdigest()
    conn.execute('BEGIN IMMEDIATE')
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS webhook_receipt(delivery_id TEXT PRIMARY KEY, digest TEXT NOT NULL, received_at REAL NOT NULL)')
        old = conn.execute('SELECT digest FROM webhook_receipt WHERE delivery_id=?', (value['delivery_id'],)).fetchone()
        if old:
            if old[0] != digest:
                raise ValueError('A delivery ID was reused with different content.')
            conn.commit()
            return False
        apply(conn, value['event'])
        conn.execute('INSERT INTO webhook_receipt VALUES(?,?,?)',
                     (value['delivery_id'], digest, time.time() if now is None else now))
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise
