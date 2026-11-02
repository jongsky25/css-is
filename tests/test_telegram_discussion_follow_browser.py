"""No-script phone own follow/unfollow previews, exact scope and receipt recovery."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_follow as manage
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('task_level',[True,False])
@pytest.mark.parametrize('choice',['follow','unfollow'])
def test_phone_exact_own_discussion_follow_change(grid_browser,app_mod,monkeypatch,task_level,choice):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_FOLLOW'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic follow unit','division','SYNTHETIC/FOLLOW')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic discussion following','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic follow task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    task_id=task['id'] if task_level else None
    if choice=='unfollow':work_updates.follow(c,user,item['id'],task_id)
    if task_level and choice=='unfollow':work_updates.follow(c,user,item['id'])
    before=list(c.execute('SELECT * FROM work_follow'))
    with live_app(app_mod.app) as base:
        monkeypatch.setenv('CSS_BASE_URL',base);monkeypatch.setattr(links,'origin',lambda:base)
        number=0
        def command(text):
            nonlocal number
            number+=1;r=httpx.post(base+bot.PATH,json=update(number,text=text),headers=HEADERS)
            assert r.status_code==200
            return r.json()
        code=re.search(r'(?m)^[a-f0-9]{64}$',command('/start')['text'])[0]
        context=grid_browser.new_context(viewport={'width':390,'height':844},java_script_enabled=False)
        context.add_cookies([{'name':auth.COOKIE_NAME,'value':session_token(user),'url':base}]);page=context.new_page()
        try:
            page.goto(base+'/account/telegram');page.get_by_label('Private linking code',exact=True).fill(code)
            for scope in ('work.read',manage.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',manage.ACTION}
            text=command('/menu')['text'];assert '/discussion_follow' in text and '/my_updates' not in text
            page.goto(command('/discussion_follow')['text'].splitlines()[-1])
            form=page.locator('form[action="'+manage.PATH+'change"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(case_id=str(item['id']),task_id=str(task_id) if task_id else '',choice=choice)
            url=base+manage.PATH+'change';headers={'Origin':base}
            for bad in ({'csrf':'bad'},{'choice':'toggle'},{'task_id':'999999'},{'user_id':str(other['id'])}):
                assert page.request.post(url,form={**values,**bad},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation') and before==list(c.execute('SELECT * FROM work_follow'))
            page.get_by_label('Work item number',exact=True).fill(str(item['id']))
            if task_id:page.get_by_label('Task number (optional)',exact=True).fill(str(task_id))
            page.get_by_label('Change',exact=True).select_option(choice)
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'Following has not changed' in body
            op=re.search(r'/discussionfollow_preview ([a-f0-9]{32})',body)[1]
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert before==list(c.execute('SELECT * FROM work_follow'))
            text=command('/discussionfollow_preview '+op)['text']
            assert 'StoredPrivate' not in text and ('off → on' if choice=='follow' else 'on → off') in text
            assert ('Task '+str(task_id) in text) if task_id else 'includes work-level and all task discussions' in text
            if task_id and choice=='unfollow':assert 'work-wide follow is currently on' in text
            confirmation=re.search(r'/discussionfollow_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome: discussion '+('followed' if choice=='follow' else 'unfollowed') in command(confirmation)['text']
            after=list(c.execute('SELECT * FROM work_follow'))
            assert 'Recorded outcome:' in command(confirmation)['text'] and 'Recorded outcome:' in command('/discussionfollow_receipt '+op)['text']
            assert after==list(c.execute('SELECT * FROM work_follow'))
            assert work_updates.following(c,user,item['id'],task_id)==(choice=='follow')
            cid=discussion.post(c,other,item['id'],'StoredPrivateFuturePost',task_id=task_id)
            notice=rows(c,'SELECT * FROM work_notice WHERE comment_id=? AND user_id=?',(cid,user['id']))
            assert bool(notice)==(choice=='follow' or task_level)
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command('/discussion_follow')
            assert after==list(c.execute('SELECT * FROM work_follow'))
        finally:context.close();c.close()
