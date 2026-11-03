"""Phone independent text-search consent, exact-thread excerpts and native source navigation."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_search as search
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('task_level',[True,False])
def test_phone_current_discussion_search_with_explicit_text_consent(grid_browser,app_mod,monkeypatch,task_level):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_DISCUSSION_SEARCH'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic text-search unit','division','SYNTHETIC/DISCUSSIONSEARCH')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic discussion search','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic search task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    target=task['id'] if task_level else None
    work_updates.follow(c,user,item['id'])
    parent=discussion.post(c,other,item['id'],'OldOnlyKeyword original revision',task_id=target)
    body='Current needle parent '+('x'*350)+'DoNotCopyPrivateTail'
    discussion.edit(c,other,item['id'],target,parent,1,body)
    reply=discussion.post(c,other,item['id'],'Current needle reply',task_id=target,parent_id=parent)
    discussion.post(c,other,item['id'],'WrongThread needle',task_id=None if task_level else task['id'])
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
            assert 'copies limited excerpts of current comments/replies' in page.locator('body').inner_text()
            for scope in ('work.read',search.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',search.ACTION}
            menu=command('/menu')['text'];assert '/discussion_search' in menu and '/my_updates' not in menu and '/my_follows' not in menu
            selected=str(target) if target is not None else 'work';start='/discussion_search '+str(item['id'])+' '+selected+' '
            assert 'Current needle parent' not in command('/find needle')['text']
            text=command(start+'needle')['text']
            assert 'Current needle parent' in text and 'Current needle reply' in text
            assert 'DoNotCopyPrivateTail' not in text and 'WrongThread needle' not in text and 'StoredPrivateOutput' not in text
            assert 'Comment '+str(parent)+' · Revision 2' in text and 'Reply '+str(reply)+' · Revision 1' in text
            assert other['username'] not in text and 'Excerpt:' in text
            assert 'No current matching' in command(start+'OldOnlyKeyword')['text']
            url=base+'/work/'+str(item['id'])+'/discussion?focus='+str(parent)+('&task_id='+str(target) if target is not None else '')+'#message-'+str(parent)
            assert url in text;page.goto(url)
            assert body in page.locator('#message-'+str(parent)).inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            for table,values in before.items():assert values==list(c.execute('SELECT * FROM '+table))
            for table in ('telegram_operation','telegram_preview','telegram_meeting_origin'):assert not rows(c,'SELECT * FROM '+table)
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command(start+'needle')
        finally:context.close();c.close()
