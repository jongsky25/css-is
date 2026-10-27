"""M2 owner-only preview -> browser confirmation -> durable MCP recovery."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import re
import time

import pytest
from mcp.server.auth.provider import AccessToken

import auth
import backups
import documents_permissions as permissions
import mcp_actions as actions
import mcp_auth
import mcp_read
import storage as st
import work_updates
from tests.conftest import session_token
from tests.test_integration_read_api import api
from tests.test_work import workspace, case

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'notice-test-operation-0001'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for name in ('CSS_MCP_ENABLED', 'CSS_MCP_NOTIFICATIONS_ENABLED', actions.FLAG):
        monkeypatch.setenv(name, '1')
    monkeypatch.delenv('CSS_BASE_URL', raising=False)
    monkeypatch.delenv('SPACE_HOST', raising=False)
    item = case(conn, users[0], unit)
    comment = conn.execute('INSERT INTO work_comment(case_id,author_id,created_at) VALUES (?,?,?)',
                           (item['id'], users[1]['id'], '2026-10-27')).lastrowid
    conn.execute('INSERT INTO work_comment_revision VALUES (?,1,?,?)', (comment, 'PRIVATE MESSAGE TEXT', '2026-10-27'))
    notice = conn.execute("INSERT INTO work_notice(comment_id,user_id,revision,reason,created_at) VALUES (?,?,1,'mention',?)",
                          (comment, users[0]['id'], '2026-10-27')).lastrowid
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('write-test', json.dumps({'client_name': 'Write test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'write-test', users[0]['id'], ['notifications:read', actions.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, item, comment, notice, token


def prepare(pilot, key=KEY):
    conn, _, _, _, _, _, notice, token = pilot
    return actions.prepare(conn, token.access_token, RESOURCE, ORIGIN, notice, key)


def form(page):
    return {key: re.search(r'name="' + key + r'" value="([^"]+)"', page.text).group(1)
            for key in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


def test_browser_confirmation_and_lost_response_recovery(pilot):
    conn, users, clients, app, item, comment, notice, token = pilot
    preview = prepare(pilot)
    assert preview['status'] == 'awaiting_confirmation'
    assert conn.execute('SELECT COUNT(*) FROM work_comment_read').fetchone()[0] == 0
    assert prepare(pilot) == preview
    path = '/account/integrations/mcp/actions/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200, page.text
    assert 'PRIVATE MESSAGE TEXT' not in page.text
    assert 'no-store' in page.headers['cache-control']
    assert conn.execute('SELECT COUNT(*) FROM work_comment_read').fetchone()[0] == 0
    confirmed = clients[0].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert confirmed.status_code == 200, confirmed.text
    assert 'Work notice marked read' in confirmed.text
    assert work_updates.read_revision(conn, users[0]['id'], comment) == 1
    assert work_updates.inbox(conn, users[0])[0] == []
    receipt = actions.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['completed_at']
    assert prepare(pilot) == receipt
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1
    # A subsequent edit remains unread even after receipt recovery/replay.
    conn.execute('INSERT INTO work_comment_revision VALUES (?,2,?,?)', (comment, 'New text', '2026-10-27'))
    conn.execute('UPDATE work_notice SET revision=2 WHERE id=?', (notice,))
    conn.commit()
    assert prepare(pilot)['status'] == 'completed'
    assert work_updates.read_revision(conn, users[0]['id'], comment) == 1
    assert len(work_updates.inbox(conn, users[0])[0]) == 1


@pytest.mark.parametrize('change,code', [('edit', 'revision_conflict'), ('read', 'revision_conflict'),
                                      ('expired', 'preview_expired'), ('switch', 'not_available'),
                                      ('revoked', 'authorization_required'), ('scope', 'authorization_required')])
def test_confirmation_rechecks_every_gate(pilot, monkeypatch, change, code):
    conn, users, clients, app, item, comment, notice, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/actions/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200
    if change == 'edit':
        conn.execute('INSERT INTO work_comment_revision VALUES (?,2,?,?)', (comment, 'Changed', '2026-10-27'))
    elif change == 'read':
        conn.execute('INSERT INTO work_comment_read VALUES (?,?,1)', (comment, users[0]['id']))
    elif change == 'expired':
        conn.execute('UPDATE mcp_action_operation SET expires_at=1')
    elif change == 'switch':
        monkeypatch.setenv(actions.FLAG, '0')
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'scope':
        conn.execute('UPDATE mcp_oauth_grant SET scopes_json=?', ('["notifications:read"]',))
    conn.commit()
    response = clients[0].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert response.status_code == 409, response.text
    assert conn.execute('SELECT completed_at FROM mcp_action_operation').fetchone()[0] is None
    if change != 'read':
        assert work_updates.read_revision(conn, users[0]['id'], comment) == 0
    with pytest.raises(actions.ActionError) as err:
        actions.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert err.value.code == code


def test_owner_source_access_csrf_digest_and_connection_boundaries(pilot):
    conn, users, clients, app, item, comment, notice, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/actions/' + KEY
    page = clients[0].get(path)
    values = form(page)
    assert clients[1].get(path).status_code == 404
    assert clients[1].post(path, data=values, headers={'Origin': ORIGIN}).status_code == 403
    assert clients[0].post(path, data=values, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert clients[0].post(path, data={**values, 'csrf': 'wrong'}, headers={'Origin': ORIGIN}).status_code == 403
    assert clients[0].post(path, data={**values, 'preview_digest': 'wrong'}, headers={'Origin': ORIGIN}).status_code == 409
    assert clients[0].post(path, data={**values, 'confirm': 'no'}, headers={'Origin': ORIGIN}).status_code == 403
    fresh = mcp_auth.Provider._tokens(conn, 'write-test', users[0]['id'], [actions.SCOPE], RESOURCE)
    conn.commit()
    with pytest.raises(permissions.Denied):
        actions.recover(conn, fresh.access_token, RESOURCE, ORIGIN, KEY)
    with pytest.raises(actions.ActionError, match='another request or connection'):
        actions.prepare(conn, fresh.access_token, RESOURCE, ORIGIN, notice, KEY)
    with pytest.raises(actions.ActionError, match='another request or connection'):
        actions.prepare(conn, token.access_token, RESOURCE, ORIGIN, notice + 1, KEY)
    # Losing record authority blocks both confirmation and receipt inspection.
    conn.execute('UPDATE work_case SET creator_id=? WHERE id=?', (users[2]['id'], item['id']))
    conn.commit()
    assert clients[0].post(path, data=values, headers={'Origin': ORIGIN}).status_code == 404
    assert work_updates.read_revision(conn, users[0]['id'], comment) == 0


def test_read_grant_cannot_prepare_and_switch_defaults_off(pilot, monkeypatch):
    conn, users, clients, app, item, comment, notice, token = pilot
    read_token = mcp_auth.Provider._tokens(conn, 'write-test', users[0]['id'], ['notifications:read'], RESOURCE)
    conn.commit()
    with pytest.raises(actions.ActionError, match='explicitly allow'):
        actions.prepare(conn, read_token.access_token, RESOURCE, ORIGIN, notice, KEY)
    monkeypatch.delenv(actions.FLAG)
    with pytest.raises(actions.ActionError, match='disabled'):
        prepare(pilot)
    assert conn.execute('SELECT COUNT(*) FROM mcp_action_operation').fetchone()[0] == 0


def test_account_session_and_restore_revoke_prepared_actions(pilot):
    conn, users, clients, app, item, comment, notice, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?', (payload['sid'],))
    conn.commit()
    with pytest.raises(permissions.Denied):
        actions.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    backups.clear_restored_sessions(app.DB, revoke_integrations=True)
    with pytest.raises(actions.ActionError):
        actions.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert work_updates.read_revision(conn, users[0]['id'], comment) == 0


def test_token_rotation_preserves_open_preview_and_original_revocation_link(pilot):
    from mcp.shared.auth import OAuthClientInformationFull

    conn, users, clients, app, item, comment, notice, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview = actions.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    grant_id = conn.execute('SELECT grant_id FROM mcp_action_operation').fetchone()[0]
    provider = mcp_auth.Provider(app.get_conn, ORIGIN)
    client = OAuthClientInformationFull(client_id='write-test', token_endpoint_auth_method='none',
        redirect_uris=['https://chatgpt.com/connector_platform_oauth_redirect'])
    async def rotate():
        refresh = await provider.load_refresh_token(client, token.refresh_token)
        rotated = await provider.exchange_refresh_token(client, refresh, None)
        assert await provider.load_refresh_token(client, token.refresh_token) is None
        assert await provider.load_access_token(token.access_token) is None
        assert await provider.load_access_token(rotated.access_token)
        return rotated
    rotated = asyncio.run(rotate())
    assert conn.execute('SELECT id FROM mcp_oauth_grant WHERE access_hash=?',
                        (mcp_auth._digest(rotated.access_token),)).fetchone()[0] == grant_id
    # A page already open before refresh still confirms the same operation.
    assert actions.browser(conn, payload, RESOURCE, ORIGIN, KEY,
                           confirm_digest=preview['preview_digest'])['status'] == 'completed'
    assert actions.recover(conn, rotated.access_token, RESOURCE, ORIGIN, KEY)['status'] == 'completed'
    mcp_auth.revoke_owner_grant(conn, users[0]['id'], grant_id)
    with pytest.raises(actions.ActionError):
        actions.recover(conn, rotated.access_token, RESOURCE, ORIGIN, KEY)


def test_confirmation_is_atomic_with_audit_and_two_client_replays(pilot, monkeypatch):
    conn, users, clients, app, item, comment, notice, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview = actions.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    original = st.audit
    def failed_audit(*args, **kwargs):
        raise RuntimeError('synthetic audit failure')
    monkeypatch.setattr(st, 'audit', failed_audit)
    with pytest.raises(RuntimeError):
        actions.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert work_updates.read_revision(conn, users[0]['id'], comment) == 0
    assert conn.execute('SELECT completed_at FROM mcp_action_operation').fetchone()[0] is None
    monkeypatch.setattr(st, 'audit', original)
    def confirm():
        c = app.get_conn()
        try:
            return actions.browser(c, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        receipts = list(executor.map(lambda _: confirm(), range(2)))
    assert receipts[0] == receipts[1]
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1


def test_actual_mcp_dispatch_requires_scope_and_returns_preview_only(pilot, monkeypatch):
    conn, users, clients, app, item, comment, notice, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='write-test', scopes=['notifications:read', actions.SCOPE],
                          resource=RESOURCE, subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        tools = {t.name: t for t in await server.list_tools()}
        assert tools['mark_my_notification_read'].annotations.readOnlyHint is False
        assert tools['get_mcp_operation'].annotations.readOnlyHint is True
        args = {'notification_id': notice, 'operation_id': KEY}
        result = await server.call_tool('mark_my_notification_read', args)
        assert 'awaiting_confirmation' in str(result)
        assert 'PRIVATE MESSAGE TEXT' not in str(result)
        with pytest.raises(Exception, match='validation error'):
            await server.call_tool('mark_my_notification_read', {**args, 'notification_id': True})
        context.scopes = ['notifications:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('mark_my_notification_read', args)
    asyncio.run(journey())
    assert conn.execute('SELECT COUNT(*) FROM work_comment_read').fetchone()[0] == 0


def test_write_permission_never_enters_default_oauth_request(pilot):
    conn, users, clients, app, item, comment, notice, token = pilot
    from mcp.server.auth.provider import AuthorizationParams
    provider = mcp_auth.Provider(app.get_conn, ORIGIN)
    async def check():
        client = await provider.get_client('write-test')
        params = AuthorizationParams(redirect_uri='https://chatgpt.com/connector_platform_oauth_redirect',
            redirect_uri_provided_explicitly=True, code_challenge='x'*43, scopes=None, state='state', resource=RESOURCE)
        url = await provider.authorize(client, params)
        ticket = url.split('ticket=')[1]
        _, pending = provider.pending(ticket)
        assert set(pending['scopes']) == mcp_auth.READ_SCOPES
        assert actions.SCOPE not in pending['scopes']
        assert actions.SCOPE in provider.consent_scopes('write-test')
    # get_client expects valid registered client metadata.
    conn.execute('UPDATE mcp_oauth_client SET metadata_json=?', (json.dumps({
        'client_id': 'write-test', 'client_name': 'Write test',
        'redirect_uris': ['https://chatgpt.com/connector_platform_oauth_redirect'],
        'token_endpoint_auth_method': 'none'}),))
    conn.commit()
    asyncio.run(check())


def test_mobile_browser_can_confirm_without_javascript(pilot):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil

    conn, users, clients, app, item, comment, notice, token = pilot
    prepare(pilot)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which('chromium') or None,
                                             args=['--no-sandbox'])
        try:
            context, page = page_for(browser, clients[0], viewport={'width': 320, 'height': 844},
                                     java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/actions/' + KEY)
                expect(page.get_by_role('heading', name='Mark this work notice read?', exact=True)).to_be_visible()
                assert work_updates.read_revision(conn, users[0]['id'], comment) == 0
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                page.get_by_role('button', name='Confirm: mark this notice read', exact=True).click()
                expect(page.get_by_role('heading', name='Work notice marked read', exact=True)).to_be_visible()
                assert work_updates.read_revision(conn, users[0]['id'], comment) == 1
            finally:
                context.close()
        finally:
            browser.close()
