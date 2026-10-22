"""A19 contract, current session/authority, bounded reads and no business effects."""
from contextlib import ExitStack
from datetime import datetime
import json

import pytest
from starlette.testclient import TestClient

import auth
import documents as docs
import documents_permissions as permissions
import integration_api
import storage as st
import work
import work_reads
import work_tasks
from tests.conftest import session_token
from tests.test_work import workspace, case, document, propose, advance


@pytest.fixture
def api(workspace, app_mod, monkeypatch):
    c, users, unit, path = workspace
    monkeypatch.setattr(app_mod, 'DB', path)
    with ExitStack() as stack:
        clients = []
        for user in users:
            client = stack.enter_context(TestClient(app_mod.app, raise_server_exceptions=False))
            client.cookies.set(auth.COOKIE_NAME, session_token(user))
            clients.append(client)
        yield c, users, unit, clients, app_mod


def body(client, path, **params):
    response = client.get('/api/v1' + path, params=params)
    assert response.status_code == 200, (response.status_code, response.text)
    assert 'no-store' in response.headers['cache-control']
    return response.json()


def test_versioned_contract_is_separate_authenticated_and_typed(api):
    c, u, unit, clients, app = api
    schema = body(clients[0], '/openapi.json')
    assert schema['info']['version'] == '1.0.0'
    from pathlib import Path
    artifact = Path(__file__).parents[1] / 'docs/api/v1/openapi.json'
    assert schema == json.loads(artifact.read_text())
    assert schema['servers'] == [{'url': '/api/v1'}]
    assert set(schema['paths']) == {'/', '/documents', '/documents/{document_id}', '/work-items',
        '/work-items/{work_item_id}', '/work-items/{work_item_id}/tasks', '/work-items/{work_item_id}/tasks/{task_id}'}
    assert all(set(path) == {'get'} for path in schema['paths'].values())
    for path in schema['paths'].values():
        operation = path['get']
        assert operation['security'] == [{'UserSession': []}]
        assert operation['responses']['200']['content']['application/json']['schema']
        assert operation['responses']['401']['content']['application/json']['schema']
        # The generic framework validation shape must not be advertised for our
        # overridden 400 contract.
        assert '422' not in operation['responses']
    assert schema['components']['securitySchemes']['UserSession'] == {
        'type': 'apiKey', 'in': 'cookie', 'name': auth.COOKIE_NAME,
        'description': 'An existing registered user session; API keys and bearer tokens are not supported by this increment.'}
    info = body(clients[0], '/')
    assert info['read_only'] and info['application_version'] == integration_api.version.APP_VERSION


@pytest.mark.parametrize('path', ['/', '/documents', '/openapi.json', '/work-items', '/unknown'])
def test_anonymous_api_returns_json_without_login_redirect(client, path):
    response = client.get('/api/v1' + path, follow_redirects=False,
                          headers={'Authorization': 'Bearer not-a-supported-token'})
    assert response.status_code == 401
    assert 'location' not in response.headers
    assert response.json() == {'error': {'code': 'authentication_required', 'message': 'A current signed-in session is required.'}}
    assert 'no-store' in response.headers['cache-control']
    assert 'access-control-allow-origin' not in response.headers


