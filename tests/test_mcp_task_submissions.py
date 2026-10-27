"""Assigned-task submissions use exact browser review and canonical API receipts."""
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
import mcp_task_submissions as pilot_service
import integration_operations as operations
import work_tasks
from tests.test_integration_task_api import headers
from tests.test_integration_submission_api import prepared as ready, url
import work
import work_blockers
import storage as st
from tests.test_integration_read_api import api
from tests.test_work import workspace

ORIGIN = 'http://testserver'
RESOURCE = ORIGIN + '/mcp'
KEY = 'task-submissions-operation-001'
NAME = 'PRIVATE_SUBMIT <script>untrusted</script>'
OUTPUT = 'PRIVATE_OUTPUT\nEvidence </textarea><script>untrusted</script> — salamat 👩🏽‍💻'


@pytest.fixture
def pilot(api, monkeypatch):
    conn, users, unit, clients, app = api
    for flag in ('CSS_MCP_ENABLED', pilot_service.FLAG):
        monkeypatch.setenv(flag, '1')
    for flag in ('CSS_BASE_URL', 'SPACE_HOST', 'CSS_MCP_COMMENT_DRAFTS_ENABLED', 'CSS_MCP_SUPPLY_DRAFTS_ENABLED'):
        monkeypatch.delenv(flag, raising=False)
    item, task, _ = ready(api)
    item = work.confirm_lead(conn, users[1], item['id'], item['revision'], users[3]['id'], 'Confirm next reviewer')
    conn.execute('INSERT INTO mcp_oauth_client VALUES (?,?,?)', ('submission-test', json.dumps({'client_name': 'Submission test'}), int(time.time())))
    token = mcp_auth.Provider._tokens(conn, 'submission-test', users[2]['id'], [pilot_service.SCOPE], RESOURCE)
    conn.commit()
    return conn, users, clients, app, item, task, token


def fields(pilot, **changes):
    return {'work_item_id': pilot[4]['id'], 'task_id': pilot[5]['id'],
            'revision': pilot[5]['revision'], 'reason': NAME, 'submission': OUTPUT, **changes}


def prepare(pilot, operation_id=KEY, data=None):
    return pilot_service.prepare(pilot[0], pilot[6].access_token, RESOURCE, ORIGIN, operation_id, data or fields(pilot))


def form(page):
    return {k: re.search(r'name="' + k + r'" value="([^"]+)"', page.text).group(1)
            for k in ('csrf', 'preview_digest')} | {'confirm': 'yes'}


@pytest.mark.parametrize('change', ['scope', 'revoked', 'expired', 'switch', 'payload', 'snapshot'])
def test_current_gates_and_preview_digest(pilot, monkeypatch, change):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/task-submissions/' + KEY
    page = clients[2].get(path)
    if change == 'scope':
        conn.execute("UPDATE mcp_oauth_grant SET scopes_json='[\"work:read\"]'")
    elif change == 'revoked':
        conn.execute('UPDATE mcp_oauth_grant SET revoked_at=1')
    elif change == 'expired':
        conn.execute('UPDATE mcp_task_submission SET expires_at=1')
    elif change == 'switch':
        monkeypatch.setenv(pilot_service.FLAG, '0')
    elif change == 'snapshot':
        conn.execute('UPDATE mcp_task_submission SET snapshot_json=NULL')
    else:
        conn.execute('UPDATE mcp_task_submission SET payload_json=?', (json.dumps(fields(pilot, reason='Changed')),))
    conn.commit()
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0
    if change == 'expired':
        assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_task_submission').fetchone() == (None, None)


def test_scope_connection_csrf_and_current_session_boundaries(pilot, monkeypatch):
    conn, users, clients, app, item, task, token = pilot
    monkeypatch.delenv(pilot_service.FLAG)
    with pytest.raises(mcp_actions.ActionError, match='disabled'):
        prepare(pilot)
    monkeypatch.setenv(pilot_service.FLAG, '1')
    prepare(pilot)
    path = '/account/integrations/mcp/task-submissions/' + KEY
    page = clients[2].get(path)
    assert clients[1].get(path).status_code == 404
    for values, origin in (({**form(page), 'csrf': 'bad'}, ORIGIN), (form(page), 'https://evil.example'),
                           ({**form(page), 'confirm': 'no'}, ORIGIN)):
        assert clients[2].post(path, data=values, headers={'Origin': origin}).status_code == 403
    assert clients[2].post(path, data={**form(page), 'preview_digest': 'bad'}, headers={'Origin': ORIGIN}).status_code == 409
    with pytest.raises(mcp_actions.ActionError, match='different submission'):
        prepare(pilot, data=fields(pilot, reason='Changed'))
    fresh = mcp_auth.Provider._tokens(conn, 'submission-test', users[2]['id'], [pilot_service.SCOPE], RESOURCE)
    read_only = mcp_auth.Provider._tokens(conn, 'submission-test', users[2]['id'], ['surveys:csm:read', 'work:task:acknowledge'], RESOURCE)
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.recover(conn, fresh.access_token, RESOURCE, ORIGIN, KEY)
    with pytest.raises(mcp_actions.ActionError, match='explicitly allow'):
        pilot_service.prepare(conn, read_only.access_token, RESOURCE, ORIGIN, 'read-ack-operation-001', fields(pilot))
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    conn.execute('DELETE FROM login_session WHERE session_id=?', (payload['sid'],))
    conn.commit()
    with pytest.raises(permissions.Denied):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)


