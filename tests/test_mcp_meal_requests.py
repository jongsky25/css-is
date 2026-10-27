"""Exact own meal submission, current gates, atomicity and recoverable receipts."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
import json
import re
import time

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents_permissions as permissions
from documents_storage import transaction
import mcp_actions
import mcp_auth
import mcp_meal_requests as pilot_service
import mcp_read
import meals
import storage as st
import tzutil as tz
from tests.conftest import join_admin_section
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN='http://testserver'
RESOURCE=ORIGIN+'/mcp'
KEY='standalone-meal-request-001'
TITLE='PRIVATE_MEAL <script>untrusted</script>'


@pytest.fixture
def pilot(api,monkeypatch):
    conn,users,unit,clients,app=api
    monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,4))
    monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,4,9))
    for flag in ('CSS_MCP_ENABLED',pilot_service.FLAG):monkeypatch.setenv(flag,'1')
    for flag in ('CSS_BASE_URL','SPACE_HOST','CSS_MCP_ROOM_REQUESTS_ENABLED'):monkeypatch.delenv(flag,raising=False)
    join_admin_section(conn,users[1]['id']);users[1]=st.get_admin_user_by_id(conn,users[1]['id'])
    owner_rp=st.add_rp(conn,'Synthetic meal requester',True,unit)
    conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(owner_rp,users[0]['id']));conn.commit()
    users[0]=st.get_admin_user_by_id(conn,users[0]['id'])
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)',('meal-test',json.dumps({'client_name':'Meal test'}),int(time.time())))
    token=mcp_auth.Provider._tokens(conn,'meal-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,token


def fields(**changes):
    return {'title':TITLE,'day':'2030-03-06','venue':'PRIVATE delivery location','pax':25,
            'special_request':'PRIVATE meal instruction\nSecond line',
            'meals':[{'meal':'lunch','deliver_at':'12:15'},{'meal':'am_snack','deliver_at':'10:00'}],**changes}


def prepare(pilot,key=KEY,data=None):
    return pilot_service.prepare(pilot[0],pilot[4].access_token,RESOURCE,ORIGIN,key,data or fields())


def form(page):
    return {k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','preview_digest')}|{'confirm':'yes'}


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    p=pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=p['preview_digest'])


def test_exact_pending_queue_source_and_historical_recovery(pilot,monkeypatch):
    import mailer
    conn,users,clients,app,token=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:pytest.fail('Standalone requests send no mail'))
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN)
    assert context['earliest_day']=='2030-03-06' and context['queue_staff_count']==1
    preview=prepare(pilot)
    assert prepare(pilot)==preview and 'PRIVATE' not in json.dumps(preview)
    assert not conn.execute('SELECT * FROM meal_request').fetchall()
    path='/account/integrations/mcp/meal-requests/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert all(t in page.text for t in ('12:15','10:00','25','PRIVATE delivery location','PRIVATE meal instruction','Synthetic meal requester'))
    assert 'Administrative Section' in page.text and 'Awaiting order' in page.text
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    result=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['status']=='completed' and result['submitted_status']=='submitted' and result['meal_status']=='pending'
    assert result['next_actor']=={'role':'administrative_section_meal_ordering','queue_staff_count':1}
    assert result['notification_status']=='none_created' and 'PRIVATE' not in json.dumps(result)
    rid=int(result['meal_request_id']);record=meals.get(conn,rid)
    assert record['requester_user_id']==users[0]['id'] and record['status']=='submitted' and record['overall']=='Awaiting order'
    assert all(record[k]==fields()[k] for k in ('title','day','venue','pax','special_request'))
    assert [(r['meal'],r['deliver_at'],r['status']) for r in record['items']]==[('am_snack','10:00','pending'),('lunch','12:15','pending')]
    assert prepare(pilot)==result
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_meal_request').fetchone()==(None,None)
    assert clients[0].get(result['web_url']).status_code==200 and TITLE in clients[1].get('/meals').text.replace('&lt;','<').replace('&gt;','>')
    assert clients[2].get(result['web_url']).status_code==403 and clients[4].get('/meals').status_code==403
    for table in ('room_reservation','calendar_entry','room_notice','room_meal'):
        assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    meals.tag(conn,rid,'lunch','requested',users[1])
    assert prepare(pilot)==result and meals.get(conn,rid)['overall'].startswith('Mixed')
    meals.withdraw(conn,rid,users[0])
    assert prepare(pilot)==result and meals.get(conn,rid)['status']=='withdrawn'


@pytest.mark.parametrize('change',['identity','routing','deadline','scope','revoked','expired','payload','snapshot','switch','global_switch'])
def test_current_authority_policy_and_snapshot_rechecked(pilot,monkeypatch,change):
    conn,users,clients,app,token=pilot;prepare(pilot)
    path='/account/integrations/mcp/meal-requests/'+KEY;page=clients[0].get(path)
    if change=='identity':conn.execute("UPDATE resource_person SET name='Changed requester' WHERE id=?",(users[0]['rp_id'],))
    elif change=='routing':join_admin_section(conn,users[2]['id'])
    elif change=='deadline':monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,5))
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"rooms:request\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_meal_request SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_meal_request SET payload_json=?',(json.dumps(fields(pax=26)),))
    elif change=='snapshot':conn.execute('UPDATE mcp_meal_request SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    else:monkeypatch.setenv(pilot_service.FLAG,'0')
    conn.commit()
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==409
    assert conn.execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==0
    if change=='expired':assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_meal_request').fetchone()==(None,None)


@pytest.mark.parametrize('changes',[
    {'pax':True},{'pax':'25'},{'pax':0},{'pax':1001},{'title':' '},{'title':'a'*241},{'title':'line\nbreak'},
    {'venue':' '},{'day':'2030-02-30'},{'day':'20300306'}, {'special_request':'a'*801}, {'special_request':'\x00'},
    {'meals':[]},{'meals':[{'meal':'dinner','deliver_at':'18:00'}]},
    {'meals':[{'meal':'lunch','deliver_at':'05:59'}]}, {'meals':[{'meal':'lunch','deliver_at':'19:01'}]},
    {'meals':[{'meal':'lunch','deliver_at':'12:15','status':'requested'}]},
    {'meals':[{'meal':'lunch','deliver_at':'12:15'}]*2}, {'requester_user_id':2},{'status':'requested'},{'reservation_id':1},
])
def test_strict_input_and_no_unsupported_actions(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(**changes))
    assert pilot[0].execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==0


def test_scope_identity_connection_session_and_browser_security(pilot):
    conn,users,clients,app,token=pilot;prepare(pilot)
    path='/account/integrations/mcp/meal-requests/'+KEY;page=clients[0].get(path)
    assert clients[1].get(path).status_code==404
    for data,origin,status in (({**form(page),'csrf':'bad'},ORIGIN,403),(form(page),'https://evil.example',403),({**form(page),'pax':'99'},ORIGIN,400)):
        assert clients[0].post(path,data=data,headers={'Origin':origin}).status_code==status
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='different meal'):prepare(pilot,data=fields(pax=26))
    fresh=mcp_auth.Provider._tokens(conn,'meal-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE)
    read_only=mcp_auth.Provider._tokens(conn,'meal-test',users[0]['id'],['calendar:read','rooms:request'],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    with pytest.raises(mcp_actions.ActionError,match='explicitly allow'):
        pilot_service.prepare(conn,read_only.access_token,RESOURCE,ORIGIN,'wrong-meal-scope-001',fields())
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)


def test_atomic_rollback_then_concurrent_same_key_and_later_distinct_request(pilot,monkeypatch):
    conn,users,clients,app,token=pilot;prepare(pilot)
    original=st.audit
    def fail(c,actor,action,**kw):
        if action=='integration_action_complete':raise RuntimeError('Synthetic receipt audit failure')
        return original(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):confirm(pilot)
    for table in ('meal_request','meal_request_item','mcp_meal_identity'):
        assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_meal_request').fetchone()[0] is None
    monkeypatch.setattr(st,'audit',original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    digest=pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)['preview_digest']
    def worker(_):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,KEY,confirm_digest=digest)
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(worker,range(2)))
    assert result[0]['meal_request_id']==result[1]['meal_request_id']
    assert conn.execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==1
    # Creation keys identify requests, rather than deduplicating matching meals forever.
    prepare(pilot,'different-meal-request-001');confirm(pilot,'different-meal-request-001')
    assert conn.execute('SELECT COUNT(*) FROM meal_request').fetchone()[0]==2


def test_deleted_source_and_reused_id_cannot_rebind_receipt(pilot):
    conn,users,clients,app,token=pilot;prepare(pilot);result=confirm(pilot);rid=int(result['meal_request_id'])
    conn.execute('DELETE FROM meal_request WHERE id=?',(rid,));conn.commit()
    replacement=meals.create(conn,users[0],**pilot_service._domain_fields(pilot_service.normalize(fields())),today=date(2030,3,4))
    assert replacement['id']==rid and not conn.execute('SELECT * FROM mcp_meal_identity').fetchall()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert conn.execute('SELECT completed_at FROM mcp_meal_request').fetchone()[0]


def test_zero_queue_staff_and_domain_transaction_boundary(pilot):
    conn,users,clients,app,token=pilot
    conn.execute("UPDATE resource_person SET archived_at='2030-03-04' WHERE id=?",(users[1]['rp_id'],));conn.commit()
    prepare(pilot);page=clients[0].get('/account/integrations/mcp/meal-requests/'+KEY)
    assert 'No active Administrative Section queue staff' in page.text
    assert confirm(pilot)['next_actor']['queue_staff_count']==0
    with pytest.raises(RuntimeError,match='caller-owned'):
        meals.create(conn,users[0],**pilot_service._domain_fields(pilot_service.normalize(fields())),commit=False)


def test_actual_sdk_and_mobile_no_javascript_confirmation(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,token=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='meal-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        context=await server.call_tool('get_my_meal_request_context',{})
        assert '2030-03-06' in str(context) and 'PRIVATE' not in str(context)
        result=await server.call_tool('prepare_meal_request',{**fields(),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE' not in str(result)
        access.scopes=['rooms:request']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_meal_request',{**fields(),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/meal-requests/'+KEY)
                expect(page.get_by_role('heading',name='Submit this meal request?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: submit meal request',exact=True).click()
                expect(page.get_by_role('heading',name='Meal request submitted',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_bounded_cleanup_commits_before_failed_confirmation_and_capacity(pilot):
    conn,users,clients,app,token=pilot;prepare(pilot)
    # A failed/expired browser action must still discard its retained text.
    conn.execute('UPDATE mcp_meal_request SET expires_at=1');conn.commit()
    with pytest.raises(mcp_actions.ActionError,match='expired'):confirm(pilot)
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_meal_request').fetchone()==(None,None)
    for i in range(50):prepare(pilot,'meal-capacity-key-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'meal-capacity-overflow')
    conn.execute("UPDATE mcp_meal_request SET expires_at=1 WHERE operation_id!=?",(KEY,));conn.commit()
    prepare(pilot,'meal-capacity-after-cleanup')
    assert conn.execute('SELECT COUNT(*) FROM mcp_meal_request WHERE payload_json IS NOT NULL').fetchone()[0]==1


def test_current_source_ownership_and_inactive_account_block_recovery(pilot):
    conn,users,clients,app,token=pilot;prepare(pilot);result=confirm(pilot)
    conn.execute('UPDATE meal_request SET requester_user_id=? WHERE id=?',(users[2]['id'],result['meal_request_id']));conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    conn.execute('UPDATE meal_request SET requester_user_id=? WHERE id=?',(users[0]['id'],result['meal_request_id']));conn.commit()
    assert pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)['status']=='completed'
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));conn.commit()
    with pytest.raises((mcp_actions.ActionError,permissions.Denied)):
        pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
