"""Phone without scripts: current-user channel and quiet-hour controls while paused."""
import auth
import storage as st
import telegram_preferences as prefs
import telegram_bot as bot
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app


def test_mobile_channel_and_quiet_preferences_no_scripts_and_stale_form_denial(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    for capability in bot.storage.SWITCHES:monkeypatch.setenv('CSS_TELEGRAM_'+capability.upper()+'_ENABLED','0')
    monkeypatch.setattr(bot.transport,'send',lambda *a:(_ for _ in ()).throw(AssertionError('Preference form sent a message')))
    with live_app(app_mod.app) as base:
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            response=page.goto(base+'/account/telegram/notifications')
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            old={k:page.locator('form[action="/account/telegram/notifications"] input[name='+k+']').input_value() for k in ('csrf','revision','calendar_email_expected')}
            page.get_by_label('Calendar changes to me',exact=True).select_option('telegram')
            page.get_by_label('My room status updates',exact=True).select_option('email')
            page.get_by_label('Quiet hours start (Asia/Manila)',exact=True).fill('22:00')
            page.get_by_label('Quiet hours end (Asia/Manila)',exact=True).fill('07:00')
            page.get_by_label('Send approved shared calendar updates to groups I own',exact=True).uncheck()
            page.get_by_role('button',name='Save notification settings',exact=True).click()
            assert 'Notification settings saved' in page.locator('body').inner_text()
            result=prefs.get(c,user['id'])
            assert result['calendar_mode']=='telegram' and result['room_mode']=='email'
            assert result['quiet_start']=='22:00' and result['quiet_end']=='07:00' and not result['group_calendar']
            assert prefs.get(c,other['id'])['revision']==0
            assert not c.execute('SELECT count(*) FROM telegram_delivery').fetchone()[0]
            fields={**old,'calendar_mode':'off','room_mode':'off','quiet_start':'','quiet_end':''}
            stale=page.request.post(base+'/account/telegram/notifications',form=fields,headers={'Origin':base})
            assert stale.status==409
            fields['csrf']='invalid'
            assert page.request.post(base+'/account/telegram/notifications',form=fields,headers={'Origin':base}).status==400
            page.goto(base+'/me')
            assert not page.get_by_label("Email me when a calendar item I'm on is added, changed or cancelled",exact=True).is_checked()
            assert prefs.get(c,user['id'])['revision']==1
        finally:context.close();c.close()
