"""One live event/F2 per own private draft, atomic receipts and initial notices."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
import re
from uuid import uuid4

import pytest
from mcp.server.auth.provider import AccessToken

import activity_creation as creation
import activity_creation_delivery as delivery
import activity_drafts as drafts
import auth
import documents_permissions as permissions
from documents_storage import transaction
import mcp_actions
import mcp_activity_creation as pilot_service
import mcp_auth
import mcp_read
import mailer
import storage as st
import tzutil as tz
from tests.test_mcp_activity_drafts import pilot as draft_pilot
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN='http://testserver'
RESOURCE=ORIGIN+'/mcp'
KEY='create-live-activity-001'
TITLE='LIVE_PRIVATE <script>untrusted</script>'
VENUE='PUBLIC_HALL'
DAY='2030-03-07'


@pytest.fixture
def pilot(draft_pilot,monkeypatch):
    conn,users,clients,app,save_token,section=draft_pilot
    conn.execute("UPDATE resource_person SET designation='Section Head' WHERE id=?",(users[1]['rp_id'],));conn.commit()
    with transaction(conn):saved=drafts.save_in_transaction(conn,users[0],
        {'activity_name':TITLE,'event_date':DAY,'section_id':section,'venue':VENUE},operation_key=str(uuid4()))
    monkeypatch.setenv(pilot_service.FLAG,'1')
    monkeypatch.delenv('CSS_MCP_ACTIVITY_DRAFTS_ENABLED',raising=False)
    token=mcp_auth.Provider._tokens(conn,'draft-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,saved['operation_key'])
    values={'draft_key':saved['operation_key'],'expected_revision':context['expected_revision']}
    return conn,users,clients,app,token,saved,save_token,values


def prepare(pilot,key=KEY,data=None):
    return pilot_service.prepare(pilot[0],pilot[4].access_token,RESOURCE,ORIGIN,key,data or pilot[7])


def form(page):
    return {k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','preview_digest')}|{'confirm':'yes'}


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    p=pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=p['preview_digest'])


def test_exact_live_creation_public_source_queue_and_historical_recovery(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:pytest.fail('Confirmation must queue, not send'))
    preview=prepare(pilot)
    assert prepare(pilot)==preview and 'LIVE_PRIVATE' not in json.dumps(preview) and preview['public_url'] is None
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0]==0
    path='/account/integrations/mcp/activity-creation/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert all(t in page.text for t in (VENUE,DAY,'Synthetic organizing section',users[0]['username'],users[1]['username'],'public registration/feedback'))
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    result=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['created_status']=='live_activity' and result['form_count']==1 and result['event_date']==DAY
    assert result['notification_status_counts']=={'queued':2}
    assert result['next_actor']=={'role':'organizer_manage_and_share','initial_notice_recipient_count':2}
    assert 'LIVE_PRIVATE' not in json.dumps(result) and users[1]['username'] not in json.dumps(result)
    mapping=creation.lookup(conn,users[0],saved['operation_key']);event,fi=creation.live_source(conn,users[0],mapping)
    assert event['title']==TITLE and event['event_date']==fi['event_date']==DAY and event['lead_org_id']==saved['fields']['section_id']
    assert event['venue']==fi['venue']==VENUE and event['modality']==fi['modality']=='f2f' and event['event_kind']=='bureau'
    assert event['created_by']==fi['created_by']==users[0]['username'] and fi['survey_type']==2 and fi['form']=='F2'
    assert fi['rp_id'] is None and fi['open_at'] is None and fi['close_at'] is None and not event['end_date']
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1 and conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0]==1
    assert {r[0] for r in conn.execute('SELECT feature FROM mcp_activity_creation_mail')}=={'event_created','event_section_notify'}
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_activity_creation').fetchone()==(None,None)
    for table in ('attendee','response','calendar_entry','room_reservation','travel_filing'):
        assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert drafts.get(conn,users[0],saved['operation_key'])['fields']==saved['fields']
    assert clients[0].get(result['web_url']).status_code==200
    public=clients[2].get(result['public_url']);assert public.status_code==200 and 'LIVE_PRIVATE' in public.text
    assert 'already created from this draft' in clients[0].get('/activity-drafts/'+saved['operation_key']).text
    assert prepare(pilot)==result and clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1
    st.set_event_dates(conn,event['id'],'2030-04-02',None)
    assert prepare(pilot)==result and st.get_event(conn,event['event_token'])['event_date']=='2030-04-02'
    with pytest.raises(mcp_actions.ActionError,match='already created'):prepare(pilot,'another-creation-key-001')


@pytest.mark.parametrize('change',['draft','section','routing','identity','date','source_deleted','duplicate','feature','scope','revoked','expired','payload','snapshot','switch','global_switch','role'])
def test_bound_live_effects_are_rechecked(pilot,monkeypatch,change):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot)
    path='/account/integrations/mcp/activity-creation/'+KEY;page=clients[0].get(path)
    if change=='draft':conn.execute('UPDATE activity_draft SET fields_json=? WHERE id=?',(json.dumps({**saved['fields'],'venue':'Changed'}),saved['id']))
    elif change=='section':conn.execute("UPDATE org_unit SET name='Renamed section' WHERE id=?",(saved['fields']['section_id'],))
    elif change=='routing':conn.execute('UPDATE resource_person SET designation=NULL WHERE id=?',(users[1]['rp_id'],))
    elif change=='identity':conn.execute("UPDATE resource_person SET name='Changed creator' WHERE id=?",(users[0]['rp_id'],))
    elif change=='date':monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,8))
    elif change=='source_deleted':conn.execute('DELETE FROM activity_draft WHERE id=?',(saved['id'],))
    elif change=='duplicate':st.create_event(conn,TITLE,DAY,created_by=users[2]['username'])
    elif change=='feature':st.set_email_feature(conn,'event_created',False)
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"activities:draft:save\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_activity_creation SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_activity_creation SET payload_json=?',(json.dumps({**values,'expected_revision':'a'*64}),))
    elif change=='snapshot':conn.execute('UPDATE mcp_activity_creation SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    elif change=='role':conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?",(users[0]['id'],))
    else:monkeypatch.setenv(pilot_service.FLAG,'0')
    conn.commit()
    response=clients[0].post(path,data=form(page),headers={'Origin':ORIGIN},follow_redirects=False)
    assert response.status_code==({'source_deleted':404,'role':401}.get(change,409))
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==int(change=='duplicate')
    for table in ('form_instance','activity_draft_creation','mcp_activity_creation_mail'):
        assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0


@pytest.mark.parametrize('extra',[{'event_date':DAY},{'activity_name':'Changed'},{'recipient_id':1},{'room':True},{'participant_emails':['x@example.test']},{'duplicate_confirm':'override'},{'status':'approved'},{'end_date':'2030-03-08'}])
def test_no_unreviewed_overrides_or_extra_effects(pilot,extra):
    with pytest.raises(ValueError):prepare(pilot,data={**pilot[7],**extra})


def test_owner_role_scope_connection_and_browser_security(pilot):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot)
    path='/account/integrations/mcp/activity-creation/'+KEY;page=clients[0].get(path)
    assert clients[1].get(path).status_code==404
    assert clients[0].post(path,data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[0].post(path,data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='explicitly allow'):
        pilot_service.prepare(conn,save_token.access_token,RESOURCE,ORIGIN,'wrong-save-scope-001',values)
    other=mcp_auth.Provider._tokens(conn,'draft-test',users[4]['id'],[pilot_service.SCOPE],RESOURCE)
    fresh=mcp_auth.Provider._tokens(conn,'draft-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.read_context(conn,other.access_token,RESOURCE,ORIGIN,saved['operation_key'])
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)


def test_atomic_rollback_then_two_keys_and_same_key_races(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot)
    original=st.audit
    def fail(c,actor,action,**kw):
        if action=='integration_action_complete':raise RuntimeError('Synthetic receipt failure')
        return original(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):confirm(pilot)
    for table in ('event','form_instance','event_form','activity_draft_creation','mcp_activity_creation_mail'):
        assert conn.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_activity_creation').fetchone()[0] is None
    monkeypatch.setattr(st,'audit',original)
    other='competing-creation-key-001';prepare(pilot,other)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    keys=(KEY,other);digests={key:pilot_service.browser(conn,payload,RESOURCE,ORIGIN,key)['preview_digest'] for key in keys}
    def worker(key):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,key,confirm_digest=digests[key])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(worker,keys))
    assert sorted(result)==['completed','conflict']
    winner=keys[result.index('completed')]
    with ThreadPoolExecutor(max_workers=2) as executor:assert list(executor.map(worker,(winner,winner)))==['completed','completed']
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_creation_mail').fetchone()[0]==2


def test_deleted_and_reused_live_id_does_not_allow_another_creation(pilot):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot);result=confirm(pilot)
    mapping=creation.lookup(conn,users[0],saved['operation_key'])
    conn.execute('DELETE FROM event_form WHERE event_id=?',(mapping['event_id'],));conn.execute('DELETE FROM event WHERE id=?',(mapping['event_id'],));conn.commit()
    replacement=st.create_event(conn,'Synthetic reused source',DAY,form_instance_ids=[mapping['form_id']],created_by=users[0]['username'])
    assert replacement['id']==mapping['event_id']
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    with pytest.raises(mcp_actions.ActionError,match='already created'):prepare(pilot,'after-deletion-creation-001')
    source=clients[0].get('/activity-drafts/'+saved['operation_key'])
    assert source.status_code==200 and 'original activity source is unavailable' in source.text
    assert conn.execute('SELECT COUNT(*) FROM activity_draft_creation').fetchone()[0]==1


@pytest.mark.parametrize('outcome',['sent','false','raise','crash','result_failure'])
def test_notice_transport_attempt_is_never_automatically_repeated(pilot,monkeypatch,outcome):
    conn,users,clients,app,token,saved,save_token,values=pilot
    conn.execute('UPDATE resource_person SET designation=NULL WHERE id=?',(users[1]['rp_id'],));conn.commit()
    updated={**values,'expected_revision':pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,saved['operation_key'])['expected_revision']}
    prepare(pilot,data=updated);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True);calls=[]
    def send(to,subject,body,**kw):
        assert not conn.in_transaction;calls.append(to)
        assert to==users[0]['username'] and '/monitor/' in body
        if outcome=='raise':raise RuntimeError('Synthetic ambiguous send')
        if outcome=='crash':raise KeyboardInterrupt('Synthetic worker death')
        return {'sent':outcome!='false'}
    original=delivery._finish
    if outcome=='result_failure':
        def fail(*a,**kw):
            if kw.get('attempt'):raise RuntimeError('Synthetic result-write failure')
            return original(*a,**kw)
        monkeypatch.setattr(delivery,'_finish',fail)
        with pytest.raises(RuntimeError):delivery.run(conn,send=send)
        monkeypatch.setattr(delivery,'_finish',original)
    elif outcome=='crash':
        with pytest.raises(KeyboardInterrupt):delivery.run(conn,send=send)
    else:assert delivery.run(conn,send=send)==1
    assert delivery.run(conn,send=send)==0
    if outcome in ('crash','result_failure'):conn.execute('UPDATE mcp_activity_creation_mail SET attempted_at=1');conn.commit()
    delivery.run(conn,send=send)
    assert calls==[users[0]['username']]
    assert conn.execute('SELECT state,payload_json FROM mcp_activity_creation_mail').fetchone()==('sent' if outcome=='sent' else 'uncertain',None)


@pytest.mark.parametrize('change,state',[('feature','skipped_off'),('pause','skipped_off'),('transport','not_configured'),('revoked','cancelled'),('edited','cancelled'),('payload','cancelled'),('expired','cancelled')])
def test_notice_gates_and_cleanup(pilot,monkeypatch,change,state):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot);result=confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:change!='transport')
    if change=='feature':
        st.set_email_feature(conn,'event_created',False);st.set_email_feature(conn,'event_section_notify',False)
    elif change=='pause':st.set_email_paused(conn,True)
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='edited':st.set_event_dates(conn,int(result['event_id']),'2030-04-03',None)
    elif change=='payload':conn.execute("UPDATE mcp_activity_creation_mail SET payload_json='{}'")
    elif change=='expired':conn.execute('UPDATE mcp_activity_creation_mail SET created_at=1')
    conn.commit()
    assert delivery.run(conn,send=lambda *a,**kw:pytest.fail('Blocked send'))==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_creation_mail WHERE state=? AND payload_json IS NULL',(state,)).fetchone()[0]==2


def test_two_delivery_workers_and_disabled_sender(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True);calls=[]
    def send(to,*a,**kw):calls.append(to);return {'sent':True}
    monkeypatch.setenv(pilot_service.FLAG,'0');assert delivery.run(conn,send=send)==0 and not calls
    monkeypatch.setenv(pilot_service.FLAG,'1')
    def worker(_):
        c=app.get_conn()
        try:return delivery.run(c,send=send)
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(worker,range(2)))
    assert sum(result)==2 and sorted(calls)==sorted([users[0]['username'],users[1]['username']])
    assert delivery.run(conn,send=send)==0


def test_shared_normal_create_path_and_caller_owned_primitives(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot
    seen=[];original=creation.create_bureau_in_transaction
    def spy(*a,**kw):seen.append(True);return original(*a,**kw)
    monkeypatch.setattr(creation,'create_bureau_in_transaction',spy)
    prepare(pilot);confirm(pilot);assert len(seen)==1
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:{'sent':True})
    normal=clients[0].post('/create',data={'event_type':'bureau','activity_name':'Separate normal bureau forum',
        'event_date':'2030-04-17','section_id':str(saved['fields']['section_id']),'venue':'Normal hall','modality':'f2f','qr_mode':'combined'},headers={'Origin':ORIGIN})
    assert normal.status_code==200 and len(seen)==2
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==2 and conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0]==2
    with pytest.raises(RuntimeError,match='caller-owned'):st.create_form_instance(conn,2,'F2',DAY,commit=False)
    with pytest.raises(RuntimeError,match='caller-owned'):st.create_event(conn,'No transaction',DAY,commit=False)


def test_sdk_and_mobile_confirmation_without_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,token,saved,save_token,values=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='draft-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        current=await server.call_tool('get_activity_creation_context',{'draft_key':saved['operation_key']})
        assert 'expected_revision' in str(current) and 'LIVE_PRIVATE' not in str(current)
        preview=await server.call_tool('prepare_activity_from_draft',{**values,'operation_id':KEY})
        assert 'awaiting_confirmation' in str(preview) and 'LIVE_PRIVATE' not in str(preview)
        access.scopes=['activities:draft:save']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_activity_from_draft',{**values,'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/activity-creation/'+KEY)
                expect(page.get_by_role('heading',name='Create this live activity from my draft?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: create live activity',exact=True).click()
                expect(page.get_by_role('heading',name='Live activity created',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_disabled_at_confirmation_never_sends_after_later_enable(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot
    st.set_email_feature(conn,'event_created',False)
    current=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,saved['operation_key'])
    prepare(pilot,data={**values,'expected_revision':current['expected_revision']});result=confirm(pilot)
    assert result['notification_status_counts']=={'queued':1,'skipped_off':1}
    assert conn.execute("SELECT payload_json FROM mcp_activity_creation_mail WHERE feature='event_created'").fetchone()[0] is None
    st.set_email_feature(conn,'event_created',True);monkeypatch.setattr(mailer,'email_configured',lambda:True);calls=[]
    assert delivery.run(conn,send=lambda to,*a,**kw:(calls.append(to) or {'sent':True}))==1
    assert calls==[users[1]['username']]
    assert conn.execute("SELECT COUNT(*) FROM email_log WHERE feature='event_created' AND status='skipped_off'").fetchone()[0]==1


def test_lost_chief_cancels_only_its_notice(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot);confirm(pilot)
    conn.execute('UPDATE resource_person SET designation=NULL WHERE id=?',(users[1]['rp_id'],));conn.commit()
    monkeypatch.setattr(mailer,'email_configured',lambda:True);calls=[]
    assert delivery.run(conn,send=lambda to,*a,**kw:(calls.append(to) or {'sent':True}))==1
    assert calls==[users[0]['username']]
    assert conn.execute("SELECT state,payload_json FROM mcp_activity_creation_mail WHERE feature='event_section_notify'").fetchone()==('cancelled',None)


def test_separate_draft_cannot_override_strong_existing_activity(pilot):
    conn,users,clients,app,token,saved,save_token,values=pilot;prepare(pilot);confirm(pilot)
    with transaction(conn):other=drafts.save_in_transaction(conn,users[0],saved['fields'],operation_key=str(uuid4()))
    with pytest.raises(mcp_actions.ActionError,match='strong activity duplicate'):
        pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,other['operation_key'])
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1


def test_expired_preview_cleanup_is_committed_even_with_creation_disabled(pilot,monkeypatch):
    conn,users,clients,app,token,saved,save_token,values=pilot
    for i in range(50):prepare(pilot,'live-capacity-key-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'live-capacity-overflow')
    conn.execute('UPDATE mcp_activity_creation SET expires_at=1');conn.commit()
    monkeypatch.setenv(pilot_service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError,match='disabled'):
        pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,'live-capacity-key-0')
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_creation WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM activity_draft').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==0
