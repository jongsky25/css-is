"""M4.3 single plain booking decision, exact requester notice, no override or resend."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime
import json
import time

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents_permissions as permissions
from documents_storage import transaction
import mcp_actions
import mcp_auth
import mcp_read
import mcp_room_approvals as service
import room_approval as approval
import room_approval_delivery as delivery
import rooms
import rooms_notify
import room_actions
import storage as st
import telegram_preferences as preferences
import tzutil as tz
import mailer
from tests.conftest import join_admin_section
from tests.test_mcp_room_requests import pilot as request_pilot,prepare as request_prepare,confirm as request_confirm,form,ORIGIN,RESOURCE,TITLE,DAY
from tests.test_integration_read_api import api
from tests.test_work import workspace

KEY='room-approval-operation-001'
REASON='APPROVAL_REASON <script>untrusted</script>'


@pytest.fixture
def pilot(request_pilot,monkeypatch):
    conn,users,clients,app,eid,old_token=request_pilot
    request_prepare(request_pilot);saved=request_confirm(request_pilot)
    monkeypatch.setenv(service.FLAG,'1');monkeypatch.delenv('CSS_MCP_ROOM_REQUESTS_ENABLED',raising=False)
    st.set_email_option(conn,'room_ics',True)
    token=mcp_auth.Provider._tokens(conn,'room-test',users[1]['id'],[service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,eid,int(saved['room_request_id']),token


def fields(pilot,**changes):
    _,_,info=approval.source(pilot[0],pilot[1][1],pilot[5])
    return {'room_request_id':pilot[5],'expected_revision':info['expected_revision'],'reason':REASON,**changes}


def prepare(pilot,key=KEY,data=None):
    return service.prepare(pilot[0],pilot[6].access_token,RESOURCE,ORIGIN,key,data or fields(pilot))


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][1].cookies.get(auth.COOKIE_NAME))
    p=service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=p['preview_digest'])


def record(pilot):return rooms.get_reservation(pilot[0],pilot[5])


def test_exact_booking_atomic_notice_calendar_unchanged_and_recovery(pilot,monkeypatch):
    conn,users,clients,app,eid,rid,token=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**k:pytest.fail('Confirmation queues, never sends'))
    current=service.read_context(conn,token.access_token,RESOURCE,ORIGIN,rid)
    assert current['day']==DAY and current['slot_count']==1 and current['competing_request_count']==0
    assert 'PRIVATE_ROOM' not in json.dumps(current) and users[0]['username'] not in json.dumps(current)
    original=fields(pilot);p=prepare(pilot,data=original)
    assert prepare(pilot,data=original)==p and record(pilot)['status']=='requested'
    path='/account/integrations/mcp/room-approvals/'+KEY;page=clients[1].get(path)
    assert page.status_code==200 and all(t in page.text for t in ('PRIVATE_ROOM','APPROVAL_REASON','09:00','10:00',users[0]['username'],'ICS attachment'))
    assert '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert 'PRIVATE_CALENDAR_NOTE' not in page.text and 'private.example' not in page.text
    entry=st.cal_get(conn,eid)
    assert clients[1].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    result=service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert result['approval_status']=='approved' and result['booking_held_at_approval'] is True and result['slot_count']==1
    assert result['notification_status_counts']=={'queued':1}
    assert result['next_actor']=={'role':'requester_use_approved_room','initial_notice_recipient_count':1}
    assert 'PRIVATE_ROOM' not in json.dumps(result) and 'APPROVAL_REASON' not in json.dumps(result) and users[0]['username'] not in json.dumps(result)
    assert record(pilot)['decide_note']==REASON and record(pilot)['decided_by']==users[1]['username']
    assert conn.execute('SELECT SUM(is_approved) FROM room_reservation_slot WHERE reservation_id=?',(rid,)).fetchone()[0]==1
    assert st.cal_get(conn,eid)==entry
    assert conn.execute("SELECT user_id,bell FROM room_notice WHERE reservation_id=? AND kind='approved'",(rid,)).fetchone()==(users[0]['id'],1)
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_room_approval').fetchone()==(None,None)
    assert clients[0].get('/rooms/mine').status_code==200
    assert prepare(pilot,data=original)==result
    rooms.withdraw(conn,rid,users[0]['id'],reason='Ordinary changed plan',actor=users[0]['username'])
    assert prepare(pilot,data=original)==result and record(pilot)['status']=='withdrawn'
    assert clients[1].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert record(pilot)['status']=='withdrawn'
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='room_approve'").fetchone()[0]==1


@pytest.mark.parametrize('change',['request','owner','authority','slot','closed','booked','meeting','meeting_access','meal','standby','series','move','event','day_started','email','preference','ics','recipient','scope','revoked','expired','payload','snapshot','switch','global_switch'])
def test_current_request_authority_conflicts_and_notice_policy_rechecked(pilot,monkeypatch,change):
    conn,users,clients,app,eid,rid,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/room-approvals/'+KEY;page=clients[1].get(path)
    if change=='request':conn.execute("UPDATE room_reservation SET purpose='Unreviewed purpose' WHERE id=?",(rid,))
    elif change=='owner':conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],))
    elif change=='authority':conn.execute('UPDATE resource_person SET is_internal=0 WHERE id=?',(users[1]['rp_id'],))
    elif change=='slot':conn.execute("UPDATE room_slot SET label='Changed hour' WHERE start_time='09:00'")
    elif change=='closed':st.set_holiday(conn,DAY,'Closed','regular')
    elif change=='booked':
        rival=rooms.request(conn,title='PRIVATE_RIVAL',day=DAY,slot_ids=record(pilot)['slot_ids'],requester_user_id=users[2]['id'],actor=users[2]['username'])
        rooms.approve(conn,rival['id'],users[1]['username'])
    elif change=='meeting':conn.execute("UPDATE calendar_entry SET note='Changed private note' WHERE id=?",(eid,))
    elif change=='meeting_access':conn.execute('DELETE FROM calendar_entry_person WHERE entry_id=?',(eid,));conn.execute('UPDATE calendar_entry SET created_by=? WHERE id=?',(users[2]['username'],eid))
    elif change=='meal':conn.execute('UPDATE room_reservation SET meals_requested=1 WHERE id=?',(rid,))
    elif change=='standby':conn.execute('UPDATE room_reservation SET standby=1 WHERE id=?',(rid,))
    elif change=='series':conn.execute('UPDATE room_reservation SET series_id=1 WHERE id=?',(rid,))
    elif change=='move':conn.execute("UPDATE room_reservation SET source='move',moves_reservation_id=? WHERE id=?",(rid,rid))
    elif change=='event':conn.execute('UPDATE room_reservation SET event_id=1 WHERE id=?',(rid,))
    elif change=='day_started':monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,7));monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,7,9))
    elif change=='email':st.set_email_feature(conn,'room_decided',False)
    elif change=='preference':conn.execute('INSERT INTO telegram_notification_preference(user_id,room_email) VALUES (?,0)',(users[0]['id'],))
    elif change=='ics':st.set_email_option(conn,'room_ics',False)
    elif change=='recipient':conn.execute("UPDATE resource_person SET name='Changed requester name' WHERE id=?",(users[0]['rp_id'],))
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"rooms:request\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_room_approval SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_room_approval SET payload_json=?',(json.dumps({**original,'reason':'Tampered'}),))
    elif change=='snapshot':conn.execute('UPDATE mcp_room_approval SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    else:monkeypatch.setenv(service.FLAG,'0')
    conn.commit()
    assert clients[1].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert record(pilot)['status']=='requested'
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_approval_identity').fetchone()[0]==0
    assert conn.execute("SELECT COUNT(*) FROM room_notice WHERE reservation_id=? AND kind='approved'",(rid,)).fetchone()[0]==0


@pytest.mark.parametrize('changes',[{'room_request_id':True},{'room_request_id':'1'},{'room_request_id':0},
    {'expected_revision':'guess'},{'reason':''},{'reason':'x'*2001},{'reason':'bad\x00text'},
    {'decline_rivals':True},{'standby':True},{'slot_ids':[1]},{'calendar_status':'confirmed'},{'send_email':False}])
def test_strict_single_approval_only(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changes))


def test_membership_self_and_filing_actor_not_technical_admin(pilot):
    conn,users,clients,app,eid,rid,token=pilot
    for idx in (0,2,4):
        granted=mcp_auth.Provider._tokens(conn,'room-test',users[idx]['id'],[service.SCOPE],RESOURCE);conn.commit()
        with pytest.raises(permissions.Denied):service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,rid)
    join_admin_section(conn,users[0]['id'])
    with pytest.raises(permissions.Denied):approval.source(conn,users[0],rid)
    conn.execute('UPDATE room_reservation SET created_by=? WHERE id=?',(users[1]['username'],rid));conn.commit()
    with pytest.raises(permissions.Denied):approval.source(conn,users[1],rid)


@pytest.mark.parametrize('failure',['audit','notice'])
def test_final_failure_rolls_back_booking_notice_and_receipt(pilot,monkeypatch,failure):
    conn,users,clients,app,eid,rid,token=pilot;prepare(pilot)
    if failure=='audit':
        original=st.audit
        def fail(c,actor,action,**kw):
            if action=='integration_action_complete':raise RuntimeError('Synthetic final audit failure')
            return original(c,actor,action,**kw)
        monkeypatch.setattr(st,'audit',fail)
    else:monkeypatch.setattr(rooms_notify,'on_decided',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Synthetic notice failure')))
    with pytest.raises(RuntimeError):confirm(pilot)
    assert record(pilot)['status']=='requested'
    assert conn.execute('SELECT SUM(is_approved) FROM room_reservation_slot WHERE reservation_id=?',(rid,)).fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_approval_identity').fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_room_approval').fetchone()[0] is None
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='room_approve'").fetchone()[0]==0
    with pytest.raises(RuntimeError,match='caller-owned'):rooms.approve_in_transaction(conn,rid,users[1]['username'])


def test_races_and_pending_rivals_never_declined(pilot):
    conn,users,clients,app,eid,rid,token=pilot
    rival=rooms.request(conn,title='PRIVATE_RIVAL_DO_NOT_COPY',day=DAY,slot_ids=record(pilot)['slot_ids'],requester_user_id=users[2]['id'],actor=users[2]['username'],quiet=True)
    original=fields(pilot);keys=(KEY,'competing-room-approval-001')
    for k in keys:prepare(pilot,k,original)
    page=clients[1].get('/account/integrations/mcp/room-approvals/'+KEY)
    assert 'PRIVATE_RIVAL_DO_NOT_COPY' not in page.text and service.read_context(conn,token.access_token,RESOURCE,ORIGIN,rid)['competing_request_count']==1
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME))
    digests={k:service.browser(conn,payload,RESOURCE,ORIGIN,k)['preview_digest'] for k in keys}
    def worker(k):
        c=app.get_conn()
        try:return service.browser(c,payload,RESOURCE,ORIGIN,k,confirm_digest=digests[k])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,keys))
    assert sorted(results)==['completed','conflict'];winner=keys[results.index('completed')]
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(worker,(winner,winner)))==['completed','completed']
    assert rooms.get_reservation(conn,rival['id'])['status']=='requested'
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_approval_notice').fetchone()[0]==1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='room_approve'").fetchone()[0]==1


@pytest.mark.parametrize('outcome',['sent','false','error','crash','result_write'])
def test_single_attempt_email_with_ics_and_legacy_sender_exclusion(pilot,monkeypatch,outcome):
    conn,users,clients,app,eid,rid,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    sent=[]
    def transport(*a,**kw):
        assert not conn.in_transaction;sent.append((a,kw))
        if outcome=='error':raise RuntimeError('Synthetic transport error')
        if outcome=='crash':raise KeyboardInterrupt('Synthetic process death')
        return {'sent':outcome!='false'}
    original_finish=delivery._finish
    if outcome=='result_write':
        def failed_finish(*a,**kw):
            if kw.get('attempt'):raise RuntimeError('Synthetic outcome write failure')
            return original_finish(*a,**kw)
        monkeypatch.setattr(delivery,'_finish',failed_finish)
    if outcome in ('crash','result_write'):
        with pytest.raises((KeyboardInterrupt,RuntimeError)):delivery.run(conn,send=transport)
        monkeypatch.setattr(delivery,'_finish',original_finish)
        conn.execute("UPDATE mcp_room_approval_notice SET attempted_at=1 WHERE state='attempting'");conn.commit()
    else:assert delivery.run(conn,send=transport)==1
    assert len(sent)==1 and sent[0][0][0]==users[0]['username'] and sent[0][1]['attachments']
    assert delivery.run(conn,send=transport)==0 and len(sent)==1
    state=conn.execute('SELECT state FROM mcp_room_approval_notice').fetchone()[0]
    assert state==('sent' if outcome=='sent' else 'uncertain')
    # Force eligibility in the old loop: exclusion must hold even if its email
    # status is reset or a retry operator bypasses the ordinary cooldown.
    conn.execute("UPDATE room_notice SET email_status=NULL WHERE reservation_id=? AND kind='approved'",(rid,));conn.commit()
    assert rooms_notify.flush(conn,ORIGIN,send=lambda *a,**k:pytest.fail('Legacy mail must exclude both MCP notice kinds'))=={}


@pytest.mark.parametrize('change,state',[('off','skipped_off'),('preference','skipped_off'),('no_mail','not_configured'),('name','cancelled'),('withdrawn','cancelled'),('authority','cancelled'),('ics','cancelled'),('meeting','cancelled')])
def test_delivery_current_source_policy_and_recipient_gates(pilot,monkeypatch,change,state):
    conn,users,clients,app,eid,rid,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    if change=='off':st.set_email_feature(conn,'room_decided',False)
    elif change=='preference':conn.execute('INSERT INTO telegram_notification_preference(user_id,room_email) VALUES (?,0)',(users[0]['id'],))
    elif change=='no_mail':monkeypatch.setattr(mailer,'email_configured',lambda:False)
    elif change=='name':conn.execute("UPDATE resource_person SET name='Changed name' WHERE id=?",(users[0]['rp_id'],))
    elif change=='withdrawn':rooms.withdraw(conn,rid,users[0]['id'],actor=users[0]['username'])
    elif change=='authority':conn.execute('UPDATE resource_person SET is_internal=0 WHERE id=?',(users[1]['rp_id'],))
    elif change=='ics':st.set_email_option(conn,'room_ics',False)
    elif change=='meeting':conn.execute("UPDATE calendar_entry SET note='Changed note' WHERE id=?",(eid,))
    conn.commit()
    assert delivery.run(conn,send=lambda *a,**k:pytest.fail('This notice must not send'))==0
    assert conn.execute('SELECT state FROM mcp_room_approval_notice').fetchone()[0]==state


def test_disabled_at_confirmation_stays_skipped_and_quiet_hours_wait(pilot,monkeypatch):
    conn,users,clients,app,eid,rid,token=pilot
    st.set_email_feature(conn,'room_decided',False);prepare(pilot);confirm(pilot)
    st.set_email_feature(conn,'room_decided',True);monkeypatch.setattr(mailer,'email_configured',lambda:True)
    assert delivery.run(conn,send=lambda *a,**k:pytest.fail('No later enabling resend'))==0
    assert conn.execute('SELECT state FROM mcp_room_approval_notice').fetchone()[0]=='skipped_off'


def test_quiet_hours_wait_then_one_worker_claim(pilot,monkeypatch):
    conn,users,clients,app,eid,rid,token=pilot
    conn.execute('INSERT INTO telegram_notification_preference(user_id,quiet_start,quiet_end) VALUES (?,?,?)',(users[0]['id'],'08:00','10:00'));conn.commit()
    prepare(pilot);confirm(pilot);monkeypatch.setattr(mailer,'email_configured',lambda:True)
    assert delivery.run(conn,send=lambda *a,**k:pytest.fail('Quiet hours hold email'))==0
    monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,4,11))
    calls=[]
    def worker(_):
        c=app.get_conn()
        try:return delivery.run(c,send=lambda *a,**kw:calls.append(a) or {'sent':True})
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(worker,(1,2)))==1
    assert len(calls)==1


def test_csrf_connection_source_identity_and_cleanup(pilot,monkeypatch):
    conn,users,clients,app,eid,rid,token=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/room-approvals/'+KEY;page=clients[1].get(path)
    assert clients[0].get(path).status_code==404
    for values,origin in (({**form(page),'csrf':'bad'},ORIGIN),(form(page),'https://evil.example')):
        assert clients[1].post(path,data=values,headers={'Origin':origin}).status_code==403
    fresh=mcp_auth.Provider._tokens(conn,'room-test',users[1]['id'],[service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    with pytest.raises(mcp_actions.ActionError,match='different'):prepare(pilot,data={**original,'reason':'Other'})
    confirm(pilot)
    original_reference=record(pilot)['ref_code']
    conn.execute("UPDATE room_reservation SET ref_code='REUSED' WHERE id=?",(rid,));conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    conn.execute('UPDATE room_reservation SET ref_code=? WHERE id=?',(original_reference,rid));conn.commit()
    monkeypatch.setenv(service.FLAG,'0');conn.execute("UPDATE mcp_room_approval_notice SET created_at=1 WHERE state='queued'");conn.commit()
    assert delivery.run(conn,send=lambda *a,**k:pytest.fail('Disabled'))==0
    assert conn.execute('SELECT state FROM mcp_room_approval_notice').fetchone()[0]=='cancelled'


def test_sdk_and_mobile_no_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,eid,rid,token=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='room-test',scopes=[service.SCOPE],resource=RESOURCE,subject=str(users[1]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        result=await server.call_tool('prepare_room_request_approval',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_ROOM' not in str(result)
        access.scopes=['rooms:request']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_room_request_approval',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[1],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/room-approvals/'+KEY)
                expect(page.get_by_role('heading',name='Approve this exact room request?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: approve and book requested hours',exact=True).click()
                expect(page.get_by_role('heading',name='Room request approved',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_preview_capacity_cleanup_and_current_session(pilot,monkeypatch):
    conn,users,clients,app,eid,rid,token=pilot
    for i in range(50):prepare(pilot,'room-approval-capacity-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'room-approval-capacity-overflow')
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):service.browser(conn,payload,RESOURCE,ORIGIN,'room-approval-capacity-0')
    conn.execute('UPDATE mcp_room_approval SET expires_at=1');conn.commit();monkeypatch.setenv(service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError):service.recover(conn,token.access_token,RESOURCE,ORIGIN,'room-approval-capacity-0')
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_approval WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_approval').fetchone()[0]==50


def test_standalone_and_same_day_unstarted_request_can_be_approved(pilot,monkeypatch):
    conn,users,clients,app,eid,rid,token=pilot
    monkeypatch.setattr(tz,'now_local',lambda:datetime(2030,3,4,8))
    res=rooms.request(conn,title='Standalone internal request',day='2030-03-04',slot_ids=record(pilot)['slot_ids'],
                      requester_user_id=users[2]['id'],actor=users[2]['username'],quiet=True)
    _,_,info=approval.source(conn,users[1],res['id'])
    service.prepare(conn,token.access_token,RESOURCE,ORIGIN,KEY,
        {'room_request_id':res['id'],'expected_revision':info['expected_revision'],'reason':REASON})
    result=confirm(pilot)
    assert result['approval_status']=='approved' and rooms.get_reservation(conn,res['id'])['status']=='approved'
    assert record(pilot)['status']=='requested'


def test_two_different_pending_requests_cannot_both_hold_same_hour(pilot):
    conn,users,clients,app,eid,rid,token=pilot
    rival=rooms.request(conn,title='Second competing request',day=DAY,slot_ids=record(pilot)['slot_ids'],requester_user_id=users[2]['id'],actor=users[2]['username'],quiet=True)
    targets=((KEY,rid),('other-room-decision-key',rival['id']))
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME));digests={}
    for key,target in targets:
        _,_,info=approval.source(conn,users[1],target)
        service.prepare(conn,token.access_token,RESOURCE,ORIGIN,key,
            {'room_request_id':target,'expected_revision':info['expected_revision'],'reason':REASON})
        digests[key]=service.browser(conn,payload,RESOURCE,ORIGIN,key)['preview_digest']
    def worker(pair):
        key,_=pair;c=app.get_conn()
        try:return service.browser(c,payload,RESOURCE,ORIGIN,key,confirm_digest=digests[key])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(worker,targets))==['completed','conflict']
    assert sorted(rooms.get_reservation(conn,target)['status'] for _,target in targets)==['approved','requested']
    assert conn.execute('SELECT COUNT(*) FROM room_reservation_slot WHERE is_approved=1').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM mcp_room_approval_notice').fetchone()[0]==1
