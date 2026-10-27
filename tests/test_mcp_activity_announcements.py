"""First pinned publication: current authority, exact review, durable identity, no mail."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json

import pytest
from mcp.server.auth.provider import AccessToken

import activity_announcements as publication
import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_activity_announcements as service
import mcp_read
import mailer
import storage as st
import tzutil as tz
from tests.test_mcp_activity_dates import pilot as date_pilot,form,ORIGIN,RESOURCE,TITLE
from tests.test_integration_read_api import api
from tests.test_work import workspace

KEY='activity-pinned-publication-001'
TEXT='PUBLIC_UPDATE <script>untrusted</script>\nPlease arrive at 9 AM.'


@pytest.fixture
def pilot(date_pilot,monkeypatch):
    conn,users,clients,app,old_token,ev,fid=date_pilot
    monkeypatch.setenv(service.FLAG,'1')
    monkeypatch.delenv('CSS_MCP_ACTIVITY_DATES_ENABLED',raising=False)
    token=mcp_auth.Provider._tokens(conn,'date-test',users[0]['id'],[service.SCOPE],RESOURCE);conn.commit()
    return conn,users,clients,app,token,ev,fid


def fields(pilot,**changes):
    _,_,info=publication.source(pilot[0],pilot[1][0],pilot[5]['id'])
    return {'event_id':pilot[5]['id'],'expected_revision':info['expected_revision'],'announcement':TEXT,**changes}


def prepare(pilot,key=KEY,data=None):
    return service.prepare(pilot[0],pilot[4].access_token,RESOURCE,ORIGIN,key,data or fields(pilot))


def confirm(pilot,key=KEY):
    payload=auth.parse_token(pilot[2][0].cookies.get(auth.COOKIE_NAME))
    preview=service.browser(pilot[0],payload,RESOURCE,ORIGIN,key)
    return service.browser(pilot[0],payload,RESOURCE,ORIGIN,key,confirm_digest=preview['preview_digest'])


def test_exact_publication_and_original_receipt_preserve_later_ui_changes(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot
    monkeypatch.setattr(mailer,'send',lambda *a,**k:pytest.fail('No mail from publication'))
    context=service.read_context(conn,token.access_token,RESOURCE,ORIGIN,ev['event_token'])
    assert context['registered_count']==0 and 'PRIVATE' not in json.dumps(context)
    original=fields(pilot);before=prepare(pilot,data=original)
    assert prepare(pilot,data=original)==before and 'PUBLIC_UPDATE' not in json.dumps(before)
    assert st.get_event(conn,ev['event_token'])['announcement'] is None
    path='/account/integrations/mcp/activity-announcements/'+KEY;page=clients[0].get(path)
    assert page.status_code==200 and 'PUBLIC_UPDATE' in page.text and '&lt;script&gt;' in page.text
    assert '<script>untrusted</script>' not in page.text and 'PRIVATE_LOCATION' not in page.text and 'PRIVATE_MESSAGE' not in page.text
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code==200
    receipt=service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)
    assert receipt['publication_status']=='published' and receipt['notification_status']=='none_created'
    assert receipt['registered_count_at_publication']==0 and 'PUBLIC_UPDATE' not in json.dumps(receipt)
    assert receipt['next_actor']=={'role':'organizer_manage_activity'}
    assert st.get_event(conn,ev['event_token'])['announcement']==TEXT
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_activity_announcements').fetchone()==(None,None)
    assert conn.execute('SELECT COUNT(*) FROM activity_announcement_publication').fetchone()[0]==1
    assert 'PUBLIC_UPDATE' not in clients[2].get(receipt['participant_url']).text
    aid=st.add_attendee(conn,ev['id'],name='Synthetic participant',email='participant@example.test',sex='F',affiliation='DOH',consent_text='Synthetic consent')
    conn.commit()
    # Existing post-consent participant page rendering must escape the text.
    clients[2].cookies.set(app._attendee_cookie_name(ev['id']),auth.make_attendee_token(aid))
    shown=clients[2].get(receipt['participant_url'])
    assert 'PUBLIC_UPDATE' in shown.text and '<script>untrusted</script>' not in shown.text
    assert clients[0].post('/activities/'+ev['event_token']+'/announcement',data={'announcement':'Later ordinary edit'},headers={'Origin':ORIGIN}).status_code in (200,303)
    assert prepare(pilot,data=original)==receipt
    assert st.get_event(conn,ev['event_token'])['announcement']=='Later ordinary edit'
    assert clients[0].post('/activities/'+ev['event_token']+'/announcement',data={'announcement':''},headers={'Origin':ORIGIN}).status_code in (200,303)
    assert prepare(pilot,data=original)==receipt and st.get_event(conn,ev['event_token'])['announcement'] is None
    with pytest.raises(mcp_actions.ActionError):service.read_context(conn,token.access_token,RESOURCE,ORIGIN,ev['event_token'])
    with pytest.raises(mcp_actions.ActionError):prepare(pilot,'replacement-publication-key',original)
    assert conn.execute('SELECT COUNT(*) FROM event').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM form_instance').fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM email_log').fetchone()[0]==0


@pytest.mark.parametrize('change',['source','authority','form','archive','existing','registration','outside','past','scope','revoked','expired','payload','snapshot','switch','global_switch'])
def test_bound_context_rechecked_before_publication(pilot,monkeypatch,change):
    conn,users,clients,app,token,ev,fid=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/activity-announcements/'+KEY;page=clients[0].get(path)
    if change=='source':conn.execute("UPDATE event SET welcome_message='Changed' WHERE id=?",(ev['id'],))
    elif change=='authority':conn.execute('UPDATE event SET created_by=? WHERE id=?',(users[2]['username'],ev['id']))
    elif change=='form':conn.execute("UPDATE form_instance SET topic='Changed' WHERE id=?",(fid,))
    elif change=='archive':conn.execute('UPDATE form_instance SET archived=1 WHERE id=?',(fid,))
    elif change=='existing':st.set_event_announcement(conn,ev['id'],'Ordinary existing update',tz.now_iso())
    elif change=='registration':st.add_attendee(conn,ev['id'],name='Synthetic registration',email='test@example.test',sex='F',affiliation='DOH',consent_text='Consent')
    elif change=='outside':conn.execute("UPDATE event SET event_kind='outside' WHERE id=?",(ev['id'],))
    elif change=='past':monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,8))
    elif change=='scope':conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"activities:read\"]'")
    elif change=='revoked':conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change=='expired':conn.execute('UPDATE mcp_activity_announcements SET expires_at=1')
    elif change=='payload':conn.execute('UPDATE mcp_activity_announcements SET payload_json=?',(json.dumps({**original,'announcement':'Tampered'}),))
    elif change=='snapshot':conn.execute('UPDATE mcp_activity_announcements SET snapshot_json=NULL')
    elif change=='global_switch':monkeypatch.setenv('CSS_MCP_ENABLED','0')
    else:monkeypatch.setenv(service.FLAG,'0')
    conn.commit()
    assert clients[0].post(path,data=form(page),headers={'Origin':ORIGIN}).status_code in (404,409)
    assert conn.execute('SELECT COUNT(*) FROM activity_announcement_publication').fetchone()[0]==0
    assert st.get_event(conn,ev['event_token'])['announcement']==('Ordinary existing update' if change=='existing' else None)


@pytest.mark.parametrize('changes',[
    {'event_id':True},{'event_id':'1'},{'event_id':0},{'expected_revision':'guess'},
    {'announcement':''},{'announcement':'   '},{'announcement':'x'*1001},{'announcement':'bad\x00text'},
    {'email_registrants':True},{'recipients':['x@example.test']},{'title':'Override'},{'status':'cancelled'},
])
def test_strict_text_and_no_unreviewed_side_effects(pilot,changes):
    with pytest.raises(ValueError):prepare(pilot,data=fields(pilot,**changes))


def test_security_connection_and_atomic_rollback(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot;original=fields(pilot);prepare(pilot,data=original)
    path='/account/integrations/mcp/activity-announcements/'+KEY;page=clients[0].get(path)
    assert clients[1].get(path).status_code==404
    assert clients[0].post(path,data={**form(page),'csrf':'bad'},headers={'Origin':ORIGIN}).status_code==403
    assert clients[0].post(path,data=form(page),headers={'Origin':'https://evil.example'}).status_code==403
    assert clients[0].post(path,data={**form(page),'preview_digest':'bad'},headers={'Origin':ORIGIN}).status_code==409
    with pytest.raises(mcp_actions.ActionError,match='different'):prepare(pilot,data={**original,'announcement':'Other'})
    fresh=mcp_auth.Provider._tokens(conn,'date-test',users[0]['id'],[service.SCOPE],RESOURCE);conn.commit()
    with pytest.raises(permissions.Denied):service.recover(conn,fresh.access_token,RESOURCE,ORIGIN,KEY)
    saved_audit=st.audit
    def fail(c,actor,action,**kw):
        if action=='integration_action_complete':raise RuntimeError('Synthetic final audit failure')
        return saved_audit(c,actor,action,**kw)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):confirm(pilot)
    assert st.get_event(conn,ev['event_token'])['announcement'] is None
    assert conn.execute('SELECT COUNT(*) FROM activity_announcement_publication').fetchone()[0]==0
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='event_announcement_set'").fetchone()[0]==0
    assert conn.execute('SELECT completed_at FROM mcp_activity_announcements').fetchone()[0] is None
    with pytest.raises(RuntimeError,match='caller-owned'):st.set_event_announcement(conn,ev['id'],'X',tz.now_iso(),commit=False)


def test_two_keys_and_same_key_races_commit_once(pilot):
    conn,users,clients,app,token,ev,fid=pilot;original=fields(pilot)
    keys=(KEY,'competing-publication-key-001')
    for key in keys:prepare(pilot,key,original)
    payload=auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    digests={key:service.browser(conn,payload,RESOURCE,ORIGIN,key)['preview_digest'] for key in keys}
    def worker(key):
        c=app.get_conn()
        try:return service.browser(c,payload,RESOURCE,ORIGIN,key,confirm_digest=digests[key])['status']
        except mcp_actions.ActionError:return 'conflict'
        finally:c.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,keys))
    assert sorted(results)==['completed','conflict'];winner=keys[results.index('completed')]
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(worker,(winner,winner)))==['completed','completed']
    assert conn.execute('SELECT COUNT(*) FROM activity_announcement_publication').fetchone()[0]==1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='event_announcement_set'").fetchone()[0]==1


def test_management_parity_retagging_and_original_identity(pilot):
    conn,users,clients,app,token,ev,fid=pilot
    for idx,allowed in ((0,True),(1,True),(2,False),(4,True)):
        current=st.get_admin_user_by_id(conn,users[idx]['id'])
        assert app._can_manage_event(current,st.get_event(conn,ev['event_token']),conn)==allowed
        granted=mcp_auth.Provider._tokens(conn,'date-test',current['id'],[service.SCOPE],RESOURCE);conn.commit()
        if allowed:assert service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,ev['event_token'])['event_id']==str(ev['id'])
        else:
            with pytest.raises(permissions.Denied):service.read_context(conn,granted.access_token,RESOURCE,ORIGIN,ev['event_token'])
    prepare(pilot);confirm(pilot)
    conn.execute('DELETE FROM event_form WHERE event_id=?',(ev['id'],));conn.execute('DELETE FROM event WHERE id=?',(ev['id'],));conn.commit()
    new=st.create_event(conn,'Reused numeric source','2030-03-09',form_instance_ids=[fid],created_by=users[0]['username'])
    assert new['id']==ev['id']
    with pytest.raises(permissions.Denied):service.recover(conn,token.access_token,RESOURCE,ORIGIN,KEY)


def test_capacity_cleanup_and_disabled_pilot(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot
    for i in range(50):prepare(pilot,'publication-capacity-'+str(i))
    with pytest.raises(mcp_actions.ActionError,match='limit'):prepare(pilot,'publication-capacity-overflow')
    conn.execute('UPDATE mcp_activity_announcements SET expires_at=1');conn.commit();monkeypatch.setenv(service.FLAG,'0')
    with pytest.raises(mcp_actions.ActionError):service.recover(conn,token.access_token,RESOURCE,ORIGIN,'publication-capacity-0')
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_announcements WHERE payload_json IS NOT NULL OR snapshot_json IS NOT NULL').fetchone()[0]==0
    assert conn.execute('SELECT COUNT(*) FROM mcp_activity_announcements').fetchone()[0]==50


def test_sdk_and_mobile_confirmation_without_javascript(pilot,monkeypatch):
    from playwright.sync_api import sync_playwright,expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn,users,clients,app,token,ev,fid=pilot
    server,_=mcp_read.build_server(app.get_conn,ORIGIN)
    access=AccessToken(token=token.access_token,client_id='date-test',scopes=[service.SCOPE],resource=RESOURCE,subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read,'get_access_token',lambda:access)
    async def journey():
        result=await server.call_tool('prepare_activity_announcement',{**fields(pilot),'operation_id':KEY})
        assert 'awaiting_confirmation' in str(result) and 'PUBLIC_UPDATE' not in str(result)
        access.scopes=['activities:read']
        with pytest.raises(Exception,match='explicitly allow'):await server.call_tool('prepare_activity_announcement',{**fields(pilot),'operation_id':KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
        try:
            bc,page=page_for(browser,clients[0],viewport={'width':320,'height':844},java_script_enabled=False)
            try:
                page.goto(ORIGIN+'/account/integrations/mcp/activity-announcements/'+KEY)
                expect(page.get_by_role('heading',name="Publish this activity's first pinned update?",exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el)=>el.scrollWidth<=window.innerWidth')
                page.get_by_role('button',name='Confirm: publish pinned update',exact=True).click()
                expect(page.get_by_role('heading',name='Pinned update published',exact=True)).to_be_visible()
            finally:bc.close()
        finally:browser.close()


def test_team_retagging_and_session_revocation_block_confirmation(pilot):
    conn,users,clients,app,token,ev,fid=pilot
    manager=mcp_auth.Provider._tokens(conn,'date-test',users[1]['id'],[service.SCOPE],RESOURCE);conn.commit()
    _,_,info=publication.source(conn,users[1],ev['id'])
    service.prepare(conn,manager.access_token,RESOURCE,ORIGIN,KEY,
        {'event_id':ev['id'],'expected_revision':info['expected_revision'],'announcement':TEXT})
    payload=auth.parse_token(clients[1].cookies.get(auth.COOKIE_NAME))
    original=service.browser(conn,payload,RESOURCE,ORIGIN,KEY)
    other=st.add_org_unit(conn,'Other division','division','OTHER/DIV')
    conn.execute('UPDATE event SET lead_org_id=? WHERE id=?',(other,ev['id']));conn.commit()
    with pytest.raises(permissions.Denied):service.browser(conn,payload,RESOURCE,ORIGIN,KEY,confirm_digest=original['preview_digest'])
    conn.execute('DELETE FROM login_session WHERE session_id=?',(payload['sid'],));conn.commit()
    with pytest.raises(permissions.Denied):service.browser(conn,payload,RESOURCE,ORIGIN,KEY)
    assert conn.execute('SELECT COUNT(*) FROM activity_announcement_publication').fetchone()[0]==0


def test_existing_registrations_and_today_are_allowed_without_email(pilot,monkeypatch):
    conn,users,clients,app,token,ev,fid=pilot
    monkeypatch.setattr(tz,'today_local',lambda:date(2030,3,7))
    st.add_attendee(conn,ev['id'],name='Already registered',email='already@example.test',sex='F',affiliation='DOH',consent_text='Consent')
    conn.commit();prepare(pilot);result=confirm(pilot)
    assert result['registered_count_at_publication']==1 and result['notification_status']=='none_created'
    assert conn.execute('SELECT COUNT(*) FROM email_log').fetchone()[0]==0
