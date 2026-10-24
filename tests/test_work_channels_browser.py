"""Native redirects and personal setup/disconnect against an actual local server."""
from contextlib import contextmanager
import json
import socket
from threading import Thread
import time

import uvicorn
import auth
import storage as st
import send_reminders
import work_channels as channels
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser

BOT='123456:'+('A'*35)
CHAT='123456789'


@contextmanager
def live_app(app):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error',access_log=False,lifespan='off'))
    thread=Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    deadline=time.monotonic()+10
    while not server.started and thread.is_alive() and time.monotonic()<deadline:time.sleep(.01)
    assert server.started,'Local test server failed to start'
    try:yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit=True;thread.join(timeout=5);sock.close()
        assert not thread.is_alive(),'Local test server failed to stop'


def test_private_channel_mobile_preferences_conflicts_disconnect_and_no_script(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    st.set_setting(c,'work.enabled','1');st.set_setting(c,'documents.enabled','1')
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_ENABLED','1')
    monkeypatch.setattr(send_reminders,'_base_url',lambda:'https://office.example')
    attempts=[];monkeypatch.setattr(channels.transport,'send',lambda *args:attempts.append(args) or True)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        context=grid_browser.new_context(viewport={'width':390,'height':844})
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            response=page.goto(base+'/work/notification-preferences')
            assert response.status==200 and response.headers['cache-control']=='no-store'
            assert page.locator('#telegram-cadence').input_value()=='off'
            assert page.locator('details code').count()==0
            page.select_option('#telegram-cadence','daily')
            page.get_by_role('button',name='Save Telegram preference',exact=True).click()
            page.wait_for_url('**/work/notification-preferences?saved=true')
            binding=page.locator('details code').text_content()
            assert len(binding)==32 and page.locator('#digest').input_value()=='off'
            monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps({binding:{'bot_token':BOT,'chat_id':CHAT}}))
            page.reload();assert 'Telegram is configured for your account.' in page.locator('.work-wrap').inner_text()
            assert BOT not in page.content() and CHAT not in page.content()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
            current=channels.preferences(c,user);channels.save(c,user,current['revision'],'weekly')
            page.select_option('#telegram-cadence','off')
            page.get_by_role('button',name='Save Telegram preference',exact=True).click()
            page.wait_for_function("document.body.textContent.includes('Your Telegram preferences changed')")
            assert page.locator('#telegram-cadence').input_value()=='weekly'
            session=page.context.new_cdp_session(page);session.send('Emulation.setScriptExecutionDisabled',{'value':True})
            page.get_by_role('button',name='Disconnect Telegram',exact=True).click()
            page.wait_for_url('**/work/notification-preferences?saved=true')
            assert page.locator('#telegram-cadence').input_value()=='off'
            assert page.locator('details code').text_content()!=binding
            assert 'Your current setup code has no entry' in page.locator('.work-wrap').inner_text()
            assert not attempts and not errors
        finally:context.close()
    c.close()
