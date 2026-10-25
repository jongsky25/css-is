"""Real meeting adapter and private-only command delivery, all provider I/O mocked."""
from datetime import timedelta
import json
import re

import pytest

import auth
import backups
from documents_storage import rows,transaction
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_meetings as meetings
import telegram_links as links
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed
from tests.test_telegram_groups import registered

FIELDS={'title':'Synthetic meeting','day':'2026-10-26','start_time':'09:00','end_time':'10:30','venue':'Synthetic hall','audience':'bureau','owner_org_id':'','people':[]}


@pytest.fixture
def meeting_env(linking,monkeypatch):
    c,users,path,client,payload=linking
    for switch in ('CALENDAR_READ','CALENDAR_CREATE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+switch+'_ENABLED','1')
    ch,raw,confirmation=claimed(linking,('calendar.read','calendar.create'))
    with transaction(c):assert links.confirm(c,101,links.digest(confirmation),bot.transport.config(),NOW)
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
    assert submit(client,update(10,text='/meeting')).status_code==200
    origin=rows(c,'SELECT * FROM telegram_meeting_origin')[0]
    return linking,origin


def prepare(env,**fields):
    linking,origin=env;c,users,_,_,_=linking
    ctx=meetings.origin(c,users[0],origin['id'],NOW)
    return actions.issue(c,ctx,meetings.ACTION,'synthetic-meeting-key',{**FIELDS,**fields},NOW)


def confirm(env,p,number=11):
    c,_,_,client,_=env[0]
    assert submit(client,update(number,text='/meeting_confirm '+p['token'])).status_code==200
    bot.process_updates(c,NOW)
    return rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(p['operation_id'],))[0]


def test_real_end_to_end_private_preview_confirm_receipt_and_replay(meeting_env,monkeypatch):
    linking,origin=meeting_env;c,users,path,client,_=linking
    p=prepare(meeting_env,people=[str(users[1]['id'])],audience='people')
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *args:calls.append(args) or ('accepted',19,None))
    assert bot.deliver(c,NOW)==1
    assert '?origin='+origin['id'] in calls[0][2]
    assert bot.deliver(c,NOW+timedelta(seconds=2))==1
    text=calls[1][2]
    assert all(v in text for v in ('Synthetic meeting','09:00','10:30','90 minutes','Asia/Manila','Only selected people','account '+str(users[1]['id']),'No room requested'))
    assert '/meeting_confirm '+p['token'] in text
    for table in ('telegram_delivery','telegram_update','telegram_preview'):
        assert p['token'] not in str(rows(c,'SELECT * FROM '+table))
    assert not rows(c,'SELECT * FROM calendar_entry')
    result=confirm(meeting_env,p)
    assert result['state']=='committed' and result['result_entry_id']
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert not rows(c,'SELECT * FROM room_reservation')
    confirm(meeting_env,p,number=12)
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert bot.deliver(c,NOW+timedelta(seconds=4))==1
    assert '/calendar/entries/'+str(result['result_entry_id']) in calls[-1][2]
    assert all(call[1]==101 for call in calls)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')


@pytest.mark.parametrize('fields',[
    {'end_time':'08:00'},{'start_time':'9:00'},{'day':'tomorrow'},{'title':''},
    {'audience':'people','people':[]},{'audience':'unit','owner_org_id':''},
    {'owner_org_id':'999999'},{'people':['999999']},{'people':[True]},
    {'people':[1]*13},{'title':'x'*121},{'venue':'x'*121},
])
def test_guided_fields_deny_ambiguity_unknown_people_and_invalid_audience(meeting_env,fields):
    with pytest.raises(ValueError):prepare(meeting_env,**fields)
    assert not rows(meeting_env[0][0],'SELECT * FROM telegram_preview')


