"""Mobile, script-disabled signed-in fields -> private bot confirmation -> source."""
from datetime import timedelta
import json
import re

import auth
from documents_storage import rows,transaction
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_meetings as meetings
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update


def test_mobile_guided_meeting_form_and_private_confirmation_without_scripts(grid_browser,app_mod,monkeypatch):
    # Legacy worker transport remains covered separately from webhook pulls.
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','direct')
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'admin@test.local')
    for capability in ('INBOUND','DELIVERY','LINK','CALENDAR_READ','CALENDAR_CREATE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+capability+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    calls=[];monkeypatch.setattr(bot.transport,'send',lambda *a:calls.append(a) or ('accepted',19,None))
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        cookie=session_token(user);payload=auth.parse_token(cookie)
        with transaction(c):links.start(c,101,bot.transport.config(),NOW)
        ch=rows(c,'SELECT * FROM telegram_link_challenge')[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':cookie,'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(links.code(ch,'claim'))
            page.get_by_label('Read permitted calendar entries',exact=True).check()
            create=page.get_by_label('Create one meeting after an exact private preview and confirmation',exact=True)
            assert not create.is_checked();create.check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            ch=rows(c,'SELECT * FROM telegram_link_challenge')[0]
            with transaction(c):assert links.confirm(c,101,links.digest(links.code(ch,'confirm')),bot.transport.config(),NOW)
            c.execute("UPDATE telegram_delivery SET state='cancelled'");c.commit()
            value=update(10,text='/meeting');bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
            origin=rows(c,'SELECT * FROM telegram_meeting_origin')[0]
            page.goto(base+meetings.PATH+'?origin='+origin['id'])
            page.get_by_label('Meeting title',exact=True).fill('Synthetic mobile meeting')
            page.get_by_label('Office date',exact=True).fill('2026-10-26')
            page.get_by_label('Start time',exact=True).fill('09:00');page.get_by_label('End time',exact=True).fill('10:30')
            page.get_by_label('Venue',exact=True).fill('Synthetic mobile venue')
            page.get_by_label('Calendar audience',exact=True).select_option('bureau')
            original_key=page.locator('input[name=key]').input_value()
            original_csrf=page.locator('input[name=csrf]').input_value()
            page.get_by_role('button',name='Send exact preview to my private chat',exact=True).click()
            assert 'preview is prepared' in page.locator('body').inner_text()
            assert not rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic mobile meeting'")
            for i in range(2):bot.deliver(c,NOW+timedelta(seconds=i*2))
            message=next(v[2] for v in calls if '/meeting_confirm ' in v[2])
            assert '90 minutes' in message and 'Asia/Manila' in message
            token=re.search(r'/meeting_confirm ([A-Za-z0-9_-]{43})',message)[1]
            assert token not in page.content()
            value=update(11,text='/meeting_confirm '+token);bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
            bot.process_updates(c,NOW)
            records=rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic mobile meeting'")
            assert len(records)==1
            bot.deliver(c,NOW+timedelta(seconds=4))
            repeated=page.request.post(base+meetings.PATH,form={'csrf':original_csrf,'key':original_key,'origin':origin['id'],
                'title':'Synthetic mobile meeting','day':'2026-10-26','start_time':'09:00','end_time':'10:30',
                'venue':'Synthetic mobile venue','audience':'bureau','owner_org_id':''},headers={'Origin':base},max_redirects=0)
            assert repeated.status==303 and 'already=1' in repeated.headers['location']
            page.goto(base+repeated.headers['location'])
            assert 'No second meeting was created' in page.locator('body').inner_text()
            assert len(rows(c,"SELECT * FROM calendar_entry WHERE title='Synthetic mobile meeting'"))==1
            page.goto(base+'/calendar/entries/'+str(records[0]['id']))
            assert 'Synthetic mobile meeting' in page.locator('body').inner_text()
            assert all(v[1]==101 for v in calls) and '/calendar/entries/' in calls[-1][2]
            assert not rows(c,'SELECT * FROM room_reservation')
            assert TOKEN not in page.content() and SECRET not in page.content()
        finally:context.close();c.close()
