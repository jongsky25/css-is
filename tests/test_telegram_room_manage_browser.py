"""Phone consent/form/preview/confirm flows for own-room actions, no external I/O."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import rooms
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_room_manage as manage
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,HEADERS,update


@pytest.mark.parametrize('mode,status',[('withdraw','approved'),('move','requested'),('move','approved')])
def test_phone_room_actions_keep_normal_approval_and_work_without_scripts(grid_browser,app_mod,monkeypatch,mode,status):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','ROOMS_READ','ROOMS_WITHDRAW','ROOMS_MOVE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    record=rooms.request(c,title='Synthetic phone room action',day='2026-10-26',slot_ids=[rooms.list_slots(c)[2]['id']],
                         requester_user_id=user['id'],actor=user['username'],today=NOW.date())
    if status=='approved':rooms.approve(c,record['id'],'synthetic approver',today=NOW.date())
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
            for scope in ('rooms.read',manage.MODES[mode]):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'rooms.read',manage.MODES[mode]}
            response=page.goto(command('/room_'+mode)['text'].splitlines()[-1])
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            form=page.locator('form[action="'+manage.PATH+mode+'"]')
            fields={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            fields['room_id']=record['ref_code']
            if mode=='move':fields['day']='2026-10-27'
            url=base+manage.PATH+mode;headers={'Origin':base}
            assert page.request.post(url,form={**fields,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**fields,'requester_user_id':str(user['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Room reference or request number',exact=True).fill(record['ref_code'])
            if mode=='move':page.get_by_label('New room date',exact=True).fill('2026-10-27')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            text=page.locator('body').inner_text()
            assert 'No request has changed' in text
            op=re.search('/'+mode+r'_preview ([a-f0-9]{32})',text)[1]
            assert rooms.get_reservation(c,record['id'])['status']==status
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/'+mode+'_preview '+op)['text']
            assert 'Synthetic phone room action' in text and 'Asia/Manila' in text
            if status=='approved' and mode=='move':assert 'old approved booking stays held' in text
            confirmation=re.search('/'+mode+r'_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome:' in command(confirmation)['text']
            assert 'Recorded outcome:' in command(confirmation)['text']
            current=rooms.get_reservation(c,record['id'])
            if mode=='withdraw':assert current['status']=='withdrawn'
            elif status=='requested':assert current['day']=='2026-10-27' and current['status']=='requested'
            else:
                assert current['status']=='approved' and current['day']=='2026-10-26'
                assert c.execute('SELECT count(*) FROM room_reservation WHERE moves_reservation_id=? AND status=?',(record['id'],'requested')).fetchone()[0]==1
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies()
            assert page.request.post(url,form=fields,headers=headers).status==401
        finally:context.close();c.close()