@pytest.mark.parametrize('change',['participant','unit','disconnect','restore','read_grant','write_grant','switch','bot','expiry'])
def test_confirmation_denied_after_choices_or_authority_change(meeting_env,monkeypatch,change):
    linking,_=meeting_env;c,users,path,client,payload=linking
    unit=st.add_org_unit(c,'Synthetic unit','division','SYNTH/1')
    p=prepare(meeting_env,people=[str(users[1]['id'])],owner_org_id=str(unit))
    if change=='participant':
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[1]['id'],));c.commit()
    elif change=='unit':
        c.execute('UPDATE org_unit SET name=? WHERE id=?',('Renamed unit',unit));c.commit()
    elif change=='disconnect':links.disconnect(c,payload,NOW)
    elif change=='restore':backups.clear_restored_sessions(path)
    elif change in ('read_grant','write_grant'):
        c.execute('UPDATE telegram_grant SET revoked_at=? WHERE action=?',(links.stamp(NOW),'calendar.read' if change=='read_grant' else 'calendar.create'));c.commit()
    elif change=='switch':monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','0')
    elif change=='bot':monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    else:monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(seconds=301))
    assert submit(client,update(11,text='/meeting_confirm '+p['token'])).status_code==200
    bot.process_updates(c,NOW+timedelta(seconds=301) if change=='expiry' else NOW)
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_hard_delete_and_receipt_recovery_after_token_purge_never_recreate(meeting_env,monkeypatch):
    c,_,_,client,_=meeting_env[0];p=prepare(meeting_env);op=confirm(meeting_env,p)
    st.cal_delete(c,op['result_entry_id'],by='fixture')
    assert rows(c,'SELECT * FROM telegram_operation')[0]['result_code']=='calendar_deleted'
    bot.cleanup(c,NOW+timedelta(days=2))
    assert not rows(c,'SELECT * FROM telegram_preview')
    assert submit(client,update(12,text='/meeting_receipt '+p['operation_id'])).status_code==200
    bot.process_updates(c,NOW+timedelta(seconds=2))
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',22,None))
    bot.deliver(c,NOW+timedelta(seconds=3))
    assert calls and 'was deleted' in calls[-1][2] and 'calendar/entries/' not in calls[-1][2]
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_unconsented_and_group_field_commands_are_ignored(linking,monkeypatch):
    from tests.test_telegram_groups import group_update
    c,_,_,client,_=linking
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','1')
    submit(client,update(10,text='/meeting'))
    assert not rows(c,'SELECT * FROM telegram_meeting_origin')
    assert bot.normalize(group_update(text='/meeting title=Private details'))['command'] is None
    assert bot.normalize(group_update(text='/meeting_confirm '+'x'*43))['command'] is None


def test_preview_and_receipt_queue_share_their_transactions(meeting_env,monkeypatch):
    linking,_=meeting_env;c=linking[0]
    original=meetings.queue
    def fail(c,ctx,kind,identifier,now,**kw):
        if kind=='meeting_preview':raise ValueError('Synthetic enqueue failure')
        return original(c,ctx,kind,identifier,now,**kw)
    monkeypatch.setattr(meetings,'queue',fail)
    with pytest.raises(ValueError):prepare(meeting_env)
    assert not rows(c,'SELECT * FROM telegram_preview') and not rows(c,'SELECT * FROM telegram_operation')
    monkeypatch.setattr(meetings,'queue',original)
    p=prepare(meeting_env)
    def fail_receipt(c,ctx,kind,identifier,now,**kw):
        if kind=='meeting_receipt':raise ValueError('Synthetic receipt enqueue failure')
        return original(c,ctx,kind,identifier,now,**kw)
    monkeypatch.setattr(meetings,'queue',fail_receipt)
    confirm(meeting_env,p)
    assert not rows(c,'SELECT * FROM calendar_entry')
    assert rows(c,'SELECT * FROM telegram_preview')[0]['state']=='pending'


