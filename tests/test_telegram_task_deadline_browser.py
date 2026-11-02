"""Phone lead-authorized deadline set/clear through exact private replies, no JavaScript."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_task_deadline as deadlines
import work
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('mode',['set','clear'])
def test_phone_lead_changes_internal_deadline_without_assigning_or_changing_state(grid_browser,app_mod,monkeypatch,mode):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    owner=st.get_admin_user(c,'encoder@test.local');officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_DEADLINE'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic deadline unit','division','SYNTHETIC/DEADLINE')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic deadline work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],user['id'],'Synthetic source lead confirmation')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic phone deadline task','expected_output':'DoNotExposeCriteria',
                                           'unit_id':unit,'proposed_owner_id':owner['id'],'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':owner['id'],'reason':'Synthetic assignment'})
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        number=0
        def command(text):
            nonlocal number
            number+=1
            response=httpx.post(base+bot.PATH,json=update(number,text=text),headers=HEADERS)
            assert response.status_code==200
            return response.json()
        code=re.search(r'(?m)^[a-f0-9]{64}$',command('/start')['text'])[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(code)
            for scope in ('work.read',deadlines.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',deadlines.ACTION}
            response=page.goto(command('/task_deadline')['text'].splitlines()[-1])
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            form=page.locator('form[action="'+deadlines.PATH+'change"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),task_id=str(task['id']),deadline_mode=mode,
                          due_date='2026-10-29' if mode=='set' else '',reason='Synthetic revised internal deadline')
            url=base+deadlines.PATH+'change';headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'owner_id':str(user['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            page.get_by_label('Task number',exact=True).fill(str(task['id']))
            page.get_by_label('Deadline action',exact=True).select_option(mode)
            if mode=='set':page.get_by_label('New task deadline',exact=True).fill('2026-10-29')
            page.get_by_label('Reason for the deadline change',exact=True).fill('Synthetic revised internal deadline')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text()
            assert 'No task deadline has changed' in body
            op=re.search(r'/deadline_preview ([a-f0-9]{32})',body)[1]
            assert rows(c,'SELECT due_date FROM work_task WHERE id=?',(task['id'],))[0]['due_date']=='2026-10-28'
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/deadline_preview '+op)['text']
            assert '2026-10-28' in text and ('2026-10-29' if mode=='set' else 'explicitly removed') in text
            assert 'DoNotExposeCriteria' not in text and 'Synthetic revised internal deadline' in text
            exact=re.search(r'/deadline_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome:' in command(exact)['text']
            assert 'Recorded outcome:' in command(exact)['text']
            current=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
            assert current['due_date']==('2026-10-29' if mode=='set' else None)
            assert current['owner_id']==owner['id'] and current['status']=='todo'
            assert current['expected_output']==task['expected_output'] and current['revision']==task['revision']+1
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies()
            assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
