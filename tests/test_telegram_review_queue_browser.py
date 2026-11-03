"""Phone queue consent to source-safe metadata and separately confirmed review actions."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_review_queue as queue
import work
import work_tasks
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('mode',['read_only','accept','return'])
def test_phone_review_queue_leads_to_separate_existing_confirmation(grid_browser,app_mod,monkeypatch,mode):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    owner=st.get_admin_user(c,'encoder@test.local');officer=st.get_admin_user(c,'admin@test.local')
    flags=['INBOUND','DELIVERY','LINK','WORK_READ','TASKS_REVIEW_READ']
    if mode!='read_only':flags.append('TASKS_'+mode.upper())
    for flag in flags:monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic queue unit','division','SYNTHETIC/QUEUE')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic queue work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],user['id'],'Synthetic lead')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic pending review','expected_output':'DoNotExposeCriteria','unit_id':unit,'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':owner['id'],'reason':'Source owner'})
    task=work_tasks.mutate(c,owner,item['id'],task['id'],task['revision'],'acknowledge',{'reason':'Source progress'})
    task=work_tasks.mutate(c,owner,item['id'],task['id'],task['revision'],'submit',{'reason':'Source evidence','submission':'DoNotExposeSubmission'})
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
            page.goto(base+'/account/telegram')
            page.get_by_label('Private linking code',exact=True).fill(code)
            scopes=['work.read',queue.ACTION]+(['tasks.'+mode] if mode!='read_only' else [])
            for scope in scopes:page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}==set(scopes)
            assert '/review_queue' in command('/menu')['text']
            text=command('/review_queue')['text']
            assert 'Synthetic pending review' in text and 'Synthetic queue work' in text and '2026-10-28' in text
            assert owner['username'] in text and 'DoNotExpose' not in text
            detail=re.search(r'/review_task [0-9]+ [0-9]+',text)[0]
            text=command(detail)['text']
            assert 'DoNotExpose' not in text and '/work/'+str(item['id']) in text
            assert not rows(c,'SELECT * FROM telegram_operation') and rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]==task
            if mode=='read_only':
                assert '/task_accept' not in text and '/task_return' not in text
                assert 'separate permissions' in text
            else:
                assert '/task_'+mode in text and '/task_'+('return' if mode=='accept' else 'accept') not in text
                page.goto(command('/task_'+mode)['text'].splitlines()[-1])
                page.get_by_label('Work item number',exact=True).fill(str(item['id']))
                page.get_by_label('Task number',exact=True).fill(str(task['id']))
                page.get_by_label('Review reason',exact=True).fill('Synthetic review from queue')
                page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                op=re.search('/task'+mode+r'_preview ([a-f0-9]{32})',page.locator('body').inner_text())[1]
                preview=command('/task'+mode+'_preview '+op)['text']
                exact=re.search('/task'+mode+r'_confirm [A-Za-z0-9_-]{43}',preview)[0]
                assert 'Recorded outcome:' in command(exact)['text'] and 'Recorded outcome:' in command(exact)['text']
                changed=rows(c,'SELECT * FROM work_task WHERE id=?',(task['id'],))[0]
                assert changed['status']==('done' if mode=='accept' else 'in_progress')
                for field in ('owner_id','due_date','submission','expected_output'):assert changed[field]==task[field]
                assert 'Synthetic pending review' not in command('/review_queue')['text']
            page.goto(base+'/account/telegram')
            page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command('/review_queue')
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
        finally:context.close();c.close()
