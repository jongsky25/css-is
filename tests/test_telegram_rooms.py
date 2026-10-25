"""Own-only room status and source-accurate slot lookup, no provider I/O."""
from datetime import date,timedelta
import json
import re
import auth

import pytest

import backups
from documents_storage import rows,transaction
import rooms
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_rooms as reads
from tests.test_work import workspace
from tests.test_telegram_bot import setup,update,submit,NOW
from tests.test_telegram_links import linking,activate

DAY=date(2026,10,26)


@pytest.fixture
def room_env(linking,monkeypatch):
    c,users,path,client,payload=linking
    monkeypatch.setenv('CSS_TELEGRAM_ROOMS_READ_ENABLED','1')
    activate(linking)
    rooms.ensure_slots(c)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    return c,users,path,client,payload


def request(env,user=0,slot=0,title='Synthetic private title',day=DAY,**extra):
    c,users,_,_,_=env
    return rooms.request(c,title=title,day=day,slot_ids=[rooms.list_slots(c)[slot]['id']],
        requester_user_id=users[user]['id'],today=date(2026,10,20),purpose='Private purpose',**extra)


def lookup(env,text='/room_slots 2026-10-26',number=10):
    c,_,_,client,_=env
    assert submit(client,update(number,text=text)).status_code==200
    bot.process_updates(c,NOW)
    result=rows(c,"SELECT * FROM telegram_delivery WHERE state='queued' ORDER BY id DESC LIMIT 1")
    return result[0] if result else None


def render(env,text='/room_slots 2026-10-26',number=10):
    c,_,_,_,_=env
    delivery=lookup(env,text,number)
    return reads.render(c,delivery,json.loads(delivery['projection_json']),bot.transport.config(),NOW)


def test_slot_states_match_source_and_other_staff_data_is_absent(room_env,monkeypatch):
    c,_,_,_,_=room_env
    pending=request(room_env,user=1,slot=0,title='Another staff private title')
    booked=request(room_env,user=1,slot=1)
    rooms.approve(c,booked['id'],'fixture',today=date(2026,10,20))
    blocked=rooms.list_slots(c)[2]['id']
    c.execute("INSERT INTO room_block(day,slot_id,reason,created_by,created_at) VALUES (?,?,?,'fixture',?)",(DAY.isoformat(),blocked,'Private closure reason',links.stamp(NOW)));c.commit()
    text=render(room_env)
    expected=rooms.day_view(c,DAY,today=NOW.astimezone(reads.common.ZONE).date())
    for slot in expected['hours']:
        assert slot['label']+': '+slot['state'] in text
    assert all(state in text for state in ('free','requested','booked','closed'))
    for secret in (pending['ref_code'],'Another staff private title','Private purpose','Private closure reason'):
        assert secret not in text
    assert 'does not hold a booking' in text
    assert '/rooms?week=2026-10-26&day=2026-10-26' in text


@pytest.mark.parametrize('kind',['weekend','holiday','past','horizon'])
def test_closed_days_follow_holiday_weekend_and_horizon_rules(room_env,kind):
    c,_,_,_,_=room_env
    today=NOW.astimezone(reads.common.ZONE).date()
    day={'weekend':date(2026,10,25),'holiday':DAY,'past':date(2026,10,23),
         'horizon':today+timedelta(days=rooms.MAX_DAYS_AHEAD+1)}[kind]
    if kind=='horizon':
        while day.weekday()>=5:
            day+=timedelta(days=1)
    if kind=='holiday':
        st.set_holiday(c,day.isoformat(),'Synthetic public holiday')
    text=render(room_env,'/room_slots '+day.isoformat())
    source=rooms.day_view(c,day,today=today)
    assert source['closed'] in text
    assert all(hour['state']=='closed' for hour in source['hours'])
    assert 'free' not in text
    if kind=='horizon':
        assert 'days ahead' in text


