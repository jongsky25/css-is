"""Owner-only personal status reads, pure source projections and independent scopes."""
from datetime import date

import pytest
import auth

import storage as st
import travel
import meals
import rooms
import rooms_meals
import telegram_bot as bot
import telegram_links as links
import telegram_personal as reads
from tests.test_work import workspace
from tests.test_telegram_bot import setup,update,submit,NOW
from tests.test_telegram_links import linking,claimed


@pytest.fixture(params=['travel','meals','arrangements'])
def personal_env(linking,monkeypatch,request):
    c,users,path,client,_=linking
    c.execute("UPDATE admin_user SET role='admin' WHERE id=?",(users[0]['id'],));c.commit()
    users[0]=st.get_admin_user_by_id(c,users[0]['id'])
    payload=auth.parse_token(auth.make_token(users[0]));st.register_login_session(c,payload);c.commit()
    linking=(c,users,path,client,payload)
    kind=request.param
    adapter={'travel':reads.TRAVEL,'meals':reads.MEALS,'arrangements':reads.ARRANGEMENTS}[kind]
    monkeypatch.setenv('CSS_TELEGRAM_'+kind.upper()+'_READ_ENABLED','1')
    _,_,code=claimed(linking,scopes=[adapter.scope])
    submit(client,update(2,text='/confirm '+code));bot.process_updates(c,NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing provider call'))
    return linking,adapter


def seed(env,owner=0):
    linking,adapter=env;c,users,*_=linking
    if adapter.kind=='travel':
        return travel.create_filing(c,users[owner],kind='reimbursement',
            source={'source_kind':'blank','title':'Synthetic travel activity','start':'2026-10-17','end':'2026-10-18','venue':'DoNotExposeVenue'},
            answers={},role='participant',dpo_no='DoNotExposeDPO',today=date(2026,10,20))['id']
    if adapter.kind=='meals':
        return meals.create(c,users[owner],title='DoNotExposeMealTitle',day='2026-10-26',venue='DoNotExposeVenue',
            pax=3,special_request='DoNotExposeDietaryReason',wanted=['lunch'],times={'lunch':'12:00'},today=date(2026,10,20))['id']
    c.execute("UPDATE work_arrangement SET status='cancelled' WHERE user_id=? AND status='pending'",(users[owner]['id'],));c.commit()
    return st.create_work_arrangement(c,users[owner]['id'],'2026-11-01','REG',note='DoNotExposeArrangementReason')


def command(env,text=None,number=10):
    linking,adapter=env
    response=submit(linking[3],update(number,text=text or adapter.COMMANDS[0]))
    assert response.status_code==200
    return response.json()


def test_current_owned_metadata_has_source_link_and_no_sensitive_fields(personal_env):
    linking,adapter=personal_env;c,*_=linking
    rid=seed(personal_env)
    tables=('travel_filing','travel_item','meal_request','meal_request_item','work_arrangement')
    before={table:list(c.execute('SELECT * FROM '+table)) for table in tables}
    text=command(personal_env)['text']
    assert str(rid) in text and 'https://office.example/' in text
    detail=command(personal_env,adapter.COMMANDS[1]+' '+str(rid),11)['text']
    assert 'DoNotExpose' not in text+detail
    assert reads.common.units(text)<=4096 and reads.common.units(detail)<=4096
    assert {table:list(c.execute('SELECT * FROM '+table)) for table in tables}==before
    assert all('DoNotExpose' not in (r[0] or '') for r in c.execute('SELECT projection_json FROM telegram_delivery'))
    if adapter.kind=='travel':
        assert 'Checklist/workflow items needing attention:' in detail and 'Paper review:' in detail
        assert 'Submitted' not in detail
    elif adapter.kind=='meals':assert 'Awaiting order' in detail
    else:assert 'Filing status: pending' in detail and 'schedule in force' in detail


def test_admin_cannot_read_other_owners_record_and_paging_is_owner_bound(personal_env):
    linking,adapter=personal_env
    own=[seed(personal_env) for _ in range(7)]
    other=[seed(personal_env,3) for _ in range(7)]
    text=command(personal_env)['text']
    assert 'Next page:' in text
    next_command=text.split('Next page: ')[1].splitlines()[0]
    second=command(personal_env,next_command,11)['text']
    assert 'Next page:' not in second
    denied=command(personal_env,adapter.COMMANDS[1]+' '+str(other[0]),12)['text']
    assert denied==command(personal_env,adapter.COMMANDS[1]+' 999999',13)['text']
    assert denied=='Record unavailable to this account.'


@pytest.mark.parametrize('change',['flag','grant','disconnect','inactive'])
def test_revocation_blocks_personal_source_reads(personal_env,monkeypatch,change):
    linking,adapter=personal_env;c,users,_,_,payload=linking
    seed(personal_env)
    if change=='flag':monkeypatch.setenv('CSS_TELEGRAM_'+adapter.kind.upper()+'_READ_ENABLED','0')
    elif change=='grant':c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),adapter.scope));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    else:c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    assert 'method' not in command(personal_env)