def test_document_projection_alias_and_current_restricted_authority(api):
    c, u, unit, clients, app = api
    secret = document(c, u[0], unit, subject='Private source subject')
    missing = clients[3].get('/api/v1/documents/99999999')
    denied = clients[3].get(f"/api/v1/documents/{secret['id']}")
    admin_denied = clients[4].get(f"/api/v1/documents/{secret['id']}")
    assert denied.status_code == admin_denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json() == admin_denied.json()
    assert body(clients[3], '/documents')['data'] == []
    secret = docs.mutate(c, u[1], secret['id'], secret['revision'], 'verify', {'verification': 'verified', 'reason': 'Checked'})
    result = body(clients[3], f"/documents/{secret['id']}")
    assert result['id'] == str(secret['id']) and result['revision'] == secret['revision']
    assert set(result) == {'id','number','subject','direction','type','status','verification','revision','due_date',
                           'created_at','updated_at','archived_at','links'}
    assert datetime.fromisoformat(result['created_at']).utcoffset().total_seconds() == 8*3600
    assert result['links']['self'] == '/api/v1/documents/' + str(secret['id'])
    secret = docs.mutate(c, u[1], secret['id'], secret['revision'], 'access',
                         {'visibility': 'restricted', 'viewers': [u[1]['id']], 'reason': 'Restrict'})
    assert clients[3].get(f"/api/v1/documents/{secret['id']}", headers={'If-None-Match': 'anything'}).status_code == 404
    assert body(clients[3], '/documents')['data'] == []
    # An obsolete receipt can be resolved only to its permitted canonical target.
    source = document(c, u[1], unit, subject='Obsolete confidential alias')
    c.execute('UPDATE document SET canonical_id=? WHERE id=?', (secret['id'], source['id'])); c.commit()
    assert clients[0].get(f"/api/v1/documents/{source['id']}").status_code == 404
    resolved = body(clients[1], f"/documents/{source['id']}")
    assert resolved['id'] == str(secret['id']) and resolved['subject'] != source['subject']


def test_session_revocation_and_account_changes_apply_to_next_api_read(api):
    c, u, unit, clients, app = api
    assert body(clients[0], '/')['read_only']
    token = clients[0].cookies.get(auth.COOKIE_NAME)
    st.revoke_login_session(c, auth.parse_token(token)['sid'])
    assert clients[0].get('/api/v1/openapi.json').status_code == 401
    clients[0].cookies.set(auth.COOKIE_NAME, session_token(u[0]))
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (u[0]['id'],)); c.commit()
    assert clients[0].get('/api/v1/documents').status_code == 401


def test_work_and_tasks_obey_case_and_every_linked_document(api):
    c, u, unit, clients, app = api
    doc = document(c, u[0], unit)
    item = case(c, u[0], unit, source_document_id=doc['id'])
    contribution = propose(c, u[0], item, unit, u[2]['id'])
    assert clients[2].get(f"/api/v1/work-items/{item['id']}").status_code == 404
    assert body(clients[4], '/work-items')['data'] == []  # A tech admin is not a case officer.
    doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Checked'})
    contribution = advance(c, u[1], contribution, 'confirm', owner_id=u[2]['id'])
    result = body(clients[2], f"/work-items/{item['id']}")
    assert result['id'] == str(item['id'])
    task_page = body(clients[2], f"/work-items/{item['id']}/tasks")
    assert len(task_page['data']) == 1
    row = task_page['data'][0]
    assert row['status'] == 'todo' and row['owner_id'] == str(u[2]['id'])
    assert row['revision'] == contribution['revision']
    assert 'submission' not in row and 'expected_output' not in row
    assert body(clients[2], row['links']['self'].removeprefix('/api/v1')) == row
    other = case(c, u[0], unit)
    assert clients[0].get(f"/api/v1/work-items/{other['id']}/tasks/{contribution['id']}").status_code == 404
    docs.mutate(c, u[1], doc['id'], doc['revision'], 'access',
                {'visibility': 'restricted', 'viewers': [u[1]['id']], 'reason': 'Narrow'})
    for path in [f"/work-items/{item['id']}", f"/work-items/{item['id']}/tasks", f"/work-items/{item['id']}/tasks/{contribution['id']}"]:
        assert clients[2].get('/api/v1' + path).status_code == 404
    assert body(clients[2], '/work-items')['data'] == []


