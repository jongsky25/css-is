"""Private activity preparation via shared UI/MCP save, never live creation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime
import json
import re
import time
from urllib.parse import urlsplit,parse_qs
from uuid import uuid4

import pytest
from mcp.server.auth.provider import AccessToken

import activity_drafts as drafts
import auth
import documents_permissions as permissions
from documents_storage import transaction
import mcp_actions
import mcp_activity_drafts as pilot_service
import mcp_auth
import mcp_read
import mailer
import storage as st
import tzutil as tz
from tests.conftest import session_token
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN='http://testserver'
RESOURCE=ORIGIN+'/mcp'
KEY='private-activity-draft-001'
TITLE='PRIVATE_DRAFT <script>untrusted</script>'
VENUE='PRIVATE_LOCATION'


@pytest.fixture
def pilot(api,monkeypatch):
    conn,users,unit,clients,app=api
    monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,4))
    monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,4,9))
    for flag in ('CSS_MCP_ENABLED',pilot_service.FLAG):monkeypatch.setenv(flag,'1')
    for flag in ('CSS_BASE_URL','SPACE_HOST'):monkeypatch.delenv(flag,raising=False)
    section=st.add_org_unit(conn,'Synthetic organizing section','section','WORK/D1/DRAFT')
    for idx in (0,1):
        rp=st.add_rp(conn,'Synthetic draft owner '+str(idx),True,section)
        conn.execute("UPDATE admin_user SET role='section_manager',rp_id=? WHERE id=?",(rp,users[idx]['id']))
    conn.commit()
    users[:2]=[st.get_admin_user_by_id(conn,u['id']) for u in users[:2]]
    for idx in (0,1):clients[idx].cookies.set(auth.COOKIE_NAME,session_token(users[idx]))
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)',('draft-test',json.dumps({'client_name':'Activity draft test'}),int(time.time())))
    token=mcp_auth.Provider._tokens(conn,'draft-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,token,section


def fields(pilot,**changes):
    return {'activity_name':TITLE,'event_date':'2030-03-07','section_id':pilot[5],'venue':VENUE,**changes}


def prepare(pilot,key=KEY,data=None):
    return pilot_service.prepare(pilot[0],pilot[4].access_token,RESOURCE,ORIGIN,key,data or fields(pilot))


def form(page):
    return {k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','preview_digest')}|{'confirm':'yes'}


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    p=pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=p['preview_digest'])


def no_live_records(conn):
    for table in ('event','form_instance','attendee','response','calendar_entry','room_reservation','travel_filing','room_notice'):
        assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0,table


def test_exact_private_save_collection_source_and_create_prefill_only(pilot,monkeypatch):
    conn,users,clients,app,token,section=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:pytest.fail('Draft save/load must never send'))
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN)
    assert any(s['id']==str(section) for s in context['sections']) and context['event_type']=='bureau'
    preview=prepare(pilot)
    assert 'PRIVATE' not in json.dumps(preview) and prepare(pilot)==preview
    no_live_records(conn);assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==0
    path='/account/integrations/mcp/activity-drafts/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert all(t in page.text for t in (VENUE,'Synthetic organizing section','Synthetic draft owner 0','2030-03-07'))
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    result=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['saved_status']=='private_draft' and result['next_actor']=={'role':'owner_review_in_create'}
    assert result['notification_status']=='none_created' and 'PRIVATE' not in json.dumps(result)
    assert prepare(pilot)==result
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM activity_draft_save').fetchone()[0]==1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_activity_draft_operation').fetchone()==(None,None)
    source=clients[0].get(result['web_url']);assert source.status_code==200 and '&lt;script&gt;' in source.text
    assert 'private, no-store' in source.headers['cache-control']
    collection=clients[0].get('/activity-drafts');assert TITLE.replace('<','&lt;').replace('>','&gt;') in collection.text
    for idx in (1,2,4):
        assert clients[idx].get(result['web_url']).status_code==404
        assert 'PRIVATE_DRAFT' not in clients[idx].get('/activity-drafts').text
    draft_key=urlsplit(result['web_url']).path.rsplit('/',1)[-1]
    loaded=clients[0].get('/create',params={'activity_draft':draft_key})
    assert loaded.status_code==200 and 'Loaded a private draft for review' in loaded.text
    assert 'value="PRIVATE_DRAFT &lt;script&gt;untrusted&lt;/script&gt;"' in loaded.text
    assert 'value="PRIVATE_LOCATION"' in loaded.text and 'value="2030-03-07"' in loaded.text
    assert f'value="{section}" selected' in loaded.text
    for idx in (1,4):assert clients[idx].get('/create',params={'activity_draft':draft_key}).status_code==404
    assert clients[0].get('/create',params={'activity_draft':draft_key,'from_entry':'1'}).status_code==400
    assert clients[0].get('/create',params={'activity_draft':draft_key,'from_room':'1'}).status_code==400
    no_live_records(conn)
    # Saving/recovering a preparation copy is independent of any later manual creation.
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:{'sent':True})
    made=clients[0].post('/create',data={'event_type':'bureau','activity_name':TITLE,'event_date':'2030-03-07',
        'section_id':str(section),'venue':VENUE,'modality':'f2f','qr_mode':'combined'},headers={'Origin':ORIGIN})
    assert made.status_code==200 and conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1
    assert prepare(pilot)==result and clients[0].get('/create',params={'activity_draft':draft_key}).status_code==200
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1


@pytest.mark.parametrize('change',['identity','section','section_level','section_deleted','date','scope','revoked','expired','payload','snapshot','switch','global_switch','role'])
def test_current_requester_section_date_and_connection_bound(pilot,monkeypatch,change):
    conn,users,clients,app,token,section=pilot;prepare(pilot)
    path='/account/integrations/mcp/activity-drafts/'+KEY;page=clients[0].get(path)
    if change=='identity':conn.execute("UPDATE resource_person SET name='Changed owner' WHERE id=?",(users[0]['rp_id'],))
    elif change=='section':conn.execute("UPDATE org_unit SET name='Changed section' WHERE id=?",(section,))
    elif change=='section_level':conn.execute("UPDATE org_unit SET level='division' WHERE id=?",(section,))
    elif change=='section_deleted':
        conn.execute('UPDATE resource_person SET org_unit_id=NULL WHERE org_unit_id=?',(section,));conn.execute('DELETE FROM org_unit WHERE id=?',(section,))
    elif change=='date':monkeypatch.setattr(tz,'today_local',lambda:date(2036,3,8))
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"activities:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_activity_draft_operation SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_activity_draft_operation SET payload_json=?',(json.dumps(fields(pilot,venue='Changed')),))
    elif change=='snapshot':conn.execute('UPDATE mcp_activity_draft_operation SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    elif change=='role':conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?",(users[0]['id'],))
    else:monkeypatch.setenv(pilot_service.FLAG,'0')
    conn.commit()
    response=clients[0].post(path,data=form(page),headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.status_code in ((401,) if change=='role' else (409,))
    assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==0
    no_live_records(conn)


@pytest.mark.parametrize('changes',[
    {'activity_name':' '},{'activity_name':'a'*201},{'activity_name':'line\nbreak'},{'venue':'a'*241},{'venue':'\x00'},
    {'event_date':'2030-02-30'},{'event_date':'20300307'},{'section_id':True},{'section_id':'1'},{'section_id':0},
    {'end_date':'2030-03-08'},{'modality':'online'},{'speakers':[1]},{'from_room':'1'},{'from_entry':'1'},
    {'open_at':'2030-03-07T09:00'},{'event_type':'outside'},{'publish':True},{'email_registrants':True},
])
def test_strict_fields_never_imply_publication(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changes))
    no_live_records(pilot[0])


def test_role_scope_csrf_origin_session_and_idempotency(pilot):
    conn,users,clients,app,token,section=pilot;prepare(pilot)
    path='/account/integrations/mcp/activity-drafts/'+KEY;page=clients[0].get(path)
    assert clients[1].get(path).status_code==404
    assert clients[0].post(path,data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[0].post(path,data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='different draft'):prepare(pilot,data=fields(pilot,venue='Changed'))
    fresh=mcp_auth.Provider._tokens(conn,'draft-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE)
    other=mcp_auth.Provider._tokens(conn,'draft-test',users[2]['id'],[pilot_service.SCOPE],RESOURCE)
    read=mcp_auth.Provider._tokens(conn,'draft-test',users[0]['id'],['activities:read'],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    with pytest.raises(permissions.Denied):pilot_service.prepare(conn,other.access_token,RESOURCE,ORIGIN,'wrong-role-draft-001',fields(pilot))
    with pytest.raises(mcp_actions.ActionError,match='explicitly allow'):pilot_service.prepare(conn,read.access_token,RESOURCE,ORIGIN,'wrong-scope-draft-001',fields(pilot))
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)


def test_atomic_rollback_and_same_key_concurrent_confirmations(pilot,monkeypatch):
    conn,users,clients,app,token,section=pilot;prepare(pilot)
    original=st.audit
    def fail(c,actor,action,**kw):
        if action=='integration_action_complete':raise RuntimeError('Synthetic completion failure')
        return original(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):confirm(pilot)
    assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM activity_draft_save').fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_activity_draft_operation').fetchone()[0] is None
    monkeypatch.setattr(st,'audit',original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    digest=pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)['preview_digest']
    def worker(_):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,KEY,confirm_digest=digest)['draft_id']
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(worker,range(2)))
    assert result[0]==result[1] and conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==1
    no_live_records(conn)


def test_source_key_tombstone_prevents_deleted_id_and_key_rebinding(pilot):
    conn,users,clients,app,token,section=pilot;prepare(pilot);result=confirm(pilot)
    old_key=urlsplit(result['web_url']).path.rsplit('/',1)[-1];old_id=int(result['draft_id'])
    conn.execute('DELETE FROM activity_draft WHERE id=?',(old_id,));conn.commit()
    with transaction(conn):
        with pytest.raises(permissions.Denied):drafts.save_in_transaction(conn,users[0],fields(pilot),operation_key=old_key)
    with transaction(conn):new=drafts.save_in_transaction(conn,users[0],fields(pilot),operation_key=str(uuid4()))
    assert new['id']==old_id and clients[0].get(result['web_url']).status_code==404
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert conn.execute('SELECT COUNT(*) FROM activity_draft_save').fetchone()[0]==2


def test_normal_form_shared_save_replay_and_current_prefill_rules(pilot,monkeypatch):
    conn,users,clients,app,token,section=pilot
    monkeypatch.setenv(pilot_service.FLAG,'0')
    monkeypatch.setenv('CSS_MCP_ENABLED','0')
    page=clients[0].get('/activity-drafts/new');assert page.status_code==200
    data={k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','operation_key')}
    data|={k:str(v) for k,v in fields(pilot).items()}
    assert clients[0].post('/activity-drafts',data={**data,'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    response=clients[0].post('/activity-drafts',data=data,headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.status_code==303
    assert clients[0].post('/activity-drafts',data=data,headers={'Origin':ORIGIN},follow_redirects=False).headers['location']==response.headers['location']
    assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==1
    conflict=clients[0].post('/activity-drafts',data={**data,'venue':'Different'},headers={'Origin':ORIGIN})
    assert conflict.status_code==409 and 'This form already saved a draft' in conflict.text
    assert 'href="/activity-drafts/new"' in conflict.text
    assert clients[0].post('/activity-drafts',data=data,headers={'Origin':'https://evil.example'}).status_code==403
    with pytest.raises(RuntimeError,match='caller-owned'):drafts.save_in_transaction(conn,users[0],fields(pilot),operation_key=str(uuid4()))
    conn.execute("UPDATE org_unit SET name='Renamed section' WHERE id=?",(section,));conn.commit()
    source=clients[0].get(response.headers['location']);assert 'section changed' in source.text
    key=data['operation_key'];loaded=clients[0].get('/create',params={'activity_draft':key})
    assert loaded.status_code==200 and 'Renamed section' in loaded.text
    conn.execute("UPDATE org_unit SET level='division' WHERE id=?",(section,));conn.commit()
    assert clients[0].get(response.headers['location']).status_code==200
    assert 'outside the current Create rules' in clients[0].get(response.headers['location']).text
    assert clients[0].get('/create',params={'activity_draft':key}).status_code==404
    no_live_records(conn)


def test_collection_pagination_and_current_create_role(pilot):
    conn,users,clients,app,token,section=pilot
    for i in range(22):
        with transaction(conn):drafts.save_in_transaction(conn,users[0],fields(pilot,activity_name='Synthetic draft '+str(i)),operation_key=str(uuid4()))
    page=drafts.listing(conn,users[0]);assert len(page['data'])==20 and page['next_before']
    older=drafts.listing(conn,users[0],before=page['next_before']);assert len(older['data'])==2 and not older['next_before']
    source='/activity-drafts/'+page['data'][0]['operation_key']
    conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?",(users[0]['id'],));conn.commit()
    current=st.get_admin_user_by_id(conn,users[0]['id']);clients[0].cookies.set(auth.COOKIE_NAME,session_token(current))
    assert clients[0].get(source).status_code==404 and clients[0].get('/activity-drafts').status_code==404
    assert clients[0].get('/create').status_code==403


def test_sdk_and_mobile_without_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,token,section=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='draft-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        context=await server.call_tool('get_activity_draft_context',{})
        assert 'Synthetic organizing section' in str(context) and 'PRIVATE' not in str(context)
        result=await server.call_tool('prepare_activity_draft',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE' not in str(result)
        access.scopes=['activities:read']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_activity_draft',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/activity-drafts/'+KEY)
                expect(page.get_by_role('heading',name='Save this private activity draft?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: save my private activity draft',exact=True).click()
                expect(page.get_by_role('heading',name='Private activity draft saved',exact=True)).to_be_visible()
                page.get_by_role('link',name='Open my private draft',exact=True).click()
                expect(page.get_by_role('heading',name='My private activity draft',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('link',name='Load into Create for separate review',exact=True).click()
                assert page.locator('input[name=activity_name]').input_value()==TITLE
            finally:bc.close()
        finally:browser.close()
    no_live_records(conn)


def test_preview_capacity_and_cleanup_persist_on_rejected_action(pilot,monkeypatch):
    conn,users,clients,app,token,section=pilot
    for i in range(50):prepare(pilot,'draft-capacity-key-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'draft-capacity-overflow')
    conn.execute('UPDATE mcp_activity_draft_operation SET expires_at=1');conn.commit()
    monkeypatch.setenv(pilot_service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError,match='disabled'):
        pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,'draft-capacity-key-0')
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_draft_operation WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_draft_operation').fetchone()[0]==50
    no_live_records(conn)


def test_section_choices_page_limits_and_normal_save_audit_rollback(pilot,monkeypatch):
    conn,users,clients,app,token,section=pilot
    page=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,limit=1)
    assert len(page['sections'])==1 and set(page['sections'][0])=={'id','name'}
    if page['next_offset'] is not None:
        other=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,limit=1,offset=page['next_offset'])
        assert other['sections'][0]['id']!=page['sections'][0]['id']
    with pytest.raises(ValueError):pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,limit=True)
    normal=clients[0].get('/activity-drafts/new')
    data={k:re.search(r'name="'+k+r'" value="([^"]+)"',normal.text).group(1) for k in ('csrf','operation_key')}
    data|={k:str(v) for k,v in fields(pilot).items()}
    original=st.audit
    def fail(c,actor,action,**kw):
        if action=='activity_draft_save':raise RuntimeError('Synthetic normal save audit failure')
        return original(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    assert clients[0].post('/activity-drafts',data=data,headers={'Origin':ORIGIN}).status_code==500
    assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM activity_draft_save').fetchone()[0]==0
