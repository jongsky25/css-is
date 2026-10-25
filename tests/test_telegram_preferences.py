"""Own-channel choices, quiet delivery, email coordination and current-session saves."""
from datetime import datetime,timedelta,timezone
import json

import pytest

import auth
import backups
from documents_storage import rows,transaction
import office_calendar as calendar
import rooms
import rooms_notify
import storage as st
import telegram_bot as bot
import telegram_changes as changes
import telegram_links as links
import telegram_notices as notices
import telegram_preferences as prefs
from tests.test_work import workspace
from tests.test_telegram_bot import setup,NOW,submit,update
from tests.test_telegram_links import linking
from tests.test_telegram_changes import routed,drain,add_grant
from tests.test_telegram_groups import registered,register


def session(c,user):
    payload=auth.parse_token(auth.make_token(user));st.register_login_session(c,payload);c.commit();return payload


def save(c,user,payload,at=NOW,**change):
    p=prefs.get(c,user['id']);values={k:p[k] for k in ('calendar_mode','room_mode')}
    values.update({k:bool(p[k]) for k in ('group_calendar','group_room')})
    values.update(quiet_start=p['quiet_start'] or '',quiet_end=p['quiet_end'] or '');values.update(change)
    prefs.save(c,payload,p['revision'],int(p['calendar_email']),values,at)


def deliveries(c):return rows(c,"SELECT * FROM telegram_delivery WHERE projection_json LIKE '%change_notice%' ORDER BY id")


def stage(c):drain(c);notices.enqueue(c,NOW)


@pytest.mark.parametrize('start,end,at,expected',[
    ('22:00','07:00','2026-10-25T13:59:59+00:00',None),
    ('22:00','07:00','2026-10-25T14:00:00+00:00','2026-10-25T23:00:00+00:00'),
    ('22:00','07:00','2026-10-25T22:59:59+00:00','2026-10-25T23:00:00+00:00'),
    ('22:00','07:00','2026-10-25T23:00:00+00:00',None),
    ('12:00','13:00','2026-10-25T04:00:00+00:00','2026-10-25T05:00:00+00:00'),
    ('12:00','13:00','2026-10-25T05:00:00+00:00',None),
    ('22:00','07:00','2026-10-25T23:30:00','2026-10-25T23:00:00+00:00'),
])
def test_manila_quiet_boundaries_include_start_exclude_end_and_cross_midnight(start,end,at,expected):
    result=prefs.quiet_until({'quiet_start':start,'quiet_end':end},datetime.fromisoformat(at))
    assert (result.isoformat() if result else None)==expected


def test_defaults_preserve_existing_calendar_email_and_other_channels(workspace):
    c,users,_,_=workspace;p=prefs.get(c,users[0]['id'])
    assert p['calendar_mode']==p['room_mode']=='both' and p['revision']==0 and not p['quiet_start']
    st.set_calendar_email_pref(c,users[0]['id'],False)
    assert prefs.get(c,users[0]['id'])['calendar_mode']=='telegram'
    assert not rows(c,'SELECT * FROM telegram_notification_preference')


@pytest.mark.parametrize('bad',[{'quiet_start':'22:00'},{'quiet_start':'22:00','quiet_end':'22:00'},
    {'quiet_start':'25:00','quiet_end':'07:00'},{'calendar_mode':'other'},{'group_room':1}])
def test_invalid_preferences_never_change_email_or_store_a_row(workspace,bad):
    c,users,_,_=workspace;payload=session(c,users[0])
    with pytest.raises(ValueError):save(c,users[0],payload,**bad)
    assert st.calendar_email_pref(c,users[0]['id']) and not rows(c,'SELECT * FROM telegram_notification_preference')


def test_stale_pref_and_shared_profile_email_changes_conflict_atomically(workspace):
    c,users,_,_=workspace;payload=session(c,users[0]);p=prefs.get(c,users[0]['id'])
    values={'calendar_mode':'telegram','room_mode':'email','group_calendar':False,'group_room':True,'quiet_start':'','quiet_end':''}
    st.set_calendar_email_pref(c,users[0]['id'],False)
    with pytest.raises(prefs.Conflict):prefs.save(c,payload,p['revision'],1,values,NOW)
    assert not rows(c,'SELECT * FROM telegram_notification_preference')
    prefs.save(c,payload,0,0,values,NOW)
    with pytest.raises(prefs.Conflict):prefs.save(c,payload,0,0,values,NOW)
    assert prefs.get(c,users[0]['id'])['room_mode']=='email'
    assert prefs.get(c,users[1]['id'])['room_mode']=='both'


