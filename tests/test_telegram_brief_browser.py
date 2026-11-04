"""Phone-width, script-free own-account staged brief controls; no delivery."""
import auth
import storage as st
import telegram_bot as bot
import telegram_brief_preferences as prefs
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app


def test_phone_brief_choices_ownership_csrf_stale_session_and_no_sending(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB)
    user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    for capability in bot.storage.SWITCHES:monkeypatch.setenv('CSS_TELEGRAM_'+capability.upper()+'_ENABLED','0')
    monkeypatch.setattr(bot.transport,'send',lambda *a:(_ for _ in ()).throw(AssertionError('Saving sent a brief')))
    with live_app(app_mod.app) as base:
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            response=page.goto(base+'/account/telegram/notifications')
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            form=page.locator('form[action="/account/telegram/notifications/brief"]')
            old={k:form.locator('input[name='+k+']').input_value() for k in ('csrf','revision')}
            assert not form.locator('[name=reminder_requested]').is_checked()
            form.locator('[name=reminder_requested]').check()
            page.get_by_label('My request statuses',exact=True).uncheck()
            page.get_by_label('Preferred daily brief time (Asia/Manila)',exact=True).fill('07:30')
            page.get_by_role('button',name='Save daily brief choices',exact=True).click()
            assert 'Daily brief choices saved. Scheduled delivery is not active.' in page.locator('body').inner_text()
            result=prefs.get(c,user['id'])
            assert result['reminder_requested']==1 and result['local_time']=='07:30' and not result['requests']
            assert prefs.get(c,other['id'])['revision']==0
            assert not c.execute('SELECT count(*) FROM telegram_delivery').fetchone()[0]
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            url=base+'/account/telegram/notifications/brief';headers={'Origin':base}
            values={**old,'local_time':'07:30','calendar':'1','work':'1'}
            assert page.request.post(url,form=values,headers=headers).status==409
            current={**values,'revision':'1'}
            for changes in ({'csrf':'bad'},{'user_id':str(other['id'])},{'local_time':'invalid'},{'calendar':'2'}):
                assert page.request.post(url,form={**current,**changes},headers=headers).status==400
            assert prefs.get(c,user['id'])['revision']==1
            context.clear_cookies()
            assert page.request.post(url,form=current,headers=headers).status==401
            assert prefs.get(c,user['id'])['revision']==1
        finally:context.close();c.close()
