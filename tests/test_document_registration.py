"""Registration retries preserve one atomic business result, using synthetic data."""
from concurrent.futures import ThreadPoolExecutor
import json
import re
import sqlite3
import threading

import pytest
import documents as docs
import documents_permissions as permissions
import documents_registration as registration
import storage as st
import work
import work_tasks
from tests.test_work import workspace, intake_fields

TABLES = ('document', 'document_sequence', 'document_reference', 'document_receipt',
          'document_file_version', 'document_assignment', 'document_notice', 'document_event',
          'work_case', 'work_document', 'work_task', 'work_event', 'audit_log', 'document_registration')


def counts(conn):
    return {table: conn.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] for table in TABLES}


def fields(user, unit, **extra):
    return {**intake_fields(unit), 'intake': 'guided', 'submission_id': registration.issue(user),
            'references': 'REF-1\nREF-2', 'drive_url': 'https://drive.google.com/file/d/sourcefile12345/view', **extra}


@pytest.mark.parametrize('mode', ['reference', 'new', 'existing', 'legacy'])
def test_retries_return_original_result_without_any_business_write(workspace, mode):
    conn, users, unit, _ = workspace
    payload = fields(users[0], unit)
    if mode == 'new':
        payload.update(work_mode='new', scenario='activity', outcome='Hold the activity', propose_steps='yes')
    elif mode == 'existing':
        case = work.create(conn, users[0], {'title': 'Existing work', 'outcome': 'A supported result', 'unit_id': unit})
        payload.update(work_mode='existing', scenario='inputs', case_selection=f"{case['id']}:{case['revision']}")
    elif mode == 'legacy':
        payload.pop('intake')
    first = registration.register(conn, users[0], payload)
    before = counts(conn)
    # JSON key order and session CSRF rotation do not change the business request.
    repeated = registration.register(conn, users[0], {**dict(reversed(list(payload.items()))), 'csrf': 'new-session-token'})
    assert first['state'] == repeated['state'] == 'saved'
    assert repeated == {**first, 'replayed': True}
    assert counts(conn) == before
    assert before['document_registration'] == before['document'] == 1
    assert conn.execute('SELECT value FROM document_sequence').fetchone()[0] == 1
    if mode == 'new':
        assert before['work_case'] == 1 and before['work_task'] == 2
    assert first['url'].startswith('/work/' if mode in ('new', 'existing') else '/documents/')


def test_conflicting_payload_never_overwrites_or_creates_another_record(workspace):
    conn, users, unit, _ = workspace
    payload = fields(users[0], unit)
    first = registration.register(conn, users[0], payload)
    before = counts(conn)
    with pytest.raises(docs.Conflict, match='different details'):
        registration.register(conn, users[0], {**payload, 'subject': 'Changed after uncertain save'})
    assert counts(conn) == before
    assert registration.status(conn, users[0], payload['submission_id'])['document_id'] == first['document_id']
    assert docs.raw(conn, first['document_id'])['subject'] == payload['subject']


def test_invalid_attempt_can_be_corrected_with_the_same_key(workspace):
    conn, users, unit, _ = workspace
    payload = fields(users[0], unit)
    before = counts(conn)
    with pytest.raises(ValueError):
        registration.register(conn, users[0], {**payload, 'subject': ''})
    assert counts(conn) == before
    assert registration.status(conn, users[0], payload['submission_id']) == {'state': 'unconfirmed'}
    assert registration.register(conn, users[0], payload)['number'].endswith('000001')


def test_failed_work_or_receipt_rolls_back_everything_then_recovers(workspace, monkeypatch):
    conn, users, unit, _ = workspace
    payload = fields(users[0], unit, work_mode='new', scenario='activity', outcome='Coordinate activity', propose_steps='yes')
    before = counts(conn)
    original = work_tasks.create_in_transaction
    def fail(*args, **kwargs): raise RuntimeError('synthetic task failure')
    monkeypatch.setattr(work_tasks, 'create_in_transaction', fail)
    with pytest.raises(RuntimeError): registration.register(conn, users[0], payload)
    assert counts(conn) == before
    monkeypatch.setattr(work_tasks, 'create_in_transaction', original)
    conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON document_registration BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError): registration.register(conn, users[0], payload)
    assert counts(conn) == before
    conn.execute('DROP TRIGGER fail_receipt'); conn.commit()
    assert registration.register(conn, users[0], payload)['number'].endswith('000001')
    assert conn.execute('SELECT COUNT(*) FROM work_task').fetchone()[0] == 2


