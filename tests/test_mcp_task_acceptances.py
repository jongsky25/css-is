"""M4.1 exact submitted-output review, current named lead and separation of duties."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents as docs
import documents_permissions as permissions
from documents_storage import rows
import mcp_actions
import mcp_auth
import mcp_read
import mcp_task_acceptances as service
import task_acceptance as acceptance
import mailer
import storage as st
import work
import work_blockers
import work_tasks
from tests.test_mcp_task_submissions import pilot as submission_pilot,form,ORIGIN,RESOURCE,OUTPUT
from tests.test_integration_read_api import api
from tests.test_work import workspace

KEY='task-acceptance-operation-001'
REASON='REVIEW_DECISION <script>untrusted</script> — Checked the saved evidence.'
SUBMIT_NOTE='ORIGINAL_SUBMISSION_NOTE <script>untrusted</script>'


@pytest.fixture
def pilot(submission_pilot,monkeypatch):
    conn,users,clients,app,item,task,old_token=submission_pilot
    task=work_tasks.mutate(conn,users[2],item['id'],task['id'],task['revision'],'submit',{'submission':OUTPUT,'reason':SUBMIT_NOTE})
    monkeypatch.setenv(service.FLAG,'1');monkeypatch.delenv('CSS_MCP_TASK_SUBMISSIONS_ENABLED',raising=False)
    token=mcp_auth.Provider._tokens(conn,'submission-test',users[3]['id'],[service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,item,task,token


def fields(pilot,**changes):
    _,case,task,info=acceptance.source(pilot[0],pilot[1][3],pilot[4]['id'],pilot[5]['id'])
    return {'work_item_id':case['id'],'task_id':task['id'],'revision':task['revision'],
            'expected_revision':info['expected_revision'],'reason':REASON,**changes}


def prepare(pilot,key=KEY,data=None):
    return service.prepare(pilot[0],pilot[6].access_token,RESOURCE,ORIGIN,key,data or fields(pilot))


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][3].cookies.get(auth.COOKIE_NAME))
    p=service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=p['preview_digest'])


def current(pilot):
    return rows(pilot[0],'SELECT * FROM work_task WHERE id=?',(pilot[5]['id'],))[0]


def test_exact_review_native_acceptance_receipt_and_later_resubmission(pilot,monkeypatch):
    conn,users,clients,app,item,task,token=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**k:pytest.fail('No direct mail from task acceptance'))
    context=service.read_context(conn,token.access_token,RESOURCE,ORIGIN,item['id'],task['id'])
    assert context['revision']==task['revision'] and context['result_status_if_confirmed']=='done'
    assert all(text not in json.dumps(context) for text in (OUTPUT,SUBMIT_NOTE,REASON,users[2]['username']))
    original=fields(pilot);preview=prepare(pilot,data=original)
    assert prepare(pilot,data=original)==preview and 'PRIVATE_OUTPUT' not in json.dumps(preview)
    assert current(pilot)['status']=='for_review'
    path='/account/integrations/mcp/task-acceptances/'+KEY;page=clients[3].get(path)
    assert page.status_code==200 and all(t in page.text for t in ('PRIVATE_OUTPUT','ORIGINAL_SUBMISSION_NOTE','REVIEW_DECISION',task['expected_output']))
    assert '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert 'For review → Done' in page.text and 'confirmed work-item lead' in page.text
    assert clients[3].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    result=service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['result_status']=='done' and result['result_revision']==task['revision']+1
    assert result['notification_status']=='no_direct_send' and result['next_actor']['lead_id']==str(users[3]['id'])
    assert 'PRIVATE_OUTPUT' not in json.dumps(result) and 'REVIEW_DECISION' not in json.dumps(result)
    updated=current(pilot)
    assert updated['status']=='done' and updated['submission']==OUTPUT and updated['owner_id']==task['owner_id'] and updated['due_date']==task['due_date']
    event=conn.execute("SELECT actor_id,detail_json FROM work_event WHERE action='task_accept'").fetchone()
    assert event[0]==users[3]['id'] and json.loads(event[1])['reason']==REASON
    assert work.raw(conn,item['id'])['status']!='completed'
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM email_log').fetchone()[0]==0
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_task_acceptances').fetchone()==(None,None)
    reopened=work_tasks.mutate(conn,users[3],item['id'],task['id'],updated['revision'],'reopen',{'reason':'Ordinary renewed work'})
    renewed=work_tasks.mutate(conn,users[2],item['id'],task['id'],reopened['revision'],'submit',{'reason':'New evidence','submission':'Later submission must survive'})
    assert prepare(pilot,data=original)==result
    assert current(pilot)['submission']=='Later submission must survive' and current(pilot)['status']=='for_review'
    assert clients[3].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert current(pilot)['revision']==renewed['revision']
    # A genuinely new submission cycle needs fresh exact context and another human decision.
    prepare(pilot,'new-acceptance-cycle-001');confirm(pilot,'new-acceptance-cycle-001')
    assert current(pilot)['status']=='done'
    assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_accept'").fetchone()[0]==2


@pytest.mark.parametrize('change',['revision','output','lead','owner','case','blocker','closed','disabled','documents_disabled','scope','revoked','expired','payload','snapshot','switch','global_switch','inactive_owner'])
def test_current_review_context_and_gates_rechecked(pilot,monkeypatch,change):
    conn,users,clients,app,item,task,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/task-acceptances/'+KEY;page=clients[3].get(path)
    if change=='revision':conn.execute('UPDATE work_task SET revision=revision+1 WHERE id=?',(task['id'],))
    elif change=='output':conn.execute("UPDATE work_task SET submission='Unreviewed changed output' WHERE id=?",(task['id'],))
    elif change=='lead':work.confirm_lead(conn,users[1],item['id'],item['revision'],users[1]['id'],'New lead')
    elif change=='owner':conn.execute('UPDATE work_task SET owner_id=? WHERE id=?',(users[0]['id'],task['id']))
    elif change=='case':conn.execute("UPDATE work_case SET outcome='New outcome' WHERE id=?",(item['id'],))
    elif change=='blocker':work_blockers.mutate(conn,users[3],item['id'],task['id'],task['revision'],'block',{'reason':'Unresolved blocker','followup_owner_id':users[2]['id'],'followup_date':'2030-01-01'})
    elif change=='closed':conn.execute("UPDATE work_case SET status='completed' WHERE id=?",(item['id'],))
    elif change=='disabled':st.set_setting(conn,'work.enabled','0')
    elif change=='documents_disabled':st.set_setting(conn,'documents.enabled','0')
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"work:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_task_acceptances SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_task_acceptances SET payload_json=?',(json.dumps({**original,'reason':'Tampered decision'}),))
    elif change=='snapshot':conn.execute('UPDATE mcp_task_acceptances SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    elif change=='inactive_owner':conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[2]['id'],))
    else:monkeypatch.setenv(service.FLAG,'0')
    conn.commit()
    assert clients[3].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_accept'").fetchone()[0]==0
    assert current(pilot)['status']=='for_review'


@pytest.mark.parametrize('changes',[
    {'task_id':True},{'work_item_id':'1'},{'revision':0},{'expected_revision':'guess'},
    {'reason':''},{'reason':'x'*2001},{'reason':'bad\x00text'},
    {'submission':'Override evidence'},{'owner_id':1},{'status':'done'},{'action':'return'},
    {'approve_document':True},{'send_email':True},
])
def test_strict_fields_no_evidence_or_decision_override(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changes))


def test_only_confirmed_lead_not_owner_submitter_officer_or_admin(pilot):
    conn,users,clients,app,item,task,token=pilot
    for idx in (0,1,2,4):
        granted=mcp_auth.Provider._tokens(conn,'submission-test',users[idx]['id'],[service.SCOPE],RESOURCE);conn.commit()
        with pytest.raises(permissions.Denied):service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,item['id'],task['id'])
    # Even a confirmed lead cannot review their own assigned contribution.
    item=work.confirm_lead(conn,users[1],item['id'],item['revision'],users[2]['id'],'Contributor now lead')
    with pytest.raises(permissions.Denied):acceptance.source(conn,users[2],item['id'],task['id'])
    # An officer can submit for another owner in the normal UI, but cannot then accept via MCP.
    item=work.confirm_lead(conn,users[1],item['id'],item['revision'],users[1]['id'],'Officer lead')
    returned=work_tasks.mutate(conn,users[1],item['id'],task['id'],task['revision'],'return',{'reason':'Review again'})
    submitted=work_tasks.mutate(conn,users[1],item['id'],task['id'],returned['revision'],'submit',{'reason':'Intervened submission','submission':'Owner output'})
    with pytest.raises(permissions.Denied):acceptance.source(conn,users[1],item['id'],submitted['id'])


def test_csrf_connection_session_security_and_atomic_rollback(pilot,monkeypatch):
    conn,users,clients,app,item,task,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/task-acceptances/'+KEY;page=clients[3].get(path)
    assert clients[1].get(path).status_code==404
    assert clients[3].post(path,data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[3].post(path,data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[3].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='different'):prepare(pilot,data={**original,'reason':'Other'})
    fresh=mcp_auth.Provider._tokens(conn,'submission-test',users[3]['id'],[service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    saved=st.audit
    def fail(c,actor,action,**kw):
        if action=='integration_action_complete':raise RuntimeError('Synthetic final audit failure')
        return saved(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):confirm(pilot)
    assert current(pilot)['status']=='for_review' and current(pilot)['revision']==task['revision']
    assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_accept'").fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_task_acceptances').fetchone()[0] is None
    with pytest.raises(RuntimeError,match='caller-owned'):acceptance.accept_in_transaction(conn,users[3],**original)
    payload=auth.parse_token(clients[3].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):service.browser(conn,payload,RESOURCE,ORIGIN,KEY)


def test_two_keys_and_same_key_races_accept_once(pilot):
    conn,users,clients,app,item,task,token=pilot;original=fields(pilot)
    keys=(KEY,'competing-acceptance-key-001')
    for key in keys:prepare(pilot,key,original)
    payload=auth.parse_token(clients[3].cookies.get(auth.COOKIE_NAME))
    digests={key:service.browser(conn,payload,RESOURCE,ORIGIN,key)['preview_digest'] for key in keys}
    def worker(key):
        c=app.get_conn()
        try:return service.browser(c,payload,RESOURCE,ORIGIN,key,confirm_digest=digests[key])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,keys))
    assert sorted(results)==['completed','conflict'];winner=keys[results.index('completed')]
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(worker,(winner,winner)))==['completed','completed']
    assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_accept'").fetchone()[0]==1


def test_source_identity_recovery_lead_loss_and_retention(pilot,monkeypatch):
    conn,users,clients,app,item,task,token=pilot;original=fields(pilot);prepare(pilot,data=original);confirm(pilot)
    conn.execute("UPDATE work_task SET created_at='reused source' WHERE id=?",(task['id'],));conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    conn.execute('UPDATE work_task SET created_at=? WHERE id=?',(task['created_at'],task['id']));conn.commit()
    assert service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)['result_status']=='done'
    work.confirm_lead(conn,users[1],item['id'],item['revision'],users[1]['id'],'Lead changed after acceptance')
    with pytest.raises(permissions.Denied):service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)


def test_capacity_and_expired_text_cleanup_with_disabled_flag(pilot,monkeypatch):
    conn,users,clients,app,item,task,token=pilot
    for i in range(50):prepare(pilot,'acceptance-capacity-key-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'acceptance-capacity-overflow')
    conn.execute('UPDATE mcp_task_acceptances SET expires_at=1');conn.commit();monkeypatch.setenv(service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError):service.recover(conn,token.access_token,RESOURCE,ORIGIN,'acceptance-capacity-key-0')
    assert conn.execute('SELECT COUNT(*) FROM mcp_task_acceptances WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_task_acceptances').fetchone()[0]==50


def test_sdk_and_mobile_confirmation_without_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,item,task,token=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='submission-test',scopes=[service.SCOPE],resource=RESOURCE,subject=str(users[3]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        result=await server.call_tool('prepare_task_acceptance',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_OUTPUT' not in str(result)
        access.scopes=['work:task:submit']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_task_acceptance',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[3],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/task-acceptances/'+KEY)
                expect(page.get_by_role('heading',name='Accept this exact submitted contribution?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: accept reviewed contribution',exact=True).click()
                expect(page.get_by_role('heading',name='Submitted task accepted',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_separate_submitting_officer_must_remain_active(pilot):
    conn,users,clients,app,item,task,token=pilot
    returned=work_tasks.mutate(conn,users[3],item['id'],task['id'],task['revision'],'return',{'reason':'Resubmit through officer'})
    work_tasks.mutate(conn,users[1],item['id'],task['id'],returned['revision'],'submit',{'reason':'Officer intervention','submission':OUTPUT})
    prepare(pilot)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[1]['id'],));conn.commit()
    with pytest.raises(mcp_actions.ActionError):confirm(pilot)
    assert current(pilot)['status']=='for_review'


def test_exact_dependency_effect_and_changed_downstream_preview(pilot):
    from tests.test_work import propose,advance
    conn,users,clients,app,item,task,token=pilot
    dependent=propose(conn,users[0],item,item['unit_id'],users[0]['id'])
    dependent=advance(conn,users[1],dependent,'confirm',owner_id=users[0]['id'])
    dependent=advance(conn,users[0],dependent,'acknowledge')
    dependent=work_blockers.mutate(conn,users[3],item['id'],dependent['id'],dependent['revision'],'dependency_add',{'prerequisite_id':task['id'],'reason':'Needs this evidence'})
    assert work_blockers.waiting(conn,dependent)
    prepare(pilot);page=clients[3].get('/account/integrations/mcp/task-acceptances/'+KEY)
    assert 'Active contributions depending on this task' in page.text
    confirm(pilot)
    assert not work_blockers.waiting(conn,dependent)
    assert rows(conn,'SELECT * FROM work_task WHERE id=?',(dependent['id'],))[0]['status']=='in_progress'


def test_linked_record_access_loss_blocks_decision(pilot):
    from tests.test_work import document
    conn,users,clients,app,item,task,token=pilot
    doc=document(conn,users[0],item['unit_id'])
    doc=docs.mutate(conn,users[1],doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Verified source'})
    item=work.link_document(conn,users[0],item['id'],item['revision'],doc['id'])
    prepare(pilot)
    docs.mutate(conn,users[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[users[0]['id'],users[2]['id']],'reason':'Withdraw lead source access'})
    with pytest.raises(permissions.Denied):confirm(pilot)
    assert current(pilot)['status']=='for_review'


def test_downstream_review_failure_rolls_back_entire_decision(pilot,monkeypatch):
    import work_review
    conn,users,clients,app,item,task,token=pilot;prepare(pilot)
    monkeypatch.setattr(work_review,'invalidate',lambda *a,**k:(_ for _ in ()).throw(docs.Conflict('Synthetic uncertain external review')))
    with pytest.raises(mcp_actions.ActionError):confirm(pilot)
    assert current(pilot)['status']=='for_review' and current(pilot)['revision']==task['revision']
    assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_accept'").fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_task_acceptances').fetchone()[0] is None
