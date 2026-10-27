"""Unsubmitted reimbursement drafts require exact browser review."""
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
import mcp_travel_drafts as pilot_service
import travel_drafts as views
import storage as st
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'travel-drafts-operation-001'
NAME = 'PRIVATE_TRAVEL <script>untrusted</script>'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG):
        monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_COMMENT_DRAFTS_ENABLED', 'CSS_MCP_SUPPLY_DRAFTS_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('travel-test', json.dumps({'client_name': 'Travel test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'travel-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.execute('DELETE FROM holiday')
    conn.commit()
    return conn, users, clients, app, token


def fields(**changes):
    return {'title': NAME, 'start_date': '2026-10-14', 'end_date': '2026-10-16', 'venue': 'Palo',
            'dpo_no': 'DPO-2026-001', 'role': 'participant', 'answers': views.ReimbursementAnswers(flew=True).model_dump(), **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[4].access_token, RESOURCE, ORIGIN, operation_id, data or fields())


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1)
            for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


@pytest.mark.parametrize('change', ['scope', 'revoked', 'expired', 'switch', 'payload', 'snapshot'])
def test_current_gates_and_preview_digest(pilot, monkeypatch, change):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/travel-drafts/' + KEY
    page = clients[0].get(path)
    if change == 'scope':
        conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"work:read\"]'")
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired':
        conn.execute('UPDATE mcp_travel_draft_operation SET expires_at=1')
    elif change == 'switch':
        monkeypatch.setenv(pilot_service.FLAG, '0')
    elif change == 'snapshot':
        conn.execute('UPDATE mcp_travel_draft_operation SET snapshot_json=NULL')
    else:
        conn.execute('UPDATE mcp_travel_draft_operation SET payload_json=?', (json.dumps(fields(title='Changed')),))
    conn.commit()
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 0
    if change == 'expired':
        assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_travel_draft_operation').fetchone() == (None, None)


def test_scope_connection_csrf_and_current_session_boundaries(pilot, monkeypatch):
    conn, users, clients, app, token = pilot
    monkeypatch.delenv(pilot_service.FLAG)
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        prepare(pilot)
    monkeypatch.setenv(pilot_service.FLAG, '1')
    prepare(pilot)
    path = '/account/integrations/mcp/travel-drafts/' + KEY
    page = clients[0].get(path)
    assert clients[1].get(path).status_code == 404
    for values, origin in (({**form(page), 'csrf': 'bad'}, ORIGIN), (form(page), 'https://evil.example'),
                           ({**form(page), 'confirm': 'no'}, ORIGIN)):
        assert clients[0].post(path, data=values, headers={'Origin': origin}).status_code == 403
    assert clients[0].post(path, data={**form(page), 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different travel reimbursement draft'):
        prepare(pilot, data=fields(title='Changed'))
    fresh = mcp_auth.Provider._tokens(conn, 'travel-test', users[0]['id'], [pilot_service.SCOPE], RESOURCE)
    read_only = mcp_auth.Provider._tokens(conn, 'travel-test', users[0]['id'], ['surveys:csm:read', 'work:comment:draft'], RESOURCE)
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
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 0
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
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1
    # A receipt must never attach to a replacement record with a reused ID.
    conn.execute("UPDATE travel_filing SET ref_code='REPLACEMENT'")
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


def test_actual_mcp_dispatch_and_mobile_no_script_confirmation(pilot, monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='travel-test', scopes=[pilot_service.SCOPE], resource=RESOURCE,
                          subject=str(users[0]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        result = await server.call_tool('prepare_travel_reimbursement_draft', {**fields(), 'operation_id': KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_TRAVEL' not in str(result)
        context.scopes = ['surveys:csm:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_travel_reimbursement_draft', {**fields(), 'operation_id': KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            browser_context, page = page_for(browser, clients[0], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/travel-drafts/' + KEY)
                expect(page.get_by_role('heading', name='Open this reimbursement draft?', exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 0
                page.get_by_role('button', name='Confirm: open my reimbursement draft', exact=True).click()
                page.get_by_role('link', name='Open my reimbursement checklist', exact=True).click()
                expect(page.get_by_text('PRIVATE_TRAVEL', exact=True).first).to_be_visible()
            finally:
                browser_context.close()
        finally:
            browser.close()



def test_exact_open_checklist_source_replay_and_no_advancement(pilot, monkeypatch):
    import travel
    conn, users, clients, app, token = pilot
    unchanged = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in
                 ('calendar_entry', 'calendar_outbox', 'room_reservation', 'event', 'response',
                  'travel_submission', 'travel_review_note', 'work_task')}
    preview = prepare(pilot)
    assert prepare(pilot) == preview and NAME not in json.dumps(preview)
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 0
    path = '/account/integrations/mcp/travel-drafts/' + KEY
    page = clients[0].get(path)
    assert page.status_code == 200, page.text
    assert '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert '2026-10-23' in page.text and 'Admin Unit' in page.text and 'reminders' in page.text
    assert 'I travelled by plane' in page.text and 'Yes' in page.text
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    receipt = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['filing_id']
    assert NAME not in json.dumps(receipt) and 'DPO-2026-001' not in json.dumps(receipt)
    assert prepare(pilot) == receipt
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 1
    filing_id = int(receipt['filing_id'])
    saved = views.get(conn, users[0], filing_id)
    assert saved['act_title'] == NAME and saved['act_venue'] == 'Palo'
    assert saved['act_start'] == fields()['start_date'] and saved['act_end'] == fields()['end_date']
    assert saved['dpo_no'] == fields()['dpo_no'] and saved['user_id'] == users[0]['id']
    assert saved['kind'] == 'reimbursement' and saved['status'] == 'open'
    assert saved['source_kind'] == 'blank' and saved['entry_id'] is None and saved['event_id'] is None
    assert saved['advance_amount'] is None and saved['ca_filing_id'] is None and saved['mc114_format'] == 'none'
    assert saved['deadline_date'] == '2026-10-23' and saved['gen_state'] == 'idle'
    assert not saved['review_state'] and saved['reviewer_id'] is None
    assert saved['ready_at'] is None and saved['submitted_at'] is None
    assert travel.answers_of(saved) == travel.clean_answers({**fields()['answers'], 'role': 'participant'}, 'reimbursement')
    items = conn.execute('SELECT state,drive_url,doc_url FROM travel_item WHERE filing_id=?', (filing_id,)).fetchall()
    assert items and all(row == ('missing', None, None) for row in items)
    assert clients[0].get(receipt['web_url']).status_code == 200
    assert clients[1].get(receipt['web_url']).status_code == 404
    with pytest.raises(permissions.Denied):
        views.get(conn, users[4], filing_id)  # receipt domain is always owner-only
    for table, before in unchanged.items():
        assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_travel_draft_operation').fetchone() == (None, None)
    assert NAME not in str(conn.execute('SELECT summary,before_text,after_text FROM audit_log').fetchall())
    # Historical completion never overwrites subsequent ordinary user changes.
    conn.execute("UPDATE travel_filing SET dpo_no='EDITED',status='submitted' WHERE id=?", (filing_id,))
    conn.commit()
    assert prepare(pilot) == receipt
    assert travel.get_filing(conn, filing_id)['dpo_no'] == 'EDITED'
    monkeypatch.delenv(pilot_service.FLAG)
    assert clients[0].get(receipt['web_url']).status_code == 200


@pytest.mark.parametrize('changed', [
    {'title': ''}, {'title': '  '}, {'title': 'x'*201}, {'title': 'two\nlines'},
    {'venue': 'bad\x00'}, {'dpo_no': ' '}, {'dpo_no': 'x'*61}, {'dpo_no': 'bad\x00'},
    {'start_date': '2026-02-30'}, {'start_date': '20261014'}, {'start_date': True},
    {'end_date': '2026-10-13'}, {'end_date': '2028-10-16'}, {'end_date': '9999-10-16'},
    {'dpo_date': '2026-02-30'}, {'role': 'approver'}, {'answers': {'flew': 'yes'}},
    {'answers': {'refund': True}}, {'entry_id': 1}, {'event_id': 1}, {'user_id': 2},
    {'advance_amount': 1000}, {'kind': 'ca'}, {'mc114_format': 'appendix_b'}, {'status': 'submitted'},
])
def test_invalid_or_extra_fields_never_create_filings(pilot, changed):
    with pytest.raises(ValueError):
        prepare(pilot, data=fields(**changed))
    assert pilot[0].execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 0
    assert pilot[0].execute('SELECT COUNT(*) FROM mcp_travel_draft_operation').fetchone()[0] == 0


def test_current_deadline_policy_and_travel_switch_are_rechecked(pilot):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/travel-drafts/' + KEY
    page = clients[0].get(path)
    st.set_holiday(conn, '2026-10-19', 'New holiday', 'regular')
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM travel_filing').fetchone()[0] == 0
    st.set_setting(conn, 'travel.enabled', '0')
    with pytest.raises(docs.Conflict):
        prepare(pilot, operation_id='travel-disabled-operation-001')
    assert clients[0].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409


def test_deleted_filing_and_reused_id_cannot_rebind_receipt(pilot):
    conn, users, clients, app, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    result = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    original = views.get(conn, users[0], int(result['filing_id']))
    conn.execute('DELETE FROM travel_filing WHERE id=?', (original['id'],))
    assert conn.execute('SELECT COUNT(*) FROM travel_draft_save').fetchone()[0] == 0
    original.pop('operation_key')
    columns = ','.join(original)
    conn.execute('INSERT INTO travel_filing (' + columns + ') VALUES (' + ','.join('?' for _ in original) + ')', tuple(original.values()))
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)


def test_preview_normalizes_title_exactly_as_travel_storage(pilot):
    conn, users, clients, app, token = pilot
    prepare(pilot, data=fields(title='  Synthetic   site   visit  '))
    payload = auth.parse_token(clients[0].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    assert preview['fields']['title'] == 'Synthetic site visit'
    result = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert views.get(conn, users[0], int(result['filing_id']))['act_title'] == preview['fields']['title']
