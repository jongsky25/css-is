"""Real script-free phone creation: proposal only, separate consent and exact confirmation."""
import re

import httpx

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_task_create as create
import work
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


def test_phone_proposal_form_preview_and_confirm_preserves_officer_assignment(grid_browser,app_mod,monkeypatch):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    other=st.get_admin_user(c,'encoder@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_CREATE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    def forbidden(*a):raise AssertionError('Task proposal used outgoing Telegram')
    monkeypatch.setattr(bot.transport,'send',forbidden)
    unit=st.add_org_unit(c,'Synthetic task unit','division','SYNTHETIC/TASK')
    item=work.create(c,user,{'title':'Synthetic phone work','outcome':'Expected shared result','unit_id':unit})
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        number=0
        def command(text):
            nonlocal number
            number+=1
            response=httpx.post(base+bot.PATH,json=update(number,text=text),headers=HEADERS)
            assert response.status_code==200
            return response.json()
        packet=command('/start');code=re.search(r'(?m)^[a-f0-9]{64}$',packet['text'])[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(code)
            for scope in ('work.read','tasks.create'):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read','tasks.create'}
            response=page.goto(command('/new_task')['text'].splitlines()[-1])
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            form=page.locator('form[action="'+create.PATH+'create"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),title='Synthetic phone task',expected_output='First line\r\nSecond line',
                          unit_id=str(unit),proposed_owner_id=str(other['id']),due_date='2026-10-28')
            url=base+create.PATH+'create';headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'owner_id':str(user['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            page.get_by_label('Task title',exact=True).fill('Synthetic phone task')
            page.get_by_label('Expected output',exact=True).fill('First line\nSecond line')
            page.get_by_label('Contributing unit',exact=True).select_option(str(unit))
            page.get_by_label('Proposed owner (optional)',exact=True).select_option(str(other['id']))
            page.get_by_label('Task deadline (optional)',exact=True).fill('2026-10-28')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text()
            assert 'No task has been created' in body
            op=re.search(r'/newtask_preview ([a-f0-9]{32})',body)[1]
            assert not rows(c,'SELECT * FROM work_task')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/newtask_preview '+op)['text']
            assert 'Synthetic phone task' in text and 'First line\nSecond line' in text and '2026-10-28' in text
            assert 'officer must confirm' in text
            exact=re.search(r'/newtask_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Current status: proposed' in command(exact)['text']
            assert 'Recorded outcome:' in command(exact)['text']
            task=rows(c,'SELECT * FROM work_task')[0]
            assert task['status']=='proposed' and task['owner_id'] is None and task['proposed_owner_id']==other['id']
            assert task['expected_output']=='First line\nSecond line'
            assert len(rows(c,'SELECT * FROM work_task'))==1
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies()
            assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
