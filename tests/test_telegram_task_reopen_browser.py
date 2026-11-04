"""Phone coordinator-authorized reopening of an accepted task through exact private replies, no JavaScript."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_task_reopen as reopening
import work
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('actor_kind',['lead','officer'])
def test_phone_coordinator_reopens_without_replacing_owner_or_submission(grid_browser,app_mod,monkeypatch,actor_kind):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    owner=st.get_admin_user(c,'encoder@test.local');officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_REOPEN'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic review unit','division','SYNTHETIC/REVIEW')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic review work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],user['id'],'Synthetic source lead confirmation')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic phone review task','expected_output':'DoNotExposeCriteria',
                                           'unit_id':unit,'proposed_owner_id':owner['id'],'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':owner['id'],'reason':'Synthetic assignment'})
    task=work_tasks.mutate(c,owner,item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Start synthetic work'})
    task=work_tasks.mutate(c,owner,item['id'],task['id'],task['revision'],'submit',{'reason':'Submit synthetic work','submission':'DoNotExposeSubmission'})
    task=work_tasks.mutate(c,user,item['id'],task['id'],task['revision'],'accept',{'reason':'Source acceptance'})
    if actor_kind=='officer':
        item=work.confirm_lead(c,officer,item['id'],item['revision'],owner['id'],'Different case lead')
        c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(user['id'],unit,links.stamp(NOW)));c.commit()
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
            for scope in ('work.read',reopening.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',reopening.ACTION}
            response=page.goto(command('/task_reopen')['text'].splitlines()[-1])
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            form=page.locator('form[action="'+reopening.PATH+'reopen"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),task_id=str(task['id']),reason='Synthetic reopening reason')
            url=base+reopening.PATH+'reopen';headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'owner_id':str(user['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            page.get_by_label('Task number',exact=True).fill(str(task['id']))
            page.get_by_label('Reopening reason',exact=True).fill('Synthetic reopening reason')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text()
            assert 'No task has been reopened' in body
            op=re.search(r'/taskreopen_preview ([a-f0-9]{32})',body)[1]
            assert rows(c,'SELECT due_date FROM work_task WHERE id=?',(task['id'],))[0]['due_date']=='2026-10-28'
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/taskreopen_preview '+op)['text']
            assert 'Current status: done' in text and 'New status: in progress' in text
            assert 'existing submission' in text.lower()
            assert 'DoNotExposeCriteria' not in text and 'Synthetic reopening reason' in text and 'DoNotExposeSubmission' not in text
            exact=re.search(r'/taskreopen_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome:' in command(exact)['text']
            assert 'Recorded outcome:' in command(exact)['text']
            current=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
            assert current['due_date']==task['due_date'] and current['submission']==task['submission']
            assert current['owner_id']==owner['id'] and current['status']=='in_progress'
            assert current['expected_output']==task['expected_output'] and current['revision']==task['revision']+1
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies()
            assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
