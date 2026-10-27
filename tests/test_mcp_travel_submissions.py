"""Ready-to-Submitted recording needs a current source and explicit paper-handover attestation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
import time

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_read
import mcp_travel_submissions as pilot_service
import mailer
import storage as st
import travel
import travel_review as review
from tests.conftest import join_admin_section
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN='http://testserver'
RESOURCE=ORIGIN+'/mcp'
KEY='travel-paper-submission-001'
TITLE='PRIVATE_HANDOVER <script>untrusted</script>'
DOC='https://docs.google.com/document/d/private-paper/edit'


@pytest.fixture
def pilot(api,monkeypatch):
    conn,users,unit,clients,app=api
    for flag in ('CSS_MCP_ENABLED',pilot_service.FLAG):monkeypatch.setenv(flag,'1')
    for flag in ('CSS_BASE_URL','SPACE_HOST','CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED'):monkeypatch.delenv(flag,raising=False)
    join_admin_section(conn,users[1]['id']);users[1]=st.get_admin_user_by_id(conn,users[1]['id'])
    filing=travel.create_filing(conn,users[0],kind='reimbursement',source={'source_kind':'blank','title':TITLE,
        'start':'2026-10-14','end':'2026-10-16','venue':'Palo'},answers={},role='participant',dpo_no='DPO-SYNTHETIC',today='2026-10-27')
    for item in travel.view_items(conn,filing):
        conn.execute("UPDATE travel_item SET drive_url=?,doc_url=?,state='present' WHERE filing_id=? AND item_code=?",(DOC,DOC,filing['id'],item['code']))
    conn.commit()
    reviewed=review.request_review(conn,filing,users[1]['id'],users[0]['username'])
    approved=review.approve(conn,reviewed,users[1]['username'])
    ready=travel.mark_ready(conn,approved)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)',('paper-test',json.dumps({'client_name':'Paper test'}),int(time.time())))
    token=mcp_auth.Provider._tokens(conn,'paper-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,ready,token


def fields(pilot,**changes):return {'filing_id':pilot[4]['id'],'expected_updated_at':pilot[4]['updated_at'],**changes}


def prepare(pilot,operation_id=KEY,data=None):
    return pilot_service.prepare(pilot[0],pilot[5].access_token,RESOURCE,ORIGIN,operation_id,data or fields(pilot))


def form(page):
    return {k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','preview_digest')}|{'confirm':'yes'}


def confirm(pilot,operation_id=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    p=pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,operation_id)
    return pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,operation_id,confirm_digest=p['preview_digest'])


def test_exact_paper_recording_receipt_source_and_replay(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot
    def no_send(*a,**kw):raise AssertionError('Recording handover must not send anything')
    monkeypatch.setattr(mailer,'send',no_send)
    unchanged={t:conn.execute('SELECT * FROM '+t).fetchall() for t in ('travel_item','travel_flag','travel_review_note',
        'mcp_travel_review_mail','supply_stock_movement','calendar_entry','email_log')}
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])
    assert context['ready_to_record'] and context['expected_updated_at']==filing['updated_at']
    assert 'PRIVATE_HANDOVER' not in json.dumps(context) and DOC not in json.dumps(context)
    result=prepare(pilot);assert prepare(pilot)==result and result['paper_handover_attested'] is None
    assert travel.get_filing(conn,filing['id'])['status']=='ready'
    path='/account/integrations/mcp/travel-submissions/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert 'physically handed in' in page.text and 'Ready → Submitted' in page.text
    assert DOC not in page.text and 'DPO-SYNTHETIC' not in page.text
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    receipt=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert receipt['status']=='completed' and receipt['recorded_status']=='submitted'
    assert receipt['paper_handover_attested'] and receipt['submitted_at']
    assert receipt['next_actor']=={'role':'traveller_follow_up_with_receiving_office','user_id':str(users[0]['id'])}
    assert 'PRIVATE_HANDOVER' not in json.dumps(receipt) and DOC not in json.dumps(receipt)
    assert prepare(pilot)==receipt
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_submit'").fetchone()[0]==1
    saved=travel.get_filing(conn,filing['id'])
    assert saved['status']=='submitted' and saved['review_state']=='approved'
    for k in ('advance_amount','answers_json','dpo_no','ready_at','reviewer_id','review_round'):assert saved[k]==filing[k]
    for table,before in unchanged.items():assert conn.execute('SELECT * FROM '+table).fetchall()==before
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_travel_submission').fetchone()==(None,None)
    assert clients[0].get(receipt['web_url']).status_code==200
    assert not pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])['ready_to_record']


@pytest.mark.parametrize('change',['stamp','papers','missing','flag','running','open','review','policy','owner','purged','scope','revoked','expired','snapshot','payload','switch','module'])
def test_current_gates_and_full_content_binding(pilot,monkeypatch,change):
    conn,users,clients,app,filing,token=pilot;prepare(pilot)
    path='/account/integrations/mcp/travel-submissions/'+KEY;page=clients[0].get(path)
    if change=='stamp':conn.execute("UPDATE travel_filing SET updated_at='changed'")
    elif change=='papers':conn.execute("UPDATE travel_item SET drive_url='https://docs.google.com/document/d/changed/edit'")
    elif change=='missing':conn.execute('UPDATE travel_item SET drive_url=NULL,doc_url=NULL')
    elif change=='flag':conn.execute("INSERT INTO travel_flag(filing_id,kind,sig,state) VALUES (?,'over_ceiling','test-flag','open')",(filing['id'],))
    elif change=='running':conn.execute("UPDATE travel_filing SET gen_state='running'")
    elif change=='open':conn.execute("UPDATE travel_filing SET status='open'")
    elif change=='review':conn.execute("UPDATE travel_filing SET review_state='changes'")
    elif change=='policy':st.set_setting(conn,review.SETTING,'0')
    elif change=='owner':conn.execute('UPDATE travel_filing SET user_id=?',(users[2]['id'],))
    elif change=='purged':conn.execute("UPDATE travel_filing SET purged_at='2026-10-27'")
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"travel:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_travel_submission SET expires_at=1')
    elif change=='snapshot':conn.execute('UPDATE mcp_travel_submission SET snapshot_json=NULL')
    elif change=='payload':conn.execute('UPDATE mcp_travel_submission SET payload_json=?',(json.dumps(fields(pilot,expected_updated_at='changed')),))
    elif change=='switch':monkeypatch.setenv(pilot_service.FLAG,'0')
    else:st.set_setting(conn,'travel.enabled','0')
    conn.commit()
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert travel.get_filing(conn,filing['id'])['submitted_at'] is None
    assert conn.execute('SELECT completed_at FROM mcp_travel_submission').fetchone()[0] is None
    if change=='expired':assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_travel_submission').fetchone()==(None,None)


@pytest.mark.parametrize('changed',[{'filing_id':True},{'filing_id':0},{'expected_updated_at':''},
    {'status':'submitted'},{'physical_handover':True},{'advance_amount':1000},{'documents':[]}])
def test_invalid_or_model_supplied_attestation_fields_rejected(pilot,changed):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changed))


def test_ownership_scope_connection_csrf_origin_and_session(pilot):
    conn,users,clients,app,filing,token=pilot
    other=mcp_auth.Provider._tokens(conn,'paper-test',users[1]['id'],[pilot_service.SCOPE],RESOURCE)
    read=mcp_auth.Provider._tokens(conn,'paper-test',users[0]['id'],['travel:read','travel:review:request','travel:filing:draft'],RESOURCE)
    fresh=mcp_auth.Provider._tokens(conn,'paper-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE)
    conn.commit();prepare(pilot)
    with pytest.raises(permissions.Denied):pilot_service.prepare(conn,other.access_token,RESOURCE,ORIGIN,KEY,fields(pilot))
    with pytest.raises(mcp_actions.ActionError):pilot_service.prepare(conn,read.access_token,RESOURCE,ORIGIN,KEY,fields(pilot))
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    path='/account/integrations/mcp/travel-submissions/'+KEY;page=clients[0].get(path)
    assert clients[1].get(path).status_code==404
    for values,origin in (({**form(page),'csrf':'bad'},ORIGIN),(form(page),'https://evil.example'),({**form(page),'confirm':'no'},ORIGIN)):
        assert clients[0].post(path,data=values,headers={'Origin':origin}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):confirm(pilot)


def test_atomic_rollback_then_concurrent_confirmations_and_different_keys(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);prepare(pilot,'other-paper-submission-001')
    original=st.audit
    def failed(*args,**kw):
        if args[2]=='integration_action_complete':raise RuntimeError('Synthetic final audit failure')
        return original(*args,**kw)
    monkeypatch.setattr(st,'audit',failed)
    with pytest.raises(RuntimeError):confirm(pilot)
    assert travel.get_filing(conn,filing['id'])['status']=='ready' and travel.get_filing(conn,filing['id'])['submitted_at'] is None
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_submit'").fetchone()[0]==0
    monkeypatch.setattr(st,'audit',original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview=pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)
    def commit(_):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,KEY,confirm_digest=preview['preview_digest'])
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(commit,range(2)))
    assert result[0]==result[1]
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_submit'").fetchone()[0]==1
    with pytest.raises(mcp_actions.ActionError):confirm(pilot,'other-paper-submission-001')


def test_optional_review_policy_and_current_source_privacy(pilot):
    conn,users,clients,app,filing,token=pilot
    st.set_setting(conn,review.SETTING,'0');conn.execute("UPDATE travel_filing SET review_state='' WHERE id=?",(filing['id'],));conn.commit()
    assert pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])['ready_to_record']
    prepare(pilot);result=confirm(pilot)
    assert result['recorded_status']=='submitted'
    conn.execute("UPDATE travel_filing SET purged_at='2027-12-01' WHERE id=?",(filing['id'],));conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)


def test_actual_mcp_dispatch_and_mobile_no_javascript_attestation(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,filing,token=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    context=AccessToken(token=token.access_token,client_id='paper-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:context)
    async def journey():
        result=await server.call_tool('get_my_travel_submission_context',{'filing_id':filing['id']})
        assert 'ready_to_record' in str(result) and DOC not in str(result)
        result=await server.call_tool('prepare_travel_filing_submission',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_HANDOVER' not in str(result)
        context.scopes=['travel:review:request']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_travel_filing_submission',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/travel-submissions/'+KEY)
                expect(page.get_by_role('heading',name='Record this paper submission?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                assert travel.get_filing(conn,filing['id'])['status']=='ready'
                page.get_by_role('button',name='Confirm: record my paper submission',exact=True).click()
                expect(page.get_by_role('heading',name='Paper submission recorded',exact=True)).to_be_visible()
                page.get_by_role('link',name='Open my submitted filing',exact=True).click()
                expect(page.get_by_text('Paper submission recorded',exact=True).first).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_two_independent_previews_commit_one_paper_record(pilot):
    conn,users,clients,app,filing,token=pilot
    prepare(pilot);prepare(pilot,'independent-paper-record-001')
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    previews=[pilot_service.browser(conn,payload,RESOURCE,ORIGIN,k) for k in (KEY,'independent-paper-record-001')]
    def commit(p):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,p['operation_id'],confirm_digest=p['preview_digest'])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(commit,previews))
    assert sorted(result)==['completed','conflict']
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_submit'").fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM mcp_travel_submission WHERE completed_at IS NOT NULL').fetchone()[0]==1


def test_domain_entry_requires_caller_transaction_when_commit_disabled(pilot):
    with pytest.raises(RuntimeError):travel.mark_submitted(pilot[0],pilot[4],commit=False)
    assert travel.get_filing(pilot[0],pilot[4]['id'])['status']=='ready'
