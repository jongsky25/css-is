"""Bounded activity re-dating: exact revision, UI authority, atomicity and recovery."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime
import json
import re
import time

import pytest
from mcp.server.auth.provider import AccessToken

import activity_scheduling as scheduling
import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_activity_dates as pilot_service
import mcp_read
import mailer
import storage as st
import tzutil as tz
from tests.test_integration_read_api import api
from tests.test_work import workspace
from tests.conftest import session_token

ORIGIN='http://testserver'
RESOURCE=ORIGIN+'/mcp'
KEY='activity-date-change-001'
TITLE='PRIVATE_ACTIVITY <script>untrusted</script>'
OLD='2030-03-07'
NEW='2030-04-08'


@pytest.fixture
def pilot(api,monkeypatch):
    conn,users,unit,clients,app=api
    monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,4))
    monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,4,9))
    for flag in ('CSS_MCP_ENABLED',pilot_service.FLAG):monkeypatch.setenv(flag,'1')
    for flag in ('CSS_BASE_URL','SPACE_HOST'):monkeypatch.delenv(flag,raising=False)
    for idx in (0,1):
        rp=st.add_rp(conn,'Synthetic activity manager '+str(idx),True,unit)
        conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,users[idx]['id']))
    # User 0 is the creator; user 1 manages the same team. Ordinary creator
    # authority also applies to a creator whose current role is viewer.
    conn.execute("UPDATE admin_user SET role='section_manager' WHERE id=?",(users[1]['id'],));conn.commit()
    users[:2]=[st.get_admin_user_by_id(conn,u['id']) for u in users[:2]]
    clients[1].cookies.set(auth.COOKIE_NAME,session_token(users[1]))
    fid=st.create_form_instance(conn,2,'F2',OLD,topic=TITLE,lead_org_id=unit,created_by=users[0]['username'])
    ev=st.create_event(conn,TITLE,OLD,venue='PRIVATE_LOCATION',lead_org_id=unit,form_instance_ids=[fid],created_by=users[0]['username'])
    conn.execute("UPDATE event SET welcome_message='PRIVATE_MESSAGE' WHERE id=?",(ev['id'],));conn.commit()
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)',('date-test',json.dumps({'client_name':'Activity dates test'}),int(time.time())))
    token=mcp_auth.Provider._tokens(conn,'date-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,token,ev,fid


def fields(pilot,**changes):
    _,_,info=scheduling.owned_context(pilot[0],pilot[1][0],pilot[5]['id'])
    return {'event_id':pilot[5]['id'],'expected_revision':info['expected_revision'],'event_date':NEW,**changes}


def prepare(pilot,key=KEY,data=None):
    return pilot_service.prepare(pilot[0],pilot[4].access_token,RESOURCE,ORIGIN,key,data or fields(pilot))


def form(page):
    return {k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','preview_digest')}|{'confirm':'yes'}


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    preview=pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=preview['preview_digest'])


def test_exact_date_form_cache_source_and_original_receipt(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:pytest.fail('Date changes must not send'))
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,ev['event_token'])
    assert context['event_date']==OLD and context['expected_revision']==fields(pilot)['expected_revision']
    assert 'PRIVATE' not in json.dumps(context)
    original=fields(pilot);preview=prepare(pilot,data=original)
    assert prepare(pilot,data=original)==preview and 'PRIVATE' not in json.dumps(preview)
    assert st.get_event(conn,ev['event_token'])['event_date']==OLD
    path='/account/integrations/mcp/activity-dates/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert OLD in page.text and NEW in page.text and 'PRIVATE_LOCATION' not in page.text and 'PRIVATE_MESSAGE' not in page.text
    epoch=app._atoms_state['epoch']
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert app._atoms_state['epoch']>epoch
    result=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['status']=='completed' and result['change_status']=='date_updated'
    assert result['old_event_date']==OLD and result['event_date']==NEW and result['updated_forms']==1
    assert result['reporting_period_before']=={'year':2030,'quarter':1} and result['reporting_period_after']=={'year':2030,'quarter':2}
    assert result['notification_status']=='none_created' and 'PRIVATE' not in json.dumps(result)
    assert conn.execute('SELECT event_date,end_date FROM event WHERE id=?',(ev['id'],)).fetchone()==(NEW,None)
    assert conn.execute('SELECT event_date,end_date FROM form_instance WHERE id=?',(fid,)).fetchone()==(NEW,None)
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0]==1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_activity_dates').fetchone()==(None,None)
    assert clients[0].get(result['web_url']).status_code==200
    assert prepare(pilot,data=original)==result
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    later='2030-05-10';st.set_event_dates(conn,ev['id'],later,None)
    assert prepare(pilot,data=original)==result and st.get_event(conn,ev['event_token'])['event_date']==later


@pytest.mark.parametrize('change',['source','authority','form','archive','pooled','locked','window','attendance','demographics','registration','response','calendar','room','travel','shared','speaker','multiday','outside','day_started','scope','revoked','expired','payload','snapshot','switch','global_switch'])
def test_confirmation_rechecks_unused_source_and_current_authority(pilot,monkeypatch,change):
    conn,users,clients,app,token,ev,fid=pilot;prepare(pilot)
    path='/account/integrations/mcp/activity-dates/'+KEY;page=clients[0].get(path)
    if change=='source':conn.execute("UPDATE event SET welcome_message='Changed private body' WHERE id=?",(ev['id'],))
    elif change=='authority':conn.execute('UPDATE event SET created_by=? WHERE id=?',(users[2]['username'],ev['id']))
    elif change=='form':conn.execute("UPDATE form_instance SET topic='Changed topic' WHERE id=?",(fid,))
    elif change in ('archive','pooled','locked'):
        column={'archive':'archived','pooled':'pooled','locked':'encoding_locked'}[change]
        conn.execute('UPDATE form_instance SET '+column+'=1 WHERE id=?',(fid,))
    elif change=='window':conn.execute("UPDATE form_instance SET open_at='2030-03-06T09:00' WHERE id=?",(fid,))
    elif change=='attendance':conn.execute('UPDATE form_instance SET attendance=1 WHERE id=?',(fid,))
    elif change=='demographics':st.set_activity_demographics(conn,ev['id'],male=1,female=0,doh=1,nondoh=0,by=users[0]['username'])
    elif change=='registration':st.add_attendee(conn,ev['id'],name='Synthetic person',email='synthetic@example.test',sex='F',affiliation='DOH',consent_text='Synthetic consent')
    elif change=='response':st.record_response(conn,fid,[])
    elif change=='calendar':st.cal_create(conn,'Synthetic linked item',OLD,event_id=ev['id'],by=users[0]['username'])
    elif change=='room':conn.execute("INSERT INTO room_reservation(title,day,status,requester_user_id,event_id) VALUES ('Synthetic room',?,'requested',?,?)",(OLD,users[0]['id'],ev['id']))
    elif change=='travel':conn.execute("INSERT INTO travel_filing(user_id,kind,source_kind,event_id,act_title,act_start,act_end,deadline_date,status) VALUES (?,'ca','blank',?,'Synthetic travel',?,?,?,'open')",(users[0]['id'],ev['id'],OLD,OLD,OLD))
    elif change=='shared':st.create_event(conn,'Synthetic shared form',OLD,form_instance_ids=[fid],created_by=users[0]['username'])
    elif change=='speaker':
        second=st.create_form_instance(conn,3,'F3',OLD,topic='Synthetic speaker')
        conn.execute('INSERT INTO event_form VALUES (?,?,1)',(ev['id'],second))
    elif change=='multiday':conn.execute("UPDATE event SET end_date='2030-03-08' WHERE id=?",(ev['id'],))
    elif change=='outside':conn.execute("UPDATE event SET event_kind='outside' WHERE id=?",(ev['id'],))
    elif change=='day_started':monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,7))
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"activities:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_activity_dates SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_activity_dates SET payload_json=?',(json.dumps(fields(pilot,event_date='2030-05-10')),))
    elif change=='snapshot':conn.execute('UPDATE mcp_activity_dates SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    else:monkeypatch.setenv(pilot_service.FLAG,'0')
    conn.commit()
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in ((404,) if change=='authority' else (409,))
    assert conn.execute('SELECT event_date FROM event WHERE id=?',(ev['id'],)).fetchone()[0]==OLD
    assert conn.execute('SELECT event_date FROM form_instance WHERE id=?',(fid,)).fetchone()[0]==OLD
    if change=='expired':assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_activity_dates').fetchone()==(None,None)


@pytest.mark.parametrize('changes',[
    {'event_id':True},{'event_id':'1'},{'event_id':0},{'event_id':2**63},
    {'expected_revision':'guess'},{'event_date':'2030-02-30'},{'event_date':'20300408'},
    {'end_date':'2030-04-10'},{'title':'Other'},{'venue':'Other'},{'event_token':'override'},
    {'email_registrants':True},{'status':'cancelled'},{'form_ids':[1]},
])
def test_strict_inputs_and_no_other_writes(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changes))


@pytest.mark.parametrize('target',[OLD,'2030-03-04','2030-03-03','2032-03-05'])
def test_future_different_date_and_current_horizon(pilot,target):
    with pytest.raises(mcp_actions.ActionError):prepare(pilot,data=fields(pilot,event_date=target))
    assert pilot[0].execute('SELECT event_date FROM event WHERE id=?',(pilot[5]['id'],)).fetchone()[0]==OLD


def test_ui_authority_team_creator_admin_and_retagging(pilot):
    conn,users,clients,app,token,ev,fid=pilot
    for idx,allowed in ((0,True),(1,True),(2,False),(4,True)):
        current=st.get_admin_user_by_id(conn,users[idx]['id'])
        assert app._can_manage_event(current,st.get_event(conn,ev['event_token']),conn)==allowed
        granted=mcp_auth.Provider._tokens(conn,'date-test',current['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
        if allowed:assert pilot_service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,ev['event_token'])['event_id']==str(ev['id'])
        else:
            with pytest.raises(permissions.Denied):pilot_service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,ev['event_token'])
    manager=mcp_auth.Provider._tokens(conn,'date-test',users[1]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    _,_,info=scheduling.owned_context(conn,users[1],ev['id'])
    data={'event_id':ev['id'],'expected_revision':info['expected_revision'],'event_date':NEW}
    pilot_service.prepare(conn,manager.access_token,RESOURCE,ORIGIN,'team-date-update-key-001',data)
    other=st.add_org_unit(conn,'Other division','division','OTHER/DIV')
    conn.execute('UPDATE event SET lead_org_id=? WHERE id=?',(other,ev['id']));conn.commit()
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME))
    with pytest.raises(permissions.Denied):pilot_service.browser(conn,payload,RESOURCE,ORIGIN,'team-date-update-key-001')


def test_security_and_domain_receipt_rollback(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot;prepare(pilot)
    path='/account/integrations/mcp/activity-dates/'+KEY;page=clients[0].get(path)
    assert clients[1].get(path).status_code==404
    assert clients[0].post(path,data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[0].post(path,data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='different date change'):
        prepare(pilot,data=fields(pilot,event_date='2030-05-10'))
    original=st.audit
    def fail(c,actor,action,**kw):
        if action=='integration_action_complete':raise RuntimeError('Synthetic final audit failure')
        return original(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):confirm(pilot)
    assert conn.execute('SELECT event_date FROM event WHERE id=?',(ev['id'],)).fetchone()[0]==OLD
    assert conn.execute('SELECT event_date FROM form_instance WHERE id=?',(fid,)).fetchone()[0]==OLD
    assert conn.execute('SELECT completed_at FROM mcp_activity_dates').fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='event_dates_set'").fetchone()[0]==0
    with pytest.raises(RuntimeError,match='caller-owned'):st.set_event_dates(conn,ev['id'],NEW,None,commit=False)


def test_same_revision_two_keys_and_same_key_races(pilot):
    conn,users,clients,app,token,ev,fid=pilot
    original=fields(pilot);keys=(KEY,'competing-date-operation-001')
    for key in keys:prepare(pilot,key,original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    digests={key:pilot_service.browser(conn,payload,RESOURCE,ORIGIN,key)['preview_digest'] for key in keys}
    def worker(key):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,key,confirm_digest=digests[key])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(worker,keys))
    assert sorted(results)==['completed','conflict']
    winner=keys[results.index('completed')]
    with ThreadPoolExecutor(max_workers=2) as executor:assert list(executor.map(worker,(winner,winner)))==['completed','completed']
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='event_dates_set'").fetchone()[0]==1


def test_deleted_reused_event_identity_and_connection_session(pilot):
    conn,users,clients,app,token,ev,fid=pilot;prepare(pilot);confirm(pilot)
    fresh=mcp_auth.Provider._tokens(conn,'date-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    conn.execute('DELETE FROM event_form WHERE event_id=?',(ev['id'],));conn.execute('DELETE FROM event WHERE id=?',(ev['id'],));conn.commit()
    new=st.create_event(conn,'Synthetic reused event',NEW,form_instance_ids=[fid],created_by=users[0]['username'])
    assert new['id']==ev['id']
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)


def test_post_commit_cache_failure_is_recoverable_without_repeating_change(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/activity-dates/'+KEY;page=clients[0].get(path)
    saved=app.invalidate_atoms
    monkeypatch.setattr(app,'invalidate_atoms',lambda:(_ for _ in ()).throw(RuntimeError('Synthetic cache failure')))
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==500
    result=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['status']=='completed' and st.get_event(conn,ev['event_token'])['event_date']==NEW
    monkeypatch.setattr(app,'invalidate_atoms',saved)
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='event_dates_set'").fetchone()[0]==1


def test_sdk_and_mobile_confirmation_without_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,token,ev,fid=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='date-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        result=await server.call_tool('prepare_activity_date_update',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE' not in str(result)
        access.scopes=['activities:read']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_activity_date_update',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/activity-dates/'+KEY)
                expect(page.get_by_role('heading',name="Change this activity's date?",exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: change activity date',exact=True).click()
                expect(page.get_by_role('heading',name='Activity date updated',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_later_normal_registration_and_response_do_not_replay_change(pilot):
    conn,users,clients,app,token,ev,fid=pilot;original=fields(pilot);prepare(pilot,data=original);confirm(pilot)
    result=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    attendee=st.add_attendee(conn,ev['id'],name='Synthetic later participant',email='synthetic-later@example.test',sex='F',affiliation='DOH',consent_text='Synthetic consent')
    st.record_response(conn,fid,[],attendee_id=attendee)
    assert prepare(pilot,data=original)==result
    with pytest.raises(mcp_actions.ActionError):pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,ev['event_token'])
    assert conn.execute('SELECT event_date FROM event WHERE id=?',(ev['id'],)).fetchone()[0]==NEW


def test_capacity_and_expiry_cleanup_survive_a_disabled_action(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot
    for i in range(50):prepare(pilot,'date-capacity-key-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'date-capacity-overflow')
    conn.execute('UPDATE mcp_activity_dates SET expires_at=1');conn.commit()
    monkeypatch.setenv(pilot_service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError,match='disabled'):
        pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,'date-capacity-key-0')
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_dates WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_dates').fetchone()[0]==50
    assert conn.execute('SELECT event_date FROM event WHERE id=?',(ev['id'],)).fetchone()[0]==OLD


def test_context_resolves_existing_monitor_link_and_custom_slug(pilot):
    from urllib.parse import urlsplit
    conn,users,clients,app,token,ev,fid=pilot
    monitor_url=ORIGIN+'/monitor/'+ev['event_token']
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,urlsplit(monitor_url).path.rsplit('/',1)[-1])
    assert context['event_id']==str(ev['id']) and '/activities/'+ev['event_token']+'/manage' in context['web_url']
    st.set_event_slug(conn,ev['id'],'synthetic-upcoming')
    alias=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,'synthetic-upcoming')
    assert alias['event_id']==str(ev['id']) and alias['web_url']==context['web_url']
    data={'event_id':int(alias['event_id']),'expected_revision':alias['expected_revision'],'event_date':NEW}
    assert prepare(pilot,data=data)['status']=='awaiting_confirmation'
    for invalid in (True,ev['id'],'/monitor/'+ev['event_token'],'x'*41,'../secret'):
        with pytest.raises(ValueError):pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,invalid)
