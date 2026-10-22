"""A19 submission uses shared authority, exact revisions and atomic receipts."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import sqlite3
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

import auth
import documents as docs
import integration_operations as operations
import storage as st
import work
import work_blockers
import work_tasks
from tests.conftest import session_token
from tests.test_integration_read_api import api, body
from tests.test_integration_task_api import ready, headers, counts, post as acknowledge
from tests.test_work import workspace, case, propose, advance


def prepared(api, linked=False):
    item, task, source = ready(api, linked=linked)
    return item, advance(api[0], api[1][2], task, 'acknowledge'), source


def url(item, task):
    return f"/api/v1/work-items/{item['id']}/tasks/{task['id']}/submit"


def send(client, item, task, key=None, **changes):
    return client.post(url(item,task),headers=headers(client,key or str(uuid4())),
        json={'revision':task['revision'],'reason':'Ready for review',
              'submission':'Private output and evidence', **changes})


def current(c, user, item, task):
    return next(t for t in work_tasks.list_for_case(c,user,item['id']) if t['id']==task['id'])


def test_submission_is_atomic_private_and_review_remains_exact_version_in_the_ui(api):
    c,u,unit,clients,app = api
    item,task,_ = prepared(api)
    item = work.confirm_lead(c,u[1],item['id'],item['revision'],u[3]['id'],'Confirm reviewer')
    key = str(uuid4()); before = counts(c)
    response = send(clients[2],item,task,key)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt['action'] == 'submit' and receipt['status'] == 'succeeded'
    assert receipt['result_status'] == 'for_review' and receipt['result_revision'] == task['revision']+1
    assert 'no-store' in response.headers['cache-control']
    assert counts(c) == tuple(n+1 for n in before)
    updated = current(c,u[2],item,task)
    assert updated['status']=='for_review' and updated['submission']=='Private output and evidence'
    event = json.loads(c.execute("SELECT detail_json FROM work_event WHERE action='task_submit'").fetchone()[0])
    assert event['submission']==updated['submission'] and event['revision']==receipt['result_revision']
    assert 'Private output' not in json.dumps(receipt)
    task_read = body(clients[2],receipt['links']['task'].removeprefix('/api/v1'))
    assert task_read['status']=='for_review' and 'submission' not in task_read
    # The ordinary reviewer form sees the saved evidence. A stale UI acceptance
    # still fails, and current-version acceptance uses the existing task route.
    page = clients[3].get(f"/work/{item['id']}")
    assert page.status_code==200 and 'Private output and evidence' in page.text
    token = re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
    path = f"/work/{item['id']}/tasks/{task['id']}/accept"
    assert clients[3].post(path,data={'csrf':token,'revision':task['revision'],'reason':'Review'},follow_redirects=False).status_code==409
    assert clients[3].post(path,data={'csrf':token,'revision':updated['revision'],'reason':'Reviewed exact contribution'},follow_redirects=False).status_code==303
    assert current(c,u[2],item,task)['status']=='done'
    before = counts(c)
    assert send(clients[2],item,task,key).json()==receipt
    assert body(clients[2],'/operations/'+key)==receipt
    assert counts(c)==before


def test_acknowledgement_and_submission_cannot_share_a_committed_key(api):
    c,u,unit,clients,app = api
    item,task,_ = ready(api); key = str(uuid4())
    ack = acknowledge(clients[2],item,task,key).json()
    task = current(c,u[2],item,task); before=counts(c)
    response = send(clients[2],item,task,key)
    assert response.status_code==409 and response.json()['error']['code']=='idempotency_conflict'
    assert counts(c)==before
    assert body(clients[2],'/operations/'+key)==ack
    submitted=send(clients[2],item,task).json()
    assert submitted['action']=='submit' and submitted['result_status']=='for_review'


def test_key_reuse_binds_the_exact_submission_and_revision(api):
    c,u,unit,clients,app = api
    item,task,_=prepared(api); key=str(uuid4())
    receipt=send(clients[2],item,task,key).json(); before=counts(c)
    for changes in ({'submission':'Changed evidence'},{'reason':'Changed reason'},{'revision':task['revision']+1}):
        response=send(clients[2],item,task,key,**changes)
        assert response.status_code==409 and response.json()['error']['code']=='idempotency_conflict'
    assert counts(c)==before and body(clients[2],'/operations/'+key)==receipt


def test_stale_submission_refused_without_reserving_key_and_returned_work_resubmits(api):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); key=str(uuid4()); before=counts(c)
    response=send(clients[2],item,task,key,revision=task['revision']-1)
    assert response.status_code==409 and response.json()['error']['code']=='revision_conflict'
    assert counts(c)==before and clients[2].get('/api/v1/operations/'+key).status_code==404
    first=send(clients[2],item,task,key).json()
    updated=current(c,u[2],item,task)
    returned=advance(c,u[1],updated,'return')
    second=send(clients[2],item,returned,submission='Corrected evidence').json()
    assert second['action']=='submit' and second['result_revision']==returned['revision']+1
    assert second['id']!=first['id'] and body(clients[2],'/operations/'+key)==first
    assert current(c,u[2],item,task)['submission']=='Corrected evidence'


@pytest.mark.parametrize('blocker',['recorded','dependency','changed-decision'])
def test_submission_honours_current_workflow_blockers(api,blocker):
    c,u,unit,clients,app=api
    item,task,_=prepared(api)
    if blocker=='recorded':
        task=work_blockers.mutate(c,u[2],item['id'],task['id'],task['revision'],'block',
            {'reason':'Waiting for correction','followup_owner_id':u[2]['id'],'followup_date':'2026-10-25'})
    elif blocker=='dependency':
        upstream=propose(c,u[0],item,unit,u[2]['id'])
        upstream=advance(c,u[1],upstream,'confirm',owner_id=u[2]['id'])
        task=work_blockers.mutate(c,u[1],item['id'],task['id'],task['revision'],'dependency_add',
            {'reason':'Need prerequisite acceptance','prerequisite_id':upstream['id']})
    else:
        # A real changed-direction decision creates an unresolved review for the
        # task; submission cannot bypass that shared domain rule.
        import work_discussion, work_decisions
        message=work_discussion.post(c,u[0],item['id'],'Direction changed',task_id=task['id'])
        work_decisions.record(c,u[1],item['id'],message,1,
            {'kind':'change','body':'Review the changed requirements','affected_tasks':[task['id']],
             'task_revisions':{str(task['id']):task['revision']}})
        task=current(c,u[2],item,task)
    before=counts(c); response=send(clients[2],item,task)
    assert response.status_code==409 and response.json()['error']['code']=='action_unavailable'
    assert counts(c)==before and current(c,u[2],item,task)['status']=='in_progress'


@pytest.mark.parametrize('index',[0,3,4])
def test_unassigned_staff_creator_and_technical_admin_cannot_submit(api,index):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); before=counts(c)
    assert send(clients[index],item,task).status_code==404
    assert counts(c)==before


@pytest.mark.parametrize('switch',['work.enabled','documents.enabled'])
def test_disabled_writes_and_completed_cases_keep_submission_unchanged(api,switch):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); st.set_setting(c,switch,'0'); before=counts(c)
    assert send(clients[2],item,task).status_code==409
    assert counts(c)==before
    st.set_setting(c,switch,'1')
    c.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],));c.commit()
    assert send(clients[2],item,task).status_code==409 and counts(c)==before


def test_restricted_access_revokes_submission_and_receipt_reads(api):
    c,u,unit,clients,app=api
    item,task,source=prepared(api,linked=True); key=str(uuid4())
    assert send(clients[2],item,task,key).status_code==200
    docs.mutate(c,u[1],source['id'],source['revision'],'access',
                {'visibility':'restricted','viewers':[u[1]['id']],'reason':'Narrow access'})
    before=counts(c)
    assert send(clients[2],item,task,key).status_code==404
    assert clients[2].get('/api/v1/operations/'+key).status_code==404
    assert clients[1].get('/api/v1/operations/'+key).status_code==404
    assert counts(c)==before


def test_reassignment_revokes_old_submitter_access_to_saved_results(api):
    c,u,unit,clients,app=api
    item,task,_=prepared(api);key=str(uuid4())
    assert send(clients[2],item,task,key).status_code==200
    advance(c,u[1],current(c,u[2],item,task),'reassign',owner_id=u[3]['id'])
    before=counts(c)
    assert send(clients[2],item,task,key).status_code==404
    assert clients[2].get('/api/v1/operations/'+key).status_code==404
    assert counts(c)==before


def test_scoped_officer_submission_keeps_the_owner_and_requires_current_access(api):
    c,u,unit,clients,app=api
    item,task,_=prepared(api)
    response=send(clients[1],item,task)
    assert response.status_code==200,response.text
    assert current(c,u[2],item,task)['owner_id']==u[2]['id']
    assert clients[2].get('/api/v1/operations/'+response.json()['id']).status_code==404


@pytest.mark.parametrize('values',[{'submission':''},{'submission':'  '},{'submission':42},
    {'submission':'x'*8001},{'submission':'\ud800'},{'status':'done'},{'owner_id':'1'},{'revision':True}])
def test_submission_validation_is_strict_and_never_echoes_private_content(api,values):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); before=counts(c)
    data={'revision':task['revision'],'reason':'Private reason','submission':'SECRET EVIDENCE',**values}
    # Escaped JSON also exercises malformed Unicode that cannot be UTF-8 encoded.
    response=clients[2].post(url(item,task),headers={**headers(clients[2],str(uuid4())),'Content-Type':'application/json'},
                             content=json.dumps(data).encode())
    assert response.status_code==400 and 'SECRET EVIDENCE' not in response.text
    assert counts(c)==before


def test_large_utf8_output_is_bounded_without_reducing_the_domain_character_limit(api):
    c,u,unit,clients,app=api
    item,task,_=prepared(api)
    response=send(clients[2],item,task,reason='R'*2000,submission='😀'*8000)
    assert response.status_code==200,response.text
    assert current(c,u[2],item,task)['submission']=='😀'*8000
    before=counts(c)
    response=clients[2].post(url(item,task),headers={**headers(clients[2],str(uuid4())),'Content-Type':'application/json'},content=b'x'*65537)
    assert response.status_code==413 and counts(c)==before


def test_submission_authentication_origin_csrf_parent_scope_and_methods(api):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); before=counts(c)
    data={'revision':task['revision'],'reason':'Ready','submission':'Evidence'}
    h=headers(clients[2],str(uuid4()))
    assert clients[2].post(url(item,task),headers={**h,'Origin':'https://hostile.example'},json=data).status_code==403
    assert clients[2].post(url(item,task),headers={'Idempotency-Key':str(uuid4())},json=data).status_code==403
    assert clients[2].post(url(item,task),headers=h,content=b'raw').status_code==415
    assert clients[2].get(url(item,task)).status_code==405
    for action in ('accept','return','cancel'):
        assert clients[2].post(url(item,task).removesuffix('submit')+action,headers=h,json=data).status_code==405
    other=case(c,u[2],unit); before=counts(c)
    assert send(clients[2],other,task).status_code==404
    with TestClient(app.app,raise_server_exceptions=False) as anonymous:
        assert anonymous.post(url(item,task),headers=h,json=data).status_code==401
    assert counts(c)==before


def test_receipt_failure_rolls_back_submission_audit_and_work_state(api):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); before=counts(c); key=str(uuid4())
    c.execute("CREATE TRIGGER fail_submit_receipt BEFORE INSERT ON work_api_operation BEGIN SELECT RAISE(ABORT,'PRIVATE STORAGE ERROR'); END");c.commit()
    response=send(clients[2],item,task,key)
    assert response.status_code==500 and 'PRIVATE STORAGE' not in response.text
    assert counts(c)==before and current(c,u[2],item,task)['submission']==''
    c.execute('DROP TRIGGER fail_submit_receipt');c.commit()
    assert send(clients[2],item,task,key).status_code==200


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_submissions_commit_once(api,same_key):
    c,u,unit,clients,app=api
    item,task,_=prepared(api); before=counts(c); key=str(uuid4())
    payload=auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    def invoke(operation_id):
        conn=st.connect(app.DB)
        try:
            try:
                result=operations.submit(conn,payload,item['id'],task['id'],operation_id,task['revision'],'Ready','Evidence')
                return result['result_revision']
            except operations.OperationError as exc:return exc.code
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(invoke,[key,key if same_key else str(uuid4())]))
    assert results.count(task['revision']+1)==(2 if same_key else 1)
    if not same_key:assert 'revision_conflict' in results
    assert counts(c)==tuple(n+1 for n in before)


def test_legacy_acknowledgement_receipts_upgrade_without_rewrites_or_key_changes(api):
    c,u,unit,clients,app=api
    item,task,_=ready(api); key=str(uuid4()); reason='Legacy acknowledgement — salamat 👩🏽‍💻'
    digest=hashlib.sha256(json.dumps(['acknowledge',str(item['id']),str(task['id']),task['revision'],reason],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    updated=work_tasks.mutate(c,u[2],item['id'],task['id'],task['revision'],'acknowledge',{'reason':reason})
    c.executescript('''DROP TABLE work_api_operation;
        CREATE TABLE work_api_operation (
          actor_id INTEGER NOT NULL REFERENCES admin_user(id), operation_id TEXT NOT NULL,
          request_digest TEXT NOT NULL, case_id INTEGER NOT NULL REFERENCES work_case(id),
          task_id INTEGER NOT NULL REFERENCES work_task(id), result_revision INTEGER NOT NULL CHECK(result_revision>0),
          completed_at TEXT NOT NULL, PRIMARY KEY(actor_id,operation_id));
        CREATE TRIGGER work_api_operation_no_update BEFORE UPDATE ON work_api_operation
          BEGIN SELECT RAISE(ABORT,'API operation receipts are immutable'); END;
        CREATE TRIGGER work_api_operation_no_delete BEFORE DELETE ON work_api_operation
          BEGIN SELECT RAISE(ABORT,'API operation receipts are retained'); END;''')
    original=(u[2]['id'],key,digest,item['id'],task['id'],updated['revision'],'2026-10-22T10:00:00')
    c.execute('INSERT INTO work_api_operation VALUES(?,?,?,?,?,?,?)',original);c.commit()
    st.init_db(c);st.init_db(c)
    assert c.execute('SELECT actor_id,operation_id,request_digest,case_id,task_id,result_revision,completed_at FROM work_api_operation').fetchone()==original
    receipt=body(clients[2],'/operations/'+key)
    assert receipt['action']=='acknowledge' and receipt['result_status']=='in_progress'
    assert acknowledge(clients[2],item,task,key,reason=reason).json()==receipt
    assert send(clients[2],item,updated).json()['action']=='submit'
    for statement in ('UPDATE work_api_operation SET action=\'submit\'','DELETE FROM work_api_operation'):
        with pytest.raises(sqlite3.IntegrityError):c.execute(statement)
        c.rollback()
