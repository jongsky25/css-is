"""Public survey journeys: real local HTTP, SQLite, DOM, IndexedDB and storage failures."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect

import storage as st
import tzutil as tz
from tests.test_document_guidance_browser import browser
from tests.test_csm_public_form import walkin


@pytest.fixture
def survey_page(browser,client,app_mod,walkin):
    state={'posts':[],'errors':[],'receipt':'normal'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def handle_request(self):
            raw=self.rfile.read(int(self.headers.get('Content-Length','0'))) if self.command=='POST' else None
            if self.command=='POST':state['posts'].append(self.path)
            response=client.request(self.command,self.path,content=raw,
                headers={'Content-Type':self.headers.get('Content-Type',''),'Accept':self.headers.get('Accept',''),'Accept-Language':self.headers.get('Accept-Language','en')},follow_redirects=False)
            body=response.content
            if self.path.startswith('/static/js/app.js') and state['posts'] and state.get('script_delay'):
                time.sleep(state['script_delay'])
            if self.command=='POST' and self.path.startswith('/r/'):
                if state['receipt']=='html':body=b'<h1>Unconfirmed proxy page</h1>'
                if state['receipt']=='wrong':body=b'{"ok":true,"submission_id":"wrong"}'
                if state['receipt']=='drop':self.close_connection=True;return
            self.send_response(response.status_code)
            for key,value in response.headers.items():
                if key.lower()=='cache-control' and state.get('script_delay') and self.path.startswith('/static/js/app.js'):
                    continue
                if key.lower() not in ('content-length','content-encoding','set-cookie','connection','transfer-encoding'):
                    self.send_header(key,value)
            if state.get('script_delay') and self.path.startswith('/static/js/app.js'):
                self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        do_GET=do_POST=handle_request
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True);thread.start()
    context=browser.new_context(base_url=f'http://127.0.0.1:{server.server_port}',viewport={'width':390,'height':844},service_workers='block',reduced_motion='reduce')
    context.add_init_script("window.testOffline=false; Object.defineProperty(Navigator.prototype,'onLine',{get(){return !window.testOffline;}})")
    page=context.new_page();page.on('pageerror',lambda error:state['errors'].append(str(error)))
    page.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname=='127.0.0.1' else route.abort())
    conn=st.connect(app_mod.DB)
    try:yield page,context,conn,walkin,state
    finally:
        context.close();server.shutdown();server.server_close();thread.join(timeout=2);conn.close()
    assert not state['errors'],state['errors']


def fill_csm(page):
    page.locator('[name=csm_service]').fill('A18 recovery <test>')
    for i in range(9):page.locator(f'[name=SQD{i}][value="4"]').check()


def draft(page,key):return page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))',key)


def speaker_form(c,name='A18 Speaker'):
    from datetime import timedelta
    rp=st.add_rp(c,name,True)
    now=tz.now_local()
    fid=st.create_form_instance(c,3,'F3',now.date().isoformat(),rp_id=rp,topic='A18 browser review')
    st.set_response_window(c,fid,(now-timedelta(days=1)).isoformat(),(now+timedelta(days=1)).isoformat())
    return c.execute('SELECT qr_token FROM form_instance WHERE id=?',(fid,)).fetchone()[0]


def test_invalid_form_has_focussed_summary_and_keeps_answers(survey_page):
    page,context,c,token,state=survey_page
    page.goto(f'/r/{token}');page.locator('[name=csm_service]').fill('Kept correction')
    page.get_by_role('button',name='Submit my answers',exact=True).click()
    expect(page.locator('[data-survey-errors]')).to_be_focused()
    page.locator('[data-survey-errors] a').first.click()
    expect(page.locator('[name=SQD0]').first).to_be_focused()
    expect(page.locator('[name=csm_service]')).to_have_value('Kept correction')
    assert not state['posts']


@pytest.mark.parametrize('failure',['html','wrong','drop'])
def test_queue_requires_matching_receipt_and_replay_keeps_one_saved_response(survey_page,failure):
    page,context,c,token,state=survey_page
    page.goto(f'/r/{token}');fill_csm(page)
    page.evaluate('window.testOffline=true')
    page.get_by_role('button',name='Submit my answers',exact=True).click()
    expect(page.locator('.offline-saved')).to_contain_text('not yet confirmed by the server')
    expect(page.locator('.offline-badge')).to_contain_text('waiting to send')
    state['receipt']=failure
    page.evaluate("window.testOffline=false;window.dispatchEvent(new Event('online'))")
    page.wait_for_timeout(500)
    expect(page.locator('.offline-badge')).to_contain_text('waiting to send')
    assert c.execute("SELECT COUNT(*) FROM response r JOIN form_instance f ON f.id=r.form_instance_id WHERE f.qr_token=?",(token,)).fetchone()[0]==1
    assert draft(page,'css_draft_v2_/r/'+token)
    state['receipt']='normal'
    page.evaluate("window.dispatchEvent(new Event('online'))")
    expect(page.locator('.offline-badge')).to_be_hidden()
    assert draft(page,'css_draft_v2_/r/'+token) is None
    assert c.execute("SELECT COUNT(*) FROM response r JOIN form_instance f ON f.id=r.form_instance_id WHERE f.qr_token=?",(token,)).fetchone()[0]==1


def test_storage_failure_keeps_form_and_does_not_claim_saved(survey_page):
    page,context,c,token,state=survey_page
    page.add_init_script("Storage.prototype.setItem=function(){throw new Error('Storage denied')}; indexedDB.open=function(){const r={};setTimeout(()=>{r.error=new Error('IDB denied');r.onerror&&r.onerror()},0);return r;}")
    page.goto(f'/r/{token}');fill_csm(page)
    expect(page.locator('[data-draft-warning]')).to_contain_text('unavailable')
    expect(page.locator('#draft-flash')).to_have_count(0)
    page.evaluate('window.testOffline=true')
    page.get_by_role('button',name='Submit my answers',exact=True).click()
    expect(page.locator('[data-survey-errors]')).to_contain_text('could not be saved')
    expect(page.get_by_role('button',name='Submit my answers',exact=True)).to_be_enabled()
    expect(page.locator('[name=csm_service]')).to_have_value('A18 recovery <test>')
    expect(page.locator('.offline-saved')).to_have_count(0)
    assert not state['posts']


def test_only_confirmed_revision_is_removed_and_duplicate_clicks_are_blocked(survey_page):
    page,context,c,token,state=survey_page
    state['script_delay']=.3  # Confirmation HTML can arrive before its deferred initializer.
    page.goto(f'/r/{token}');fill_csm(page)
    page.get_by_role('button',name='Submit my answers',exact=True).evaluate("b=>{b.click();document.querySelector('#surveyform').dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}));}")
    expect(page.locator('[data-confirmed-draft]')).to_be_visible()
    assert state['posts']==[f'/r/{token}']
    # Receipt HTML is visible before its deferred browser cleanup necessarily runs.
    page.wait_for_function('(key)=>localStorage.getItem(key)===null',arg='css_draft_v2_/r/'+token,timeout=5000)
    assert draft(page,'css_draft_v2_/r/'+token) is None
    page.evaluate("localStorage.setItem('newer',JSON.stringify({revision:'new'}));window.clearSurveyDraft('newer','old')")
    assert draft(page,'newer')['revision']=='new'


def test_conversation_keeps_focus_after_rating_and_reveals_hidden_error(survey_page):
    page,context,c,token,state=survey_page
    page.goto(f'/r/{token}');page.locator('#conv-toggle').click()
    page.locator('#conv-next').click();page.locator('#conv-next').click()
    item=page.locator('.item.conv-current')
    item.locator('[value="3"]').check()
    page.wait_for_timeout(600)
    expect(item).to_be_visible();expect(item.locator('[value="3"]')).to_be_focused()
    # A submit with earlier hidden unanswered questions links back to that actual step.
    page.locator('#surveyform').evaluate("f=>f.requestSubmit()")
    expect(page.locator('[data-survey-errors]')).to_be_focused()
    page.locator('[data-survey-errors] a').first.click()
    expect(page.locator('[name=SQD1]').first).to_be_focused()
    assert not state['posts']


def test_native_no_script_form_still_records_the_same_scores(survey_page):
    page,context,c,token,state=survey_page
    context.new_cdp_session(page).send('Emulation.setScriptExecutionDisabled',{'value':True})
    page.goto(f'/r/{token}');fill_csm(page)
    page.get_by_role('button',name='Submit my answers',exact=True).click()
    expect(page.get_by_role('heading',name='Thank you!',exact=False)).to_be_visible()
    assert c.execute("SELECT COUNT(*) FROM answer a JOIN response r ON r.id=a.response_id JOIN form_instance f ON f.id=r.form_instance_id WHERE f.qr_token=? AND a.value=4",(token,)).fetchone()[0]==9


def test_unconfirmed_native_response_keeps_draft_for_explicit_recovery(survey_page):
    page,context,c,token,state=survey_page
    page.goto(f'/r/{token}');fill_csm(page);state['receipt']='html'
    page.get_by_role('button',name='Submit my answers',exact=True).click()
    expect(page.get_by_role('heading',name='Unconfirmed proxy page')).to_be_visible()
    assert draft(page,'css_draft_v2_/r/'+token)['fields']['csm_service']=='A18 recovery <test>'
    assert state['posts']==[f'/r/{token}']
    state['receipt']='normal';page.goto(f'/r/{token}')
    page.get_by_role('button',name='Resume draft',exact=True).click()
    expect(page.locator('[name=csm_service]')).to_have_value('A18 recovery <test>')
    assert state['posts']==[f'/r/{token}']


def test_window_closing_during_completion_offers_readonly_device_copy(survey_page):
    from datetime import timedelta
    page,context,c,token,state=survey_page
    token=speaker_form(c)
    page.goto(f'/r/{token}')
    page.locator('[name=sex]').select_option('F');page.locator('[name=affil]').select_option('DOH')
    for item in page.locator('.item').all():item.locator('.scale input').last.check()
    page.locator('[name=remarks]').fill('My unsaved note <safe>')
    fid=c.execute('SELECT id FROM form_instance WHERE qr_token=?',(token,)).fetchone()[0]
    st.set_response_window(c,fid,(tz.now_local()-timedelta(days=2)).isoformat(),(tz.now_local()-timedelta(days=1)).isoformat())
    page.get_by_role('button',name='Submit my answers',exact=True).click()
    page.get_by_text('Show saved answers',exact=True).click()
    expect(page.locator('[data-survey-recovery] textarea')).to_have_value(__import__('re').compile('My unsaved note <safe>'))
    assert c.execute('SELECT COUNT(*) FROM response WHERE form_instance_id=?',(fid,)).fetchone()[0]==0


@pytest.mark.parametrize('language',['en','fil'])
def test_combined_skip_and_completion_use_actual_saved_count(survey_page,language):
    import i18n
    page,context,c,unused,state=survey_page
    state['script_delay']=.3  # Exercise receipt HTML arriving before deferred cleanup.
    context.set_extra_http_headers({'Accept-Language':language})
    first=speaker_form(c,'First speaker');second=speaker_form(c,'Second speaker')
    tokens=first+','+second
    page.goto('/seq?tokens='+tokens)
    page.locator('[name=sex]').select_option('M');page.locator('[name=affil]').select_option('DOH')
    page.locator('.skip-toggle').first.check()
    for item in page.locator('.spk-section').nth(1).locator('.item').all():item.locator('.scale input').last.check()
    page.get_by_role('button',name=str(i18n.t('submit',language)),exact=True).click()
    expect(page.locator('[data-confirmed-draft]')).to_contain_text('1')
    counts=c.execute('SELECT f.qr_token,COUNT(r.id) FROM form_instance f LEFT JOIN response r ON r.form_instance_id=f.id WHERE f.qr_token IN (?,?) GROUP BY f.id',(first,second)).fetchall()
    assert dict(counts)=={first:0,second:1}
    key='css_draft_v2_'+','.join(sorted([first,second]))
    page.wait_for_function('(key)=>localStorage.getItem(key)===null',arg=key,timeout=5000)
    assert draft(page,key) is None
