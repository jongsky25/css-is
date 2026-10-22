"""Run a bounded change-feed to HTTPS adapter on an integration owner's runner.

No Office Connect host worker, new authority, or upstream write is installed.
Run collect, then deliver on a schedule; inspect status and explicitly replay
failed/blocked deliveries after fixing their cause. See docs/INTEGRATION_WEBHOOKS.md.
"""
import argparse
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import hashlib
from http.client import HTTPException
import json
import os
import re
import secrets
import sqlite3
import stat
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

if __package__:
    from .read_api import ApiFailure, NoRedirect, ReadClient
    from .webhook_receiver import Receiver, canonical, validate_notice
else:
    from read_api import ApiFailure, NoRedirect, ReadClient
    from webhook_receiver import Receiver, canonical, validate_notice


MAX_ATTEMPTS = 8
MAX_AGE = 3 * 86400
LEASE_SECONDS = 120
MAX_PENDING = 1000


def private_file(path, *, create=False):
    """Refuse links/nonregular/shared files; new files are owner-only."""
    flags = os.O_RDWR if create else os.O_RDONLY
    flags |= getattr(os, 'O_NOFOLLOW', 0)
    if create:
        flags |= os.O_CREAT
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or (os.name == 'posix' and info.st_mode & 0o077):
            raise ValueError('Use an owner-only regular file in a private directory.')
        if not create:
            with os.fdopen(fd, 'rb', closefd=False) as source:
                value = source.read(16385)
            if len(value) > 16384:
                raise ValueError('The private configuration file is too large.')
            return value.decode('utf-8').strip()
    finally:
        os.close(fd)


def retry_delay(attempt, retry_after, now):
    delay = min(3600, 5 * 2 ** min(attempt - 1, 10))
    if retry_after:
        try:
            requested = int(retry_after)
        except (ValueError, TypeError):
            try:
                requested = parsedate_to_datetime(retry_after).timestamp() - now
            except (ValueError, TypeError, OverflowError):
                requested = 0
        delay = max(delay, min(3600, max(0, requested)))
    return delay