def test_work_pages_filter_before_limit_and_use_visible_cursors(api):
    c, u, unit, clients, app = api
    expected = [case(c, u[0], unit)['id'] for _ in range(3)]
    # A large newer hidden population must not produce an empty API page or a
    # cursor made from a hidden case's ID.
    c.executemany('''INSERT INTO work_case(title,outcome,unit_id,creator_id,created_at,updated_at)
        VALUES('HIDDEN CASE','Hidden outcome',?,?, '2026-10-21', '2026-10-21')''', [(unit,u[3]['id'])]*270)
    c.commit()
    first = body(clients[0], '/work-items', limit=2)
    assert [r['id'] for r in first['data']] == [str(i) for i in reversed(expected[1:])]
    assert first['page'] == {'limit': 2, 'has_more': True, 'next_before': str(expected[1])}
    second = body(clients[0], '/work-items', limit=2, before=first['page']['next_before'])
    assert [r['id'] for r in second['data']] == [str(expected[0])]
    assert second['page']['next_before'] is None
    assert 'HIDDEN CASE' not in json.dumps(first)


def test_document_and_task_pages_no_skips_and_identifiers_remain_strings(api):
    c, u, unit, clients, app = api
    expected = [document(c, u[0], unit)['id'] for _ in range(4)]
    first = body(clients[0], '/documents', limit=2)
    second = body(clients[0], '/documents', limit=2, before=first['page']['next_before'])
    assert [r['id'] for r in first['data'] + second['data']] == [str(i) for i in reversed(expected)]
    assert not second['page']['has_more']
    item = case(c, u[0], unit)
    tasks = [propose(c,u[0],item,unit)['id'] for _ in range(4)]
    first = body(clients[0], f"/work-items/{item['id']}/tasks", limit=2)
    second = body(clients[0], f"/work-items/{item['id']}/tasks", limit=2, before=first['page']['next_before'])
    assert [r['id'] for r in first['data'] + second['data']] == [str(i) for i in reversed(tasks)]
    large_id = 9007199254740993
    c.execute('''INSERT INTO work_case(id,title,outcome,unit_id,creator_id,created_at,updated_at)
        VALUES(?, 'Large identifier', 'Outcome', ?, ?, '2026-10-21', '2026-10-21')''', (large_id, unit, u[0]['id'])); c.commit()
    assert body(clients[0], '/work-items/' + str(large_id))['id'] == str(large_id)


@pytest.mark.parametrize('suffix', ['/documents?limit=0', '/documents?limit=101', '/documents?before=-1',
    '/documents?before=9223372036854775808', '/documents?queue=unsupported', '/documents?extra=secret',
    '/documents?limit=1&limit=2', '/work-items?status=unsupported', '/documents/9223372036854775808',
    '/work-items/zero', '/work-items/1/tasks?limit=99999'])
def test_invalid_inputs_are_bounded_generic_json(api, suffix):
    response = api[3][0].get('/api/v1' + suffix)
    assert response.status_code == 400
    assert set(response.json()) == {'error'} and response.json()['error']['code'] == 'invalid_request'
    assert 'secret' not in response.text


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'])
def test_only_get_is_supported_and_no_business_state_changes(api, method):
    c, u, unit, clients, app = api
    item = case(c, u[0], unit)
    before = c.iterdump()
    before = '\n'.join(before)
    response = clients[0].request(method, f"/api/v1/work-items/{item['id']}", content=b'{"role":"admin"}')
    assert response.status_code == 405 and response.headers['allow'] == 'GET'
    if method != 'HEAD':
        assert response.json()['error']['code'] == 'method_not_allowed'
    assert '\n'.join(c.iterdump()) == before


