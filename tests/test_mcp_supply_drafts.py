"""New own supply draft previews: no submission, stock or duplicate creation."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import re
import time

import pytest
from starlette.testclient import TestClient
from mcp.server.auth.provider import AccessToken

import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_read
import mcp_supply_drafts as drafts
import storage as st
from tests.conftest import session_token
from tests.test_supplies import supplies_db, setup_catalog, create, key
from tests.test_supplies_requests import request_db

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'supply-draft-test-operation-001'


@pytest.fixture
def pilot(request_db, app_mod, monkeypatch):
    conn, users, units, path, item = request_db
    monkeypatch.setattr(app_mod, 'DB', path)
    for name in ('CSS_MCP_ENABLED', drafts.FLAG):
        monkeypatch.setenv(name, '1')
    for name in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_NOTIFICATION_WRITES_ENABLED'):
        monkeypatch.delenv(name, raising=False)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('supply-test', json.dumps({'client_name': 'Supply test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'supply-test', users[2]['id'], [drafts.SCOPE], RESOURCE)
    conn.commit()
    with ExitStack() as stack:
        clients = []
        for user in users:
            client = stack.enter_context(TestClient(app_mod.app, raise_server_exceptions=False))
            client.cookies.set(auth.COOKIE_NAME, session_token(user))
            clients.append(client)
        yield conn, users, clients, app_mod, item, token


def fields(item):
    return {'purpose': 'Draft purpose <script>untrusted</script>', 'date_needed': '2026-11-02',
            'lines': [{'item_id': item, 'requested_quantity': 3}]}


def prepare(pilot, operation_id=KEY, data=None):
    conn, _, _, _, item, token = pilot
    return drafts.prepare(conn, token.access_token, RESOURCE, ORIGIN, operation_id, data or fields(item))


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1)
            for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


def test_exact_preview_confirm_and_replay_create_one_draft_only(pilot):
    conn, users, clients, app, item, token = pilot
    unchanged = {table: conn.execute('SELECT * FROM ' + table).fetchall() for table in
                 ('supply_stock_movement', 'supply_reservation', 'supply_request_revision', 'supply_sequence', 'supply_alert_event')}
    preview = prepare(pilot)
    assert prepare(pilot) == preview
    assert 'purpose' not in json.dumps(preview)
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
    path = '/account/integrations/mcp/supply-drafts/' + KEY
    page = clients[2].get(path)
    assert page.status_code == 200, page.text
    assert '&lt;script&gt;untrusted&lt;/script&gt;' in page.text
    assert '<script>untrusted</script>' not in page.text
    assert '2026-11-02' in page.text and 'TEST-PAPER' in page.text
    assert 'no-store' in page.headers['cache-control']
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
    response = clients[2].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert response.status_code == 200 and 'Supply request draft saved' in response.text, response.text
    receipt = drafts.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed'
    assert receipt['draft']['saved_status'] == 'draft'
    source = clients[2].get(receipt['web_url'])
    assert source.status_code == 200 and 'Draft purpose' in source.text
    assert clients[3].get(receipt['web_url']).status_code in (403, 404)
    assert prepare(pilot) == receipt
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    row = conn.execute('SELECT requester_id,approval_status,purpose,date_needed,control_number,current_revision FROM supply_request').fetchone()
    assert tuple(row) == (users[2]['id'], 'draft', fields(item)['purpose'], '2026-11-02', None, 0)
    assert conn.execute('SELECT COUNT(*) FROM supply_request_draft_line').fetchone()[0] == 1
    assert conn.execute('SELECT requested_quantity FROM supply_request_draft_line').fetchone()[0] == 3
    for table, before in unchanged.items():
        assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    assert conn.execute("SELECT COUNT(*) FROM supply_operation WHERE action='request_save'").fetchone()[0] == 1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_supply_draft_operation').fetchone() == (None, None)
    # Later UI edits do not cause a recovery/retry to recreate or overwrite it.
    conn.execute("UPDATE supply_request SET purpose='Changed later',revision=revision+1")
    conn.commit()
    assert prepare(pilot) == receipt
    assert conn.execute('SELECT purpose FROM supply_request').fetchone()[0] == 'Changed later'


@pytest.mark.parametrize('change', ['catalog', 'inactive', 'directory', 'unit', 'revoked', 'scope', 'expired', 'module', 'switch'])
def test_every_current_gate_is_rechecked_before_commit(pilot, monkeypatch, change):
    conn, users, clients, app, item, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/supply-drafts/' + KEY
    page = clients[2].get(path)
    assert page.status_code == 200
    if change == 'catalog':
        conn.execute("UPDATE supply_item SET unit='Box',revision=revision+1 WHERE id=?", (item,))
    elif change == 'inactive':
        conn.execute('UPDATE supply_item SET active=0 WHERE id=?', (item,))
    elif change == 'directory':
        conn.execute("UPDATE resource_person SET archived_at='2026-10-27' WHERE id=?", (users[2]['rp_id'],))
    elif change == 'unit':
        conn.execute("UPDATE org_unit SET name='Renamed unit' WHERE id=(SELECT org_unit_id FROM resource_person WHERE id=?)", (users[2]['rp_id'],))
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'scope':
        conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"supplies:read\"]'")
    elif change == 'expired':
        conn.execute('UPDATE mcp_supply_draft_operation SET expires_at=1')
    elif change == 'module':
        conn.execute("UPDATE app_setting SET value='0' WHERE key='supplies.enabled'")
    else:
        monkeypatch.setenv(drafts.FLAG, '0')
    conn.commit()
    response = clients[2].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert response.status_code in (404, 409), response.text
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM supply_operation WHERE action=?', ('request_save',)).fetchone()[0] == 0
    if change == 'expired':
        assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_supply_draft_operation').fetchone() == (None, None)


def test_other_account_grant_payload_csrf_and_origin_are_denied(pilot):
    conn, users, clients, app, item, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/supply-drafts/' + KEY
    page = clients[2].get(path)
    values = form(page)
    assert clients[3].get(path).status_code == 404
    for data, origin in (({**values, 'csrf': 'bad'}, ORIGIN), (values, 'https://evil.example'),
                         ({**values, 'confirm': 'no'}, ORIGIN)):
        assert clients[2].post(path, data=data, headers={'Origin': origin}).status_code == 403
    assert clients[2].post(path, data={**values, 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different draft'):
        prepare(pilot, data={**fields(item), 'purpose': 'Changed'})
    fresh = mcp_auth.Provider._tokens(conn, 'supply-test', users[2]['id'], [drafts.SCOPE], RESOURCE)
    conn.commit()
    with pytest.raises(permissions.Denied):
        drafts.recover(conn, fresh.access_token, RESOURCE, ORIGIN, KEY)
    read_token = mcp_auth.Provider._tokens(conn, 'supply-test', users[2]['id'], ['supplies:read', 'notifications:mark_read'], RESOURCE)
    conn.commit()
    with pytest.raises(mcp_actions.ActionError, match='explicitly allow'):
        drafts.prepare(conn, read_token.access_token, RESOURCE, ORIGIN, 'other-operation-001', fields(item))
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0


def test_default_off_and_revoked_browser_session_cannot_save(pilot, monkeypatch):
    conn, users, clients, app, item, token = pilot
    monkeypatch.delenv(drafts.FLAG)
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        prepare(pilot)
    assert conn.execute('SELECT COUNT(*) FROM mcp_supply_draft_operation').fetchone()[0] == 0
    monkeypatch.setenv(drafts.FLAG, '1')
    prepare(pilot)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = drafts.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    conn.execute('DELETE FROM login_session WHERE session_id=?', (payload['sid'],))
    conn.commit()
    with pytest.raises(permissions.Denied):
        drafts.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0


def test_atomic_audit_failure_and_two_browser_confirmations(pilot, monkeypatch):
    conn, users, clients, app, item, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = drafts.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    original = st.audit
    def failed(*args, **kwargs):
        if args[2] == 'integration_action_complete':
            raise RuntimeError('synthetic receipt audit failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(st, 'audit', failed)
    with pytest.raises(RuntimeError):
        drafts.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM supply_operation WHERE action='request_save'").fetchone()[0] == 0
    monkeypatch.setattr(st, 'audit', original)
    def confirm(_):
        c = app.get_conn()
        try:
            return drafts.browser(c, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, range(2)))
    assert results[0] == results[1]
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1


def test_mcp_dispatch_strict_lines_and_separate_scope(pilot, monkeypatch):
    conn, users, clients, app, item, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='supply-test', scopes=[drafts.SCOPE], resource=RESOURCE,
                          subject=str(users[2]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        args = {**fields(item), 'operation_id': KEY}
        result = await server.call_tool('prepare_supply_request_draft', args)
        assert 'awaiting_confirmation' in str(result)
        assert 'Draft purpose' not in str(result)
        for bad in ({'item_id': True, 'requested_quantity': 3}, {'item_id': item, 'requested_quantity': 0},
                    {'item_id': item, 'requested_quantity': 1, 'approved_quantity': 10}):
            with pytest.raises(Exception, match='validation error'):
                await server.call_tool('prepare_supply_request_draft', {**args, 'lines': [bad]})
        context.scopes = ['supplies:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_supply_request_draft', args)
    asyncio.run(journey())
    assert conn.execute('SELECT COUNT(*) FROM supply_request').fetchone()[0] == 0


def test_mobile_confirmation_without_scripts(pilot):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, item, token = pilot
    prepare(pilot)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            context, page = page_for(browser, clients[2], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/supply-drafts/' + KEY)
                expect(page.get_by_role('heading', name='Save this new supply request draft?', exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                page.get_by_role('button', name='Confirm: save my supply draft', exact=True).click()
                expect(page.get_by_role('heading', name='Supply request draft saved', exact=True)).to_be_visible()
            finally:
                context.close()
        finally:
            browser.close()