def test_atomic_audit_failure_and_two_confirmations(pilot, monkeypatch):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    original = st.audit
    def failed(*args, **kwargs):
        if args[2] == 'integration_action_complete':
            raise RuntimeError('synthetic completion audit failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(st, 'audit', failed)
    with pytest.raises(RuntimeError):
        pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0
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
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='integration_action_complete'").fetchone()[0] == 1


def test_actual_mcp_dispatch_and_mobile_no_script_confirmation(pilot, monkeypatch):
    from playwright.sync_api import sync_playwright, expect
    from tests.test_appearance_browser import page_for
    import shutil
    conn, users, clients, app, item, task, token = pilot
    server, _ = mcp_read.build_server(app.get_conn, ORIGIN)
    context = AccessToken(token=token.access_token, client_id='submission-test', scopes=[pilot_service.SCOPE], resource=RESOURCE,
                          subject=str(users[2]['id']))
    monkeypatch.setattr(mcp_read, 'get_access_token', lambda: context)
    async def journey():
        result = await server.call_tool('prepare_task_submission', {**fields(pilot), 'operation_id': KEY})
        assert 'awaiting_confirmation' in str(result) and 'PRIVATE_SUBMIT' not in str(result)
        context.scopes = ['surveys:csm:read']
        with pytest.raises(Exception, match='explicitly allow'):
            await server.call_tool('prepare_task_submission', {**fields(pilot), 'operation_id': KEY})
    asyncio.run(journey())
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=shutil.which('chromium') or None, args=['--no-sandbox'])
        try:
            browser_context, page = page_for(browser, clients[2], viewport={'width': 320, 'height': 844}, java_script_enabled=False)
            try:
                page.goto(ORIGIN + '/account/integrations/mcp/task-submissions/' + KEY)
                expect(page.get_by_role('heading', name='Submit this assigned task for review?', exact=True)).to_be_visible()
                assert page.locator('html').evaluate('(el) => el.scrollWidth <= window.innerWidth')
                assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0
                page.get_by_role('button', name='Confirm: submit my task for review', exact=True).click()
                page.get_by_role('link', name='Open my task', exact=True).click()
                expect(page.get_by_text('For review', exact=True).first).to_be_visible()
            finally:
                browser_context.close()
        finally:
            browser.close()