class Adapter:
    def __init__(self, client, path, resource, receiver, *, clock=None):
        if (client.credential is None or resource not in ('documents', 'work-items')
                or not 0 < client.timeout <= 30):
            raise ValueError('Use a delegated read client, supported family and bounded timeout.')
        self.client, self.path, self.resource, self.receiver = client, str(path), resource, receiver
        self.clock = clock or time.time
        # Binding contains only public identity and hashes, never either secret.
        self.binding = hashlib.sha256(canonical([client.base_url, client.credential[8:40], resource,
            receiver.url, receiver.key_id, hashlib.sha256(bytes.fromhex(receiver.secret)).hexdigest()])).hexdigest()
        self.opener = build_opener(NoRedirect())  # Retains the runner's proxy and CA policy.
        private_file(self.path, create=True)
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS webhook_state(singleton INTEGER PRIMARY KEY CHECK(singleton=1), binding TEXT NOT NULL, cursor TEXT NOT NULL)')
            conn.execute('''CREATE TABLE IF NOT EXISTS webhook_delivery(
                id TEXT PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, body BLOB NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('pending','in_flight','accepted','failed','blocked')),
                attempts INTEGER NOT NULL DEFAULT 0, cycle_attempts INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL, cycle_started REAL NOT NULL, due REAL NOT NULL,
                lease_until REAL, claim TEXT, outcome TEXT, http_status INTEGER)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS webhook_attempt(
                delivery_id TEXT NOT NULL, number INTEGER NOT NULL, claim TEXT NOT NULL,
                started_at REAL NOT NULL, finished_at REAL, outcome TEXT NOT NULL,
                http_status INTEGER, PRIMARY KEY(delivery_id,number))''')
            conn.execute('''CREATE TABLE IF NOT EXISTS webhook_replay(
                id INTEGER PRIMARY KEY, delivery_id TEXT NOT NULL, requested_at REAL NOT NULL)''')
            saved = conn.execute('SELECT binding FROM webhook_state WHERE singleton=1').fetchone()
            if saved and saved['binding'] != self.binding:
                raise ValueError('Use a separate state file for this source, credential, family and receiver/key.')
            conn.execute('INSERT OR IGNORE INTO webhook_state VALUES(1,?,?)', (self.binding, ''))

    @contextmanager
    def database(self):
        conn = sqlite3.connect(self.path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def collect(self, limit=25):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Use a page size from 1 to 100.')
        with self.database() as conn:
            old = conn.execute('SELECT cursor FROM webhook_state WHERE singleton=1').fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM webhook_delivery WHERE status IN ('pending','in_flight')").fetchone()[0]
        if pending >= MAX_PENDING:
            return {'received': 0, 'backpressure': True}
        page = self.client.changes(self.resource, cursor=old, limit=min(limit, MAX_PENDING - pending))
        prepared = []
        now = self.clock()
        for event in page['data']:
            validate_notice(event)
            if (event['type'] == 'document.changed') != (self.resource == 'documents'):
                raise ValueError('The feed returned a different resource family.')
            # Identity survives runner restart, explicit replay and key/credential
            # rotation for this same site and destination. Secrets are not IDs.
            delivery_id = hashlib.sha256(canonical([self.client.base_url, self.receiver.url, event['id']])).hexdigest()
            body = canonical({'schema_version': '1', 'delivery_id': delivery_id, 'event': event})
            prepared.append((delivery_id, event['id'], body))
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            saved = conn.execute('SELECT cursor FROM webhook_state WHERE singleton=1').fetchone()[0]
            if saved != old:
                return {'received': 0, 'concurrent_poll': True}
            for delivery_id, event_id, body in prepared:
                prior = conn.execute('SELECT body FROM webhook_delivery WHERE event_id=?', (event_id,)).fetchone()
                if prior and prior['body'] != body:
                    raise ValueError('A notice ID was reused with different content.')
                conn.execute('''INSERT OR IGNORE INTO webhook_delivery
                    (id,event_id,body,status,created_at,cycle_started,due) VALUES(?,?,?,'pending',?,?,?)''',
                    (delivery_id, event_id, body, now, now, now))
            conn.execute('UPDATE webhook_state SET cursor=? WHERE singleton=1', (page['next_cursor'],))
        return {'received': len(prepared), 'initialized': page['initialized'], 'has_more': page['has_more']}

    def claim(self):
        now = self.clock()
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            # A crashed sender may already have reached the receiver. Its stable
            # delivery ID and the receiver's durable receipt make retry safe.
            expired = conn.execute("SELECT id,attempts,claim FROM webhook_delivery WHERE status='in_flight' AND lease_until<=?", (now,)).fetchall()
            for row in expired:
                conn.execute("UPDATE webhook_attempt SET outcome='unknown_after_lease',finished_at=? WHERE delivery_id=? AND number=? AND claim=?", (now, row['id'], row['attempts'], row['claim']))
            conn.execute("UPDATE webhook_delivery SET status='pending',claim=NULL,lease_until=NULL,outcome='unknown_after_lease' WHERE status='in_flight' AND lease_until<=?", (now,))
            conn.execute("UPDATE webhook_delivery SET status='failed',outcome='retry_budget_exhausted' WHERE status='pending' AND (cycle_attempts>=? OR cycle_started<?)", (MAX_ATTEMPTS, now - MAX_AGE))
            row = conn.execute("SELECT * FROM webhook_delivery WHERE status='pending' AND due<=? ORDER BY created_at,id LIMIT 1", (now,)).fetchone()
            if row is None:
                return None
            nonce = secrets.token_hex(16)
            conn.execute("UPDATE webhook_delivery SET status='in_flight',attempts=attempts+1,cycle_attempts=cycle_attempts+1,claim=?,lease_until=? WHERE id=?", (nonce, now + LEASE_SECONDS, row['id']))
            conn.execute("INSERT INTO webhook_attempt VALUES(?,?,?,?,NULL,'in_flight',NULL)", (row['id'], row['attempts'] + 1, nonce, now))
            return dict(conn.execute('SELECT * FROM webhook_delivery WHERE id=?', (row['id'],)).fetchone())

    def finish(self, row, status, outcome, *, http_status=None, retry_after=None):
        now = self.clock()
        if status == 'pending' and (row['cycle_attempts'] >= MAX_ATTEMPTS or now - row['cycle_started'] >= MAX_AGE):
            status = 'failed'
        due = now + retry_delay(row['cycle_attempts'], retry_after, now) if status == 'pending' else now
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            changed = conn.execute('''UPDATE webhook_delivery SET status=?,outcome=?,http_status=?,due=?,claim=NULL,lease_until=NULL
                WHERE id=? AND status='in_flight' AND claim=? AND lease_until>?''',
                (status, outcome, http_status, due, row['id'], row['claim'], now)).rowcount
            if changed:
                conn.execute('''UPDATE webhook_attempt SET finished_at=?,outcome=?,http_status=?
                    WHERE delivery_id=? AND number=? AND claim=?''',
                    (now, outcome, http_status, row['id'], row['attempts'], row['claim']))
        return bool(changed)

    def deliver_one(self):
        row = self.claim()
        if row is None:
            return False
        event = json.loads(row['body'])['event']
        try:
            current = self.client.get(event['resource_url'])
        except ApiFailure as exc:
            terminal = exc.status in (400, 401, 403, 404, 410)
            self.finish(row, 'blocked' if terminal else 'pending',
                        'source_unavailable' if terminal else 'source_retry', http_status=exc.status)
            # Stop this invocation on authentication/scope failures. Never send
            # a cached payload just because an earlier poll could read it.
            if exc.status in (401, 403):
                raise ApiFailure('Source access is unavailable; delivery stopped.', status=exc.status) from None
            return True
        if (not isinstance(current, dict) or current.get('id') != event['resource_id']
                or type(current.get('revision')) is not int or current['revision'] < event['revision']
                or (event['type'] == 'task.changed' and current.get('work_item_id') != event['work_item_id'])):
            self.finish(row, 'blocked', 'source_identity_or_revision_changed')
            return True
        # Recheck the lease after source I/O and before starting an outbound call.
        # Network calls occur outside SQLite writer transactions.
        with self.database() as conn:
            active = conn.execute("SELECT 1 FROM webhook_delivery WHERE id=? AND status='in_flight' AND claim=? AND lease_until>?",
                                  (row['id'], row['claim'], self.clock() + 20)).fetchone()
        if not active:
            return True
        request = Request(self.receiver.url, data=row['body'], method='POST',
                          headers=self.receiver.headers(row['body'], self.clock()))
        try:
            with self.opener.open(request, timeout=15) as response:
                code, retry_after = response.status, response.headers.get('Retry-After')
                # Neither the body nor arbitrary headers enter the local log.
        except HTTPError as exc:
            code, retry_after = exc.code, exc.headers.get('Retry-After')
            exc.close()
        except (URLError, OSError, TimeoutError, HTTPException):
            self.finish(row, 'pending', 'transport_unknown')
            return True
        if 200 <= code < 300:
            self.finish(row, 'accepted', 'http_accepted', http_status=code)
        else:
            retry = code in (408, 425, 429) or 500 <= code < 600
            self.finish(row, 'pending' if retry else 'failed', 'receiver_http', http_status=code, retry_after=retry_after)
        return True

    def deliver(self, limit=25):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError('Use a delivery limit from 1 to 100.')
        count = 0
        while count < limit and self.deliver_one():
            count += 1
        return {'attempted': count}

    def replay(self, delivery_id):
        now = self.clock()
        with self.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            changed = conn.execute("""UPDATE webhook_delivery SET status='pending',cycle_attempts=0,cycle_started=?,due=?,outcome='operator_replay'
                WHERE id=? AND status IN ('failed','blocked')""", (now, now, delivery_id)).rowcount
            if not changed:
                raise ValueError('Replay requires one failed or blocked delivery ID.')
            conn.execute('INSERT INTO webhook_replay(delivery_id,requested_at) VALUES(?,?)', (delivery_id, now))
        return {'replayed': delivery_id}

    def status(self):
        with self.database() as conn:
            counts = dict(conn.execute('SELECT status,COUNT(*) FROM webhook_delivery GROUP BY status').fetchall())
            rows = conn.execute('''SELECT id,event_id,status,attempts,outcome,http_status,due FROM webhook_delivery
                WHERE status!='accepted' ORDER BY created_at,id LIMIT 100''').fetchall()
        return {'counts': counts, 'outstanding': [dict(row) for row in rows]}

    def history(self, delivery_id):
        if not isinstance(delivery_id, str) or not re.fullmatch(r'[0-9a-f]{64}', delivery_id):
            raise ValueError('Choose a saved delivery ID.')
        with self.database() as conn:
            row = conn.execute('SELECT id,event_id,status,attempts,outcome,http_status FROM webhook_delivery WHERE id=?', (delivery_id,)).fetchone()
            if row is None:
                raise ValueError('Choose a saved delivery ID.')
            attempts = conn.execute('SELECT number,started_at,finished_at,outcome,http_status FROM webhook_attempt WHERE delivery_id=? ORDER BY number', (delivery_id,)).fetchall()
            replays = conn.execute('SELECT requested_at FROM webhook_replay WHERE delivery_id=? ORDER BY id', (delivery_id,)).fetchall()
        return {'delivery': dict(row), 'attempts': [dict(x) for x in attempts], 'replays': [x[0] for x in replays]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('collect', 'deliver', 'status', 'history', 'replay'))
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--credential-file', required=True)
    parser.add_argument('--receiver-file', required=True, help='Private JSON: url, key_id, secret (64 hex characters)')
    parser.add_argument('--state', required=True, help='Private local SQLite delivery history')
    parser.add_argument('--resource', required=True, choices=('documents', 'work-items'))
    parser.add_argument('--limit', type=int, default=25)
    parser.add_argument('--delivery-id')
    parser.add_argument('--allow-loopback-http', action='store_true', help='Local synthetic receiver tests only')
    args = parser.parse_args()
    try:
        config = json.loads(private_file(args.receiver_file))
        if not isinstance(config, dict) or set(config) != {'url', 'key_id', 'secret'}:
            raise ValueError
        receiver = Receiver(**config, allow_loopback_http=args.allow_loopback_http)
        client = ReadClient(args.base_url, credential=private_file(args.credential_file))
        adapter = Adapter(client, args.state, args.resource, receiver)
        if args.command in ('collect', 'deliver'):
            result = getattr(adapter, args.command)(args.limit)
        elif args.command in ('replay', 'history'):
            result = getattr(adapter, args.command)(args.delivery_id)
        else:
            result = adapter.status()
        print(json.dumps(result))
    except (ApiFailure, ValueError, TypeError, UnicodeError, OSError, sqlite3.Error):
        parser.exit(1, 'Adapter stopped. Keep the state file; check private configuration, source access and recovery guidance.\n')


if __name__ == '__main__':
    main()