def test_scope_isolation_and_module_independence(personal_env):
    linking,adapter=personal_env;c,*_=linking
    seed(personal_env)
    for module in ('documents','work','supplies'):st.set_setting(c,module+'.enabled','0')
    assert 'method' in command(personal_env)
    c.execute("UPDATE telegram_grant SET action='calendar.read'");c.commit()
    assert 'method' not in command(personal_env,number=11)


def test_invalid_arguments_and_private_only_duplicate_rules(personal_env,monkeypatch):
    linking,adapter=personal_env
    assert command(personal_env,adapter.COMMANDS[0]+' -1')['text']==adapter.usage()
    assert command(personal_env,adapter.COMMANDS[1]+' nope',11)['text']==adapter.usage()
    message=update(12,text=adapter.COMMANDS[0]);message['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(linking[3],message).json()
    assert 'method' in command(personal_env,number=13)
    assert 'method' not in command(personal_env,number=13)
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    assert 'method' not in command(personal_env,number=14)


def test_final_reply_fence_rechecks_grant(personal_env,monkeypatch):
    linking,adapter=personal_env
    seed(personal_env)
    original=adapter.render
    def revoked(*args):
        text=original(*args)
        args[0].execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),adapter.scope))
        return text
    monkeypatch.setattr(adapter,'render',revoked)
    assert 'method' not in command(personal_env)


@pytest.mark.parametrize('personal_env',['travel'],indirect=True)
def test_travel_module_pause_and_purge_are_respected(personal_env):
    linking,adapter=personal_env;c,*_=linking
    rid=seed(personal_env)
    c.execute("UPDATE travel_filing SET purged_at='2026-10-25' WHERE id=?",(rid,));c.commit()
    assert 'No records' in command(personal_env)['text']
    assert 'unavailable' in command(personal_env,'/travel_status '+str(rid),11)['text']
    st.set_setting(c,'travel.enabled','0')
    assert 'method' not in command(personal_env,number=12)


@pytest.mark.parametrize('personal_env',['meals'],indirect=True)
def test_room_linked_meals_uses_wanted_source_states(personal_env):
    linking,adapter=personal_env;c,users,*_=linking
    rooms.ensure_slots(c)
    slot=rooms.list_slots(c)[0]['id']
    reservation=rooms.request(c,title='DoNotExposeRoomTitle',day=date(2026,10,26),slot_ids=[slot],
                              requester_user_id=users[0]['id'],today=date(2026,10,20))
    rid=reservation['id']
    rooms_meals.ensure_form(c,rid,by='fixture',today=date(2026,10,20))
    rooms_meals.save_form(c,rid,'fixture',pax=3,special_request='DoNotExposeSpecial',wanted=['lunch'],
                         times={'lunch':'12:00'},today=date(2026,10,20))
    text=command(personal_env,'/room_meal_status '+str(rid))['text']
    assert 'Lunch: Not yet requested' in text and '/rooms/meals/'+str(rid) in text
    assert 'DoNotExpose' not in text
    c.execute("UPDATE room_meal_item SET status='delivered' WHERE reservation_id=? AND meal='lunch'",(rid,));c.commit()
    assert 'Lunch: Delivered' in command(personal_env,'/my_room_meals',11)['text']


def test_status_reads_reflect_current_source_state(personal_env):
    linking,adapter=personal_env;c,*_=linking
    rid=seed(personal_env)
    if adapter.kind=='travel':
        c.execute("UPDATE travel_filing SET review_state='changes' WHERE id=?",(rid,));c.commit()
        filing=travel.get_filing(c,rid)
        text=command(personal_env,'/travel_status '+str(rid))['text']
        assert 'Changes needed' in text
        assert 'items needing attention: '+str(len(travel.missing_for(c,filing))) in text
    elif adapter.kind=='meals':
        c.execute("UPDATE meal_request_item SET status='delivered',status_note='DoNotExposeReviewNote' WHERE request_id=?",(rid,));c.commit()
        text=command(personal_env,'/meal_status '+str(rid))['text']
        assert 'Delivered' in text and 'DoNotExpose' not in text
    else:
        c.execute("UPDATE work_arrangement SET status='denied',decide_note='DoNotExposeReviewNote' WHERE id=?",(rid,));c.commit()
        text=command(personal_env,'/arrangement_status '+str(rid))['text']
        assert 'Filing status: denied' in text and 'DoNotExpose' not in text