def test_exact_submission_canonical_api_parity_replay_and_source(pilot):
    conn, users, clients, app, item, task, token = pilot
    unchanged = {t: conn.execute('SELECT * FROM ' + t).fetchall() for t in
                 ('work_comment', 'work_notice', 'calendar_entry', 'room_reservation', 'supply_request', 'travel_filing')}
    before_events = conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_submit'").fetchone()[0]
    preview = prepare(pilot)
    assert prepare(pilot) == preview and 'PRIVATE_SUBMIT' not in json.dumps(preview)
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0
    path = '/account/integrations/mcp/task-submissions/' + KEY
    page = clients[2].get(path)
    assert page.status_code == 200 and '&lt;script&gt;' in page.text and '<script>untrusted</script>' not in page.text
    assert 'In progress → For review' in page.text and 'shared-work history' in page.text
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    receipt = pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, KEY)
    assert receipt['status'] == 'completed' and receipt['result_status'] == 'for_review'
    assert receipt['result_revision'] == task['revision'] + 1
    assert receipt['next_actor'] == {'role': 'work_item_lead_or_authorized_officer',
                                     'lead_id': str(users[3]['id']), 'unit_id': str(item['unit_id'])}
    assert 'PRIVATE_SUBMIT' not in json.dumps(receipt) and 'PRIVATE_OUTPUT' not in json.dumps(receipt)
    canonical = clients[2].get(receipt['api_receipt_url'])
    assert canonical.status_code == 200
    assert canonical.json()['result_revision'] == receipt['result_revision']
    assert canonical.json()['id'] == receipt['api_operation_id'] and canonical.json()['action'] == 'submit'
    # API replay uses the exact original canonical fingerprint and key.
    replay = clients[2].post(url(item, task), headers=headers(clients[2], receipt['api_operation_id']),
        json={'revision': task['revision'], 'reason': NAME, 'submission': OUTPUT})
    assert replay.status_code == 200 and replay.json() == canonical.json()
    assert prepare(pilot) == receipt
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 200
    row = conn.execute('SELECT status,owner_id,due_date,submission,revision FROM work_task WHERE id=?', (task['id'],)).fetchone()
    assert row == ('for_review', task['owner_id'], task['due_date'], OUTPUT, task['revision'] + 1)
    assert conn.execute("SELECT COUNT(*) FROM work_event WHERE action='task_submit'").fetchone()[0] == before_events + 1
    for table, before in unchanged.items():
        assert conn.execute('SELECT * FROM ' + table).fetchall() == before
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_task_submission').fetchone() == (None, None)
    assert clients[2].get(receipt['web_url']).status_code == 200
    # Completed receipts are historical and do not repeat/overwrite later work.
    work_tasks.mutate(conn, users[3], item['id'], task['id'], receipt['result_revision'], 'accept',
                      {'reason': 'Reviewed exact submitted output'})
    assert prepare(pilot) == receipt
    assert conn.execute('SELECT status FROM work_task WHERE id=?', (task['id'],)).fetchone()[0] == 'done'


@pytest.mark.parametrize('change', ['revision', 'case_revision', 'owner', 'completed', 'work_off'])
def test_stale_or_unavailable_target_never_advances(pilot, change):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/task-submissions/' + KEY
    page = clients[2].get(path)
    if change == 'revision':
        conn.execute('UPDATE work_task SET revision=revision+1 WHERE id=?', (task['id'],))
    elif change == 'case_revision':
        conn.execute('UPDATE work_case SET revision=revision+1 WHERE id=?', (item['id'],))
    elif change == 'owner':
        conn.execute('UPDATE work_task SET owner_id=? WHERE id=?', (users[3]['id'], task['id']))
    elif change == 'completed':
        conn.execute("UPDATE work_case SET status='completed' WHERE id=?", (item['id'],))
    else:
        st.set_setting(conn, 'work.enabled', '0')
    conn.commit()
    response = clients[2].post(path, data=form(page), headers={'Origin': ORIGIN})
    assert response.status_code in (404, 409), response.text
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0
    assert conn.execute('SELECT status FROM work_task WHERE id=?', (task['id'],)).fetchone()[0] == 'in_progress'


@pytest.mark.parametrize('changed', [{'revision': True}, {'revision': 0}, {'reason': ' '}, {'reason': 'x'*2001},
    {'reason': 'bad\x00'}, {'task_id': -1}, {'work_item_id': 2**63}, {'submission': ''}, {'submission': 'x'*8001}, {'submission': True}, {'submission': 'bad\x00'}, {'owner_id': 1}])
def test_invalid_fields_do_not_prepare(pilot, changed):
    with pytest.raises(ValueError):
        prepare(pilot, data=fields(pilot, **changed))
    assert pilot[0].execute('SELECT COUNT(*) FROM mcp_task_submission').fetchone()[0] == 0


def test_two_distinct_previews_race_on_one_revision(pilot):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    prepare(pilot, 'other-submission-001')
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    previews = [pilot_service.browser(conn, payload, RESOURCE, ORIGIN, key)
                for key in (KEY, 'other-submission-001')]
    def confirm(preview):
        c = app.get_conn()
        try:
            return pilot_service.browser(c, payload, RESOURCE, ORIGIN, preview['operation_id'], confirm_digest=preview['preview_digest'])['status']
        except mcp_actions.ActionError as exc:
            return exc.code
        finally:
            c.close()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(confirm, previews))
    assert sorted(results) == ['completed', 'revision_conflict']
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 1


def test_officer_or_admin_cannot_prepare_for_other_owner(pilot):
    conn, users, clients, app, item, task, token = pilot
    for user in (users[0], users[1], users[4]):
        other = mcp_auth.Provider._tokens(conn, 'submission-test', user['id'], [pilot_service.SCOPE], RESOURCE)
        conn.commit()
        with pytest.raises(permissions.Denied):
            pilot_service.prepare(conn, other.access_token, RESOURCE, ORIGIN, KEY, fields(pilot))