def test_api_reads_skip_nav_and_business_mutations_even_when_modules_disabled(api, monkeypatch):
    c, u, unit, clients, app = api
    doc = document(c,u[0],unit)
    item = case(c,u[0],unit)
    task = propose(c,u[0],item,unit)
    st.set_setting(c, 'documents.enabled', '0'); st.set_setting(c, 'work.enabled', '0')
    def forbidden(*a, **k):
        raise AssertionError('Browser navigation/provider mutation must not run during an API read')
    monkeypatch.setattr(app, '_notification_items', forbidden)
    for module, name in [(docs,'mutate'),(work_tasks,'mutate')]:
        monkeypatch.setattr(module,name,forbidden)
    before = '\n'.join(c.iterdump())
    for path in ['/', '/openapi.json', '/documents', f"/documents/{doc['id']}", '/work-items',
                 f"/work-items/{item['id']}", f"/work-items/{item['id']}/tasks", f"/work-items/{item['id']}/tasks/{task['id']}"]:
        body(clients[0], path)
    assert '\n'.join(c.iterdump()) == before


def test_unexpected_errors_are_sanitized_and_private(api, monkeypatch):
    def failed(*a, **k):
        raise RuntimeError('PRIVATE SQL DETAILS AND SECRET SENTINEL')
    monkeypatch.setattr(docs, 'list_page', failed)
    response = api[3][0].get('/api/v1/documents')
    assert response.status_code == 500
    assert response.json() == {'error': {'code': 'internal_error', 'message': 'The request could not be completed. Retry later.'}}
    assert 'SENTINEL' not in response.text and 'no-store' in response.headers['cache-control']


def test_work_sql_selection_matches_existing_detail_policy(workspace):
    c, users, unit, path = workspace
    other = st.add_org_unit(c,'Other division','division','WORK/D10')
    entries = []
    for idx in range(12):
        creator = users[idx % 4]
        item = case(c,creator,unit if idx % 2 else other)
        if idx % 3 == 0:
            propose(c,creator,item,unit,users[2]['id'])
        if idx % 3 == 1:
            task = propose(c,creator,item,unit,creator['id'])
            advance(c,users[1],task,'confirm',owner_id=creator['id'])
        if idx % 4 == 0:
            source = document(c,creator,unit)
            work.link_document(c,creator,item['id'],item['revision'],source['id'])
        entries.append(work.raw(c,item['id']))
    for user in users:
        expected = [r['id'] for r in reversed(entries) if work._can_view(c,permissions.actor(c,user),r)]
        actual, before = work_reads.page(c,user,limit=100)
        assert [r['id'] for r in actual] == expected and before is None


def test_standalone_client_reads_real_http_and_never_follows_login_redirect(api):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from examples.read_api import ReadClient, ApiFailure
    c, users, unit, clients, app = api
    expected = [document(c,users[0],unit)['id'] for _ in range(3)]
    # Bridge raw local HTTP to the real application; the incoming cookie is the
    # only authentication. The bridge never injects a privileged fixture session.
    adapter = TestClient(app.app, raise_server_exceptions=False)
    traps = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            if self.path == '/api/v1/redirect':
                self.send_response(302); self.send_header('Location','/must-not-visit'); self.end_headers(); return
            if self.path == '/must-not-visit':
                traps.append(self.path)
            response = adapter.get(self.path, headers={'Cookie':self.headers.get('Cookie','')}, follow_redirects=False)
            self.send_response(response.status_code)
            for key,value in response.headers.items():
                if key.lower() not in ('content-length','content-encoding','connection','transfer-encoding'):
                    self.send_header(key,value)
            self.send_header('Content-Length',str(len(response.content))); self.end_headers()
            self.wfile.write(response.content)
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = Thread(target=server.serve_forever, kwargs={'poll_interval':.05},daemon=True); thread.start()
    client = ReadClient(f'http://127.0.0.1:{server.server_port}/api/v1',clients[0].cookies.get(auth.COOKIE_NAME),auth.COOKIE_NAME)
    try:
        data = [r for page in client.pages(limit=2) for r in page]
        assert [r['id'] for r in data] == [str(i) for i in reversed(expected)]
        assert client.get(data[0]['links']['self'])['id'] == data[0]['id']
        assert client.get('/openapi.json')['info']['version'] == '1.0.0'
        with pytest.raises(ApiFailure, match='HTTP 302'):
            client.get('/redirect')
        assert not traps
        st.revoke_login_session(c, auth.parse_token(client.session)['sid'])
        with pytest.raises(ApiFailure, match='HTTP 401'):
            client.get('/documents')
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); adapter.close()


