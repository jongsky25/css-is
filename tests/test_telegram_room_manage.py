"""Own-room actions: approval preservation, exact previews and full rollback."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import re

import pytest

import backups
from documents_storage import rows, transaction
import rooms
import rooms_notify
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_room_manage as manage
from tests.test_work import workspace
from tests.test_telegram_bot import setup, submit, update, NOW
from tests.test_telegram_links import linking, claimed, start
from tests.test_telegram_menu import menu_env, command
from tests.test_telegram_brief import grant


@pytest.fixture(params=[('withdraw','requested'),('withdraw','approved'),('move','requested'),('move','approved')])
def management(menu_env,monkeypatch,request):
    env=menu_env;c,users,*_=env;mode,status=request.param
    grant(env,'rooms.read',monkeypatch);grant(env,manage.MODES[mode],monkeypatch)
    record=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],
                         requester_user_id=users[0]['id'],actor=users[0]['username'],purpose='DoNotExposePurpose',today=NOW.date())
    if status=='approved':rooms.approve(c,record['id'],users[4]['username'],today=NOW.date())
    return env,mode,record['id']


def prepare(env,mode,rid,number=10,key='room-management-operation'):
    c,users,*_=env
    guide=command(env,'/room_'+mode,number)['text']
    assert manage.PATH+mode+'?origin=' in guide
    identifier=guide.split('?origin=')[1]
    ctx=meetings.origin(c,users[0],identifier,NOW,manage.MODES[mode])
    fields={'room_id':rooms.get_reservation(c,rid)['ref_code']}
    if mode=='move':fields['day']='2026-10-27'
    result=actions.issue(c,ctx,manage.MODES[mode],key,fields,NOW)
    return ctx,result


def exact(env,mode,result,number=20):
    text=command(env,'/'+mode+'_preview '+result['operation_id'],number)['text']
    assert 'Synthetic managed room' in text and 'Asia/Manila' in text and 'DoNotExpose' not in text
    assert manage.common.units(text)<=4096
    return re.search('/'+mode+r'_confirm [A-Za-z0-9_-]{43}',text)[0]


def snapshot(c):
    return {table:list(c.execute('SELECT * FROM '+table)) for table in
            ('room_reservation','room_reservation_slot','room_notice','audit_log','calendar_entry','telegram_change_head')}


def held(c,rid):return c.execute('SELECT COALESCE(sum(is_approved),0) FROM room_reservation_slot WHERE reservation_id=?',(rid,)).fetchone()[0]


def test_preview_confirm_recovery_and_approved_move_keeps_original_held(management):
    env,mode,rid=management;c,users,*_=env
    before=rooms.get_reservation(c,rid);count=c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]
    _,result=prepare(env,mode,rid);confirmation=exact(env,mode,result)
    assert rooms.get_reservation(c,rid)==before
    text=command(env,confirmation,21)['text'];assert 'Recorded outcome:' in text
    operation=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(result['operation_id'],))[0]
    changed=rooms.get_reservation(c,operation['result_room_id'])
    if mode=='withdraw':
        assert changed['status']=='withdrawn' and held(c,rid)==0
    elif before['status']=='requested':
        assert changed['id']==rid and changed['day']=='2026-10-27' and changed['status']=='requested' and held(c,rid)==0
    else:
        assert changed['id']!=rid and changed['moves_reservation_id']==rid and changed['status']=='requested'
        assert held(c,rid)==1 and held(c,changed['id'])==0
        assert rooms.get_reservation(c,rid)['status']=='approved' and 'approval remains separate' in text
        assert c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]==count+1
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,confirmation,22)['text']
    assert 'Recorded outcome:' in command(env,'/'+mode+'_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c) and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    if mode=='move' and before['status']=='approved':
        rooms.approve(c,changed['id'],users[4]['username'],today=NOW.date())
        assert held(c,rid)==0 and held(c,changed['id'])==1
        assert rooms.get_reservation(c,rid)['status']=='withdrawn'


@pytest.mark.parametrize('change',['edit','revert','slots','write_grant','read_grant','flag','expiry','disconnect','restore'])
def test_stale_or_revoked_previews_cannot_write(management,monkeypatch,change):
    env,mode,rid=management;c,users,path,_,payload=env
    _,result=prepare(env,mode,rid);confirmation=exact(env,mode,result)
    if change in ('edit','revert'):
        old=rooms.get_reservation(c,rid)
        c.execute("UPDATE room_reservation SET title='Changed title' WHERE id=?",(rid,))
        if change=='revert':c.execute('UPDATE room_reservation SET title=? WHERE id=?',(old['title'],rid))
        c.commit()
    elif change=='slots':c.execute("UPDATE room_slot SET label='Changed label' WHERE id=?",(rooms.get_reservation(c,rid)['slot_ids'][0],));c.commit()
    elif change in ('write_grant','read_grant'):
        scope=manage.MODES[mode] if change=='write_grant' else 'rooms.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_'+manage.MODES[mode].replace('.','_').upper()+'_ENABLED','0')
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21).get('text','')
    assert saved==snapshot(c)


@pytest.mark.parametrize('failure',['audit','late_receipt','handoff'])
def test_late_failures_roll_back_source_notices_and_receipt(management,monkeypatch,failure):
    env,mode,rid=management;c,users,*_=env
    _,result=prepare(env,mode,rid);confirmation=exact(env,mode,result);saved=snapshot(c)
    fail=lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic failure'))
    if failure=='audit':monkeypatch.setattr(st,'audit',fail)
    elif failure=='late_receipt':monkeypatch.setattr(actions.ADAPTERS[manage.MODES[mode]],'receipt_text',fail)
    else:c.execute("CREATE TRIGGER fail_room_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=confirmation))
    if failure=='handoff':assert response.status_code==503
    else:assert 'Recorded outcome:' not in response.json()['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


@pytest.mark.parametrize('mode,status',[('withdraw','requested'),('withdraw','approved'),('move','approved')])
def test_native_notice_hook_failure_never_commits_room_action(menu_env,monkeypatch,mode,status):
    env=menu_env;c,users,*_=env
    grant(env,'rooms.read',monkeypatch);grant(env,manage.MODES[mode],monkeypatch)
    record=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[0]['id'],today=NOW.date())
    if status=='approved':rooms.approve(c,record['id'],users[4]['username'],today=NOW.date())
    _,result=prepare(env,mode,record['id']);confirmation=exact(env,mode,result);saved=snapshot(c)
    monkeypatch.setattr(rooms_notify,'on_withdrawn' if mode=='withdraw' else 'on_requested',
                        lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic notice failure')))
    assert 'Recorded outcome:' not in command(env,confirmation,21)['text']
    assert saved==snapshot(c)


@pytest.mark.parametrize('field,value',[('meals_requested',1),('series_id',1),('standby',1),('event_id',999),('on_behalf_of','Someone else')])
def test_special_source_cases_stay_in_office_connect(management,field,value):
    env,mode,rid=management;c,*_=env
    ctx,_=prepare(env,mode,rid)
    c.execute('UPDATE room_reservation SET '+field+'=? WHERE id=?',(value,rid));c.commit()
    saved=snapshot(c)
    with pytest.raises(ValueError):actions.issue(c,ctx,manage.MODES[mode],'unsupported-room-operation',{'room_id':rid,**({'day':'2026-10-27'} if mode=='move' else {})},NOW)
    assert saved==snapshot(c)


@pytest.mark.parametrize('status',['requested','approved'])
def test_new_date_booked_after_preview_preserves_old_request(menu_env,monkeypatch,status):
    env=menu_env;c,users,*_=env
    grant(env,'rooms.read',monkeypatch);grant(env,'rooms.move',monkeypatch)
    slot=rooms.list_slots(c)[2]['id']
    record=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[slot],requester_user_id=users[0]['id'],today=NOW.date())
    if status=='approved':rooms.approve(c,record['id'],users[4]['username'],today=NOW.date())
    _,result=prepare(env,'move',record['id']);confirmation=exact(env,'move',result)
    rival=rooms.request(c,title='Other approved room',day='2026-10-27',slot_ids=[slot],requester_user_id=users[3]['id'],today=NOW.date())
    rooms.approve(c,rival['id'],users[4]['username'],today=NOW.date())
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21)['text']
    assert saved==snapshot(c) and held(c,record['id'])==int(status=='approved')


def test_approval_after_pending_move_preview_cannot_silently_change_action(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'rooms.read',monkeypatch);grant(env,'rooms.move',monkeypatch)
    record=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[0]['id'],today=NOW.date())
    _,result=prepare(env,'move',record['id']);confirmation=exact(env,'move',result)
    rooms.approve(c,record['id'],users[4]['username'],today=NOW.date())
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,confirmation,21)['text']
    assert saved==snapshot(c) and held(c,record['id'])==1


def test_concurrent_confirmations_produce_one_mutation(management):
    env,mode,rid=management;c,users,path,*_=env
    ctx,result=prepare(env,mode,rid)
    def confirm(_):
        conn=st.connect(path)
        try:return actions.confirm(conn,ctx,result['token'],NOW)
        finally:conn.close()
    before=c.execute("SELECT count(*) FROM audit_log WHERE action IN ('room_move','room_withdraw')").fetchone()[0]
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(confirm,range(2)))
    assert outcomes[0]==outcomes[1]
    assert c.execute("SELECT count(*) FROM audit_log WHERE action IN ('room_move','room_withdraw')").fetchone()[0]==before+1


def test_other_owner_and_group_direct_modes_do_not_gain_authority(management,monkeypatch):
    env,mode,rid=management;c,users,*_=env
    ctx,result=prepare(env,mode,rid);confirmation=exact(env,mode,result)
    other=rooms.request(c,title='Other private room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[3]['id']],requester_user_id=users[3]['id'],today=NOW.date())
    with pytest.raises(ValueError):actions.issue(c,ctx,manage.MODES[mode],'other-owner-operation',{'room_id':other['id'],**({'day':'2026-10-27'} if mode=='move' else {})},NOW)
    with pytest.raises(ValueError):manage.actions.ADAPTERS[manage.MODES[mode]].prepare(c,users[4],{'room_id':other['id'],**({'day':'2026-10-27'} if mode=='move' else {})})
    packet=update(21,text=confirmation);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    saved=snapshot(c);monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,confirmation,22) and saved==snapshot(c)


def test_linked_move_follows_current_meeting_and_calendar_revoke_cancels(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'rooms.read',monkeypatch);grant(env,'rooms.move',monkeypatch)
    record=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[0]['id'],today=NOW.date())
    eid=st.cal_create(c,'Linked meeting','2026-10-27',by=users[0]['username'],audience='people',people=[users[0]['id']])
    rooms.link_entry(c,record['id'],eid,users[0]);ctx,result=prepare(env,'move',record['id'])
    with pytest.raises(ValueError):actions.issue(c,ctx,'rooms.move','wrong-date-operation',{'room_id':record['id'],'day':'2026-10-28'},NOW)
    confirmation=exact(env,'move',result);source_before=st.cal_get(c,eid)
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='cancelled'
    assert 'Recorded outcome:' not in command(env,confirmation,21)['text']
    assert rooms.get_reservation(c,record['id'])['day']=='2026-10-26' and st.cal_get(c,eid)==source_before


def test_withdraw_original_also_withdraws_pending_move_and_child_alone_keeps_old_booking(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'rooms.read',monkeypatch);grant(env,'rooms.withdraw',monkeypatch)
    original=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[0]['id'],today=NOW.date())
    rooms.approve(c,original['id'],users[4]['username'],today=NOW.date())
    child=rooms.request_move(c,original['id'],'2026-10-27',users[0],today=NOW.date())
    _,result=prepare(env,'withdraw',child['id']);confirmation=exact(env,'withdraw',result)
    command(env,confirmation,21)
    assert held(c,original['id'])==1 and rooms.get_reservation(c,child['id'])['status']=='withdrawn'
    child=rooms.request_move(c,original['id'],'2026-10-27',users[0],today=NOW.date())
    _,result=prepare(env,'withdraw',original['id'],22,'withdraw-original-operation')
    text=command(env,'/withdraw_preview '+result['operation_id'],23)['text']
    assert child['ref_code'] in text and 'Also withdraw' in text
    command(env,re.search(r'/withdraw_confirm [A-Za-z0-9_-]{43}',text)[0],24)
    assert held(c,original['id'])==0 and rooms.get_reservation(c,child['id'])['status']=='withdrawn'


def test_pending_move_with_cancelled_original_does_not_claim_original_is_held(menu_env,monkeypatch):
    env=menu_env;c,users,*_=env
    grant(env,'rooms.read',monkeypatch);grant(env,'rooms.withdraw',monkeypatch)
    original=rooms.request(c,title='Synthetic managed room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[0]['id'],today=NOW.date())
    rooms.approve(c,original['id'],users[4]['username'],today=NOW.date())
    child=rooms.request_move(c,original['id'],'2026-10-27',users[0],today=NOW.date())
    with transaction(c):rooms._cancel_in_txn(c,original['id'],users[4]['username'],'Synthetic cancellation')
    _,result=prepare(env,'withdraw',child['id'])
    text=command(env,'/withdraw_preview '+result['operation_id'],20)['text']
    assert 'current status: cancelled' in text and 'hours stay held' not in text
    confirmation=re.search(r'/withdraw_confirm [A-Za-z0-9_-]{43}',text)[0]
    command(env,confirmation,21)
    assert rooms.get_reservation(c,original['id'])['status']=='cancelled' and rooms.get_reservation(c,child['id'])['status']=='withdrawn'


@pytest.mark.parametrize('mode',['withdraw','move'])
def test_explicit_management_scope_and_read_consent_are_required(linking,monkeypatch,mode):
    c,users,_,_,payload=linking;scope=manage.MODES[mode]
    ch,raw,confirmation=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[scope],NOW)
    links.claim(c,payload,raw,['rooms.read',scope],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')
