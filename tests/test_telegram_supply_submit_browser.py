"""No-script own draft/returned submission and independent private consent."""
import re
from uuid import uuid4

import httpx
import pytest

import auth
from documents_storage import rows
import ratelimit
import storage as st
import supplies
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_stock as stock
import telegram_bot as bot
import telegram_links as links
import telegram_supply_submit as manager
from tests.conftest import session_token
from tests.test_document_registry_grid_browser import grid_browser
from tests.test_work_channels_browser import live_app
from tests.test_telegram_bot import TOKEN,SECRET,NOW,update,HEADERS


@pytest.mark.parametrize('mode',['draft','returned','no_approvers'])
def test_phone_exact_supply_submission_and_historical_recovery(grid_browser,app_mod,monkeypatch,mode):
    c=st.connect(app_mod.DB);user=st.get_admin_user(c,'viewer@test.local');admin=st.get_admin_user(c,'admin@test.local')
    for flag in ('INBOUND','DELIVERY','LINK','SUPPLIES_READ','SUPPLIES_SUBMIT'):monkeypatch.setenv('CSS_TELEGRAM_'+flag+'_ENABLED','1')
    monkeypatch.setenv('CSS_TELEGRAM_REPLY_TRANSPORT','webhook');monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN',TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_WEBHOOK_SECRET',SECRET);monkeypatch.setattr(bot,'now_utc',lambda:NOW)
    monkeypatch.setattr(bot.transport,'send',lambda *a:pytest.fail('Outgoing Telegram'))
    unit=st.add_org_unit(c,'Synthetic submission unit','division','SYNTHETIC/SUPPLYSUBMIT')
    rp=st.add_rp(c,'Synthetic submission requester',True,unit)
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,user['id']));c.commit();user=st.get_admin_user_by_id(c,user['id'])
    supplies.grant_role(c,admin,admin['id'],'custodian',operation_key=str(uuid4()))
    if mode!='no_approvers':supplies.grant_role(c,admin,admin['id'],'request_approver',unit_id=unit,operation_key=str(uuid4()))
    supplies.set_enabled(c,admin,'1',expected_revision=0,operation_key=str(uuid4()))
    item=supplies.create_item(c,admin,{'code':'SUBMIT-PAPER','description':'Synthetic submission paper','unit':'Ream','critical_level':'0'},operation_key=str(uuid4()))['id']
    stock.post_opening(c,admin,item,{'quantity':'10','effective_date':'2026-10-19','reason':'Synthetic opening'},expected_revision=1,operation_key=str(uuid4()))
    values={'purpose':'Phone submission purpose','date_needed':'2026-11-06','lines':[{'item_id':item,'requested_quantity':2}]}
    saved=requests.save_draft(c,user,values,operation_key=str(uuid4()));rid=saved['id'];old_number=None
    if mode=='returned':
        first=requests.submit(c,user,rid,expected_revision=1,operation_key=str(uuid4()));old_number=first['control_number']
        approvals.decide_request(c,admin,rid,{'decision':'returned','reason':'Clarify purpose'},expected_revision=first['revision'],submitted_revision=first['current_revision'],operation_key=str(uuid4()))
        returned=requests._owned(c,user,rid)
        requests.save_draft(c,user,values,request_id=rid,expected_revision=returned['revision'],operation_key=str(uuid4()))
    current=requests._owned(c,user,rid);before=current.copy()
    inventory={table:list(c.execute('SELECT * FROM '+table)) for table in ('supply_stock_movement','supply_reservation')}
    mail_before=len(rows(c,'SELECT * FROM supply_mail'))
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
            for scope in ('supplies.read',manager.ACTION):page.get_by_label(links.SCOPES[scope],exact=True).check()
            page.get_by_label('Link this Office Connect account to my own private Telegram account.',exact=True).check()
            page.get_by_role('button',name='Request confirmation in Telegram',exact=True).click()
            command(re.search(r'/confirm [a-f0-9]{64}',command('/status')['text'])[0])
            assert {r[0] for r in c.execute('SELECT action FROM telegram_grant WHERE revoked_at IS NULL')}=={'supplies.read',manager.ACTION}
            menu=command('/menu')['text'];assert '/supply_submit' in menu and '/supply_draft' not in menu
            detail=command('/supply_status '+str(rid))['text']
            assert 'Request revision: '+str(current['revision']) in detail and 'Phone submission purpose' not in detail
            shortcut=re.search(r'Submit for approval form: (.*)',detail)[1]
            assert shortcut==base+manager.PATH+'submit?request_id='+str(rid)+'&revision='+str(current['revision'])
            page.goto(shortcut);assert 'No current private request' in page.locator('body').inner_text()
            assert not rows(c,'SELECT * FROM telegram_meeting_origin') and not rows(c,'SELECT * FROM telegram_operation')
            command('/supply_submit');page.goto(shortcut)
            assert page.get_by_label('Request number',exact=True).input_value()==str(rid)
            assert page.get_by_label('Current request revision',exact=True).input_value()==str(current['revision'])
            assert page.locator('[name=purpose]').count()==0
            form=page.locator('form[method=post]');fields={key:form.locator('[name='+key+']').input_value() for key in ('csrf','origin','key','request_id','revision')}
            for bad in ({'csrf':'bad'},{'purpose':'Injected purpose'},{'owner_id':str(admin['id'])},{'revision':'0'}):
                assert page.request.post(base+manager.PATH+'submit',form={**fields,**bad},headers={'Origin':base}).status==400
            assert not rows(c,'SELECT * FROM telegram_operation') and requests._owned(c,user,rid)==before
            page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
            body=page.locator('body').inner_text();assert 'Your request has not been submitted' in body
            op=re.search(r'/supplysubmit_preview ([a-f0-9]{32})',body)[1]
            assert requests._owned(c,user,rid)==before and len(rows(c,'SELECT * FROM supply_mail'))==mail_before
            text=command('/supplysubmit_preview '+op)['text']
            assert 'Phone submission purpose' in text and 'Synthetic submission paper' in text and 'Quantity: 2' in text
            assert ('WARNING: No eligible approver' in text)==(mode=='no_approvers')
            if old_number:assert old_number+' (retained)' in text
            exact=re.search(r'/supplysubmit_confirm [A-Za-z0-9_-]{43}',text)[0]
            if mode=='draft':
                requests.save_draft(c,user,{**values,'purpose':'New native purpose'},request_id=rid,expected_revision=current['revision'],operation_key=str(uuid4()))
                assert 'Recorded outcome' not in command(exact)['text']
                page.goto(shortcut);page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
                assert 'changed' in page.locator('body').inner_text()
                detail=command('/supply_status '+str(rid))['text'];shortcut=re.search(r'Submit for approval form: (.*)',detail)[1]
                ratelimit.reset();page.goto(shortcut);page.get_by_role('button',name='Prepare exact private preview',exact=True).click()
                op=re.search(r'/supplysubmit_preview ([a-f0-9]{32})',page.locator('body').inner_text())[1]
                text=command('/supplysubmit_preview '+op)['text'];assert 'New native purpose' in text
                exact=re.search(r'/supplysubmit_confirm [A-Za-z0-9_-]{43}',text)[0]
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            text=command(exact)['text'];assert 'Recorded outcome: supply request submitted for approval.' in text
            submitted=requests._owned(c,user,rid);assert submitted['approval_status']=='submitted' and submitted['current_revision']==(2 if mode=='returned' else 1)
            if old_number:assert submitted['control_number']==old_number
            assert len(rows(c,'SELECT * FROM supply_request'))==1
            assert c.execute('SELECT last_value FROM supply_sequence').fetchone()[0]==1
            after=submitted.copy();assert 'Recorded outcome' in command(exact)['text']
            assert 'Recorded submitted version' in command('/supplysubmit_receipt '+op)['text'] and requests._owned(c,user,rid)==after
            assert 'Submit for approval form:' not in command('/supply_status '+str(rid))['text']
            for table,original in inventory.items():assert original==list(c.execute('SELECT * FROM '+table))
            assert len(rows(c,'SELECT * FROM supply_mail'))==mail_before+(0 if mode=='no_approvers' else 1)
            assert not rows(c,"SELECT * FROM telegram_delivery WHERE state='queued'")
            page.goto(base+'/supplies/requests/'+str(rid));assert submitted['control_number'] in page.locator('body').inner_text()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            context.clear_cookies();assert page.request.post(base+manager.PATH+'submit',form=fields,headers={'Origin':base}).status==401
        finally:context.close();c.close()
