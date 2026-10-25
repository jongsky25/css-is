"""Explicit group disclosure, current grants and source-change fences."""
from datetime import date,timedelta
import json

import pytest

import auth
import backups
from documents_storage import rows,transaction
import rooms
import storage as st
import telegram_bot as bot
import telegram_groups as groups
import telegram_group_reads as reads
import telegram_links as links
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,NOW
from tests.test_telegram_groups import registered,register,group_update,bind


@pytest.fixture
def shared_env(registered,monkeypatch):
    c,users,path,client,payload=registered
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_ROOMS_READ_ENABLED','1')
    group=register(registered,topic=7)
    connection=groups.linked(c,users[4]['id'])
    for action in ('calendar.read','rooms.read'):
        c.execute('''INSERT INTO telegram_grant (connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],connection['account_id'],action,connection['generation'],
              bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit()
    return registered,group


def entry(env,title='Shared synthetic meeting',**kw):
    c=env[0][0]
    eid=st.cal_create(c,title,'2026-10-26',audience=kw.pop('audience','bureau'),by='fixture',
                         start_time='09:00',end_time='10:00',venue='Shared venue',**kw)
    return st.cal_get(c,eid)


def share(env,item):
    registered,group=env;c,users,_,_,payload=registered
    source=reads.shareable(c,users[4],item['id'])
    reads.consent(c,payload,group['id'],group['generation'],item['id'],reads.revision(source),True,NOW)


def queue(env,text='/group_calendar 2026-10-26',number=10,topic=7,sender=101):
    registered,group=env;c,_,_,client,_=registered
    submit(client,group_update(number,topic=topic,sender=sender,text=text));bot.process_updates(c,NOW)
    found=rows(c,"SELECT * FROM telegram_delivery WHERE chat_id<0 AND state='queued' ORDER BY id DESC LIMIT 1")
    return found[0] if found else None


def render(env,**kw):
    d=queue(env,**kw)
    return reads.render(env[0][0],d,json.loads(d['projection_json']),bot.transport.config(),NOW)


def test_only_explicit_exact_destination_shared_fields(shared_env,monkeypatch):
    registered,group=shared_env;c,_,_,client,_=registered
    item=entry(shared_env,note='Private notes',meeting_url='https://private.example/meeting')
    entry(shared_env,title='Unshared bureau title')
    entry(shared_env,title='Private people title',audience='people')
    share(shared_env,item)
    text=render(shared_env)
    assert all(value in text for value in ('Shared synthetic meeting','2026-10-26','09:00','Shared venue','Asia/Manila','/calendar/entries/'+str(item['id'])))
    assert all(value not in text for value in ('Private notes','private.example','Unshared bureau title','Private people title','fixture'))
    # No body in durable projection and duplicate update is inert.
    delivery=rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')[0]
    assert 'Shared synthetic' not in delivery['projection_json']
    queue(shared_env,number=10)
    assert len(rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0'))==1
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *args:calls.append(args) or ('accepted',9,None))
    assert bot.deliver(c,NOW)==1 and calls[0][1]==-100 and calls[0][3]==7
    assert calls[0][2]==text
    assert queue(shared_env,number=11,topic=8) is None
    assert queue(shared_env,number=12,topic=None) is None


@pytest.mark.parametrize('audience',['unit','people'])
def test_bureau_visibility_is_required_even_for_admin(shared_env,audience):
    item=entry(shared_env,audience=audience)
    c,users,_,_,payload=shared_env[0];group=shared_env[1]
    assert reads.shareable(c,users[4],item['id']) is None
    with pytest.raises(ValueError):
        reads.consent(c,payload,group['id'],group['generation'],item['id'],'bad',True,NOW)


@pytest.mark.parametrize('change',['edit','audience','revoke','delete','restore','disconnect','grant','flag','reregister'])
def test_change_after_queue_fences_group_send(shared_env,monkeypatch,change):
    item=entry(shared_env);share(shared_env,item);queue(shared_env)
    registered,group=shared_env;c,_,path,_,payload=registered
    if change=='edit':
        c.execute('UPDATE calendar_entry SET title=? WHERE id=?',('Changed source',item['id']));c.commit()
    elif change=='audience':
        c.execute("UPDATE calendar_entry SET audience='people' WHERE id=?",(item['id'],));c.commit()
    elif change=='revoke':
        reads.consent(c,payload,group['id'],group['generation'],item['id'],'',False,NOW)
    elif change=='delete':
        c.execute('DELETE FROM calendar_entry WHERE id=?',(item['id'],));c.commit()
    elif change=='restore':
        backups.clear_restored_sessions(path)
    elif change=='disconnect':
        links.disconnect(c,payload,NOW)
    elif change=='grant':
        c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.read'",(links.stamp(NOW),));c.commit()
    elif change=='flag':
        monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_READ_ENABLED','0')
    else:
        groups.manage(c,payload,group['id'],group['generation'],'pause');register(registered,number=13,topic=7)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Stale group body sent'))
    assert bot.deliver(c,NOW)==0
    assert rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')[0]['state']=='cancelled'


def test_source_change_during_render_is_fenced(shared_env,monkeypatch):
    c=shared_env[0][0];item=entry(shared_env);share(shared_env,item);queue(shared_env)
    original=reads.render
    def racing(*args):
        text=original(*args)
        c.execute('UPDATE calendar_entry SET title=? WHERE id=?',('Changed after render',item['id']));c.commit()
        return text
    monkeypatch.setattr(reads,'render',racing)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Render race leaked body'))
    assert bot.deliver(c,NOW)==0
    assert rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')[0]['state']=='uncertain'


def test_room_group_only_date_slots_and_states(shared_env):
    c,users,_,_,_=shared_env[0];rooms.ensure_slots(c)
    slot=rooms.list_slots(c)[0]['id']
    reservation=rooms.request(c,title='Other private request',day=date(2026,10,26),slot_ids=[slot],
                            requester_user_id=users[0]['id'],purpose='Secret purpose',today=date(2026,10,20))
    c.execute("INSERT INTO room_block(day,slot_id,reason,created_by,created_at) VALUES (?,?,?,'fixture',?)",('2026-10-26',rooms.list_slots(c)[1]['id'],'Secret reason',links.stamp(NOW)));c.commit()
    text=render(shared_env,text='/group_rooms 2026-10-26')
    assert 'requested' in text and 'closed' in text and 'free' in text
    assert all(value not in text for value in ('Other private request','Secret purpose','Secret reason',reservation['ref_code']))
    rooms.approve(c,reservation['id'],'fixture',today=date(2026,10,20))
    text=render(shared_env,text='/group_rooms 2026-10-26',number=11)
    assert 'booked' in text


@pytest.mark.parametrize('command',['/my_rooms','/room_status CR-2026-0001','/calendar','/room_slots','/group_calendar 2026-10-26 2026-12-31','/group_rooms bad'])
def test_private_commands_and_malformed_queries_never_query_private_sources(shared_env,command,monkeypatch):
    monkeypatch.setattr(rooms,'get_by_ref',lambda *a,**kw:pytest.fail('Private status lookup'))
    monkeypatch.setattr(rooms,'list_for_user',lambda *a,**kw:pytest.fail('Private own list'))
    d=queue(shared_env,text=command)
    if command.startswith('/group_'):
        assert reads.render(shared_env[0][0],d,json.loads(d['projection_json']),bot.transport.config(),NOW)==reads.USAGE
    else:
        assert d is None


def test_new_owner_generation_does_not_inherit_old_shares(shared_env):
    registered,group=shared_env;item=entry(shared_env);share(shared_env,item)
    c,_,_,_,payload=registered
    groups.manage(c,payload,group['id'],group['generation'],'pause')
    register(registered,number=2,topic=7)
    assert 'Shared synthetic meeting' not in render(shared_env)


def test_staff_actor_requires_own_read_grant_and_current_membership(shared_env,monkeypatch):
    registered,group=shared_env;c,users,_,_,_=registered
    item=entry(shared_env);share(shared_env,item)
    bind(c,users[0],102)
    assert queue(shared_env,sender=102) is None
    actor=groups.linked(c,users[0]['id'])
    c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
        VALUES (?,?,'calendar.read',?,?,?,?)''',(actor['id'],actor['account_id'],actor['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)));c.commit()
    assert queue(shared_env,number=11,sender=102)
    monkeypatch.setattr(bot.transport,'member_status',lambda token,chat,sender:'left' if sender==102 else 'administrator')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Departed actor'))
    # Private handshake notices are unrelated and omitted.
    c.execute("UPDATE telegram_delivery SET state='cancelled' WHERE chat_id>0");c.commit()
    assert bot.deliver(c,NOW)==0


def test_preview_stale_consent(shared_env):
    registered,group=shared_env;c,users,_,client,payload=registered
    item=entry(shared_env);source=reads.shareable(c,users[4],item['id']);expected=reads.revision(source)
    c.execute('UPDATE calendar_entry SET title=? WHERE id=?',('Revised',item['id']));c.commit()
    with pytest.raises(ValueError):
        reads.consent(c,payload,group['id'],group['generation'],item['id'],expected,True,NOW)


def test_bounded_schedule_and_restart(shared_env):
    c,_,path,_,_=shared_env[0]
    for i in range(12):
        share(shared_env,entry(shared_env,title='Synthetic shared '+str(i)))
    text=render(shared_env)
    assert text.count('/calendar/entries/')==10 and 'narrow the dates' in text
    assert reads.common.units(text)<=4096
    restarted=st.connect(path)
    try:
        st.init_db(restarted)
        d=rows(restarted,"SELECT * FROM telegram_delivery WHERE state='queued' AND chat_id<0")[0]
        assert reads.render(restarted,d,json.loads(d['projection_json']),bot.transport.config(),NOW)==text
    finally:
        restarted.close()


@pytest.mark.parametrize('shape',[
    {'mode':'status','reference':'CR-2026-0001'},
    {'mode':'calendar','start':'2026-10-26','end':'2026-10-26','scope':'mine'},
    {'mode':'rooms','day':'2026-10-26','requester':1},
])
def test_group_descriptor_rejects_private_or_extended_shapes(shared_env,shape):
    c=shared_env[0][0]
    d=queue(shared_env)
    projection={'kind':'group_read','bot':bot.transport.config()[0],'fingerprint':bot.transport.config()[2],'query':shape}
    d['projection_json']=json.dumps(projection)
    assert groups.authorize_delivery(c,d,bot.transport.config()) is None


@pytest.mark.parametrize('change',['grant','read_flag','inactive','unlinked'])
def test_room_group_requires_independent_current_room_authority(shared_env,change,monkeypatch):
    c,users,_,_,_=shared_env[0]
    if change=='grant':
        c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='rooms.read'",(links.stamp(NOW),));c.commit()
    elif change=='read_flag':
        monkeypatch.setenv('CSS_TELEGRAM_ROOMS_READ_ENABLED','0')
    elif change=='inactive':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[4]['id'],));c.commit()
    else:
        links.disconnect(c,shared_env[0][4],NOW)
    monkeypatch.setattr(rooms,'day_view',lambda *a,**kw:pytest.fail('Unauthorized room source lookup'))
    assert queue(shared_env,text='/group_rooms 2026-10-26') is None


def test_group_owner_cannot_approve_stale_registration_or_foreign_account(shared_env):
    registered,group=shared_env;c,users,_,_,payload=registered
    item=entry(shared_env);expected=reads.revision(item)
    other=bind(c,users[0],102)
    with pytest.raises(ValueError):
        reads.consent(c,other,group['id'],group['generation'],item['id'],expected,True,NOW)
    with pytest.raises(ValueError):
        reads.consent(c,payload,group['id'],'stale',item['id'],expected,True,NOW)
    assert not rows(c,'SELECT * FROM telegram_group_share')


def test_source_change_during_provider_verification_denies_content(shared_env,monkeypatch):
    c=shared_env[0][0];item=entry(shared_env);share(shared_env,item);queue(shared_env)
    def verify(*args):
        c.execute('UPDATE calendar_entry SET title=? WHERE id=?',('Changed in provider check',item['id']));c.commit()
        return 'administrator'
    monkeypatch.setattr(bot.transport,'member_status',verify)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Changed source send'))
    assert bot.deliver(c,NOW)==0


def test_parsing_manila_date_and_private_chat_group_command_denial(shared_env):
    from datetime import datetime,timezone
    from tests.test_telegram_bot import update
    now=datetime(2026,10,25,18,tzinfo=timezone.utc)
    assert reads.parse('/group_calendar',now)=={'mode':'calendar','start':'2026-10-26','end':'2026-10-26'}
    assert reads.parse('/group_rooms',now)=={'mode':'rooms','day':'2026-10-26'}
    assert bot.normalize(update(text='/group_calendar'))['command'] is None
    assert bot.normalize(update(text='/group_rooms'))['command'] is None
