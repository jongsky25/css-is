"""A19 explicit acknowledgement, serialized authority and durable recovery."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

import auth
import documents as docs
import integration_operations as operations
import storage as st
import work_tasks
from tests.conftest import session_token
from tests.test_integration_read_api import api, body
from tests.test_work import workspace, case, document, propose, advance


def ready(api, linked=False):
    c, users, unit, clients, app = api
    source = document(c, users[0], unit) if linked else None
    if source:
        source = docs.mutate(c, users[1], source['id'], source['revision'], 'verify',
                             {'verification': 'verified', 'reason': 'Checked'})
    item = case(c, users[0], unit, **({'source_document_id': source['id']} if source else {}))
    task = propose(c, users[0], item, unit, users[2]['id'])
    task = advance(c, users[1], task, 'confirm', owner_id=users[2]['id'])
    return item, task, source


def url(item, task):
    return f"/api/v1/work-items/{item['id']}/tasks/{task['id']}/acknowledge"


def headers(client, key):
    return {'X-CSRF-Token': body(client, '/write-context')['csrf_token'], 'Idempotency-Key': key}


def post(client, item, task, key, **values):
    return client.post(url(item, task), headers=headers(client, key),
                       json={'revision': task['revision'], 'reason': 'Starting my assigned contribution', **values})


def counts(c):
    return tuple(c.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                 for table in ('work_event', 'audit_log', 'work_api_operation'))


def test_acknowledgement_records_one_atomic_event_and_receipt_and_replays_after_ui_edits(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api)
    before = counts(c)
    key = str(uuid4())
    response = post(clients[2], item, task, key)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['status'] == 'succeeded' and saved['result_status'] == 'in_progress'
    assert saved['id'] == key and saved['result_revision'] == task['revision'] + 1
    assert saved['work_item_id'] == str(item['id']) and saved['task_id'] == str(task['id'])
    assert set(saved) == {'id','action','status','work_item_id','task_id','result_revision','result_status','completed_at','links'}
    assert 'no-store' in response.headers['cache-control']
    assert counts(c) == tuple(x + 1 for x in before)
    event = json.loads(c.execute("SELECT detail_json FROM work_event WHERE action='task_acknowledge'").fetchone()[0])
    assert event['reason'] == 'Starting my assigned contribution' and event['revision'] == saved['result_revision']
    current = dict(zip([x[0] for x in c.execute('SELECT * FROM work_task').description], c.execute('SELECT * FROM work_task').fetchone()))
    advance(c, u[2], current, 'submit', submission='Newer submitted evidence must stay private')
    before_retry = counts(c)
    assert post(clients[2], item, task, key).json() == saved
    assert body(clients[2], '/operations/' + key) == saved
    assert counts(c) == before_retry
    current = body(clients[2], saved['links']['task'].removeprefix('/api/v1'))
    assert current['status'] == 'for_review' and current['revision'] > saved['result_revision']
    assert 'Newer submitted evidence' not in json.dumps(saved)


def test_revision_conflict_and_key_reuse_do_not_mutate_or_consume_a_failed_key(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api)
    key = str(uuid4()); before = counts(c)
    rejected = post(clients[2], item, task, key, revision=task['revision']-1)
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'revision_conflict'
    assert counts(c) == before
    assert clients[2].get('/api/v1/operations/' + key).status_code == 404
    assert post(clients[2], item, task, key).status_code == 200
    before = counts(c)
    rejected = post(clients[2], item, task, key, reason='Different request')
    assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'idempotency_conflict'
    assert counts(c) == before
    rejected = post(clients[2], item, task, str(uuid4()), revision=task['revision']+1)
    assert rejected.status_code == 404  # State no longer permits acknowledgement.
    assert counts(c) == before


@pytest.mark.parametrize('user_index', [0, 3, 4])
def test_creator_other_staff_and_technical_admin_cannot_acknowledge(api, user_index):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); before = counts(c)
    response = post(clients[user_index], item, task, str(uuid4()))
    assert response.status_code == 404
    assert counts(c) == before


def test_scoped_officer_retains_existing_authority_and_receipts_are_actor_owned(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4())
    assert post(clients[1], item, task, key).status_code == 200
    assert body(clients[1], '/operations/' + key)['status'] == 'succeeded'
    for client in (clients[0], clients[2], clients[4]):
        missing = client.get('/api/v1/operations/' + str(uuid4()))
        denied = client.get('/api/v1/operations/' + key)
        assert denied.status_code == missing.status_code == 404
        assert denied.json() == missing.json()


def test_receipt_lookup_and_retry_obey_revoked_linked_document_access(api):
    c, u, unit, clients, app = api
    item, task, source = ready(api, linked=True); key = str(uuid4())
    assert post(clients[2], item, task, key).status_code == 200
    docs.mutate(c, u[1], source['id'], source['revision'], 'access',
                {'visibility':'restricted','viewers':[u[1]['id']],'reason':'Revoke'})
    before = counts(c)
    assert clients[2].get('/api/v1/operations/' + key).status_code == 404
    assert post(clients[2], item, task, key).status_code == 404
    assert counts(c) == before


def test_reassignment_revokes_prior_owner_before_new_write_or_receipt_lookup(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4())
    saved = post(clients[2], item, task, key).json()
    current = {**task, 'revision':saved['result_revision'], 'status':'in_progress'}
    advance(c, u[1], current, 'reassign', owner_id=u[3]['id'])
    before = counts(c)
    assert clients[2].get('/api/v1/operations/' + key).status_code == 404
    assert post(clients[2], item, task, key).status_code == 404
    assert counts(c) == before


@pytest.mark.parametrize('switch', ['documents.enabled','work.enabled'])
def test_disabled_switch_rejects_new_effect_but_keeps_existing_receipt_readable(api, switch):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4())
    st.set_setting(c, switch, '0'); before = counts(c)
    assert post(clients[2], item, task, key).status_code == 409
    assert counts(c) == before
    st.set_setting(c, switch, '1')
    saved = post(clients[2], item, task, key).json()
    st.set_setting(c, switch, '0'); before = counts(c)
    assert post(clients[2], item, task, key).json() == saved
    assert body(clients[2], '/operations/' + key) == saved
    assert counts(c) == before


def test_receipt_or_audit_storage_failure_rolls_back_task_and_all_effects(api, monkeypatch):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4()); before = counts(c)
    c.execute("CREATE TRIGGER fail_api_receipt BEFORE INSERT ON work_api_operation BEGIN SELECT RAISE(ABORT,'PRIVATE FAILURE'); END"); c.commit()
    response = post(clients[2], item, task, key)
    assert response.status_code == 500 and 'PRIVATE' not in response.text
    assert counts(c) == before
    assert c.execute('SELECT status,revision FROM work_task WHERE id=?',(task['id'],)).fetchone() == ('todo', task['revision'])
    c.execute('DROP TRIGGER fail_api_receipt'); c.commit()
    def fail(*a, **kw): raise RuntimeError('PRIVATE AUDIT FAILURE')
    with monkeypatch.context() as patch:
        patch.setattr(st, 'audit', fail)
        assert post(clients[2], item, task, key).status_code == 500
    assert counts(c) == before
    assert post(clients[2], item, task, key).status_code == 200


@pytest.mark.parametrize('which', ['origin', 'csrf', 'both', 'cross-site', 'duplicate-origin', 'duplicate-csrf', 'missing-origin', 'missing-csrf'])
def test_cookie_write_verification_fails_closed(api, which):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); client = clients[2]; key = str(uuid4()); before = counts(c)
    h = headers(client, key)
    with TestClient(app.app, raise_server_exceptions=False) as attacker:
        attacker.cookies.set(auth.COOKIE_NAME, client.cookies.get(auth.COOKIE_NAME))
        attacker.headers.pop('origin', None)
        if which in ('origin', 'both'): h['Origin'] = 'https://attacker.example'
        else: h['Origin'] = 'http://testserver'
        if which in ('csrf', 'both'): h['X-CSRF-Token'] = 'bad'
        if which == 'missing-origin': h.pop('Origin')
        if which == 'missing-csrf': h.pop('X-CSRF-Token')
        if which == 'cross-site': h['Sec-Fetch-Site'] = 'cross-site'
        pairs = list(h.items())
        if which == 'duplicate-origin': pairs.append(('Origin','http://testserver'))
        if which == 'duplicate-csrf': pairs.append(('X-CSRF-Token',h['X-CSRF-Token']))
        response = attacker.post(url(item, task), headers=pairs, json={'revision':task['revision'],'reason':'Start'})
    assert response.status_code == 403 and 'no-store' in response.headers['cache-control']
    assert counts(c) == before


@pytest.mark.parametrize('values', [{'revision':True}, {'revision':'2'}, {'revision':0}, {'revision':9223372036854775807},
    {'reason':''}, {'reason':'   '}, {'reason':42}, {'reason':'x'*2001}, {'actor_id':'1'}, {'status':'done'}])
def test_invalid_json_fields_cannot_change_records(api, values):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); before = counts(c)
    response = post(clients[2], item, task, str(uuid4()), **values)
    assert response.status_code == 400
    assert counts(c) == before


@pytest.mark.parametrize('data,status', [(b'{"revision":2,"revision":3,"reason":"x"}',400),
    (b'[]',400),(b'{',400),(b'null',400),(b'x'*8193,413)])
def test_invalid_or_oversized_raw_requests(api, data, status):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); before = counts(c)
    h = {**headers(clients[2], str(uuid4())), 'Content-Type':'application/json'}
    response = clients[2].post(url(item,task), headers=h, content=data)
    assert response.status_code == status, response.text
    assert counts(c) == before


def test_missing_headers_media_parent_scope_and_methods(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); before = counts(c); client = clients[2]
    key = str(uuid4()); h = headers(client, key)
    assert client.post(url(item,task), headers=h, data={'revision':task['revision'],'reason':'Start'}).status_code == 415
    assert client.post(url(item,task), headers={**h,'Idempotency-Key':'bad'},json={}).status_code == 400
    assert client.post(url(item,task), headers={'X-CSRF-Token':h['X-CSRF-Token']},json={}).status_code == 400
    other = case(c,u[2],unit)
    before = counts(c)
    assert post(client,other,task,key).status_code == 404
    assert client.get(url(item,task)).status_code == 405
    assert client.patch(url(item,task),headers=h,json={}).status_code == 405
    assert client.post('/api/v1/operations/'+key,headers=h,json={}).status_code == 405
    assert client.post(url(item,task)+'?role=admin',headers=h,json={}).status_code == 400
    assert counts(c) == before


def test_registered_session_is_rechecked_after_parent_authentication(api, monkeypatch):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4()); h = headers(clients[2],key)
    original = app._user_from_request
    def revoke_after_auth(request):
        user = original(request)
        if request.method == 'POST':
            conn = st.connect(app.DB)
            try:
                st.revoke_login_session(conn, auth.parse_token(request.cookies[auth.COOKIE_NAME])['sid'])
            finally:
                conn.close()
        return user
    monkeypatch.setattr(app,'_user_from_request',revoke_after_auth)
    before = counts(c)
    response = clients[2].post(url(item,task),headers=h,json={'revision':task['revision'],'reason':'Start'})
    assert response.status_code == 401
    assert counts(c) == before


def test_concurrent_identical_requests_commit_once_and_durable_receipts_survive_reconnect(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4()); before = counts(c)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    def invoke():
        conn = st.connect(app.DB)
        try: return operations.acknowledge(conn,payload,item['id'],task['id'],key,task['revision'],'Start')
        finally: conn.close()
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: invoke(),range(3)))
    assert results[0] == results[1] == results[2]
    assert counts(c) == tuple(x+1 for x in before)
    st.init_db(c)  # Repeated startup preserves the receipt.
    assert body(clients[2],'/operations/'+key)['result_revision'] == task['revision']+1
    for sql in ('UPDATE work_api_operation SET result_revision=100','DELETE FROM work_api_operation'):
        with pytest.raises(sqlite3.IntegrityError): c.execute(sql)
        c.rollback()


def test_concurrent_different_keys_cannot_both_change_the_same_revision(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); before = counts(c)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    def invoke(key):
        conn = st.connect(app.DB)
        try:
            try:
                operations.acknowledge(conn,payload,item['id'],task['id'],key,task['revision'],'Start')
                return 'succeeded'
            except operations.OperationError as exc:
                return exc.code
        finally: conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(invoke,[str(uuid4()),str(uuid4())]))
    assert sorted(results) == ['revision_conflict','succeeded']
    assert counts(c) == tuple(x+1 for x in before)


def test_independent_client_recovers_a_committed_write_after_a_lost_response_over_real_http(api):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from examples.read_api import TaskClient, ApiFailure
    c, u, unit, clients, app = api
    item, task, _ = ready(api); before = counts(c); key = str(uuid4())
    attempts = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self): self.forward('GET')
        def do_POST(self): self.forward('POST')
        def forward(self, method):
            incoming = {name:value for name,value in self.headers.items()
                        if name.lower() in ('cookie','origin','x-csrf-token','idempotency-key','content-type')}
            data = self.rfile.read(int(self.headers.get('Content-Length','0'))) if method == 'POST' else None
            response = adapter.request(method,self.path,headers=incoming,content=data,follow_redirects=False)
            if method == 'POST':
                attempts.append(response.status_code)
                if len(attempts) == 1:
                    # The real application committed, but the client sees no
                    # successful response. No automatic second POST is allowed.
                    self.send_response(502); self.send_header('Content-Length','0'); self.end_headers(); return
            self.send_response(response.status_code)
            self.send_header('Content-Type',response.headers.get('content-type','application/json'))
            self.send_header('Content-Length',str(len(response.content))); self.end_headers()
            self.wfile.write(response.content)
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    base = f'http://127.0.0.1:{server.server_port}'
    adapter = TestClient(app.app,base_url=base,raise_server_exceptions=False)
    thread = Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True); thread.start()
    client = TaskClient(base+'/api/v1',clients[2].cookies.get(auth.COOKIE_NAME))
    args = {'revision':task['revision'],'reason':'Start','operation_id':key}
    try:
        with pytest.raises(ApiFailure,match='HTTP 502'):
            client.acknowledge(str(item['id']),str(task['id']),**args)
        assert attempts == [200]
        result = client.operation(key)
        assert result['status'] == 'succeeded'
        assert client.acknowledge(str(item['id']),str(task['id']),**args) == result
        assert attempts == [200,200]
        assert counts(c) == tuple(x+1 for x in before)
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2); adapter.close()


def test_operation_key_is_bound_to_target_and_not_shared_between_actors(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); another = propose(c,u[0],item,unit,u[2]['id'])
    another = advance(c,u[1],another,'confirm',owner_id=u[2]['id'])
    key = str(uuid4())
    assert post(clients[2],item,task,key).status_code == 200
    before = counts(c)
    response = post(clients[2],item,another,key)
    assert response.status_code == 409 and response.json()['error']['code'] == 'idempotency_conflict'
    assert counts(c) == before
    # Identical UUID text for another actor is an independent key. It does not
    # reveal or replay the first person's acknowledgement.
    assert post(clients[1],item,another,key).status_code == 200
    assert body(clients[1],'/operations/'+key)['task_id'] == str(another['id'])
    assert body(clients[2],'/operations/'+key)['task_id'] == str(task['id'])


def test_token_is_session_bound_and_deployment_origin_is_server_configured(api, monkeypatch):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4()); before = counts(c)
    h = headers(clients[1],key)
    assert clients[2].post(url(item,task),headers=h,json={'revision':task['revision'],'reason':'Start'}).status_code == 403
    h = headers(clients[2],key)
    monkeypatch.setenv('CSS_BASE_URL','https://office.example')
    data = {'revision':task['revision'],'reason':'Start'}
    assert clients[2].post(url(item,task),headers=h,json=data).status_code == 403
    assert counts(c) == before
    h['Origin'] = 'https://office.example'
    assert clients[2].post(url(item,task),headers=h,json=data).status_code == 200


def test_duplicate_key_and_invalid_unicode_are_rejected_without_effects(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4()); before = counts(c)
    h = headers(clients[2],key)
    pairs = [*h.items(),('Idempotency-Key',key)]
    assert clients[2].post(url(item,task),headers=pairs,json={'revision':task['revision'],'reason':'Start'}).status_code == 400
    h['Content-Type'] = 'application/json'
    response = clients[2].post(url(item,task),headers=h,content=br'{"revision":2,"reason":"\uD800"}')
    assert response.status_code == 400
    assert counts(c) == before


def test_real_writer_contention_returns_retryable_json_without_a_partial_change(api, monkeypatch):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4()); before = counts(c)
    h = headers(clients[2],key)
    original = st.connect
    def short_wait(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.execute('PRAGMA busy_timeout=1')
        return conn
    monkeypatch.setattr(st,'connect',short_wait)
    c.execute('BEGIN IMMEDIATE')
    try:
        response = clients[2].post(url(item,task),headers=h,json={'revision':task['revision'],'reason':'Start'})
        assert response.status_code == 503, response.text
        assert response.headers['retry-after'] == '1'
        assert response.json()['error']['code'] == 'temporarily_unavailable'
    finally: c.rollback()
    assert counts(c) == before
    assert post(clients[2],item,task,key,reason='Start').status_code == 200


def test_completed_case_and_lead_without_task_authority_are_refused(api):
    import work
    c, u, unit, clients, app = api
    item, task, _ = ready(api)
    item = work.confirm_lead(c,u[1],item['id'],item['revision'],u[3]['id'],'Confirm lead')
    before = counts(c)
    assert post(clients[3],item,task,str(uuid4())).status_code == 404
    assert counts(c) == before
    c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],)); c.commit()
    before = counts(c)
    response = post(clients[2],item,task,str(uuid4()))
    assert response.status_code == 409 and response.json()['error']['code'] == 'action_unavailable'
    assert counts(c) == before


def test_same_actor_can_recover_after_new_login_but_anonymous_requests_cannot_write(api):
    c, u, unit, clients, app = api
    item, task, _ = ready(api); key = str(uuid4())
    result = post(clients[2],item,task,key).json(); before = counts(c)
    with TestClient(app.app,raise_server_exceptions=False) as other:
        assert other.post(url(item,task),json={'revision':task['revision'],'reason':'Start'}).status_code == 401
        assert other.get('/api/v1/operations/'+key).status_code == 401
        other.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
        assert body(other,'/operations/'+key) == result
    assert counts(c) == before


def test_uncertain_legacy_document_operation_is_a_workflow_blocker_not_a_stale_task(api):
    from tests.test_work import legacy_setup, migrate
    import work
    c, u, unit, clients, app = api
    doc = legacy_setup(c,u,unit)
    report = migrate(c,u,doc)
    item = work.raw(c,report['case_id'])
    task = work_tasks.list_for_case(c,u[3],item['id'])[0]
    c.execute('''INSERT INTO document_job(id,document_id,actor_id,kind,payload_json,state,created_at,updated_at)
        VALUES(?,?,?,'dispatch','{}','unknown','2026-10-22','2026-10-22')''',
        (str(uuid4()),doc['id'],u[1]['id'])); c.commit()
    before = counts(c)
    response = post(clients[3],item,task,str(uuid4()))
    assert response.status_code == 409, response.text
    assert response.json()['error']['code'] == 'action_unavailable'
    assert 'related workflow operation' in response.json()['error']['message']
    assert counts(c) == before
