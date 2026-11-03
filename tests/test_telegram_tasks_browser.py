"""Mobile submission preparation and confirmation through actual browser/webhook."""
import re

import httpx

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import work
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN, SECRET, NOW, update, HEADERS


def test_mobile_task_acknowledge_then_submit_without_scripts(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB)
    user=st.get_admin_user(c,'viewer@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_ACKNOWLEDGE','TASKS_SUBMIT'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a: (_ for _ in ()).throw(AssertionError('Outgoing send')))
    unit=st.add_org_unit(c,'Synthetic Telegram task unit','division','TELEGRAM/TASKS')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-11-01')",(user['id'],unit));c.commit()
    item=work.create(c,user,{'title':'Synthetic review work','outcome':'Synthetic result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic task','expected_output':'Evidence','unit_id':unit})
    task=work_tasks.mutate(c,user,item['id'],task['id'],task['revision'],'confirm',{'reason':'Synthetic assignment','owner_id':user['id']})
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        def command(text,number):
            response=httpx.post(base+bot.PATH,json=update(number,text=text),headers=HEADERS)
            assert response.status_code==200
            return response.json()
        packet=command('/start',1)
        code=re.search(r'(?m)^[a-f0-9]{64}$',packet['text'])[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}])
        page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code').fill(code)
            for label in ('Read my tasks and permitted work status in private','Acknowledge my task after private confirmation','Submit my task for review after private confirmation'):
                assert not page.get_by_label(label).is_checked()
                page.get_by_label(label).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.').check()
            page.get_by_role('button',name='Request confirmation in Telegram').click()
            packet=command('/status',2)
            command(re.search(r'/confirm [a-f0-9]{64}',packet['text'])[0],3)
            packet=command(f"/task_ack {item['id']} {task['id']}",4)
            packet=command(re.search(r'/task_confirm [A-Za-z0-9_-]{43}',packet['text'])[0],5)
            assert 'in_progress' in packet['text']
            guide=command(f"/task_submit {item['id']} {task['id']}",6)
            page.goto(guide['text'].splitlines()[-1])
            assert page.get_by_role('heading',name='Prepare task submission').is_visible()
            page.get_by_label('Output or evidence for review').fill('Synthetic browser output.')
            page.get_by_label('Submission note').fill('Please review the synthetic output.')
            # Stale or cross-site forms cannot prepare an action.
            form={e.get_attribute('name'):e.get_attribute('value') for e in page.locator('input').all()}
            form.update(submission='Synthetic browser output.',reason='Please review the synthetic output.')
            bad={**form,'csrf':'wrong'}
            response=httpx.post(base+'/account/telegram/task',data=bad,cookies={auth.COOKIE_NAME:session_token(user)},headers={'Origin':base})
            assert response.status_code in (400,403)
            page.get_by_role('button',name='Prepare private preview').click()
            assert 'No task has been submitted yet' in page.locator('body').inner_text()
            assert c.execute('SELECT status FROM work_task WHERE id=?',(task['id'],)).fetchone()[0]=='in_progress'
            operation=re.search(r'/task_preview ([a-f0-9]{32})',page.locator('body').inner_text())[1]
            packet=command('/task_preview '+operation,7)
            assert 'Synthetic browser output.' in packet['text']
            confirmation=re.search(r'/task_confirm [A-Za-z0-9_-]{43}',packet['text'])[0]
            assert 'task_submitted' in command(confirmation,8)['text']
            assert c.execute('SELECT status,submission FROM work_task WHERE id=?',(task['id'],)).fetchone()==('for_review','Synthetic browser output.')
            assert 'task_submitted' in command(confirmation,9)['text']
        finally:
            context.close();c.close()
