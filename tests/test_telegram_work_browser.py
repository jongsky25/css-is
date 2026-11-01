"""Phone consent and private work lookup without JavaScript or outgoing sends."""
import re

import httpx
import pytest

import auth
import storage as st
import telegram_bot as bot
import telegram_links as links
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN, SECRET, NOW, update, HEADERS


@pytest.mark.parametrize('scope,label,command,empty',[
    ('work.read','Read my tasks and permitted work status in private','/my_summary','Overdue tasks: 0'),
    ('documents.read','Read permitted document metadata and status in private','/documents','No matching documents'),
    ('supplies.read','Read my supply request approval and collection status in private','/my_supplies','No requests on this page')])
def test_phone_can_consent_to_private_reads_without_outgoing(grid_browser, app_mod, monkeypatch,scope,label,command,empty):
    c = st.connect(app_mod.DB)
    user = st.get_admin_user(c, 'viewer@test.local')
    for capability in ('INBOUND', 'DELIVERY', 'LINK', 'WORK_READ', 'DOCUMENTS_READ', 'SUPPLIES_READ'):
        monkeypatch.setenv('CSS_TELEGRAM_' + capability + '_ENABLED', '1')
    for module in ('documents', 'work', 'supplies'):
        st.set_setting(c, module + '.enabled', '1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT', 'webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET', SECRET)
    monkeypatch.setattr(bot, 'now_utc', lambda: NOW)
    def forbidden(*args):
        raise AssertionError('Lookup required an outgoing connection')
    monkeypatch.setattr(bot.transport, 'send', forbidden)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL', base)
        monkeypatch.setattr(links, 'origin', lambda: base)
        packet = httpx.post(base + bot.PATH, json=update(), headers=HEADERS).json()
        code = re.search(r'(?m)^[a-f0-9]{64}$', packet['text'])[0]
        context = grid_browser.new_context(viewport={'width':390,'height':844}, java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        page = context.new_page()
        try:
            page.goto(base + '/account/telegram')
            checkbox = page.get_by_label(label)
            assert not checkbox.is_checked()
            checkbox.check()
            page.get_by_label('Private linking code').fill(code)
            page.get_by_label('Link this Office Connect account to my own private Telegram account.').check()
            page.get_by_role('button', name='Request confirmation in Telegram').click()
            assert 'awaiting confirmation' in page.locator('body').inner_text()
            packet = httpx.post(base + bot.PATH, json=update(2,text='/status'), headers=HEADERS).json()
            confirmation = re.search(r'/confirm [a-f0-9]{64}', packet['text'])[0]
            packet = httpx.post(base + bot.PATH, json=update(3,text=confirmation), headers=HEADERS).json()
            assert packet['method'] == 'sendMessage'
            page.reload()
            assert command in page.locator('body').inner_text()
            assert c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL').fetchall() == [(scope,)]
            packet = httpx.post(base + bot.PATH, json=update(4,text=command), headers=HEADERS).json()
            assert empty in packet['text']
            page.get_by_role('button', name='Disconnect Telegram and cancel pending links').click()
            packet = httpx.post(base + bot.PATH, json=update(5,text=command), headers=HEADERS).json()
            assert 'method' not in packet
        finally:
            context.close()
            c.close()