def test_independent_concurrent_connections_create_only_one_document_and_work(workspace):
    conn, users, unit, path = workspace
    payload = fields(users[0], unit, work_mode='new', scenario='activity', outcome='Coordinate activity', propose_steps='yes')
    start = threading.Barrier(2)
    def submit():
        other = st.connect(path)
        try:
            start.wait(timeout=3)
            return registration.register(other, users[0], payload)
        finally: other.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        results = [future.result(timeout=8) for future in futures]
    assert sorted(result['replayed'] for result in results) == [False, True]
    assert results[0]['document_id'] == results[1]['document_id']
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1
    assert conn.execute('SELECT value FROM document_sequence').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM work_case').fetchone()[0] == 1
    assert conn.execute('SELECT COUNT(*) FROM work_task').fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM document_event WHERE action='registered'").fetchone()[0] == 1


def test_inflight_result_is_unconfirmed_until_atomic_commit(workspace, monkeypatch):
    conn, users, unit, path = workspace
    payload = fields(users[0], unit, work_mode='new', scenario='activity', outcome='Coordinate activity', propose_steps='yes')
    entered, release = threading.Event(), threading.Event()
    original = work_tasks.create_in_transaction
    def wait(*args, **kwargs):
        entered.set()
        assert release.wait(4)
        return original(*args, **kwargs)
    monkeypatch.setattr(work_tasks, 'create_in_transaction', wait)
    def submit():
        other = st.connect(path)
        try: return registration.register(other, users[0], payload)
        finally: other.close()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(submit)
        try:
            assert entered.wait(3)
            assert registration.status(conn, users[0], payload['submission_id']) == {'state': 'unconfirmed'}
            assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 0
        finally: release.set()
        result = future.result(timeout=5)
    assert registration.status(conn, users[0], payload['submission_id'])['document_id'] == result['document_id']


def test_receipt_survives_connection_restart_and_repeat_schema_install(workspace):
    conn, users, unit, path = workspace
    payload = fields(users[0], unit)
    result = registration.register(conn, users[0], payload)
    other = st.connect(path)
    try:
        st.init_db(other); st.init_db(other)
        assert registration.status(other, users[0], payload['submission_id'])['number'] == result['number']
        assert registration.register(other, users[0], payload)['replayed']
        stored = other.execute('SELECT * FROM document_registration').fetchone()
        assert payload['subject'] not in json.dumps(stored)
    finally: other.close()


def test_receipts_do_not_grant_access_or_accept_another_account_key(workspace):
    conn, users, unit, _ = workspace
    payload = fields(users[0], unit)
    result = registration.register(conn, users[0], payload)
    before = counts(conn)
    with pytest.raises(permissions.Denied): registration.status(conn, users[1], payload['submission_id'])
    with pytest.raises(permissions.Denied): registration.register(conn, users[1], payload)
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?", (result['document_id'],)); conn.commit()
    with pytest.raises(permissions.Denied): registration.status(conn, users[0], payload['submission_id'])
    with pytest.raises(permissions.Denied): registration.register(conn, users[0], payload)
    assert counts(conn) == before


def test_disabled_account_and_module_and_forged_keys(workspace):
    conn, users, unit, _ = workspace
    payload = fields(users[0], unit)
    result = registration.register(conn, users[0], payload)
    st.set_setting(conn, 'documents.enabled', '0')
    assert registration.register(conn, users[0], payload)['replayed']  # Read-only recovery still works.
    with pytest.raises(ValueError, match='disabled'):
        registration.register(conn, users[0], fields(users[0], unit))
    for invalid in ('', 'bad', payload['submission_id'][:-1] + ('0' if payload['submission_id'][-1] != '0' else '1')):
        with pytest.raises(permissions.Denied): registration.status(conn, users[0], invalid)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],)); conn.commit()
    with pytest.raises(permissions.Denied): registration.status(conn, users[0], payload['submission_id'])
    assert conn.execute('SELECT COUNT(*) FROM document').fetchone()[0] == 1