def test_own_reference_status_updates_are_fresh_and_notes_stay_private(room_env):
    c,_,_,_,_=room_env
    item=request(room_env)
    delivery=lookup(room_env,'/room_status '+item['ref_code'])
    assert item['ref_code'] in delivery['projection_json']
    assert 'Synthetic private title' not in delivery['projection_json']
    rooms.approve(c,item['id'],'fixture',note='Private decision explanation',today=date(2026,10,20))
    text=reads.render(c,delivery,json.loads(delivery['projection_json']),bot.transport.config(),NOW)
    assert 'approved (booked)' in text and item['ref_code'] in text
    assert 'Private decision' not in text and 'Private purpose' not in text and 'Synthetic private title' not in text
    assert '/rooms/mine' in text


def test_another_users_reference_and_nonexistent_reference_have_same_denial(room_env):
    item=request(room_env,user=1)
    denied=render(room_env,'/room_status '+item['ref_code'])
    unknown=render(room_env,'/room_status CR-1900-9999',number=11)
    assert denied==unknown and 'unavailable to this account' in denied
    assert item['ref_code'] not in denied


def test_pending_standby_and_terminal_own_status_labels(room_env):
    c,_,_,_,_=room_env
    item=request(room_env)
    assert 'awaiting approval; no booking held' in render(room_env,'/room_status '+item['ref_code'])
    c.execute('UPDATE room_reservation SET standby=1 WHERE id=?',(item['id'],));c.commit()
    assert 'standby; no booking held' in render(room_env,'/room_status '+item['ref_code'],11)
    for i,status in enumerate(('declined','withdrawn','cancelled','expired'),12):
        c.execute('UPDATE room_reservation SET status=? WHERE id=?',(status,item['id']));c.commit()
        assert status in render(room_env,'/room_status '+item['ref_code'],i)


def test_own_list_is_bounded_and_date_filtered(room_env):
    c,users,_,_,_=room_env
    for i in range(12):
        request(room_env,title='Private content '+str(i))
    other=request(room_env,user=1)
    text=render(room_env,'/my_rooms 2026-10-26 2026-10-26')
    assert len(set(re.findall(r'CR-[0-9]{4}-[0-9]{4}',text)))==10
    assert 'More requests' in text and other['ref_code'] not in text
    assert 'Private content' not in text
    assert len(rooms.list_for_user(c,users[0]['id'],start=DAY,end=DAY,limit=11))==11
    assert len(rooms.list_for_user(c,users[0]['id']))==12  # Existing UI default remains unchanged.
    assert reads.common.units(text)<=4096
    assert 'No requests' in render(room_env,'/my_rooms 2026-10-27 2026-10-27',11)


@pytest.mark.parametrize('text',['/room_slots yesterday','/room_slots 2026-02-30','/my_rooms 2026-10-26 2026-10-01',
    '/my_rooms 2026-10-01 2026-11-01','/room_status private-user','/room_status'])
def test_invalid_queries_never_read_source_records(room_env,monkeypatch,text):
    monkeypatch.setattr(rooms,'day_view',lambda *a,**k:pytest.fail('Invalid slot read'))
    monkeypatch.setattr(rooms,'get_by_ref',lambda *a,**k:pytest.fail('Invalid reference read'))
    monkeypatch.setattr(rooms,'list_for_user',lambda *a,**k:pytest.fail('Invalid list read'))
    assert render(room_env,text)==reads.USAGE


@pytest.mark.parametrize('change',['feature','grant','disconnect','deactivate','restore'])
def test_revoke_after_queue_blocks_next_source_read_and_send(room_env,monkeypatch,change):
    c,users,path,_,payload=room_env
    lookup(room_env)
    if change=='feature':
        monkeypatch.setenv('CSS_TELEGRAM_ROOMS_READ_ENABLED','0')
    elif change=='grant':
        c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='rooms.read'",(links.stamp(NOW),));c.commit()
    elif change=='disconnect':
        links.disconnect(c,payload,NOW)
    elif change=='deactivate':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    else:
        backups.clear_restored_sessions(path)
    monkeypatch.setattr(rooms,'day_view',lambda *a,**k:pytest.fail('Revoked slot read'))
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Revoked send'))
    assert bot.deliver(c,NOW)==0


