"""No-script phone catalog selection, exact private draft confirmation and recovery."""
import re
from uuid import uuid4

import httpx
import pytest

import auth
from documents_storage import rows
import storage as st
import supplies
import supplies_requests as requests
import supplies_stock as stock
import telegram_bot as bot
import telegram_links as links
import telegram_supply_draft as draft
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('multiple_and_stale',[False,True])
def test_phone_catalog_form_creates_only_one_confirmed_own_draft(grid_browser,app_mod,monkeypatch,multiple_and_stale):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');admin=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','SUPPLIES_READ','SUPPLIES_DRAFT'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic supply unit','division','SYNTHETIC/SUPPLYDRAFT')
    rp=st.add_rp(c,'Synthetic requester',True,unit)
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,user['id']));c.commit();user=st.get_admin_user_by_id(c,user['id'])
    supplies.grant_role(c,admin,admin['id'],'custodian',operation_key=str(uuid4()))
    supplies.set_enabled(c,admin,'1',expected_revision=0,operation_key=str(uuid4()))
    chosen=[]
    for i in range(28):
        item=supplies.create_item(c,admin,{'code':('PHONE' if i in (0,26) else 'OTHER')+str(i),'description':'Synthetic catalog '+str(i),'unit':'Pack','critical_level':'0'},operation_key=str(uuid4()))['id']
        if i in (0,26):
            chosen.append(item)
            stock.post_opening(c,admin,item,{'quantity':'10','effective_date':'2026-10-19','reason':'Synthetic opening'},expected_revision=1,operation_key=str(uuid4()))
    tables=('supply_stock_movement','supply_reservation','supply_request_revision','supply_sequence','supply_alert_event','supply_mail')
    unchanged={table:list(c.execute('SELECT * FROM '+table)) for table in tables}
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
            for scope in ('supplies.read',draft.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'supplies.read',draft.ACTION}
            assert '/supply_draft' in command('/menu')['text']
            page.goto(base+draft.PATH+'create');assert 'No current private request' in page.locator('body').inner_text()
            assert not rows(c,'SELECT * FROM telegram_meeting_origin')
            guide=command('/supply_draft')['text'];page.goto(guide.splitlines()[-1])
            assert page.locator('select[name=item_1] option').count()==26
            page.get_by_role('link',name='Next catalog page',exact=True).click()
            assert page.locator('select[name=item_1] option').count()==4
            page.get_by_label('Search active catalog',exact=True).fill('PHONE');page.get_by_role('button',name='Search catalog',exact=True).click()
            assert page.locator('select[name=item_1] option').count()==3
            assert 'on_hand' not in page.content() and 'reserved_quantity' not in page.content()
            def fill():
                page.get_by_label('Purpose',exact=True).fill('Phone supplies 🌿')
                page.get_by_label('Date needed (optional)',exact=True).fill('2026-11-05')
                page.get_by_label('Item 1',exact=True).select_option(str(chosen[0]));page.get_by_label('Quantity 1',exact=True).fill('3')
                if multiple_and_stale:
                    page.get_by_label('Item 2',exact=True).select_option(str(chosen[1]));page.get_by_label('Quantity 2',exact=True).fill('2')
            fill();form=page.locator('form[method=post]')
            values={key:form.locator('[name='+key+']').input_value() for key in ('csrf','origin','key',*draft.FIELDS['create'])}
            for bad in ({'csrf':'bad'},{'owner_id':str(admin['id'])},{'quantity_1':'999'}):
                assert page.request.post(base+draft.PATH+'create',form={**values,**bad},headers={'Origin':base}).status==400
            assert not rows(c,'SELECT * FROM supply_request') and not rows(c,'SELECT * FROM telegram_operation')
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'No supply draft exists yet' in body
            op=re.search(r'/supplydraft_preview ([a-f0-9]{32})',body)[1]
            text=command('/supplydraft_preview '+op)['text']
            assert 'Phone supplies 🌿' in text and 'Requester: Synthetic requester' in text and 'Quantity: 3' in text and 'No control number' in text
            if multiple_and_stale:assert 'Quantity: 2' in text
            exact=re.search(r'/supplydraft_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert not rows(c,'SELECT * FROM supply_request')
            if multiple_and_stale:
                c.execute('UPDATE supply_item SET description=?,revision=revision+1 WHERE id=?',('New native description',chosen[0]));c.commit()
                assert 'Recorded outcome' not in command(exact)['text'] and not rows(c,'SELECT * FROM supply_request')
                page.goto(guide.splitlines()[-1])
                page.get_by_label('Search active catalog',exact=True).fill('PHONE');page.get_by_role('button',name='Search catalog',exact=True).click()
                fill();page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
                op=re.search(r'/supplydraft_preview ([a-f0-9]{32})',page.locator('body').inner_text())[1]
                text=command('/supplydraft_preview '+op)['text'];assert 'New native description' in text
                exact=re.search(r'/supplydraft_confirm [A-Za-z0-9_-]{43}',text)[0]
            text=command(exact)['text'];assert 'Recorded outcome: supply draft saved.' in text
            request=rows(c,'SELECT * FROM supply_request')[0]
            assert request['requester_id']==user['id'] and request['approval_status']=='draft' and request['control_number'] is None
            assert len(rows(c,'SELECT * FROM supply_request_draft_line'))==(2 if multiple_and_stale else 1)
            assert 'Recorded outcome' in command(exact)['text'] and 'Saved revision 1' in command('/supplydraft_receipt '+op)['text']
            assert len(rows(c,'SELECT * FROM supply_request'))==1
            page.goto(base+'/supplies/requests/'+str(request['id']));assert 'Phone supplies' in page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            for table,before in unchanged.items():assert before==list(c.execute('SELECT * FROM '+table))
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            context.clear_cookies();assert page.request.post(base+draft.PATH+'create',form=values,headers={'Origin':base}).status==401
        finally:context.close();c.close()
