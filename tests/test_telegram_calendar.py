"""Private lookup parity, current visibility, bounded paging and safe delivery."""
from datetime import date, timedelta
import json
import re

import pytest

import auth
import backups
from documents_storage import rows,transaction
import office_calendar as oc
import rooms
import storage as st
import telegram_bot as bot
import telegram_calendar as reads
import telegram_links as links
from tests.test_work import workspace
from tests.test_telegram_bot import setup,update,submit,NOW
from tests.test_telegram_links import linking,activate
from tests.test_calendar_scope import world, add


@pytest.fixture
def calendar_env(linking,monkeypatch):
    c,users,path,client,payload=linking
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    activate(linking)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    return c,users,path,client,payload


def lookup(calendar_env,number=10,text='/calendar 2026-10-25 2026-10-31 bureau'):
    c,_,_,client,_=calendar_env
    assert submit(client,update(number,text=text)).status_code==200
    bot.process_updates(c,NOW)
    return rows(c,"SELECT * FROM telegram_delivery WHERE state='queued' ORDER BY id DESC LIMIT 1")


def populate(c,*,count=1,day='2026-10-26',prefix='Private meeting',**fields):
    return [st.cal_create(c,f'{prefix} {i}',day,audience='bureau',by='fixture',start_time='09:00',end_time='10:00',**fields) for i in range(count)]


def test_end_to_end_private_projection_and_no_saved_business_content(calendar_env,monkeypatch):
    c,_,_,_,_=calendar_env
    ids=populate(c,note='Confidential note',meeting_url='https://meeting.secret.example',venue='Office')
    delivery=lookup(calendar_env)[0]
    assert 'Private meeting' not in delivery['projection_json']
    assert 'Confidential' not in delivery['projection_json']
    messages=[]
    monkeypatch.setattr(bot.transport,'send',lambda *args:messages.append(args) or ('accepted',77,None))
    assert bot.deliver(c,NOW)==1
    text=messages[0][2]
    assert messages[0][1]==101 and 'Private meeting 0' in text
    assert 'Asia/Manila' in text and '09:00–10:00' in text
    assert f'https://office.example/calendar/entries/{ids[0]}' in text
    assert 'Confidential note' not in text and 'meeting.secret' not in text
    assert not rows(c,"SELECT * FROM telegram_operation")
    assert 'Private meeting' not in rows(c,'SELECT * FROM telegram_delivery ORDER BY id DESC LIMIT 1')[0]['projection_json']


@pytest.mark.parametrize('text',['/calendar 2026-02-30 2026-03-01','/calendar 2026-10-31 2026-10-01',
    '/calendar 2026-10-01 2026-11-01','/calendar yesterday tomorrow','/calendar 2026-10-01 2026-10-02 all',
    '/calendar_next forged-token'])
def test_invalid_input_is_neutral_and_does_not_query_records(calendar_env,monkeypatch,text):
    c,_,_,_,_=calendar_env
    monkeypatch.setattr(oc,'items_between',lambda *args,**kwargs:pytest.fail('Invalid calendar read'))
    lookup(calendar_env,text=text)
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *args:sent.append(args) or ('accepted',1,None))
    assert bot.deliver(c,NOW)==1
    assert sent[0][2]==reads.USAGE


def test_empty_window_timezone_boundaries_and_inclusive_limits(calendar_env):
    c,_,_,_,_=calendar_env
    query=reads.parse('/calendar',NOW.replace(hour=16))
    assert query['start']=='2026-10-26' and query['end']=='2026-11-01'
    assert reads.parse('/calendar 2026-10-01 2026-10-31',NOW)['end']=='2026-10-31'
    delivery=lookup(calendar_env)[0]
    text=reads.render(c,delivery,json.loads(delivery['projection_json']),bot.transport.config(),NOW)
    assert 'No calendar items' in text and 'https://office.example/calendar?day=2026-10-25' in text


@pytest.mark.parametrize('change',['feature','consent','disconnect','deactivate','restore'])
def test_revocation_or_disabled_feature_blocks_next_read_and_send(calendar_env,monkeypatch,change):
    c,users,path,_,payload=calendar_env
    populate(c);lookup(calendar_env)
    if change=='feature':
        monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
    elif change=='consent':
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=\'calendar.read\'',(links.stamp(NOW),));c.commit()
    elif change=='disconnect':
        links.disconnect(c,payload,NOW)
    elif change=='deactivate':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    else:
        backups.clear_restored_sessions(path)
    monkeypatch.setattr(oc,'items_between',lambda *args,**kwargs:pytest.fail('Revoked source read'))
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Revoked private send'))
    assert bot.deliver(c,NOW)==0


