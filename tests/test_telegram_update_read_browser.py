"""No-script phone acknowledgement after independent consent and exact private confirmation."""
import re

import httpx
import pytest

import auth
import ratelimit
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_discussion_updates as inbox
import telegram_update_read as manage
import work
import work_discussion as discussion
import work_updates
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('task_level',[True,False])
@pytest.mark.parametrize('reason',['mention','reply','following'])
def test_phone_acknowledgement_has_exact_notice_preview_and_read_only_recovery(grid_browser,app_mod,monkeypatch,reason,task_level):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');other=st.get_admin_user(c,'encoder@test.local')
    officer=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','WORK_UPDATES_READ','WORK_UPDATES_ACKNOWLEDGE'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic inbox unit','division','SYNTHETIC/UPDATES')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic discussion inbox','outcome':'Shared result','unit_id':unit})
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic discussion task','expected_output':'StoredPrivateOutput','unit_id':unit})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':other['id'],'reason':'Native contributor'})
    target=task['id'] if task_level else None
    parent=discussion.post(c,user,item['id'],'StoredPrivateParent',task_id=target) if reason=='reply' else None
    if reason=='following':work_updates.follow(c,user,item['id'],task_id=target)
    identifier=discussion.post(c,other,item['id'],'StoredPrivateMessage',task_id=target,parent_id=parent,mentions=[user['id']] if reason=='mention' else [])
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
            for scope in ('work.read',inbox.ACTION,manage.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',inbox.ACTION,manage.ACTION}
            assert '/my_updates' in command('/menu')['text']
            category={'mention':'mentions','reply':'replies','following':'following'}[reason]
            text=command('/my_updates '+category)['text']
            assert 'Update '+str(notice['id']) in text and 'StoredPrivate' not in text
            text=command('/update_status '+str(notice['id']))['text']
            assert 'Status: unread' in text and 'StoredPrivate' not in text
            shortcut=re.search(r'Mark this update read form: (.*)',text)[1]
            assert shortcut==base+manage.PATH+'read?notice_id='+str(notice['id'])+'&revision=1'
            page.goto(shortcut)
            assert 'No current private request' in page.locator('body').inner_text()
            for table in ('telegram_meeting_origin','telegram_operation','telegram_preview'):assert not rows(c,'SELECT * FROM '+table)
            assert work_updates.read_revision(c,user['id'],identifier)==0
            assert not rows(c,'SELECT * FROM telegram_operation')
            url=re.search(re.escape(base)+r'/work/[^\s]+',text)[0]
            page.goto(url);assert 'StoredPrivateMessage' in page.locator('#message-'+str(identifier)).inner_text()
            assert 'Comment '+str(identifier)+' · Revision 1' in page.locator('#message-'+str(identifier)).inner_text()
            command('/update_read');page.goto(shortcut)
            assert page.get_by_label('Notice number',exact=True).input_value()==str(notice['id'])
            assert page.get_by_label('Notice revision',exact=True).input_value()=='1'
            for table in ('telegram_operation','telegram_preview'):assert not rows(c,'SELECT * FROM '+table)
            assert work_updates.read_revision(c,user['id'],identifier)==0
            form=page.locator('form[action="'+manage.PATH+'read"]')
            values={k:form.locator('[name='+k+']').input_value() for k in ('csrf','origin','key')}
            values.update(notice_id=str(notice['id']),revision='1')
            url=base+manage.PATH+'read';headers={'Origin':base}
            for bad in ({'csrf':'bad'},{'revision':'2'},{'notice_id':'999999'},{'body':'unsupported'}):
                assert page.request.post(url,form={**values,**bad},headers=headers).status==400
            assert not rows(c,'SELECT * FROM telegram_operation')
            assert work_updates.read_revision(c,user['id'],identifier)==0
            page.get_by_label('Notice number',exact=True).fill(str(notice['id']))
            page.get_by_label('Notice revision',exact=True).fill('1')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'Nothing has been marked read' in body
            op=re.search(r'/updateread_preview ([a-f0-9]{32})',body)[1]
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert work_updates.read_revision(c,user['id'],identifier)==0
            text=command('/updateread_preview '+op)['text']
            assert 'Notice revision 1 · Current revision 1' in text and 'StoredPrivate' not in text
            confirmation=re.search(r'/updateread_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert 'Recorded outcome: notice marked read.' in command(confirmation)['text']
            assert 'Recorded outcome:' in command(confirmation)['text']
            assert 'Recorded acknowledged revision: 1' in command('/updateread_receipt '+op)['text']
            assert work_updates.read_revision(c,user['id'],identifier)==1
            assert not re.search(r'Update [0-9]+ ·',command('/my_updates '+category)['text'])
            done=command('/update_status '+str(notice['id']))['text']
            assert 'already read' in done and 'Mark this update read form:' not in done
            operations=list(c.execute('SELECT * FROM telegram_operation'))
            page.goto(shortcut)
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            assert 'already read' in page.locator('body').inner_text()
            assert operations==list(c.execute('SELECT * FROM telegram_operation'))
            # Isolate the revoked-permission check from earlier intentional bad POSTs.
            ratelimit.reset()
            monkeypatch.setenv('CSS_TELEGRAM_WORK_UPDATES_ACKNOWLEDGE_ENABLED','0')
            page.goto(shortcut);assert 'No current private request' in page.locator('body').inner_text()
            assert page.request.post(url,form=values,headers=headers).status==403
            assert work_updates.read_revision(c,user['id'],identifier)==1
            assert operations==list(c.execute('SELECT * FROM telegram_operation'))
            assert rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command('/my_updates')
        finally:context.close();c.close()
