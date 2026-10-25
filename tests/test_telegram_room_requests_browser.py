"""Mobile no-JavaScript room fields -> private bot confirm -> pending request."""
from datetime import timedelta
import json
import re

import auth
from documents_storage import rows,transaction
import rooms
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_room_requests as requests
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update


def test_mobile_room_preview_confirmation_and_form_replay_without_scripts(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','CALENDAR_READ','ROOMS_READ','ROOMS_REQUEST'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    messages=[];monkeypatch.setattr(bot.transport,'send',lambda *a:messages.append(a) or ('accepted',15,None))
    rid=None;eid=None
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        cookie=session_token(user);payload=auth.parse_token(cookie)
        with transaction(c):links.start(c,101,bot.transport.config(),NOW)
        ch=rows(c,'SELECT * FROM telegram_link_challenge ORDER BY created_at DESC')[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':cookie,'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(links.code(ch,'claim'))
            for label in ('Read permitted calendar entries','Read room availability and own requests','Request a room for my permitted meeting after private confirmation'):
                choice=page.get_by_label(label,exact=True);assert not choice.is_checked();choice.check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            ch=rows(c,'SELECT * FROM telegram_link_challenge ORDER BY created_at DESC')[0]
            with transaction(c):assert links.confirm(c,101,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW)
            c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
            eid=st.cal_create(c,'Synthetic mobile room meeting','2026-10-26',audience='bureau',by=user['username'],start_time='09:00',end_time='10:00')
            value=update(10,text='/room_request');bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
            origin=rows(c,"SELECT * FROM telegram_meeting_origin WHERE action='rooms.request'")[0]
            page.goto(base+requests.PATH+'?origin='+origin['id'])
            page.get_by_label('Meeting entry number',exact=True).fill(str(eid))
            page.get_by_label('Room from',exact=True).select_option('09:00');page.get_by_label('Room until',exact=True).select_option('10:00')
            key=page.locator('input[name=key]').input_value();csrf=page.locator('input[name=csrf]').input_value()
            page.get_by_role('button',name='Send room preview to my private chat',exact=True).click()
            assert 'room preview is prepared' in page.locator('body').inner_text()
            assert not rows(c,"SELECT * FROM room_reservation WHERE calendar_entry_id=?",(eid,))
            for i in range(2):bot.deliver(c,NOW+timedelta(seconds=i*2))
            message=next(v[2] for v in messages if '/room_confirm ' in v[2])
            assert 'No booking is held' in message and 'Asia/Manila' in message and '60 minutes' in message
            token=re.search(r'/room_confirm ([A-Za-z0-9_-]{43})',message)[1]
            value=update(11,text='/room_confirm '+token);bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW);bot.process_updates(c,NOW)
            record=rows(c,'SELECT * FROM room_reservation WHERE calendar_entry_id=?',(eid,))[0];rid=record['id']
            assert record['status']=='requested' and record['requester_user_id']==user['id']
            repeated=page.request.post(base+requests.PATH,form={'csrf':csrf,'key':key,'origin':origin['id'],'entry_id':str(eid),'from_time':'09:00','to_time':'10:00'},headers={'Origin':base},max_redirects=0)
            assert repeated.status==303 and 'already=1' in repeated.headers['location']
            assert len(rows(c,'SELECT * FROM room_reservation WHERE calendar_entry_id=?',(eid,)))==1
            bot.deliver(c,NOW+timedelta(seconds=4))
            assert any('pending approval' in v[2] and '/rooms/mine' in v[2] for v in messages)
            assert all(v[1]==101 for v in messages)
            assert token not in page.content() and TOKEN not in page.content() and SECRET not in page.content()
        finally:
            context.close()
            if rid:
                c.execute('UPDATE telegram_operation SET result_room_id=NULL WHERE result_room_id=?',(rid,))
                c.execute('DELETE FROM room_notice WHERE reservation_id=?',(rid,));c.execute('DELETE FROM room_reservation_slot WHERE reservation_id=?',(rid,));c.execute('DELETE FROM room_reservation WHERE id=?',(rid,));c.commit()
            if eid:st.cal_delete(c,eid)
            c.close()