def test_notice_quiet_deferral_does_not_attempt_and_manual_lookup_stays_immediate(routed,monkeypatch):
    linking,eid=routed;c,users,_,client,payload=linking
    save(c,users[0],payload,quiet_start='07:00',quiet_end='09:00')
    stage(c);d=deliveries(c)[0]
    assert d['not_before']==links.stamp(NOW+timedelta(hours=1)) and not d['attempts']
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',3,None))
    assert bot.deliver(c,NOW)==0 and not calls
    submit(client,update(30,text='/calendar 2026-10-26'));bot.process_updates(c,NOW)
    assert bot.deliver(c,NOW)==1 and 'Synthetic private source' in calls[-1][2]
    assert deliveries(c)[0]['attempts']==0
    assert bot.deliver(c,NOW+timedelta(hours=1))==1 and 'Calendar update' in calls[-1][2]
    assert deliveries(c)[0]['state']=='accepted'


def test_quiet_change_after_enqueue_holds_and_clearing_releases_without_erasing_429(routed,monkeypatch):
    linking,eid=routed;c,users,_,_,payload=linking;stage(c)
    save(c,users[0],payload,quiet_start='07:00',quiet_end='09:00')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Quiet notice sent'))
    assert bot.deliver(c,NOW)==0 and deliveries(c)[0]['attempts']==0
    save(c,users[0],payload,quiet_start='',quiet_end='')
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('retry_wait',None,120))
    assert bot.deliver(c,NOW)==1
    deadline=deliveries(c)[0]['retry_at']
    save(c,users[0],payload,quiet_start='07:00',quiet_end='09:00')
    assert bot.deliver(c,NOW+timedelta(minutes=3))==0
    assert deliveries(c)[0]['retry_at']==deadline and deliveries(c)[0]['attempts']==1
    save(c,users[0],payload,quiet_start='',quiet_end='')
    assert deliveries(c)[0]['retry_at']==deadline
    assert bot.deliver(c,NOW+timedelta(seconds=30))==0
    assert bot.deliver(c,NOW+timedelta(minutes=4))==1
    assert len(calls)==2


def test_optout_cancels_pending_and_inflight_claim_then_reenable_does_not_replay(routed,monkeypatch):
    linking,eid=routed;c,users,_,_,payload=linking;stage(c)
    def send(*a):
        save(c,users[0],payload,calendar_mode='email')
        return 'accepted',7,None
    monkeypatch.setattr(bot.transport,'send',send)
    assert bot.deliver(c,NOW)==1 and deliveries(c)[0]['state']=='uncertain'
    save(c,users[0],payload,calendar_mode='both')
    assert notices.enqueue(c,NOW)==0 and bot.deliver(c,NOW+timedelta(seconds=2))==0
    calendar_entry=st.cal_get(c,eid);assert calendar_entry and len(rows(c,'SELECT * FROM calendar_entry'))==1


def test_preference_edit_after_render_blocks_http_and_failed_audit_rolls_back(routed,monkeypatch):
    linking,eid=routed;c,users,_,_,payload=linking;stage(c);render=notices.render
    def changed(*args):
        text=render(*args);save(c,users[0],payload,calendar_mode='email');return text
    monkeypatch.setattr(notices,'render',changed)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Preference changed after render'))
    assert bot.deliver(c,NOW)==0 and deliveries(c)[0]['state']=='uncertain'
    before=prefs.get(c,users[0]['id'])
    monkeypatch.setattr(st,'audit',lambda *a,**kw:(_ for _ in ()).throw(ValueError('Synthetic audit failure')))
    with pytest.raises(ValueError):save(c,users[0],payload,calendar_mode='off',room_mode='off')
    assert prefs.get(c,users[0]['id'])==before


def test_email_choices_and_quiet_hours_coordinate_calendar_and_own_room_status(workspace,monkeypatch):
    import tzutil as tz
    c,users,_,_=workspace;user=users[0];payload=session(c,user)
    local=tz.now_local().replace(hour=22,minute=30,second=0,microsecond=0);day=(local.date()+timedelta(days=1)).isoformat()
    save(c,user,payload,quiet_start='22:00',quiet_end='07:00')
    st.cal_create(c,'Synthetic email choice',day,people=[user['id']],audience='bureau',by='another')
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True)
    sent=[];send=lambda *a,**kw:sent.append(a) or {'sent':True,'detail':'synthetic'}
    assert calendar.flush_outbox(c,'https://office.example',now=local,send=send)==0 and not sent
    assert c.execute('SELECT SUM(attempts) FROM calendar_outbox').fetchone()[0]==0
    assert calendar.flush_outbox(c,'https://office.example',now=local+timedelta(hours=9),send=send)==1
    slots=rooms.list_slots(c);record=rooms.request(c,title='Synthetic room email',day=day,slot_ids=[slots[2]['id']],requester_user_id=user['id'],today=local.date())
    rooms.approve(c,record['id'],'another',today=local.date())
    before=len(sent);rooms_notify.flush(c,'https://office.example',now=local,send=send)
    assert len(sent)==before
    save(c,user,payload,calendar_mode='telegram',room_mode='telegram',quiet_start='',quiet_end='')
    rooms_notify.flush(c,'https://office.example',now=local+timedelta(hours=9),send=send)
    assert len(sent)==before
    assert rows(c,"SELECT email_status FROM room_notice WHERE user_id=? AND kind='approved'",(user['id'],))[0]['email_status']=='skipped_off'
    assert not st.calendar_email_pref(c,user['id'])


