"""Supply submission previews bind exact lines, current identity and approval routing."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import json
import re
import time

import pytest
from mcp.server.auth.provider import AccessToken
from starlette.testclient import TestClient

import auth
import documents_permissions as permissions
import mcp_actions
import mcp_auth
import mcp_read
import mcp_supply_submissions as pilot_service
import storage as st
import supplies
import supplies_requests as requests
import supplies_approvals as approvals
import supplies_storage as domain
from tests.conftest import session_token
from tests.test_supplies import supplies_db, setup_catalog, create, key
from tests.test_supplies_requests import request_db

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'supply-submission-operation-001'
PURPOSE = 'PRIVATE_PURPOSE <script>untrusted</script>'


@pytest.fixture
def pilot(request_db, app_mod, monkeypatch):
    conn, users, units, path, item = request_db
    monkeypatch.setattr(app_mod, 'DB', path)
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG):
        monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_SUPPLY_DRAFTS_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    saved = requests.save_draft(conn, users[2], {'purpose': PURPOSE, 'date_needed': '2026-11-02',
        'lines': [{'item_id': item, 'requested_quantity': 3}]}, operation_key=key())
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('supply-submit-test', json.dumps({'client_name': 'Supply submission test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'supply-submit-test', users[2]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    with ExitStack() as stack:
        clients = []
        for user in users:
            client = stack.enter_context(TestClient(app_mod.app, raise_server_exceptions=False))
            client.cookies.set(auth.COOKIE_NAME, session_token(user))
            clients.append(client)
        yield conn, users, clients, app_mod, item, saved, token


def fields(pilot, **changes):
    return {'request_id': pilot[5]['id'], 'revision': pilot[5]['revision'], **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[6].access_token, RESOURCE, ORIGIN, operation_id, data or fields(pilot))


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1)
            for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


def submitted_count(conn):
    return conn.execute("SELECT COUNT(*) FROM supply_operation WHERE action='request_submit'").fetchone()[0]


def test_exact_submission_source_domain_replay_and_no_stock_effects(pilot):
    conn, users, clients, app, item, draft, token = pilot
    unchanged = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in
        ('supply_stock_movement', 'supply_reservation', 'supply_request_decision', 'supply_issue', 'supply_alert_event')}
    preview = prepare(pilot)
    assert prepare(pilot) == preview and PURPOSE not in json.dumps(preview)
    assert not conn.execute('SELECT * FROM supply_sequence').fetchall() and submitted_count(conn) == 0
    path = '/account/integrations/mcp/supply-submissions/' + KEY
    page = clients[2].get(path)
    assert page.status_code == 200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert 'TEST-PAPER' in page.text and '3 Ream' in page.text and '2026-11-02' in page.text
    assert 'No eligible approver is configured' in page.text and 'no-store' in page.headers['cache-control']
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    receipt = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['submitted']['approval_status'] == 'submitted'
    assert receipt['submitted']['control_number'] == 'SUP-2026-00001'
    assert receipt['submitted']['revision'] == 2 and receipt['submitted']['current_revision'] == 1
    assert receipt['next_actor']['role'] == 'supply_request_approver' and receipt['next_actor']['routing_warning']
    assert 'PRIVATE_PURPOSE' not in json.dumps(receipt) and 'TEST-PAPER' not in json.dumps(receipt)
    assert prepare(pilot) == receipt
    assert requests.submit(conn, users[2], draft['id'], expected_revision=1,
                           operation_key=receipt['domain_operation_id']) == receipt['submitted']
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    assert submitted_count(conn) == 1
    snapshot = conn.execute('SELECT purpose,date_needed,unit_id FROM supply_request_revision').fetchone()
    assert snapshot == (PURPOSE, '2026-11-02', int(receipt['next_actor']['unit_id']))
    assert conn.execute('SELECT requested_quantity FROM supply_request_revision_line').fetchone()[0] == 3
    source = clients[2].get(receipt['web_url'])
    assert source.status_code == 200 and 'SUP-2026-00001' in source.text
    assert clients[3].get(receipt['web_url']).status_code in (403, 404)
    for table, before in unchanged.items():
        assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_supply_submission').fetchone() == (None, None)
    # A later ordinary return/edit cannot be overwritten by original recovery.
    supplies.grant_role(conn, users[0], users[3]['id'], 'request_approver', snapshot[2], operation_key=key())
    approvals.decide_request(conn, users[3], draft['id'], {'decision': 'returned', 'reason': 'Clarify need'},
        expected_revision=2, submitted_revision=1, operation_key=key())
    assert prepare(pilot) == receipt
    assert requests._owned(conn, users[2], draft['id'])['approval_status'] == 'returned'


@pytest.mark.parametrize('change', ['scope', 'revoked', 'expired', 'switch', 'payload', 'snapshot', 'module',
    'request', 'quantity', 'catalog', 'inactive', 'directory', 'unit', 'routing'])
def test_pending_rechecks_all_bound_fields_and_authority(pilot, monkeypatch, change):
    conn, users, clients, app, item, draft, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/supply-submissions/' + KEY
    page = clients[2].get(path)
    if change == 'scope': conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"supplies:read\"]'")
    elif change == 'revoked': conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired': conn.execute('UPDATE mcp_supply_submission SET expires_at=1')
    elif change == 'switch': monkeypatch.setenv(pilot_service.FLAG, '0')
    elif change == 'payload': conn.execute('UPDATE mcp_supply_submission SET payload_json=?', (json.dumps(fields(pilot, revision=2)),))
    elif change == 'snapshot': conn.execute('UPDATE mcp_supply_submission SET snapshot_json=NULL')
    elif change == 'module': st.set_setting(conn, 'supplies.enabled', '0')
    elif change == 'request': conn.execute("UPDATE supply_request SET purpose='Changed without revision'")
    elif change == 'quantity': conn.execute('UPDATE supply_request_draft_line SET requested_quantity=7')
    elif change == 'catalog': conn.execute("UPDATE supply_item SET description='Changed catalog',revision=revision+1 WHERE id=?", (item,))
    elif change == 'inactive': conn.execute('UPDATE supply_item SET active=0 WHERE id=?', (item,))
    elif change == 'directory': conn.execute("UPDATE resource_person SET archived_at='2026-10-27' WHERE id=?", (users[2]['rp_id'],))
    elif change == 'unit': conn.execute("UPDATE org_unit SET name='Changed unit' WHERE id=?", (requests.requester(conn, users[2])[1]['unit_id'],))
    else:
        supplies.grant_role(conn, users[0], users[3]['id'], 'request_approver',
                            requests.requester(conn, users[2])[1]['unit_id'], operation_key=key())
    conn.commit()
    response = clients[2].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert response.status_code in (404, 409), response.text
    assert submitted_count(conn) == 0 and not conn.execute('SELECT * FROM supply_sequence').fetchall()
    if change == 'expired':
        assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_supply_submission').fetchone() == (None, None)


@pytest.mark.parametrize('changed', [{'request_id': True}, {'request_id': 0}, {'request_id': 2**31},
    {'revision': True}, {'revision': 0}, {'purpose': 'No edits'}, {'lines': []}, {'approval_status': 'approved'}])
def test_invalid_fields_cannot_prepare(pilot, changed):
    with pytest.raises(ValueError): prepare(pilot, data=fields(pilot, **changed))
    assert submitted_count(pilot[0]) == 0


def test_scope_owner_session_origin_csrf_and_connection_boundaries(pilot):
    conn, users, clients, app, item, draft, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/supply-submissions/' + KEY
    page = clients[2].get(path)
    assert clients[3].get(path).status_code == 404
    for user in (users[0], users[1], users[3]):
        other = mcp_auth.Provider._tokens(conn, 'supply-submit-test', user['id'], [pilot_service.SCOPE], RESOURCE)
        conn.commit()
        with pytest.raises(domain.Denied):
            pilot_service.prepare(conn, other.access_token, RESOURCE, ORIGIN, KEY, fields(pilot))
    read_only = mcp_auth.Provider._tokens(conn, 'supply-submit-test', users[2]['id'], ['supplies:read', 'supplies:request:draft'], RESOURCE)
    fresh = mcp_auth.Provider._tokens(conn, 'supply-submit-test', users[2]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    with pytest.raises(mcp_actions.ActionError):
        pilot_service.prepare(conn, read_only.access_token, RESOURCE, ORIGIN, 'read-only-operation-001', fields(pilot))
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, fresh.access_token, RESOURCE, ORIGIN, KEY)
    for values, origin in (({**form(page), 'csrf': 'bad'}, ORIGIN), (form(page), 'https://evil.example'),
                           ({**form(page), 'confirm': 'no'}, ORIGIN)):
        assert clients[2].post(path, data=values, headers={'Origin': origin}).status_code == 403
    assert clients[2].post(path, data={**form(page), 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different supply submission'):
        prepare(pilot, data=fields(pilot, revision=2))
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?', (payload['sid'],)); conn.commit()
    with pytest.raises(permissions.Denied): pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)


def test_atomic_rollback_then_two_confirmations_create_one_number(pilot, monkeypatch):
    conn, users, clients, app, item, draft, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    original = st.audit
    def fail(*args, **kwargs):
        if args[2] == 'integration_action_complete': raise RuntimeError('Synthetic final audit failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(st, 'audit', fail)
    with pytest.raises(RuntimeError):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert submitted_count(conn) == 0 and not conn.execute('SELECT * FROM supply_sequence').fetchall()
    assert not conn.execute('SELECT * FROM supply_request_revision').fetchall()
    monkeypatch.setattr(st, 'audit', original)
    def confirm(_):
        c = app.get_conn()
        try: return pilot_service.browser(c, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
        finally: c.close()
    with ThreadPoolExecutor(max_workers=2) as executor: results = list(executor.map(confirm, range(2)))
    assert results[0] == results[1] and submitted_count(conn) == 1
    assert conn.execute("SELECT last_value FROM supply_sequence WHERE kind='SUP'").fetchone()[0] == 1


def test_actual_dispatch_and_mobile_no_javascript_review(pilot, monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, item, draft, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='supply-submit-test', scopes=[pilot_service.SCOPE], resource=RESOURCE,
                          subject=str(users[2]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        result = await server.call_tool('prepare_supply_request_submission', {**fields(pilot), 'operation_id': KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_PURPOSE' not in str(result)
        context.scopes = ['supplies:request:draft']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_supply_request_submission', {**fields(pilot), 'operation_id': KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            bc, page = page_for(browser, clients[2], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/supply-submissions/' + KEY)
                expect(page.get_by_role('heading', name='Submit this supply request for approval?', exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                assert submitted_count(conn) == 0
                page.get_by_role('button', name='Confirm: submit my supply request', exact=True).click()
                page.get_by_role('link', name='Open my submitted supply request', exact=True).click()
                expect(page.get_by_text('SUP-2026-00001', exact=True).first).to_be_visible()
            finally: bc.close()
        finally: browser.close()


def test_returned_request_resubmits_new_snapshot_without_new_number(pilot):
    conn, users, clients, app, item, draft, token = pilot
    unit_id = requests.requester(conn, users[2])[1]['unit_id']
    supplies.grant_role(conn, users[0], users[3]['id'], 'request_approver', unit_id, operation_key=key())
    first = requests.submit(conn, users[2], draft['id'], expected_revision=1, operation_key=key())
    approvals.decide_request(conn, users[3], draft['id'], {'decision': 'returned', 'reason': 'Clarify quantities'},
                            expected_revision=2, submitted_revision=1, operation_key=key())
    returned = requests._owned(conn, users[2], draft['id'])
    edited = requests.save_draft(conn, users[2], {'purpose': 'Revised need', 'date_needed': '2026-11-03',
        'lines': [{'item_id': item, 'requested_quantity': 4}]}, request_id=draft['id'],
        expected_revision=returned['revision'], operation_key=key())
    prepare(pilot, data=fields(pilot, revision=edited['revision']))
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    assert preview['snapshot']['status'] == 'returned' and preview['snapshot']['control_number'] == first['control_number']
    assert preview['snapshot']['next_actor']['eligible_approver_count'] == 1
    result = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert result['submitted']['current_revision'] == 2 and result['submitted']['control_number'] == first['control_number']
    assert result['next_actor'] == {'role': 'supply_request_approver', 'unit_id': str(unit_id),
                                    'eligible_approver_count': 1, 'routing_warning': False}
    assert conn.execute("SELECT last_value FROM supply_sequence WHERE kind='SUP'").fetchone()[0] == 1
    assert conn.execute('SELECT purpose FROM supply_request_revision ORDER BY revision').fetchall() == [(PURPOSE,), ('Revised need',)]
    assert any(r['id'] == draft['id'] for r in approvals.inbox(conn, users[3])['requests'])


def test_two_independent_previews_against_one_revision_commit_once(pilot):
    conn, users, clients, app, item, draft, token = pilot
    prepare(pilot)
    prepare(pilot, 'other-supply-submission-001')
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    previews = [pilot_service.browser(conn, payload, RESOURCE, ORIGIN, k) for k in (KEY, 'other-supply-submission-001')]
    def confirm(preview):
        c = app.get_conn()
        try:
            return pilot_service.browser(c, payload, RESOURCE, ORIGIN, preview['operation_id'], confirm_digest=preview['preview_digest'])['status']
        except domain.Conflict:
            return 'conflict'
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as executor: results = list(executor.map(confirm, previews))
    assert sorted(results) == ['completed', 'conflict']
    assert submitted_count(conn) == 1
    assert conn.execute('SELECT COUNT(*) FROM supply_request_revision').fetchone()[0] == 1
    assert conn.execute("SELECT last_value FROM supply_sequence WHERE kind='SUP'").fetchone()[0] == 1


def test_number_capacity_failure_leaves_no_partial_submission(pilot):
    import tzutil as tz
    conn, users, clients, app, item, draft, token = pilot
    prepare(pilot)
    conn.execute("INSERT INTO supply_sequence VALUES ('SUP',?,99999)", (tz.today_local().year,)); conn.commit()
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    with pytest.raises(domain.Conflict):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert submitted_count(conn) == 0 and not conn.execute('SELECT * FROM supply_request_revision').fetchall()
    assert requests._owned(conn, users[2], draft['id'])['approval_status'] == 'draft'
