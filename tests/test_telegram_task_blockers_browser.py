"""Phone blocker metadata links to source resolution without Telegram write authority."""
import re

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import telegram_bot as bot
import telegram_links as links
import telegram_task_blockers as reads
import work
import work_tasks
import work_blockers as blockers
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('actor_kind',['owner','lead'])
def test_phone_blocker_read_scope_exposes_only_metadata_and_source_link(grid_browser,app_mod,monkeypatch,actor_kind):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local')
    other=st.get_admin_user(c,'encoder@test.local');officer=st.get_admin_user(c,'admin@test.local')
    owner=user if actor_kind=='owner' else other
    for flag in ('INBOUND','DELIVERY','LINK','WORK_READ','TASKS_BLOCKERS_READ'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    for module in ('documents','work'):st.set_setting(c,module+'.enabled','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook')
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN);monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET)
    monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic blocker unit','division','SYNTHETIC/BLOCKER')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,?)",(officer['id'],unit,links.stamp(NOW)));c.commit()
    item=work.create(c,user,{'title':'Synthetic blocker work','outcome':'Shared result','unit_id':unit})
    item=work.confirm_lead(c,officer,item['id'],item['revision'],user['id'],'Initial source lead')
    task=work_tasks.create(c,user,item['id'],{'title':'Synthetic blocked task','expected_output':'DoNotExposeCriteria','unit_id':unit,'due_date':'2026-10-28'})
    task=work_tasks.mutate(c,officer,item['id'],task['id'],task['revision'],'confirm',{'owner_id':owner['id'],'reason':'Source owner'})
    task=blockers.mutate(c,user,item['id'],task['id'],task['revision'],'block',{'reason':'DoNotExposeBlockerReason','followup_owner_id':owner['id'],'followup_date':'2026-10-30'})
    upstream=work_tasks.create(c,user,item['id'],{'title':'Synthetic prerequisite','expected_output':'DoNotExposeUpstreamOutput','unit_id':unit})
    task=blockers.mutate(c,user,item['id'],task['id'],task['revision'],'dependency_add',{'reason':'DoNotExposeDependencyReason','prerequisite_id':upstream['id']})
    if actor_kind=='owner':item=work.confirm_lead(c,officer,item['id'],item['revision'],officer['id'],'Different source lead')
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
            for scope in ('work.read',reads.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'work.read',reads.ACTION}
            assert '/task_blockers' in command('/menu')['text']
            before=rows(c,'SELECT * FROM work_task ORDER BY id');edges=rows(c,'SELECT * FROM work_dependency')
            lookup='/task_blockers '+str(item['id'])+' '+str(task['id'])
            text=command(lookup)['text']
            assert 'Recorded blocker: yes' in text and 'Native blocker check: waiting' in text
            assert owner['username'] in text and '2026-10-30' in text and 'Synthetic prerequisite' in text
            assert 'DoNotExpose' not in text
            source_url=re.search(r'Resolve in Office Connect: (\S+)',text)[1]
            response=page.goto(source_url)
            assert response.status==200 and 'DoNotExposeBlockerReason' in page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert rows(c,'SELECT * FROM work_task ORDER BY id')==before and rows(c,'SELECT * FROM work_dependency')==edges
            assert not rows(c,'SELECT * FROM telegram_operation') and not rows(c,'SELECT * FROM telegram_preview')
            # A separate native source resolution is reflected by the next read.
            task=blockers.mutate(c,user,item['id'],task['id'],task['revision'],'unblock',{'reason':'Source resolution'})
            text=command(lookup)['text']
            assert 'Recorded blocker: no' in text and 'Native blocker check: waiting' in text and 'Synthetic prerequisite' in text
            page.goto(base+'/account/telegram');page.get_by_role('button',name='Disconnect Telegram and cancel pending links').click()
            assert 'method' not in command(lookup)
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
        finally:context.close();c.close()
