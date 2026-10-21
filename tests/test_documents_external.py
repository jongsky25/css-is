"""Real HTTP responsiveness and bounded worker/receipt lifetime; no live services."""
import asyncio
import json
import threading
import time

import httpx
import pytest

import documents as docs
import documents_external as external
import documents_operations as ops
import storage as st
from tests.test_documents_routes import token


@pytest.fixture
def world(app_mod, viewer, monkeypatch):
    conn = app_mod.get_conn()
    st.set_setting(conn, 'documents.enabled', '1')
    st.set_setting(conn, 'documents.sending_enabled', '1')
    st.set_setting(conn, 'documents.official_sender', 'office@example.test')
    user = st.get_admin_user(conn, 'viewer@test.local')
    conn.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,'records','2026-10-21')", (user['id'],))
    conn.commit()
    documents = [docs.register(conn, user, {'subject': f'External test {n}', 'type': 'memo', 'direction': 'OUT'})
                 for n in range(3)]
    csrf = token(viewer.get(f"/documents/{documents[0]['id']}"))
    runner = external.Runner()
    monkeypatch.setattr(external, 'RUNNER', runner)
    yield {'conn': conn, 'user': user, 'docs': documents, 'csrf': csrf, 'cookies': viewer.cookies, 'runner': runner}
    runner._pool.shutdown(wait=True)
    conn.close()


def payload(world, document, **values):
    return {'csrf': world['csrf'], 'revision': document['revision'],
            'url': 'https://drive.google.com/file/d/sourcefile12345/view', **values}


def client(app_mod, world):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app_mod.app),
        base_url='http://testserver', cookies=world['cookies'],
        headers={'Origin': 'http://testserver', 'Accept': 'application/json'})


def result(action, values):
    if action == 'extract':
        return {'state': 'confirmed', 'suggestions': {'subject': 'Untrusted suggestion'}, 'excerpts': []}
    if action == 'inspect':
        return {'accessible': True, 'file_id': values['file_id'], 'fingerprint': 'v1', 'size': 100}
    if action == 'dispatch':
        return {'state': 'confirmed', 'fingerprint': values['fingerprint'], 'sender': values['sender'],
                'recipients': {r: {'outcome': 'accepted', 'evidence': 'synthetic message receipt'} for r in values['recipients']}}
    raise AssertionError(action)


def ready_to_send(world):
    conn, document = world['conn'], world['docs'][0]
    vid = conn.execute('''INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at)
        VALUES (?,?,'sourcefile12345','v1','draft',?,'2026-10-21')''',
        (document['id'], 'https://drive.google.com/file/d/sourcefile12345/view', world['user']['id'])).lastrowid
    conn.execute("UPDATE document SET current_version=?,approved_version=?,status='ready_to_release',verification='verified',policy_json=? WHERE id=?",
                 (vid, vid, json.dumps({'signature_required': False, 'ack_required': False, 'release': []}), document['id']))
    conn.commit()
    return payload(world, document, channel='direct_email', recipients=['recipient@example.test'], checklist={})


@pytest.mark.parametrize('action', ['extract', 'attach', 'intake_preview'])
def test_two_second_provider_stall_leaves_same_loop_navigation_responsive(app_mod, world, monkeypatch, action):
    entered = threading.Event()
    worker_threads = []
    class Relay:
        def call(self, kind, values, operation):
            worker_threads.append(threading.get_ident())
            entered.set()
            time.sleep(2)
            return result(kind, values)
    monkeypatch.setattr(ops, 'get_adapter', lambda: Relay())
    document = world['docs'][0]
    data = payload(world, document, classification='material', reason='New source')
    url = f"/documents/{document['id']}/{action}"
    if action == 'intake_preview':
        url = '/documents/intake/preview'
        data['drive_url'] = data['url']
    async def scenario():
        async with client(app_mod, world) as http:
            first = asyncio.create_task(http.post(url, json=data))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                started = time.monotonic()
                for page in ('/health', '/documents/new'):
                    response = await asyncio.wait_for(http.get(page), timeout=1.5)
                    assert response.status_code == 200
                assert time.monotonic() - started < 1.5
                assert not first.done()
            finally:
                response = await asyncio.wait_for(first, 6)
            assert response.status_code in (200, 303), response.text
    asyncio.run(scenario())
    assert worker_threads and all(t != threading.get_ident() for t in worker_threads)


