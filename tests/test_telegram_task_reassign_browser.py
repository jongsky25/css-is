"""Phone officer transfer makes the status reset explicit and preserves submission history."""
import re

import httpx
import pytest

import auth
import documents as docs
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_task_reassign as reassignment
import work
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('state',['in_progress','for_review'])
def test_phone_officer_transfers_with_explicit_status_reset_and_preserved_submission(grid_browser,app_mod,monkeypatch,state):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    owner=st.get_admin_user(c,'encoder@test.local');suggested=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_REASSIGN'):
        monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic transfer unit','division','SYNTHETIC/TRANSFER')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(user['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic transfer work','outcome':'Shared result','unit_id':unit})
    doc=docs.register(c,user,{'subject':'Synthetic transfer source','type':'request','unit_id':unit})
    doc=docs.mutate(c,user,doc['id'],doc['revision'],'access',
                    {'visibility':'restricted','viewers':[user['id'],suggested['id'],owner['id']],'reason':'Synthetic existing access'})
    item=work.link_document(c,user,item['id'],item['revision'],doc['id'])
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic phone transfer','expected_output':'DoNotExposeCriteria',
                                           'unit_id':unit,'proposed_owner_id':suggested['id'],'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,user,item['id'],task['id'],task['revision'],'confirm',{'owner_id':suggested['id'],'reason':'Initial source owner'})
    task=work_tasks.mutate(c,suggested,item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Source progress'})
    if state=='for_review':task=work_tasks.mutate(c,suggested,item['id'],task['id'],task['revision'],'submit',{'reason':'Submit source','submission':'DoNotExposeSubmission'})
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
            for scope in ('work.read',reassignment.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',reassignment.ACTION}
            response=page.goto(command('/task_reassign')['text'].splitlines()[-1])
            assert response.status==200 and 'no-store' in response.headers['cache-control']
            assert 'Reassignment returns the task to To do' in page.locator('body').inner_text()
            form=page.locator('form[action="'+reassignment.PATH+'reassign"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),task_id=str(task['id']),owner_id=str(owner['id']),reason='Synthetic officer transfer')
            url=base+reassignment.PATH+'reassign';headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'due_date':'2026-10-29'},headers=headers).status==400
            assert page.request.post(url,form={**values,'owner_id':''},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            page.get_by_label('Task number',exact=True).fill(str(task['id']))
            assert page.get_by_label('New task owner',exact=True).input_value()==''
            page.get_by_label('New task owner',exact=True).select_option(str(owner['id']))
            page.get_by_label('Reassignment reason',exact=True).fill('Synthetic officer transfer')
            saved_access=list(c.execute('SELECT * FROM document_access'))
            saved_doc=rows(c,'SELECT * FROM document WHERE id=?',(doc['id'],))[0]
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text()
            assert 'No task has been reassigned' in body
            op=re.search(r'/taskreassign_preview ([a-f0-9]{32})',body)[1]
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/taskreassign_preview '+op)['text']
            assert 'New status: to do' in text and state.replace('_',' ') in text and 'returns the task to To do' in text
            assert 'Current owner account: '+str(suggested['id']) in text and '(account '+str(owner['id'])+')' in text
            assert '2026-10-28' in text and 'DoNotExposeSubmission' not in text
            assert 'DoNotExposeCriteria' not in text and 'Synthetic officer transfer' in text
            exact=re.search(r'/taskreassign_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome:' in command(exact)['text']
            assert 'Recorded outcome:' in command(exact)['text']
            current=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
            assert current['owner_id']==owner['id'] and current['status']=='todo' and current['revision']==task['revision']+1
            for key in ('due_date','submission','expected_output','proposed_owner_id','mandatory'):assert current[key]==task[key]
            assert list(c.execute('SELECT * FROM document_access'))==saved_access
            assert rows(c,'SELECT * FROM document WHERE id=?',(doc['id'],))[0]==saved_doc
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies()
            assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