def test_permissions_are_recomputed_after_enqueue(calendar_env,monkeypatch):
    c,users,_,_,_=calendar_env
    eid=st.cal_create(c,'Restricted after enqueue','2026-10-26',audience='bureau',by=users[1]['username'])
    lookup(calendar_env)
    st.cal_update(c,eid,audience='people',people=[(users[1]['id'],'attending')],by=users[1]['username'])
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *args:sent.append(args) or ('accepted',1,None))
    assert bot.deliver(c,NOW)==1
    assert 'Restricted after enqueue' not in sent[0][2] and 'No calendar items' in sent[0][2]


def test_paging_is_current_actor_bound_expiring_and_detects_visible_changes(calendar_env):
    c,users,_,_,_=calendar_env
    ids=populate(c,count=15)
    delivery=lookup(calendar_env)[0];projection=json.loads(delivery['projection_json'])
    with transaction(c):
        first=reads.page(c,delivery,projection['query'],bot.transport.config(),NOW)
    assert 1<=len(first['items'])<=10 and first['next_token']
    query=reads.parse('/calendar_next '+first['next_token'],NOW)
    with transaction(c):
        second=reads.page(c,delivery,query,bot.transport.config(),NOW)
    assert not {x['key'] for x in first['items']} & {x['key'] for x in second['items']}
    with pytest.raises(ValueError):
        reads.parse('/calendar_next '+first['next_token'],NOW+timedelta(minutes=10))
    with pytest.raises(ValueError):
        reads.parse('/calendar_next '+first['next_token'][:-1]+'0',NOW) if first['next_token'][-1]!='0' else reads.parse('/calendar_next '+first['next_token'][:-1]+'1',NOW)
    # A different active linked actor cannot use another account's cursor.
    other=bind_read(c,users[1],102)
    with transaction(c),pytest.raises(reads.Unavailable):
        reads.page(c,other,query,bot.transport.config(),NOW)
    st.cal_update(c,ids[0],title='Changed visible title',by='fixture')
    with transaction(c),pytest.raises(reads.Unavailable,match='changed'):
        reads.page(c,delivery,query,bot.transport.config(),NOW)


def bind_read(c,user,sender):
    payload=auth.parse_token(auth.make_token(user));st.register_login_session(c,payload);c.commit()
    with transaction(c):
        links.start(c,sender,bot.transport.config(),NOW)
    ch=rows(c,'SELECT * FROM telegram_link_challenge WHERE telegram_user_id=? ORDER BY rowid DESC LIMIT 1',(sender,))[0]
    links.claim(c,payload,links.code(ch,'claim'),['calendar.read'],NOW)
    with transaction(c):
        cid,generation=links.confirm(c,sender,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW)
    return {'connection_id':cid,'generation':generation,'chat_id':sender,'topic_id':None,'registration_id':None}


