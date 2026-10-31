"""Phone-sized, script-disabled linking and disconnect against the real application."""
import json
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
from tests.test_telegram_bot import TOKEN, SECRET, NOW, update, HEADERS


@pytest.mark.parametrize('mode',['direct','webhook'])
def test_private_link_confirmation_and_disconnect_without_scripts(grid_browser, app_mod, monkeypatch, mode):
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT',mode)
    c=st.connect(app_mod.DB)
    user=st.get_admin_user(c,'viewer@test.local')
    for capability in ('INBOUND','DELIVERY','LINK'):
        monkeypatch.setenv('CSS_TELEGRAM_'+capability+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    sent=[]
    monkeypatch.setattr(bot.transport,'send',lambda token,chat,text:sent.append(text) or ('accepted',len(sent),None))
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        # Local test transport is HTTP; production origin validation is checked separately.
        monkeypatch.setattr(links,'origin',lambda:base)
        if mode == 'webhook':
            def outgoing_forbidden(*args):
                pytest.fail('Linking required an outgoing connection')
            monkeypatch.setattr(bot.transport,'send',outgoing_forbidden)
            packet=httpx.post(base+bot.PATH,json=update(),headers=HEADERS).json()
            raw=re.search(r'(?m)^[a-f0-9]{64}$',packet['text'])[0]
        else:
            value=update()
            bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
            bot.process_updates(c,NOW)
            assert bot.deliver(c,NOW)==1
            ch=rows(c,'SELECT * FROM telegram_link_challenge')[0]
            raw=links.code(ch,'claim')
            assert raw in sent[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        page=context.new_page()
        try:
            response=page.goto(base+'/account/telegram')
            assert response.status==200
            assert page.get_by_role('heading',name='Private Telegram connection',exact=True).is_visible()
            page.get_by_label('Private linking code').fill(raw)
            page.get_by_label('Read permitted calendar entries').check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.').check()
            page.get_by_role('button',name='Request confirmation in Telegram').click()
            assert 'Waiting for confirmation' in page.locator('body').inner_text()
            assert raw not in page.url and raw not in page.content()
            assert c.execute('SELECT count(*) FROM telegram_connection').fetchone()[0]==0
            if mode == 'webhook':
                assert 'Connection: awaiting confirmation' in page.locator('body').inner_text()
                assert 'Send /status' in page.locator('body').inner_text()
                assert not rows(c,"SELECT * FROM telegram_delivery WHERE dedupe_key LIKE 'link-confirm:%'")
                packet=httpx.post(base+bot.PATH,json=update(2,text='/status'),headers=HEADERS).json()
                assert user['username'] in packet['text']
                confirmation=re.search(r'/confirm [a-f0-9]{64}',packet['text'])[0]
                response=httpx.post(base+bot.PATH,json=update(3,text=confirmation),headers=HEADERS)
                assert 'active' in response.json()['text']
                assert bot.deliver(c,NOW)==0
            else:
                from datetime import timedelta
                assert bot.deliver(c,NOW+timedelta(seconds=2))==1
                assert user['username'] in sent[-1]
                value=update(2,text='/confirm '+links.code(ch,'confirm'))
                bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
                bot.process_updates(c,NOW)
            page.reload()
            assert 'Connection: active' in page.locator('body').inner_text()
            assert 'Read permitted calendar entries' in page.locator('body').inner_text()
            monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED','0')
            monkeypatch.setenv('CSS_TELEGRAM_DELIVERY_ENABLED','0')
            page.reload()
            page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'Connection: revoked' in page.locator('body').inner_text()
            assert c.execute('SELECT count(*) FROM telegram_grant WHERE revoked_at IS NULL').fetchone()[0]==0
            assert page.locator('input[type=password]').count()==0
        finally:
            context.close()
            c.close()