@pytest.mark.parametrize('change',['none','paused','left','migrated','wrong_topic','proof_expired'])
def test_registered_group_origin_never_sends_private_fields_to_group(registered,monkeypatch,change):
    from tests.test_telegram_groups import register,group_update
    import telegram_groups as groups
    c,users,path,client,payload=registered
    for switch in ('CALENDAR_READ','CALENDAR_CREATE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+switch+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id'])
    for scope in ('calendar.read','calendar.create'):
        c.execute('''INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at)
            VALUES (?,?,?,?,?,?,?)''',(connection['id'],connection['account_id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit();group=register(registered,topic=7)
    submit(client,group_update(10,topic=8 if change=='wrong_topic' else 7,text='/meeting'))
    found=rows(c,'SELECT * FROM telegram_meeting_origin')
    if change=='wrong_topic':
        assert not found;return
    origin=found[0];ctx=meetings.origin(c,users[4],origin['id'],NOW)
    p=actions.issue(c,ctx,meetings.ACTION,'group-origin-meeting-key',FIELDS,NOW)
    if change=='paused':groups.manage(c,payload,group['id'],group['generation'],'pause')
    elif change=='left':monkeypatch.setattr(bot.transport,'member_status',lambda *a:'left')
    elif change=='proof_expired':
        elapsed=[0.0]
        monkeypatch.setattr(actions.time,'monotonic',lambda:elapsed[0])
        def slow_proof(*args):
            elapsed[0]=301.0
            return 'administrator'
        monkeypatch.setattr(bot.transport,'member_status',slow_proof)
    elif change=='migrated':
        event=group_update(11,topic=7,text='');event['message']['migrate_to_chat_id']=-200;submit(client,event)
    submit(client,update(12,text='/meeting_confirm '+p['token']));bot.process_updates(c,NOW)
    assert len(rows(c,'SELECT * FROM calendar_entry'))==(1 if change=='none' else 0)
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',9,None))
    for i in range(3):bot.deliver(c,NOW+timedelta(seconds=i*2))
    assert all(call[1]==101 for call in calls)
    assert not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')
    assert not rows(c,'SELECT * FROM telegram_group_share')


def test_foreign_account_cannot_use_another_origin_or_confirmation(meeting_env):
    from tests.test_telegram_groups import bind
    c,users,_,client,_=meeting_env[0];p=prepare(meeting_env)
    bind(c,users[1],102)
    with pytest.raises(ValueError):meetings.origin(c,users[1],meeting_env[1]['id'],NOW)
    submit(client,update(11,sender=102,text='/meeting_confirm '+p['token']));bot.process_updates(c,NOW)
    assert not rows(c,'SELECT * FROM calendar_entry')


def test_preview_changed_during_render_is_suppressed(meeting_env,monkeypatch):
    c,users,_,_,_=meeting_env[0];p=prepare(meeting_env,people=[str(users[1]['id'])])
    c.execute("UPDATE telegram_delivery SET state='cancelled' WHERE dedupe_key LIKE 'meeting_guide:%'");c.commit()
    original=meetings.render
    def render(*args):
        text=original(*args)
        c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[1]['id'],));c.commit()
        return text
    monkeypatch.setattr(meetings,'render',render)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Stale preview sent'))
    assert bot.deliver(c,NOW)==0


def test_restart_and_lost_update_finalization_do_not_duplicate_business_action(meeting_env):
    c,_,path,client,_=meeting_env[0];p=prepare(meeting_env)
    submit(client,update(11,text='/meeting_confirm '+p['token']))
    restarted=st.connect(path)
    try:
        st.init_db(restarted);bot.process_updates(restarted,NOW)
    finally:restarted.close()
    row=rows(c,'SELECT * FROM telegram_update WHERE update_id=11')[0]
    c.execute("UPDATE telegram_update SET state='processing',lease_until=?,payload_json=? WHERE id=?",(links.stamp(NOW),json.dumps({'kind':'meeting_action','command':'/meeting_confirm','argument':actions.digest(p['token']),'bot':bot.transport.config()[0],'fingerprint':bot.transport.config()[2]}),row['id']));c.commit()
    bot.process_updates(c,NOW)
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert len(rows(c,"SELECT * FROM telegram_delivery WHERE dedupe_key=?",('meeting_receipt:'+p['operation_id'],)))==1


def test_two_real_workers_and_repeated_confirmations_create_one_record(meeting_env):
    from concurrent.futures import ThreadPoolExecutor
    c,_,path,client,_=meeting_env[0];p=prepare(meeting_env)
    for number in (11,12):submit(client,update(number,text='/meeting_confirm '+p['token']))
    def run():
        conn=st.connect(path)
        try:bot.process_updates(conn,NOW)
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as executor:list(executor.map(lambda _:run(),range(2)))
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1
    assert len(rows(c,"SELECT * FROM telegram_delivery WHERE dedupe_key=?",('meeting_receipt:'+p['operation_id'],)))==1


def test_action_arriving_between_worker_checks_is_not_discarded(meeting_env,monkeypatch):
    c,_,_,client,_=meeting_env[0];p=prepare(meeting_env)
    original=meetings.process_one;injected=[]
    def race(*args,**kw):
        if not injected:
            injected.append(True)
            submit(client,update(11,text='/meeting_confirm '+p['token']))
            return False
        return original(*args,**kw)
    monkeypatch.setattr(meetings,'process_one',race)
    bot.process_updates(c,NOW)
    assert len(rows(c,'SELECT * FROM calendar_entry'))==1


def test_deleted_source_between_receipt_render_and_send_fences_delivery(meeting_env,monkeypatch):
    c,_,_,_,_=meeting_env[0];p=prepare(meeting_env);op=confirm(meeting_env,p)
    c.execute("UPDATE telegram_delivery SET state='cancelled' WHERE dedupe_key NOT LIKE 'meeting_receipt:%'");c.commit()
    original=meetings.render
    def race(*args):
        text=original(*args)
        st.cal_delete(c,op['result_entry_id'],by='fixture')
        return text
    monkeypatch.setattr(meetings,'render',race)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Deleted source receipt sent'))
    assert bot.deliver(c,NOW)==0
    assert rows(c,"SELECT * FROM telegram_delivery WHERE dedupe_key LIKE 'meeting_receipt:%'")[0]['state']=='uncertain'


def test_write_consent_requires_pilot_and_read_choice(linking,monkeypatch):
    from tests.test_telegram_links import start
    c,_,_,_,payload=linking
    ch,code,_=start(linking)
    with pytest.raises(ValueError):links.claim(c,payload,code,['calendar.read','calendar.create'],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','1')
    with pytest.raises(ValueError):links.claim(c,payload,code,['calendar.create'],NOW)
    links.claim(c,payload,code,['calendar.read','calendar.create'],NOW)
    monkeypatch.setenv('CSS_TELEGRAM_CALENDAR_CREATE_ENABLED','0')
    with transaction(c):assert links.confirm(c,101,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW) is None
    assert not rows(c,'SELECT * FROM telegram_grant')


def test_upgrade_from_t31_adds_metadata_without_granting_or_enabling_actions(meeting_env):
    c,_,_,_,_=meeting_env[0];p=prepare(meeting_env)
    c.execute('DROP TABLE telegram_meeting_origin')
    c.execute('ALTER TABLE telegram_preview DROP COLUMN token_nonce')
    c.execute('ALTER TABLE telegram_operation DROP COLUMN context_json');c.commit()
    st.init_db(c);st.init_db(c)
    preview=rows(c,'SELECT * FROM telegram_preview')[0];operation=rows(c,'SELECT * FROM telegram_operation')[0]
    assert preview['token_nonce'] is None and operation['context_json'] is None
    assert preview['token_hash']==actions.digest(p['token'])
    assert not rows(c,'SELECT * FROM telegram_meeting_origin')
    assert not rows(c,'SELECT * FROM calendar_entry')
