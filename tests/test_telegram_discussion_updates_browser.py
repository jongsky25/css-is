"""Phone consent, own-notice metadata and exact source navigation without Telegram read marking."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_updates as inbox
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('reason',['mention','reply','following'])
def test_phone_inbox_metadata_links_and_source_managed_read_status(grid_browser,app_mod,monkeypatch,reason):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_UPDATES_READ'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic inbox unit','division','SYNTHETIC/UPDATES')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic discussion inbox','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic discussion task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    parent=discussion.post(c,user,item['id'],'StoredPrivateParent',task_id=task['id']) if reason=='reply' else None
    if reason=='following':work_updates.follow(c,user,item['id'],task_id=task['id'])
    identifier=discussion.post(c,other,item['id'],'StoredPrivateMessage',task_id=task['id'],parent_id=parent,mentions=[user['id']] if reason=='mention' else [])
    notice=rows(c,'SELECT * FROM work_notice WHERE comment_id=? AND user_id=?',(identifier,user['id']))[0]
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
            for scope in ('work.read',inbox.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',inbox.ACTION}
            assert '/my_updates' in command('/menu')['text']
            category={'mention':'mentions','reply':'replies','following':'following'}[reason]
            text=command('/my_updates '+category)['text']
            assert 'Update '+str(notice['id']) in text and 'StoredPrivate' not in text
            text=command('/update_status '+str(notice['id']))['text']
            assert 'Status: unread' in text and 'StoredPrivate' not in text
            assert work_updates.read_revision(c,user['id'],identifier)==0
            assert not rows(c,'SELECT * FROM telegram_operation')
            url=re.search(re.escape(base)+r'/work/[^\s]+',text)[0]
            page.goto(url);assert 'StoredPrivateMessage' in page.locator('#message-'+str(identifier)).inner_text()
            assert 'Comment '+str(identifier)+' · Revision 1' in page.locator('#message-'+str(identifier)).inner_text()
            # Source read management remains authoritative, independently of Telegram's lookups.
            work_updates.mark_read(c,user,item['id'],task['id'],[(identifier,1)])
            assert not re.search(r'Update [0-9]+ ·',command('/my_updates '+category)['text'])
            assert 'already read' in command('/update_status '+str(notice['id']))['text']
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command('/my_updates')
        finally:context.close();c.close()
