"""No-script phone same-thread replies require exact confirmation and independent consent."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_reply_manage as manage
import work
import work_tasks
import work_discussion as discussion
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('mode',['work','task'])
def test_phone_same_thread_reply_after_exact_private_preview(grid_browser,app_mod,monkeypatch,mode):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ',manage.MODES[mode].replace('.','_').upper()):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic comment unit','division','SYNTHETIC/COMMENT')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic comment work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],officer['id'],'Other source lead')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic comment task','expected_output':'StoredPrivateOutput','unit_id':unit,'due_date':'2026-10-28'})
    parent=discussion.post(c,officer,item['id'],'StoredPrivateParentText',task_id=task['id'] if mode=='task' else None)
    comment='Actor-entered '+mode+' reply\n<script>plain text</script> @plain-name'
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        number=0
        def command(text):
            nonlocal number
            number+=1;response=httpx.post(base+bot.PATH,json=update(number,text=text),headers=HEADERS)
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
            text=command('/menu')['text'];assert '/'+mode+'_reply' in text
            other='task' if mode=='work' else 'work';assert '/'+other+'_reply' not in text
            page.goto(base+'/work/'+str(item['id'])+'/discussion'+('?task_id='+str(task['id']) if mode=='task' else ''))
            assert 'Comment '+str(parent)+' · Revision 1' in page.locator('#message-'+str(parent)).inner_text()
            page.goto(command('/'+mode+'_reply')['text'].splitlines()[-1])
            form=page.locator('form[action="'+manage.PATH+mode+'"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),parent_id=str(parent),body=comment)
            if mode=='task':values['task_id']=str(task['id'])
            url=base+manage.PATH+mode;headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'parent_id':'999999'},headers=headers).status==400
            if mode=='work':assert page.request.post(url,form={**values,'task_id':str(task['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation') and len(rows(c,'SELECT * FROM work_comment'))==1
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            if mode=='task':page.get_by_label('Task number',exact=True).fill(str(task['id']))
            else:assert page.get_by_label('Task number',exact=True).count()==0
            page.get_by_label('Reply to comment number',exact=True).fill(str(parent))
            page.get_by_label('Reply text',exact=True).fill(comment)
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'No reply has been posted' in body
            op=re.search('/'+mode+r'reply_preview ([a-f0-9]{32})',body)[1]
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task and len(rows(c,'SELECT * FROM work_comment'))==1
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/'+mode+'reply_preview '+op)['text']
            assert comment in text and 'StoredPrivate' not in text and 'Reply to comment '+str(parent)+' · Revision 1' in text
            exact=re.search('/'+mode+r'reply_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome: reply posted.' in command(exact)['text'] and 'Recorded outcome:' in command(exact)['text']
            saved=rows(c,'SELECT * FROM work_comment WHERE parent_id=?',(parent,));assert len(saved)==1
            assert saved[0]['task_id']==(task['id'] if mode=='task' else None) and saved[0]['parent_id']==parent
            assert rows(c,'SELECT body FROM work_comment_revision WHERE comment_id=?',(saved[0]['id'],))[0]['body']==comment
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert rows(c,'SELECT * FROM work_case WHERE id=?',(item['id'],))[0]==item
            assert not rows(c,'SELECT * FROM work_mention') and not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies();assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
