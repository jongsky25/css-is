"""Private opt-in reminders, synthetic sources/provider and restart-safe identities."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timedelta,timezone
import json

import pytest

import backups
from documents_storage import rows
import rooms
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_preferences as prefs
import telegram_reminders as reminders
from tests.test_work import workspace
from tests.test_telegram_bot import setup,NOW,update,submit
from tests.test_telegram_links import linking,activate
from tests.test_telegram_changes import routed,add_grant
from tests.test_telegram_preferences import session,save as channels

AT=NOW+timedelta(days=1,minutes=30)  # 08:30 Manila, meeting at 09:00
START=AT+timedelta(minutes=30)


def deliveries(c):return rows(c,"SELECT * FROM telegram_delivery WHERE dedupe_key LIKE 'reminder:%' ORDER BY id")


@pytest.fixture
def ready(routed,monkeypatch):
    linking,eid=routed;c,users,path,client,payload=linking
    monkeypatch.setenv('CSS_TELEGRAM_REMINDERS_ENABLED','1')
    reminders.save(c,payload,0,30,30,NOW)
    return linking,eid


def test_defaults_and_idempotent_migration_preserve_existing_sources_and_choices(workspace):
    c,users,_,_=workspace;payload=session(c,users[0]);eid=st.cal_create(c,'Synthetic old source','2026-10-26')
    assert reminders.get(c,users[0]['id'])['calendar_minutes']==0
    assert not rows(c,'SELECT * FROM telegram_reminder_preference')
    c.execute('DELETE FROM telegram_change_event');c.execute('DELETE FROM telegram_change_head');c.commit()
    reminders.install(c);c.commit()
    first=rows(c,'SELECT * FROM telegram_change_head');assert first and not rows(c,'SELECT * FROM telegram_change_event')
    reminders.save(c,payload,0,15,60,NOW)
    reminders.install(c);c.commit()
    assert rows(c,'SELECT * FROM telegram_change_head')==first and st.cal_get(c,eid)
    assert reminders.get(c,users[0]['id'])['calendar_minutes']==15


def test_current_account_stale_and_invalid_choices_and_atomic_audit(workspace,monkeypatch):
    c,users,_,_=workspace;payload=session(c,users[0])
    with pytest.raises(ValueError):reminders.save(c,payload,0,'1',30,NOW)
    reminders.save(c,payload,0,15,60,NOW)
    with pytest.raises(prefs.Conflict):reminders.save(c,payload,0,30,30,NOW)
    assert reminders.get(c,users[1]['id'])['revision']==0
    before=reminders.get(c,users[0]['id'])
    monkeypatch.setattr(st,'audit',lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic audit failure')))
    with pytest.raises(ValueError):reminders.save(c,payload,1,0,0,NOW)
    assert reminders.get(c,users[0]['id'])==before
    c.execute('DELETE FROM login_session');c.commit()
    with pytest.raises(ValueError):reminders.save(c,payload,1,0,0,NOW)


@pytest.mark.parametrize('offset,expected',[(-1,0),(0,1),(1799,1),(1800,0)])
def test_due_inclusive_start_exclusive_and_no_past_start_catchup(ready,offset,expected):
    c=ready[0][0]
    assert reminders.enqueue(c,AT+timedelta(seconds=offset))==expected
    assert len(deliveries(c))==expected


def test_two_workers_restart_repeated_ticks_and_retention_keep_one_occurrence(ready,monkeypatch):
    linking,eid=ready;c,users,path,_,_=linking
    def enqueue(_):
        other=st.connect(path)
        try:return reminders.enqueue(other,AT)
        finally:other.close()
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(enqueue,range(2)))==1
    assert reminders.enqueue(c,AT)==0
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *a:sent.append(a) or ('accepted',12,None))
    assert bot.deliver(c,AT)==1 and 'Calendar reminder' in sent[0][2] and '09:00' in sent[0][2]
    assert bot.deliver(c,AT+timedelta(seconds=2))==0
    assert deliveries(c)[0]['provider_message_id']==12
    c.execute("UPDATE telegram_delivery SET updated_at='2025-01-01T00:00:00Z' WHERE dedupe_key LIKE 'reminder:%'");c.commit()
    bot.cleanup(c,AT)
    assert not deliveries(c) and reminders.enqueue(c,AT)==0
    tombstones=rows(c,'SELECT * FROM telegram_reminder_occurrence')
    assert len(tombstones)==1 and set(tombstones[0])=={'occurrence_key','created_at'}
    assert 'Synthetic' not in str(tombstones)


def test_failed_handoff_rolls_back_occurrence_and_cursor_then_recovers(ready):
    c=ready[0][0]
    c.executescript("CREATE TRIGGER synthetic_reminder_failure BEFORE INSERT ON telegram_delivery WHEN NEW.dedupe_key LIKE 'reminder:%' BEGIN SELECT RAISE(ABORT,'synthetic handoff failure'); END;")
    with pytest.raises(Exception,match='synthetic handoff failure'):reminders.enqueue(c,AT)
    assert not rows(c,'SELECT * FROM telegram_reminder_occurrence') and not deliveries(c)
    c.execute('DROP TRIGGER synthetic_reminder_failure');c.commit()
    assert reminders.enqueue(c,AT)==1


def test_recurring_occurrences_are_separate_and_skipped_dates_suppress(ready,monkeypatch):
    c=ready[0][0];eid=ready[1]
    st.cal_update(c,eid,rrule='FREQ=WEEKLY;BYDAY=MO;UNTIL=20261109',exdates='2026-11-02')
    assert reminders.enqueue(c,AT)==1
    assert reminders.enqueue(c,AT+timedelta(days=7))==0
    assert reminders.enqueue(c,AT+timedelta(days=14))==1
    assert len(deliveries(c))==2
    st.cal_update(c,eid,exdates='2026-10-26,2026-11-02')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Skipped occurrence escaped'))
    assert bot.deliver(c,AT)==0


def test_midnight_manila_occurrence_due_on_previous_local_and_utc_day(ready):
    c=ready[0][0];eid=ready[1]
    st.cal_update(c,eid,start_time='00:15',end_time='01:00')
    at=datetime(2026,10,25,15,45,tzinfo=timezone.utc)  # 23:45 Manila on previous day
    assert reminders.enqueue(c,at)==1
    assert deliveries(c)[0]['expires_at']==links.stamp(datetime(2026,10,25,16,15,tzinfo=timezone.utc))


def test_reschedule_replaces_pending_occurrence_but_title_edit_renders_current_data(ready,monkeypatch):
    c=ready[0][0];eid=ready[1];reminders.enqueue(c,AT)
    oldkey=deliveries(c)[0]['dedupe_key'];st.cal_update(c,eid,start_time='10:00',end_time='11:00')
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *a:sent.append(a) or ('accepted',2,None))
    assert bot.deliver(c,AT)==0 and deliveries(c)[0]['state']=='cancelled'
    later=AT+timedelta(hours=1);assert reminders.enqueue(c,later)==1
    st.cal_update(c,eid,title='Synthetic newest permitted title')
    assert bot.deliver(c,later)==1 and 'Synthetic newest permitted title' in sent[0][2] and '10:00' in sent[0][2]
    assert deliveries(c)[-1]['dedupe_key']!=oldkey and reminders.enqueue(c,later)==0


@pytest.mark.parametrize('change',['cancel','postpone','all_day','owner','grant','inactive','disconnect','bot','flag','delete','restore'])
def test_current_authority_configuration_source_and_restore_suppress(ready,monkeypatch,change):
    linking,eid=ready;c,users,path,_,payload=linking;reminders.enqueue(c,AT)
    if change=='cancel':st.cal_update(c,eid,status='cancelled')
    elif change=='postpone':st.cal_update(c,eid,status='postponed')
    elif change=='all_day':st.cal_update(c,eid,start_time=None,end_time=None)
    elif change=='owner':c.execute("UPDATE calendar_entry SET created_by='another',audience='people' WHERE id=?",(eid,));c.commit()
    elif change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(AT),));c.commit()
    elif change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,AT)
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_REMINDERS_ENABLED','0')
    elif change=='delete':st.cal_delete(c,eid)
    else:backups.clear_restored_sessions(path)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Stale reminder escaped'))
    assert bot.deliver(c,AT)==0 and deliveries(c)[0]['state']=='cancelled'


def test_private_only_approved_own_room_booking_with_current_slot_time(ready,monkeypatch):
    linking,_=ready;c,users,_,_,_=linking
    reminders.save(c,linking[-1],1,0,30,NOW)
    slots=rooms.list_slots(c);slot=next(s['id'] for s in slots if s['start_time']=='09:00')
    record=rooms.request(c,title='Synthetic room reminder',day='2026-10-26',slot_ids=[slot],requester_user_id=users[0]['id'],today=date(2026,10,20))
    assert reminders.enqueue(c,AT)==0
    rooms.approve(c,record['id'],'synthetic',today=date(2026,10,20))
    assert reminders.enqueue(c,AT)==1
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *a:sent.append(a) or ('accepted',3,None))
    assert bot.deliver(c,AT)==1 and 'approved (booked)' in sent[0][2] and record['ref_code'] in sent[0][2]
    assert sent[0][1]==101 and deliveries(c)[0]['registration_id'] is None
    assert 'Synthetic room reminder' not in str(deliveries(c))


def test_quiet_defer_reset_preserves_provider_retry_and_stale_quiet_expires(ready,monkeypatch):
    linking,_=ready;c,users,_,_,payload=linking
    reminders.save(c,payload,1,60,0,NOW)
    at=AT-timedelta(minutes=30);reminders.enqueue(c,at)
    monkeypatch.setattr(bot.transport,'send',lambda *a:('retry_wait',None,120))
    assert bot.deliver(c,at)==1
    retry=deliveries(c)[0]['retry_at']
    channels(c,users[0],payload,quiet_start='08:00',quiet_end='08:30')
    assert bot.deliver(c,at+timedelta(minutes=2))==0
    assert deliveries(c)[0]['not_before']==links.stamp(AT) and deliveries(c)[0]['attempts']==1
    channels(c,users[0],payload,quiet_start='',quiet_end='')
    assert deliveries(c)[0]['not_before'] is None and deliveries(c)[0]['retry_at']==retry
    monkeypatch.setattr(bot.transport,'send',lambda *a:('accepted',1,None))
    assert bot.deliver(c,at+timedelta(minutes=3))==1
    eid=st.cal_create(c,'Synthetic expired quiet','2026-10-26',start_time='09:00',end_time='10:00',by=users[0]['username'])
    channels(c,users[0],payload,quiet_start='08:00',quiet_end='09:00')
    assert reminders.enqueue(c,AT)==1 and deliveries(c)[-1]['state']=='cancelled'


@pytest.mark.parametrize('change',['source','lead','channel','grant'])
def test_changes_after_render_or_during_http_fence_claims(ready,monkeypatch,change):
    linking,eid=ready;c,users,_,_,payload=linking;reminders.enqueue(c,AT)
    def edit():
        if change=='source':st.cal_update(c,eid,title='Synthetic changed during send')
        elif change=='lead':reminders.save(c,payload,1,0,0,AT)
        elif change=='channel':channels(c,users[0],payload,calendar_mode='email')
        else:c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(AT),));c.commit()
    def send(*args):edit();return 'accepted',99,None
    monkeypatch.setattr(bot.transport,'send',send)
    assert bot.deliver(c,AT)==1 and deliveries(c)[0]['state']=='uncertain' and deliveries(c)[0]['provider_message_id'] is None
    assert reminders.enqueue(c,AT)==0 and bot.deliver(c,AT+timedelta(seconds=2))==0


def test_source_change_after_render_blocks_http(ready,monkeypatch):
    c=ready[0][0];eid=ready[1];reminders.enqueue(c,AT);original=reminders.render
    def render(*args):
        text=original(*args);st.cal_update(c,eid,title='Synthetic race');return text
    monkeypatch.setattr(reminders,'render',render)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Source changed after rendering'))
    assert bot.deliver(c,AT)==0 and deliveries(c)[0]['state']=='uncertain'


def test_email_only_suppresses_new_reminders_and_optout_cancels_without_replay(ready,monkeypatch):
    linking,eid=ready;c,users,_,_,payload=linking
    channels(c,users[0],payload,calendar_mode='email');assert reminders.enqueue(c,AT)==0
    channels(c,users[0],payload,calendar_mode='telegram');assert reminders.enqueue(c,AT)==1
    reminders.save(c,payload,1,0,0,AT)
    assert deliveries(c)[0]['state']=='cancelled'
    reminders.save(c,payload,2,30,0,AT)
    assert reminders.enqueue(c,AT)==0


def test_provider_rejection_pauses_subsequent_automatic_reminders(ready,monkeypatch):
    linking,eid=ready;c,users,_,_,_=linking;reminders.enqueue(c,AT)
    monkeypatch.setattr(bot.transport,'send',lambda *a:('failed',None,None))
    assert bot.deliver(c,AT)==1
    assert rows(c,'SELECT * FROM telegram_notice_pause')
    st.cal_create(c,'Synthetic subsequent reminder','2026-10-26',start_time='09:00',end_time='10:00',by=users[0]['username'])
    assert reminders.enqueue(c,AT)==1
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Blocked bot got another reminder'))
    assert bot.deliver(c,AT+timedelta(seconds=2))==0


def test_bounded_source_cursor_eventually_visits_later_due_entries(ready,monkeypatch):
    c=ready[0][0];uid=ready[0][1][0]['username']
    monkeypatch.setattr(reminders,'SOURCES_PER_USER',1)
    st.cal_create(c,'Synthetic second due','2026-10-26',start_time='09:00',end_time='10:00',by=uid)
    assert reminders.enqueue(c,AT)==1 and reminders.enqueue(c,AT)==1 and reminders.enqueue(c,AT)==0
    assert reminders.enqueue(c,AT)==0 and len(deliveries(c))==2


def test_tick_runs_reminders_independently_of_change_notice_switch(ready,monkeypatch):
    c=ready[0][0]
    monkeypatch.setenv('CSS_TELEGRAM_CHANGE_NOTICES_ENABLED','0')
    monkeypatch.setattr(bot.transport,'send',lambda *a:('accepted',5,None))
    assert bot.tick(c,AT)[1]==1 and deliveries(c)[0]['state']=='accepted'
    assert bot.tick(c,AT+timedelta(seconds=2))[1]==0


def test_source_numeric_id_reuse_cannot_authorize_old_occurrence(ready,monkeypatch):
    linking,eid=ready;c,users,_,_,_=linking;reminders.enqueue(c,AT)
    incarnation=json.loads(deliveries(c)[0]['projection_json'])['incarnation']
    st.cal_delete(c,eid)
    new_id=st.cal_create(c,'Synthetic reused source','2026-10-26',start_time='09:00',end_time='10:00',by=users[0]['username'])
    assert new_id==eid
    assert reminders.enqueue(c,AT)==1
    assert json.loads(deliveries(c)[-1]['projection_json'])['incarnation']!=incarnation
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *a:sent.append(a) or ('accepted',2,None))
    assert bot.deliver(c,AT)==1 and 'Synthetic reused source' in sent[0][2]
    assert deliveries(c)[0]['state']=='cancelled' and deliveries(c)[-1]['state']=='accepted'


def test_quiet_restore_and_lead_choices_persist_without_replaying_old_job(ready):
    linking,eid=ready;c,users,path,_,payload=linking
    channels(c,users[0],payload,quiet_start='08:00',quiet_end='08:45')
    reminders.enqueue(c,AT);before=reminders.get(c,users[0]['id'])
    assert deliveries(c)[0]['not_before'] and deliveries(c)[0]['attempts']==0
    backups.clear_restored_sessions(path)
    assert reminders.get(c,users[0]['id'])==before
    assert deliveries(c)[0]['state']=='cancelled' and reminders.enqueue(c,AT)==0


def test_room_slot_change_during_http_fences_sender(ready,monkeypatch):
    linking,_=ready;c,users,_,_,payload=linking;reminders.save(c,payload,1,0,30,NOW)
    slot=next(s['id'] for s in rooms.list_slots(c) if s['start_time']=='09:00')
    record=rooms.request(c,title='Synthetic room race',day='2026-10-26',slot_ids=[slot],requester_user_id=users[0]['id'],today=date(2026,10,20))
    rooms.approve(c,record['id'],'synthetic',today=date(2026,10,20));reminders.enqueue(c,AT)
    def send(*args):
        c.execute("UPDATE room_slot SET end_time='10:30' WHERE id=?",(slot,));c.commit();return 'accepted',5,None
    monkeypatch.setattr(bot.transport,'send',send)
    assert bot.deliver(c,AT)==1 and deliveries(c)[0]['state']=='uncertain'
    assert bot.deliver(c,AT+timedelta(seconds=2))==0


def test_malformed_cross_destination_and_expired_reminders_never_send(ready,monkeypatch):
    c=ready[0][0];reminders.enqueue(c,AT);d=deliveries(c)[0];p=json.loads(d['projection_json'])
    p['occurrence']='2026-99-99'
    assert not reminders.descriptor(p,bot.transport.config())
    assert not reminders.allowed(c,{**d,'chat_id':-100},json.loads(d['projection_json']),bot.transport.config(),AT)
    c.execute('UPDATE telegram_delivery SET not_before=? WHERE id=?',(links.stamp(START+timedelta(days=2)),d['id']));c.commit()
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Expired deferred reminder'))
    bot.cleanup(c,START)
    assert deliveries(c)[0]['state']=='cancelled' and bot.deliver(c,START)==0


@pytest.mark.parametrize('lead',[15,30,60,1440])
def test_each_lead_becomes_due_at_its_exact_utc_instant(ready,lead):
    linking,_=ready;c,_,_,_,payload=linking;reminders.save(c,payload,1,lead,0,NOW)
    at=START-timedelta(minutes=lead)
    assert reminders.enqueue(c,at-timedelta(seconds=1))==0
    assert reminders.enqueue(c,at)==1 and deliveries(c)[0]['expires_at']==links.stamp(START)


@pytest.mark.parametrize('change',['withdrawn','day','slot','requester'])
def test_approved_room_schedule_status_and_requester_are_rechecked(ready,monkeypatch,change):
    linking,_=ready;c,users,_,_,payload=linking;reminders.save(c,payload,1,0,30,NOW)
    slots=rooms.list_slots(c);slot=next(s['id'] for s in slots if s['start_time']=='09:00')
    record=rooms.request(c,title='Synthetic stale booking',day='2026-10-26',slot_ids=[slot],requester_user_id=users[0]['id'],today=date(2026,10,20))
    rooms.approve(c,record['id'],'synthetic',today=date(2026,10,20));assert reminders.enqueue(c,AT)==1
    if change=='withdrawn':c.execute("UPDATE room_reservation SET status='withdrawn' WHERE id=?",(record['id'],))
    elif change=='day':c.execute("UPDATE room_reservation SET day='2026-10-27' WHERE id=?",(record['id'],))
    elif change=='requester':c.execute('UPDATE room_reservation SET requester_user_id=? WHERE id=?',(users[1]['id'],record['id']))
    else:
        later=next(s['id'] for s in slots if s['start_time']=='10:00')
        c.execute('UPDATE room_reservation_slot SET slot_id=? WHERE reservation_id=?',(later,record['id']))
    c.commit();monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Stale booking reminder'))
    assert bot.deliver(c,AT)==0 and deliveries(c)[0]['state']=='cancelled'


def test_failed_settings_audit_rolls_back_pending_reminder_cancellation(ready,monkeypatch):
    linking,_=ready;c,_,_,_,payload=linking;reminders.enqueue(c,AT)
    monkeypatch.setattr(st,'audit',lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic audit rollback')))
    with pytest.raises(ValueError):reminders.save(c,payload,1,0,0,AT)
    assert reminders.get(c,linking[1][0]['id'])['calendar_minutes']==30 and deliveries(c)[0]['state']=='queued'
