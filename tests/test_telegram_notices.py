"""Synthetic change-to-provider flow with no real credentials or business replay."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import json

import pytest

import backups
from documents_storage import rows,transaction
import rooms
import storage as st
import telegram_bot as bot
import telegram_changes as changes
import telegram_groups as groups
import telegram_group_reads as shared
import telegram_links as links
import telegram_notices as notices
from tests.test_work import workspace
from tests.test_telegram_bot import setup,NOW,submit,update
from tests.test_telegram_links import linking
from tests.test_telegram_groups import registered,register
from tests.test_telegram_changes import routed,drain,add_grant


def queued(c):return rows(c,"SELECT * FROM telegram_delivery WHERE projection_json LIKE '%change_notice%' ORDER BY id")


def stage(c):
    drain(c);return notices.enqueue(c,NOW)


def test_private_calendar_ui_change_current_fields_receipt_and_restart_dedup(routed,monkeypatch):
    linking,eid=routed;c,users,path,_,_=linking
    assert stage(c)==1;delivery=queued(c)[0]
    assert delivery['event_key'] and 'Synthetic private source' not in delivery['projection_json']
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',17,None))
    assert bot.deliver(c,NOW)==1
    assert all(s in calls[-1][2] for s in ('Calendar update','Synthetic private source','09:00','10:00','Asia/Manila','/calendar/entries/'+str(eid)))
    assert queued(c)[0]['state']=='accepted'
    restarted=st.connect(path)
    try:assert notices.enqueue(restarted,NOW)==0
    finally:restarted.close()
    assert bot.deliver(c,NOW+timedelta(seconds=2))==0
    st.cal_update(c,eid,start_time='11:00',end_time='12:00',title='Synthetic moved meeting');assert stage(c)==1
    assert bot.deliver(c,NOW+timedelta(seconds=3))==1
    assert '11:00' in calls[-1][2] and 'Synthetic moved meeting' in calls[-1][2]
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1 and not rows(c,'SELECT * FROM telegram_operation')
    assert all(a[1]==101 for a in calls)


@pytest.mark.parametrize('decision',['approved','declined','withdrawn'])
def test_own_room_decisions_show_true_status_without_meeting_disclosure(routed,monkeypatch,decision):
    linking,eid=routed;c,users,_,_,_=linking
    slot=next(s['id'] for s in rooms.list_slots(c) if s['start_time']=='09:00')
    record=rooms.request(c,title='Synthetic confidential room title',day='2026-10-26',slot_ids=[slot],requester_user_id=users[0]['id'],today=date(2026,10,20))
    stage(c);calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',3,None))
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=i*2))
    text=next(a[2] for a in calls if 'Room request update' in a[2])
    assert 'pending Administrative Section approval' in text and 'no booking held' in text
    if decision=='approved':rooms.approve(c,record['id'],'fixture',today=date(2026,10,20))
    elif decision=='declined':rooms.decline(c,record['id'],'fixture',note='Synthetic private reason')
    else:rooms.withdraw(c,record['id'],users[0]['id'],'fixture')
    assert stage(c)==1
    bot.deliver(c,NOW+timedelta(seconds=8));text=calls[-1][2]
    assert decision in text and record['ref_code'] in text and '/rooms/mine' in text
    if decision=='approved':assert 'approved (booked)' in text
    assert all(v not in text for v in ('Synthetic confidential room title','Synthetic private reason','/calendar/entries/'))
    assert len(rows(c,'SELECT * FROM room_reservation'))==1


@pytest.mark.parametrize('change',['source','grant','disconnect','restore','flag','bot','delete','ownership'])
def test_change_after_handoff_suppresses_queued_send(routed,monkeypatch,change):
    linking,eid=routed;c,users,path,_,payload=linking;stage(c)
    if change=='source':st.cal_update(c,eid,title='New source version')
    elif change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_CHANGE_NOTICES_ENABLED','0')
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    elif change=='delete':st.cal_delete(c,eid)
    else:c.execute("UPDATE calendar_entry SET created_by='another',audience='people' WHERE id=?",(eid,));c.commit()
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Stale notice send'))
    assert bot.deliver(c,NOW)==0
    assert queued(c)[0]['state']=='cancelled'


def test_source_change_after_render_is_fenced_and_accepted_inflight_becomes_uncertain(routed,monkeypatch):
    c=routed[0][0];eid=routed[1];stage(c);original=notices.render
    def render(*args):
        text=original(*args);st.cal_update(c,eid,title='Synthetic edit after rendering');return text
    monkeypatch.setattr(notices,'render',render)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Changed source escaped final fence'))
    assert bot.deliver(c,NOW)==0 and queued(c)[0]['state']=='uncertain'
    monkeypatch.setattr(notices,'render',original);stage(c)
    def send(*args):
        st.cal_update(c,eid,title='Synthetic edit during HTTP')
        return 'accepted',12,None
    monkeypatch.setattr(bot.transport,'send',send)
    assert bot.deliver(c,NOW+timedelta(seconds=2))==1
    assert queued(c)[-1]['state']=='uncertain' and queued(c)[-1]['provider_message_id'] is None
    assert bot.deliver(c,NOW+timedelta(seconds=4))==0


@pytest.mark.parametrize('outcome',['uncertain','retry_wait'])
def test_provider_uncertainty_never_replays_and_rate_limit_is_bounded(routed,monkeypatch,outcome):
    c=routed[0][0];stage(c);calls=[]
    monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or (outcome,None,2 if outcome=='retry_wait' else None))
    assert bot.deliver(c,NOW)==1
    assert bot.deliver(c,NOW)==0
    for i in range(1,7):bot.deliver(c,NOW+timedelta(seconds=i*3))
    assert len(calls)==(1 if outcome=='uncertain' else 5)
    assert queued(c)[0]['state']==('uncertain' if outcome=='uncertain' else 'failed')
    assert notices.enqueue(c,NOW+timedelta(seconds=30))==0
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1


def test_definite_rejection_pauses_new_notices_until_fresh_recognized_command(routed,monkeypatch):
    linking,eid=routed;c,users,_,client,_=linking;stage(c)
    monkeypatch.setattr(bot.transport,'send',lambda *a:('failed',None,None))
    assert bot.deliver(c,NOW)==1 and rows(c,'SELECT * FROM telegram_notice_pause')
    st.cal_update(c,eid,title='Synthetic while blocked');stage(c)
    assert len(queued(c))==1
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Paused notice replay'))
    assert bot.deliver(c,NOW+timedelta(seconds=2))==0
    monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(seconds=3))
    submit(client,update(30,text='unsupported text'));bot.process_updates(c,NOW+timedelta(seconds=3))
    assert rows(c,'SELECT * FROM telegram_notice_pause')
    submit(client,update(31,text='/status'));bot.process_updates(c,NOW+timedelta(seconds=3))
    assert not rows(c,'SELECT * FROM telegram_notice_pause')
    c.execute("UPDATE telegram_delivery SET state='cancelled' WHERE state='queued'");c.commit()
    st.cal_update(c,eid,title='Synthetic after recovery');drain(c);assert notices.enqueue(c,NOW+timedelta(seconds=4))==1
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',4,None))
    assert bot.deliver(c,NOW+timedelta(seconds=5))==1 and 'after recovery' in calls[-1][2]
    assert queued(c)[0]['state']=='failed'


def test_handoff_insert_rollback_two_workers_and_metadata_id_binding(routed,monkeypatch):
    c=routed[0][0];path=routed[0][2];drain(c)
    c.executescript("CREATE TRIGGER synthetic_notice_failure BEFORE UPDATE OF delivery_key ON telegram_change_route BEGIN SELECT RAISE(ABORT,'synthetic failure'); END;")
    with pytest.raises(Exception):notices.enqueue(c,NOW)
    assert not queued(c) and rows(c,'SELECT delivery_key FROM telegram_change_route')[0]['delivery_key'] is None
    c.execute('DROP TRIGGER synthetic_notice_failure');c.commit()
    def run():
        other=st.connect(path)
        try:return notices.enqueue(other,NOW)
        finally:other.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(lambda _:run(),range(2)))==1
    assert len(queued(c))==1
    delivery=queued(c)[0];p=json.loads(delivery['projection_json']);p['event']='f'*32
    assert not notices.allowed(c,delivery,p,bot.transport.config(),NOW)
    assert not notices.allowed(c,{**delivery,'chat_id':102},json.loads(delivery['projection_json']),bot.transport.config(),NOW)
    assert not rows(c,'SELECT * FROM telegram_operation')


def group_source(registered,monkeypatch):
    c,users,_,_,payload=registered
    for flag in ('CALENDAR_READ','CHANGE_NOTICES'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    add_grant(c,groups.linked(c,users[4]['id']),'calendar.read');group=register(registered,topic=7)
    eid=st.cal_create(c,'Synthetic shared meeting','2026-10-26',audience='bureau',by=users[4]['username'],venue='Synthetic venue')
    entry=st.cal_get(c,eid);shared.consent(c,payload,group['id'],group['generation'],eid,shared.revision(entry),True,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit();stage(c)
    return eid,group


@pytest.mark.parametrize('change',['none','membership','source','unshare','removed','during_proof'])
def test_shared_calendar_notice_exact_topic_current_consent_and_final_proof(registered,monkeypatch,change):
    c,users,_,_,payload=registered;eid,group=group_source(registered,monkeypatch)
    if change=='membership':monkeypatch.setattr(bot.transport,'member_status',lambda *a:'left')
    elif change=='source':st.cal_update(c,eid,title='Unapproved changed title')
    elif change=='unshare':shared.consent(c,payload,group['id'],group['generation'],eid,'',False,NOW)
    elif change=='removed':groups.manage(c,payload,group['id'],group['generation'],'pause')
    elif change=='during_proof':
        def proof(*a):
            assert not c.in_transaction
            st.cal_update(c,eid,venue='Unapproved proof-time edit');return 'administrator'
        monkeypatch.setattr(bot.transport,'member_status',proof)
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',11,None))
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=i*2))
    group_calls=[a for a in calls if a[1]<0]
    assert len(group_calls)==(1 if change=='none' else 0)
    if group_calls:
        assert group_calls[0][3]==7 and 'Shared calendar update' in group_calls[0][2]
        assert '/calendar/entries/'+str(eid) in group_calls[0][2]
        assert all(v not in group_calls[0][2] for v in ('Participants','account ',users[4]['username']))


def test_group_room_notice_is_anonymous_exact_topic_and_current_booking_status(registered,monkeypatch):
    import telegram_actions as actions
    import telegram_meetings as meetings
    from tests.test_telegram_groups import group_update
    c,users,_,client,_=registered
    for flag in ('CALENDAR_READ','ROOMS_READ','ROOMS_REQUEST','CHANGE_NOTICES'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id'])
    for scope in ('calendar.read','rooms.read','rooms.request'):add_grant(c,connection,scope)
    register(registered,topic=7);register(registered,number=2,topic=8)
    eid=st.cal_create(c,'Synthetic secret meeting','2026-10-26',audience='bureau',by=users[4]['username'])
    submit(client,group_update(10,topic=7,text='/room_request'))
    origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request'")[0]
    ctx=meetings.origin(c,users[4],origin['id'],NOW,'rooms.request')
    p=actions.issue(c,ctx,'rooms.request','synthetic-group-notice-key',{'entry_id':eid,'from_time':'09:00','to_time':'10:00'},NOW)
    result=actions.confirm(c,ctx,p['token'],NOW);record=rooms.get_reservation(c,result['result_room_id'])
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit();stage(c)
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',14,None))
    for i in range(4):bot.deliver(c,NOW+timedelta(seconds=i*2))
    texts=[a[2] for a in calls if a[1]<0]
    assert len(texts)==1 and 'requested' in texts[0] and 'no hold' in texts[0]
    assert all(a[3]==7 for a in calls if a[1]<0)
    assert all(s not in texts[0] for s in (record['ref_code'],'Synthetic secret meeting',users[4]['username'],'/calendar/entries/'))
    rooms.approve(c,record['id'],'fixture',today=date(2026,10,20));assert stage(c)==2
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=10+i*2))
    text=[a[2] for a in calls if a[1]<0][-1]
    assert ': booked' in text and 'Booked means approved' in text
    assert record['ref_code'] not in text
    assert len(rows(c,'SELECT * FROM room_reservation'))==1


def test_group_rejection_pause_requires_fresh_command_in_same_topic(registered,monkeypatch):
    from tests.test_telegram_groups import group_update,bind
    c,users,_,client,payload=registered;eid,group=group_source(registered,monkeypatch)
    c.execute("UPDATE telegram_delivery SET state='cancelled' WHERE chat_id>0");c.commit()
    monkeypatch.setattr(bot.transport,'send',lambda *a:('failed',None,None))
    assert bot.deliver(c,NOW)==1
    assert rows(c,'SELECT * FROM telegram_notice_pause')[0]['topic_id']==7
    monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(seconds=3))
    submit(client,group_update(20,topic=8,text='/group_status'));bot.process_updates(c,NOW+timedelta(seconds=3))
    assert rows(c,'SELECT * FROM telegram_notice_pause')
    bind(c,users[0],102);other=groups.linked(c,users[0]['id'])
    route=rows(c,'SELECT * FROM telegram_change_route WHERE chat_id<0')[0]
    assert notices.paused(c,{**route,'connection_id':other['id'],'generation':other['generation']})
    submit(client,group_update(21,sender=102,topic=7,text='/group_status'));bot.process_updates(c,NOW+timedelta(seconds=3))
    assert not rows(c,'SELECT * FROM telegram_notice_pause')
    assert len([d for d in queued(c) if d['chat_id']<0])==1


def test_restore_during_http_fences_provider_success_and_new_generation(routed,monkeypatch):
    linking,eid=routed;c,_,path,_,_=linking;stage(c)
    def send(*args):
        backups.clear_restored_sessions(path)
        return 'accepted',29,None
    monkeypatch.setattr(bot.transport,'send',send)
    assert bot.deliver(c,NOW)==1
    assert queued(c)[0]['state']=='uncertain' and queued(c)[0]['provider_message_id'] is None
    assert notices.enqueue(c,NOW+timedelta(seconds=2))==0
    assert bot.deliver(c,NOW+timedelta(seconds=3))==0
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1


def test_additive_handoff_migration_preserves_old_routes_and_no_backfill(routed):
    c=routed[0][0];drain(c);before=rows(c,'SELECT event_key,chat_id,generation FROM telegram_change_route')
    # An earlier T4.1 database has routes but no notice handoff metadata.
    for trigger in ('telegram_notice_route_fence','telegram_notice_recover_insert','telegram_notice_recover_processed'):
        c.execute('DROP TRIGGER '+trigger)
    c.execute('DROP INDEX telegram_notice_handoff');c.execute('ALTER TABLE telegram_change_route DROP COLUMN delivery_key')
    c.execute('DROP TABLE telegram_notice_pause');c.commit();st.init_db(c)
    assert rows(c,'SELECT event_key,chat_id,generation FROM telegram_change_route')==before
    assert rows(c,'SELECT delivery_key FROM telegram_change_route')[0]['delivery_key'] is None
    assert not queued(c)
    dump=sorted(c.iterdump());st.init_db(c);assert sorted(c.iterdump())==dump
    assert notices.enqueue(c,NOW)==1 and not c.execute('PRAGMA foreign_key_check').fetchall()


def test_expired_handoff_and_old_cancelled_route_ids_cannot_revive_delivery(routed):
    c=routed[0][0];stage(c);old=queued(c)[0];p=json.loads(old['projection_json'])
    bot.cleanup(c,NOW+timedelta(days=31))
    assert not rows(c,'SELECT * FROM telegram_change_route')
    assert not notices.allowed(c,old,p,bot.transport.config(),NOW)
    assert notices.enqueue(c,NOW+timedelta(days=31))==0
    assert queued(c)[0]['state']=='cancelled'
    st.cal_update(c,routed[1],title='Synthetic new source version')
    stage(c)
    assert rows(c,'SELECT * FROM telegram_change_route')[0]['id']==p['route']
    assert not notices.allowed(c,old,p,bot.transport.config(),NOW)


def test_stale_pause_metadata_cleanup_retains_only_active_invalid_binding(routed,monkeypatch):
    linking,eid=routed;c,_,_,_,payload=linking;stage(c)
    monkeypatch.setattr(bot.transport,'send',lambda *a:('failed',None,None));bot.deliver(c,NOW)
    with transaction(c):notices.cleanup_in_transaction(c,NOW+timedelta(days=31))
    assert rows(c,'SELECT * FROM telegram_notice_pause')
    links.disconnect(c,payload,NOW)
    with transaction(c):notices.cleanup_in_transaction(c,NOW+timedelta(days=31))
    assert not rows(c,'SELECT * FROM telegram_notice_pause')


def test_signed_in_ui_create_and_edit_reach_private_notice(manager,app_mod,monkeypatch):
    from urllib.parse import urlencode
    import auth
    from tests.test_telegram_bot import TOKEN,SECRET
    from tests.test_telegram_groups import bind
    c=st.connect(app_mod.DB)
    try:
        for flag in ('INBOUND','DELIVERY','LINK','CALENDAR_READ','CHANGE_NOTICES'):
            monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
        monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
        monkeypatch.setenv('CSS_BASE_URL','https://office.example')
        user=links.current(c,auth.parse_token(manager.cookies.get(auth.COOKIE_NAME)));user_id=user['id']
        bind(c,user,101);add_grant(c,groups.linked(c,user_id),'calendar.read')
        c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
        fields={'title':'Synthetic UI meeting notice','kind':'meeting','status':'confirmed','start_date':'2026-10-26',
                'audience':'bureau','start_time':'09:00','end_time':'10:00'}
        headers={'Content-Type':'application/x-www-form-urlencoded','Origin':'https://office.example'}
        response=manager.post('/calendar/new',content=urlencode(fields),headers=headers,follow_redirects=False)
        assert response.status_code==303
        eid=int(response.headers['location'].split('/calendar/entries/')[1].split('?')[0])
        calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',14,None))
        stage(c);assert bot.deliver(c,NOW)==1 and 'Synthetic UI meeting notice' in calls[-1][2]
        response=manager.post('/calendar/entries/'+str(eid)+'/edit',content=urlencode({**fields,'start_time':'11:00','end_time':'12:00'}),headers=headers,follow_redirects=False)
        assert response.status_code==303
        stage(c);assert bot.deliver(c,NOW+timedelta(seconds=2))==1
        assert '11:00' in calls[-1][2] and '/calendar/entries/'+str(eid) in calls[-1][2]
        assert len(rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic UI meeting notice'"))==1
        assert not rows(c,'SELECT * FROM telegram_operation')
    finally:c.close()