def test_work_permission_sql_handles_revoked_grants_and_damaged_merge_chains(api):
    c, u, unit, clients, app = api
    source = document(c,u[0],unit)
    item = case(c,u[0],unit,source_document_id=source['id'])
    assert body(clients[1], '/work-items')['data']
    c.execute("UPDATE document_role_grant SET revoked_at='2026-10-22' WHERE user_id=? AND role='records'",(u[1]['id'],)); c.commit()
    assert body(clients[1], '/work-items')['data'] == []
    a = document(c,u[0],unit); b = document(c,u[0],unit)
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(a['id'],source['id']))
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(b['id'],a['id']))
    c.execute('UPDATE document SET canonical_id=? WHERE id=?',(a['id'],b['id'])); c.commit()
    assert body(clients[0], '/work-items')['data'] == []
    assert clients[0].get(f"/api/v1/documents/{source['id']}").status_code == 404
    assert clients[0].get(f"/api/v1/work-items/{item['id']}").status_code == 404


def test_work_page_sql_runs_on_system_sqlite(workspace, tmp_path):
    from pathlib import Path
    import sqlite3
    import subprocess
    import sys
    c, u, unit, _ = workspace
    source = document(c,u[0],unit)
    item = case(c,u[0],unit,source_document_id=source['id'])
    captured = []
    c.set_trace_callback(lambda sql: captured.append(sql) if sql.lstrip().startswith('SELECT wc.*') else None)
    try:
        for user in u:
            work_reads.page(c,user,limit=2)
    finally:
        c.set_trace_callback(None)
    assert len(captured) == 5
    cases = [{'sql':sql, 'expected':[list(row) for row in c.execute(sql)]} for sql in captured]
    database = tmp_path/'api-read-compat.db'
    with sqlite3.connect(database) as backup:
        c.backup(backup)
    corpus = tmp_path/'api-read-statements.json'
    corpus.write_text(json.dumps(cases))
    runner = """import json,sqlite3,sys
c=sqlite3.connect(sys.argv[1])
for case in json.load(open(sys.argv[2])):
    assert [list(r) for r in c.execute(case['sql'])]==case['expected']
print(sqlite3.sqlite_version)
"""
    executable = '/usr/bin/python3' if Path('/usr/bin/python3').exists() else sys.executable
    result = subprocess.run([executable,'-c',runner,str(database),str(corpus)], capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stderr


def test_task_reassignment_revokes_old_owner_without_waiting_for_session_expiry(api):
    c, u, unit, clients, app = api
    item = case(c,u[0],unit)
    task = propose(c,u[0],item,unit,u[2]['id'])
    task = advance(c,u[1],task,'confirm',owner_id=u[2]['id'])
    assert body(clients[2], f"/work-items/{item['id']}/tasks/{task['id']}")['status'] == 'todo'
    task = advance(c,u[1],task,'reassign',owner_id=u[3]['id'])
    assert clients[2].get(f"/api/v1/work-items/{item['id']}/tasks/{task['id']}").status_code == 404
    result = body(clients[3], f"/work-items/{item['id']}/tasks/{task['id']}")
    assert result['revision'] == task['revision'] and result['owner_id'] == str(u[3]['id'])


@pytest.mark.parametrize('session',['bad\r\nheader','private-é-token','token; other=cookie'])
def test_standalone_client_rejects_unsafe_cookie_text_without_echoing_it(session):
    from examples.read_api import ReadClient
    with pytest.raises(ValueError) as caught:
        ReadClient('https://office.example/api/v1',session)
    assert str(caught.value) == 'The session value is invalid.'
