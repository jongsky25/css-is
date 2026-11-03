"""Private meeting/room guides, pulls and confirmations without outbound transport."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import re

import pytest

from documents_storage import rows
import storage as st
import telegram_actions as actions
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
import telegram_room_requests as requests
import telegram_meeting_webhook as inline
from tests.test_work import workspace
from tests.test_telegram_bot import setup,submit,update,NOW
from tests.test_telegram_links import linking,claimed
from tests.test_telegram_groups import registered
from tests.test_telegram_meetings import meeting_env,FIELDS
from tests.test_telegram_room_requests import request_env
from tests.test_telegram_meeting_rooms import combined_env,ROOM


def webhook(monkeypatch):
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram send'))


def command(linking,text,number=20,sender=101):
    response=submit(linking[3],update(number,text=text,sender=sender))
    assert response.status_code==200
    return response.json()


def token(packet,prefix):
    return re.search('/'+prefix+'_confirm ([A-Za-z0-9_-]{43})',packet['text'])[1]


def prepare_meeting(env,**extra):
    linking,origin=env;c,users,*_=linking
    ctx=meetings.origin(c,users[0],origin['id'],NOW)
    return actions.issue(c,ctx,'calendar.create','webhook-meeting-preview-key',{**FIELDS,**extra},NOW)


def prepare_room(env,**extra):
    linking,origin,eid=env;c,users,*_=linking
    ctx=meetings.origin(c,users[0],origin['id'],NOW,'rooms.request')
    return actions.issue(c,ctx,'rooms.request','webhook-room-preview-key',{'entry_id':str(eid),**ROOM,**extra},NOW)


def test_guide_preview_confirm_and_receipt_are_private_webhook_only(meeting_env,monkeypatch):
    linking,_=meeting_env;c,*_=linking
    # Remove old direct-mode queued guide so this flow starts with a fresh command.
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit();webhook(monkeypatch)
    guide=command(linking,'/meeting')
    assert '/account/telegram/meeting?origin=' in guide['text']
    assert 'method' not in command(linking,'/meeting')
    latest=rows(c,'SELECT * FROM telegram_meeting_origin ORDER BY rowid DESC LIMIT 1')[0]
    p=prepare_meeting((linking,latest))
    assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
    preview=command(linking,'/meeting_preview '+p['operation_id'],21)
    assert all(word in preview['text'] for word in ('Synthetic meeting','09:00','10:30','Asia/Manila','No room requested'))
    raw=token(preview,'meeting')
    assert raw not in '\n'.join(c.iterdump())
    receipt=command(linking,'/meeting_confirm '+raw,22)
    assert 'Meeting created' in receipt['text']
    assert c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    assert not c.execute('SELECT 1 FROM room_reservation').fetchone()
    assert 'Meeting created' in command(linking,'/meeting_confirm '+raw,23)['text']
    assert 'Meeting created' in command(linking,'/meeting_receipt '+p['operation_id'],24)['text']
    assert c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    assert bot.deliver(c,NOW)==0


def test_room_preview_confirmation_keeps_pending_approval(request_env,monkeypatch):
    linking,_,_=request_env;c,*_=linking
    c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit();webhook(monkeypatch)
    assert '/account/telegram/room?origin=' in command(linking,'/room_request')['text']
    p=prepare_room(request_env)
    preview=command(linking,'/room_preview '+p['operation_id'],21)
    assert 'Pending Administrative Section approval' in preview['text']
    raw=token(preview,'room')
    receipt=command(linking,'/room_confirm '+raw,22)
    assert 'pending approval; no booking held' in receipt['text']
    assert 'pending approval' in command(linking,'/room_receipt '+p['operation_id'],23)['text']
    assert 'pending approval' in command(linking,'/room_confirm '+raw,24)['text']
    assert c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]==1
    assert c.execute('SELECT sum(is_approved) FROM room_reservation_slot').fetchone()[0]==0
    assert bot.deliver(c,NOW)==0


@pytest.mark.parametrize('change',['expiry','grant','account','delivery','bot'])
def test_changed_authority_or_expiry_cannot_confirm(meeting_env,monkeypatch,change):
    linking,_=meeting_env;c,users,*_=linking
    webhook(monkeypatch);p=prepare_meeting(meeting_env)
    raw=token(command(linking,'/meeting_preview '+p['operation_id']),'meeting')
    if change=='expiry':monkeypatch.setattr(bot,'now_utc',lambda:NOW+timedelta(minutes=6))
    elif change=='grant':c.execute("UPDATE telegram_grant SET revoked_at=? WHERE action='calendar.create'",(links.stamp(NOW),));c.commit()
    elif change=='account':c.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],));c.commit()
    elif change=='delivery':monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
    else:monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN','123456:'+'B'*35)
    packet=command(linking,'/meeting_confirm '+raw,21)
    assert 'Meeting created' not in packet.get('text','')
    assert not c.execute('SELECT 1 FROM calendar_entry').fetchone()


def test_foreign_sender_wrong_action_and_private_group_input_denied(meeting_env,monkeypatch):
    linking,_=meeting_env;c,*_=linking
    webhook(monkeypatch);p=prepare_meeting(meeting_env)
    assert 'method' not in command(linking,'/meeting_preview '+p['operation_id'],sender=102)
    assert 'unavailable' in command(linking,'/room_preview '+p['operation_id'],21)['text']
    preview=command(linking,'/meeting_preview '+p['operation_id'],22)
    raw=token(preview,'meeting')
    msg=update(23,text='/meeting_confirm '+raw);msg['message']['chat']={'id':-100,'type':'group'}
    assert 'method' not in submit(linking[3],msg).json()
    assert not c.execute('SELECT 1 FROM calendar_entry').fetchone()


def test_late_domain_error_rolls_back_meeting_and_preview(meeting_env,monkeypatch):
    linking,_=meeting_env;c,*_=linking
    webhook(monkeypatch);p=prepare_meeting(meeting_env)
    raw=token(command(linking,'/meeting_preview '+p['operation_id']),'meeting')
    original=meetings.Adapter.apply
    def fail(self,*args):
        original(self,*args)
        raise ValueError('Synthetic late failure')
    monkeypatch.setattr(meetings.Adapter,'apply',fail)
    assert 'unavailable' in command(linking,'/meeting_confirm '+raw,21)['text']
    assert not c.execute('SELECT 1 FROM calendar_entry').fetchone()
    assert c.execute('SELECT state FROM telegram_preview').fetchone()[0]=='pending'


def test_response_receipt_failure_returns_503_and_rolls_back(meeting_env,monkeypatch):
    linking,_=meeting_env;c,*_=linking
    webhook(monkeypatch);p=prepare_meeting(meeting_env)
    raw=token(command(linking,'/meeting_preview '+p['operation_id']),'meeting')
    c.execute("CREATE TRIGGER test_webhook_failure BEFORE INSERT ON telegram_delivery WHEN NEW.error_code='webhook_response' BEGIN SELECT RAISE(ABORT,'synthetic'); END;");c.commit()
    response=submit(linking[3],update(21,text='/meeting_confirm '+raw))
    assert response.status_code==503
    assert not c.execute('SELECT 1 FROM calendar_entry').fetchone()
    assert not c.execute('SELECT 1 FROM telegram_update WHERE update_id=21').fetchone()


def test_worker_cannot_push_old_private_preview_after_mode_switch(meeting_env,monkeypatch):
    linking,_=meeting_env;c,*_=linking
    p=prepare_meeting(meeting_env)
    assert c.execute("SELECT 1 FROM telegram_delivery WHERE state='queued'").fetchone()
    webhook(monkeypatch)
    assert bot.deliver(c,NOW)==0
    assert 'Meeting preview' in command(linking,'/meeting_preview '+p['operation_id'])['text']


def test_combined_partial_and_room_only_retry_never_recreate_meeting(combined_env,monkeypatch):
    import room_actions
    import rooms
    linking,_=combined_env;c,users,*_=linking
    webhook(monkeypatch)
    p=prepare_meeting(combined_env,room=ROOM)
    raw=token(command(linking,'/meeting_preview '+p['operation_id']),'meeting')
    original=room_actions.request_in_transaction
    def unavailable(*args,**kwargs):raise rooms.RoomError('Synthetic room failure')
    monkeypatch.setattr(room_actions,'request_in_transaction',unavailable)
    receipt=command(linking,'/meeting_confirm '+raw,21)
    assert 'Room request failed; no booking held' in receipt['text']
    parent=rows(c,'SELECT * FROM telegram_operation WHERE operation_id=?',(p['operation_id'],))[0]
    assert parent['state']=='partial' and c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    monkeypatch.setattr(room_actions,'request_in_transaction',original)
    assert '/account/telegram/room?origin=' in command(linking,'/room_request',22)['text']
    origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request' ORDER BY rowid DESC LIMIT 1")[0]
    retry=prepare_room((linking,origin,parent['result_entry_id']),parent_operation_id=parent['operation_id'])
    raw=token(command(linking,'/room_preview '+retry['operation_id'],23),'room')
    assert 'pending approval' in command(linking,'/room_confirm '+raw,24)['text']
    assert 'pending approval' in command(linking,'/meeting_receipt '+parent['operation_id'],25)['text']
    assert c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    assert c.execute('SELECT count(*) FROM room_reservation').fetchone()[0]==1


def test_group_origin_confirmation_keeps_async_membership_path(registered,monkeypatch):
    import telegram_groups as groups
    from tests.test_telegram_groups import register,group_update
    c,users,_,client,_=registered
    for flag in ('CALENDAR_READ','CALENDAR_CREATE'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    connection=groups.linked(c,users[4]['id'])
    for scope in ('calendar.read','calendar.create'):
        c.execute('INSERT INTO telegram_grant(connection_id,account_id,action,generation,bot_identity,bot_fingerprint,consented_at) VALUES (?,?,?,?,?,?,?)',
            (connection['id'],users[4]['id'],scope,connection['generation'],bot.transport.config()[0],bot.transport.config()[2],links.stamp(NOW)))
    c.commit();register(registered,topic=7)
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    submit(client,group_update(10,topic=7,text='/meeting'))
    origin=rows(c,'SELECT * FROM telegram_meeting_origin')[0]
    ctx=meetings.origin(c,users[4],origin['id'],NOW)
    p=actions.issue(c,ctx,'calendar.create','group-webhook-preservation-key',FIELDS,NOW)
    response=command(registered,'/meeting_confirm '+p['token'],20)
    assert 'method' not in response
    assert c.execute('SELECT state FROM telegram_update WHERE update_id=20').fetchone()[0]=='queued'
    bot.process_updates(c,NOW)
    assert c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    sent=[];monkeypatch.setattr(bot.transport,'send',lambda *a:sent.append(a) or ('accepted',1,None))
    assert bot.deliver(c,NOW)==1
    assert all(row[1]==101 for row in sent)


def test_two_private_webhook_confirmations_commit_one_meeting(meeting_env,monkeypatch):
    linking,_=meeting_env;c,*_=linking
    webhook(monkeypatch);p=prepare_meeting(meeting_env)
    raw=token(command(linking,'/meeting_preview '+p['operation_id']),'meeting')
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda n:command(linking,'/meeting_confirm '+raw,n),(21,22)))
    assert all('Meeting created' in reply['text'] for reply in replies)
    assert c.execute('SELECT count(*) FROM calendar_entry').fetchone()[0]==1
    assert c.execute("SELECT count(*) FROM telegram_operation WHERE state='committed'").fetchone()[0]==1
