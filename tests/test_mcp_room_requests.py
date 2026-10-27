"""One plain linked room request, pending approval, with durable initial notices."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime
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
import mcp_room_requests as pilot_service
import mailer
import room_actions
import room_request_delivery as delivery
import rooms
import rooms_notify
import storage as st
import tzutil as tz
from tests.conftest import join_admin_section
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN='http://testserver'
RESOURCE=ORIGIN+'/mcp'
KEY='linked-room-request-001'
TITLE='PRIVATE_ROOM <script>untrusted</script>'
DAY='2030-03-07'


@pytest.fixture
def pilot(api,monkeypatch):
    conn,users,unit,clients,app=api
    monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,4))
    monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,4,9))
    for flag in ('CSS_MCP_ENABLED',pilot_service.FLAG):monkeypatch.setenv(flag,'1')
    for flag in ('CSS_BASE_URL','SPACE_HOST','CSS_MCP_PERSONAL_CALENDAR_ENABLED'):monkeypatch.delenv(flag,raising=False)
    join_admin_section(conn,users[1]['id']);users[1]=st.get_admin_user_by_id(conn,users[1]['id'])
    owner_rp=st.add_rp(conn,'Synthetic room owner',True,unit)
    conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(owner_rp,users[0]['id']));conn.commit()
    users[0]=st.get_admin_user_by_id(conn,users[0]['id'])
    eid=st.cal_create(conn,TITLE,DAY,kind='meeting',status='tentative',audience='people',people=[users[0]['id']],
                      start_time='09:00',end_time='10:00',meeting_url='https://private.example/meeting',note='PRIVATE_CALENDAR_NOTE',by=users[0]['username'])
    rooms.ensure_slots(conn)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)',('room-test',json.dumps({'client_name':'Room test'}),int(time.time())))
    token=mcp_auth.Provider._tokens(conn,'room-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,eid,token


def fields(pilot,**changes):
    return {'entry_id':pilot[4],'expected_revision':room_actions.revision(st.cal_get(pilot[0],pilot[4])),
            'from_time':'09:00','to_time':'10:00',**changes}


def prepare(pilot,operation_id=KEY,data=None):
    return pilot_service.prepare(pilot[0],pilot[5].access_token,RESOURCE,ORIGIN,operation_id,data or fields(pilot))


def form(page):
    return {k:re.search(r'name="'+k+r'" value="([^"]+)"',page.text).group(1) for k in ('csrf','preview_digest')}|{'confirm':'yes'}


def confirm(pilot,operation_id=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    p=pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,operation_id)
    return pilot_service.browser(pilot[0],payload,RESOURCE,ORIGIN,operation_id,confirm_digest=p['preview_digest'])


def test_exact_request_link_notices_pending_state_and_recovery(pilot,monkeypatch):
    conn,users,clients,app,eid,token=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**kw:pytest.fail('Confirmation must queue, not send'))
    before=st.cal_get(conn,eid)
    preview=prepare(pilot)
    assert prepare(pilot)==preview and 'PRIVATE_ROOM' not in json.dumps(preview)
    assert not conn.execute('SELECT * FROM room_reservation').fetchall()
    path='/account/integrations/mcp/room-requests/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert '09:00' in page.text and '10:00' in page.text and 'no booking' in page.text
    assert users[1]['username'] in page.text and 'PRIVATE_CALENDAR_NOTE' not in page.text and 'private.example' not in page.text
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    receipt=pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert receipt['status']=='completed' and receipt['requested_status']=='requested' and receipt['booking_held'] is False
    assert receipt['next_actor']=={'role':'administrative_section_room_approver','initial_notice_recipient_count':1}
    assert receipt['notification_status_counts']=={'queued':1}
    assert 'PRIVATE_ROOM' not in json.dumps(receipt) and users[1]['username'] not in json.dumps(receipt)
    record=rooms.get_reservation(conn,int(receipt['room_request_id']))
    assert record['requester_user_id']==users[0]['id'] and record['calendar_entry_id']==eid and record['status']=='requested'
    assert not record['standby'] and not record['meals_requested'] and not record['series_id'] and not record['event_id']
    assert conn.execute('SELECT SUM(is_approved) FROM room_reservation_slot').fetchone()[0]==0
    assert st.cal_get(conn,eid)==before
    assert prepare(pilot)==receipt
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute('SELECT COUNT(*) FROM room_reservation').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_notice').fetchone()[0]==1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_room_request').fetchone()==(None,None)
    assert clients[0].get(receipt['web_url']).status_code==200 and receipt['reference'] in clients[0].get(receipt['web_url']).text
    rooms.approve(conn,record['id'],users[1]['username'],today=date(2030,3,4))
    assert prepare(pilot)==receipt and rooms.get_reservation(conn,record['id'])['status']=='approved'


@pytest.mark.parametrize('change',['meeting','access','cancelled','repeat','multiday','closed','booked','slots','routing','identity','scope','revoked','expired','payload','snapshot','switch'])
def test_current_meeting_availability_and_authority_rechecked(pilot,monkeypatch,change):
    conn,users,clients,app,eid,token=pilot;prepare(pilot)
    path='/account/integrations/mcp/room-requests/'+KEY;page=clients[0].get(path)
    if change=='meeting':conn.execute("UPDATE calendar_entry SET note='changed without time' WHERE id=?",(eid,))
    elif change=='access':
        conn.execute("UPDATE calendar_entry SET created_by=? WHERE id=?",(users[2]['username'],eid));conn.execute('DELETE FROM calendar_entry_person WHERE entry_id=?',(eid,))
    elif change=='cancelled':conn.execute("UPDATE calendar_entry SET status='cancelled' WHERE id=?",(eid,))
    elif change=='repeat':conn.execute("UPDATE calendar_entry SET rrule='FREQ=WEEKLY;UNTIL=20300401' WHERE id=?",(eid,))
    elif change=='multiday':conn.execute("UPDATE calendar_entry SET end_date='2030-03-08' WHERE id=?",(eid,))
    elif change=='closed':st.set_holiday(conn,DAY,'New holiday','regular')
    elif change=='booked':
        conn.commit();slot=room_actions.slot_block(conn,'09:00','10:00')[0]['id']
        rival=rooms.request(conn,title='PRIVATE_RIVAL',day=DAY,slot_ids=[slot],requester_user_id=users[2]['id'],actor=users[2]['username'])
        rooms.approve(conn,rival['id'],users[1]['username'],today=date(2030,3,4))
    elif change=='slots':conn.execute("UPDATE room_slot SET label='Changed configured hour' WHERE start_time='09:00'")
    elif change=='routing':join_admin_section(conn,users[2]['id'])
    elif change=='identity':conn.execute("UPDATE resource_person SET name='Changed requester name' WHERE id=?",(users[0]['rp_id'],))
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"calendar:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_room_request SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_room_request SET payload_json=?',(json.dumps(fields(pilot,from_time='10:00')),))
    elif change=='snapshot':conn.execute('UPDATE mcp_room_request SET snapshot_json=NULL')
    else:monkeypatch.setenv(pilot_service.FLAG,'0')
    conn.commit()
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (303,404,409)
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_identity').fetchone()[0]==0


@pytest.mark.parametrize('changed',[{'entry_id':True},{'entry_id':0},{'expected_revision':'guess'},{'from_time':'25:00'},
    {'from_time':'09:30'},{'to_time':'09:00'},{'meals_requested':True},{'standby':True},{'requester_user_id':2},{'repeat':'weekly'}])
def test_invalid_and_unsupported_fields_rejected(pilot,changed):
    with pytest.raises((ValueError,mcp_actions.ActionError)):prepare(pilot,data=fields(pilot,**changed))
    assert not pilot[0].execute('SELECT * FROM room_reservation').fetchall()


def test_scope_actor_connection_csrf_origin_session(pilot):
    conn,users,clients,app,eid,token=pilot;prepare(pilot)
    foreign=mcp_auth.Provider._tokens(conn,'room-test',users[2]['id'],[pilot_service.SCOPE],RESOURCE)
    read=mcp_auth.Provider._tokens(conn,'room-test',users[0]['id'],['calendar:read','calendar:entry:create'],RESOURCE)
    fresh=mcp_auth.Provider._tokens(conn,'room-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.prepare(conn,foreign.access_token,RESOURCE,ORIGIN,KEY,fields(pilot))
    with pytest.raises(mcp_actions.ActionError):pilot_service.prepare(conn,read.access_token,RESOURCE,ORIGIN,KEY,fields(pilot))
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    path='/account/integrations/mcp/room-requests/'+KEY;page=clients[0].get(path)
    assert clients[2].get(path).status_code==404
    for values,origin in (({**form(page),'csrf':'bad'},ORIGIN),(form(page),'https://evil.example'),({**form(page),'confirm':'no'},ORIGIN)):
        assert clients[0].post(path,data=values,headers={'Origin':origin}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME));conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):confirm(pilot)


def test_rollback_and_two_distinct_previews_commit_one_request_and_notice(pilot,monkeypatch):
    conn,users,clients,app,eid,token=pilot;prepare(pilot);prepare(pilot,'second-linked-room-001')
    original=st.audit
    def failed(*a,**kw):
        if a[2]=='integration_action_complete':raise RuntimeError('Synthetic completion failure')
        return original(*a,**kw)
    monkeypatch.setattr(st,'audit',failed)
    with pytest.raises(RuntimeError):confirm(pilot)
    for table in ('room_reservation','room_reservation_slot','room_notice','mcp_room_identity','mcp_room_notice'):
        assert not conn.execute('SELECT * FROM '+table).fetchall()
    monkeypatch.setattr(st,'audit',original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME));previews=[pilot_service.browser(conn,payload,RESOURCE,ORIGIN,k) for k in (KEY,'second-linked-room-001')]
    def commit(p):
        c=app.get_conn()
        try:return pilot_service.browser(c,payload,RESOURCE,ORIGIN,p['operation_id'],confirm_digest=p['preview_digest'])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(commit,previews))
    assert sorted(result)==['completed','conflict']
    assert conn.execute('SELECT COUNT(*) FROM room_reservation').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_notice').fetchone()[0]==1


@pytest.mark.parametrize('outcome',['sent','false','raise','crash','result_failure'])
def test_notice_delivery_attempts_once_and_legacy_flush_never_replays(pilot,monkeypatch,outcome):
    conn,users,clients,app,eid,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True);calls=[]
    def send(*a,**kw):
        assert not conn.in_transaction;calls.append(a)
        if outcome=='raise':raise RuntimeError('Synthetic ambiguous transport')
        if outcome=='crash':raise KeyboardInterrupt('Synthetic worker death')
        return {'sent':outcome not in ('false',)}
    assert rooms_notify.flush(conn,ORIGIN,send=send)=={} and not calls
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
    if outcome in ('crash','result_failure'):
        assert delivery.run(conn,send=send)==0
        conn.execute('UPDATE mcp_room_notice SET attempted_at=1');conn.commit()
    delivery.run(conn,send=send)
    assert len(calls)==1
    assert conn.execute('SELECT state FROM mcp_room_notice').fetchone()[0]==('sent' if outcome=='sent' else 'uncertain')
    assert rooms_notify.flush(conn,ORIGIN,send=send)=={} and len(calls)==1


@pytest.mark.parametrize('change,expected',[('feature','skipped_off'),('pause','skipped_off'),('transport','not_configured'),
    ('reviewer','cancelled'),('revoked','cancelled'),('expired','cancelled')])
def test_notice_gates(pilot,monkeypatch,change,expected):
    conn,users,clients,app,eid,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:change!='transport')
    if change=='feature':st.set_email_feature(conn,'room_new_request',False)
    elif change=='pause':st.set_email_paused(conn,True)
    elif change=='reviewer':conn.execute("UPDATE resource_person SET archived_at='2030-03-04' WHERE id=?",(users[1]['rp_id'],))
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_room_notice SET created_at=1')
    conn.commit()
    def send(*a,**kw):pytest.fail('Blocked notice cannot send')
    assert delivery.run(conn,send=send)==0
    assert conn.execute('SELECT state FROM mcp_room_notice').fetchone()[0]==expected


def test_read_context_and_mobile_confirmation(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,eid,token=pilot
    context=pilot_service.read_context(conn,token.access_token,RESOURCE,ORIGIN,eid)
    assert context['expected_revision']==fields(pilot)['expected_revision'] and not context['has_live_request']
    assert 'PRIVATE_ROOM' not in json.dumps(context) and 'private.example' not in json.dumps(context) and users[1]['username'] not in json.dumps(context)
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='room-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        result=await server.call_tool('prepare_room_request',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_ROOM' not in str(result)
        access.scopes=['calendar:read']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_room_request',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/room-requests/'+KEY)
                expect(page.get_by_role('heading',name='Request the room for this meeting?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: request the room',exact=True).click()
                expect(page.get_by_role('heading',name='Room request recorded',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_two_delivery_workers_one_transport_and_disabled_legacy_guard(pilot,monkeypatch):
    conn,users,clients,app,eid,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True);calls=[]
    def send(*a,**kw):calls.append(a);return {'sent':True}
    monkeypatch.setenv(pilot_service.FLAG,'0')
    assert delivery.run(conn,send=send)==0 and rooms_notify.flush(conn,ORIGIN,send=send)=={} and not calls
    monkeypatch.setenv(pilot_service.FLAG,'1')
    def worker(_):
        c=app.get_conn()
        try:return delivery.run(c,send=send)
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:result=list(executor.map(worker,range(2)))
    assert sum(result)==1 and len(calls)==1


def test_zero_recipients_and_participant_authority(pilot):
    conn,users,clients,app,eid,token=pilot
    conn.execute("UPDATE resource_person SET archived_at='2030-03-04' WHERE id=?",(users[1]['rp_id'],));conn.commit()
    prepare(pilot);result=confirm(pilot)
    assert result['next_actor']['initial_notice_recipient_count']==0 and result['notification_status_counts']=={}
    # A participant may prepare a new self-owned request for another meeting;
    # mere broad calendar visibility or technical admin authority is insufficient.
    second=st.cal_create(conn,'Synthetic participant meeting',DAY,audience='people',people=[users[0]['id']],by=users[2]['username'])
    prepare(pilot,'participant-room-request-001',fields(pilot,entry_id=second,expected_revision=room_actions.revision(st.cal_get(conn,second))))
    other=mcp_auth.Provider._tokens(conn,'room-test',users[4]['id'],[pilot_service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):pilot_service.read_context(conn,other.access_token,RESOURCE,ORIGIN,second)


def test_deleted_room_identity_never_rebinds_to_reused_id(pilot):
    conn,users,clients,app,eid,token=pilot;prepare(pilot);result=confirm(pilot)
    rid=int(result['room_request_id'])
    # Same controlled deletion order as an administrative purge; child markers
    # cascade and the operation tombstone remains, so recovery cannot recreate.
    conn.execute('DELETE FROM room_notice WHERE reservation_id=?',(rid,))
    conn.execute('DELETE FROM room_reservation_slot WHERE reservation_id=?',(rid,))
    conn.execute('DELETE FROM room_reservation WHERE id=?',(rid,));conn.commit()
    assert not conn.execute('SELECT * FROM mcp_room_identity').fetchall()
    with pytest.raises(permissions.Denied):pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert conn.execute('SELECT completed_at FROM mcp_room_request').fetchone()[0]
