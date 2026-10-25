"""Phone-sized, script-disabled linking and disconnect against the real application."""
import json

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN, SECRET, NOW, update


def test_private_link_confirmation_and_disconnect_without_scripts(grid_browser, app_mod, monkeypatch):
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
