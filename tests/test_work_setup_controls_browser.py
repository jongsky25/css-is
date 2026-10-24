"""A phone-sized, script-disabled admin can resolve both module blockers."""
import json

import auth
import documents as docs
import send_reminders
import storage as st
import work
import work_channels as channels
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_documents_setup import setup_db
from tests.test_work_channels_browser import live_app


def test_admin_resolves_disabled_modules_then_can_pause_work_without_sending(grid_browser,app_mod,setup_db,monkeypatch,tmp_path):
    conn,users,path=setup_db;user=users[0]
    docs.bootstrap_admins(conn,user,docs.preview_admin_setup(conn,user,user['username'],'Owner appointment'))
    channels.save(conn,user,0,'off');binding=channels.preferences(conn,user)['binding']
    token='123456:'+('A'*35);chat='123456789'
    monkeypatch.setattr(app_mod,'DB',path)
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_ENABLED','1')
    monkeypatch.setenv('CSS_APPRISE_TELEGRAM_TARGETS',json.dumps({binding:{'bot_token':token,'chat_id':chat}}))
    monkeypatch.setattr(send_reminders,'_base_url',lambda:'https://office.example')
    attempts=[];monkeypatch.setattr(channels.transport,'send',lambda *args:attempts.append(args) or True)
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base)
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        page=context.new_page()
        try:
            page.goto(base+'/work/notification-preferences')
            assert 'Documents is disabled' in page.locator('.work-wrap').inner_text()
            assert 'Collaborative work is disabled' in page.locator('.work-wrap').inner_text()
            assert token not in page.content() and chat not in page.content()
            page.get_by_role('link',name='Open Documents and Collaborative work setup').click()
            assert page.get_by_role('button',name='Enable Collaborative work',exact=True).count()==0
            page.get_by_role('link',name='enable Documents in the Documents feature section below').click()
            form=page.locator('form').filter(has=page.locator('input[name="action"][value="enable_module"]'))
            form.locator('textarea[name="authorization"]').fill('Enable authorized discussion pilot')
            form.locator('input[name="confirmed"]').check();form.get_by_role('button',name='Enable Documents',exact=True).click()
            page.wait_for_url(base+'/admin/documents/setup*')
            page.get_by_role('link',name='Next: enable Collaborative work',exact=True).click()
            form=page.locator('form').filter(has=page.locator('input[name="action"][value="enable_work"]'))
            form.locator('textarea[name="authorization"]').fill('Enable shared-work discussion pilot')
            form.locator('input[name="confirmed"]').check();form.get_by_role('button',name='Enable Collaborative work',exact=True).click()
            page.wait_for_url('**/setup#collaborative-work')
            assert page.get_by_role('heading',name='Collaborative work',exact=True).bounding_box()['y']>=60
            assert work.enabled(conn) and st.get_setting(conn,'documents.sending_enabled')=='0'
            page.get_by_role('link',name='Return to notification preferences').click()
            assert 'Telegram is configured for your account.' in page.locator('.work-wrap').inner_text()
            page.screenshot(path=str(tmp_path/'telegram-configured-mobile.png'),full_page=True)
            page.goto(base+'/admin/documents/setup#collaborative-work')
            page.screenshot(path=str(tmp_path/'work-controls-mobile.png'),full_page=True)
            form=page.locator('form').filter(has=page.locator('input[name="action"][value="disable_work"]'))
            form.locator('textarea[name="authorization"]').fill('Pause discussion pilot')
            form.locator('input[name="confirmed"]').check();form.get_by_role('button',name='Disable Collaborative work',exact=True).click()
            page.wait_for_url('**/setup#collaborative-work')
            page.get_by_role('link',name='Return to notification preferences').click()
            text=page.locator('.work-wrap').inner_text()
            assert 'Collaborative work is disabled' in text and 'Documents is disabled' not in text
            assert docs.enabled(conn) and not work.enabled(conn) and not attempts
        finally:context.close()
