"""No-script phone work/task comments require exact private confirmation and separate grants."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_comment_manage as comments
import telegram_reply_manage as replies
import telegram_mentions as mentions
import work
import work_tasks
import work_discussion as discussion
import work_updates
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('mode',['work','task'])
@pytest.mark.parametrize('kind',['comment','reply'])
def test_phone_selected_mentions_after_exact_private_preview(grid_browser,app_mod,monkeypatch,mode,kind):
    manage=comments if kind=='comment' else replies
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_MENTIONS',manage.MODES[mode].replace('.','_').upper()):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic comment unit','division','SYNTHETIC/COMMENT')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic comment work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],officer['id'],'Other source lead')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic comment task','expected_output':'StoredPrivateOutput','unit_id':unit,'due_date':'2026-10-28'})
    parent=discussion.post(c,officer,item['id'],'StoredPrivateParentText',task_id=task['id'] if mode=='task' else None) if kind=='reply' else None
    initial_count=1 if kind=='reply' else 0
    comment='Actor-entered '+mode+' comment\n<script>plain text</script> @plain-name'
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
            for scope in ('work.read',manage.MODES[mode],mentions.SCOPE):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',manage.MODES[mode],mentions.SCOPE}
            text=command('/menu')['text'];assert '/'+mode+'_'+kind in text
            other='task' if mode=='work' else 'work';assert '/'+other+'_'+kind not in text
            page.goto(command('/'+mode+'_'+kind)['text'].splitlines()[-1])
            page.get_by_label('Work item number for recipient choices',exact=True).fill(str(item['id']))
            if mode=='task':page.get_by_label('Task number for recipient choices',exact=True).fill(str(task['id']))
            if kind=='reply':page.get_by_label('Parent comment number for recipient choices (optional)',exact=True).fill(str(parent))
            page.get_by_role('button',name='Load eligible colleagues',exact=True).click()
            assert 'body=' not in page.url and len(rows(c,'SELECT * FROM work_comment'))==initial_count
            assert not rows(c,'SELECT * FROM telegram_operation')
            form=page.locator('form[method=post][action="'+manage.PATH+mode+'"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),body=comment,mentions=str(officer['id']))
            if kind=='reply':values['parent_id']=str(parent)
            if mode=='task':values['task_id']=str(task['id'])
            url=base+manage.PATH+mode;headers={'Origin':base}
            assert page.request.post(url,form={**values,'csrf':'bad'},headers=headers).status==400
            assert page.request.post(url,form={**values,'mentions':'999999'},headers=headers).status==400
            assert page.request.post(url,form={**values,'owner_id':str(user['id'])},headers=headers).status==400
            if mode=='work':assert page.request.post(url,form={**values,'task_id':str(task['id'])},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation') and len(rows(c,'SELECT * FROM work_comment'))==initial_count
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            if mode=='task':page.get_by_label('Task number',exact=True).fill(str(task['id']))
            else:assert page.get_by_label('Task number',exact=True).count()==0
            if kind=='reply':page.get_by_label('Reply to comment number',exact=True).fill(str(parent))
            page.get_by_label('Comment text' if kind=='comment' else 'Reply text',exact=True).fill(comment)
            boxes=form.locator('input[name=mentions]');assert boxes.count()>0
            assert all(not boxes.nth(i).is_checked() for i in range(boxes.count()))
            form.locator('input[name=mentions][value=\"'+str(officer['id'])+'\"]').check()
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert ('No comment has been posted' if kind=='comment' else 'No reply has been posted') in body
            op=re.search('/'+mode+kind+r'_preview ([a-f0-9]{32})',body)[1]
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task and len(rows(c,'SELECT * FROM work_comment'))==initial_count
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command('/'+mode+kind+'_preview '+op)['text']
            assert comment in text and 'StoredPrivate' not in text and 'Selected colleague mentions:' in text and '(account '+str(officer['id'])+')' in text
            exact=re.search('/'+mode+kind+r'_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome:' in command(exact)['text'] and 'Recorded outcome:' in command(exact)['text']
            saved=rows(c,'SELECT * FROM work_comment ORDER BY id DESC LIMIT 1');assert len(rows(c,'SELECT * FROM work_comment'))==initial_count+1
            assert saved[0]['task_id']==(task['id'] if mode=='task' else None) and saved[0]['parent_id']==parent
            assert rows(c,'SELECT body FROM work_comment_revision WHERE comment_id=?',(saved[0]['id'],))[0]['body']==comment
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert rows(c,'SELECT * FROM work_case WHERE id=?',(item['id'],))[0]==item
            assert [p['user_id'] for p in work_updates.mentions(c,saved[0]['id'],1)]==[officer['id']]
            notices=rows(c,'SELECT * FROM work_notice WHERE comment_id=?',(saved[0]['id'],));assert len(notices)==1 and notices[0]['reason']=='mention'
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies();assert page.request.post(url,form=values,headers=headers).status==401
        finally:context.close();c.close()