def hidden(page, key):
    return re.search(r'name="' + key + r'" value="([^"]+)"', page.text)[1]


def test_http_native_json_lost_reply_and_status_privacy(app_mod, viewer, admin, monkeypatch):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    page = viewer.get('/documents/new')
    payload = dict(csrf=hidden(page, 'csrf'), submission_id=hidden(page, 'submission_id'), subject='Private retry record', type='memo')
    headers = {'Accept': 'application/json'}
    before = counts(conn)
    assert viewer.get('/documents/registrations/' + payload['submission_id']).json() == {'state': 'unconfirmed'}
    assert viewer.post('/documents/new', data={**payload, 'csrf': 'invalid'}, headers=headers).status_code == 403
    assert counts(conn) == before
    original = registration.register
    def lost(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('synthetic lost reply after commit')
    monkeypatch.setattr(registration, 'register', lost)
    response = viewer.post('/documents/new', data=payload, headers=headers)
    assert response.status_code == 500 and response.json()['state'] == 'unconfirmed'
    assert 'synthetic lost reply' not in response.text
    status = viewer.get('/documents/registrations/' + payload['submission_id'])
    assert status.json()['state'] == 'saved' and status.headers['cache-control'] == 'no-store'
    assert admin.get('/documents/registrations/' + payload['submission_id']).status_code == 404
    monkeypatch.setattr(registration, 'register', original)
    before_retry = counts(conn)
    native = viewer.post('/documents/new', data=payload, follow_redirects=False)
    assert native.status_code == 303 and native.headers['location'] == status.json()['url']
    replay = viewer.post('/documents/new', data=payload, headers=headers)
    assert replay.status_code == 200 and replay.json()['replayed']
    assert counts(conn) == before_retry
    conflict = viewer.post('/documents/new', data={**payload, 'subject': 'Edited'}, headers=headers)
    assert conflict.status_code == 409 and conflict.json()['state'] == 'conflict'
    assert counts(conn) == before_retry
    conn.close()


def test_http_writer_contention_is_retryable(app_mod, viewer, monkeypatch):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    page = viewer.get('/documents/new')
    payload = dict(csrf=hidden(page, 'csrf'), submission_id=hidden(page, 'submission_id'), subject='Busy write', type='memo')
    original = registration.register
    def short_wait(connection, *args, **kwargs):
        connection.execute('PRAGMA busy_timeout=30')
        return original(connection, *args, **kwargs)
    monkeypatch.setattr(registration, 'register', short_wait)
    conn.execute('BEGIN IMMEDIATE')
    try:
        response = viewer.post('/documents/new', data=payload, headers={'Accept': 'application/json'})
        assert response.status_code == 503 and response.headers['retry-after'] == '3'
        assert response.json()['state'] == 'unconfirmed'
        assert viewer.get('/documents/registrations/' + payload['submission_id']).json() == {'state': 'unconfirmed'}
    finally: conn.rollback()
    assert viewer.post('/documents/new', data=payload, headers={'Accept': 'application/json'}).json()['state'] == 'saved'
    conn.close()


def test_waiting_registration_does_not_block_another_request_on_the_same_loop(app_mod, viewer, monkeypatch):
    import asyncio
    import httpx
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    page = viewer.get('/documents/new')
    payload = dict(csrf=hidden(page, 'csrf'), submission_id=hidden(page, 'submission_id'), subject='Waiting write', type='memo')
    entered = threading.Event()
    original = registration.register
    def record(*args, **kwargs):
        entered.set()
        return original(*args, **kwargs)
    monkeypatch.setattr(registration, 'register', record)
    conn.execute('BEGIN IMMEDIATE')
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_mod.app),
                base_url='http://testserver', cookies=viewer.cookies, headers={'Origin': 'http://testserver'}) as client:
            first = asyncio.create_task(client.post('/documents/new', data=payload, headers={'Accept': 'application/json'}))
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                response = await asyncio.wait_for(client.get('/documents/new'), timeout=2)
                assert response.status_code == 200 and not first.done()
            finally: conn.rollback()
            assert (await first).json()['state'] == 'saved'
    try: asyncio.run(scenario())
    finally: conn.rollback(); conn.close()
