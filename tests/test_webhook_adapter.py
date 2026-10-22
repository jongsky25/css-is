"""A21 independent delivery: real local HTTP, durable recovery and current access."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sqlite3
import time
from threading import Barrier, Thread

import pytest

from examples.read_api import ApiFailure, ReadClient
from examples.webhook_adapter import Adapter, MAX_ATTEMPTS, LEASE_SECONDS, private_file, retry_delay
from examples.webhook_receiver import Receiver, accept, canonical, validate_notice, verify
from tests.test_integration_access import connected, api, workspace, mint, tool
from tests.test_work import case, document
import auth
import documents as docs
import integration_access as access


SECRET = 'ab' * 32
TOKEN = 'oc_read_' + 'a' * 32 + '.' + 'b' * 64


def notice(identifier='1' * 32, **overrides):
    return dict(dict(id=identifier, schema_version='1', type='work_item.changed',
                resource_id='1', work_item_id='1', revision=1,
                recorded_at='2026-10-22T00:00:00+00:00',
                resource_url='/api/v1/work-items/1'), **overrides)


def fake_client(events=None):
    client = ReadClient('http://localhost/api/v1', credential=TOKEN)
    client.changes = lambda resource, **kw: dict(data=events or [], next_cursor='c' * 64, initialized=False, has_more=False)
    client.get = lambda path: {'id': '1', 'revision': 1, 'work_item_id': '1'}
    return client


@contextmanager
def receiver_server(tmp_path, codes=None, headers=None):
    path = str(tmp_path / 'receiver.sqlite')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE effect(event_id TEXT PRIMARY KEY)'); conn.commit(); conn.close()
    requests, responses = [], list(codes or [204])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            requests.append((self.path, body, dict(self.headers)))
            with sqlite3.connect(path) as db:
                accept(db, body, self.headers, key_id='local-test', secret=SECRET,
                       apply=lambda c, event: c.execute('INSERT INTO effect VALUES(?)', (event['id'],)))
            code = responses.pop(0) if responses else 204
            if code is None:
                self.close_connection = True
                return  # Receiver committed, but the HTTP response is lost.
            self.send_response(code)
            for key, value in (headers or {}).items(): self.send_header(key, value)
            self.end_headers()
        def do_GET(self):
            requests.append((self.path, b'', dict(self.headers)))
            self.send_response(200); self.end_headers()
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    try:
        yield Receiver(f'http://127.0.0.1:{server.server_port}/hook', 'local-test', SECRET, True), requests, path
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)


@contextmanager
def source_server(connected, owner=0):
    from starlette.testclient import TestClient
    bridge = TestClient(connected[-1].app, raise_server_exceptions=False)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            response = bridge.get(base + self.path, headers={'Authorization': self.headers.get('Authorization', '')}, follow_redirects=False)
            self.send_response(response.status_code)
            self.send_header('Content-Type', response.headers.get('Content-Type', ''))
            self.send_header('Content-Length', str(len(response.content)))
            self.end_headers(); self.wfile.write(response.content)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    base = f'http://127.0.0.1:{server.server_port}'
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True); thread.start()
    token = mint(connected, owner=owner, audience=json.dumps(['http', '127.0.0.1', server.server_port, '/api/v1'], separators=(',', ':')))
    try:
        yield ReadClient(base + '/api/v1', credential=token), token
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); bridge.close()


@pytest.mark.parametrize('first_code', [502, None])
def test_real_http_lost_response_durable_restart_and_receiver_dedup(tmp_path, first_code):
    now = [time.time()]
    with receiver_server(tmp_path, [first_code, 204]) as (receiver, requests, receipt_path):
        path = tmp_path / 'sender.sqlite'
        client = fake_client([notice()])
        sender = Adapter(client, path, 'work-items', receiver, clock=lambda: now[0])
        sender.collect()
        assert sender.deliver() == {'attempted': 1}
        row = sender.status()['outstanding'][0]
        assert row['status'] == 'pending' and row['http_status'] == first_code
        assert sender.deliver() == {'attempted': 0}
        now[0] += 6
        resumed = Adapter(client, path, 'work-items', receiver, clock=lambda: now[0])
        resumed.deliver()
        assert resumed.status()['counts'] == {'accepted': 1}
        assert len(requests) == 2 and requests[0][1] == requests[1][1]
        assert requests[0][2]['X-Officeconnect-Timestamp'] != requests[1][2]['X-Officeconnect-Timestamp']
        assert all(not any(k.lower() in ('cookie', 'authorization') for k in request[2]) for request in requests)
        history = resumed.history(row['id'])
        assert [x['http_status'] for x in history['attempts']] == [first_code, 204]
        with sqlite3.connect(receipt_path) as conn:
            assert conn.execute('SELECT COUNT(*) FROM effect').fetchone()[0] == 1
            assert conn.execute('SELECT COUNT(*) FROM webhook_receipt').fetchone()[0] == 1


def test_signatures_freshness_canonical_payload_and_atomic_receipts(tmp_path):
    receiver = Receiver('https://hooks.example/office', 'test', SECRET)
    body = canonical({'schema_version': '1', 'delivery_id': 'd' * 64, 'event': notice()})
    headers = receiver.headers(body, 1000)
    assert verify(body, headers, key_id='test', secret=SECRET, now=1000)['event'] == notice()
    for bad_body, bad_headers, stamp in (
            (body + b' ', headers, 1000), (body, headers, 1301), (body, headers, 699),
            (body, {**headers, 'X-OfficeConnect-Key-Id': 'other'}, 1000),
            (body, {**headers, 'X-OfficeConnect-Signature': 'v1=' + '0' * 64}, 1000),
            (body, {**headers, 'x-officeconnect-key-id': 'test'}, 1000)):
        with pytest.raises(ValueError): verify(bad_body, bad_headers, key_id='test', secret=SECRET, now=stamp)
    conn = sqlite3.connect(tmp_path / 'receipts.sqlite')
    conn.execute('CREATE TABLE effect(value TEXT)'); conn.commit()
    def fail(c, event):
        c.execute('INSERT INTO effect VALUES(?)', (event['id'],))
        raise RuntimeError('Local transaction failed')
    with pytest.raises(RuntimeError): accept(conn, body, headers, key_id='test', secret=SECRET, apply=fail, now=1000)
    assert not conn.execute('SELECT * FROM effect').fetchall()
    apply = lambda c, event: c.execute('INSERT INTO effect VALUES(?)', (event['id'],))
    assert accept(conn, body, headers, key_id='test', secret=SECRET, apply=apply, now=1000)
    assert not accept(conn, body, receiver.headers(body, 1001), key_id='test', secret=SECRET, apply=apply, now=1001)
    assert conn.execute('SELECT COUNT(*) FROM effect').fetchone()[0] == 1
    changed = json.loads(body); changed['event']['revision'] = 2; changed = canonical(changed)
    with pytest.raises(ValueError, match='different content'):
        accept(conn, changed, receiver.headers(changed, 1001), key_id='test', secret=SECRET, apply=apply, now=1001)
    conn.close()


@pytest.mark.parametrize('override', [
    {'resource_url': 'https://hostile.example/exfiltrate'}, {'resource_url': '/api/v1/write-context'},
    {'resource_id': '01'}, {'revision': True}, {'work_item_id': '2'},
    {'recorded_at': '2026-10-22T00:00:00'}, {'private_text': 'do not forward'},
])
def test_notice_validation_refuses_extra_fields_bad_identity_and_paths(override):
    event = notice(); event.update(override)
    with pytest.raises(ValueError): validate_notice(event)


@pytest.mark.parametrize('url', ['http://remote.example/hook', 'http://localhost/hook',
    'https://user:secret@hooks.example/hook', 'https://hooks.example/hook?token=secret',
    'https://hooks.example/hook#fragment', 'https://hooks.example/\nhook'])
def test_receiver_requires_safe_fixed_https_configuration(url):
    with pytest.raises(ValueError): Receiver(url, 'test', SECRET)


def test_collection_rolls_back_checkpoint_and_deduplicates(tmp_path):
    receiver = Receiver('https://hooks.example/hook', 'test', SECRET)
    client = fake_client()
    sender = Adapter(client, tmp_path / 'sender.sqlite', 'work-items', receiver)
    sender.collect()
    client.changes = lambda *a, **kw: dict(data=[notice()], next_cursor='e' * 64, initialized=False, has_more=False)
    with sender.database() as conn:
        conn.execute("CREATE TRIGGER fail_progress BEFORE UPDATE ON webhook_state BEGIN SELECT RAISE(ABORT,'full'); END")
    with pytest.raises(sqlite3.IntegrityError): sender.collect()
    assert sender.status()['counts'] == {}
    with sender.database() as conn:
        assert conn.execute('SELECT cursor FROM webhook_state').fetchone()[0] == 'c' * 64
        conn.execute('DROP TRIGGER fail_progress')
    sender.collect(); sender.collect()
    assert sender.status()['counts'] == {'pending': 1}
    client.changes = lambda *a, **kw: dict(data=[dict(notice(), revision=2)], next_cursor='f' * 64, initialized=False, has_more=False)
    with pytest.raises(ValueError, match='different content'): sender.collect()
    with sender.database() as conn:
        assert conn.execute('SELECT cursor FROM webhook_state').fetchone()[0] == 'e' * 64


def test_concurrent_claim_lease_recovery_nonce_and_explicit_replay(tmp_path):
    now = [1000.]
    receiver = Receiver('https://hooks.example/hook', 'test', SECRET)
    client = fake_client([notice()])
    path = tmp_path / 'sender.sqlite'
    sender = Adapter(client, path, 'work-items', receiver, clock=lambda: now[0]); sender.collect()
    def claim(_):
        return Adapter(client, path, 'work-items', receiver, clock=lambda: now[0]).claim()
    with ThreadPoolExecutor(max_workers=2) as pool: claims = list(pool.map(claim, range(2)))
    first = next(x for x in claims if x)
    assert sum(x is not None for x in claims) == 1
    with pytest.raises(ValueError): sender.replay(first['id'])
    now[0] += LEASE_SECONDS + 1
    second = sender.claim()
    assert second['id'] == first['id'] and second['claim'] != first['claim']
    assert not sender.finish(first, 'accepted', 'http_accepted')
    assert sender.finish(second, 'failed', 'receiver_http', http_status=400)
    sender.replay(first['id'])
    replay = sender.claim()
    assert replay['body'] == first['body'] and replay['cycle_attempts'] == 1
    sender.finish(replay, 'accepted', 'http_accepted', http_status=204)
    history = sender.history(first['id'])
    assert [x['outcome'] for x in history['attempts']] == ['unknown_after_lease', 'receiver_http', 'http_accepted']
    assert len(history['replays']) == 1 and history['delivery']['attempts'] == 3
    with pytest.raises(ValueError): sender.replay(first['id'])


def test_retry_budget_and_bounded_retry_after(tmp_path):
    now = [1000.]
    sender = Adapter(fake_client([notice()]), tmp_path / 'sender.sqlite', 'work-items',
                     Receiver('https://hooks.example/hook', 'test', SECRET), clock=lambda: now[0])
    sender.collect()
    for attempt in range(MAX_ATTEMPTS):
        row = sender.claim(); assert row['cycle_attempts'] == attempt + 1
        sender.finish(row, 'pending', 'transport_unknown')
        now[0] += 4000
    assert sender.claim() is None and sender.status()['counts'] == {'failed': 1}
    assert retry_delay(1, '99999999999999', 1000) == 3600
    assert retry_delay(1, '-3', 1000) == 5
    assert retry_delay(1, 'Thu, 01 Jan 1970 00:18:20 GMT', 1000) == 100
    assert retry_delay(1, 'private invalid value', 1000) == 5


def test_private_files_binding_and_secret_hygiene(tmp_path):
    path = tmp_path / 'sender.sqlite'
    receiver = Receiver('https://hooks.example/hook', 'test', SECRET)
    client = fake_client([notice()])
    sender = Adapter(client, path, 'work-items', receiver); sender.collect()
    assert path.stat().st_mode & 0o777 == 0o600
    assert TOKEN.encode() not in path.read_bytes() and SECRET.encode() not in path.read_bytes()
    for family, target in [('documents', receiver), ('work-items', Receiver('https://other.example/hook', 'test', SECRET)),
                           ('work-items', Receiver(receiver.url, 'rotated', 'cd' * 32))]:
        with pytest.raises(ValueError, match='separate state'): Adapter(client, path, family, target)
    shared = tmp_path / 'shared'; shared.write_text(TOKEN); shared.chmod(0o644)
    with pytest.raises(ValueError): private_file(shared)
    linked = tmp_path / 'linked'; linked.symlink_to(path)
    with pytest.raises(OSError): private_file(linked)


def test_real_api_to_http_receiver_revoked_credential_stops_retry(connected, tmp_path):
    c, users, unit, clients, app = connected
    now = [time.time()]
    with source_server(connected) as (source, token), receiver_server(tmp_path, [502]) as (target, requests, receipt_path):
        sender = Adapter(source, tmp_path / 'sender.sqlite', 'work-items', target, clock=lambda: now[0])
        assert sender.collect()['initialized']
        item = case(c, users[0], unit)
        assert sender.collect()['received'] == 1
        sender.deliver()
        delivery_id = sender.status()['outstanding'][0]['id']
        assert len(requests) == 1 and sender.status()['counts'] == {'pending': 1}
        access.revoke(c, auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME)), token[8:40])
        now[0] += 6
        with pytest.raises(ApiFailure) as denied: sender.deliver()
        assert denied.value.status == 401 and len(requests) == 1
        assert sender.status()['counts'] == {'blocked': 1}
        assert sender.history(delivery_id)['attempts'][-1]['outcome'] == 'source_unavailable'
        with pytest.raises(ApiFailure) as denied: sender.collect()
        assert denied.value.status == 401
        assert json.loads(requests[0][1])['event']['resource_id'] == str(item['id'])
        assert token not in repr(requests) and item['title'] not in requests[0][1].decode()


def test_real_api_current_document_restriction_blocks_already_queued_notices(connected, tmp_path):
    c, users, unit, clients, app = connected
    now = [time.time()]
    with source_server(connected, owner=3) as (source, token), receiver_server(tmp_path, [502]) as (target, requests, receipt_path):
        sender = Adapter(source, tmp_path / 'sender.sqlite', 'documents', target, clock=lambda: now[0])
        sender.collect()
        doc = document(c, users[0], unit, subject='Private prose must not be sent')
        doc = docs.mutate(c, users[1], doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Verify'})
        assert sender.collect()['received'] >= 1
        sender.deliver(limit=1)
        assert len(requests) == 1
        docs.mutate(c, users[1], doc['id'], doc['revision'], 'access', {'visibility': 'restricted', 'viewers': [users[1]['id']], 'reason': 'Restrict'})
        now[0] += 6
        sender.deliver()
        assert len(requests) == 1
        assert set(sender.status()['counts']) == {'blocked'}
        assert 'Private prose' not in requests[0][1].decode()


@pytest.mark.parametrize('status', [302, 307, 400, 401, 403, 404])
def test_receiver_redirects_and_other_terminal_errors_are_not_retried(tmp_path, status):
    with receiver_server(tmp_path, [status], {'Location': '/trap'}) as (target, requests, receipt_path):
        sender = Adapter(fake_client([notice()]), tmp_path / 'sender.sqlite', 'work-items', target)
        sender.collect(); sender.deliver(); sender.deliver()
        assert len(requests) == 1 and requests[0][0] == '/hook'
        assert sender.status()['counts'] == {'failed': 1}
        delivery_id = sender.status()['outstanding'][0]['id']
        sender.replay(delivery_id)
        sender.deliver()
        assert sender.status()['counts'] == {'accepted': 1}
        assert requests[0][1] == requests[1][1]
        with sqlite3.connect(receipt_path) as conn:
            assert conn.execute('SELECT COUNT(*) FROM effect').fetchone()[0] == 1


def test_receiver_retry_after_is_durable_and_respected(tmp_path):
    now = [time.time()]
    with receiver_server(tmp_path, [429, 204], {'Retry-After': '60'}) as (target, requests, receipt_path):
        sender = Adapter(fake_client([notice()]), tmp_path / 'sender.sqlite', 'work-items', target, clock=lambda: now[0])
        sender.collect(); sender.deliver()
        now[0] += 59
        assert sender.deliver()['attempted'] == 0
        now[0] += 2
        assert sender.deliver()['attempted'] == 1
        assert len(requests) == 2 and sender.status()['counts'] == {'accepted': 1}


@pytest.mark.parametrize('current', [{'id': '2', 'revision': 1}, {'id': '1', 'revision': 0}, {'id': '1', 'revision': True}])
def test_obsolete_alias_and_older_restored_resource_never_leave_runner(tmp_path, current):
    source = fake_client([notice()]); source.get = lambda path: current
    sender = Adapter(source, tmp_path / 'sender.sqlite', 'work-items', Receiver('https://hooks.example/hook', 'test', SECRET))
    # Fail loudly if a network request occurs; source revalidation must stop it.
    class NoNetwork:
        def open(self, *a, **kw): raise AssertionError('No outbound request permitted')
    sender.opener = NoNetwork()
    sender.collect(); sender.deliver()
    assert sender.status()['counts'] == {'blocked': 1}


def test_task_parent_revalidation_and_expired_lease_prevent_send(tmp_path):
    now = [time.time()]
    event = notice(type='task.changed', work_item_id='2', resource_url='/api/v1/work-items/2/tasks/1')
    source = fake_client([event])
    sender = Adapter(source, tmp_path / 'sender.sqlite', 'work-items', Receiver('https://hooks.example/hook', 'test', SECRET), clock=lambda: now[0])
    class NoNetwork:
        def open(self, *a, **kw): raise AssertionError('No outbound request permitted')
    sender.opener = NoNetwork()
    sender.collect(); sender.deliver()
    row = sender.status()['outstanding'][0]
    assert row['status'] == 'blocked'
    sender.replay(row['id'])
    def slow_current(path):
        now[0] += LEASE_SECONDS + 1
        return {'id': '1', 'work_item_id': '2', 'revision': 1}
    source.get = slow_current
    sender.deliver(limit=1)
    assert sender.status()['counts'] == {'in_flight': 1}
    recovered = sender.claim()
    assert recovered['attempts'] == 3


def test_concurrent_pollers_commit_one_checkpoint_and_one_notice(tmp_path):
    barrier = Barrier(2)
    source = fake_client([notice()])
    def page(*args, **kwargs):
        barrier.wait(timeout=5)
        return dict(data=[notice()], next_cursor='d' * 64, initialized=False, has_more=False)
    source.changes = page
    target = Receiver('https://hooks.example/hook', 'test', SECRET)
    path = tmp_path / 'sender.sqlite'
    senders = [Adapter(source, path, 'work-items', target) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda sender: sender.collect(), senders))
    assert sum(x['received'] for x in results) == 1
    assert sum(bool(x.get('concurrent_poll')) for x in results) == 1
    assert senders[0].status()['counts'] == {'pending': 1}


def test_concurrent_receiver_receipts_commit_the_effect_once(tmp_path):
    path = tmp_path / 'receiver.sqlite'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE effect(event_id TEXT PRIMARY KEY)')
    target = Receiver('https://hooks.example/hook', 'test', SECRET)
    body = canonical({'schema_version': '1', 'delivery_id': 'd' * 64, 'event': notice()})
    barrier = Barrier(2)
    def receive(_):
        with sqlite3.connect(path) as conn:
            barrier.wait(timeout=5)
            return accept(conn, body, target.headers(body, 1000), key_id='test', secret=SECRET, now=1000,
                          apply=lambda c, event: c.execute('INSERT INTO effect VALUES(?)', (event['id'],)))
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(receive, range(2)))
    assert sorted(results) == [False, True]
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM effect').fetchone()[0] == 1


def test_rotation_retains_same_delivery_identity_and_backpressure_stops_poll(tmp_path, monkeypatch):
    source = fake_client([notice()])
    target = Receiver('https://hooks.example/hook', 'test', SECRET)
    sender = Adapter(source, tmp_path / 'original.sqlite', 'work-items', target); sender.collect()
    original = sender.claim()
    replacement = fake_client([notice()])
    replacement.credential = 'oc_read_' + 'd' * 32 + '.' + 'e' * 64
    rotated = Adapter(replacement, tmp_path / 'rotated.sqlite', 'work-items', Receiver(target.url, 'rotated', 'cd' * 32))
    rotated.collect()
    assert rotated.claim()['body'] == original['body']
    monkeypatch.setattr('examples.webhook_adapter.MAX_PENDING', 1)
    source.changes = lambda *a, **kw: pytest.fail('A full queue must stop collection before an API call')
    assert sender.collect() == {'received': 0, 'backpressure': True}
