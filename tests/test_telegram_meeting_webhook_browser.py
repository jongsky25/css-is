"""Real no-script phone forms and message-visible codes; no outbound provider."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('combined',[False,True])
def test_mobile_private_meeting_and_room_flow_uses_webhook_only(grid_browser,app_mod,monkeypatch,combined):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','CALENDAR_READ','CALENDAR_CREATE','ROOMS_READ','ROOMS_REQUEST'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    def forbidden(*args):pytest.fail('Private flow used outgoing Telegram')
    monkeypatch.setattr(bot.transport,'send',forbidden)
    monkeypatch.setattr(bot.transport,'member_status',forbidden)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        number=0
        def command(text):
            nonlocal number
            number+=1
            response=httpx.post(base+bot.PATH,json=update(number,text=text),headers=HEADERS)
            assert response.status_code==200
            return response.json()
        packet=command('/start');code=re.search(r'(?m)^[a-f0-9]{64}$',packet['text'])[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(code)
            for label in ('Read permitted calendar entries','Read room availability and own requests',
                          'Create one meeting after an exact private preview and confirmation',
                          'Request a room for my permitted meeting after private confirmation'):
                page.get_by_label(label,exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            packet=command('/status')
            command(re.search(r'/confirm [a-f0-9]{64}',packet['text'])[0])
            guide=command('/meeting')
            page.goto(guide['text'].splitlines()[-1])
            page.get_by_label('Meeting title',exact=True).fill('Synthetic webhook phone meeting')
            page.get_by_label('Office date',exact=True).fill('2026-10-26')
            page.get_by_label('Start time',exact=True).fill('09:00')
            page.get_by_label('End time',exact=True).fill('10:30')
            page.get_by_label('Calendar audience',exact=True).select_option('bureau')
            if combined:
                page.get_by_label('Also submit a room request for myself after saving this meeting',exact=True).check()
                page.get_by_label('Room from',exact=True).select_option('09:00')
                page.get_by_label('Room until',exact=True).select_option('10:00')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            text=page.locator('body').inner_text()
            op=re.search(r'/meeting_preview ([a-f0-9]{32})',text)[1]
            meeting_operation=op
            assert not rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic webhook phone meeting'")
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            preview=command('/meeting_preview '+op)
            assert 'Synthetic webhook phone meeting' in preview['text'] and 'Asia/Manila' in preview['text']
            confirmation=re.search(r'/meeting_confirm [A-Za-z0-9_-]{43}',preview['text'])[0]
            receipt=command(confirmation)
            saved=rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic webhook phone meeting'")
            assert len(saved)==1
            assert 'method' in command(confirmation)
            assert len(rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic webhook phone meeting'"))==1
            if not combined:
                guide=command('/room_request');page.goto(guide['text'].splitlines()[-1])
                page.get_by_label('Meeting entry number',exact=True).fill(str(saved[0]['id']))
                page.get_by_label('Room from',exact=True).select_option('09:00')
                page.get_by_label('Room until',exact=True).select_option('10:00')
                page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
                op=re.search(r'/room_preview ([a-f0-9]{32})',page.locator('body').inner_text())[1]
                preview=command('/room_preview '+op)
                assert 'No booking is held' in preview['text']
                confirmation=re.search(r'/room_confirm [A-Za-z0-9_-]{43}',preview['text'])[0]
                receipt=command(confirmation)
            assert 'pending approval; no booking held' in receipt['text']
            assert c.execute('SELECT count(*) FROM room_reservation WHERE calendar_entry_id=?',(saved[0]['id'],)).fetchone()[0]==1
            assert c.execute('SELECT sum(is_approved) FROM room_reservation_slot').fetchone()[0]==0
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            assert bot.deliver(c,NOW)==0
            # Old/retained operations may have no routing context. The page
            # must not crash or advertise an unusable private pull command.
            c.execute('UPDATE telegram_operation SET context_json=NULL WHERE operation_id=?',(meeting_operation,));c.commit()
            response=page.goto(base+'/account/telegram/meeting?queued=1&operation='+meeting_operation)
            assert response.status==200
            assert '/meeting_preview '+meeting_operation not in page.locator('body').inner_text()
        finally:context.close();c.close()