def test_room_consent_is_independent_calendar_cannot_grant_room_access(room_env,monkeypatch):
    c,_,_,_,_=room_env
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
    assert 'conference-room slots' in render(room_env)
    c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='rooms.read'",(links.stamp(NOW),));c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    before=len(rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'"))
    lookup(room_env,number=11)
    assert len(rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'"))==before
    assert rows(c,'SELECT * FROM telegram_update WHERE update_id=11')[0]['state']=='ignored'
    assert bot.eligible(c,rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")[0],bot.transport.config(),NOW) is False


def test_dedup_restart_group_denial_and_no_mutation(room_env,monkeypatch):
    c,_,path,client,_=room_env
    before=c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]
    lookup(room_env)
    submit(client,update(10,text='/room_slots 2026-10-26'))
    from tests.test_telegram_groups import group_update
    submit(client,group_update(11,text='/room_slots 2026-10-26'))
    assert len(rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'"))==1
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *args:calls.append(args) or ('accepted',12,None))
    restarted=st.connect(path)
    try:
        assert bot.deliver(restarted,NOW)==1
        assert bot.deliver(restarted,NOW)==0
    finally:
        restarted.close()
    assert len(calls)==1 and calls[0][1]==101
    assert c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]==before
    assert not rows(c,'SELECT * FROM telegram_operation')


def test_timezone_and_final_boundary_disconnect(room_env,monkeypatch):
    c,_,_,_,payload=room_env
    assert reads.parse('/room_slots',NOW.replace(hour=16))['day']=='2026-10-26'
    lookup(room_env)
    original=reads.render
    def disconnect_after_read(*args):
        text=original(*args);links.disconnect(c,payload,NOW);return text
    monkeypatch.setattr(reads,'render',disconnect_after_read)
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Send after disconnect'))
    assert bot.deliver(c,NOW)==0


def test_admin_still_cannot_read_another_persons_request(room_env):
    c,users,_,_,_=room_env
    item=request(room_env,user=1)
    payload=auth.parse_token(auth.make_token(users[4]));st.register_login_session(c,payload);c.commit()
    with transaction(c):
        links.start(c,202,bot.transport.config(),NOW)
    ch=rows(c,'SELECT * FROM telegram_link_challenge WHERE telegram_user_id=202')[0]
    links.claim(c,payload,links.code(ch,'claim'),['rooms.read'],NOW)
    with transaction(c):
        cid,generation=links.confirm(c,202,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW)
    delivery={'connection_id':cid,'generation':generation,'chat_id':202,'topic_id':None,'registration_id':None}
    projection={'kind':'rooms','bot':bot.transport.config()[0],'fingerprint':bot.transport.config()[2],
                'query':{'mode':'status','reference':item['ref_code']}}
    text=reads.render(c,delivery,projection,bot.transport.config(),NOW)
    assert text=='Room request unavailable to this account.\n\nOpen my requests: https://office.example/rooms/mine'


def test_reassigned_request_is_not_disclosed_after_enqueue(room_env):
    c,users,_,_,_=room_env
    item=request(room_env)
    delivery=lookup(room_env,'/room_status '+item['ref_code'])
    c.execute('UPDATE room_reservation SET requester_user_id=? WHERE id=?',(users[1]['id'],item['id']));c.commit()
    text=reads.render(c,delivery,json.loads(delivery['projection_json']),bot.transport.config(),NOW)
    assert 'unavailable to this account' in text and item['ref_code'] not in text


def test_signed_in_room_instructions_follow_current_consent_and_switch(room_env,monkeypatch):
    import app
    from starlette.testclient import TestClient
    c,users,path,_,_=room_env
    monkeypatch.setattr(app,'DB',path)
    token=auth.make_token(users[0]);st.register_login_session(c,auth.parse_token(token));c.commit()
    client=TestClient(app.app,base_url='https://office.example');client.cookies.set(auth.COOKIE_NAME,token)
    try:
        response=client.get('/account/telegram')
        assert response.status_code==200 and '<code>/room_slots YYYY-MM-DD</code>' in response.text
        monkeypatch.setenv('CSS_TELEGRAM_ROOMS_READ_ENABLED','0')
        response=client.get('/account/telegram')
        assert 'Private room lookup requires its optional pilot' in response.text
        assert '<code>/room_slots YYYY-MM-DD</code>' not in response.text
    finally:
        client.close()
