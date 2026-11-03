"""Phone own-follow listing and safe source-prefilled controls without lookup writes."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_read as reader
import telegram_discussion_follow as manage
import telegram_followed_discussions as reads
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('with_read',[False,True])
@pytest.mark.parametrize('with_controls',[False,True])
def test_phone_saved_follows_source_links_and_explicit_separate_controls(grid_browser,app_mod,monkeypatch,with_controls,with_read):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_FOLLOWS_READ'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED','1')
    if with_controls:monkeypatch.setenv('CSS_TELEGRAM_WORK_FOLLOW_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic saved-follow unit','division','SYNTHETIC/FOLLOWLIST')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic saved follows','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic followed task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    for target in (None,task['id']):work_updates.follow(c,user,item['id'],target)
    work_updates.follow(c,other,item['id'])
    cid=discussion.post(c,other,item['id'],'StoredPrivateMessage',task_id=task['id'])
    before_follow=list(c.execute('SELECT * FROM work_follow'));before_read=list(c.execute('SELECT * FROM work_comment_read'))
    before_notice=list(c.execute('SELECT * FROM work_notice'))
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
            scopes={'work.read',reads.ACTION}|({manage.ACTION} if with_controls else set())|({reader.ACTION} if with_read else set())
            page.goto(base+'/account/telegram');page.get_by_label('Private linking code',exact=True).fill(code)
            for scope in scopes:page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}==scopes
            text=command('/menu')['text'];assert '/my_follows' in text and ('/discussion_follow' in text)==with_controls
            text=command('/my_follows')['text']
            assert 'Work-wide also on' in text and 'all task discussions' in text and 'StoredPrivate' not in text
            assert ('Follow controls:' in text)==with_controls
            assert ('Browse comments:' in text)==with_read
            if with_read:
                browse=re.search(r'Browse comments: (.*)',text)[1]
                listing=command(browse)['text'];assert 'StoredPrivateMessage' in listing
                thread=re.search(r'View thread: (.*)',listing)[1]
                assert 'StoredPrivateMessage' in command(thread)['text']
                assert before_follow==list(c.execute('SELECT * FROM work_follow')) and before_read==list(c.execute('SELECT * FROM work_comment_read'))
                assert before_notice==list(c.execute('SELECT * FROM work_notice'))
            assert not rows(c,'SELECT * FROM telegram_operation') and not rows(c,'SELECT * FROM telegram_meeting_origin')
            source=base+'/work/'+str(item['id'])+'/discussion?task_id='+str(task['id'])
            assert source in text;page.goto(source)
            assert 'StoredPrivateMessage' in page.locator('#message-'+str(cid)).inner_text()
            assert before_follow==list(c.execute('SELECT * FROM work_follow')) and before_read==list(c.execute('SELECT * FROM work_comment_read'))
            assert before_notice==list(c.execute('SELECT * FROM work_notice'))
            if with_controls:
                controls=re.search(r'Follow controls: ([^\s]+&task_id='+str(task['id'])+r')',text)[1]
                page.goto(controls)
                assert 'No current private request' in page.locator('body').inner_text()
                assert not rows(c,'SELECT * FROM telegram_meeting_origin') and not rows(c,'SELECT * FROM telegram_operation')
                command('/discussion_follow');page.goto(controls)
                assert page.get_by_label('Work item number',exact=True).input_value()==str(item['id'])
                assert page.get_by_label('Task number (optional)',exact=True).input_value()==str(task['id'])
                assert page.get_by_label('Change',exact=True).input_value()==''
                assert before_follow==list(c.execute('SELECT * FROM work_follow')) and not rows(c,'SELECT * FROM telegram_operation')
                page.get_by_label('Change',exact=True).select_option('unfollow')
                page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
                body=page.locator('body').inner_text();assert 'Following has not changed' in body
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                op=re.search(r'/discussionfollow_preview ([a-f0-9]{32})',body)[1]
                preview=command('/discussionfollow_preview '+op)['text'];assert 'work-wide follow is currently on' in preview
                assert before_follow==list(c.execute('SELECT * FROM work_follow'))
                exact=re.search(r'/discussionfollow_confirm [A-Za-z0-9_-]{43}',preview)[0]
                assert 'Recorded outcome: discussion unfollowed.' in command(exact)['text']
                assert 'No visible saved follows on this page' in command('/my_follows tasks')['text']
                assert 'Work-wide follow' in command('/my_follows work')['text']
                assert work_updates.following(c,user,item['id']) and not work_updates.following(c,user,item['id'],task['id'])
            else:assert before_follow==list(c.execute('SELECT * FROM work_follow'))
            assert before_read==list(c.execute('SELECT * FROM work_comment_read')) and before_notice==list(c.execute('SELECT * FROM work_notice'))
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command('/my_follows')
        finally:context.close();c.close()
