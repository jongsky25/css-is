"""Selected reviewer decisions bind exact papers/notes and commit once, with one email attempt."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_read
import mcp_travel_decisions as service
import mailer
import storage as st
import travel
import travel_review as review
import travel_decision_delivery as delivery
from tests.test_mcp_travel_reviews import pilot as request_pilot, form, TITLE, DOC, ORIGIN, RESOURCE
from tests.test_integration_read_api import api
from tests.test_work import workspace

KEY = 'travel-decision-operation-001'
NOTE = 'PRIVATE_NOTE <script>untrusted</script> Please correct this saved paper.'


@pytest.fixture
def pilot(request_pilot, monkeypatch):
    conn, users, clients, app, filing, _ = request_pilot
    traveller_rp = st.add_rp(conn, 'Synthetic traveller', True)
    conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?', (traveller_rp, users[0]['id'])); conn.commit()
    users[0] = st.get_admin_user_by_id(conn, users[0]['id'])
    review.request_review(conn, filing, users[1]['id'], users[0]['username'])
    monkeypatch.delenv('CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED')
    monkeypatch.setenv(service.FLAG, '1')
    token = mcp_auth.Provider._tokens(conn, 'review-test', users[1]['id'], [service.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, travel.get_filing(conn, filing['id']), token


def fields(pilot, **changes):
    revision = service.read_context(pilot[0], pilot[5].access_token, RESOURCE, ORIGIN, pilot[4]['id'])['expected_revision']
    return {'filing_id': pilot[4]['id'], 'expected_revision': revision, 'decision': 'approve', **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return service.prepare(pilot[0], pilot[5].access_token, RESOURCE, ORIGIN, operation_id, data or fields(pilot))


def confirm(pilot, operation_id=KEY):
    payload = auth.parse_token(pilot[2][1].cookies.get(auth.COOKIE_NAME))
    preview = service.browser(pilot[0], payload, RESOURCE, ORIGIN, operation_id)
    return service.browser(pilot[0], payload, RESOURCE, ORIGIN, operation_id, confirm_digest=preview['preview_digest'])


def add_note(pilot):
    review.add_note(pilot[0], pilot[4], '', 'incorrect', NOTE, pilot[1][1]['username'])


def path():
    return '/account/integrations/mcp/travel-review-decisions/' + KEY


@pytest.mark.parametrize('decision', ['approve', 'return_notes'])
def test_exact_browser_atomic_decision_receipt_preserves_later_round(pilot, monkeypatch, decision):
    conn, users, clients, app, filing, token = pilot
    if decision == 'return_notes': add_note(pilot)
    def no_send(*a, **kw): raise AssertionError('No email inside decision transaction')
    monkeypatch.setattr(mailer, 'send', no_send)
    unchanged = {t: conn.execute('SELECT * FROM '+t).fetchall() for t in ('travel_item', 'travel_flag', 'supply_stock_movement', 'calendar_entry')}
    args = fields(pilot, decision=decision)
    preview = prepare(pilot, data=args)
    assert prepare(pilot, data=args) == preview
    assert all(secret not in json.dumps(preview) for secret in (TITLE, DOC, NOTE, users[0]['username']))
    page = clients[1].get(path())
    assert page.status_code == 200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert users[0]['username'] in page.text and DOC not in page.text
    assert ('PRIVATE_NOTE' in page.text) == (decision == 'return_notes')
    assert not conn.execute('SELECT * FROM mcp_travel_decision_mail').fetchall()
    assert clients[1].post(path(), data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    result = service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert result['status']=='completed' and result['decision']==decision and result['review_round']==1
    assert result['recorded_review_state']==('approved' if decision=='approve' else 'changes')
    assert result['returned_note_count']==int(decision=='return_notes')
    assert result['next_actor']=={'role':'traveller','user_id':str(users[0]['id'])}
    assert result['notification_status']=='queued' and all(x not in json.dumps(result) for x in (TITLE,DOC,NOTE,users[0]['username']))
    assert prepare(pilot,data=args)==result
    assert clients[1].post(path(),data=form(page),headers={'Origin':ORIGIN}).status_code==200
    assert conn.execute('SELECT COUNT(*) FROM mcp_travel_decision_mail').fetchone()[0]==1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_travel_decision').fetchone()==(None,None)
    assert clients[1].get(result['web_url']).status_code==200
    done=travel.get_filing(conn,filing['id']);assert done['status']=='open'
    for table,before in unchanged.items():assert conn.execute('SELECT * FROM '+table).fetchall()==before
    if decision=='return_notes':
        assert review.notes_of(conn,filing['id'])[0]['state']=='sent'
        review.request_review(conn,done,users[1]['id'],users[0]['username'])
        assert service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)==result
        assert prepare(pilot,data=args)==result
        assert travel.get_filing(conn,filing['id'])['review_state']=='requested'
        assert service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])['can_approve_papers']
        prepare(pilot,'travel-decision-round-two');confirm(pilot,'travel-decision-round-two')
        assert conn.execute('SELECT COUNT(*) FROM mcp_travel_decision_mail').fetchone()[0]==2
    else:
        travel.mark_ready(conn,done)
        assert service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)==result
        assert travel.get_filing(conn,filing['id'])['status']=='ready'


@pytest.mark.parametrize('change', ['stamp','papers','raw_papers','missing','running','reviewer','reviewer_unit','owner',
    'inactive_traveller','recipient','traveller_name','notes','round','state','scope','revoked','expired','snapshot','payload','switch','module','mail','required'])
def test_current_gates_invalidate_exact_preview(pilot, monkeypatch, change):
    conn,users,clients,app,filing,token=pilot
    prepare(pilot);page=clients[1].get(path())
    if change=='stamp': conn.execute("UPDATE travel_filing SET updated_at='changed'")
    elif change=='papers': conn.execute("UPDATE travel_item SET drive_url='https://docs.google.com/document/d/changed/edit'")
    elif change=='raw_papers': conn.execute("UPDATE travel_item SET updated_at='changed'")
    elif change=='missing': conn.execute('UPDATE travel_item SET drive_url=NULL,doc_url=NULL')
    elif change=='running': conn.execute("UPDATE travel_filing SET gen_state='running'")
    elif change=='reviewer': conn.execute("UPDATE resource_person SET archived_at='2026-10-27' WHERE id=?",(users[1]['rp_id'],))
    elif change=='reviewer_unit':conn.execute("UPDATE org_unit SET name='Changed title' WHERE id=(SELECT org_unit_id FROM resource_person WHERE id=?)",(users[1]['rp_id'],))
    elif change=='owner': conn.execute('UPDATE travel_filing SET user_id=?',(users[2]['id'],))
    elif change=='inactive_traveller': conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(users[0]['id'],))
    elif change=='recipient': conn.execute("UPDATE admin_user SET username='changed@example.test' WHERE id=?",(users[0]['id'],))
    elif change=='traveller_name': conn.execute("UPDATE resource_person SET name='Changed traveller' WHERE id=?",(users[0]['rp_id'],))
    elif change=='notes':add_note(pilot)
    elif change=='round':conn.execute('UPDATE travel_filing SET review_round=2')
    elif change=='state':conn.execute("UPDATE travel_filing SET status='ready'")
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"travel:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_travel_decision SET expires_at=1')
    elif change=='snapshot':conn.execute('UPDATE mcp_travel_decision SET snapshot_json=NULL')
    elif change=='payload':conn.execute('UPDATE mcp_travel_decision SET payload_json=?',(json.dumps({'filing_id':filing['id']}),))
    elif change=='switch':monkeypatch.setenv(service.FLAG,'0')
    elif change=='module':st.set_setting(conn,'travel.enabled','0')
    elif change=='mail':st.set_email_feature(conn,'travel_review_result',False)
    else:st.set_setting(conn,review.SETTING,'0')
    conn.commit()
    assert clients[1].post(path(),data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert not conn.execute('SELECT * FROM mcp_travel_decision_mail').fetchall()
    assert travel.get_filing(conn,filing['id'])['review_state']=='requested'


@pytest.mark.parametrize('changed',[{'filing_id':True},{'filing_id':0},{'filing_id':-1},{'filing_id':2**63},{'filing_id':'1'},
    {'decision':True},{'decision':'pay'},{'decision':'reject'},{'expected_revision':''},{'expected_revision':'f'*63},
    {'notes':['invented']},{'email':'other@example.test'},{'approval':'approved'}])
def test_strict_fields(pilot,changed):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changed))


def test_permission_scope_grant_and_browser_boundaries(pilot):
    conn,users,clients,app,filing,token=pilot
    for uid in (users[0]['id'],users[2]['id']):
        other=mcp_auth.Provider._tokens(conn,'review-test',uid,[service.SCOPE],RESOURCE);conn.commit()
        with pytest.raises(permissions.Denied):service.read_context(conn,other.access_token,RESOURCE,ORIGIN,filing['id'])
    narrow=mcp_auth.Provider._tokens(conn,'review-test',users[1]['id'],['travel:read','travel:review:request'],RESOURCE)
    fresh=mcp_auth.Provider._tokens(conn,'review-test',users[1]['id'],[service.SCOPE],RESOURCE);conn.commit()
    args=fields(pilot);prepare(pilot,data=args)
    with pytest.raises(mcp_actions.ActionError):service.prepare(conn,narrow.access_token,RESOURCE,ORIGIN,KEY,args)
    with pytest.raises(permissions.Denied):service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    with pytest.raises(mcp_actions.ActionError):service.prepare(conn,token.access_token,RESOURCE,ORIGIN,KEY,{**args,'decision':'return_notes'})
    page=clients[1].get(path())
    assert clients[0].get(path()).status_code==404 and clients[2].get(path()).status_code==404
    assert clients[1].post(path(),data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[1].post(path(),data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[1].post(path(),data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):confirm(pilot)


@pytest.mark.parametrize('decision',['approve','return_notes'])
def test_selected_reviewer_cannot_self_decide(pilot,decision):
    conn,users,clients,app,filing,token=pilot
    if decision=='return_notes':add_note(pilot)
    conn.execute('UPDATE travel_filing SET user_id=?',(users[1]['id'],));conn.commit()
    with pytest.raises(permissions.Denied):prepare(pilot,data={'filing_id':filing['id'],'expected_revision':'f'*64,'decision':decision})


def test_approval_readiness_and_return_note_round_gates(pilot):
    conn,users,clients,app,filing,token=pilot
    with pytest.raises(mcp_actions.ActionError):prepare(pilot,data=fields(pilot,decision='return_notes'))
    add_note(pilot)
    with pytest.raises(mcp_actions.ActionError):prepare(pilot)
    conn.execute('UPDATE travel_review_note SET round=0');conn.commit()
    with pytest.raises(mcp_actions.ActionError):prepare(pilot,data=fields(pilot,decision='return_notes'))
    conn.execute('DELETE FROM travel_review_note')
    conn.execute('UPDATE travel_item SET drive_url=NULL,doc_url=NULL');conn.commit()
    assert not service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])['can_approve_papers']
    with pytest.raises(mcp_actions.ActionError):prepare(pilot)
    add_note(pilot);prepare(pilot,data=fields(pilot,decision='return_notes'));confirm(pilot)
    assert travel.get_filing(conn,filing['id'])['review_state']=='changes'


@pytest.mark.parametrize('decision',['approve','return_notes'])
@pytest.mark.parametrize('failure',['domain_audit','final_audit','mail'])
def test_atomic_rollback(pilot,monkeypatch,decision,failure):
    conn,users,clients,app,filing,token=pilot
    if decision=='return_notes':add_note(pilot)
    prepare(pilot,data=fields(pilot,decision=decision))
    original=st.audit
    def fail(*args,**kwargs):
        if args[2]==('integration_action_complete' if failure=='final_audit' else 'travel_review_approve' if decision=='approve' else 'travel_review_feedback'):
            raise RuntimeError('Synthetic audit failure')
        return original(*args,**kwargs)
    if failure=='mail':
        conn.execute("CREATE TRIGGER fail_decision_mail BEFORE INSERT ON mcp_travel_decision_mail BEGIN SELECT RAISE(ABORT,'Synthetic queue failure'); END");conn.commit()
    else:monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(Exception):confirm(pilot)
    assert travel.get_filing(conn,filing['id'])['review_state']=='requested'
    assert not conn.execute('SELECT * FROM mcp_travel_decision_mail').fetchall()
    assert conn.execute('SELECT completed_at FROM mcp_travel_decision').fetchone()==(None,)
    if decision=='return_notes':assert review.notes_of(conn,filing['id'])[0]['state']=='draft'


@pytest.mark.parametrize('same_key',[True,False])
def test_racing_confirmations_decide_once(pilot,same_key):
    conn,users,clients,app,filing,token=pilot
    keys=[KEY,KEY if same_key else 'travel-decision-operation-002']
    for key in set(keys):prepare(pilot,key)
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME))
    previews=[service.browser(conn,payload,RESOURCE,ORIGIN,key) for key in keys]
    def commit(p):
        c=app.get_conn()
        try:return service.browser(c,payload,RESOURCE,ORIGIN,p['operation_id'],confirm_digest=p['preview_digest'])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(commit,previews))
    assert sorted(results)==(['completed','completed'] if same_key else ['completed','conflict'])
    assert conn.execute('SELECT COUNT(*) FROM mcp_travel_decision_mail').fetchone()[0]==1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='travel_review_approve'").fetchone()[0]==1


@pytest.mark.parametrize('decision',['approve','return_notes'])
@pytest.mark.parametrize('outcome',['sent','false','raise','crash','write_failure'])
def test_email_single_attempt_with_exact_native_content(pilot,monkeypatch,decision,outcome):
    conn,users,clients,app,filing,token=pilot
    if decision=='return_notes':add_note(pilot)
    prepare(pilot,data=fields(pilot,decision=decision));confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[];original=delivery._finish
    def finish(*a,**kw):
        if outcome=='write_failure' and kw.get('attempt_id'):raise RuntimeError('Synthetic result-write failure')
        return original(*a,**kw)
    monkeypatch.setattr(delivery,'_finish',finish)
    def send(to,subject,body,html=None):
        assert not conn.in_transaction and to==users[0]['username']
        assert ('PRIVATE_NOTE' in body)==(decision=='return_notes')
        assert DOC not in body and 'PRIVATE_REVIEW' in body and filing['ref_code'] in body
        assert '<script>untrusted</script>' not in html
        calls.append(to)
        if outcome=='raise':raise RuntimeError('Synthetic provider timeout')
        if outcome=='crash':raise KeyboardInterrupt('Synthetic process death')
        return {'sent':outcome in ('sent','write_failure')}
    if outcome=='crash':
        with pytest.raises(KeyboardInterrupt):delivery.run(conn,send=send)
    elif outcome=='write_failure':
        with pytest.raises(RuntimeError):delivery.run(conn,send=send)
    else:assert delivery.run(conn,send=send)==1
    if outcome in ('crash','write_failure'):
        conn.execute('UPDATE mcp_travel_decision_mail SET attempted_at=1');conn.commit()
    delivery.run(conn,send=send)
    assert calls==[users[0]['username']]
    state='sent' if outcome=='sent' else 'uncertain'
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_decision_mail').fetchone()==(state,None)
    assert service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)['notification_status']==state


@pytest.mark.parametrize('change',['recipient','papers','notes','reviewer','round','ready','grant','identity','mail','pause','config'])
def test_worker_current_source_recipient_and_policy(pilot,monkeypatch,change):
    conn,users,clients,app,filing,token=pilot
    prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    if change=='recipient':conn.execute("UPDATE admin_user SET username='other@example.test' WHERE id=?",(users[0]['id'],))
    elif change=='papers':conn.execute("UPDATE travel_item SET doc_url='changed'")
    elif change=='notes':conn.execute("UPDATE travel_filing SET act_title='changed'")
    elif change=='reviewer':conn.execute('UPDATE travel_filing SET reviewer_id=?',(users[2]['id'],))
    elif change=='round':conn.execute('UPDATE travel_filing SET review_round=2')
    elif change=='ready':travel.mark_ready(conn,travel.get_filing(conn,filing['id']))
    elif change=='grant':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='identity':conn.execute("UPDATE travel_filing SET opened_at='reused-source'")
    elif change=='mail':st.set_email_feature(conn,'travel_review_result',False)
    elif change=='pause':st.set_email_paused(conn,True)
    else:monkeypatch.setattr(mailer,'email_configured',lambda:False)
    conn.commit()
    def no_send(*a,**kw):raise AssertionError('Current gate must suppress transport')
    assert delivery.run(conn,send=no_send)==0
    expected='skipped_off' if change in ('mail','pause') else 'not_configured' if change=='config' else 'cancelled'
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_decision_mail').fetchone()==(expected,None)


def test_disabled_at_confirmation_terminal_cleanup_and_worker_race(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot
    st.set_email_feature(conn,'travel_review_result',False)
    prepare(pilot);confirm(pilot)
    st.set_email_feature(conn,'travel_review_result',True)
    assert delivery.run(conn,send=lambda *a,**k:pytest.fail('No late enable send'))==0
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_decision_mail').fetchone()==('skipped_off',None)
    assert conn.execute("SELECT status FROM email_log WHERE feature='travel_review_result'").fetchone()==('skipped_off',)


def test_two_workers_claim_once_and_scheduler_hook(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    monkeypatch.setattr(mailer,'email_configured',lambda:True)
    calls=[]
    def send(*a,**kw):calls.append(a);return {'sent':True}
    monkeypatch.setattr(delivery,'_transport',send)
    with ThreadPoolExecutor(max_workers=2) as executor:totals=list(executor.map(lambda _:app._mcp_travel_review_tick(),range(2)))
    assert sum(totals)==1 and len(calls)==1


def test_limits_cleanup_and_identity_not_replayed(pilot,monkeypatch):
    conn,users,clients,app,filing,token=pilot
    args=fields(pilot)
    for i in range(50):prepare(pilot,'travel-decision-capacity-%03d'%i,args)
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'travel-decision-over-limit',args)
    conn.execute('UPDATE mcp_travel_decision SET expires_at=1');conn.commit()
    monkeypatch.setenv(service.FLAG,'0');delivery.run(conn)
    assert conn.execute('SELECT COUNT(*) FROM mcp_travel_decision WHERE payload_json IS NOT NULL').fetchone()[0]==0
    monkeypatch.setenv(service.FLAG,'1');prepare(pilot);confirm(pilot)
    conn.execute("UPDATE travel_filing SET review_state='requested'");conn.commit()
    assert not service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])['can_approve_papers']
    with pytest.raises(mcp_actions.ActionError):prepare(pilot,'travel-decision-replay-key')
    conn.execute('UPDATE mcp_travel_decision_mail SET created_at=1');conn.commit()
    monkeypatch.setenv(service.FLAG,'0');delivery.run(conn)
    assert conn.execute('SELECT state,payload_json FROM mcp_travel_decision_mail').fetchone()==('cancelled',None)


@pytest.mark.parametrize('decision',['approve','return_notes'])
def test_sdk_dispatch_and_mobile_no_javascript(pilot,monkeypatch,decision):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,filing,token=pilot
    if decision=='return_notes':add_note(pilot)
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    context=AccessToken(token=token.access_token,client_id='review-test',scopes=[service.SCOPE],resource=RESOURCE,subject=str(users[1]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:context)
    async def journey():
        args=fields(pilot,decision=decision)
        result=await server.call_tool('get_travel_review_decision_context',{'filing_id':filing['id']})
        assert 'expected_revision' in str(result) and 'PRIVATE_NOTE' not in str(result)
        result=await server.call_tool('prepare_travel_review_decision',{**args,'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_REVIEW' not in str(result)
        context.scopes=['travel:read']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_travel_review_decision',{**args,'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[1],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+path())
                expect(page.get_by_role('heading',name='Confirm travel papers decision?',exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: papers are complete' if decision=='approve' else 'Confirm: return these notes',exact=True).click()
                expect(page.get_by_role('heading',name='Travel papers decision recorded',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


@pytest.mark.parametrize('decision',['approve','return_notes'])
def test_native_decision_requires_caller_transaction_and_rolls_back(pilot,decision):
    conn,users,clients,app,filing,token=pilot
    if decision=='return_notes':add_note(pilot)
    fn=review.approve if decision=='approve' else review.send_feedback
    with pytest.raises(RuntimeError,match='caller-owned'):
        fn(conn,filing,users[1]['username'],commit=False)
    from documents_storage import transaction
    with pytest.raises(RuntimeError,match='Synthetic'):
        with transaction(conn):
            fn(conn,filing,users[1]['username'],commit=False)
            raise RuntimeError('Synthetic later transaction failure')
    assert travel.get_filing(conn,filing['id'])['review_state']=='requested'
    if decision=='return_notes':assert review.notes_of(conn,filing['id'])[0]['state']=='draft'


def test_technical_admin_selected_without_section_membership_is_denied(pilot):
    conn,users,clients,app,filing,token=pilot
    conn.execute("UPDATE admin_user SET role='admin' WHERE id=?",(users[2]['id'],))
    conn.execute('UPDATE travel_filing SET reviewer_id=?',(users[2]['id'],))
    technical=mcp_auth.Provider._tokens(conn,'review-test',users[2]['id'],[service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):service.read_context(conn,technical.access_token,RESOURCE,ORIGIN,filing['id'])


@pytest.mark.parametrize('change',['purge','source_identity','traveller','selected_reviewer','original_marker'])
def test_completed_receipt_requires_original_visible_source_and_marker(pilot,change):
    conn,users,clients,app,filing,token=pilot;prepare(pilot);confirm(pilot)
    if change=='purge':conn.execute("UPDATE travel_filing SET purged_at='2026-10-27'")
    elif change=='source_identity':conn.execute("UPDATE travel_filing SET opened_at='new-source'")
    elif change=='traveller':conn.execute('UPDATE travel_filing SET user_id=?',(users[2]['id'],))
    elif change=='selected_reviewer':conn.execute('UPDATE travel_filing SET reviewer_id=?',(users[2]['id'],))
    else:conn.execute('DELETE FROM mcp_travel_decision_mail')
    conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert travel.get_filing(conn,filing['id'])['review_state']=='approved'


def test_large_note_history_uses_ordinary_review(pilot):
    conn,users,clients,app,filing,token=pilot
    for _ in range(101):add_note(pilot)
    with pytest.raises(mcp_actions.ActionError,match='larger filing'):
        service.read_context(conn,token.access_token,RESOURCE,ORIGIN,filing['id'])
    assert not conn.execute('SELECT * FROM mcp_travel_decision').fetchall()
