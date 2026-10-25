"""Linked room submission, domain authorization and atomic receipts; no provider I/O."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import json

import pytest

import backups
from documents_storage import rows,transaction
import rooms
import rooms_notify
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as dispatch
import telegram_room_requests as requests
import room_actions
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed
from tests.test_telegram_groups import registered,register,group_update


@pytest.fixture
def request_env(linking,monkeypatch):
    c,users,path,client,payload=linking
    for flag in ('CALENDAR_READ','ROOMS_READ','ROOMS_REQUEST'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    ch,raw,confirmation=claimed(linking,('calendar.read','rooms.read','rooms.request'))
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    submit(client,update(10,text='/room_request'))
    origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request'")[0]
    eid=st.cal_create(c,'Synthetic permitted meeting','2026-10-26',audience='bureau',by=users[0]['username'],start_time='09:00',end_time='10:00')
    return linking,origin,eid


def prepare(env,key='synthetic-room-request-key',**extra):
    linking,origin,eid=env;c,users,_,_,_=linking
    context=dispatch.origin(c,users[0],origin['id'],NOW,requests.ACTION)
    return actions.issue(c,context,requests.ACTION,key,{'entry_id':str(eid),'from_time':'09:00','to_time':'10:00',**extra},NOW)


def confirm(env,preview,number=11):
    c,_,_,client,_=env[0]
    submit(client,update(number,text='/room_confirm '+preview['token']));bot.process_updates(c,NOW)
    return rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(preview['operation_id'],))[0]


def test_private_request_is_linked_pending_self_owned_and_one_on_replay(request_env,monkeypatch):
    linking,origin,eid=request_env;c,users,path,client,_=linking
    p=prepare(request_env)
    assert 'No booking is held' in requests.ADAPTER.text(p['preview'])
    assert not rows(c,'SELECT * FROM room_reservation')
    result=confirm(request_env,p);record=rooms.get_reservation(c,result['result_room_id'])
    assert result['state']=='committed' and result['result_entry_id']==eid
    assert record['calendar_entry_id']==eid and record['requester_user_id']==users[0]['id']
    assert record['status']=='requested' and not record['standby'] and not record['meals_requested']
    assert c.execute('SELECT SUM(is_approved) FROM room_reservation_slot WHERE reservation_id=?',(record['id'],)).fetchone()[0]==0
    confirm(request_env,p,12)
    assert len(rows(c,'SELECT * FROM room_reservation'))==1 and len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert prepare(request_env)['receipt']['result_room_id']==record['id']
    with pytest.raises(ValueError):prepare(request_env,key='other-room-request-key')
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',15,None))
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=2*i))
    assert messages and all(a[1]==101 for a in messages)
    assert any(record['ref_code'] in a[2] and 'pending approval' in a[2] for a in messages)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')


@pytest.mark.parametrize('role',['viewer','encoder','section_manager','admin'])
def test_bureau_visibility_does_not_allow_linking_anothers_meeting_even_for_admin(request_env,role):
    c,users,_,_,_=request_env[0];eid=request_env[2]
    c.execute('UPDATE admin_user SET role=? WHERE id=?',(role,users[0]['id']))
    c.execute("UPDATE calendar_entry SET created_by='another' WHERE id=?",(eid,));c.commit()
    # Direct domain service isolates authority from the credential revocation caused by role change.
    with pytest.raises(ValueError):room_actions.meeting(c,users[0],eid)
    st.cal_update(c,eid,by='fixture',people=[users[0]['id']])
    assert room_actions.meeting(c,users[0],eid)[1]['id']==eid


@pytest.mark.parametrize('change',['revision','participant','private','cancel','existing_link','approved','blocked','holiday','past','horizon','slots','disconnect','restore','grant','read','calendar_read','switch','expiry'])
def test_stale_or_ineligible_confirmation_never_submits(request_env,monkeypatch,change):
    linking,origin,eid=request_env;c,users,path,client,payload=linking
    if change=='participant':
        c.execute("UPDATE calendar_entry SET created_by='another' WHERE id=?",(eid,));c.commit()
        st.cal_update(c,eid,by='fixture',people=[users[0]['id']])
    p=prepare(request_env)
    if change=='revision':st.cal_update(c,eid,by='fixture',title='Edited title')
    elif change=='participant':st.cal_update(c,eid,by='fixture',people=[])
    elif change=='private':
        c.execute("UPDATE calendar_entry SET created_by='another',audience='people' WHERE id=?",(eid,));c.commit()
    elif change=='cancel':st.cal_cancel(c,eid,by='fixture')
    elif change in ('existing_link','approved'):
        r=rooms.request(c,title='Other private room request',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[1]['id'],today=date(2026,10,20),calendar_entry_id=eid if change=='existing_link' else None)
        if change=='approved':rooms.approve(c,r['id'],'fixture',today=date(2026,10,20))
    elif change=='blocked':
        c.execute("INSERT INTO room_block(day,slot_id,reason,created_by,created_at) VALUES (?,?,?,'fixture',?)",('2026-10-26',rooms.list_slots(c)[2]['id'],'Synthetic private reason',links.stamp(NOW)));c.commit()
    elif change=='holiday':st.set_holiday(c,'2026-10-26','Synthetic holiday')
    elif change=='past':monkeypatch.setattr(room_actions.tz,'today_local',lambda:date(2026,10,27))
    elif change=='horizon':monkeypatch.setattr(room_actions.tz,'today_local',lambda:date(2026,1,1))
    elif change=='slots':
        c.execute("UPDATE room_slot SET label='Edited hour' WHERE id=?",(rooms.list_slots(c)[2]['id'],));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change in ('grant','read','calendar_read'):
        scope={'grant':'rooms.request','read':'rooms.read','calendar_read':'calendar.read'}[change]
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
    elif change=='switch':monkeypatch.setenv('CSS_TELEGRAM_ROOMS_REQUEST_ENABLED','0')
    else:monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(seconds=301))
    before=c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]
    submit(client,update(11,text='/room_confirm '+p['token']));bot.process_updates(c,NOW+timedelta(seconds=301) if change=='expiry' else NOW)
    assert c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]==before


def test_pending_conflict_does_not_hold_or_auto_approve(request_env):
    c,users,_,_,_=request_env[0]
    other=rooms.request(c,title='Another pending request',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[1]['id'],today=date(2026,10,20))
    p=prepare(request_env);op=confirm(request_env,p)
    assert op['state']=='committed' and rooms.get_reservation(c,other['id'])['status']=='requested'
    assert rooms.get_reservation(c,op['result_room_id'])['status']=='requested'


def test_atomic_rollback_includes_room_link_audit_notices_and_receipt(request_env,monkeypatch):
    c,users,_,_,_=request_env[0];p=prepare(request_env)
    monkeypatch.setattr(rooms_notify,'approver_accounts',lambda conn:[{'id':users[4]['id']}])
    before=c.execute('SELECT count(*) FROM audit_log').fetchone()[0]
    original=requests.ADAPTER.queue_receipt
    monkeypatch.setattr(requests.ADAPTER,'queue_receipt',lambda *a:(_ for _ in ()).throw(ValueError('Synthetic receipt enqueue failure')))
    confirm(request_env,p)
    for table in ('room_reservation','room_reservation_slot','room_notice'):
        assert not rows(c,'SELECT * FROM '+table)
    assert c.execute('SELECT count(*) FROM audit_log').fetchone()[0]==before
    assert rows(c,'SELECT * FROM telegram_preview')[0]['state']=='pending'
    monkeypatch.setattr(requests.ADAPTER,'queue_receipt',original)
    op=confirm(request_env,p,12)
    assert op['state']=='committed' and rows(c,'SELECT * FROM room_notice')


def test_two_workers_create_one_request_and_receipt(request_env):
    c,_,path,client,_=request_env[0];p=prepare(request_env)
    for number in (11,12):submit(client,update(number,text='/room_confirm '+p['token']))
    def run():
        conn=st.connect(path)
        try:bot.process_updates(conn,NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:run(),range(2)))
    assert len(rows(c,'SELECT * FROM room_reservation'))==1
    assert len(rows(c,"SELECT * FROM telegram_delivery WHERE dedupe_key LIKE 'room_receipt:%'"))==1


def test_recovery_after_approval_and_token_purge_shows_current_truth(request_env,monkeypatch):
    c,_,_,client,_=request_env[0];p=prepare(request_env);op=confirm(request_env,p)
    rooms.approve(c,op['result_room_id'],'fixture',today=date(2026,10,20))
    bot.cleanup(c,NOW+timedelta(days=2))
    submit(client,update(12,text='/room_receipt '+p['operation_id']));bot.process_updates(c,NOW)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',1,None))
    bot.deliver(c,NOW+timedelta(seconds=2))
    assert messages and 'approved (booked)' in messages[-1][2]
    assert len(rows(c,'SELECT * FROM room_reservation'))==1


@pytest.mark.parametrize('change',['none','paused','left','wrong_topic'])
def test_group_request_context_is_fenced_and_all_details_stay_private(registered,monkeypatch,change):
    import telegram_groups as groups
    c,users,path,client,payload=registered
    for flag in ('CALENDAR_READ','ROOMS_READ','ROOMS_REQUEST'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id'])
    for scope in ('calendar.read','rooms.read','rooms.request'):
        c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],connection['account_id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit();group=register(registered,topic=7)
    eid=st.cal_create(c,'Synthetic group-authorized meeting','2026-10-26',audience='people',people=[users[4]['id']],by=users[4]['username'])
    submit(client,group_update(10,topic=8 if change=='wrong_topic' else 7,text='/room_request'))
    origins=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request'")
    if change=='wrong_topic':assert not origins;return
    ctx=dispatch.origin(c,users[4],origins[0]['id'],NOW,requests.ACTION)
    p=actions.issue(c,ctx,requests.ACTION,'group-room-operation-key',{'entry_id':eid,'from_time':'09:00','to_time':'10:00'},NOW)
    if change=='paused':groups.manage(c,payload,group['id'],group['generation'],'pause')
    elif change=='left':monkeypatch.setattr(bot.transport,'member_status',lambda *a:'left')
    submit(client,update(11,text='/room_confirm '+p['token']));bot.process_updates(c,NOW)
    assert len(rows(c,'SELECT * FROM room_reservation'))==(1 if change=='none' else 0)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',12,None))
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=i*2))
    assert all(v[1]==101 for v in messages)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')


def test_action_tokens_and_origins_cannot_cross_meeting_and_room_commands(request_env):
    c,users,_,client,_=request_env[0];p=prepare(request_env)
    submit(client,update(11,text='/meeting_confirm '+p['token']));bot.process_updates(c,NOW)
    assert not rows(c,'SELECT * FROM room_reservation')
    with pytest.raises(ValueError):dispatch.origin(c,users[0],request_env[1]['id'],NOW,'calendar.create')
    assert bot.normalize(group_update(text='/room_confirm '+p['token']))['command'] is None


def test_source_hard_delete_detaches_receipt_without_recreating_request(request_env,monkeypatch):
    c,_,_,client,_=request_env[0];p=prepare(request_env);op=confirm(request_env,p)
    st.cal_delete(c,request_env[2],by='fixture')
    submit(client,update(12,text='/room_receipt '+p['operation_id']));bot.process_updates(c,NOW)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',12,None))
    for i in range(2):bot.deliver(c,NOW+timedelta(seconds=2+i*2))
    assert messages and 'deleted' in messages[-1][2] and '/calendar/entries/' not in messages[-1][2]
    assert len(rows(c,'SELECT * FROM room_reservation'))==1


def test_lazy_slot_seed_and_notifications_do_not_commit_caller_work(request_env,monkeypatch):
    c,users,_,_,_=request_env[0]
    c.execute('DELETE FROM room_slot');c.execute('DELETE FROM app_setting WHERE key=?',(rooms._SEED_KEY,));c.commit()
    with pytest.raises(RuntimeError):
        with transaction(c):
            slots=rooms.list_slots(c)
            rooms.request(c,title='Synthetic rollback request',day='2026-10-26',slot_ids=[slots[0]['id']],requester_user_id=users[0]['id'],today=date(2026,10,20),commit=False)
            raise RuntimeError('Synthetic caller rollback')
    assert not rows(c,'SELECT * FROM room_reservation') and not rows(c,'SELECT * FROM room_slot')
    assert st.get_setting(c,rooms._SEED_KEY) is None


def test_calendar_read_revocation_immediately_scrubs_room_preview(request_env):
    c,_,_,_,_=request_env[0];p=prepare(request_env)
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    preview=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(p['operation_id'],))[0]
    assert preview['state']=='cancelled' and preview['fields_json'] is None and preview['summary_json'] is None
    assert rows(c,'SELECT state FROM telegram_operation WHERE operation_id=?',(p['operation_id'],))[0]['state']=='cancelled'


@pytest.mark.parametrize('fields',[{'from_time':'10:00','to_time':'09:00'},{'from_time':'09:30'},{'to_time':'25:00'},{'entry_id':True},{'entry_id':'999999'}])
def test_invalid_target_or_slot_fields_never_prepare_or_mutate(request_env,fields):
    with pytest.raises(ValueError):prepare(request_env,**fields)
    assert not rows(request_env[0][0],'SELECT * FROM room_reservation')
    assert not rows(request_env[0][0],'SELECT * FROM telegram_preview')


def test_inactive_hour_cannot_be_silently_skipped_in_one_block(request_env):
    c,_,_,_,_=request_env[0]
    slots=rooms.list_slots(c)
    c.execute('UPDATE room_slot SET active=0 WHERE start_time=?',('10:00',));c.commit()
    with pytest.raises(ValueError):prepare(request_env,from_time='09:00',to_time='12:00')
    assert not rows(c,'SELECT * FROM room_reservation')


def test_pending_action_recovery_is_distinct_from_a_submitted_room_request(request_env,monkeypatch):
    c,_,_,client,_=request_env[0];p=prepare(request_env)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    submit(client,update(11,text='/room_receipt '+p['operation_id']));bot.process_updates(c,NOW)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',1,None))
    bot.deliver(c,NOW)
    assert messages and 'Action '+p['operation_id']+' status: pending' in messages[-1][2]
    assert not rows(c,'SELECT * FROM room_reservation')
