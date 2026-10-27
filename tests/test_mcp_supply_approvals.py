"""Exact approval decisions, initial stock reservations and immutable recovery."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
from datetime import datetime,timedelta
import time

import pytest
from mcp.server.auth.provider import AccessToken
from starlette.testclient import TestClient

import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_read
import mcp_supply_approvals as service
import supply_approval as approval
import storage as st
import supplies
import supplies_approvals as approvals
import supplies_allocations as allocations
import supplies_requests as requests
import supplies_stock as stock
import supplies_storage as domain
import supplies_notify as notify
import mailer
from tests.conftest import session_token
from tests.test_supplies import supplies_db,key
from tests.test_supplies_requests import request_db,draft,submit,get
from tests.test_supplies_approvals import approval_db,decide
from tests.test_supplies_backorders import receipt
from tests.test_mcp_supply_submissions import form,ORIGIN,RESOURCE,PURPOSE

KEY='supply-approval-operation-001'
REASON='APPROVAL_REASON <script>untrusted</script>'


@pytest.fixture
def pilot(approval_db,app_mod,monkeypatch):
    conn,users,units,path,item=approval_db
    monkeypatch.setattr(app_mod,'DB',path)
    for flag in ('CSS_MCP_ENABLED',service.FLAG):monkeypatch.setenv(flag,'1')
    for flag in ('CSS_BASE_URL','SPACE_HOST','CSS_MCP_SUPPLY_SUBMISSIONS_ENABLED'):monkeypatch.delenv(flag,raising=False)
    rid=draft(conn,users,item,purpose=PURPOSE,lines=[{'item_id':item,'requested_quantity':12}]);saved=submit(conn,users,rid)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)',('supply-approve-test',json.dumps({'client_name':'Supply approval test'}),int(time.time())))
    token=mcp_auth.Provider._tokens(conn,'supply-approve-test',users[3]['id'],[service.SCOPE],RESOURCE);conn.commit()
    with ExitStack() as stack:
        clients=[]
        for user in users:
            client=stack.enter_context(TestClient(app_mod.app,raise_server_exceptions=False))
            client.cookies.set(auth.COOKIE_NAME,session_token(user));clients.append(client)
        yield conn,users,clients,app_mod,item,saved,token


def fields(pilot,**changes):
    _,request,header,info=approval.source(pilot[0],pilot[1][3],pilot[5]['id'])
    return {'request_id':request['id'],'revision':request['revision'],'expected_revision':info['expected_revision'],'reason':REASON,**changes}


def prepare(pilot,key=KEY,data=None):
    return service.prepare(pilot[0],pilot[6].access_token,RESOURCE,ORIGIN,key,data or fields(pilot))


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][3].cookies.get(auth.COOKIE_NAME))
    p=service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=p['preview_digest'])


def request(pilot):return requests.get_request(pilot[0],pilot[1][3],pilot[5]['id'])


def test_exact_approval_reservation_stock_equation_and_historical_recovery(pilot,monkeypatch):
    conn,users,clients,app,item,saved,token=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**k:pytest.fail('No mail from approval'))
    context=service.read_context(conn,token.access_token,RESOURCE,ORIGIN,saved['id'])
    assert context['revision']==saved['revision'] and context['line_count']==1
    assert 'PRIVATE_PURPOSE' not in json.dumps(context) and 'TEST-PAPER' not in json.dumps(context)
    original=fields(pilot);preview=prepare(pilot,data=original)
    assert prepare(pilot,data=original)==preview and 'PRIVATE_PURPOSE' not in json.dumps(preview)
    assert request(pilot)['approval_status']=='submitted' and conn.execute('SELECT COUNT(*) FROM supply_reservation').fetchone()[0]==0
    path='/account/integrations/mcp/supply-approvals/'+KEY;page=clients[3].get(path)
    assert page.status_code==200 and all(t in page.text for t in ('PRIVATE_PURPOSE','APPROVAL_REASON','TEST-PAPER','12 / 12 Ream','10 Ream','2 Ream'))
    assert '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    movements=conn.execute('SELECT * FROM supply_stock_movement').fetchall()
    assert clients[3].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    result=service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['approval_status']=='approved' and result['result_revision']==saved['revision']+1
    assert result['next_actor']=={'role':'supply_custodian_issue_or_await_stock'}
    assert 'PRIVATE_PURPOSE' not in json.dumps(result) and 'APPROVAL_REASON' not in json.dumps(result) and 'TEST-PAPER' not in json.dumps(result)
    current=request(pilot);line=current['lines'][0]
    assert (line['approved_quantity'],line['reserved_quantity'],line['awaiting_stock_quantity'],line['effective_issued_quantity'])==(12,10,2,0)
    assert allocations.availability(conn,item)=={'on_hand':10,'reserved_quantity':10,'available':0}
    assert movements==conn.execute('SELECT * FROM supply_stock_movement').fetchall()
    assert conn.execute('SELECT COUNT(*) FROM supply_issue').fetchone()[0]==0
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_supply_approvals').fetchone()==(None,None)
    prior=json.loads(conn.execute('SELECT result_json FROM supply_operation WHERE operation_key=?',(result['domain_operation_id'],)).fetchone()[0])
    assert prior['approval_status']=='approved' and prior['decision_id']==conn.execute('SELECT id FROM supply_request_decision').fetchone()[0]
    assert prepare(pilot,data=original)==result
    # A separate ordinary issue changes physical stock and fulfillment; old receipt must not repeat allocation.
    from tests.test_supplies_issues import issue
    issued=issue(conn,users,saved['id'],quantity=4)
    assert issued['id'] and allocations.availability(conn,item)=={'on_hand':6,'reserved_quantity':6,'available':0}
    assert prepare(pilot,data=original)==result
    assert clients[3].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert allocations.availability(conn,item)['on_hand']==6 and request(pilot)['lines'][0]['effective_issued_quantity']==4
    assert conn.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM supply_notice').fetchone()[0]>=1


@pytest.mark.parametrize('change',['request','revision','item','inactive_item','requester','grant','scope_path','disabled','scope','revoked','expired','payload','snapshot','switch','global_switch','stock','queue'])
def test_current_source_stock_and_authority_rechecked(pilot,monkeypatch,change):
    conn,users,clients,app,item,saved,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/supply-approvals/'+KEY;page=clients[3].get(path)
    if change=='request':requests.withdraw(conn,users[2],saved['id'],reason='No longer needed',expected_revision=saved['revision'],operation_key=key())
    elif change=='revision':conn.execute('UPDATE supply_request SET revision=revision+1 WHERE id=?',(saved['id'],))
    elif change=='item':conn.execute("UPDATE supply_item SET unit='Pack',revision=revision+1 WHERE id=?",(item,))
    elif change=='inactive_item':conn.execute('UPDATE supply_item SET active=0 WHERE id=?',(item,))
    elif change=='requester':conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[2]['id'],))
    elif change=='grant':conn.execute("UPDATE supply_role_grant SET revoked_at='2030-01-01',revoked_by=? WHERE user_id=? AND role='request_approver'",(users[0]['id'],users[3]['id']))
    elif change=='scope_path':conn.execute("UPDATE org_unit SET path='OTHER' WHERE id=(SELECT unit_id FROM supply_role_grant WHERE user_id=? AND role='request_approver')",(users[3]['id'],))
    elif change=='disabled':st.set_setting(conn,'supplies.enabled','0')
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"supplies:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_supply_approvals SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_supply_approvals SET payload_json=?',(json.dumps({**original,'reason':'Tampered'}),))
    elif change=='snapshot':conn.execute('UPDATE mcp_supply_approvals SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    elif change=='stock':receipt(conn,users,item,1)
    elif change=='queue':
        other=draft(conn,users,item,lines=[{'item_id':item,'requested_quantity':2}]);submit(conn,users,other);decide(conn,users,other)
    else:monkeypatch.setenv(service.FLAG,'0')
    conn.commit()
    assert clients[3].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert conn.execute('SELECT COUNT(*) FROM supply_request_decision WHERE request_id=?',(saved['id'],)).fetchone()[0]==0


@pytest.mark.parametrize('changes',[
    {'request_id':True},{'request_id':'1'},{'revision':0},{'expected_revision':'guess'},
    {'reason':''},{'reason':'x'*2001},{'reason':'bad\x00text'},{'lines':[]},
    {'approved_quantity':1},{'decision':'returned'},{'issue':True},{'send_email':True},
])
def test_strict_full_quantity_only_inputs(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changes))


def test_scoped_grant_only_self_admin_custodian_and_foreign_requests(pilot):
    conn,users,clients,app,item,saved,token=pilot
    supplies.grant_role(conn,users[0],users[2]['id'],'request_approver',unit_id=request(pilot)['unit_id'],operation_key=key())
    for idx in (0,1,2):
        granted=mcp_auth.Provider._tokens(conn,'supply-approve-test',users[idx]['id'],[service.SCOPE],RESOURCE);conn.commit()
        with pytest.raises(domain.Denied):service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,saved['id'])
    prepare(pilot)
    assert clients[4].get('/account/integrations/mcp/supply-approvals/'+KEY).status_code==404


@pytest.mark.parametrize('failure',['audit','enqueue','allocation_guard'])
def test_atomic_decision_reservations_receipts_and_warning_failure(pilot,monkeypatch,failure):
    conn,users,clients,app,item,saved,token=pilot;prepare(pilot)
    before={t:conn.execute('SELECT * FROM '+t).fetchall() for t in ('supply_operation','supply_event','supply_reservation','supply_request_decision','supply_request_decision_line','supply_alert_event','supply_notice','supply_stock_movement')}
    if failure=='audit':
        original=st.audit
        def fail(c,actor,action,**kw):
            if action=='integration_action_complete':raise RuntimeError('Synthetic audit failure')
            return original(c,actor,action,**kw)
        monkeypatch.setattr(st,'audit',fail)
    elif failure=='enqueue':monkeypatch.setattr(notify,'enqueue',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Synthetic enqueue failure')))
    else:
        original=allocations.allocation_projection
        def changed(c,*a,**kw):
            result=original(c,*a,**kw)
            if kw.get('max_existing')==45:result[0]['on_hand']+=1
            return result
        monkeypatch.setattr(allocations,'allocation_projection',changed)
    with pytest.raises((RuntimeError,mcp_actions.ActionError)):confirm(pilot)
    assert request(pilot)['approval_status']=='submitted'
    assert conn.execute('SELECT completed_at FROM mcp_supply_approvals').fetchone()[0] is None
    for table,value in before.items():assert conn.execute('SELECT * FROM '+table).fetchall()==value


def test_post_commit_warning_projection_failure_and_recovery_never_reapprove(pilot,monkeypatch):
    conn,users,clients,app,item,saved,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    monkeypatch.setattr(notify,'process_pending',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Synthetic projection failure')))
    result=confirm(pilot)
    assert result['approval_status']=='approved' and prepare(pilot,data=original)['result_revision']==result['result_revision']
    assert conn.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM supply_alert_event WHERE processed_at IS NULL').fetchone()[0]>0
    assert allocations.availability(conn,item)['reserved_quantity']==10


def test_same_revision_competing_keys_and_same_key_replays(pilot):
    conn,users,clients,app,item,saved,token=pilot;original=fields(pilot);keys=(KEY,'competing-supply-approval-001')
    for k in keys:prepare(pilot,k,original)
    payload=auth.parse_token(clients[3].cookies.get(auth.COOKIE_NAME))
    digests={k:service.browser(conn,payload,RESOURCE,ORIGIN,k)['preview_digest'] for k in keys}
    def worker(k):
        c=app.get_conn()
        try:return service.browser(c,payload,RESOURCE,ORIGIN,k,confirm_digest=digests[k])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,keys))
    assert sorted(results)==['completed','conflict'];winner=keys[results.index('completed')]
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(worker,(winner,winner)))==['completed','completed']
    assert conn.execute('SELECT COUNT(*) FROM supply_request_decision').fetchone()[0]==1
    assert allocations.availability(conn,item)['reserved_quantity']==10


def test_csrf_session_connection_and_preview_limits(pilot,monkeypatch):
    conn,users,clients,app,item,saved,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/supply-approvals/'+KEY;page=clients[3].get(path)
    for values,origin in (({**form(page),'csrf':'bad'},ORIGIN),(form(page),'https://evil.example')):
        assert clients[3].post(path,data=values,headers={'Origin':origin}).status_code==403
    assert clients[3].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='different'):prepare(pilot,data={**original,'reason':'Other'})
    fresh=mcp_auth.Provider._tokens(conn,'supply-approve-test',users[3]['id'],[service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    for i in range(49):prepare(pilot,'supply-approval-capacity-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'supply-approval-capacity-overflow')
    conn.execute('UPDATE mcp_supply_approvals SET expires_at=1');conn.commit();monkeypatch.setenv(service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError):service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert conn.execute('SELECT COUNT(*) FROM mcp_supply_approvals WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    payload=auth.parse_token(clients[3].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):service.browser(conn,payload,RESOURCE,ORIGIN,KEY)


def test_sdk_and_mobile_confirmation_without_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,item,saved,token=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='supply-approve-test',scopes=[service.SCOPE],resource=RESOURCE,subject=str(users[3]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        result=await server.call_tool('prepare_supply_request_approval',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_PURPOSE' not in str(result)
        access.scopes=['supplies:request:submit']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_supply_request_approval',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[3],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/supply-approvals/'+KEY)
                expect(page.get_by_role('heading',name='Approve this exact supply request?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: approve full quantities and reserve',exact=True).click()
                expect(page.get_by_role('heading',name='Supply request approved',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


@pytest.mark.parametrize('displacing',[False,True])
def test_older_reservations_kept_and_displacement_refused_without_private_details(pilot,monkeypatch,displacing):
    conn,users,clients,app,item,saved,token=pilot
    older=draft(conn,users,item,purpose='OTHER_PRIVATE_PURPOSE',lines=[{'item_id':item,'requested_quantity':4}]);submit(conn,users,older)
    fixture_time=datetime.fromisoformat(__import__('tzutil').now_iso())
    with monkeypatch.context() as patch:
        patch.setattr(__import__('tzutil'),'now_iso',lambda:(fixture_time+timedelta(days=1 if displacing else -1)).isoformat())
        decide(conn,users,older)
    assert get(conn,users,older)['lines'][0]['reserved_quantity']==4
    if displacing:
        with pytest.raises(mcp_actions.ActionError):service.read_context(conn,token.access_token,RESOURCE,ORIGIN,saved['id'])
        assert get(conn,users,older)['lines'][0]['reserved_quantity']==4
        assert request(pilot)['approval_status']=='submitted'
        return
    original=fields(pilot);prepare(pilot,data=original)
    page=clients[3].get('/account/integrations/mcp/supply-approvals/'+KEY)
    assert 'OTHER_PRIVATE_PURPOSE' not in page.text and get(conn,users,older)['control_number'] not in page.text
    assert '6 Ream' in page.text
    result=confirm(pilot)
    assert result['approval_status']=='approved' and get(conn,users,older)['lines'][0]['reserved_quantity']==4
    assert request(pilot)['lines'][0]['reserved_quantity']==6
    assert allocations.availability(conn,item)=={'on_hand':10,'reserved_quantity':10,'available':0}
    lines=request(pilot)['lines']
    # Canonical ordinary replay of the same domain operation also cannot reallocate.
    same=approvals.decide_request(conn,users[3],saved['id'],{'decision':'approved','reason':REASON,
        'lines':[{'revision_line_id':l['id'],'approved_quantity':l['requested_quantity'],'reason':''} for l in lines]},
        expected_revision=saved['revision'],submitted_revision=saved['current_revision'],operation_key=result['domain_operation_id'])
    assert same['revision']==result['result_revision'] and allocations.availability(conn,item)['reserved_quantity']==10
