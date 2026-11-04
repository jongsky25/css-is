"""Real phone forms and explicit linking/confirmation; synthetic sources, no outbound I/O."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_meeting_manage as manage
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN, SECRET, NOW, update, HEADERS


@pytest.mark.parametrize('mode',['reschedule','cancel'])
def test_phone_can_consent_prepare_and_confirm_own_meeting_without_scripts(grid_browser,app_mod,monkeypatch,mode):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','CALENDAR_READ','CALENDAR_RESCHEDULE','CALENDAR_CANCEL'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    monkeypatch.setattr(manage.meet_relay,'call',lambda *a,**kw:pytest.fail('Outgoing Meet relay'))
    eid=st.cal_create(c,'Synthetic phone-managed meeting','2026-10-26',start_time='09:00',end_time='10:00',
                      by=user['username'],audience='people',people=[user['id']])
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
            page.get_by_label(links.SCOPES['calendar.read'],exact=True).check()
            page.get_by_label(links.SCOPES[manage.MODES[mode]],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'calendar.read',manage.MODES[mode]}
            guide=command('/meeting_'+mode)
            response=page.goto(guide['text'].splitlines()[-1])
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            form=page.locator('form[action="'+manage.PATH+mode+'"]')
            fields={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            fields['entry_id']=str(eid)
            if mode=='reschedule':fields.update(day='2026-10-27',start_time='11:00',end_time='12:00')
            url=base+manage.PATH+mode;headers={'Origin':base}
            assert page.request.post(url,form={**fields,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**fields,'user_id':str(user['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Meeting entry number',exact=True).fill(str(eid))
            if mode=='reschedule':
                page.get_by_label('New office date',exact=True).fill('2026-10-27')
                page.get_by_label('New start time',exact=True).fill('11:00')
                page.get_by_label('New end time',exact=True).fill('12:00')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text()
            assert 'No meeting has changed' in body
            op=re.search('/'+mode+r'_preview ([a-f0-9]{32})',body)[1]
            assert st.cal_get(c,eid)['start_date']=='2026-10-26' and st.cal_get(c,eid)['status']=='confirmed'
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            preview=command('/'+mode+'_preview '+op)['text']
            assert 'Synthetic phone-managed meeting' in preview and '2026-10-26' in preview
            if mode=='reschedule':assert '2026-10-27' in preview and '11:00' in preview
            exact=re.search('/'+mode+r'_confirm [A-Za-z0-9_-]{43}',preview)[0]
            assert 'Recorded outcome:' in command(exact)['text']
            assert 'Recorded outcome:' in command(exact)['text']
            record=st.cal_get(c,eid)
            if mode=='reschedule':assert record['start_date']=='2026-10-27' and record['start_time']=='11:00'
            else:assert record['status']=='cancelled'
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies()
            assert page.request.post(url,form=fields,headers=headers).status==401
        finally:context.close();c.close()
