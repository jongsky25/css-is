"""Phone independently consented current thread/reply and revision-bound message reading."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_read as reader
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('task_level',[True,False])
def test_phone_thread_nested_replies_and_current_revision_parts_without_read_marking(grid_browser,app_mod,monkeypatch,task_level):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_DISCUSSION_READ'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic thread unit','division','SYNTHETIC/THREADREAD')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic thread reading','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic thread task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    target=task['id'] if task_level else None;query={'case_id':item['id'],'task_id':target}
    work_updates.follow(c,user,item['id'])
    original='Current long root\n'+('Word '*410)+'PrivateTailEnd'
    root=discussion.post(c,other,item['id'],original,task_id=target)
    direct=discussion.post(c,other,item['id'],'Direct reply text',task_id=target,parent_id=root)
    nested=discussion.post(c,other,item['id'],'Nested reply text',task_id=target,parent_id=direct)
    discussion.post(c,other,item['id'],'OtherThreadText',task_id=None if task_level else task['id'])
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
            assert 'Reading discussion threads requires independent text-reading consent' in page.locator('body').inner_text()
            for scope in ('work.read',reader.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',reader.ACTION}
            menu=command('/menu')['text'];assert '/discussion_thread' in menu and '/discussion_search' not in menu
            text=command(reader.command(query,root))['text']
            assert 'Current long root' in text and 'Direct reply text' in text and 'Nested reply text' not in text
            assert 'PrivateTailEnd' not in text and 'OtherThreadText' not in text and other['username'] not in text
            text=command(reader.command(query,root,'/discussion_message'))['text'];collected=[]
            for _ in range(5):
                assert reader.common.units(text)<=4096
                collected.append(text.split('Text (current part):\n',1)[1].split('\nEnd of message part.',1)[0])
                next_=re.search(r'Next part: (.*)',text)
                if not next_:break
                assert 'part:1:' in next_[1];text=command(next_[1])['text']
            assert ''.join(collected)==original
            text=command(reader.command(query,direct))['text'];assert 'Nested reply text' in text and 'Parent: '+reader.command(query,root) in text
            assert 'OtherThreadText' not in text and 'Current long root' not in text
            for table,values in before.items():assert values==list(c.execute('SELECT * FROM '+table))
            discussion.edit(c,other,item['id'],target,root,1,'CurrentRootEdited')
            stale=command(reader.command(query,root,'/discussion_message')+' part:1:2')['text']
            assert 'This message changed' in stale and 'CurrentRootEdited' not in stale
            current=command(reader.command(query,root,'/discussion_message'))['text'];assert 'Revision 2' in current and 'CurrentRootEdited' in current
            url=reader.source(query,root);page.goto(url)
            assert 'CurrentRootEdited' in page.locator('#message-'+str(root)).inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert work_updates.read_revision(c,user['id'],root)==0
            assert before['work_follow']==list(c.execute('SELECT * FROM work_follow')) and before['work_notice']==list(c.execute('SELECT * FROM work_notice'))
            for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command(reader.command(query,root))
        finally:context.close();c.close()
