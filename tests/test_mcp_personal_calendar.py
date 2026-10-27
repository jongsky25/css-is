"""Personal calendar entries require explicit confirmation and send no invitations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import documents as docs
import documents_permissions as permissions
from documents_storage import transaction
import mcp_actions
import mcp_auth
import mcp_read
import mcp_personal_calendar as pilot_service
import personal_calendar as views
import storage as st
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'personal-calendar-operation-001'
NAME = 'PRIVATE_ENTRY <script>untrusted</script>'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG):
        monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_COMMENT_DRAFTS_ENABLED', 'CSS_MCP_SUPPLY_DRAFTS_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('calendar-test', json.dumps({'client_name': 'Calendar test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'calendar-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, token


def fields(**changes):
    return {'title': NAME, 'start_date': '2026-11-02', 'venue': 'Palo', 'note': 'Private planning note', **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[4].access_token, RESOURCE, ORIGIN, operation_id, data or fields())


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1)
            for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


@pytest.mark.parametrize('change', ['scope', 'revoked', 'expired', 'switch', 'payload'])
def test_current_gates_and_preview_digest(pilot, monkeypatch, change):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/personal-calendar/' + KEY
    page = clients[0].get(path)
    if change == 'scope':
        conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"work:read\"]'")
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired':
        conn.execute('UPDATE mcp_personal_calendar_operation SET expires_at=1')
    elif change == 'switch':
        monkeypatch.setenv(pilot_service.FLAG, '0')
    else:
        conn.execute('UPDATE mcp_personal_calendar_operation SET payload_json=?', (json.dumps(fields(title='Changed')),))
    conn.commit()
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 0
    if change == 'expired':
        assert conn.execute('SELECT payload_json FROM mcp_personal_calendar_operation').fetchone()[0] is None


def test_scope_connection_csrf_and_current_session_boundaries(pilot, monkeypatch):
    conn, users, clients, app, token = pilot
    monkeypatch.delenv(pilot_service.FLAG)
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        prepare(pilot)
    monkeypatch.setenv(pilot_service.FLAG, '1')
    prepare(pilot)
    path = '/account/integrations/mcp/personal-calendar/' + KEY
    page = clients[0].get(path)
    assert clients[1].get(path).status_code == 404
    for values, origin in (({**form(page), 'csrf': 'bad'}, ORIGIN), (form(page), 'https://evil.example'),
                           ({**form(page), 'confirm': 'no'}, ORIGIN)):
        assert clients[0].post(path, data=values, headers={'Origin': origin}).status_code == 403
    assert clients[0].post(path, data={**form(page), 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different personal calendar entry'):
        prepare(pilot, data=fields(title='Changed'))
    fresh = mcp_auth.Provider._tokens(conn, 'calendar-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    read_only = mcp_auth.Provider._tokens(conn, 'calendar-test', users[0]['id'], ['surveys:csm:read', 'work:comment:draft'], RESOURCE)
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, fresh.access_token, RESOURCE, ORIGIN, KEY)
    with pytest.raises(mcp_actions.ActionError, match='explicitly allow'):
        pilot_service.prepare(conn, read_only.access_token, RESOURCE, ORIGIN, 'read-report-operation-001', fields())
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?', (payload['sid'],))
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)


def test_atomic_audit_failure_and_two_confirmations(pilot, monkeypatch):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    original = st.audit
    def failed(*args, **kwargs):
        if args[2] == 'integration_action_complete':
            raise RuntimeError('synthetic completion audit failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(st, 'audit', failed)
    with pytest.raises(RuntimeError):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 0
    monkeypatch.setattr(st, 'audit', original)
    def confirm(_):
        c = app.get_conn()
        try:
            return pilot_service.browser(c, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, range(2)))
    assert results[0] == results[1]
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1
    # A receipt must never attach to a replacement record with a reused ID.
    conn.execute("UPDATE calendar_entry SET uid='replacement-uid'")
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


def test_actual_mcp_dispatch_and_mobile_no_script_confirmation(pilot, monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='calendar-test', scopes=[pilot_service.SCOPE], resource=RESOURCE,
                          subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        result = await server.call_tool('prepare_personal_calendar_entry', {**fields(), 'operation_id': KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_ENTRY' not in str(result)
        context.scopes = ['surveys:csm:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_personal_calendar_entry', {**fields(), 'operation_id': KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            browser_context, page = page_for(browser, clients[0], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/personal-calendar/' + KEY)
                expect(page.get_by_role('heading', name='Save this personal calendar entry?', exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 0
                page.get_by_role('button', name='Confirm: save my calendar entry', exact=True).click()
                page.get_by_role('link', name='Open my calendar entry', exact=True).click()
                expect(page.get_by_text(NAME, exact=True).first).to_be_visible()
            finally:
                browser_context.close()
        finally:
            browser.close()


def test_personal_entry_exact_source_and_replay_have_no_external_effects(pilot, monkeypatch):
    import office_calendar as oc
    conn, users, clients, app, token = pilot
    unchanged = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in
                 ('calendar_outbox', 'room_reservation', 'travel_filing', 'event', 'response', 'work_task')}
    preview = prepare(pilot)
    assert prepare(pilot) == preview and NAME not in json.dumps(preview)
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 0
    path = '/account/integrations/mcp/personal-calendar/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200 and '&lt;script&gt;' in page.text
    assert '<script>untrusted</script>' not in page.text
    assert 'Only you' in page.text and 'All day' in page.text
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    receipt = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['entry_id']
    assert NAME not in json.dumps(receipt)
    assert prepare(pilot) == receipt
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 1
    entry_id = int(receipt['entry_id'])
    saved = views.get(conn, users[0], entry_id)
    assert saved['title'] == NAME and saved['note'] == fields()['note']
    assert saved['start_date'] == '2026-11-02' and saved['end_date'] is None
    assert saved['kind'] == 'meeting' and saved['status'] == 'tentative'
    assert saved['audience'] == 'people' and saved['owner_org_id'] is None
    assert saved['event_id'] is None and saved['rrule'] is None and saved['meeting_url'] is None
    assert [p['user_id'] for p in saved['people']] == [users[0]['id']]
    assert not saved['extra_org_ids'] and not saved['tags']
    for other in (users[1], users[4]):
        assert oc.viewable_entry(conn, other, entry_id) is None
    assert clients[0].get(receipt['web_url']).status_code == 200
    assert clients[1].get(receipt['web_url']).status_code == 404
    for table, before in unchanged.items():
        assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    assert conn.execute('SELECT payload_json FROM mcp_personal_calendar_operation').fetchone()[0] is None
    assert fields()['note'] not in str(conn.execute('SELECT summary,before_text,after_text FROM audit_log').fetchall())
    # A later ordinary UI edit is never overwritten by recovery/retries.
    st.cal_update(conn, entry_id, by=users[0]['username'], title='Edited later')
    assert prepare(pilot) == receipt
    assert st.cal_get(conn, entry_id)['title'] == 'Edited later'
    monkeypatch.delenv(pilot_service.FLAG)
    assert clients[0].get(receipt['web_url']).status_code == 200


@pytest.mark.parametrize('changed', [
    {'title': ''}, {'title': '  '}, {'title': 'x'*201}, {'title': 'two\nlines'},
    {'venue': 'bad\x00'}, {'note': 'hidden\x00'}, {'note': 'x'*2001},
    {'start_date': '2026-02-30'}, {'start_date': '20261102'}, {'start_date': True},
    {'end_date': '2026-11-01'}, {'end_date': '2028-11-02'},
    {'start_time': '09:00'}, {'start_time': '', 'end_time': ''},
    {'start_time': '25:00', 'end_time': '26:00'}, {'start_time': '10:00', 'end_time': '09:00'},
    {'audience': 'bureau'}, {'people': [2]}, {'room_id': 1}, {'meeting_url': 'https://example.com'},
    {'kind': 'travel'}, {'repeat': 'weekly'}, {'status': 'confirmed'},
])
def test_invalid_or_extra_fields_never_create_entries(pilot, changed):
    with pytest.raises(ValueError):
        prepare(pilot, data=fields(**changed))
    assert pilot[0].execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 0
    assert pilot[0].execute('SELECT COUNT(*) FROM mcp_personal_calendar_operation').fetchone()[0] == 0


def test_timed_multiday_and_current_calendar_eligibility(pilot):
    conn, users, clients, app, token = pilot
    rp = conn.execute("INSERT INTO resource_person(name,is_internal) VALUES ('Synthetic calendar staff',1)").lastrowid
    conn.execute('UPDATE admin_user SET rp_id=? WHERE id=?', (rp, users[0]['id']))
    token = mcp_auth.Provider._tokens(conn, 'calendar-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    pilot = conn, users, clients, app, token
    values = fields(start_time='09:30', end_time='08:00', end_date='2026-11-03')
    prepare(pilot, data=values)
    path = '/account/integrations/mcp/personal-calendar/' + KEY
    page = clients[0].get(path)
    assert 'Asia/Manila' in page.text and '09:30 to 08:00' in page.text
    # Eligibility can disappear without changing the grant/account.
    conn.execute("UPDATE resource_person SET archived_at='2026-10-27' WHERE id=?", (rp,))
    conn.commit()
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 404
    assert conn.execute('SELECT COUNT(*) FROM calendar_entry').fetchone()[0] == 0
