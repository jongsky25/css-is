"""Private task drafts: preview, explicit save, source and manual compose review."""
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
import mcp_actions
import mcp_auth
import mcp_comment_drafts as pilot_service
import mcp_read
import storage as st
import work_comment_drafts as drafts
import work_tasks
import work_updates
from tests.test_integration_read_api import api
from tests.test_work import workspace, case

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'comment-draft-operation-001'
BODY = 'PRIVATE_DRAFT_TEXT\nReview </textarea><script>untrusted</script> before sharing.'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG):
        monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_SUPPLY_DRAFTS_ENABLED', 'CSS_MCP_NOTIFICATION_WRITES_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    item = case(conn, users[0], unit)
    task = work_tasks.create(conn, users[0], item['id'], {'title': 'Draft target', 'expected_output': 'A reviewed contribution'})
    work_updates.follow(conn, users[1], item['id'])
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('comment-test', json.dumps({'client_name': 'Comment test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'comment-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, item, task, token


def fields(pilot):
    return {'work_item_id': pilot[4]['id'], 'task_id': pilot[5]['id'], 'body': BODY}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[6].access_token, RESOURCE, ORIGIN, operation_id, data or fields(pilot))


def form(page):
    return {name: re.search(r'name="' + name + r'" value="([^"]+)"', page.text).group(1)
            for name in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


def state(conn):
    return {table: conn.execute('SELECT * FROM ' + table).fetchall() for table in
            ('work_case', 'work_task', 'work_comment', 'work_comment_revision', 'work_notice',
             'work_mention', 'work_comment_read', 'work_follow', 'work_event')}


def test_private_preview_save_receipt_source_and_prefill_do_not_publish(pilot):
    conn, users, clients, app, item, task, token = pilot
    before = state(conn)
    preview = prepare(pilot)
    assert prepare(pilot) == preview
    assert BODY not in json.dumps(preview)
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 0
    path = '/account/integrations/mcp/comment-drafts/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200, page.text
    assert 'PRIVATE_DRAFT_TEXT' in page.text and '&lt;script&gt;' in page.text
    assert '<script>untrusted</script>' not in page.text
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 0
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    receipt = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['draft_id']
    assert 'PRIVATE_DRAFT_TEXT' not in json.dumps(receipt)
    assert prepare(pilot) == receipt
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    source = clients[0].get(receipt['web_url'])
    assert source.status_code == 200 and 'PRIVATE_DRAFT_TEXT' in source.text
    assert 'no-store' in source.headers['cache-control']
    # A case officer and technical administrator cannot read another actor's draft.
    for client in (clients[1], clients[4]):
        assert client.get(receipt['web_url']).status_code == 404
    compose = clients[0].get(f"/work/{item['id']}/discussion", params={'task_id': task['id'], 'draft_id': receipt['draft_id']})
    assert compose.status_code == 200 and 'Your private draft is loaded' in compose.text
    assert 'PRIVATE_DRAFT_TEXT' in compose.text and 'no-store' in compose.headers['cache-control']
    foreign_compose = clients[1].get(f"/work/{item['id']}/discussion", params={'task_id': task['id'], 'draft_id': receipt['draft_id']})
    assert foreign_compose.status_code == 404 and 'PRIVATE_DRAFT_TEXT' not in foreign_compose.text
    assert state(conn) == before
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 1
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_comment_draft_operation').fetchone() == (None, None)
    audit = conn.execute('SELECT summary,before_text,after_text FROM audit_log').fetchall()
    assert 'PRIVATE_DRAFT_TEXT' not in str(audit)
    other_task = work_tasks.create(conn, users[0], item['id'], {'title': 'Another contribution', 'expected_output': 'Other output'})
    wrong_compose = clients[0].get(f"/work/{item['id']}/discussion", params={'task_id': other_task['id'], 'draft_id': receipt['draft_id']})
    assert wrong_compose.status_code == 404 and 'PRIVATE_DRAFT_TEXT' not in wrong_compose.text
    # A later target revision changes the review banner, never re-saves/posts.
    conn.execute('UPDATE work_task SET revision=revision+1 WHERE id=?', (task['id'],))
    conn.commit()
    assert prepare(pilot) == receipt
    assert 'changed since this draft' in clients[0].get(receipt['web_url']).text


@pytest.mark.parametrize('change', ['case', 'task', 'access', 'scope', 'revoked', 'expired', 'module', 'switch', 'payload', 'snapshot'])
def test_current_target_and_authority_are_checked_at_confirmation(pilot, monkeypatch, change):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/comment-drafts/' + KEY
    page = clients[0].get(path)
    if change == 'case':
        conn.execute('UPDATE work_case SET revision=revision+1 WHERE id=?', (item['id'],))
    elif change == 'task':
        conn.execute('UPDATE work_task SET revision=revision+1 WHERE id=?', (task['id'],))
    elif change == 'access':
        conn.execute('UPDATE work_case SET creator_id=? WHERE id=?', (users[2]['id'], item['id']))
    elif change == 'scope':
        conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"work:read\"]'")
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired':
        conn.execute('UPDATE mcp_comment_draft_operation SET expires_at=1')
    elif change == 'module':
        conn.execute("UPDATE app_setting SET value='0' WHERE key='work.enabled'")
    elif change == 'payload':
        conn.execute('UPDATE mcp_comment_draft_operation SET payload_json=?', (json.dumps({**fields(pilot), 'body': 'Changed stored text'}),))
    elif change == 'snapshot':
        conn.execute("UPDATE mcp_comment_draft_operation SET snapshot_json='{}'")
    else:
        monkeypatch.setenv(pilot_service.FLAG, '0')
    conn.commit()
    response = clients[0].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert response.status_code in (404, 409), response.text
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 0
    assert conn.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == 0
    if change == 'expired':
        assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_comment_draft_operation').fetchone() == (None, None)


def test_cross_account_payload_connection_csrf_and_wrong_target_denial(pilot):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/comment-drafts/' + KEY
    page = clients[0].get(path)
    for values, origin in (({**form(page), 'csrf': 'bad'}, ORIGIN), (form(page), 'https://evil.example'),
                           ({**form(page), 'confirm': 'no'}, ORIGIN)):
        assert clients[0].post(path, data=values, headers={'Origin': origin}).status_code == 403
    assert clients[0].post(path, data={**form(page), 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different draft'):
        prepare(pilot, data={**fields(pilot), 'body': 'Changed'})
    with pytest.raises(permissions.Denied):
        prepare(pilot, 'wrong-task-operation-001', {**fields(pilot), 'task_id': task['id'] + 999})
    fresh = mcp_auth.Provider._tokens(conn, 'comment-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    read_only = mcp_auth.Provider._tokens(conn, 'comment-test', users[0]['id'], ['work:read', 'supplies:request:draft'], RESOURCE)
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, fresh.access_token, RESOURCE, ORIGIN, KEY)
    with pytest.raises(mcp_actions.ActionError, match='explicitly allow'):
        pilot_service.prepare(conn, read_only.access_token, RESOURCE, ORIGIN, 'read-only-operation-001', fields(pilot))
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 0


def test_atomic_failure_concurrent_save_and_revoked_source_access(pilot, monkeypatch):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    original = st.audit
    def failed(*args, **kwargs):
        if args[2] == 'integration_action_complete':
            raise RuntimeError('synthetic receipt audit failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(st, 'audit', failed)
    with pytest.raises(RuntimeError):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 0
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
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1
    conn.execute('UPDATE work_case SET creator_id=? WHERE id=?', (users[2]['id'], item['id']))
    conn.commit()
    assert clients[0].get(results[0]['web_url']).status_code == 404
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


def test_default_off_session_and_restore_denial(pilot, monkeypatch):
    conn, users, clients, app, item, task, token = pilot
    monkeypatch.delenv(pilot_service.FLAG)
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        prepare(pilot)
    monkeypatch.setenv(pilot_service.FLAG, '1')
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?', (payload['sid'],))
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    backups.clear_restored_sessions(app.DB, revoke_integrations=True)
    with pytest.raises(mcp_actions.ActionError):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


def test_actual_dispatch_validates_ids_text_and_never_returns_body(pilot, monkeypatch):
    conn, users, clients, app, item, task, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='comment-test', scopes=[pilot_service.SCOPE],
                          resource=RESOURCE, subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        args = {**fields(pilot), 'operation_id': KEY}
        result = await server.call_tool('prepare_task_comment_draft', args)
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_DRAFT_TEXT' not in str(result)
        for changed in ({'task_id': True}, {'task_id': -1}, {'body': 'x'*4001}, {'body': '\x00hidden'}):
            with pytest.raises(Exception):
                await server.call_tool('prepare_task_comment_draft', {**args, **changed})
        context.scopes = ['work:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_task_comment_draft', args)
    asyncio.run(journey())
    assert conn.execute('SELECT COUNT(*) FROM work_comment_draft').fetchone()[0] == 0


def test_mobile_no_script_save_prefill_and_separate_manual_post(pilot):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            context, page = page_for(browser, clients[0], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/comment-drafts/' + KEY)
                expect(page.get_by_label('Exact draft text')).to_have_value(BODY)
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                page.get_by_role('button', name='Confirm: save my private draft', exact=True).click()
                expect(page.get_by_role('heading', name='Private task comment draft saved', exact=True)).to_be_visible()
                page.get_by_role('link', name='Open my private draft', exact=True).click()
                page.get_by_role('link', name='Load into the discussion form for review', exact=True).click()
                expect(page.get_by_label('Your message', exact=True)).to_have_value(BODY)
                assert conn.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == 0
                assert conn.execute('SELECT COUNT(*) FROM work_notice').fetchone()[0] == 0
                # Existing UI action only: the person explicitly chooses to publish.
                page.get_by_role('button', name='Post message', exact=True).click()
                assert conn.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == 1
                assert conn.execute('SELECT COUNT(*) FROM work_notice').fetchone()[0] == 1
            finally:
                context.close()
        finally:
            browser.close()