def test_excess_external_request_does_not_start_or_queue_an_operation(app_mod, world, monkeypatch):
    entered = [threading.Event(), threading.Event()]
    release = threading.Event()
    calls = []
    lock = threading.Lock()
    class Relay:
        def call(self, action, values, operation):
            with lock:
                index = len(calls)
                calls.append(operation)
            entered[index].set()
            assert release.wait(5)
            return result(action, values)
    monkeypatch.setattr(ops, 'get_adapter', lambda: Relay())
    async def scenario():
        async with client(app_mod, world) as http:
            pending = [asyncio.create_task(http.post(f"/documents/{d['id']}/extract", json=payload(world, d))) for d in world['docs'][:2]]
            try:
                assert all(await asyncio.gather(*(asyncio.to_thread(e.wait, 3) for e in entered)))
                third = world['docs'][2]
                response = await asyncio.wait_for(http.post(f"/documents/{third['id']}/extract", json=payload(world, third)), 1.5)
                assert response.status_code == 503 and response.json()['state'] == 'not_started'
                assert response.headers['retry-after'] == '3'
                assert world['conn'].execute('SELECT count(*) FROM document_job WHERE document_id=?', (third['id'],)).fetchone()[0] == 0
                assert docs.raw(world['conn'], third['id'])['revision'] == third['revision']
                assert len(calls) == 2
            finally:
                release.set()
                responses = await asyncio.gather(*pending)
            assert all(r.status_code == 200 for r in responses)
    asyncio.run(scenario())


@pytest.mark.parametrize('abandon', ['timeout', 'cancel'])
def test_abandoned_dispatch_retains_capacity_and_settles_one_receipt(app_mod, world, monkeypatch, abandon):
    entered, release = threading.Event(), threading.Event()
    calls = []
    runner = external.Runner(workers=1, wait_seconds=.1 if abandon == 'timeout' else 5)
    world['runner']._pool.shutdown(wait=True)
    monkeypatch.setattr(external, 'RUNNER', runner)
    data = ready_to_send(world)
    document = world['docs'][0]
    class Relay:
        def call(self, action, values, operation):
            calls.append(operation)
            entered.set()
            assert release.wait(5)
            return result(action, values)
    monkeypatch.setattr(ops, 'get_adapter', lambda: Relay())
    async def scenario():
        async with client(app_mod, world) as http:
            first = asyncio.create_task(http.post(f"/documents/{document['id']}/dispatch", json=data))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                if abandon == 'timeout':
                    response = await asyncio.wait_for(first, 2)
                    assert response.status_code == 504 and response.json()['state'] == 'unconfirmed'
                    assert 'retry-after' not in response.headers
                else:
                    first.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await first
                assert world['conn'].execute('SELECT state FROM document_job').fetchone()[0] == 'running'
                other = world['docs'][1]
                denied = await http.post(f"/documents/{other['id']}/extract", json=payload(world, other))
                assert denied.status_code == 503
                assert len(calls) == 1
            finally:
                release.set()
                await asyncio.to_thread(runner._pool.shutdown, wait=True)
                if not first.done():
                    await first
            assert world['conn'].execute('SELECT state FROM document_job').fetchone()[0] == 'confirmed'
            assert world['conn'].execute('SELECT count(*) FROM document_dispatch').fetchone()[0] == 1
            assert world['conn'].execute('SELECT count(*) FROM document_dispatch_recipient').fetchone()[0] == 1
    try:
        asyncio.run(scenario())
    finally:
        release.set()
        runner._pool.shutdown(wait=True)


