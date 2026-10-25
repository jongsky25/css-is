"""Committed UI/service changes and dormant routing; no provider send or action replay."""
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
from tests.test_work import workspace
from tests.test_telegram_bot import setup,NOW
from tests.test_telegram_links import linking,activate
from tests.test_telegram_groups import registered,register


def events(c,entity=None,identifier=None):
    sql='SELECT * FROM telegram_change_event WHERE 1=1';args=[]
    if entity:sql+=' AND entity=?';args.append(entity)
    if identifier is not None:sql+=' AND source_id=?';args.append(identifier)
    return rows(c,sql+' ORDER BY sequence',args)


def last(c,entity,identifier):return events(c,entity,identifier)[-1]


def add_grant(c,connection,scope):
    c.execute('''INSERT OR IGNORE INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
        VALUES (?,?,?,?,?,?,?)''',(connection['id'],connection['account_id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()


@pytest.fixture
def routed(linking,monkeypatch):
    activate(linking)
    c,users,_,_,_=linking
    for flag in ('CALENDAR_READ','ROOMS_READ','CHANGE_NOTICES'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=rows(c,"SELECT * FROM telegram_connection WHERE state='active'")[0]
    for scope in ('calendar.read','rooms.read'):add_grant(c,connection,scope)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    eid=st.cal_create(c,'Synthetic private source','2026-10-26',audience='people',people=[users[1]['id']],by=users[0]['username'],start_time='09:00',end_time='10:00')
    return linking,eid


def drain(c):
    for _ in range(100):
        if not rows(c,"SELECT 1 FROM telegram_change_event WHERE state='pending'"):return
        changes.prepare_routes(c,NOW)
    raise AssertionError('bounded drain did not finish')


def test_capture_metadata_same_writer_rollback_and_idempotent_import(workspace):
    c,users,_,path=workspace
    assert not events(c)
    try:
        with transaction(c):
            eid=st.cal_create(c,'Synthetic rollback body','2026-10-26',by=users[0]['username'],audience='bureau',commit=False)
            assert last(c,'calendar',eid)['kind']=='calendar.insert'
            other=st.connect(path)
            try:assert not events(other)
            finally:other.close()
            raise ValueError('Synthetic rollback')
    except ValueError:pass
    assert not events(c) and not rows(c,'SELECT * FROM telegram_change_head')
    eid=st.cal_create(c,'Synthetic body never persisted here','2026-10-26',audience='bureau',source='import',import_key='synthetic-import')
    before=events(c);assert st.cal_create(c,'Ignored duplicate','2026-10-26',import_key='synthetic-import')==eid
    assert events(c)==before
    raw=str(events(c))+str(rows(c,'SELECT * FROM telegram_change_head'))
    assert 'Synthetic body' not in raw and 'Ignored duplicate' not in raw
    with pytest.raises(Exception):c.execute("UPDATE telegram_change_event SET kind='changed'")
    c.rollback()


def test_calendar_people_tags_units_and_seen_noise_capture(workspace):
    c,users,_,_=workspace
    eid=st.cal_create(c,'Synthetic','2026-10-26',audience='bureau',people=[users[0]['id']])
    before=len(events(c));st.cal_mark_seen(c,users[0]['id'],[eid]);st.cal_mark_css_nudged(c,eid)
    assert len(events(c))==before
    seq=st.cal_get(c,eid)['sequence']
    st.cal_update(c,eid,title='Renamed')
    assert st.cal_get(c,eid)['sequence']==seq and last(c,'calendar',eid)['revision']>1
    before=len(events(c));st.cal_update(c,eid,title='Renamed');assert len(events(c))==before
    st.cal_add_people(c,eid,[users[1]['id']],by='fixture')
    assert len(events(c))>before
    st.cal_update(c,eid,tags=['Synthetic tag'])
    assert last(c,'calendar',eid)['kind']=='calendar.details'
    st.cal_cancel(c,eid);assert last(c,'calendar',eid)['kind']=='calendar.update'
    st.cal_restore(c,eid,force=True)
    assert last(c,'calendar',eid)['kind']=='calendar.update'
    old=last(c,'calendar',eid);st.cal_delete(c,eid)
    assert last(c,'calendar',eid)['kind']=='calendar.delete'
    new=st.cal_create(c,'Reused number','2026-10-26',audience='bureau')
    assert new==eid and last(c,'calendar',new)['incarnation']!=old['incarnation']
    assert not changes.current(c,old,NOW)


def test_room_request_hours_link_decision_move_expiry_and_savepoint_rollback(workspace):
    import rooms_notify
    c,users,_,_=workspace;slots=rooms.list_slots(c)
    eid=st.cal_create(c,'Synthetic source','2026-10-26',audience='bureau',by=users[0]['username'])
    record=rooms.request(c,title='Synthetic own request',day='2026-10-26',slot_ids=[slots[2]['id']],requester_user_id=users[0]['id'],today=date(2026,10,20))
    rid=record['id'];assert last(c,'room',rid)['kind']=='room.details'
    rooms.link_entry(c,rid,eid,users[0]);assert last(c,'room',rid)['kind']=='room.update'
    rooms.request_move(c,rid,'2026-10-27',users[0],today=date(2026,10,20))
    assert last(c,'room',rid)['kind']=='room.details'
    before=last(c,'room',rid)['revision'];rooms.approve(c,rid,'fixture',today=date(2026,10,20))
    assert last(c,'room',rid)['revision']>before
    with transaction(c):
        c.execute('SAVEPOINT synthetic')
        rooms.request(c,title='Synthetic child rollback',day='2026-10-28',slot_ids=[slots[2]['id']],requester_user_id=users[0]['id'],today=date(2026,10,20),commit=False)
        c.execute('ROLLBACK TO synthetic');c.execute('RELEASE synthetic')
    assert len({e['source_id'] for e in events(c,'room')})==1
    assert all('Synthetic own request' not in str(e) for e in events(c))
    rooms.request(c,title='Synthetic expiry',day='2026-10-26',slot_ids=[slots[3]['id']],requester_user_id=users[0]['id'],today=date(2026,10,20))
    rooms_notify.expire_past_requests(c,today=date(2026,10,28))
    assert any(r['status']=='expired' for r in rows(c,'SELECT * FROM room_reservation'))


def test_private_routes_current_parties_only_and_replay_never_writes(routed):
    linking,eid=routed;c,users,_,_,_=linking
    before=rows(c,'SELECT * FROM calendar_entry');event=last(c,'calendar',eid)
    drain(c);routes=rows(c,'SELECT * FROM telegram_change_route')
    assert len(routes)==1 and routes[0]['projection']=='calendar_private' and routes[0]['chat_id']==101
    assert changes.authorize_route(c,routes[0]['id'],NOW)
    assert changes.verify_route(c,routes[0]['id'],NOW)
    for _ in range(3):assert changes.prepare_routes(c,NOW)==0
    assert rows(c,'SELECT * FROM calendar_entry')==before
    assert len(rows(c,'SELECT * FROM telegram_change_route'))==1
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    assert not rows(c,'SELECT * FROM telegram_operation')
    assert 'Synthetic private source' not in str(routes) and not {'text','body','title','token'}&set(routes[0])


@pytest.mark.parametrize('change',['read','link','inactive','source','source_delete','flag','bot','restore','expiry'])
def test_route_revocation_source_and_restore_fences(routed,monkeypatch,change):
    linking,eid=routed;c,users,path,_,payload=linking;drain(c)
    route=rows(c,'SELECT * FROM telegram_change_route')[0];when=NOW
    if change=='read':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    elif change=='link':links.disconnect(c,payload,NOW)
    elif change=='inactive':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='source':st.cal_update(c,eid,title='Synthetic changed')
    elif change=='source_delete':st.cal_delete(c,eid)
    elif change=='flag':monkeypatch.setenv('CSS_TELEGRAM_CHANGE_NOTICES_ENABLED','0')
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    elif change=='restore':backups.clear_restored_sessions(path)
    else:when+=timedelta(days=2)
    assert not changes.authorize_route(c,route['id'],when)
    assert not changes.verify_route(c,route['id'],when)
    if change in ('read','link','inactive','source','source_delete','restore'):
        assert rows(c,'SELECT state FROM telegram_change_route WHERE id=?',(route['id'],))[0]['state']=='cancelled'


def test_unrelated_bureau_viewer_and_room_admin_do_not_receive_broadcasts(routed):
    linking,eid=routed;c,users,_,_,_=linking
    c.execute("UPDATE calendar_entry SET created_by='another',audience='bureau' WHERE id=?",(eid,));c.commit()
    slots=rooms.list_slots(c)
    rooms.request(c,title='Another private request',day='2026-10-26',slot_ids=[slots[2]['id']],requester_user_id=users[1]['id'],today=date(2026,10,20))
    drain(c);assert not rows(c,'SELECT * FROM telegram_change_route')


def test_restart_and_two_workers_prepare_one_route_without_business_replay(routed):
    linking,eid=routed;c,_,path,_,_=linking
    def run():
        other=st.connect(path)
        try:changes.prepare_routes(other,NOW)
        finally:other.close()
    with ThreadPoolExecutor(max_workers=2) as workers:list(workers.map(lambda _:run(),range(2)))
    assert len(rows(c,'SELECT * FROM telegram_change_route'))==1
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert not rows(c,'SELECT * FROM telegram_operation')


def test_route_insert_failure_rolls_back_cursor_and_restart_retries(routed,monkeypatch):
    c=routed[0][0];original=changes._insert
    def fail(*args,**kw):original(*args,**kw);raise ValueError('Synthetic staging failure')
    monkeypatch.setattr(changes,'_insert',fail)
    with pytest.raises(ValueError):changes.prepare_routes(c,NOW)
    assert not rows(c,'SELECT * FROM telegram_change_route')
    assert rows(c,'SELECT * FROM telegram_change_event')[0]['private_after']==0
    monkeypatch.setattr(changes,'_insert',original);drain(c)
    assert len(rows(c,'SELECT * FROM telegram_change_route'))==1


def test_group_exact_share_and_fresh_membership_recheck(registered,monkeypatch):
    c,users,_,_,payload=registered
    for flag in ('CALENDAR_READ','CHANGE_NOTICES'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id']);add_grant(c,connection,'calendar.read')
    group=register(registered,topic=7)
    eid=st.cal_create(c,'Synthetic shared source','2026-10-26',audience='bureau',by=users[4]['username'])
    drain(c);assert not rows(c,'SELECT * FROM telegram_change_route WHERE chat_id<0')
    # New exact source consent permits current-version routing, never old content.
    entry=st.cal_get(c,eid);shared.consent(c,payload,group['id'],group['generation'],eid,shared.revision(entry),True,NOW)
    st.cal_add_people(c,eid,[users[1]['id']])
    assert rows(c,'SELECT revoked_at FROM telegram_group_share')[0]['revoked_at']
    entry=st.cal_get(c,eid);shared.consent(c,payload,group['id'],group['generation'],eid,shared.revision(entry),True,NOW)
    drain(c);route=rows(c,'SELECT * FROM telegram_change_route WHERE chat_id<0')[0]
    assert route['topic_id']==7 and route['projection']=='calendar_shared'
    assert changes.verify_route(c,route['id'],NOW)
    monkeypatch.setattr(bot.transport,'member_status',lambda *a:'left')
    assert not changes.verify_route(c,route['id'],NOW)
    assert not changes.authorize_route(c,route['id'],NOW)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE chat_id<0")


def test_bounded_pagination_and_route_migration_preserve_restart_state(routed,monkeypatch):
    from tests.test_telegram_groups import bind
    linking,eid=routed;c,users,_,_,_=linking
    bind(c,users[1],102);add_grant(c,groups.linked(c,users[1]['id']),'calendar.read')
    monkeypatch.setattr(changes,'BATCH',1)
    assert changes.prepare_routes(c,NOW)==1
    event=last(c,'calendar',eid)
    assert event['state']=='pending' and event['private_after']>0 and not event['private_done']
    assert changes.prepare_routes(c,NOW)==1
    assert len(rows(c,'SELECT * FROM telegram_change_route'))==2
    assert last(c,'calendar',eid)['state']=='routed'
    assert changes.prepare_routes(c,NOW)==0
    before=sorted(c.iterdump());st.init_db(c);st.init_db(c);assert sorted(c.iterdump())==before
    assert not c.execute('PRAGMA foreign_key_check').fetchall()


def test_room_owner_route_and_group_availability_use_original_context_only(registered,monkeypatch):
    from tests.test_telegram_room_requests import prepare,confirm
    from tests.test_telegram_bot import submit
    from tests.test_telegram_groups import group_update
    import telegram_meetings as meetings
    import telegram_actions as actions
    c,users,_,client,_=registered
    for flag in ('CALENDAR_READ','ROOMS_READ','ROOMS_REQUEST','CHANGE_NOTICES'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id'])
    for scope in ('calendar.read','rooms.read','rooms.request'):add_grant(c,connection,scope)
    group=register(registered,topic=7);register(registered,number=2,topic=8)
    eid=st.cal_create(c,'Synthetic confidential meeting','2026-10-26',audience='bureau',by=users[4]['username'])
    submit(client,group_update(10,topic=7,text='/room_request'))
    origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request'")[0]
    ctx=meetings.origin(c,users[4],origin['id'],NOW,'rooms.request')
    p=actions.issue(c,ctx,'rooms.request','synthetic-room-notice-source',{'entry_id':eid,'from_time':'09:00','to_time':'10:00'},NOW)
    result=actions.confirm(c,ctx,p['token'],NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    drain(c)
    routes=rows(c,'SELECT * FROM telegram_change_route')
    private=next(r for r in routes if r['projection']=='room_private')
    group_route=next(r for r in routes if r['projection']=='room_availability')
    assert private['chat_id']==101 and group_route['chat_id']==-100 and group_route['topic_id']==7
    assert not any(r['topic_id']==8 for r in routes)
    assert changes.verify_route(c,group_route['id'],NOW)
    assert 'Synthetic confidential' not in str(routes) and 'CR-' not in str(routes)
    rooms.approve(c,result['result_room_id'],'fixture',today=date(2026,10,20));drain(c)
    assert not changes.authorize_route(c,private['id'],NOW)
    assert len(rows(c,"SELECT * FROM telegram_change_route WHERE projection='room_private' AND state='prepared'"))==1
    c.execute('UPDATE room_reservation SET requester_user_id=? WHERE id=?',(users[1]['id'],result['result_room_id']));c.commit()
    assert not changes.authorize_route(c,group_route['id'],NOW)
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")


def test_group_share_revocation_and_topic_generation_immediately_cancel_routes(registered,monkeypatch):
    c,users,_,_,payload=registered
    for flag in ('CALENDAR_READ','CHANGE_NOTICES'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    add_grant(c,groups.linked(c,users[4]['id']),'calendar.read');group=register(registered,topic=7)
    eid=st.cal_create(c,'Synthetic shared source','2026-10-26',audience='bureau',by=users[4]['username'])
    entry=st.cal_get(c,eid);shared.consent(c,payload,group['id'],group['generation'],eid,shared.revision(entry),True,NOW)
    drain(c);route=rows(c,'SELECT * FROM telegram_change_route WHERE chat_id<0')[0]
    shared.consent(c,payload,group['id'],group['generation'],eid,'',False,NOW)
    assert not changes.authorize_route(c,route['id'],NOW)
    assert rows(c,'SELECT state FROM telegram_change_route WHERE id=?',(route['id'],))[0]['state']=='cancelled'
    # New source version/consent creates a new event, then group pause fences that route.
    st.cal_update(c,eid,venue='Synthetic hall');entry=st.cal_get(c,eid)
    shared.consent(c,payload,group['id'],group['generation'],eid,shared.revision(entry),True,NOW)
    drain(c);route=rows(c,"SELECT * FROM telegram_change_route WHERE chat_id<0 AND state='prepared'")[0]
    groups.manage(c,payload,group['id'],group['generation'],'pause')
    assert not changes.authorize_route(c,route['id'],NOW)
    assert rows(c,'SELECT state FROM telegram_change_route WHERE id=?',(route['id'],))[0]['state']=='cancelled'


def test_expiry_retention_restore_epoch_and_no_backfill(workspace):
    c,users,_,path=workspace
    eid=st.cal_create(c,'Synthetic existing','2026-10-26',audience='bureau')
    # Simulate installation on an earlier database: remove only this feature.
    for name, in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'telegram_change_%'").fetchall():
        c.execute('DROP TRIGGER '+name)
    for table in ('telegram_change_route','telegram_change_event','telegram_change_head'):c.execute('DROP TABLE '+table)
    c.commit();st.init_db(c)
    assert not events(c) and st.cal_get(c,eid)
    st.cal_update(c,eid,venue='Synthetic change')
    event=last(c,'calendar',eid);epoch=event['epoch']
    backups.clear_restored_sessions(path)
    assert st.get_setting(c,changes.EPOCH_KEY)!=epoch
    assert not changes.current(c,event,NOW)
    st.cal_update(c,eid,venue='Synthetic after restore')
    assert last(c,'calendar',eid)['epoch']!=epoch
    with transaction(c):changes.cleanup_in_transaction(c,NOW+timedelta(days=200))
    assert not events(c) and rows(c,'SELECT * FROM telegram_change_head')


def test_overlay_activity_and_config_capture_without_body_snapshots(workspace):
    c,users,_,_=workspace
    # Owned parent tables can also be changed by existing activity/config writers.
    c.execute("INSERT INTO event(event_token,title,event_date) VALUES ('synthetic-token','Synthetic activity','2026-10-26')");activity=c.execute('SELECT last_insert_rowid()').fetchone()[0];c.commit()
    eid=st.cal_create(c,'Synthetic overlay','2026-10-26',audience='bureau',event_id=activity)
    c.execute('UPDATE event SET venue=? WHERE id=?',('Synthetic hidden venue',activity));c.commit()
    assert last(c,'calendar',eid)['kind']=='calendar.activity'
    c.execute("INSERT INTO calendar_entry_doc(entry_id,doc_key,needed) VALUES (?, 'dpo',1)",(eid,));c.commit()
    assert last(c,'calendar',eid)['kind']=='calendar.details'
    slots=rooms.list_slots(c);c.execute('UPDATE room_slot SET label=? WHERE id=?',('Synthetic label',slots[0]['id']));c.commit()
    assert events(c,'availability')
    assert all('Synthetic hidden venue' not in str(e) for e in events(c))


def test_real_signed_in_calendar_form_and_approval_writes_capture_events(manager,app_mod):
    from urllib.parse import urlencode
    from conftest import in_the_directory
    c=st.connect(app_mod.DB)
    try:
        slots=rooms.list_slots(c)
        values={'title':'Synthetic UI change event','kind':'meeting','status':'confirmed','start_date':'2026-10-26','audience':'bureau',
                'reserve_room':'1','room_from':slots[2]['id'],'room_to':slots[2]['id']}
        response=manager.post('/calendar/new',content=urlencode(values),headers={'Content-Type':'application/x-www-form-urlencoded'},follow_redirects=False)
        assert response.status_code==303
        eid=int(response.headers['location'].split('/calendar/entries/')[1].split('?')[0])
        assert events(c,'calendar',eid)
        rid=c.execute('SELECT id FROM room_reservation WHERE calendar_entry_id=?',(eid,)).fetchone()[0]
        assert events(c,'room',rid)
        with in_the_directory(app_mod,'admin@test.local',path='ADMINFX/ADMIN'):
            rooms.approve(c,rid,'fixture',today=date(2026,10,20))
        assert last(c,'room',rid)['kind']=='room.update'
        assert not rows(c,'SELECT * FROM telegram_change_route')
        assert not rows(c,'SELECT * FROM telegram_delivery')
    finally:c.close()


def test_feature_off_scheduler_still_cleans_metadata_without_network(app_mod,monkeypatch):
    c=st.connect(app_mod.DB)
    try:
        st.cal_create(c,'Synthetic cleanup source','2026-10-26',audience='bureau')
        assert events(c)
        for capability in bot.storage.SWITCHES:monkeypatch.setenv('CSS_TELEGRAM_'+capability.upper()+'_ENABLED','0')
        monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(days=200))
        monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Disabled provider send'))
        monkeypatch.setattr(bot.transport,'member_status',lambda *a:pytest.fail('Disabled provider read'))
        assert app_mod._telegram_tick()==(0,0)
        assert not events(c)
        assert rows(c,'SELECT * FROM calendar_entry')
    finally:c.close()


@pytest.mark.parametrize('change',['elapsed_expiry','source_during_proof'])
def test_group_final_check_counts_elapsed_time_and_source_change(registered,monkeypatch,change):
    from datetime import datetime
    c,users,_,_,payload=registered
    for flag in ('CALENDAR_READ','CHANGE_NOTICES'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    add_grant(c,groups.linked(c,users[4]['id']),'calendar.read');group=register(registered,topic=7)
    eid=st.cal_create(c,'Synthetic proof source','2026-10-26',audience='bureau',by=users[4]['username'])
    entry=st.cal_get(c,eid);shared.consent(c,payload,group['id'],group['generation'],eid,shared.revision(entry),True,NOW)
    drain(c);route=rows(c,'SELECT * FROM telegram_change_route WHERE chat_id<0')[0]
    event=last(c,'calendar',eid);when=NOW
    elapsed=[0.0];monkeypatch.setattr(changes.time,'monotonic',lambda:elapsed[0])
    if change=='elapsed_expiry':when=datetime.fromisoformat(event['recorded_at'])+changes.TTL-timedelta(seconds=1)
    def proof(*args):
        assert not c.in_transaction
        elapsed[0]+=3
        if change=='source_during_proof':st.cal_update(c,eid,venue='Synthetic changed during proof')
        return 'administrator'
    monkeypatch.setattr(bot.transport,'member_status',proof)
    assert not changes.verify_route(c,route['id'],when)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')


def test_cancelled_destination_metadata_expires_before_event_identity(routed):
    linking,eid=routed;c,_,_,_,payload=linking;drain(c)
    event=last(c,'calendar',eid);links.disconnect(c,payload,NOW)
    with transaction(c):changes.cleanup_in_transaction(c,NOW+timedelta(days=31))
    assert not rows(c,'SELECT * FROM telegram_change_route')
    assert rows(c,'SELECT * FROM telegram_change_event WHERE event_key=?',(event['event_key'],))
    assert changes.prepare_routes(c,NOW+timedelta(days=31))==0
