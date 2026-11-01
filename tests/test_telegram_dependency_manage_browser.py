"""Phone prerequisite guides preserve coordinator rules and independent confirmation."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_dependency_manage as manage
import work
import work_tasks
import work_blockers as blockers
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('mode',['add','remove'])
def test_phone_coordinator_amends_prerequisite_after_exact_private_preview(grid_browser,app_mod,monkeypatch,mode):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    other=st.get_admin_user(c,'encoder@test.local');officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_DEPENDENCY_'+mode.upper()):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic dependency change unit','division','SYNTHETIC/DEPENDENCY-CHANGE')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic dependency change work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],user['id'],'Confirmed source lead')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic dependency change task','expected_output':'DoNotExposeCriteria','unit_id':unit,'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':user['id'],'reason':'Source task owner'})
    prerequisite=work_tasks.create(c,user,item['id'],{'title':'Synthetic prerequisite','expected_output':'PrivatePrerequisiteOutput','unit_id':unit})
    if mode=='remove':task=blockers.mutate(c,user,item['id'],task['id'],task['revision'],'dependency_add',{'reason':'StoredPrivateDependencyReason','prerequisite_id':prerequisite['id']})
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
            page.goto(base+'/account/telegram');page.get_by_label('Private linking code',exact=True).fill(code)
            for scope in ('work.read',manage.MODES[mode]):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',manage.MODES[mode]}
            text=command('/menu')['text'];assert '/task_dependency_'+mode in text
            other_mode='remove' if mode=='add' else 'add';assert '/task_dependency_'+other_mode not in text
            page.goto(command('/task_dependency_'+mode)['text'].splitlines()[-1])
            form=page.locator('form[action="'+manage.PATH+mode+'"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),task_id=str(task['id']),prerequisite_id=str(prerequisite['id']),reason='Actor-entered '+mode+' reason')
            url=base+manage.PATH+mode;headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'due_date':'2026-10-31'},headers=headers).status==400
            assert page.request.post(url,form={**values,'prerequisite_id':str(task['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            page.get_by_label('Dependent task number',exact=True).fill(str(task['id']))
            page.get_by_label('Prerequisite task number',exact=True).fill(str(prerequisite['id']))
            page.get_by_label('Dependency change reason',exact=True).fill('Actor-entered '+mode+' reason')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'No dependency has changed' in body
            op=re.search('/taskdep'+mode+r'_preview ([a-f0-9]{32})',body)[1]
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/taskdep'+mode+'_preview '+op)['text']
            assert 'Actor-entered '+mode+' reason' in text and 'StoredPrivateDependencyReason' not in text and 'DoNotExposeCriteria' not in text
            exact=re.search('/taskdep'+mode+r'_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome:' in command(exact)['text'] and 'Recorded outcome:' in command(exact)['text']
            changed=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
            assert bool(c.execute('SELECT 1 FROM work_dependency WHERE task_id=? AND prerequisite_id=?',(task['id'],prerequisite['id'])).fetchone())==(mode=='add')
            for field in ('owner_id','status','due_date','submission','expected_output','blocker_reason','blocker_owner_id','blocker_due_date'):assert changed[field]==task[field]
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies();assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
