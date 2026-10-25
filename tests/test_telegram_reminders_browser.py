"""Phone without scripts: explicit private reminder opt-ins while pilots are paused."""
import auth
import storage as st
import telegram_bot as bot
import telegram_reminders as reminders
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app


def test_mobile_private_reminder_form_ownership_csrf_stale_and_no_scripts(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    for capability in bot.storage.SWITCHES:monkeypatch.setenv('CSS_TELEGRAM_'+capability.upper()+'_ENABLED','0')
    monkeypatch.setattr(bot.transport,'send',lambda *a:(_ for _ in ()).throw(AssertionError('Saving sent a reminder')))
    with live_app(app_mod.app) as base:
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            response=page.goto(base+'/account/telegram/notifications');assert response.status==200
            form=page.locator('form[action="/account/telegram/notifications/reminders"]')
            old={k:form.locator('input[name='+k+']').input_value() for k in ('csrf','revision')}
            assert page.get_by_label('Remind me before my timed calendar entries',exact=True).input_value()=='0'
            page.get_by_label('Remind me before my timed calendar entries',exact=True).select_option('30')
            page.get_by_label('Remind me before my approved room bookings',exact=True).select_option('1440')
            page.get_by_role('button',name='Save reminder settings',exact=True).click()
            assert 'Notification settings saved' in page.locator('body').inner_text()
            p=reminders.get(c,user['id']);assert p['calendar_minutes']==30 and p['room_minutes']==1440
            assert reminders.get(c,other['id'])['revision']==0 and not c.execute('SELECT count(*) FROM telegram_delivery').fetchone()[0]
            url=base+'/account/telegram/notifications/reminders';headers={'Origin':base}
            assert page.request.post(url,form={**old,'calendar_minutes':'0','room_minutes':'0'},headers=headers).status==409
            current={'csrf':old['csrf'],'revision':'1','calendar_minutes':'60','room_minutes':'15'}
            assert page.request.post(url,form={**current,'user_id':str(other['id'])},headers=headers).status==400
            assert page.request.post(url,form={**current,'calendar_minutes':'5'},headers=headers).status==400
            assert page.request.post(url,form={**current,'csrf':'bad'},headers=headers).status==400
            assert reminders.get(c,user['id'])['revision']==1
            context.clear_cookies()
            assert page.request.post(url,form=current,headers=headers).status==401
            assert reminders.get(c,user['id'])['revision']==1
        finally:context.close();c.close()
