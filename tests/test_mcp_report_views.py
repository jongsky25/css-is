"""Personal report selections save metadata only, with explicit confirmation."""
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
import mcp_report_views as pilot_service
import report_views as views
import storage as st
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'report-view-operation-001'
NAME = 'PRIVATE_VIEW <script>untrusted</script>'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG):
        monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_COMMENT_DRAFTS_ENABLED', 'CSS_MCP_SUPPLY_DRAFTS_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('report-test', json.dumps({'client_name': 'Report test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'report-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, token


def fields(**changes):
    return {'name': NAME, 'report_type': 'csm_month', 'year': 2024, 'month': 2, **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[4].access_token, RESOURCE, ORIGIN, operation_id, data or fields())


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1)
            for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


def test_exact_selection_save_source_and_replay_do_not_load_or_change_results(pilot, monkeypatch):
    conn, users, clients, app, token = pilot
    unchanged = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in ('response', 'answer', 'form_instance', 'work_case', 'work_task', 'supply_request')}
    original = app.get_atoms
    def no_report_reads(*args, **kwargs):
        raise AssertionError('Saving or viewing a selection must not load survey data')
    monkeypatch.setattr(app, 'get_atoms', no_report_reads)
    preview = prepare(pilot)
    assert prepare(pilot) == preview and NAME not in json.dumps(preview)
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 0
    path = '/account/integrations/mcp/report-views/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200 and '&lt;script&gt;' in page.text
    assert '<script>untrusted</script>' not in page.text
    assert 'date_to=2024-02-29' in page.text
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 0
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    receipt = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['view_id']
    assert prepare(pilot) == receipt
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 1
    saved = views.get(conn, users[0], int(receipt['view_id']))
    assert saved['selection'] == fields()
    assert parse_qs(urlsplit(saved['report_url']).query) == {'type': ['1'], 'date_from': ['2024-02-01'], 'date_to': ['2024-02-29']}
    source = clients[0].get(receipt['web_url'])
    assert source.status_code == 200 and '&lt;script&gt;' in source.text
    assert 'no-store' in source.headers['cache-control']
    assert 'PRIVATE_VIEW' in clients[0].get('/reports/saved').text
    for client in (clients[1], clients[4]):
        assert client.get(receipt['web_url']).status_code == 404
        assert 'PRIVATE_VIEW' not in client.get('/reports/saved').text
    for table, before in unchanged.items():
        assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    assert conn.execute('SELECT payload_json FROM mcp_report_view_operation').fetchone()[0] is None
    assert 'PRIVATE_VIEW' not in str(conn.execute('SELECT summary,before_text,after_text FROM audit_log').fetchall())
    monkeypatch.setattr(app, 'get_atoms', original)
    report = clients[0].get(saved['report_url'])
    assert report.status_code == 200, report.text[:200]
    assert '/reports/saved' in report.text
    # Turning off the MCP pilot leaves normal owner preferences available.
    monkeypatch.delenv(pilot_service.FLAG)
    assert clients[0].get(receipt['web_url']).status_code == 200
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


@pytest.mark.parametrize('data,query', [
    ({'name': 'CSM September', 'report_type': 'csm_month', 'year': 2026, 'month': 9},
     {'type': ['1'], 'date_from': ['2026-09-01'], 'date_to': ['2026-09-30']}),
    ({'name': 'Quarter one', 'report_type': 'activity_quarter', 'year': 2026, 'quarter': 1},
     {'type': ['2'], 'period': ['quarter:2026-Q1']}),
])
def test_canonical_source_links(data, query):
    link = urlsplit(views.report_path(data))
    assert not link.netloc and link.path == '/reports'
    assert parse_qs(link.query) == query


@pytest.mark.parametrize('changed', [
    {'name': ''}, {'name': '  '}, {'name': 'x'*61}, {'name': 'two\nlines'}, {'name': 'hidden\x00'},
    {'report_type': 'resource_person'}, {'year': True}, {'year': 1899}, {'year': 9999},
    {'month': 0}, {'month': 13}, {'quarter': 1}, {'month': None}, {'url': 'https://evil.example'}, {'org': 'OTHER'},
])
def test_invalid_or_extra_selections_never_become_views(pilot, changed):
    with pytest.raises(ValueError):
        prepare(pilot, data=fields(**changed))
    assert pilot[0].execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 0
    assert pilot[0].execute('SELECT COUNT(*) FROM mcp_report_view_operation').fetchone()[0] == 0


def test_name_race_and_ten_view_limit_are_rechecked(pilot):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    prepare(pilot, 'second-report-operation-001')
    first_path = '/account/integrations/mcp/report-views/' + KEY
    second_path = '/account/integrations/mcp/report-views/second-report-operation-001'
    first, second = clients[0].get(first_path), clients[0].get(second_path)
    assert clients[0].post(first_path, data=form(first), headers={'Origin': ORIGIN}).status_code == 200
    assert clients[0].post(second_path, data=form(second), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 1
    with pytest.raises(docs.Conflict):
        prepare(pilot, 'case-insensitive-name-001', fields(name=NAME.upper()))
    prepare(pilot, 'capacity-report-operation-001', fields(name='Final view'))
    capacity_path = '/account/integrations/mcp/report-views/capacity-report-operation-001'
    capacity_page = clients[0].get(capacity_path)
    with transaction(conn):
        for i in range(9):
            views.save_in_transaction(conn, users[0], fields(name=f'Other view {i}'), operation_key=str(uuid4()))
    assert clients[0].post(capacity_path, data=form(capacity_page), headers={'Origin': ORIGIN}).status_code == 409
    assert len(views.listing(conn, users[0])) == 10
    assert prepare(pilot)['status'] == 'completed'


@pytest.mark.parametrize('change', ['scope', 'revoked', 'expired', 'switch', 'payload'])
def test_current_gates_and_preview_digest(pilot, monkeypatch, change):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/report-views/' + KEY
    page = clients[0].get(path)
    if change == 'scope':
        conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"work:read\"]'")
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired':
        conn.execute('UPDATE mcp_report_view_operation SET expires_at=1')
    elif change == 'switch':
        monkeypatch.setenv(pilot_service.FLAG, '0')
    else:
        conn.execute('UPDATE mcp_report_view_operation SET payload_json=?', (json.dumps(fields(month=3)),))
    conn.commit()
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 0
    if change == 'expired':
        assert conn.execute('SELECT payload_json FROM mcp_report_view_operation').fetchone()[0] is None


def test_scope_connection_csrf_and_current_session_boundaries(pilot, monkeypatch):
    conn, users, clients, app, token = pilot
    monkeypatch.delenv(pilot_service.FLAG)
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        prepare(pilot)
    monkeypatch.setenv(pilot_service.FLAG, '1')
    prepare(pilot)
    path = '/account/integrations/mcp/report-views/' + KEY
    page = clients[0].get(path)
    assert clients[1].get(path).status_code == 404
    for values, origin in (({**form(page), 'csrf': 'bad'}, ORIGIN), (form(page), 'https://evil.example'),
                           ({**form(page), 'confirm': 'no'}, ORIGIN)):
        assert clients[0].post(path, data=values, headers={'Origin': origin}).status_code == 403
    assert clients[0].post(path, data={**form(page), 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different report view'):
        prepare(pilot, data=fields(name='Changed'))
    fresh = mcp_auth.Provider._tokens(conn, 'report-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    read_only = mcp_auth.Provider._tokens(conn, 'report-test', users[0]['id'], ['surveys:csm:read', 'work:comment:draft'], RESOURCE)
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
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 0
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
    assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1
    # A receipt must never attach to a replacement record with a reused ID.
    conn.execute('UPDATE report_saved_view SET operation_key=?', (str(uuid4()),))
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


def test_actual_mcp_dispatch_and_mobile_no_script_confirmation(pilot, monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='report-test', scopes=[pilot_service.SCOPE], resource=RESOURCE,
                          subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        result = await server.call_tool('prepare_saved_report_view', {**fields(), 'operation_id': KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_VIEW' not in str(result)
        context.scopes = ['surveys:csm:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_saved_report_view', {**fields(), 'operation_id': KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            browser_context, page = page_for(browser, clients[0], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/report-views/' + KEY)
                expect(page.get_by_role('heading', name='Save this personal report view?', exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                assert conn.execute('SELECT COUNT(*) FROM report_saved_view').fetchone()[0] == 0
                page.get_by_role('button', name='Confirm: save my report view', exact=True).click()
                page.get_by_role('link', name='Open my saved report view', exact=True).click()
                expect(page.get_by_role('heading', name=NAME, exact=True)).to_be_visible()
                page.get_by_role('link', name='My saved report views', exact=True).click()
                expect(page.get_by_role('link', name=NAME, exact=True)).to_be_visible()
            finally:
                browser_context.close()
        finally:
            browser.close()
