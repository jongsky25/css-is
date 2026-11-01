"""Creator-bound management, stale-source fences and atomic calendar/receipt writes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import re

import pytest

import backups
from documents_storage import rows
import rooms
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meeting_manage as manage
import telegram_meetings as meetings
from tests.test_work import workspace
from tests.test_telegram_bot import setup, submit, update, NOW
from tests.test_telegram_links import linking, claimed
from tests.test_telegram_links import start
from documents_storage import transaction
from tests.test_telegram_menu import menu_env, command
from tests.test_telegram_brief import grant


@pytest.fixture(params=['reschedule','cancel'])
def management(menu_env,monkeypatch,request):
    env=menu_env;c,users,*_=env;mode=request.param
    grant(env,manage.MODES[mode],monkeypatch)
    eid=st.cal_create(c,'Synthetic managed meeting','2026-10-26',start_time='09:00',end_time='10:00',
                      by=users[0]['username'],audience='people',people=[users[0]['id'],users[3]['id']],note='KeepThisNote')
    return env,mode,eid


def prepare(management,number=10,key='management-operation-key'):
    env,mode,eid=management;c,users,*_=env
    guide=command(env,'/meeting_'+mode,number)
    assert manage.PATH+mode+'?origin=' in guide['text']
    origin=guide['text'].split('?origin=')[1]
    ctx=meetings.origin(c,users[0],origin,NOW,manage.MODES[mode])
    fields={'entry_id':eid}
    if mode=='reschedule':fields.update(day='2026-10-27',start_time='11:00',end_time='12:30')
    result=actions.issue(c,ctx,manage.MODES[mode],key,fields,NOW)
    return ctx,result


def confirmation(management,result,number=20):
    env,mode,_=management
    preview=command(env,'/'+mode+'_preview '+result['operation_id'],number)['text']
    assert 'Synthetic managed meeting' in preview and '2026-10-26' in preview and 'Asia/Manila' in preview
    assert manage.common.units(preview)<=4096
    return re.search('/'+mode+'_confirm [A-Za-z0-9_-]{43}',preview)[0]


def snapshot(c):
    return {table:list(c.execute('SELECT * FROM '+table)) for table in
            ('calendar_entry','calendar_entry_revision','calendar_outbox','calendar_entry_person','audit_log')}


def test_private_preview_confirm_duplicate_and_current_state_recovery(management):
    env,mode,eid=management;c,*_=env
    before=st.cal_get(c,eid);ctx,result=prepare(management)
    assert st.cal_get(c,eid)==before
    exact=confirmation(management,result)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    assert exact.split()[1] not in '\n'.join(c.iterdump())
    receipt=command(env,exact,21)['text']
    assert 'Recorded outcome: meeting '+('rescheduled' if mode=='reschedule' else 'cancelled') in receipt
    current=st.cal_get(c,eid)
    assert current['note']==before['note']
    assert [(p['user_id'],p['role']) for p in current['people']]==[(p['user_id'],p['role']) for p in before['people']]
    assert current['people'][0]['seen_seq']==current['sequence']
    if mode=='reschedule':assert (current['start_date'],current['start_time'],current['end_time'])==('2026-10-27','11:00','12:30')
    else:
        assert current['status']=='cancelled'
        assert rows(c,'SELECT action FROM calendar_entry_revision WHERE entry_id=? ORDER BY id DESC LIMIT 1',(eid,))[0]['action']=='cancel'
    saved=snapshot(c)
    assert 'Recorded outcome:' in command(env,exact,22)['text']
    assert 'Recorded outcome:' in command(env,'/'+mode+'_receipt '+result['operation_id'],23)['text']
    assert saved==snapshot(c)
    assert len(rows(c,"SELECT * FROM telegram_operation WHERE state='committed'"))==1
    assert bot.deliver(c,NOW)==0


@pytest.mark.parametrize('change',['edit','new_room','expiry','write_grant','read_grant','flag','disconnect','restore'])
def test_changed_source_or_authority_cannot_consume_preview(management,monkeypatch,change):
    env,mode,eid=management;c,users,path,_,payload=env
    _,result=prepare(management);exact=confirmation(management,result)
    if change=='edit':st.cal_update(c,eid,by=users[0]['username'],venue='Changed venue')
    elif change=='new_room':
        room=rooms.request(c,title='Synthetic linked room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],
                           requester_user_id=users[0]['id'],today=NOW.date())
        rooms.link_entry(c,room['id'],eid,users[0])
    elif change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change in ('write_grant','read_grant'):
        scope=manage.MODES[mode] if change=='write_grant' else 'calendar.read'
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
        p=rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]
        assert p['state']=='cancelled' and p['fields_json'] is None
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_'+manage.MODES[mode].replace('.','_').upper()+'_ENABLED','0')
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:backups.clear_restored_sessions(path)
    saved=snapshot(c)
    packet=command(env,exact,21)
    assert 'Recorded outcome:' not in packet.get('text','')
    assert saved==snapshot(c)
    assert not rows(c,"SELECT * FROM telegram_operation WHERE state='committed'")


@pytest.mark.parametrize('kind',['other','recurring','multi_day','import','video','linked_room','activity'])
def test_unsupported_or_other_creators_meetings_are_not_prepared(management,kind):
    env,mode,eid=management;c,users,*_=env
    ctx,_=prepare(management)
    if kind=='other':c.execute('UPDATE calendar_entry SET created_by=? WHERE id=?',(users[3]['username'],eid));c.commit()
    elif kind=='recurring':st.cal_update(c,eid,rrule='FREQ=WEEKLY;BYDAY=MO;UNTIL=20261130')
    elif kind=='multi_day':st.cal_update(c,eid,end_date='2026-10-27')
    elif kind=='import':c.execute("UPDATE calendar_entry SET source='import' WHERE id=?",(eid,));c.commit()
    elif kind=='activity':
        # The adapter must reject an activity overlay before attempting a write.
        record=st.cal_get(c,eid)
        original=st.cal_get
        def linked(conn,identifier):
            result=original(conn,identifier)
            if result and identifier==eid:result['event_id']=999
            return result
        from unittest.mock import patch
        with patch.object(st,'cal_get',linked):
            with pytest.raises(ValueError):manage.actions.ADAPTERS[manage.MODES[mode]].prepare(c,users[0],{'entry_id':eid,**({'day':'2026-10-27','start_time':'11:00','end_time':'12:00'} if mode=='reschedule' else {})})
        return
    elif kind=='video':st.cal_update(c,eid,modality='online',meeting_url='https://meet.google.com/abc-defg-hij')
    else:
        room=rooms.request(c,title='Synthetic linked room',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=users[0]['id'],today=NOW.date())
        rooms.link_entry(c,room['id'],eid,users[0])
    fields={'entry_id':eid,**({'day':'2026-10-27','start_time':'11:00','end_time':'12:00'} if mode=='reschedule' else {})}
    saved=snapshot(c)
    with pytest.raises(ValueError):actions.issue(c,ctx,manage.MODES[mode],'unsupported-new-operation',fields,NOW)
    assert saved==snapshot(c)


def test_failed_audit_rolls_back_source_notices_revision_and_keeps_preview(management,monkeypatch):
    env,mode,eid=management;c,*_=env
    _,result=prepare(management);exact=confirmation(management,result);saved=snapshot(c)
    monkeypatch.setattr(st,'audit',lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic audit failure')))
    packet=command(env,exact,21)
    assert 'Recorded outcome:' not in packet['text'] and saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


def test_failed_response_handoff_rolls_back_entire_confirm(management):
    env,mode,eid=management;c,*_=env
    _,result=prepare(management);exact=confirmation(management,result);saved=snapshot(c)
    c.execute("CREATE TRIGGER test_manage_handoff BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(env[3],update(21,text=exact))
    assert response.status_code==503 and saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'
    assert not rows(c,'SELECT * FROM telegram_update WHERE update_id=21')


def test_create_consent_cannot_grant_management_or_other_action(management,monkeypatch):
    env,mode,eid=management;c,*_=env
    other='cancel' if mode=='reschedule' else 'reschedule'
    monkeypatch.setenv('CSS_TELEGRAM_'+manage.MODES[other].replace('.','_').upper()+'_ENABLED','1')
    assert 'unavailable' in command(env,'/meeting_'+other)['text']
    assert not rows(c,'SELECT * FROM telegram_meeting_origin WHERE action=?',(manage.MODES[other],))
    menu=command(env,'/menu',11)['text']
    assert '/meeting_'+mode in menu and '/meeting_'+other not in menu


def test_source_edited_and_reverted_cannot_revive_old_preview(management):
    env,mode,eid=management;c,users,*_=env
    _,result=prepare(management);exact=confirmation(management,result)
    original=st.cal_get(c,eid)
    st.cal_update(c,eid,by=users[0]['username'],venue='Temporary venue')
    st.cal_update(c,eid,by=users[0]['username'],venue=original['venue'])
    # Simulate a same-second edit/revert with all visible entry fields restored.
    c.execute('UPDATE calendar_entry SET updated_at=?,updated_by=? WHERE id=?',(original['updated_at'],original['updated_by'],eid));c.commit()
    saved=snapshot(c)
    assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)


def test_late_receipt_render_failure_rolls_back_confirm(management,monkeypatch):
    env,mode,eid=management;c,*_=env
    _,result=prepare(management);exact=confirmation(management,result);saved=snapshot(c)
    adapter=actions.ADAPTERS[manage.MODES[mode]]
    monkeypatch.setattr(adapter,'receipt_text',lambda *a:(_ for _ in ()).throw(ValueError('Synthetic late receipt failure')))
    assert 'Recorded outcome:' not in command(env,exact,21)['text']
    assert saved==snapshot(c)
    assert rows(c,'SELECT state FROM telegram_preview WHERE operation_id=?',(result['operation_id'],))[0]['state']=='pending'


@pytest.mark.parametrize('mode',['reschedule','cancel'])
def test_linking_requires_read_consent_and_current_management_pilot(linking,monkeypatch,mode):
    c,users,_,_,payload=linking;scope=manage.MODES[mode]
    ch,raw,confirmation=start(linking)
    monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,raw,[scope],NOW)
    links.claim(c,payload,raw,['calendar.read',scope],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_'+scope.replace('.','_').upper()+'_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_concurrent_confirmation_changes_source_once(management):
    env,mode,eid=management;c,_,path,*_=env
    ctx,result=prepare(management)
    def confirm(_):
        other=st.connect(path)
        try:return actions.confirm(other,ctx,result['token'],NOW)
        finally:other.close()
    before=c.execute('SELECT count(*) FROM calendar_entry_revision WHERE entry_id=?',(eid,)).fetchone()[0]
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(confirm,range(2)))
    assert results[0]==results[1]
    assert c.execute('SELECT count(*) FROM calendar_entry_revision WHERE entry_id=?',(eid,)).fetchone()[0]==before+1


def test_group_direct_and_other_account_contexts_never_mutate(management,monkeypatch):
    env,mode,eid=management;c,*_=env
    _,result=prepare(management);exact=confirmation(management,result);saved=snapshot(c)
    packet=update(21,text=exact);packet['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(env[3],packet).json()
    assert 'Recorded outcome:' not in submit(env[3],update(22,sender=202,text=exact)).json().get('text','')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(env,exact,23)
    assert saved==snapshot(c)


def test_deleted_meeting_receipt_does_not_recreate_source(management):
    env,mode,eid=management;c,*_=env
    _,result=prepare(management);exact=confirmation(management,result)
    command(env,exact,21)
    st.cal_delete(c,eid)
    text=command(env,'/'+mode+'_receipt '+result['operation_id'],22)['text']
    assert 'was deleted' in text and st.cal_get(c,eid) is None
