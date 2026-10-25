"""Phone without JavaScript: combined preview -> partial receipt -> room-only retry."""
from datetime import timedelta
import json
import re

import auth
from documents_storage import rows,transaction
import rooms
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update


def test_mobile_combined_fields_partial_receipt_and_saved_meeting_retry(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','CALENDAR_READ','CALENDAR_CREATE','ROOMS_READ','ROOMS_REQUEST'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',15,None))
    def receive(number,text):
        value=update(number,text=text);bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
        bot.process_updates(c,NOW)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        cookie=session_token(user)
        with transaction(c):links.start(c,101,bot.transport.config(),NOW)
        ch=rows(c,'SELECT * FROM telegram_link_challenge')[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':cookie,'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(links.code(ch,'claim'))
            for label in ('Read permitted calendar entries','Create one meeting after an exact private preview and confirmation',
                          'Read room availability and own requests','Request a room for my permitted meeting after private confirmation'):
                choice=page.get_by_label(label,exact=True);assert not choice.is_checked();choice.check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            ch=rows(c,'SELECT * FROM telegram_link_challenge')[0]
            with transaction(c):assert links.confirm(c,101,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW)
            c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
            receive(10,'/meeting')
            origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='calendar.create'")[0]
            page.goto(base+meetings.PATH+'?origin='+origin['id'])
            room=page.get_by_label('Also submit a room request for myself after saving this meeting',exact=True)
            assert not room.is_checked();room.check()
            page.get_by_label('Meeting title',exact=True).fill('Synthetic combined mobile meeting')
            page.get_by_label('Office date',exact=True).fill('2026-10-26')
            page.get_by_label('Start time',exact=True).fill('09:00');page.get_by_label('End time',exact=True).fill('10:30')
            page.get_by_label('Calendar audience',exact=True).select_option('bureau')
            page.get_by_role('button',name='Send exact preview to my private chat',exact=True).click()
            assert 'Choose configured start and end hours' in page.locator('body').inner_text()
            assert page.get_by_label('Also submit a room request for myself after saving this meeting',exact=True).is_checked()
            assert page.get_by_label('Meeting title',exact=True).input_value()=='Synthetic combined mobile meeting'
            page.get_by_label('Room from',exact=True).select_option('09:00');page.get_by_label('Room until',exact=True).select_option('10:00')
            key=page.locator('input[name=key]').input_value();csrf=page.locator('input[name=csrf]').input_value()
            page.get_by_role('button',name='Send exact preview to my private chat',exact=True).click()
            assert 'preview is prepared' in page.locator('body').inner_text()
            assert not rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic combined mobile meeting'")
            for i in range(2):bot.deliver(c,NOW+timedelta(seconds=2*i))
            text=next(m[2] for m in messages if '/meeting_confirm ' in m[2])
            assert '90 minutes' in text and '60 minutes' in text and 'keep the meeting' in text
            token=re.search(r'/meeting_confirm ([A-Za-z0-9_-]{43})',text)[1]
            sid=next(s['id'] for s in rooms.list_slots(c) if s['start_time']=='09:00')
            c.execute("INSERT INTO room_block(day,slot_id,reason,created_by,created_at) VALUES (?,?,?,'fixture',?)",('2026-10-26',sid,'Synthetic private reason',links.stamp(NOW)));c.commit()
            receive(11,'/meeting_confirm '+token)
            parent=rows(c,"SELECT * FROM telegram_operation WHERE action='calendar.create'")[0]
            assert parent['state']=='partial' and parent['result_entry_id']
            assert not rows(c,'SELECT * FROM room_reservation')
            bot.deliver(c,NOW+timedelta(seconds=4))
            receipt=next(m[2] for m in messages if 'Room request failed' in m[2])
            assert '/calendar/entries/'+str(parent['result_entry_id']) in receipt and 'Next: you' in receipt
            # Reposting the original combined form recovers its receipt, without retrying the calendar.
            response=page.request.post(base+meetings.PATH,form={'csrf':csrf,'key':key,'origin':origin['id'],
                'title':'Synthetic combined mobile meeting','day':'2026-10-26','start_time':'09:00','end_time':'10:30',
                'venue':'','audience':'bureau','owner_org_id':'','room_request':'1','room_from':'09:00','room_to':'10:00'},headers={'Origin':base},max_redirects=0)
            assert response.status==303 and 'already=1' in response.headers['location']
            c.execute('DELETE FROM room_block');c.commit()
            receive(12,'/room_request')
            page.goto(base+'/account/telegram/room?parent_operation_id='+parent['operation_id'])
            assert page.get_by_label('Meeting entry number',exact=True).input_value()==str(parent['result_entry_id'])
            assert page.get_by_label('Meeting entry number',exact=True).get_attribute('readonly') is not None
            assert 'No new meeting will be created' in page.locator('body').inner_text()
            page.get_by_label('Room from',exact=True).select_option('09:00');page.get_by_label('Room until',exact=True).select_option('10:00')
            page.get_by_role('button',name='Send room preview to my private chat',exact=True).click()
            for i in range(2):bot.deliver(c,NOW+timedelta(seconds=6+2*i))
            room_text=next(m[2] for m in messages if '/room_confirm ' in m[2])
            assert parent['operation_id'] in room_text and 'No meeting is created' in room_text
            room_token=re.search(r'/room_confirm ([A-Za-z0-9_-]{43})',room_text)[1]
            receive(13,'/room_confirm '+room_token)
            records=rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic combined mobile meeting'")
            assert len(records)==1 and records[0]['id']==parent['result_entry_id']
            record=rows(c,'SELECT * FROM room_reservation WHERE calendar_entry_id=?',(records[0]['id'],))[0]
            assert record['status']=='requested' and record['requester_user_id']==user['id']
            assert len(rows(c,'SELECT * FROM telegram_operation WHERE parent_operation_id=?',(parent['operation_id'],)))==2
            page.goto(base+'/calendar/entries/'+str(records[0]['id']))
            assert 'Synthetic combined mobile meeting' in page.locator('body').inner_text()
            assert all(m[1]==101 for m in messages) and not rows(c,'SELECT * FROM telegram_delivery WHERE chat_id<0')
            assert all(v not in page.content() for v in (TOKEN,SECRET,token,room_token))
        finally:context.close();c.close()
