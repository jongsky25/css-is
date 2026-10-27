"""Travel review confirmation, current-paper checks and single-attempt notification delivery."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
import time

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_read
import mcp_travel_reviews as pilot_service
import mailer
import storage as st
import travel
import travel_review as review
import travel_review_delivery as delivery
from tests.conftest import join_admin_section
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'travel-review-operation-001'
TITLE = 'PRIVATE_REVIEW <script>untrusted</script>'
DOC = 'https://docs.google.com/document/d/private-document/edit'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG): monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST'): monkeypatch.delenv(flag, raising=False)
    join_admin_section(conn, users[1]['id'])
    users[1] = st.get_admin_user_by_id(conn, users[1]['id'])
    filing = travel.create_filing(conn, users[0], kind='reimbursement',
        source={'source_kind': 'blank', 'title': TITLE, 'start': '2026-10-14', 'end': '2026-10-16', 'venue': 'Palo'},
        answers={}, role='participant', dpo_no='DPO-SYNTHETIC', today='2026-10-27')
    for item in travel.view_items(conn, filing):
        conn.execute('UPDATE travel_item SET drive_url=?,doc_url=?,state=\'present\' WHERE filing_id=? AND item_code=?',
                     (DOC, DOC, filing['id'], item['code']))
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('review-test', json.dumps({'client_name': 'Review test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'review-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, filing, token


def fields(pilot, **changes):
    return {'filing_id': pilot[4]['id'], 'reviewer_id': pilot[1][1]['id'],
            'expected_updated_at': pilot[4]['updated_at'], **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[5].access_token, RESOURCE, ORIGIN, operation_id, data or fields(pilot))


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1) for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


def confirm(pilot, operation_id=KEY):
    payload = auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(pilot[0], payload, RESOURCE, ORIGIN, operation_id)
    return pilot_service.browser(pilot[0], payload, RESOURCE, ORIGIN, operation_id, confirm_digest=preview['preview_digest'])


def test_exact_confirmation_queues_one_email_and_preserves_later_decision(pilot, monkeypatch):
    conn, users, clients, app, filing, token = pilot
    def no_send(*a, **kw): raise AssertionError('No transport call in prepare/confirm/recover')
    monkeypatch.setattr(mailer, 'send', no_send)
    unchanged = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in ('travel_item','travel_flag','supply_stock_movement','calendar_entry')}
    preview = prepare(pilot)
    assert prepare(pilot) == preview and 'PRIVATE_REVIEW' not in json.dumps(preview) and DOC not in json.dumps(preview)
    path = '/account/integrations/mcp/travel-review-requests/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert users[1]['username'] in page.text and DOC not in page.text
    assert not conn.execute('SELECT * FROM mcp_travel_review_mail').fetchall()
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    result = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert result['status'] == 'completed' and result['review_state'] == 'requested' and result['review_round'] == 1
    assert result['next_actor'] == {'role': 'selected_travel_reviewer', 'user_id': str(users[1]['id'])}
    assert result['notification_status'] == 'queued' and 'PRIVATE_REVIEW' not in json.dumps(result)
    assert prepare(pilot) == result
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    assert conn.execute('SELECT COUNT(*) FROM mcp_travel_review_mail').fetchone()[0] == 1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_travel_review').fetchone() == (None, None)
    assert clients[0].get(result['web_url']).status_code == 200
    assert filing['ref_code'] in clients[1].get('/travel/review').text
    for table, before in unchanged.items(): assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    review.approve(conn, travel.get_filing(conn, filing['id']), users[1]['username'])
    assert prepare(pilot) == result
    assert travel.get_filing(conn, filing['id'])['review_state'] == 'approved'


@pytest.mark.parametrize('change', ['stamp','papers','missing','running','reviewer','owner','scope','revoked','expired','snapshot','payload','switch','module'])
def test_current_gates_and_exact_content_binding(pilot, monkeypatch, change):
    conn, users, clients, app, filing, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/travel-review-requests/' + KEY
    page = clients[0].get(path)
    if change == 'stamp': conn.execute("UPDATE travel_filing SET updated_at='changed'")
    elif change == 'papers': conn.execute("UPDATE travel_item SET drive_url='https://docs.google.com/document/d/changed/edit'")
    elif change == 'missing': conn.execute('UPDATE travel_item SET drive_url=NULL,doc_url=NULL')
    elif change == 'running': conn.execute("UPDATE travel_filing SET gen_state='running'")
    elif change == 'reviewer': conn.execute('UPDATE resource_person SET archived_at=\'2026-10-27\' WHERE id=?',(users[1]['rp_id'],))
    elif change == 'owner': conn.execute('UPDATE travel_filing SET user_id=?',(users[2]['id'],))
    elif change == 'scope': conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"travel:read\"]'")
    elif change == 'revoked': conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired': conn.execute('UPDATE mcp_travel_review SET expires_at=1')
    elif change == 'snapshot': conn.execute('UPDATE mcp_travel_review SET snapshot_json=NULL')
    elif change == 'payload': conn.execute('UPDATE mcp_travel_review SET payload_json=?', (json.dumps(fields(pilot, reviewer_id=users[2]['id'])),))
    elif change == 'switch': monkeypatch.setenv(pilot_service.FLAG,'0')
    else: st.set_setting(conn,'travel.enabled','0')
    conn.commit()
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert not conn.execute('SELECT * FROM mcp_travel_review_mail').fetchall()
    assert travel.get_filing(conn,filing['id'])['review_round'] == 0


@pytest.mark.parametrize('changed', [{'filing_id':True},{'filing_id':0},{'reviewer_id':True},
    {'expected_updated_at':''},{'approval':'approved'},{'documents':[]},{'email':'other@example.test'}])
def test_invalid_fields_rejected(pilot,changed):
    with pytest.raises(ValueError): prepare(pilot,data=fields(pilot,**changed))


def test_self_foreign_reviewer_cross_account_and_scope_boundaries(pilot):
    conn,users,clients,app,filing,token=pilot
    for uid in (users[0]['id'], users[2]['id']):
        with pytest.raises(permissions.Denied): prepare(pilot,data=fields(pilot,reviewer_id=uid))
    other=mcp_auth.Provider._tokens(conn,'review-test',users[2]['id'],[pilot_service.SCOPE],RESOURCE)
    read=mcp_auth.Provider._tokens(conn,'review-test',users[0]['id'],['travel:read','travel:filing:draft'],RESOURCE)
    fresh=mcp_auth.Provider._tokens(conn,'review-test',users[0]['id'],[pilot_service.SCOPE],RESOURCE)
    conn.commit();prepare(pilot)
    with pytest.raises(permissions.Denied): pilot_service.prepare(conn,other.access_token,RESOURCE,ORIGIN,KEY,fields(pilot))
    with pytest.raises(mcp_actions.ActionError): pilot_service.prepare(conn,read.access_token,RESOURCE,ORIGIN,KEY,fields(pilot))
    with pytest.raises(permissions.Denied): pilot_service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    path='/account/integrations/mcp/travel-review-requests/'+KEY;page=clients[0].get(path)
    assert clients[2].get(path).status_code==404
    assert clients[0].post(path,data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[0].post(path,data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied): confirm(pilot)


def test_atomic_rollback_and_two_previews_only_one_review_round(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot
    prepare(pilot);prepare(pilot,'other-travel-review-001')
    original=st.audit
    def failed(*args,**kwargs):
        if args[2]=='integration_action_complete': raise RuntimeError('Synthetic completion audit failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(st,'audit',failed)
    with pytest.raises(RuntimeError): confirm(pilot)
    assert travel.get_filing(conn,filing['id'])['review_round']==0 and not conn.execute('SELECT * FROM mcp_travel_review_mail').fetchall()
    monkeypatch.setattr(st,'audit',original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    previews=[pilot_service.browser(conn,payload,RESOURCE,ORIGIN,k) for k in (KEY,'other-travel-review-001')]
    def commit(p):
        c=app.get_conn()
        try: return pilot_service.browser(c,payload,RESOURCE,ORIGIN,p['operation_id'],confirm_digest=p['preview_digest'])['status']
        except mcp_actions.ActionError: return 'conflict'
        finally: c.close()
    with ThreadPoolExecutor(max_workers=2) as executor: result=list(executor.map(commit,previews))
    assert sorted(result)==['completed','conflict'] and travel.get_filing(conn,filing['id'])['review_round']==1


@pytest.mark.parametrize('outcome',['sent','false','raise','crash'])
def test_delivery_attempts_once_and_uncertainty_never_requeues(pilot,monkeypatch,outcome):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[]
    def send(*args,**kw):
        assert not conn.in_transaction
        calls.append(args)
        if outcome=='raise': raise RuntimeError('Synthetic timeout after possible acceptance')
        if outcome=='crash': raise KeyboardInterrupt('Synthetic process death')
        return {'sent':outcome=='sent'}
    if outcome=='crash':
        with pytest.raises(KeyboardInterrupt): delivery.run(conn,send=send)
        conn.execute('UPDATE mcp_travel_review_mail SET attempted_at=1');conn.commit()
    else: assert delivery.run(conn,send=send)==1
    delivery.run(conn,send=send)
    assert len(calls)==1
    status=conn.execute('SELECT state,payload_json FROM mcp_travel_review_mail').fetchone()
    assert status==('sent' if outcome=='sent' else 'uncertain',None)
    assert pilot_service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)['notification_status']==status[0]


def test_two_delivery_workers_send_once(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[]
    def send(*args,**kw): calls.append(args);return {'sent':True}
    def worker(_):
        c=app.get_conn()
        try:return delivery.run(c,send=send)
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor: totals=list(executor.map(worker,range(2)))
    assert sum(totals)==1 and len(calls)==1


def test_actual_dispatch_mobile_confirmation_and_scheduled_delivery(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,filing,token=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    context=AccessToken(token=token.access_token,client_id='review-test',scopes=[pilot_service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:context)
    async def journey():
        result=await server.call_tool('prepare_travel_review_request',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_REVIEW' not in str(result)
        context.scopes=['travel:filing:draft']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_travel_review_request',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/travel-review-requests/'+KEY)
                expect(page.get_by_role('heading',name='Request review of these travel papers?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: request travel review',exact=True).click()
                expect(page.get_by_role('heading',name='Travel review requested',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[];monkeypatch.setattr(mailer,'send',lambda *a,**kw:calls.append(a) or {'sent':True})
    assert app._mcp_travel_review_tick()==1 and len(calls)==1


@pytest.mark.parametrize('change,expected',[('feature','skipped_off'),('pause','skipped_off'),('transport','not_configured'),
    ('revoked','cancelled'),('reviewer','cancelled'),('approved','cancelled'),('payload','cancelled'),('expired','cancelled')])
def test_queued_notice_current_gates_and_expiry(pilot,monkeypatch,change,expected):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:change!='transport')
    if change=='feature':st.set_email_feature(conn,'travel_review_request',False)
    elif change=='pause':st.set_email_paused(conn,True)
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='reviewer':conn.execute("UPDATE resource_person SET archived_at='2026-10-27' WHERE id=?",(users[1]['rp_id'],))
    elif change=='approved':review.approve(conn,travel.get_filing(conn,filing['id']),users[1]['username'])
    elif change=='payload':conn.execute("UPDATE mcp_travel_review_mail SET payload_json='{}'")
    elif change=='expired':conn.execute('UPDATE mcp_travel_review_mail SET created_at=1')
    conn.commit()
    def no_send(*a,**kw):raise AssertionError('No transport is allowed for a blocked notice')
    assert delivery.run(conn,send=no_send)==0
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_review_mail').fetchone()==(expected,None)
    assert travel.get_filing(conn,filing['id'])['review_round']==1


def test_retry_after_feedback_resolves_sent_notes_once(pilot):
    conn,users,clients,app,filing,token=pilot
    conn.execute("UPDATE travel_filing SET review_state='changes',review_round=1,reviewer_id=?",(users[1]['id'],))
    conn.execute("INSERT INTO travel_review_note(filing_id,round,kind,note,state,created_by,created_at) VALUES (?,1,'other','Corrected note','sent',?,'2026-10-27')",(filing['id'],users[1]['username']))
    conn.commit();prepare(pilot)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview=pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY)
    assert preview['snapshot']['sent_notes_to_resolve']==1
    result=pilot_service.browser(conn,payload,RESOURCE,ORIGIN,KEY,confirm_digest=preview['preview_digest'])
    assert result['review_round']==2
    assert conn.execute('SELECT state FROM travel_review_note').fetchone()[0]=='resolved'
    assert prepare(pilot)['review_round']==2
    assert conn.execute('SELECT COUNT(*) FROM mcp_travel_review_mail').fetchone()[0]==1


def test_cleanup_discards_expired_queue_content_even_when_disabled(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    conn.execute('UPDATE mcp_travel_review_mail SET created_at=1');conn.commit()
    monkeypatch.setenv(pilot_service.FLAG,'0')
    assert delivery.run(conn)==0
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_review_mail').fetchone()==('cancelled',None)



def test_failure_recording_transport_result_never_sends_twice(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[]
    def send(*a,**kw):calls.append(a);return {'sent':True}
    original=delivery._finish
    def failed(*a,**kw):
        if kw.get('attempt_id'):raise RuntimeError('Synthetic database failure after accepted transport')
        return original(*a,**kw)
    monkeypatch.setattr(delivery,'_finish',failed)
    with pytest.raises(RuntimeError):delivery.run(conn,send=send)
    assert conn.execute('SELECT state FROM mcp_travel_review_mail').fetchone()[0]=='attempting'
    monkeypatch.setattr(delivery,'_finish',original)
    assert delivery.run(conn,send=send)==0 and len(calls)==1
    conn.execute('UPDATE mcp_travel_review_mail SET attempted_at=1');conn.commit()
    assert delivery.run(conn,send=send)==0 and len(calls)==1
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_review_mail').fetchone()==('uncertain',None)