def test_restore_and_relink_preserve_choices_without_reviving_quiet_queued_notice(routed):
    linking,eid=routed;c,users,path,_,payload=linking
    save(c,users[0],payload,room_mode='email',quiet_start='07:00',quiet_end='09:00');stage(c)
    before=prefs.get(c,users[0]['id']);backups.clear_restored_sessions(path)
    assert prefs.get(c,users[0]['id'])==before
    assert deliveries(c)[0]['state']=='cancelled'
    assert not changes.authorize_route(c,1,NOW)


def test_owned_group_control_does_not_apply_another_users_preferences(registered,monkeypatch):
    from tests.test_telegram_notices import group_source
    from tests.test_telegram_groups import group_update
    c,users,_,client,payload=registered;eid,group=group_source(registered,monkeypatch)
    other=session(c,users[0]);save(c,users[0],other,group_calendar=False)
    group_delivery=next(d for d in deliveries(c) if d['chat_id']<0)
    assert group_delivery['state']=='queued'
    save(c,users[4],payload,group_calendar=False)
    assert next(d for d in deliveries(c) if d['chat_id']<0)['state']=='cancelled'
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',3,None))
    bot.deliver(c,NOW)
    assert all(a[1]>0 for a in calls)
    submit(client,group_update(30,topic=7,text='/group_calendar 2026-10-26'));bot.process_updates(c,NOW)
    bot.deliver(c,NOW+timedelta(seconds=2))
    assert any(a[1]==-100 and a[3]==7 and 'Shared schedule' in a[2] for a in calls)


def test_owned_group_uses_owners_quiet_hours_before_provider_proof(registered,monkeypatch):
    from tests.test_telegram_notices import group_source
    c,users,_,_,payload=registered;eid,group=group_source(registered,monkeypatch)
    save(c,users[4],payload,quiet_start='07:00',quiet_end='09:00')
    monkeypatch.setattr(bot.transport,'member_status',lambda *a:pytest.fail('Quiet group proof'))
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Quiet group send'))
    assert bot.deliver(c,NOW)==0
    assert all(d['attempts']==0 and d['not_before'] for d in deliveries(c))


def test_preferences_save_requires_current_session_and_preserves_restore_settings(workspace):
    c,users,_,_=workspace;payload=session(c,users[0])
    save(c,users[0],payload,calendar_mode='email',room_mode='off')
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    with pytest.raises(ValueError):save(c,users[0],payload,calendar_mode='both')
    assert prefs.get(c,users[0]['id'])['room_mode']=='off'


def test_deferred_source_expiry_and_permission_loss_do_not_send_after_quiet(routed,monkeypatch):
    linking,eid=routed;c,users,_,_,payload=linking
    save(c,users[0],payload,quiet_start='07:00',quiet_end='09:00');stage(c)
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Revoked quiet notice'))
    assert bot.deliver(c,NOW+timedelta(hours=1))==0 and deliveries(c)[0]['state']=='cancelled'


def test_email_optout_during_build_is_rechecked_before_provider(workspace,monkeypatch):
    import mailer
    import tzutil as tz
    c,users,_,_=workspace;user=users[0];payload=session(c,user);at=tz.now_local()+timedelta(minutes=15)
    day=(at.date()+timedelta(days=1)).isoformat()
    monkeypatch.setattr(st,'email_feature_enabled',lambda *a:True)
    st.cal_create(c,'Synthetic final email fence',day,people=[user['id']],audience='bureau',by='another')
    original=mailer.calendar_changes_message
    def calendar_body(*args,**kw):
        body=original(*args,**kw);save(c,user,payload,calendar_mode='telegram');return body
    monkeypatch.setattr(mailer,'calendar_changes_message',calendar_body)
    send=lambda *a,**kw:pytest.fail('Preference changed before email I/O')
    assert calendar.flush_outbox(c,'https://office.example',now=at,send=send)==0
    assert c.execute('SELECT result FROM calendar_outbox').fetchone()[0]=='skipped'
    monkeypatch.setattr(rooms_notify,'approver_accounts',lambda *a:[])
    record=rooms.request(c,title='Synthetic final room fence',day=day,slot_ids=[rooms.list_slots(c)[2]['id']],requester_user_id=user['id'],today=at.date())
    rooms.approve(c,record['id'],'another',today=at.date())
    build=rooms_notify._build
    def room_body(*args,**kw):
        body=build(*args,**kw);save(c,user,payload,room_mode='telegram');return body
    monkeypatch.setattr(rooms_notify,'_build',room_body)
    rooms_notify.flush(c,'https://office.example',now=at,send=send)
    assert rows(c,"SELECT email_status FROM room_notice WHERE kind='approved'")[0]['email_status']=='skipped_off'
