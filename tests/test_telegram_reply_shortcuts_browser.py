"""No-script thread-to-reply shortcuts still require native private preview/confirmation."""
import re
from urllib.parse import urlparse,parse_qs

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_read as reader
import telegram_reply_manage as replies
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('task_level',[True,False])
@pytest.mark.parametrize('reply_to_child',[True,False])
def test_phone_reply_shortcut_has_source_only_prefill_and_native_confirmation(grid_browser,app_mod,monkeypatch,task_level,reply_to_child):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local');mode='task' if task_level else 'work';scope=replies.MODES[mode]
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_DISCUSSION_READ',scope.replace('.','_').upper()):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic reply shortcut unit','division','SYNTHETIC/REPLYSHORTCUT')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic reply shortcut work','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic reply shortcut task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    target=task['id'] if task_level else None;query={'case_id':item['id'],'task_id':target}
    root=discussion.post(c,other,item['id'],'StoredPrivateRootText',task_id=target)
    child=discussion.post(c,other,item['id'],'StoredPrivateChildText',task_id=target,parent_id=root)
    parent=child if reply_to_child else root
    before={t:list(c.execute('SELECT * FROM '+t)) for t in ('work_follow','work_comment_read','work_notice','work_comment','work_comment_revision')}
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
            for selected in ('work.read',reader.ACTION,scope):page.get_by_label(links.SCOPES[selected],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',reader.ACTION,scope}
            text=command(reader.command(query,root))['text']
            urls=re.findall(r'(?:^|\n)Reply form: ([^\s]+)',text);assert len(urls)==2
            url=next(u for u in urls if u.endswith('&parent_id='+str(parent)))
            assert urlparse(url).path==replies.PATH+mode
            assert set(parse_qs(urlparse(url).query))==({'case_id','task_id','parent_id'} if task_level else {'case_id','parent_id'})
            assert 'StoredPrivate' not in url and 'origin=' not in url and 'body=' not in url
            page.goto(url);assert 'No current private request is available' in page.locator('body').inner_text()
            assert not rows(c,'SELECT * FROM telegram_meeting_origin') and not rows(c,'SELECT * FROM telegram_operation')
            for table,values in before.items():assert values==list(c.execute('SELECT * FROM '+table))
            command('/'+mode+'_reply')
            # Only source IDs are accepted from URL values, never draft text or mentions.
            page.goto(url+'&body=DoNotPrefillText&mentions='+str(other['id']))
            assert page.get_by_label('Work item number',exact=True).input_value()==str(item['id'])
            if task_level:assert page.get_by_label('Task number',exact=True).input_value()==str(task['id'])
            else:assert page.get_by_label('Task number',exact=True).count()==0
            assert page.get_by_label('Reply to comment number',exact=True).input_value()==str(parent)
            assert page.get_by_label('Reply text',exact=True).input_value()==''
            assert page.locator('input[name="mentions"]:checked').count()==0
            assert not rows(c,'SELECT * FROM telegram_operation')
            form=page.locator('form[action="'+replies.PATH+mode+'"]')
            data={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key','case_id','parent_id')}
            if task_level:data['task_id']=str(task['id'])
            data['body']='Actor-entered shortcut reply\n@literal is plain text'
            assert page.request.post(base+replies.PATH+mode,form={**data,'csrf':'bad'},headers={'Origin':base}).status==400
            assert page.request.post(base+replies.PATH+mode,form={**data,'revision':'1'},headers={'Origin':base}).status==400
            page.get_by_label('Reply text',exact=True).fill(data['body'])
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'No reply has been posted' in body
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            for table,values in before.items():assert values==list(c.execute('SELECT * FROM '+table))
            op=re.search('/'+mode+r'reply_preview ([a-f0-9]{32})',body)[1]
            preview=command('/'+mode+'reply_preview '+op)['text']
            assert 'Reply to comment '+str(parent)+' · Revision 1' in preview and data['body'] in preview and 'StoredPrivate' not in preview
            exact=re.search('/'+mode+r'reply_confirm [A-Za-z0-9_-]{43}',preview)[0]
            assert 'Recorded outcome: reply posted.' in command(exact)['text']
            after={t:list(c.execute('SELECT * FROM '+t)) for t in before}
            assert 'Recorded outcome: reply posted.' in command(exact)['text'] and after=={t:list(c.execute('SELECT * FROM '+t)) for t in before}
            saved=rows(c,'SELECT * FROM work_comment WHERE author_id=? AND parent_id=?',(user['id'],parent));assert len(saved)==1
            assert saved[0]['case_id']==item['id'] and saved[0]['task_id']==target
            assert rows(c,'SELECT body FROM work_comment_revision WHERE comment_id=?',(saved[0]['id'],))==[{'body':data['body']}]
            assert rows(c,'SELECT user_id,reason FROM work_notice WHERE comment_id=?',(saved[0]['id'],))==[{'user_id':other['id'],'reason':'reply'}]
            assert not rows(c,'SELECT * FROM work_mention') and work_updates.read_revision(c,user['id'],parent)==0
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task and rows(c,'SELECT * FROM work_case WHERE id=?',(item['id'],))[0]==item
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
        finally:context.close();c.close()