def test_linked_record_revocation_blocks_pending_and_completed_recovery(pilot):
    conn, users, clients, app, item, task, token = pilot
    linked_item, linked_task, source = ready((conn, users, item['unit_id'], clients, app), linked=True)
    values = fields(pilot, work_item_id=linked_item['id'], task_id=linked_task['id'], revision=linked_task['revision'])
    prepare(pilot, data=values)
    prepare(pilot, 'other-linked-ack-operation-001', values)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    docs.mutate(conn, users[1], source['id'], source['revision'], 'access',
                {'visibility': 'restricted', 'viewers': [users[1]['id']], 'reason': 'Revoke source access'})
    for key in (KEY, 'other-linked-ack-operation-001'):
        with pytest.raises(permissions.Denied):
            pilot_service.recover(conn, token.access_token, RESOURCE, ORIGIN, key)
        with pytest.raises(permissions.Denied):
            pilot_service.browser(conn, payload, RESOURCE, ORIGIN, key)
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 1


@pytest.mark.parametrize('blocker', ['recorded', 'dependency', 'changed-decision'])
def test_new_blockers_prevent_confirmation_and_fresh_preparation(pilot, blocker):
    from tests.test_work import propose, advance
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/task-submissions/' + KEY
    page = clients[2].get(path)
    if blocker == 'recorded':
        updated = work_blockers.mutate(conn, users[2], item['id'], task['id'], task['revision'], 'block',
            {'reason': 'Waiting for correction', 'followup_owner_id': users[2]['id'], 'followup_date': '2026-10-29'})
    elif blocker == 'dependency':
        prerequisite = propose(conn, users[0], item, item['unit_id'], users[2]['id'])
        prerequisite = advance(conn, users[1], prerequisite, 'confirm', owner_id=users[2]['id'])
        updated = work_blockers.mutate(conn, users[1], item['id'], task['id'], task['revision'], 'dependency_add',
            {'reason': 'Wait for prerequisite acceptance', 'prerequisite_id': prerequisite['id']})
    else:
        import work_discussion, work_decisions
        message = work_discussion.post(conn, users[0], item['id'], 'Direction changed', task_id=task['id'])
        work_decisions.record(conn, users[1], item['id'], message, 1,
            {'kind': 'change', 'body': 'Review changed requirements', 'affected_tasks': [task['id']],
             'task_revisions': {str(task['id']): task['revision']}})
        updated = work_reads_task(conn, task['id'])
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code in (404, 409)
    with pytest.raises(permissions.Denied):
        prepare(pilot, 'blocked-new-submission-001', fields(pilot, revision=updated['revision']))
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0
    assert conn.execute('SELECT status,submission FROM work_task WHERE id=?', (task['id'],)).fetchone() == ('in_progress', task['submission'])


def work_reads_task(conn, task_id):
    from documents_storage import rows
    return rows(conn, 'SELECT * FROM work_task WHERE id=?', (task_id,))[0]


def test_routing_change_without_task_revision_requires_new_preview(pilot):
    conn, users, clients, app, item, task, token = pilot
    prepare(pilot)
    path = '/account/integrations/mcp/task-submissions/' + KEY
    page = clients[2].get(path)
    # Bind routing itself, even if an external import omits a revision bump.
    conn.execute('UPDATE work_case SET lead_id=? WHERE id=?', (users[1]['id'], item['id']))
    conn.commit()
    assert clients[2].post(path, data=form(page), headers={'Origin': ORIGIN}).status_code == 409
    assert conn.execute('SELECT COUNT(*) FROM work_api_operation').fetchone()[0] == 0


def test_large_utf8_output_is_exact_and_completed_copies_clear(pilot):
    conn, users, clients, app, item, task, token = pilot
    values = fields(pilot, reason='R'*2000, submission='😀'*8000)
    prepare(pilot, data=values)
    payload = auth.parse_token(clients[2].cookies.get(auth.COOKIE_NAME))
    preview = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY)
    assert preview['fields']['submission'] == values['submission']
    receipt = pilot_service.browser(conn, payload, RESOURCE, ORIGIN, KEY, confirm_digest=preview['preview_digest'])
    assert receipt['result_status'] == 'for_review'
    assert conn.execute('SELECT submission FROM work_task WHERE id=?', (task['id'],)).fetchone()[0] == values['submission']
    assert conn.execute('SELECT payload_json,snapshot_json FROM mcp_task_submission').fetchone() == (None, None)
    assert values['submission'] not in json.dumps(receipt)
