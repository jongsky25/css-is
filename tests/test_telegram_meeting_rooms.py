"""Combined confirmed intent, separate child receipts and room-only recovery."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,timedelta
import json

import pytest

import backups
from documents_storage import rows,transaction
import room_actions
import rooms
import rooms_notify
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_meeting_rooms as combined
import telegram_room_requests as requests
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking
from tests.test_telegram_meetings import meeting_env,FIELDS,confirm
from tests.test_telegram_groups import registered,register,group_update


ROOM={'from_time':'09:00','to_time':'10:00'}


def add_room_grants(c,user,monkeypatch):
    for flag in ('ROOMS_READ','ROOMS_REQUEST'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=rows(c,'SELECT * FROM telegram_connection WHERE account_id=? AND state=\'active\'',(user['id'],))[0]
    for scope in ('rooms.read','rooms.request'):
        c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],user['id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()


@pytest.fixture
def combined_env(meeting_env,monkeypatch):
    c,users,_,_,_=meeting_env[0]
    add_room_grants(c,users[0],monkeypatch)
    return meeting_env


def prepare(env,key='synthetic-combined-meeting-key',**fields):
    c,users,_,_,_=env[0]
    ctx=meetings.origin(c,users[0],env[1]['id'],NOW)
    return actions.issue(c,ctx,meetings.ACTION,key,{**FIELDS,'room':ROOM,**fields},NOW)


def block(c):
    sid=next(s['id'] for s in rooms.list_slots(c) if s['start_time']=='09:00')
    c.execute("INSERT INTO room_block(day,slot_id,reason,created_by,created_at) VALUES (?,?,?,'fixture',?)",('2026-10-26',sid,'Synthetic private reason',links.stamp(NOW)));c.commit()


def test_combined_success_has_separate_child_and_current_pending_approval(combined_env,monkeypatch):
    c,users,_,client,_=combined_env[0];p=prepare(combined_env)
    text=meetings.ADAPTER.text(p['preview'])
    assert all(s in text for s in ('09:00 – 10:00','60 minutes','09:00 – 10:30','no booking held','keep the meeting'))
    parent=confirm(combined_env,p)
    assert parent['state']=='committed' and parent['result_code']=='meeting_room_requested'
    child=combined.children(c,parent)[0]
    assert child['state']=='committed' and child['action']=='rooms.request'
    assert child['result_room_id']==parent['result_room_id'] and child['result_entry_id']==parent['result_entry_id']
    record=rooms.get_reservation(c,parent['result_room_id'])
    assert record['status']=='requested' and record['requester_user_id']==users[0]['id'] and record['calendar_entry_id']==parent['result_entry_id']
    confirm(combined_env,p,12)
    assert len(rows(c,'SELECT * FROM calendar_entry'))==len(rows(c,'SELECT * FROM room_reservation'))==1
    assert len(rows(c,'SELECT * FROM telegram_operation'))==2
    assert not rows(c,'SELECT * FROM telegram_preview WHERE operation_id=?',(child['operation_id'],))
    assert prepare(combined_env)['receipt']['result_entry_id']==parent['result_entry_id']
    text=meetings.ADAPTER.receipt_text(c,users[0],parent)
    assert 'pending approval' in text and '/calendar/entries/'+str(parent['result_entry_id']) in text and '/rooms/mine' in text
    rooms.approve(c,record['id'],'fixture',today=date(2026,10,20))
    assert 'approved (booked)' in meetings.ADAPTER.receipt_text(c,users[0],parent)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',19,None))
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=2*i))
    assert all(a[1]==101 for a in messages) and not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')


def test_calendar_success_room_failure_and_fresh_child_retry_reuse_original_meeting(combined_env,monkeypatch):
    c,users,path,client,_=combined_env[0];p=prepare(combined_env);block(c)
    parent=confirm(combined_env,p)
    assert parent['state']=='partial' and parent['result_code']=='meeting_room_failed'
    failed=combined.children(c,parent)[0]
    assert failed['state']=='failed' and failed['result_code']=='room_unavailable' and not failed['result_room_id']
    assert failed['result_entry_id']==parent['result_entry_id']
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1 and not rows(c,'SELECT * FROM room_reservation')
    text=meetings.ADAPTER.receipt_text(c,users[0],parent)
    assert 'Room request failed' in text and 'Next: you' in text and '?parent_operation_id='+p['operation_id'] in text
    assert 'Synthetic private reason' not in text
    # A restart and replay of the parent never retry either mutation.
    restarted=st.connect(path)
    try:
        ctx=json.loads(parent['context_json'])
        assert actions.confirm(restarted,ctx,p['token'],NOW)['result_entry_id']==parent['result_entry_id']
    finally:restarted.close()
    c.execute('DELETE FROM room_block');c.commit()
    submit(client,update(12,text='/room_request'))
    origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request'")[0]
    ctx=meetings.origin(c,users[0],origin['id'],NOW,'rooms.request')
    retry=actions.issue(c,ctx,'rooms.request','synthetic-room-retry-key',{'entry_id':parent['result_entry_id'],**ROOM,'parent_operation_id':parent['operation_id']},NOW)
    assert retry['preview']['parent_operation_id']==parent['operation_id']
    submit(client,update(13,text='/room_confirm '+retry['token']));bot.process_updates(c,NOW)
    child=combined.children(c,parent)[0]
    assert child['operation_id']==retry['operation_id'] and child['state']=='committed'
    assert child['result_entry_id']==parent['result_entry_id']
    assert len(rows(c,'SELECT * FROM calendar_entry'))==len(rows(c,'SELECT * FROM room_reservation'))==1
    bot.cleanup(c,NOW+timedelta(days=2))
    assert not rows(c,'SELECT * FROM telegram_preview')
    submit(client,update(14,text='/meeting_receipt '+parent['operation_id']));bot.process_updates(c,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled' WHERE dedupe_key NOT LIKE 'action-recover:%'");c.commit()
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',3,None))
    bot.deliver(c,NOW+timedelta(seconds=3))
    assert messages and 'pending approval' in messages[-1][2]
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1


@pytest.mark.parametrize('failure',['notice','receipt','unexpected_child'])
def test_unexpected_failure_rolls_back_calendar_child_audit_outboxes_and_tokens(combined_env,monkeypatch,failure):
    c,users,_,_,_=combined_env[0];p=prepare(combined_env)
    before=c.execute('SELECT count(*) FROM audit_log').fetchone()[0]
    def fail(*a,**kw):raise RuntimeError('Synthetic unexpected failure')
    if failure=='notice':monkeypatch.setattr(rooms_notify,'on_requested',fail)
    elif failure=='receipt':monkeypatch.setattr(meetings.ADAPTER,'queue_receipt',fail)
    else:monkeypatch.setattr(room_actions,'request_in_transaction',fail)
    with pytest.raises(RuntimeError):actions.confirm(c,meetings.origin(c,users[0],combined_env[1]['id'],NOW),p['token'],NOW)
    for table in ('calendar_entry','calendar_outbox','room_reservation','room_notice'):
        assert not rows(c,'SELECT * FROM '+table)
    assert len(rows(c,'SELECT * FROM telegram_operation'))==1
    assert rows(c,'SELECT * FROM telegram_preview')[0]['state']=='pending'
    assert c.execute('SELECT count(*) FROM audit_log').fetchone()[0]==before


@pytest.mark.parametrize('scope',['rooms.read','rooms.request'])
def test_room_grant_revocation_scrubs_combined_but_preserves_calendar_only_preview(combined_env,scope):
    c,users,_,_,_=combined_env[0];p=prepare(combined_env)
    ctx=meetings.origin(c,users[0],combined_env[1]['id'],NOW)
    plain=actions.issue(c,ctx,'calendar.create','synthetic-calendar-only-key',FIELDS,NOW)
    c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),scope));c.commit()
    previews={r['operation_id']:r for r in rows(c,'SELECT * FROM telegram_preview')}
    assert previews[p['operation_id']]['state']=='cancelled' and previews[p['operation_id']]['fields_json'] is None
    assert previews[plain['operation_id']]['state']=='pending'
    with pytest.raises(ValueError):actions.confirm(c,ctx,p['token'],NOW)
    assert actions.confirm(c,ctx,plain['token'],NOW)['state']=='committed'
    assert not rows(c,'SELECT * FROM room_reservation')


@pytest.mark.parametrize('change',['rooms_read','rooms_request','slots','restore','expiry'])
def test_changed_authority_slots_restore_or_expiry_deny_before_calendar_write(combined_env,monkeypatch,change):
    c,users,path,_,_=combined_env[0];p=prepare(combined_env);ctx=meetings.origin(c,users[0],combined_env[1]['id'],NOW)
    when=NOW
    if change.startswith('rooms_'):monkeypatch.setenv('CSS_TELEGRAM_'+change.upper()+'_ENABLED','0')
    elif change=='slots':c.execute("UPDATE room_slot SET label='Changed hour' WHERE start_time='09:00'");c.commit()
    elif change=='restore':backups.clear_restored_sessions(path)
    else:when+=timedelta(seconds=301)
    with pytest.raises(ValueError):actions.confirm(c,ctx,p['token'],when)
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_unconsented_room_fields_and_known_conflict_cannot_prepare(meeting_env):
    with pytest.raises(ValueError):prepare(meeting_env)
    assert not rows(meeting_env[0][0],'SELECT * FROM telegram_preview')


def test_known_conflict_denies_new_preview_without_business_writes(combined_env):
    c=combined_env[0][0];block(c)
    with pytest.raises(ValueError):prepare(combined_env)
    assert not rows(c,'SELECT * FROM telegram_operation') and not rows(c,'SELECT * FROM calendar_entry')


def test_two_workers_create_one_meeting_and_one_child(combined_env):
    c,users,path,_,_=combined_env[0];p=prepare(combined_env);ctx=meetings.origin(c,users[0],combined_env[1]['id'],NOW)
    def run():
        other=st.connect(path)
        try:return actions.confirm(other,ctx,p['token'],NOW)
        finally:other.close()
    with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(lambda _:run(),range(2)))
    assert results[0]==results[1]
    assert len(rows(c,'SELECT * FROM calendar_entry'))==len(rows(c,'SELECT * FROM room_reservation'))==1
    assert len(combined.children(c,results[0]))==1


@pytest.mark.parametrize('lost_membership',[False,True])
def test_group_origin_binds_combined_child_and_keeps_all_details_private(registered,monkeypatch,lost_membership):
    import telegram_groups as groups
    c,users,_,client,payload=registered
    for flag in ('CALENDAR_READ','CALENDAR_CREATE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id'])
    for scope in ('calendar.read','calendar.create'):
        c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],users[4]['id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit();add_room_grants(c,users[4],monkeypatch);register(registered,topic=7)
    submit(client,group_update(10,topic=7,text='/meeting'))
    origin=rows(c,'SELECT * FROM telegram_meeting_origin')[0];ctx=meetings.origin(c,users[4],origin['id'],NOW)
    p=actions.issue(c,ctx,'calendar.create','synthetic-group-combined-key',{**FIELDS,'room':ROOM},NOW)
    if lost_membership:monkeypatch.setattr(bot.transport,'member_status',lambda *a:'left')
    submit(client,update(11,text='/meeting_confirm '+p['token']));bot.process_updates(c,NOW)
    assert len(rows(c,'SELECT * FROM calendar_entry'))==(0 if lost_membership else 1)
    assert len(rows(c,'SELECT * FROM room_reservation'))==(0 if lost_membership else 1)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0') and not rows(c,'SELECT * FROM telegram_group_share')
    if not lost_membership:
        child=rows(c,'SELECT * FROM telegram_operation WHERE parent_operation_id IS NOT NULL')[0]
        assert json.loads(child['context_json'])==ctx


def test_retry_parent_is_actor_and_source_bound_and_never_recreates_deleted_source(combined_env):
    c,users,_,_,_=combined_env[0];p=prepare(combined_env);block(c);parent=confirm(combined_env,p)
    with pytest.raises(ValueError):combined.retry_parent(c,users[1],parent['operation_id'])
    with pytest.raises(ValueError):combined.retry_parent(c,users[0],parent['operation_id'],999999)
    st.cal_delete(c,parent['result_entry_id'],by='fixture')
    with pytest.raises(ValueError):combined.retry_parent(c,users[0],parent['operation_id'])
    assert 'deleted' in meetings.ADAPTER.receipt_text(c,users[0],rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(p['operation_id'],))[0])
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_domain_failure_after_room_insert_rolls_back_only_child_records(combined_env,monkeypatch):
    c,users,_,_,_=combined_env[0];p=prepare(combined_env,people=[str(users[1]['id'])])
    monkeypatch.setattr(rooms_notify,'approver_accounts',lambda conn:[{'id':users[4]['id']}])
    def denied(*a,**kw):raise rooms.RoomError('Synthetic linking refusal')
    monkeypatch.setattr(rooms,'link_entry',denied)
    parent=confirm(combined_env,p)
    assert parent['state']=='partial' and len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert rows(c,'SELECT * FROM calendar_outbox')
    for table in ('room_reservation','room_reservation_slot','room_notice'):
        assert not rows(c,'SELECT * FROM '+table)
    assert not rows(c,"SELECT * FROM audit_log WHERE action LIKE 'room_%'")
    assert combined.children(c,parent)[0]['state']=='failed'


@pytest.mark.parametrize('change',['grant','switch'])
def test_room_authority_lost_during_child_rolls_back_entire_confirm(combined_env,monkeypatch,change):
    c,users,_,_,_=combined_env[0];p=prepare(combined_env);original=room_actions.request_in_transaction
    def lose(c,*a,**kw):
        record=original(c,*a,**kw)
        if change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='rooms.request'",(links.stamp(NOW),))
        else:monkeypatch.setenv('CSS_TELEGRAM_ROOMS_REQUEST_ENABLED','0')
        return record
    monkeypatch.setattr(room_actions,'request_in_transaction',lose)
    with pytest.raises(ValueError):actions.confirm(c,meetings.origin(c,users[0],combined_env[1]['id'],NOW),p['token'],NOW)
    assert not rows(c,'SELECT * FROM calendar_entry') and not rows(c,'SELECT * FROM room_reservation')
    assert not rows(c,'SELECT * FROM telegram_operation WHERE parent_operation_id IS NOT NULL')


def test_additive_parent_migration_preserves_old_preview_and_is_idempotent(combined_env):
    c,users,_,_,_=combined_env[0]
    ctx=meetings.origin(c,users[0],combined_env[1]['id'],NOW)
    old=actions.issue(c,ctx,'calendar.create','synthetic-old-calendar-key',FIELDS,NOW)
    c.execute('DROP INDEX telegram_operation_parent')
    c.execute('ALTER TABLE telegram_operation DROP COLUMN parent_operation_id');c.commit()
    st.init_db(c)
    assert 'parent_operation_id' in {r[1] for r in c.execute('PRAGMA table_info(telegram_operation)')}
    assert rows(c,'SELECT * FROM telegram_operation')[0]['parent_operation_id'] is None
    before=sorted(c.iterdump());st.init_db(c);assert sorted(c.iterdump())==before
    assert actions.confirm(c,ctx,old['token'],NOW)['state']=='committed'
    p=prepare(combined_env);parent=confirm(combined_env,p)
    assert combined.children(c,parent)[0]['parent_operation_id']==parent['operation_id']
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_restore_preserves_partial_parent_and_failed_child_without_reexecution(combined_env):
    c,users,path,_,_=combined_env[0];p=prepare(combined_env);block(c);parent=confirm(combined_env,p)
    child=combined.children(c,parent)[0]
    backups.clear_restored_sessions(path)
    assert rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(parent['operation_id'],))[0]['state']=='partial'
    assert rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(child['operation_id'],))[0]['state']=='failed'
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1 and not rows(c,'SELECT * FROM room_reservation')
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state IN ('queued','claimed','retry_wait')")
    with pytest.raises(ValueError):actions.recover(c,json.loads(parent['context_json']),'calendar.create',parent['operation_id'])


@pytest.mark.parametrize('change',['room_read','room_owner','source_access','room_delete'])
def test_receipt_fences_current_room_and_source_access_or_reports_deletion(combined_env,monkeypatch,change):
    c,users,_,client,_=combined_env[0];p=prepare(combined_env);parent=confirm(combined_env,p)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    submit(client,update(12,text='/meeting_receipt '+p['operation_id']));bot.process_updates(c,NOW)
    if change=='room_read':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='rooms.read'",(links.stamp(NOW),))
    elif change=='room_owner':c.execute('UPDATE room_reservation SET requester_user_id=? WHERE id=?',(users[1]['id'],parent['result_room_id']))
    elif change=='source_access':
        c.execute("UPDATE calendar_entry SET audience='people',created_by='another' WHERE id=?",(parent['result_entry_id'],))
    else:
        c.execute('DELETE FROM room_reservation_slot WHERE reservation_id=?',(parent['result_room_id'],))
        c.execute('DELETE FROM room_reservation WHERE id=?',(parent['result_room_id'],))
    c.commit()
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',8,None))
    bot.deliver(c,NOW)
    if change=='room_delete':
        # Deletion cancels the queued receipt; explicit later recovery gives the deletion truth.
        submit(client,update(13,text='/meeting_receipt '+p['operation_id']));bot.process_updates(c,NOW);bot.deliver(c,NOW+timedelta(seconds=2))
        assert messages and 'deleted' in messages[-1][2] and 'pending approval' not in messages[-1][2]
    else:assert not messages


@pytest.mark.parametrize('room',[None,{}, {'from_time':'10:00','to_time':'09:00'}, {'from_time':'09:30','to_time':'10:00'}, {**ROOM,'requester_user_id':999}])
def test_optional_room_shape_and_hours_are_explicit_and_self_only(combined_env,room):
    with pytest.raises(ValueError):prepare(combined_env,room=room)
    assert not rows(combined_env[0][0],'SELECT * FROM telegram_preview')