def test_provider_timeout_is_unknown_sanitized_and_never_replayed(app_mod, world, monkeypatch):
    calls = []
    class Relay:
        def call(self, *args):
            calls.append(True)
            raise httpx.ReadTimeout('private provider credential https://private.test/token')
    monkeypatch.setattr(ops, 'get_adapter', lambda: Relay())
    data = ready_to_send(world)
    document = world['docs'][0]
    async def scenario():
        async with client(app_mod, world) as http:
            response = await http.post(f"/documents/{document['id']}/dispatch", json=data)
            assert response.status_code == 400
            assert 'private provider' not in response.text and 'private.test' not in response.text
            assert 'Check this document' in response.text
            again = await http.post(f"/documents/{document['id']}/dispatch", json=data)
            assert again.status_code == 409
    asyncio.run(scenario())
    assert calls == [True]
    assert world['conn'].execute('SELECT state FROM document_job').fetchone()[0] == 'unknown'
    assert world['conn'].execute('SELECT count(*) FROM document_dispatch').fetchone()[0] == 0


def test_status_and_manual_reconciliation_cannot_race_a_live_dispatch(app_mod, world, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Relay:
        def call(self, action, values, operation):
            calls.append(action)
            entered.set()
            assert release.wait(5)
            return result(action, values)
    monkeypatch.setattr(ops, 'get_adapter', lambda: Relay())
    data = ready_to_send(world)
    document = world['docs'][0]
    async def scenario():
        async with client(app_mod, world) as http:
            first = asyncio.create_task(http.post(f"/documents/{document['id']}/dispatch", json=data))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                operation = world['conn'].execute('SELECT id FROM document_job').fetchone()[0]
                current = docs.raw(world['conn'], document['id'])
                check = payload(world, current, operation_id=operation, outcome='confirmed_no_effect', evidence='User observation')
                for action in ('operation_status', 'operation_reconcile'):
                    response = await http.post(f"/documents/{document['id']}/{action}", json=check)
                    assert response.status_code == 409 and 'still in progress' in response.text
                assert calls == ['dispatch']
                assert world['conn'].execute('SELECT state FROM document_job').fetchone()[0] == 'running'
            finally:
                release.set()
                assert (await first).status_code == 303
    asyncio.run(scenario())
    assert world['conn'].execute('SELECT state FROM document_job').fetchone()[0] == 'confirmed'
    assert world['conn'].execute('SELECT count(*) FROM document_dispatch').fetchone()[0] == 1


def test_csrf_and_private_document_checks_precede_provider_io(app_mod, world, admin, monkeypatch):
    calls = []
    monkeypatch.setattr(ops, 'get_adapter', lambda: calls.append(True))
    document = world['docs'][0]
    bad = payload(world, document, csrf='invalid')
    async def scenario():
        async with client(app_mod, world) as http:
            assert (await http.post(f"/documents/{document['id']}/extract", json=bad)).status_code == 403
    asyncio.run(scenario())
    admin_token = token(admin.get('/documents/new'))
    denied = admin.post(f"/documents/{document['id']}/extract", json=payload(world, document, csrf=admin_token))
    assert denied.status_code == 403
    assert not calls
    assert world['conn'].execute('SELECT count(*) FROM document_job').fetchone()[0] == 0


def test_worker_error_releases_capacity_without_changing_exception():
    runner = external.Runner(workers=1)
    def fail():
        raise TimeoutError('worker timeout')
    async def scenario():
        with pytest.raises(TimeoutError, match='worker timeout'):
            await runner.run(fail)
        assert await runner.run(lambda: 'next') == 'next'
    try:
        asyncio.run(scenario())
    finally:
        runner._pool.shutdown(wait=True)