@pytest.mark.parametrize('role',['viewer','encoder','section_manager','admin'])
def test_calendar_visibility_matches_screen_for_all_roles(world,monkeypatch,role):
    c=world['conn']
    for flag in ('LINK','CALENDAR_READ'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    from tests.test_telegram_bot import TOKEN,SECRET
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setenv('CSS_BASE_URL','https://office.example')
    add(world,'Bureau item',audience='bureau');add(world,'Section item',owner='T/D1/S1')
    add(world,'Private people',audience='people',people=[world['s1']])
    for number,key in enumerate(('unlinked','s1','d1chief','director')):
        user={**world[key],'role':role}
        c.execute('UPDATE admin_user SET role=? WHERE id=?',(role,user['id']));c.commit()
        delivery=bind_read(c,user,200+number)
        query={'start':'2026-10-01','end':'2026-10-31','scope':'bureau','cursor':None}
        expected=oc.items_between(c,user,query['start'],query['end'],scope='bureau',layers=reads.LAYERS)
        with transaction(c):
            result=reads.page(c,delivery,query,bot.transport.config(),NOW)
        assert {i['key'] for i in result['items']}=={i['key'] for i in expected}
        if key=='unlinked':
            assert [i['title'] for i in result['items']]==['Bureau item']  # Admin alone buys no scope.


def test_recurrence_room_pending_unicode_budget_and_excluded_layers(calendar_env):
    c,users,_,_,_=calendar_env
    populate(c,count=12,prefix='😀'*120,note='Hidden note',meeting_url='https://secret.example',venue='😀'*80)
    rooms.ensure_slots(c)
    slot=rooms.list_slots(c)[0]['id']
    rooms.request(c,title='Own pending room',day=date(2026,10,26),slot_ids=[slot],requester_user_id=users[0]['id'],today=date(2026,10,20))
    st.cal_create(c,'Weekly meeting','2026-10-26',audience='bureau',by='fixture',rrule='FREQ=WEEKLY;BYDAY=MO;UNTIL=20261130')
    delivery=lookup(calendar_env)[0]
    with transaction(c):
        page=reads.page(c,delivery,json.loads(delivery['projection_json'])['query'],bot.transport.config(),NOW)
    assert reads.units(page['text'])<=4096
    assert page['next_token'] and len(page['items'])<10
    assert reads.LAYERS==('entries','holidays','rooms')
    visible=oc.items_between(c,users[0],'2026-10-25','2026-10-31',scope='bureau',layers=reads.LAYERS)
    own=next(i for i in visible if i['title']=='Own pending room')
    assert reads.project(own,links.origin())['status']=='requested (not booked)'


def test_duplicate_restart_and_group_requests_never_send_private_data(calendar_env,monkeypatch):
    c,_,path,client,_=calendar_env
    populate(c);lookup(calendar_env)
    assert submit(client,update(10,text='/calendar 2026-10-25 2026-10-31 bureau')).status_code==200
    assert c.execute("SELECT count(*) FROM telegram_delivery WHERE state='queued'").fetchone()[0]==1
    from tests.test_telegram_groups import group_update
    submit(client,group_update(11,text='/calendar 2026-10-25 2026-10-31 bureau'))
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *args:sent.append(args) or ('accepted',1,None))
    restarted=st.connect(path)
    try:
        assert bot.deliver(restarted,NOW)==1
        assert bot.deliver(restarted,NOW)==0
    finally:
        restarted.close()
    assert len(sent)==1 and sent[0][1]==101


def test_disconnect_between_render_and_provider_call_suppresses_message(calendar_env,monkeypatch):
    c,_,_,_,payload=calendar_env
    populate(c);lookup(calendar_env)
    render=reads.render
    def disconnect_after_read(*args):
        text=render(*args)
        links.disconnect(c,payload,NOW)
        return text
    monkeypatch.setattr(reads,'render',disconnect_after_read)
    monkeypatch.setattr(bot.transport,'send',lambda *args:pytest.fail('Send after completed disconnect'))
    assert bot.deliver(c,NOW)==0


def test_holiday_all_day_recurring_occurrence_links_and_visible_capacity(calendar_env,monkeypatch):
    c,_,_,_,_=calendar_env
    st.set_holiday(c,'2026-10-26','Synthetic office holiday')
    eid=st.cal_create(c,'Repeated office entry','2026-10-26',audience='bureau',by='fixture',
                      rrule='FREQ=WEEKLY;BYDAY=MO;UNTIL=20261130')
    delivery=lookup(calendar_env)[0];query=json.loads(delivery['projection_json'])['query']
    with transaction(c):
        result=reads.page(c,delivery,query,bot.transport.config(),NOW)
    assert 'Synthetic office holiday' in result['text'] and 'All day' in result['text']
    assert f'/calendar/entries/{eid}?date=2026-10-26' in result['text']
    monkeypatch.setattr(reads,'MAX_ITEMS',1)
    with transaction(c),pytest.raises(reads.Unavailable,match='Too many'):
        reads.page(c,delivery,query,bot.transport.config(),NOW)


def test_signed_in_page_explains_current_calendar_availability(calendar_env,monkeypatch):
    import app
    from starlette.testclient import TestClient
    c,users,path,_,_=calendar_env
    monkeypatch.setattr(app,'DB',path)
    token=auth.make_token(users[0]);st.register_login_session(c,auth.parse_token(token));c.commit()
    client=TestClient(app.app,base_url='https://office.example')
    client.cookies.set(auth.COOKIE_NAME,token)
    try:
        page=client.get('/account/telegram')
        assert page.status_code==200 and 'send <code>/calendar</code>' in page.text
        monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
        page=client.get('/account/telegram')
        assert 'Private calendar lookup requires its optional pilot' in page.text
        assert 'send <code>/calendar</code>' not in page.text
    finally:
        client.close()
