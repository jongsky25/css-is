"""Real mobile, script-disabled administrator registration and emergency pause."""
import json

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW
from tests.test_telegram_groups import bind,group_update


def test_mobile_group_registration_consent_and_pause_without_scripts(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'admin@test.local')
    for capability in ('INBOUND','DELIVERY','LINK','GROUPS'):
        monkeypatch.setenv('CSS_TELEGRAM_'+capability+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'member_status',lambda *args:'administrator')
    monkeypatch.setattr(bot.transport,'send',lambda *args:(_ for _ in ()).throw(AssertionError('Unexpected provider send')))
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        monkeypatch.setattr(links,'origin',lambda:base)  # Isolated local HTTP harness; production requires HTTPS.
        bind(c,user,101)
        value=group_update(topic=7)
        bot.receive(c,bot.normalize(value),json.dumps(value).encode(),bot.transport.config(),NOW)
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        page=context.new_page()
        try:
            response=page.goto(base+'/account/telegram/groups')
            assert response.status==200
            assert 'Group -100 · Topic 7' in page.locator('body').inner_text()
            page.get_by_label('Purpose',exact=True).fill('Synthetic internal coordination')
            page.get_by_label('I own this connection and approve these shared-audience rules for all current and future members.').check()
            page.get_by_role('button',name='Verify administrators and register',exact=True).click()
            assert rows(c,'SELECT * FROM telegram_group')[0]['state']=='active'
            assert 'Status: active' in page.locator('body').inner_text()
            monkeypatch.setenv('CSS_TELEGRAM_GROUPS_ENABLED','0')
            page.reload()
            assert 'Group registration and replies are paused' in page.locator('body').inner_text()
            page.get_by_role('button',name='Pause registration',exact=True).click()
            assert rows(c,'SELECT * FROM telegram_group')[0]['state']=='paused'
            page.get_by_role('button',name='Revoke registration',exact=True).click()
            assert rows(c,'SELECT * FROM telegram_group')[0]['state']=='revoked'
            assert TOKEN not in page.content() and SECRET not in page.content()
        finally:
            context.close();c.close()
