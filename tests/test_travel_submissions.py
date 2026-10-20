"""Ambiguous responses, actual process interruption and concurrent filing opens."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode, urlsplit, unquote
import uuid

import pytest

import storage as st
import travel
import travel_submissions as operations
import tzutil as tz
from test_travel_pages import conn
from travel_requests import operation_id


def fields(key):
    return {'operation_id': key, 'kind': 'liquidation', 'title': 'Receipt test',
            'start': (tz.today_local() - timedelta(days=10)).isoformat(),
            'end': (tz.today_local() - timedelta(days=8)).isoformat(),
            'role': 'secretariat', 'advance_amount': '5000', 'dpo_no': '2026-100'}


def post(client, data, *, json_response=True, path='/travel/new'):
    return client.post(path, content=urlencode(data), follow_redirects=False,
        headers={'Content-Type': 'application/x-www-form-urlencoded',
                 'Accept': 'application/json' if json_response else 'text/html'})


def status(client, key):
    return client.get('/travel/submissions/' + key, headers={'Accept': 'application/json'})


def effects(conn):
    return tuple(conn.execute(sql).fetchone()[0] for sql in (
        'SELECT COUNT(*) FROM travel_filing',
        "SELECT COUNT(*) FROM audit_log WHERE action='travel_open'"))


def test_repeated_post_returns_original_filing_and_audit(viewer, conn):
    key = operation_id(viewer)
    first = post(viewer, fields(key))
    second = post(viewer, fields(key))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()['state'] == 'completed'
    assert effects(conn) == (1, 1)
    receipt = status(viewer, key)
    assert receipt.json() == first.json()
    assert receipt.headers['cache-control'] == 'no-store'


def test_commit_then_lost_response_is_recoverable(viewer, conn, monkeypatch):
    key = operation_id(viewer)
    execute = operations.execute
    def commit_then_drop(*args, **kw):
        execute(*args, **kw)
        raise ConnectionError('Response lost after commit')
    with monkeypatch.context() as patch:
        patch.setattr(operations, 'execute', commit_then_drop)
        lost = post(viewer, fields(key))
        native_lost = post(viewer, fields(key), json_response=False)
        assert native_lost.status_code == 503 and native_lost.headers['cache-control'] == 'no-store'
    assert lost.status_code == 503 and lost.json()['state'] == 'unknown'
    saved = status(viewer, key)
    assert saved.json()['state'] == 'completed'
    assert post(viewer, fields(key)).json() == saved.json()
    assert effects(conn) == (1, 1)


def test_partial_work_rolls_back_and_same_operation_can_resume(viewer, conn, monkeypatch):
    key = operation_id(viewer)
    create = travel.create_filing
    def fail_after_insert(*args, **kw):
        create(*args, **kw)
        raise RuntimeError('Interrupted before receipt')
    with monkeypatch.context() as patch:
        patch.setattr(travel, 'create_filing', fail_after_insert)
        assert post(viewer, fields(key)).status_code == 503
    assert effects(conn) == (0, 0)
    assert conn.execute('SELECT COUNT(*) FROM travel_item').fetchone()[0] == 0
    assert status(viewer, key).json()['state'] == 'pending'
    reloaded = viewer.get('/travel/new/' + key)
    assert 'action="/travel/submissions/' + key + '/close"' in reloaded.text
    assert post(viewer, {**fields(key), 'advance_amount': '6000'}).status_code == 409
    assert post(viewer, fields(key)).json()['state'] == 'completed'
    assert effects(conn) == (1, 1)


def test_audit_failure_rolls_back_filing_and_receipt(viewer, conn, monkeypatch):
    key = operation_id(viewer)
    audit = st.audit
    def fail_audit(c, actor, action, **kw):
        audit(c, actor, action, **kw)
        if action == 'travel_open':
            raise RuntimeError('Audit interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(st, 'audit', fail_audit)
        assert post(viewer, fields(key)).status_code == 503
    assert effects(conn) == (0, 0)
    assert status(viewer, key).json()['state'] == 'pending'
    assert post(viewer, fields(key)).json()['state'] == 'completed'
    assert effects(conn) == (1, 1)


def test_actual_process_exit_rolls_back_work_then_restart_resumes(viewer, conn, app_mod):
    key = operation_id(viewer)
    script = '''
import json, os, sys
from datetime import date
import storage as st, travel, travel_submissions as ops
c = st.connect(sys.argv[1]); f = json.loads(sys.argv[2])
u = st.get_admin_user(c, 'viewer@test.local')
def work():
    source = dict(source_kind='blank', entry_id=None, event_id=None,
                  title=f['title'], start=f['start'], end=f['end'], venue='')
    filing = travel.create_filing(c, u, kind=f['kind'], source=source, answers=f,
        role=f['role'], dpo_no=f['dpo_no'], advance_amount=f['advance_amount'],
        today=date.fromisoformat(f['end']), commit=False)
    st.audit(c, u['username'], 'travel_open', target_id=filing['id'], commit=False)
    os._exit(17)
ops.execute(c, u['id'], f['operation_id'], f, work)
'''
    child = subprocess.run([sys.executable, '-c', script, app_mod.DB, json.dumps(fields(key))],
                           capture_output=True, text=True, timeout=20)
    assert child.returncode == 17, child.stderr
    assert effects(conn) == (0, 0)
    assert status(viewer, key).json()['state'] == 'pending'
    assert post(viewer, fields(key)).json()['state'] == 'completed'
    assert effects(conn) == (1, 1)


def test_simultaneous_connections_execute_one_business_action(viewer, conn, app_mod):
    key, barrier, calls = operation_id(viewer), threading.Barrier(2), []
    data = fields(key)
    def submit():
        c = st.connect(app_mod.DB)
        try:
            user = st.get_admin_user(c, 'viewer@test.local')
            barrier.wait(timeout=5)
            def action():
                calls.append(1)
                time.sleep(0.1)
                source = dict(source_kind='blank', entry_id=None, event_id=None,
                    title=data['title'], start=data['start'], end=data['end'], venue='')
                filing = travel.create_filing(c, user, kind=data['kind'], source=source, answers=data,
                    role=data['role'], dpo_no=data['dpo_no'], advance_amount=data['advance_amount'],
                    today=tz.today_local(), commit=False)
                st.audit(c, user['username'], 'travel_open', target_id=filing['id'], commit=False)
                return filing['ref_code']
            return operations.execute(c, user['id'], key, data, action)
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = [f.result(timeout=10) for f in [pool.submit(submit), pool.submit(submit)]]
    assert a == b and calls == [1]
    assert effects(conn) == (1, 1)


def test_changed_payload_cannot_reuse_completed_key(viewer, conn):
    key = operation_id(viewer)
    assert post(viewer, fields(key)).json()['state'] == 'completed'
    response = post(viewer, {**fields(key), 'advance_amount': '6000'})
    assert response.status_code == 409
    other = operation_id(viewer)
    mismatch = post(viewer, fields(key), path='/travel/new/' + other)
    assert mismatch.status_code == 409 and status(viewer, other).json()['state'] == 'ready'
    assert effects(conn) == (1, 1)


def test_other_actor_and_unknown_keys_are_indistinguishable(viewer, encoder, admin, conn):
    key = operation_id(viewer)
    assert post(viewer, fields(key)).status_code == 200
    unknown = str(uuid.uuid4())
    for client in (encoder, admin):
        assert status(client, key).status_code == 404
        assert status(client, key).json() == status(client, unknown).json()
        assert post(client, fields(key)).status_code == 404
    assert effects(conn) == (1, 1)


def test_validation_rejection_issues_a_new_key_for_corrected_form(viewer, conn):
    key = operation_id(viewer)
    bad = post(viewer, {**fields(key), 'dpo_no': ''})
    assert bad.status_code == 400 and bad.json()['state'] == 'rejected'
    assert status(viewer, key).json()['state'] == 'rejected'
    assert effects(conn) == (0, 0)
    replacement = bad.json()['operation_id']
    assert replacement != key
    assert post(viewer, fields(replacement)).json()['state'] == 'completed'
    assert effects(conn) == (1, 1)


def test_missing_key_requires_review_instead_of_unprotected_write(viewer, conn):
    data = fields(''); del data['operation_id']
    response = post(viewer, data, json_response=False)
    assert response.status_code == 400 and 'name="operation_id"' in response.text
    assert effects(conn) == (0, 0)


def test_native_form_replay_redirects_to_the_same_checklist(viewer, conn):
    key = operation_id(viewer)
    a, b = [post(viewer, fields(key), json_response=False, path='/travel/new/' + key) for _ in range(2)]
    assert a.status_code == b.status_code == 303
    assert a.headers['location'] == b.headers['location']
    assert effects(conn) == (1, 1)


def test_foreign_origin_does_not_claim_operation(viewer, conn):
    key = operation_id(viewer)
    response = viewer.post('/travel/new', content=urlencode(fields(key)), headers={
        'Content-Type': 'application/x-www-form-urlencoded', 'Origin': 'https://evil.example'})
    assert response.status_code == 403
    assert status(viewer, key).json()['state'] == 'ready'
    assert effects(conn) == (0, 0)


def test_removed_filing_never_recreates_from_its_receipt(viewer, conn):
    key = operation_id(viewer)
    assert post(viewer, fields(key)).status_code == 200
    for table in ('travel_item', 'travel_filing'):
        conn.execute('DELETE FROM ' + table)
    conn.commit()
    again = post(viewer, fields(key))
    assert again.json()['state'] == 'completed' and again.json()['location'] is None
    assert effects(conn) == (0, 1)


def test_form_is_not_cached_and_native_status_is_available(viewer, conn):
    assert viewer.get('/travel/new').headers['cache-control'] == 'no-store'
    key = operation_id(viewer)
    page = viewer.get('/travel/submissions/' + key)
    assert page.status_code == 200 and 'No completed filing' in page.text
    assert page.headers['cache-control'] == 'no-store'


def test_form_url_retains_its_key_and_reload_recovers_the_result(viewer, conn):
    page = viewer.get('/travel/new')
    key = urlsplit(str(page.url)).path.rsplit('/', 1)[1]
    assert viewer.get(str(page.url)).text.count('value="' + key + '"') == 1
    assert conn.execute('SELECT COUNT(*) FROM travel_submission').fetchone()[0] == 1
    result = post(viewer, fields(key)).json()
    recovered = viewer.get(str(page.url), follow_redirects=False)
    assert recovered.status_code == 303 and recovered.headers['location'] == result['location']
    assert recovered.headers['cache-control'] == 'no-store'
    assert effects(conn) == (1, 1)


def test_revoked_account_cannot_read_or_replay_receipt(viewer, conn):
    key = operation_id(viewer)
    assert post(viewer, fields(key)).status_code == 200
    st.set_admin_active(conn, st.get_admin_user(conn, 'viewer@test.local')['id'], False)
    denied = viewer.get('/travel/submissions/' + key, follow_redirects=False)
    assert denied.status_code in (303, 401, 403)
    sign_in = viewer.get('/travel/new/' + key, follow_redirects=False)
    assert sign_in.status_code == 303 and '/travel/new/' + key in unquote(sign_in.headers['location'])
    assert post(viewer, fields(key)).status_code in (401, 403)
    assert effects(conn) == (1, 1)


def test_busy_database_never_creates_an_untracked_filing(viewer, conn, app_mod):
    import sqlite3
    key = operation_id(viewer)
    writer, attempt = st.connect(app_mod.DB), st.connect(app_mod.DB)
    user = st.get_admin_user(conn, 'viewer@test.local')
    called = []
    try:
        writer.execute('BEGIN IMMEDIATE')
        attempt.execute('PRAGMA busy_timeout=10')
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            operations.execute(attempt, user['id'], key, fields(key), lambda: called.append(1))
        assert called == [] and effects(conn) == (0, 0)
    finally:
        writer.rollback(); writer.close(); attempt.close()
    assert post(viewer, fields(key)).json()['state'] == 'completed'
    assert effects(conn) == (1, 1)


def test_lost_form_can_be_closed_and_its_key_cannot_execute(viewer, conn):
    key = operation_id(viewer)
    response = viewer.post('/travel/submissions/' + key + '/close', follow_redirects=False)
    assert response.status_code == 303
    assert viewer.post('/travel/submissions/' + key + '/close', follow_redirects=False).status_code == 303
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_submission_close'").fetchone()[0] == 1
    assert status(viewer, key).json()['state'] == 'rejected'
    assert post(viewer, fields(key)).status_code == 400
    assert effects(conn) == (0, 0)


def test_closing_completed_attempt_keeps_the_original_result(viewer, conn):
    key = operation_id(viewer)
    original = post(viewer, fields(key)).json()
    assert viewer.post('/travel/submissions/' + key + '/close', follow_redirects=False).status_code == 303
    assert status(viewer, key).json() == original
    assert effects(conn) == (1, 1)


def test_close_requires_the_owner_and_same_origin(viewer, encoder, conn):
    key = operation_id(viewer)
    url = '/travel/submissions/' + key + '/close'
    assert encoder.post(url).status_code == 404
    assert viewer.post(url, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert status(viewer, key).json()['state'] == 'ready'


def test_close_waits_for_the_writer_and_preserves_its_commit(viewer, conn, app_mod):
    key = operation_id(viewer)
    user = st.get_admin_user(conn, 'viewer@test.local')
    running, release, closing_started = threading.Event(), threading.Event(), threading.Event()
    def write():
        c = st.connect(app_mod.DB)
        try:
            def action():
                running.set()
                assert release.wait(timeout=5)
                source = dict(source_kind='blank', title='Original', start=fields(key)['start'], end=fields(key)['end'])
                filing = travel.create_filing(c, user, kind='liquidation', source=source, answers={},
                    role='secretariat', dpo_no='2026-100', advance_amount='5000', today=tz.today_local(), commit=False)
                return filing['ref_code']
            return operations.execute(c, user['id'], key, fields(key), action)
        finally:
            c.close()
    def close():
        c = st.connect(app_mod.DB)
        try:
            closing_started.set()
            operations.close_unfinished(c, user['id'], key)
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        writing = pool.submit(write)
        assert running.wait(timeout=5)
        closing = pool.submit(close)
        assert closing_started.wait(timeout=5)
        time.sleep(0.05)
        assert not closing.done()
        release.set()
        ref = writing.result(timeout=10)
        closing.result(timeout=10)
    assert status(viewer, key).json()['location'] == '/travel/f/' + ref
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 1


def test_close_audit_failure_keeps_the_attempt_resumable(viewer, conn, monkeypatch):
    key = operation_id(viewer)
    audit = st.audit
    def interrupt(c, actor, action, **kw):
        audit(c, actor, action, **kw)
        if action == 'travel_submission_close':
            raise RuntimeError('Audit interrupted')
    with monkeypatch.context() as patch:
        patch.setattr(st, 'audit', interrupt)
        response = viewer.post('/travel/submissions/' + key + '/close', follow_redirects=False)
    assert response.status_code == 503
    assert status(viewer, key).json()['state'] == 'ready'
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_submission_close'").fetchone()[0] == 0
    assert post(viewer, fields(key)).json()['state'] == 'completed'
