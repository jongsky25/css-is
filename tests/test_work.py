"""P1.1: synthetic work items, no external files, signatures, or mail."""
from tests.conftest import session_token
import re
import sqlite3

import pytest

import auth
import documents as docs
import documents_permissions as permissions
import storage as st
import work


@pytest.fixture
def workspace(tmp_path):
    path = str(tmp_path / 'work.db')
    conn = st.connect(path)
    st.init_db(conn)
    unit = st.add_org_unit(conn, 'Work Division', 'division', 'WORK/D1')
    users = []
    for i in range(5):
        uid = st.create_admin_user(conn, f'work{i}@example.test', 'unused', 'unused',
                                   'admin' if i == 4 else 'viewer', active=True)
        st.mark_onboarded(conn, uid)
        users.append(st.get_admin_user_by_id(conn, uid))
    conn.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-16')",
                 (users[1]['id'], unit))
    conn.commit()
    st.set_setting(conn, 'documents.enabled', '1')
    st.set_setting(conn, 'work.enabled', '1')
    yield conn, users, unit, path
    conn.close()


def case(conn, user, unit, **extra):
    return work.create(conn, user, {'title': 'Consolidate technical inputs', 'outcome': 'One supported response',
                                    'unit_id': unit, **extra})


def document(conn, user, unit, **extra):
    return docs.register(conn, user, {'subject': 'Correspondence source', 'type': 'request', 'unit_id': unit, **extra})


def test_repeat_migration_and_disabled_write_preserve_read(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    st.init_db(c)
    assert work.enabled(c)
    for setting in ('work.enabled', 'documents.enabled'):
        st.set_setting(c, setting, '0')
        st.init_db(c)
        assert not work.enabled(c)
        assert work.get(c, u[0], item['id'])['title'] == item['title']
        with pytest.raises(ValueError, match='not enabled'):
            case(c, u[0], unit)
        st.set_setting(c, setting, '1')
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0] == 1


def test_lead_proposal_does_not_grant_access_and_confirmation_is_scoped(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit, proposed_lead_id=u[2]['id'])
    assert item['lead_id'] is None
    for person in (u[2], u[3], u[4], {**u[3], 'role': 'admin'}):
        with pytest.raises(permissions.Denied):
            work.get(c, person, item['id'])
    with pytest.raises(permissions.Denied):
        work.confirm_lead(c, u[0], item['id'], 1, u[2]['id'], 'Self appointment')
    item = work.confirm_lead(c, u[1], item['id'], 1, u[2]['id'], 'Chief confirmed responsibility')
    assert work.get(c, u[2], item['id'])['lead_id'] == u[2]['id']
    with pytest.raises(docs.Conflict):
        work.confirm_lead(c, u[1], item['id'], 1, u[3]['id'], 'Stale reassignment')
    item = work.confirm_lead(c, u[1], item['id'], item['revision'], u[3]['id'], 'Reassigned')
    with pytest.raises(permissions.Denied):
        work.get(c, u[2], item['id'])
    # A records grant in a different unit provides no work authority here.
    other_unit = st.add_org_unit(c, 'Other', 'division', 'OTHER')
    other = case(c, u[0], other_unit)
    with pytest.raises(permissions.Denied):
        work.confirm_lead(c, u[1], other['id'], 1, u[2]['id'], 'Outside scope')


def test_multiple_references_leave_document_lifecycles_unchanged(workspace):
    c, u, unit, _ = workspace
    incoming = document(c, u[0], unit)
    outgoing = document(c, u[0], unit, direction='OUT')
    access_before = c.execute('SELECT * FROM document_access ORDER BY document_id,user_id,source').fetchall()
    item = case(c, u[0], unit, source_document_id=incoming['id'])
    item = work.link_document(c, u[0], item['id'], item['revision'], outgoing['id'])
    assert len(work.linked_documents(c, u[0], item['id'])) == 2
    assert docs.raw(c, incoming['id']) == incoming
    assert docs.raw(c, outgoing['id']) == outgoing
    assert c.execute('SELECT * FROM document_access ORDER BY document_id,user_id,source').fetchall() == access_before
    events = c.execute('SELECT COUNT(*) FROM work_event').fetchone()[0]
    assert work.link_document(c, u[0], item['id'], item['revision'], outgoing['id']) == item
    assert c.execute('SELECT COUNT(*) FROM work_event').fetchone()[0] == events
    assert work.cases_for_document(c, u[4], incoming['id']) == []


def test_link_requires_access_for_creator_and_lead_without_granting_it(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    item = work.confirm_lead(c, u[1], item['id'], 1, u[2]['id'], 'Confirmed')
    private = document(c, u[0], unit)
    with pytest.raises(ValueError, match='creator and confirmed lead'):
        work.link_document(c, u[0], item['id'], item['revision'], private['id'])
    assert not c.execute('SELECT 1 FROM work_document').fetchone()
    with pytest.raises(permissions.Denied):
        work.link_document(c, u[2], item['id'], item['revision'], private['id'])
    # Linking to a case does not implicitly make a proposed or confirmed lead a document viewer.
    assert not permissions.can_view(c, u[2], private)


def test_restricted_document_revocation_hides_entire_case_and_reverse_links(workspace):
    c, u, unit, _ = workspace
    doc = document(c, u[0], unit)
    item = case(c, u[0], unit, source_document_id=doc['id'])
    with pytest.raises(ValueError, match='every linked document'):
        work.confirm_lead(c, u[1], item['id'], 1, u[2]['id'], 'Needs document access')
    doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Checked'})
    item = work.confirm_lead(c, u[1], item['id'], 1, u[2]['id'], 'Confirmed')
    assert work.get(c, u[2], item['id'])
    docs.mutate(c, u[1], doc['id'], doc['revision'], 'access',
                {'visibility': 'restricted', 'viewers': [u[1]['id']], 'reason': 'Limit readership'})
    for user in (u[0], u[2], u[4]):
        with pytest.raises(permissions.Denied):
            work.get(c, user, item['id'])
        assert work.list_page(c, user)[0] == []
        assert work.cases_for_document(c, user, doc['id']) == []
    assert work.get(c, u[1], item['id'])


def test_invalid_create_and_audit_failure_roll_back_everything(workspace, monkeypatch):
    c, u, unit, _ = workspace
    hidden = document(c, u[3], unit)
    with pytest.raises(permissions.Denied):
        case(c, u[0], unit, source_document_id=hidden['id'])
    with pytest.raises(ValueError):
        case(c, u[0], unit, due_date='not a date')
    with pytest.raises(ValueError, match='concerned unit'):
        case(c, u[0], 99999)
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0] == 0
    def fail(*args, **kwargs):
        raise RuntimeError('Audit storage unavailable')
    monkeypatch.setattr(st, 'audit', fail)
    with pytest.raises(RuntimeError):
        case(c, u[0], unit)
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM work_event').fetchone()[0] == 0


def test_inactive_accounts_and_append_only_history(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (u[2]['id'],)); c.commit()
    with pytest.raises(ValueError, match='active staff'):
        work.confirm_lead(c, u[1], item['id'], 1, u[2]['id'], 'Inactive')
    with pytest.raises(permissions.Denied):
        case(c, u[2], unit)
    for sql in ('UPDATE work_event SET action=\'rewritten\'', 'DELETE FROM work_event'):
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            c.execute(sql)
        c.rollback()


def test_keyset_pages_do_not_skip_visible_records(workspace):
    c, u, unit, _ = workspace
    expected = []
    for i in range(7):
        item = case(c, u[0] if i % 2 == 0 else u[3], unit)
        if i % 2 == 0:
            expected.insert(0, item['id'])
    first, cursor = work.list_page(c, u[0], limit=2)
    second, final = work.list_page(c, u[0], before=cursor, limit=2)
    assert [x['id'] for x in first + second] == expected
    assert final is None


def test_merged_document_links_resolve_current_permissions_and_metadata(workspace):
    c, u, unit, _ = workspace
    source = document(c, u[0], unit, subject='Old reference')
    target = document(c, u[0], unit, subject='Current canonical reference')
    item = case(c, u[0], unit, source_document_id=source['id'])
    # Represent the result of a merge; the document merge service is covered separately.
    c.execute('UPDATE document SET canonical_id=? WHERE id=?', (target['id'], source['id'])); c.commit()
    linked = work.linked_documents(c, u[0], item['id'])
    assert linked[0]['id'] == target['id'] and linked[0]['subject'] == target['subject']
    assert work.cases_for_document(c, u[0], target['id'])[0]['id'] == item['id']
    assert work.link_document(c, u[0], item['id'], item['revision'], target['id']) == item
    assert len(work.linked_documents(c, u[0], item['id'])) == 1


def test_http_creation_lead_link_and_access(workspace, app_mod, monkeypatch):
    from starlette.testclient import TestClient
    c, u, unit, path = workspace
    monkeypatch.setattr(app_mod, 'DB', path)
    def client(user):
        result = TestClient(app_mod.app)
        result.cookies.set(auth.COOKIE_NAME, session_token(user))
        return result
    def token(page):
        assert page.status_code == 200, page.text
        return re.search(r'name="csrf" value="([a-f0-9]+)"', page.text)[1]
    with client(u[0]) as creator, client(u[1]) as officer, client(u[4]) as admin:
        csrf = token(creator.get('/work/new'))
        payload = {'csrf': csrf, 'title': 'Private coordination outcome', 'outcome': 'One response', 'unit_id': unit}
        assert creator.post('/work/new', data={**payload, 'csrf': ''}).status_code == 403
        result = creator.post('/work/new', data=payload, follow_redirects=False)
        assert result.status_code == 303, result.text
        url = result.headers['location']
        assert 'Awaiting confirmation' in creator.get(url).text
        assert 'Private coordination outcome' not in admin.get('/work').text
        assert admin.get(url).status_code == 404
        officer_csrf = token(officer.get(url))
        assert officer.post(url + '/lead', data={'csrf': csrf, 'revision': 1, 'lead_id': u[2]['id'], 'reason': 'Spoofed session'}).status_code == 403
        assert officer.post(url + '/lead', data={'csrf': officer_csrf, 'revision': 1, 'lead_id': u[2]['id'], 'reason': 'Assigned'}, follow_redirects=False).status_code == 303
        stale = officer.post(url + '/lead', data={'csrf': officer_csrf, 'revision': 1, 'lead_id': u[2]['id'], 'reason': 'Stale'})
        assert stale.status_code == 409
        doc = document(c, u[0], unit)
        doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Checked'})
        result = creator.post(url + '/link', data={'csrf': csrf, 'revision': 2, 'document_id': doc['id']}, follow_redirects=False)
        assert result.status_code == 303, result.text
        assert doc['number'] in creator.get(url).text
        assert 'Private coordination outcome' in creator.get(f"/documents/{doc['id']}").text
        assert 'Private coordination outcome' not in admin.get(f"/documents/{doc['id']}").text
        st.set_setting(c, 'work.enabled', '0')
        assert creator.get(url).status_code == 200
        assert 'Confirm lead' not in officer.get(url).text
        assert creator.post('/work/new', data=payload).status_code == 400

# P1.2 contribution workflows intentionally do not mutate legacy assignments.
import json
import work_tasks as tasks


def propose(c, user, item, unit, owner=None, **extra):
    return tasks.create(c, user, item['id'], {'title': 'Technical contribution', 'expected_output': 'Supported findings',
                        'unit_id': unit, 'proposed_owner_id': owner, **extra})


def advance(c, user, task, action, **extra):
    return tasks.mutate(c, user, task['case_id'], task['id'], task['revision'], action,
                        {'reason': 'Recorded decision', **extra})


def test_independent_contributions_return_resubmit_and_lead_acceptance(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    item = work.confirm_lead(c, u[1], item['id'], 1, u[2]['id'], 'Lead confirmed')
    a = propose(c, u[2], item, unit, u[0]['id'])
    b = propose(c, u[2], item, unit, u[3]['id'])
    for task, owner in ((a, u[0]), (b, u[3])):
        with pytest.raises(permissions.Denied):
            advance(c, u[2], task, 'confirm', owner_id=owner['id'])
    a = advance(c, u[1], a, 'confirm', owner_id=u[0]['id'])
    b = advance(c, u[1], b, 'confirm', owner_id=u[3]['id'])
    assert work.get(c, u[3], item['id'])
    assert b in tasks.list_for_case(c, u[3], item['id'])
    with pytest.raises(permissions.Denied):
        advance(c, u[0], a, 'submit', submission='Skipped acknowledgement')
    a = advance(c, u[0], a, 'acknowledge')
    b = advance(c, u[3], b, 'acknowledge')
    a = advance(c, u[0], a, 'submit', submission='First draft evidence')
    with pytest.raises(permissions.Denied):
        advance(c, u[0], a, 'accept')
    a = advance(c, u[2], a, 'return', reason='Add the missing basis')
    a = advance(c, u[0], a, 'submit', submission='Revised supported output')
    a = advance(c, u[2], a, 'accept')
    assert a['status'] == 'done'
    assert tasks.list_for_case(c, u[2], item['id'])[1] == b
    assert work.raw(c, item['id'])['revision'] == item['revision']
    history = [json.loads(r[0]) for r in c.execute("SELECT detail_json FROM work_event WHERE action='task_submit'")]
    assert [h['submission'] for h in history] == ['First draft evidence', 'Revised supported output']
    a = advance(c, u[2], a, 'reopen', reason='New technical clarification')
    assert a['status'] == 'in_progress'
    assert not c.execute('SELECT 1 FROM document_assignment').fetchone()


def test_proposed_owners_scoped_confirmation_and_reassignment(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    other = st.add_org_unit(c, 'Partner division', 'division', 'WORK/D2')
    task = propose(c, u[0], item, other, u[3]['id'])
    with pytest.raises(permissions.Denied):
        work.get(c, u[3], item['id'])
    with pytest.raises(permissions.Denied):
        advance(c, u[1], task, 'confirm', owner_id=u[3]['id'])
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-16')", (u[2]['id'], other)); c.commit()
    assert work.get(c, u[2], item['id'])
    task = advance(c, u[2], task, 'confirm', owner_id=u[3]['id'])
    assert work.get(c, u[3], item['id'])
    task = advance(c, u[3], task, 'acknowledge')
    task = advance(c, u[3], task, 'submit', submission='Prior owner output')
    task = advance(c, u[2], task, 'reassign', owner_id=u[4]['id'])
    assert task['status'] == 'todo' and task['submission'] == 'Prior owner output'
    with pytest.raises(permissions.Denied):
        work.get(c, u[3], item['id'])
    assert work.get(c, u[4], item['id'])
    task = advance(c, u[2], task, 'cancel')
    with pytest.raises(permissions.Denied):
        work.get(c, u[4], item['id'])
    assert work.get(c, u[2], item['id'])  # scoped officer retains the history


def test_task_source_access_deadlines_and_later_linking(workspace):
    c, u, unit, _ = workspace
    doc = document(c, u[0], unit)
    c.execute('UPDATE document SET due_date=? WHERE id=?', ('2026-10-25', doc['id'])); c.commit()
    item = case(c, u[0], unit, source_document_id=doc['id'])
    with pytest.raises(ValueError, match='official deadline'):
        propose(c, u[0], item, unit, due_date='2026-10-26')
    task = propose(c, u[0], item, unit, u[3]['id'], due_date='2026-10-24')
    with pytest.raises(ValueError, match='every linked document'):
        advance(c, u[1], task, 'confirm', owner_id=u[3]['id'])
    doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Checked'})
    task = advance(c, u[1], task, 'confirm', owner_id=u[3]['id'])
    hidden = document(c, u[0], unit)
    with pytest.raises(ValueError, match='contributor needs document access'):
        work.link_document(c, u[0], item['id'], item['revision'], hidden['id'])
    with pytest.raises(permissions.Denied):
        work.link_document(c, u[3], item['id'], item['revision'], doc['id'])
    docs.mutate(c, u[1], doc['id'], doc['revision'], 'access',
                {'visibility': 'restricted', 'viewers': [u[0]['id'], u[1]['id']], 'reason': 'Restricted'})
    with pytest.raises(permissions.Denied):
        advance(c, u[3], task, 'acknowledge')
    assert work.list_page(c, u[3])[0] == []
    assert work.cases_for_document(c, u[3], doc['id']) == []


def test_task_stale_revision_inactive_owner_and_audit_rollback(workspace, monkeypatch):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    task = propose(c, u[0], item, unit, u[3]['id'])
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (u[3]['id'],)); c.commit()
    with pytest.raises(ValueError, match='active staff'):
        advance(c, u[1], task, 'confirm', owner_id=u[3]['id'])
    task = advance(c, u[1], task, 'confirm', owner_id=u[0]['id'])
    old = task.copy()
    task = advance(c, u[0], task, 'acknowledge')
    with pytest.raises(docs.Conflict):
        advance(c, u[0], old, 'acknowledge')
    with pytest.raises(ValueError, match='Output or evidence'):
        advance(c, u[0], task, 'submit', submission='')
    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(st, 'audit', fail)
    with pytest.raises(RuntimeError):
        advance(c, u[0], task, 'submit', submission='Should roll back')
    assert tasks.list_for_case(c, u[0], item['id'])[0] == task
    with pytest.raises(RuntimeError):
        propose(c, u[0], item, unit)
    assert len(tasks.list_for_case(c, u[0], item['id'])) == 1


def test_task_http_authorization_csrf_stale_and_disabled(workspace, app_mod, monkeypatch):
    from starlette.testclient import TestClient
    c, u, unit, path = workspace
    monkeypatch.setattr(app_mod, 'DB', path)
    item = case(c, u[0], unit)
    url = f"/work/{item['id']}"
    with TestClient(app_mod.app) as client:
        def login(user):
            client.cookies.set(auth.COOKIE_NAME, session_token(user))
            page = client.get(url)
            assert page.status_code == 200
            return re.search(r'name="csrf" value="([a-f0-9]+)"', page.text)[1]
        csrf = login(u[0])
        payload = {'csrf': csrf, 'revision': item['revision'], 'title': 'HTTP contribution',
                   'expected_output': 'A supported answer', 'unit_id': unit, 'proposed_owner_id': u[3]['id']}
        assert client.post(url + '/tasks', data={**payload, 'csrf': ''}).status_code == 403
        assert client.post(url + '/tasks', data=payload).status_code == 200
        task = tasks.list_for_case(c, u[0], item['id'])[0]
        target = url + f"/tasks/{task['id']}"
        assert client.post(target + '/confirm', data={'csrf': csrf, 'revision': 1, 'owner_id': u[3]['id'], 'reason': 'Unscoped'}).status_code == 403
        csrf = login(u[1])
        assignment = {'csrf': csrf, 'revision': 1, 'owner_id': u[3]['id'], 'reason': 'Confirmed'}
        assert client.post(target + '/confirm', data=assignment).status_code == 200
        assert client.post(target + '/confirm', data=assignment).status_code == 409
        csrf = login(u[3])
        assert 'Acknowledge and start' in client.get(url).text
        assert 'Confirm accountable lead' not in client.get(url).text
        assert 'Link an existing document' not in client.get(url).text
        assert client.post(target + '/acknowledge', data={'csrf': csrf, 'revision': 2, 'reason': 'Started'}).status_code == 200
        invalid = client.post(target + '/submit', data={'csrf': csrf, 'revision': 3, 'reason': '',
                                                       'submission': 'Preserve this typed evidence'})
        assert invalid.status_code == 400
        assert 'Preserve this typed evidence</textarea>' in invalid.text
        assert client.post(target + '/submit', data={'csrf': csrf, 'revision': 3, 'reason': 'Ready', 'submission': '<script>bad()</script>'}).status_code == 200
        page = client.get(url)
        assert '&lt;script&gt;bad()&lt;/script&gt;' in page.text
        assert '<script>bad()</script>' not in page.text
        st.set_setting(c, 'work.enabled', '0')
        assert client.get(url).status_code == 200
        assert 'Propose a contribution' not in client.get(url).text
        assert client.post(target + '/submit', data={'csrf': csrf, 'revision': 4, 'reason': 'Ready', 'submission': 'Again'}).status_code == 400
        st.init_db(c)
        assert not work.enabled(c) and len(tasks.list_for_case(c, u[3], item['id'])) == 1


def test_legacy_document_lead_can_accept_but_cannot_submit_for_another(workspace):
    c, u, unit, _ = workspace
    doc = document(c, u[0], unit)
    doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'lead',
                      {'user_id': u[2]['id'], 'reason': 'Lead', 'task': 'Coordinate'})
    doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'assign',
                      {'user_id': u[3]['id'], 'reason': 'Contributor', 'task': 'Provide input'})
    assignment = c.execute("SELECT id FROM document_assignment WHERE document_id=? AND user_id=?", (doc['id'], u[3]['id'])).fetchone()[0]
    payload = {'assignment_id': assignment, 'status': 'submitted', 'outcome': 'Input'}
    with pytest.raises(permissions.Denied):
        docs.mutate(c, u[2], doc['id'], doc['revision'], 'contribution', payload)
    doc = docs.mutate(c, u[3], doc['id'], doc['revision'], 'contribution', payload)
    with pytest.raises(permissions.Denied):
        docs.mutate(c, u[3], doc['id'], doc['revision'], 'contribution', {**payload, 'status': 'completed'})
    doc = docs.mutate(c, u[2], doc['id'], doc['revision'], 'contribution', {**payload, 'status': 'completed'})
    assert c.execute('SELECT status FROM document_assignment WHERE id=?', (assignment,)).fetchone()[0] == 'completed'

# P1.3 explicit, idempotent migration and compatibility contracts.
import work_compat as compat


def legacy_setup(c, u, unit, statuses=('assigned',), mandatory=1):
    doc = document(c, u[0], unit)
    doc = docs.mutate(c, u[1], doc['id'], doc['revision'], 'verify', {'verification': 'verified', 'reason': 'Checked'})
    c.execute("UPDATE document SET lead_id=?,policy_json=?,reconcile=0 WHERE id=?", (u[2]['id'], '{"closure":[]}', doc['id']))
    c.execute("INSERT INTO document_assignment(document_id,user_id,role,action,status,created_at) VALUES (?,?,'lead','Coordinate','assigned','2026-10-16')", (doc['id'],u[2]['id']))
    for state in statuses:
        c.execute('''INSERT INTO document_assignment(document_id,user_id,role,action,status,due_date,outcome,mandatory,created_at)
                     VALUES (?,?,'contributor','Technical input',?,'2026-10-23',?,?, '2026-10-16')''',
                  (doc['id'],u[3]['id'],state,'Original evidence: '+state,mandatory))
    c.commit()
    return docs.raw(c,doc['id'])


def migrate(c, u, doc):
    return compat.migrate(c,u[1],doc['id'],doc['revision'],'One agreed response','Rehearse this explicit record')


def test_migration_maps_every_state_preserves_sources_and_repeats(workspace):
    c,u,unit,_ = workspace
    doc=legacy_setup(c,u,unit,tuple(compat.STATES))
    original=c.execute('SELECT * FROM document_assignment').fetchall()
    report=migrate(c,u,doc)
    assert report['source_rows_preserved'] and len(report['lead_assignment_ids'])==1
    assert len(report['contributors'])==7
    for row in report['contributors']:
        assert row['current_status']==compat.STATES[row['source_status']]
        assert row['owner_id']==(None if row['source_status']=='proposed' else u[3]['id'])
        assert row['source_due_date']==row['due_date'] and row['mandatory']==row['source_mandatory']==1
        assert row['initial_evidence_preserved']
    assert work.raw(c,report['case_id'])['lead_id']==u[2]['id']
    assert len(tasks.list_for_case(c,u[1],report['case_id']))==7 # no redundant lead task
    assert migrate(c,u,doc)==report
    st.init_db(c)
    assert c.execute('SELECT * FROM document_assignment').fetchall()==original
    for sql in ('UPDATE document_assignment SET outcome=\'overwritten\'', 'DELETE FROM document_assignment'):
        with pytest.raises(sqlite3.IntegrityError): c.execute(sql)
        c.rollback()
    assert c.execute('SELECT COUNT(*) FROM work_case').fetchone()[0]==1


def test_migrated_old_and_new_entry_points_share_task_state_and_closure(workspace):
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit)
    report=migrate(c,u,doc); cid=report['case_id']; aid=report['contributors'][0]['assignment_id']
    task=tasks.list_for_case(c,u[1],cid)[0]
    doc=docs.raw(c,doc['id'])
    with pytest.raises(ValueError,match='Mandatory contributions'):
        docs.mutate(c,u[2],doc['id'],doc['revision'],'close',{'evidence':{}})
    payload={'assignment_id':aid,'status':'acknowledged','outcome':'Starting'}
    with pytest.raises(docs.Conflict,match='task revision'):
        docs.mutate(c,u[3],doc['id'],doc['revision'],'contribution',payload)
    doc=docs.mutate(c,u[3],doc['id'],doc['revision'],'contribution',{**payload,'task_revision':1})
    task=tasks.list_for_case(c,u[3],cid)[0]
    assert task['status']=='in_progress' and task['revision']==2
    task=advance(c,u[3],task,'submit',submission='Current submitted output')
    with pytest.raises(docs.Conflict):
        docs.mutate(c,u[2],doc['id'],doc['revision'],'contribution',
                    {**payload,'status':'completed','task_revision':2})
    doc=docs.mutate(c,u[2],doc['id'],doc['revision'],'contribution',
                    {**payload,'status':'completed','task_revision':task['revision']})
    assert c.execute('SELECT status FROM document_assignment WHERE id=?',(aid,)).fetchone()[0]=='assigned'
    assert c.execute('SELECT status FROM document_assignment_effective WHERE id=?',(aid,)).fetchone()[0]=='completed'
    assert docs.metrics(c,[doc])['unacknowledged']==0
    doc=docs.mutate(c,u[2],doc['id'],doc['revision'],'close',{'evidence':{}})
    task=tasks.list_for_case(c,u[2],cid)[0]
    with pytest.raises(ValueError,match='Reopen the official'):
        advance(c,u[2],task,'reopen')
    assert doc['status']=='closed'


def test_migrated_new_tasks_optional_flags_and_atomic_lead_sync(workspace):
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit,('assigned',),mandatory=0)
    report=migrate(c,u,doc); item=work.get(c,u[1],report['case_id'])
    task=propose(c,u[1],item,unit,u[0]['id'])
    effective=c.execute('SELECT id,mandatory FROM document_assignment_effective WHERE id=?',(-task['id'],)).fetchone()
    assert effective==(-task['id'],1)
    doc=docs.raw(c,doc['id'])
    with pytest.raises(ValueError,match='Mandatory contributions'):
        docs.mutate(c,u[2],doc['id'],doc['revision'],'close',{'evidence':{}})
    task=advance(c,u[1],task,'cancel')
    item=work.confirm_lead(c,u[1],item['id'],item['revision'],u[0]['id'],'Officer-approved handoff')
    doc=docs.raw(c,doc['id'])
    assert doc['lead_id']==item['lead_id']==u[0]['id']
    assert doc['revision']>report.get('source_revision',1)
    docs.mutate(c,u[0],doc['id'],doc['revision'],'close',{'evidence':{}}) # optional legacy input doesn't block


def test_migration_refuses_unsafe_sources_and_rolls_back(workspace,monkeypatch):
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit)
    with pytest.raises(permissions.Denied):
        compat.migrate(c,u[0],doc['id'],doc['revision'],'Outcome','Unscoped')
    c.execute("UPDATE document_assignment SET status='unknown' WHERE role='contributor'");c.commit()
    with pytest.raises(ValueError,match='unsupported'): migrate(c,u,doc)
    assert not c.execute('SELECT 1 FROM work_case').fetchone()
    c.execute("UPDATE document_assignment SET status='assigned' WHERE role='contributor'")
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[3]['id'],));c.commit()
    with pytest.raises(ValueError,match='active staff'): migrate(c,u,doc)
    c.execute('UPDATE admin_user SET active=1 WHERE id=?',(u[3]['id'],));c.commit()
    def fail(*args,**kwargs): raise RuntimeError('Audit unavailable')
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError): migrate(c,u,doc)
    assert not c.execute('SELECT 1 FROM work_case').fetchone()
    assert not c.execute('SELECT 1 FROM work_legacy_assignment').fetchone()


def test_migrated_legacy_writes_cannot_fall_back_when_disabled(workspace):
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit); report=migrate(c,u,doc);doc=docs.raw(c,doc['id'])
    with pytest.raises(ValueError,match='Shared work'):
        docs.mutate(c,u[1],doc['id'],doc['revision'],'assign',{'user_id':u[0]['id'],'reason':'New','task':'Input'})
    st.set_setting(c,'work.enabled','0')
    row=report['contributors'][0]
    with pytest.raises(ValueError,match='not enabled'):
        docs.mutate(c,u[3],doc['id'],doc['revision'],'contribution',
                    {'assignment_id':row['assignment_id'],'task_revision':1,'status':'acknowledged','outcome':'Try fallback'})
    assert c.execute('SELECT status FROM document_assignment_effective WHERE id=?',(row['assignment_id'],)).fetchone()[0]=='assigned'
    assert work.get(c,u[3],report['case_id'])


def test_copy_rehearsal_preserves_source_and_refuses_overwrite(workspace,tmp_path):
    import hashlib
    from scripts.rehearse_work_migration import rehearse
    c,u,unit,path=workspace
    doc=legacy_setup(c,u,unit,('proposed','submitted','superseded'))
    plan=[{'document_id':doc['id'],'revision':doc['revision'],'outcome':'Agreed output','reason':'Rehearsal'}]
    before=hashlib.sha256(open(path,'rb').read()).hexdigest()
    dest=tmp_path/'copy.db'
    result=rehearse(path,dest,plan,u[1]['id'])
    assert result['repeat_migration_verified'] and result['rehearsal_only']
    assert hashlib.sha256(open(path,'rb').read()).hexdigest()==before
    assert not c.execute('SELECT 1 FROM work_legacy_document').fetchone()
    with pytest.raises(FileExistsError): rehearse(path,dest,plan,u[1]['id'])
    with pytest.raises(ValueError): rehearse(path,path,plan,u[1]['id'])


def test_migrated_http_projection_respects_shared_audience(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace
    monkeypatch.setattr(app_mod,'DB',path)
    doc=legacy_setup(c,u,unit); report=migrate(c,u,doc); cid=report['case_id']
    task=tasks.list_for_case(c,u[3],cid)[0]
    task=advance(c,u[3],task,'acknowledge')
    task=advance(c,u[3],task,'submit',submission='Confidential collaborative evidence')
    # Link a second restricted source, permitted to all confirmed participants but not another bureau reader.
    private=document(c,u[0],unit)
    private=docs.mutate(c,u[1],private['id'],private['revision'],'access',
                       {'visibility':'restricted','viewers':[x['id'] for x in u[:4]],'reason':'Limited audience'})
    item=work.raw(c,cid)
    work.link_document(c,u[1],cid,item['revision'],private['id'])
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
        page=client.get(f"/documents/{doc['id']}")
        assert page.status_code==200 and 'Confidential collaborative evidence' in page.text
        assert f'/work/{cid}' in page.text and 'Assignment number' not in page.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        page=client.get(f"/documents/{doc['id']}")
        assert page.status_code==200
        assert 'Confidential collaborative evidence' not in page.text
        assert f'/work/{cid}' not in page.text
        assert client.get(f'/work/{cid}').status_code==404
    assert not permissions.assigned(c,u[4],doc)
    assert permissions.can_release(c,u[2],doc) # lead ownership retains its former authority


def test_migrated_milestones_and_reminders_use_current_task_state(workspace):
    import documents_notify as notices
    from datetime import datetime
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit)
    c.execute('UPDATE document SET due_date=?,policy_json=? WHERE id=?',('2026-10-25',json.dumps(
        {'closure':[],'cutoff':'17:00','reminder_time':'08:00','escalate_chief_days':1,'escalate_director_days':2}),doc['id']));c.commit()
    report=migrate(c,u,doc);cid=report['case_id'];task=tasks.list_for_case(c,u[1],cid)[0]
    task=advance(c,u[3],task,'acknowledge')
    task=advance(c,u[2],task,'milestone',due_date='2026-10-22')
    aid=report['contributors'][0]['assignment_id']
    assert c.execute('SELECT due_date FROM document_assignment WHERE id=?',(aid,)).fetchone()[0]=='2026-10-23'
    assert c.execute('SELECT due_date FROM document_assignment_effective WHERE id=?',(aid,)).fetchone()[0]=='2026-10-22'
    notices.schedule(c,datetime(2026,10,22,10))
    assert c.execute("SELECT 1 FROM document_notice WHERE kind LIKE 'milestone:%' AND state='pending'").fetchone()
    task=advance(c,u[3],task,'submit',submission='All input supplied')
    advance(c,u[2],task,'accept')
    notices.schedule(c,datetime(2026,10,22,10))
    assert not c.execute("SELECT 1 FROM document_notice WHERE kind LIKE 'milestone:%' AND state='pending'").fetchone()
    assert c.execute("SELECT 1 FROM document_notice WHERE kind='assignments_migrated' AND state='pending'").fetchone()

# P1.4 personal responsibilities, independent of broad visibility.
import work_inbox as inbox


def inbox_case(c,u,unit):
    item=case(c,u[0],unit)
    return work.confirm_lead(c,u[1],item['id'],item['revision'],u[2]['id'],'Confirmed coordination lead')


def test_personal_inbox_tracks_owner_waiting_and_lead_review(workspace):
    c,u,unit,_=workspace
    item=inbox_case(c,u,unit)
    task=propose(c,u[0],item,unit,u[3]['id'],due_date='2026-10-15')
    assert inbox.page(c,u[3])[0]==[] # suggestion grants no personal task
    assert inbox.page(c,u[2])[0]==[] # lead cannot confirm assignments
    assert inbox.page(c,u[1])[0][0]['action']=='Confirm contribution owner'
    task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    assert inbox.page(c,u[1])[0]==[] # broad officer authority is not a personal assignment
    entry=inbox.page(c,u[3],today=__import__('datetime').date(2026,10,16))[0][0]
    assert entry['action']=='Acknowledge and start' and entry['due_label']=='Overdue'
    task=advance(c,u[3],task,'acknowledge')
    assert inbox.page(c,u[3])[0][0]['action']=='Prepare and submit output'
    task=advance(c,u[3],task,'submit',submission='Input ready')
    assert inbox.page(c,u[3])[0]==[]
    assert inbox.page(c,u[3],waiting=True)[0][0]['action']=='Waiting for contribution review'
    assert inbox.page(c,u[2])[0][0]['action']=='Review submitted contribution'
    assert inbox.page(c,u[1])[0]==[]
    task=advance(c,u[2],task,'return')
    assert inbox.page(c,u[3],waiting=True)[0]==[]
    task=advance(c,u[3],task,'submit',submission='Revised input')
    advance(c,u[2],task,'accept')
    for user in u:
        assert inbox.page(c,user)[0]==[] and inbox.page(c,user,waiting=True)[0]==[]


def test_inbox_reassignment_revocation_and_disabled_home(workspace):
    c,u,unit,_=workspace
    item=inbox_case(c,u,unit); task=propose(c,u[0],item,unit,u[3]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    assert inbox.home_rows(c,u[3])
    task=advance(c,u[1],task,'reassign',owner_id=u[0]['id'])
    assert inbox.home_rows(c,u[3])==[]
    doc=document(c,u[0],unit)
    doc=docs.mutate(c,u[1],doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Checked'})
    work.link_document(c,u[0],item['id'],item['revision'],doc['id'])
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Limit source access'})
    assert inbox.page(c,u[0])[0]==[] and inbox.home_rows(c,u[0])==[]
    # Feature switches remove action cards; permitted read-only lists remain available.
    second=inbox_case(c,u,unit);another=propose(c,u[0],second,unit,u[3]['id'])
    advance(c,u[1],another,'confirm',owner_id=u[3]['id'])
    st.set_setting(c,'work.enabled','0')
    assert inbox.page(c,u[3])[0][0]['can_act'] is False
    assert inbox.home_rows(c,u[3])==[]
    st.set_setting(c,'documents.enabled','0')
    assert inbox.home_rows(c,u[1])==[]


def test_inbox_migration_deduplication_and_legacy_completion(workspace):
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit)
    entries=inbox.page(c,u[3])[0]
    assert len(entries)==1 and entries[0]['url']==f"/documents/{doc['id']}"
    assert inbox.page(c,u[1])[0]==[]
    report=migrate(c,u,doc)
    entries=inbox.page(c,u[3])[0]
    assert len(entries)==1 and entries[0]['url'].startswith(f"/work/{report['case_id']}#task-")
    assert entries[0]['key'].startswith('work:task:')
    item=tasks.list_for_case(c,u[3],report['case_id'])[0]
    item=advance(c,u[3],item,'acknowledge');item=advance(c,u[3],item,'submit',submission='Ready')
    assert len(inbox.page(c,u[3],waiting=True)[0])==1
    assert len(inbox.page(c,u[2])[0])==1
    advance(c,u[2],item,'accept')
    assert inbox.home_rows(c,u[3])==[] and inbox.home_rows(c,u[2])==[]


def test_inbox_pagination_skips_hidden_candidates_without_losing_tasks(workspace):
    c,u,unit,_=workspace
    item=inbox_case(c,u,unit)
    expected=[]
    for i in range(7):
        task=propose(c,u[0],item,unit,u[3]['id'])
        task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
        expected.insert(0, 'work:task:'+str(task['id']))
    first,cursor=inbox.page(c,u[3],limit=3)
    # The cursor's task can complete or be reassigned between pages without losing the boundary.
    boundary_id=int(first[-1]['key'].split(':')[-1])
    task=next(t for t in tasks.list_for_case(c,u[3],item['id']) if t['id']==boundary_id)
    advance(c,u[1],task,'reassign',owner_id=u[0]['id'])
    second,cursor=inbox.page(c,u[3],before=cursor,limit=3)
    third,end=inbox.page(c,u[3],before=cursor,limit=3)
    assert [e['key'] for e in first+second+third]==expected and end is None
    # More than one scan of unrelated decision candidates exposes no titles or counts.
    for i in range(251):
        c.execute("INSERT INTO work_case(title,outcome,unit_id,creator_id,created_at,updated_at) VALUES ('Hidden subject','Hidden output',?,?,?,?)",(unit,u[0]['id'],'2099-01-01','2099-01-01'))
    c.commit()
    hidden,cursor=inbox.page(c,u[3])
    assert hidden==[] and cursor
    later,end=inbox.page(c,u[3],before=cursor)
    assert len(later)==6 and all('Hidden' not in str(x) for x in later)


def test_home_approvals_not_duplicated_in_personal_tasks(workspace):
    import office_connect as oc
    c,u,unit,_=workspace
    doc=document(c,u[0],unit,direction='OUT')
    c.execute("UPDATE document SET status='in_review',reviewer_id=?,visibility='bureau',verification='verified' WHERE id=?",(u[2]['id'],doc['id']));c.commit()
    assert inbox.home_rows(c,u[2])==[]
    cards=oc.home_tasks(c,u[2])
    approvals=[x for x in cards if x['key']=='approvals']
    assert len(approvals)==1 and '1 document review' in approvals[0]['detail']
    assert not any(x['key']=='documents' for x in cards)
    item=inbox_case(c,u,unit);task=propose(c,u[0],item,unit,u[2]['id'])
    advance(c,u[1],task,'confirm',owner_id=u[2]['id'])
    cards=oc.home_tasks(c,u[2])
    assert len([x for x in cards if x['key'].startswith('work:task:')])==1
    assert len([x for x in cards if x['key']=='approvals'])==1


def test_personal_inbox_http_filters_home_and_dates(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace
    monkeypatch.setattr(app_mod,'DB',path)
    item=inbox_case(c,u,unit);task=propose(c,u[0],item,unit,u[3]['id'],title='Prepare the regional input',due_date='2026-10-23')
    task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
        page=client.get('/work/mine')
        assert page.status_code==200 and 'Prepare the regional input' in page.text
        assert 'October 23, 2026' in page.text and 'Acknowledge and start' in page.text
        assert 'Prepare the regional input' in client.get('/').text
        assert 'Prepare the regional input' not in client.get('/work/mine?view=waiting').text.split('<div class="work-wrap">',1)[1]
        assert client.get('/work/mine?view=bogus').status_code==400
        assert client.get('/work/mine?before=-3').status_code==400
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert 'Prepare the regional input' not in client.get('/work/mine').text
        assert 'Prepare the regional input' not in client.get('/').text


def test_bell_and_fallback_review_follow_real_responsibilities(workspace):
    import documents_notify as notices
    c,u,unit,_=workspace
    item=inbox_case(c,u,unit);task=propose(c,u[0],item,unit,u[3]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    assert notices.bell_rows(c,u[1]['id'])==[]
    assert len(notices.bell_rows(c,u[3]['id']))==1
    task=advance(c,u[3],task,'acknowledge');task=advance(c,u[3],task,'submit',submission='Ready')
    assert notices.bell_rows(c,u[3]['id'])==[]
    assert len(notices.bell_rows(c,u[2]['id']))==1
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[2]['id'],));c.commit()
    assert inbox.page(c,u[1])[0][0]['action']=='Review submitted contribution'
    other=st.add_org_unit(c,'Other unit','division','WORK/OTHER')
    c.execute('UPDATE document_role_grant SET unit_id=? WHERE user_id=?',(other,u[1]['id']));c.commit()
    assert inbox.page(c,u[1])[0]==[] # fresh scope, no cached officer role

# P1.5 reviewed intake and atomic work selection.
import work_intake as intake


def intake_fields(unit,**extra):
    return {'subject':'New correspondence','type':'request','unit_id':unit,'scenario':'reference',
            'work_mode':'reference','confirmed':'yes',**extra}


def test_reference_intake_suppresses_automatic_assignments_but_retains_policy(workspace):
    c,u,unit,_=workspace
    import documents_rules
    # Evaluate through a controlled routing result, preserving its formal policy.
    from unittest.mock import patch
    evaluation={'leads':[u[2]['id']],'assignees':[u[3]['id']],'lead_units':[unit],
                'unit_ids':[unit],'policy':{'closure':['outcome']},'matches':[]}
    with patch.object(documents_rules,'evaluate',return_value=evaluation):
        doc,item=intake.register(c,u[0],intake_fields(unit))
    assert item is None and doc['lead_id'] is None
    assert json.loads(doc['policy_json'])=={'closure':['outcome']}
    assert not c.execute('SELECT 1 FROM document_assignment').fetchone()
    assert not c.execute('SELECT 1 FROM work_task').fetchone()
    assert not c.execute('SELECT 1 FROM work_case').fetchone()
    assert doc['number'].endswith('000001')


@pytest.mark.parametrize('scenario,count',[('response',1),('inputs',1),('activity',2)])
def test_curated_intake_proposes_only_confirmed_choice_without_authority(workspace,scenario,count):
    c,u,unit,_=workspace
    doc,item=intake.register(c,u[0],intake_fields(unit,scenario=scenario,work_mode='new',
                  outcome=intake.SCENARIOS[scenario]['outcome'],proposed_lead_id=u[2]['id'],propose_steps='yes'))
    contributions=tasks.list_for_case(c,u[0],item['id'])
    assert len(contributions)==count
    assert all(t['status']=='proposed' and t['owner_id'] is None and t['due_date'] is None for t in contributions)
    assert item['lead_id'] is None and doc['lead_id'] is None
    assert doc['status']=='registered' and doc['approved_version'] is None
    assert not c.execute('SELECT 1 FROM document_assignment').fetchone()
    assert work.linked_documents(c,u[0],item['id'])[0]['id']==doc['id']
    assert inbox.page(c,u[2])[0]==[]


def test_intake_existing_link_stale_and_access_failure_are_atomic(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    fields=intake_fields(unit,scenario='inputs',work_mode='existing',case_selection=f"{item['id']}:{item['revision']}")
    doc,linked=intake.register(c,u[0],fields)
    assert linked['id']==item['id'] and len(work.linked_documents(c,u[0],item['id']))==1
    before=c.execute('SELECT * FROM document_sequence').fetchall()
    with pytest.raises(docs.Conflict):intake.register(c,u[0],fields)
    assert c.execute('SELECT * FROM document_sequence').fetchall()==before
    # Existing lead cannot read the newly created preverification record; linking must not grant access.
    other=inbox_case(c,u,unit)
    with pytest.raises(ValueError,match='creator and confirmed lead'):
        intake.register(c,u[0],{**fields,'case_selection':f"{other['id']}:{other['revision']}"})
    assert c.execute('SELECT COUNT(*) FROM document').fetchone()[0]==1
    assert c.execute('SELECT * FROM document_sequence').fetchall()==before


def test_intake_invalid_and_failed_steps_roll_back_numbering(workspace,monkeypatch):
    c,u,unit,_=workspace
    fields=intake_fields(unit,scenario='response',work_mode='new',outcome='A supported response',propose_steps='yes')
    with pytest.raises(ValueError,match='confirm'):intake.register(c,u[0],{**fields,'confirmed':''})
    with pytest.raises(ValueError,match='reference'):intake.register(c,u[0],{**fields,'scenario':'reference'})
    def fail(*args,**kwargs):raise RuntimeError('Task storage failed')
    monkeypatch.setattr(tasks,'create_in_transaction',fail)
    with pytest.raises(RuntimeError):intake.register(c,u[0],fields)
    for table in ('document','document_sequence','work_case','work_task','work_event','document_event'):
        assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    st.set_setting(c,'work.enabled','0')
    doc,item=intake.register(c,u[0],intake_fields(unit))
    assert item is None and doc['number'].endswith('000001')


class IntakeAdapter:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def call(self,action,payload,operation):
        self.calls.append((action,payload))
        if self.fail:raise RuntimeError('Relay unavailable')
        if action=='inspect':return {'file_id':payload['file_id'],'fingerprint':'source-v1','accessible':True,'size':200}
        return {'state':'confirmed','suggestions':{'subject':'Suggested subject','type':'request',
               'due_date':'2026-11-01','lead_id':'999','approval':'approved'},
                'excerpts':['<script>untrusted()</script>'],'warnings':['Check the source date.']}


def test_pre_registration_extraction_is_transient_and_allowlisted(workspace):
    c,u,unit,_=workspace
    adapter=IntakeAdapter()
    result=intake.preview(c,u[0],'https://drive.google.com/file/d/sourcefile123456/view',adapter)
    assert result['suggestions']=={'subject':'Suggested subject','type':'request','due_date':'2026-11-01'}
    assert adapter.calls[1][1]['transient'] and adapter.calls[1][1]['actor_id']==u[0]['id']
    for table in ('document','document_sequence','document_job','document_event'):
        assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0
    with pytest.raises(ValueError):intake.preview(c,u[0],'https://other.example/file',adapter)
    with pytest.raises(RuntimeError):intake.preview(c,u[0],'https://drive.google.com/file/d/sourcefile123456/view',IntakeAdapter(True))
    assert not c.execute('SELECT 1 FROM document_sequence').fetchone()


def test_guided_intake_http_preview_failure_manual_entry_and_existing_scope(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    import documents_operations as operations
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    item=case(c,u[0],unit)
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        page=client.get('/documents/new')
        assert page.status_code==200 and 'Reference only' in page.text
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        payload={**intake_fields(unit),'intake':'guided','csrf':csrf,'direction':'OUT','priority':'urgent',
                 'subject':'My manually checked subject','drive_url':'https://drive.google.com/file/d/sourcefile123456/view'}
        monkeypatch.setattr(operations,'get_adapter',lambda:IntakeAdapter(True))
        failed=client.post('/documents/intake/preview',data=payload)
        assert failed.status_code==200 and 'continue manually' in failed.text
        assert 'My manually checked subject' in failed.text and 'value="OUT" selected' in failed.text
        assert not c.execute('SELECT 1 FROM document').fetchone()
        monkeypatch.setattr(operations,'get_adapter',lambda:IntakeAdapter())
        preview=client.post('/documents/intake/preview',data=payload)
        assert '&lt;script&gt;untrusted()&lt;/script&gt;' in preview.text
        assert '<script>untrusted()</script>' not in preview.text
        assert 'My manually checked subject' in preview.text
        assert client.post('/documents/intake/preview',data={**payload,'csrf':''}).status_code==403
        saved=client.post('/documents/new',data=payload,follow_redirects=False)
        assert saved.status_code==303 and saved.headers['location'].startswith('/documents/')
        doc=docs.raw(c,1)
        assert doc['subject']=='My manually checked subject' and doc['direction']=='OUT' and doc['priority']=='urgent'
        assert doc['due_date'] is None # preview didn't silently apply suggestion
        assert client.get(f"/documents/new?case_id={item['id']}").status_code==200
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert client.get(f"/documents/new?case_id={item['id']}").status_code==404


def test_deployment_includes_imported_work_modules():
    import ast
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'deploy_hf.py').read_text())
    runtime=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                 and any(isinstance(target,ast.Name) and target.id=='RUNTIME_PY' for target in node.targets))
    for file in runtime:
        source=root/file
        if not source.exists():continue
        for node in ast.walk(ast.parse(source.read_text())):
            names=[alias.name for alias in node.names] if isinstance(node,ast.Import) else ([node.module] if isinstance(node,ast.ImportFrom) else [])
            for name in names:
                if name and name.startswith('work') and (root/(name+'.py')).exists():
                    assert name+'.py' in runtime, f'{file} imports undeployed module {name}'

# P1.6 contextual actions and readable history.
def test_contextual_work_two_units_return_note_and_independent_progress(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    other=st.add_org_unit(c,'Evidence Division','division','WORK/D2')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-16')",(u[1]['id'],other));c.commit()
    item=inbox_case(c,u,unit)
    a=propose(c,u[0],item,unit,u[0]['id'],title='Compile service inputs')
    b=propose(c,u[0],item,other,u[3]['id'],title='Validate evidence sources')
    a=advance(c,u[1],a,'confirm',owner_id=u[0]['id'])
    b=advance(c,u[1],b,'confirm',owner_id=u[3]['id'])
    a=advance(c,u[0],a,'acknowledge');a=advance(c,u[0],a,'submit',submission='First evidence set')
    a=advance(c,u[2],a,'return',reason='Add the missing regional basis')
    a=advance(c,u[2],a,'milestone',due_date='2026-10-25')
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        page=client.get(f"/work/{item['id']}")
        assert page.status_code==200
        assert 'Your next actions' in page.text and 'Submit for review — Compile service inputs' in page.text
        assert '<strong>Changes requested:</strong> Add the missing regional basis' in page.text
        assert 'Required contributions still outstanding' in page.text and 'Validate evidence sources' in page.text
        assert 'First evidence set' in page.text and 'Contribution history' in page.text
        assert f'/tasks/{b["id"]}/acknowledge' not in page.text
        a=advance(c,u[0],a,'submit',submission='Revised regional basis')
        client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
        page=client.get(f"/work/{item['id']}")
        assert 'Review submitted contribution — Compile service inputs' in page.text
        assert f'/tasks/{a["id"]}/accept' in page.text and f'/tasks/{a["id"]}/return' in page.text
        a=advance(c,u[2],a,'accept')
        page=client.get(f"/work/{item['id']}")
        outstanding=page.text.split('Required contributions still outstanding:',1)[1].split('</ul>',1)[0]
        assert 'Compile service inputs' not in outstanding and 'Validate evidence sources' in outstanding
        assert '<strong>Changes requested:</strong>' not in page.text
        assert tasks.list_for_case(c,u[2],item['id'])[1]==b


def test_named_document_assignment_forms_enforce_scope_and_revision(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    doc=legacy_setup(c,u,unit)
    assignment=c.execute("SELECT id FROM document_assignment WHERE document_id=? AND role='contributor'",(doc['id'],)).fetchone()[0]
    url=f"/documents/{doc['id']}"
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[3]))
        page=client.get(url)
        assert page.status_code==200 and 'Technical input' in page.text
        assert 'name="assignment_id" type="number"' not in page.text and 'Assignment number' not in page.text
        assert f'name="assignment_id" value="{assignment}"' in page.text
        assert 'value="completed"' not in page.text
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        payload={'csrf':csrf,'revision':doc['revision'],'assignment_id':assignment,'status':'submitted','outcome':'Named form output'}
        response=client.post(url+'/contribution',data=payload,follow_redirects=False)
        assert response.status_code==303
        assert client.post(url+'/contribution',data=payload).status_code==409
        client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
        page=client.get(url)
        assert 'Confirm contribution complete' in page.text and 'Actor #' not in page.text
        assert 'Named form output' in page.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        page=client.get(url)
        assert f'name="assignment_id" value="{assignment}"' not in page.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
        page=client.get(url)
        assert 'Replace an existing assignment (optional)' in page.text
        assert '<select name="supersede_id">' in page.text and 'Replace assignment number' not in page.text


def test_contextual_actions_hide_blocked_and_inactive_owner_paths(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    doc=legacy_setup(c,u,unit);report=migrate(c,u,doc);cid=report['case_id']
    task=tasks.list_for_case(c,u[1],cid)[0]
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[3]['id'],));c.commit()
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
        page=client.get(f'/work/{cid}')
        assert page.status_code==200 and 'Choose an active staff account.' in page.text
        assert f'/tasks/{task["id"]}/acknowledge' not in page.text
        assert f'/tasks/{task["id"]}/reassign' in page.text
        c.execute("UPDATE document SET status='closed' WHERE id=?",(doc['id'],));c.commit()
        page=client.get(f'/work/{cid}')
        assert 'Reopen the official document' in page.text
        assert '/reassign' not in page.text and 'Propose a contribution' not in page.text
        assert 'Confirm lead</button>' not in page.text


# P2.1: discussion has its own immutable history and concurrency boundary.
import work_discussion as discussion


def test_discussion_two_contributors_and_independent_revisions(workspace):
    c, u, unit, _ = workspace
    doc = document(c, u[0], unit)
    item = case(c, u[0], unit, source_document_id=doc['id'])
    # Approved source state is deliberately fixed: informal discussion must not touch it.
    c.execute("UPDATE document SET status='approved' WHERE id=?", (doc['id'],));c.commit()
    task = propose(c, u[0], item, unit, u[0]['id'])
    task = advance(c, u[1], task, 'confirm', owner_id=u[0]['id'])
    before_doc = tuple(c.execute('SELECT * FROM document WHERE id=?', (doc['id'],)).fetchone())
    first = discussion.post(c, u[0], item['id'], 'Can we check these totals?', task['id'])
    reply = discussion.post(c, u[1], item['id'], 'Yes, the second row needs review.', task['id'], first)
    discussion.edit(c, u[0], item['id'], task['id'], first, 1, 'Please check the second row totals.')
    result = discussion.page(c, u[0], item['id'], task['id'])
    assert [m['id'] for m in result['messages']] == [first, reply]
    assert result['messages'][1]['parent']['id'] == first
    assert work.get(c, u[0], item['id'])['revision'] == item['revision']
    assert tuple(c.execute('SELECT * FROM document WHERE id=?', (doc['id'],)).fetchone()) == before_doc
    assert advance(c, u[0], task, 'acknowledge')['status'] == 'in_progress'
    current, history = discussion.history(c, u[1], item['id'], task['id'], first)
    assert current['revision'] == 2
    assert [r['body'] for r in history] == ['Please check the second row totals.', 'Can we check these totals?']
    with pytest.raises(docs.Conflict):
        discussion.edit(c, u[0], item['id'], task['id'], first, 1, 'Stale overwrite')


def test_discussion_thread_boundaries_and_author_only_edits(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    other = case(c, u[0], unit)
    a = propose(c, u[0], item, unit)
    b = propose(c, u[0], item, unit)
    cid = discussion.post(c, u[0], item['id'], 'Task A only', a['id'])
    for case_id, task_id in [(item['id'], None), (item['id'], b['id']), (other['id'], a['id'])]:
        with pytest.raises(permissions.Denied):
            discussion.post(c, u[0], case_id, 'Wrong thread', task_id, cid)
        with pytest.raises(permissions.Denied):
            discussion.history(c, u[0], case_id, task_id, cid)
    with pytest.raises(permissions.Denied):
        discussion.edit(c, u[1], item['id'], a['id'], cid, 1, 'Officer overwrite')
    assert c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == 1


def test_discussion_revocation_and_disabled_writes(workspace):
    c, u, unit, _ = workspace
    doc = document(c, u[0], unit)
    item = case(c, u[0], unit, source_document_id=doc['id'])
    cid = discussion.post(c, u[0], item['id'], 'Restricted discussion')
    docs.mutate(c, u[1], doc['id'], doc['revision'], 'access',
                {'visibility':'restricted', 'viewers':[u[0]['id']], 'reason':'Restrict discussion source'})
    c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?', (doc['id'], u[1]['id']));c.commit()
    for user in (u[1], u[4], {**u[3], 'role':'admin'}):
        with pytest.raises(permissions.Denied):
            discussion.page(c, user, item['id'])
    for key in ('work.enabled', 'documents.enabled'):
        st.set_setting(c, key, '0')
        assert discussion.page(c, u[0], item['id'])['messages']
        with pytest.raises(ValueError, match='not enabled'):
            discussion.post(c, u[0], item['id'], 'Disabled')
        with pytest.raises(ValueError, match='not enabled'):
            discussion.edit(c, u[0], item['id'], None, cid, 1, 'Disabled')
        st.set_setting(c, key, '1')
    c.execute('DELETE FROM document_access WHERE document_id=? AND user_id=?', (doc['id'], u[0]['id']));c.commit()
    for operation in (lambda: discussion.page(c,u[0],item['id']),
                      lambda: discussion.history(c,u[0],item['id'],None,cid),
                      lambda: discussion.edit(c,u[0],item['id'],None,cid,1,'Revoked'),
                      lambda: discussion.post(c,u[0],item['id'],'Revoked')):
        with pytest.raises(permissions.Denied):
            operation()


def test_discussion_pagination_and_immutable_history(workspace):
    c, u, unit, _ = workspace
    item = case(c, u[0], unit)
    ids = [discussion.post(c,u[0],item['id'],f'Message {n}') for n in range(32)]
    latest = discussion.page(c,u[0],item['id'])
    older = discussion.page(c,u[0],item['id'],before=latest['older'])
    assert [m['id'] for m in older['messages'] + latest['messages']] == ids
    assert older['older'] is None
    assert discussion.page(c,u[0],item['id'],focus=ids[0])['messages'][0]['id'] == ids[0]
    st.init_db(c)
    for table in ('work_comment', 'work_comment_revision'):
        with pytest.raises(sqlite3.IntegrityError, match='append-only'):
            c.execute('DELETE FROM ' + table)
        c.rollback()
    for body in (' ', 'x'*4001):
        with pytest.raises(ValueError):
            discussion.post(c,u[0],item['id'],body)
    assert c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == 32


def test_discussion_concurrent_edits_preserve_one_winner(workspace):
    from concurrent.futures import ThreadPoolExecutor
    c,u,unit,path = workspace
    item = case(c,u[0],unit)
    cid = discussion.post(c,u[0],item['id'],'Original')
    def edit(body):
        conn=st.connect(path)
        try:
            discussion.edit(conn,u[0],item['id'],None,cid,1,body)
            return 'saved'
        except docs.Conflict:
            return 'conflict'
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(edit,['First edit','Second edit'])) == ['conflict','saved']
    assert len(discussion.history(c,u[0],item['id'],None,cid)[1]) == 2


def test_discussion_http_csrf_reply_edit_and_escape(workspace, app_mod, monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path = workspace
    item = case(c,u[0],unit)
    monkeypatch.setattr(app_mod,'DB',path)
    url=f"/work/{item['id']}/discussion"
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        page=client.get(url)
        assert page.status_code==200
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        fields={'action':'post','body':'<script>unsafe()</script>'}
        assert client.post(url+'/messages',data=fields).status_code==403
        posted=client.post(url+'/messages',data={**fields,'csrf':csrf})
        assert posted.status_code==200
        assert '&lt;script&gt;unsafe()&lt;/script&gt;' in posted.text
        assert '<script>unsafe()</script>' not in posted.text
        cid=c.execute('SELECT id FROM work_comment').fetchone()[0]
        reply=client.post(url+'/messages?reply='+str(cid),data={'action':'post','body':'A reply','csrf':csrf,'parent_id':cid})
        assert 'A reply' in reply.text
        target=url+'/messages?message='+str(cid)
        edit={'action':'edit','comment_id':cid,'revision':1,'body':'Corrected text','csrf':csrf}
        assert client.post(target,data=edit).status_code==200
        stale=client.post(target,data={**edit,'body':'Keep my unsaved draft'})
        assert stale.status_code==409
        assert 'Keep my unsaved draft' in stale.text and 'Corrected text' in stale.text
        history=client.get(url+'?message='+str(cid))
        assert 'Original message' in history.text and 'Corrected text' in history.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert client.get(url).status_code==404


def test_discussion_history_paging_and_atomic_post(workspace):
    c,u,unit,_ = workspace
    item=case(c,u[0],unit)
    cid=discussion.post(c,u[0],item['id'],'Original')
    for revision in range(1,33):
        discussion.edit(c,u[0],item['id'],None,cid,revision,f'Edit {revision}')
    _,latest=discussion.history(c,u[0],item['id'],None,cid)
    _,older=discussion.history(c,u[0],item['id'],None,cid,before=latest[29]['revision'])
    assert [r['revision'] for r in latest[:30]+older] == list(range(33,0,-1))
    c.execute("CREATE TRIGGER fail_discussion BEFORE INSERT ON work_comment_revision BEGIN SELECT RAISE(ABORT,'write failed'); END;")
    c.commit()
    with pytest.raises(sqlite3.IntegrityError):
        discussion.post(c,u[0],item['id'],'Must roll back')
    assert c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0] == 1
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    with pytest.raises(permissions.Denied):
        discussion.history(c,u[0],item['id'],None,cid)


# P2.2: targeted updates never create access and are delivered through current ACLs.
import work_updates as updates


def test_updates_mentions_followers_replies_deduplicate(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    item=work.confirm_lead(c,u[1],item['id'],1,u[2]['id'],'Confirmed')
    updates.follow(c,u[1],item['id'])
    updates.follow(c,u[1],item['id'])
    parent=discussion.post(c,u[1],item['id'],'Please check')
    cid=discussion.post(c,u[0],item['id'],'Checked',parent_id=parent,mentions=[u[1]['id'],u[1]['id'],u[0]['id']])
    assert c.execute('SELECT COUNT(*) FROM work_notice WHERE comment_id=?',(cid,)).fetchone()[0]==1
    assert updates.inbox(c,u[1])[0][0]['reason']=='mention'
    assert not updates.inbox(c,u[0])[0]  # no self notification
    discussion.edit(c,u[0],item['id'],None,cid,1,'Checked again',mentions=[u[1]['id'],u[2]['id']])
    assert len(updates.inbox(c,u[1])[0])==1
    assert len(updates.inbox(c,u[2])[0])==1
    assert [m['user_id'] for m in updates.mentions(c,cid,1)]==[u[0]['id'],u[1]['id']]
    assert [m['user_id'] for m in updates.mentions(c,cid,2)]==[u[1]['id'],u[2]['id']]
    st.init_db(c)
    assert len(updates.inbox(c,u[1])[0])==1


def test_updates_follow_scope_unfollow_and_read_revision(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    a=propose(c,u[0],item,unit)
    b=propose(c,u[0],item,unit)
    updates.follow(c,u[1],item['id'],a['id'])
    discussion.post(c,u[0],item['id'],'Case-wide')
    discussion.post(c,u[0],item['id'],'Other task',b['id'])
    cid=discussion.post(c,u[0],item['id'],'Followed task',a['id'])
    assert [n['comment_id'] for n in updates.inbox(c,u[1])[0]]==[cid]
    discussion.edit(c,u[0],item['id'],a['id'],cid,1,'Edited while viewing')
    updates.mark_read(c,u[1],item['id'],a['id'],[[cid,1]])
    assert updates.read_revision(c,u[1]['id'],cid)==1  # concurrent edit stays unread in thread
    assert not updates.inbox(c,u[1])[0]  # original targeted alert acknowledged
    updates.mark_read(c,u[1],item['id'],a['id'],[[cid,2]])
    updates.mark_read(c,u[1],item['id'],a['id'],[[cid,1]])
    assert updates.read_revision(c,u[1]['id'],cid)==2
    updates.follow(c,u[1],item['id'],a['id'],False)
    discussion.post(c,u[0],item['id'],'After unfollow',a['id'])
    assert not updates.inbox(c,u[1])[0]
    updates.follow(c,u[1],item['id'])
    discussion.post(c,u[0],item['id'],'Case follow includes other tasks',b['id'])
    assert len(updates.inbox(c,u[1])[0])==1


def test_updates_revoked_access_never_delivers_or_mentions(workspace):
    c,u,unit,_=workspace
    doc=document(c,u[0],unit)
    item=case(c,u[0],unit,source_document_id=doc['id'])
    updates.follow(c,u[0],item['id'])
    cid=discussion.post(c,u[1],item['id'],'Restricted later',mentions=[u[0]['id']])
    assert updates.bell_rows(c,u[0])
    before=c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0]
    with pytest.raises(ValueError,match='no longer has access'):
        discussion.post(c,u[0],item['id'],'Mention cannot grant access',mentions=[u[4]['id']])
    assert c.execute('SELECT COUNT(*) FROM work_comment').fetchone()[0]==before
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restricted'})
    assert not updates.inbox(c,u[0])[0]
    assert not updates.bell_rows(c,u[0])
    assert u[0]['id'] not in [p['id'] for p in updates.candidates(c,u[1],item['id'])]
    discussion.post(c,u[1],item['id'],'No delivery to revoked follower')
    assert c.execute('SELECT COUNT(*) FROM work_notice WHERE user_id=?',(u[0]['id'],)).fetchone()[0]==1
    with pytest.raises(permissions.Denied):
        updates.mark_read(c,u[0],item['id'],None,[[cid,1]])
    with pytest.raises(permissions.Denied):
        updates.follow(c,u[0],item['id'])


def test_updates_read_scope_atomicity_and_disabled_preferences(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    task=propose(c,u[0],item,unit)
    cid=discussion.post(c,u[1],item['id'],'Case message',mentions=[u[0]['id']])
    other=discussion.post(c,u[1],item['id'],'Task message',task['id'])
    with pytest.raises(permissions.Denied):
        updates.mark_read(c,u[0],item['id'],None,[[cid,1],[other,1]])
    assert updates.read_revision(c,u[0]['id'],cid)==0
    with pytest.raises(ValueError):
        updates.mark_read(c,u[0],item['id'],None,[[cid,2]])
    st.set_setting(c,'work.enabled','0')
    with pytest.raises(ValueError):
        updates.follow(c,u[0],item['id'])
    updates.mark_read(c,u[0],item['id'],None,[[cid,1]])
    assert not updates.inbox(c,u[0])[0]
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    with pytest.raises(permissions.Denied):
        updates.inbox(c,u[0])


def test_updates_atomic_notice_failure_and_scan_pagination(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    updates.follow(c,u[1],item['id'])
    c.execute("CREATE TRIGGER fail_notice BEFORE INSERT ON work_notice BEGIN SELECT RAISE(ABORT,'notice failed'); END;");c.commit()
    with pytest.raises(sqlite3.IntegrityError):
        discussion.post(c,u[0],item['id'],'Must roll back')
    assert not c.execute('SELECT 1 FROM work_comment').fetchone()
    c.execute('DROP TRIGGER fail_notice');c.commit()
    ids=[discussion.post(c,u[0],item['id'],f'Update {n}') for n in range(28)]
    first,cursor=updates.inbox(c,u[1]);second,_=updates.inbox(c,u[1],cursor)
    assert [n['comment_id'] for n in first+second]==list(reversed(ids))


def test_updates_http_mentions_unread_csrf_and_no_get_mutation(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace
    item=case(c,u[0],unit)
    monkeypatch.setattr(app_mod,'DB',path)
    url=f"/work/{item['id']}/discussion"
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        page=client.get(url)
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        assert client.post(url+'/preferences',data={'action':'follow'}).status_code==403
        assert client.post(url+'/preferences',data={'action':'follow','csrf':csrf}).status_code==200
        posted=client.post(url+'/messages',data={'action':'post','csrf':csrf,'body':'Please review','mentions':str(u[1]['id'])})
        assert posted.status_code==200 and 'Mentioned:' in posted.text
        cid=c.execute('SELECT id FROM work_comment').fetchone()[0]
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
        inbox=client.get('/work/updates')
        assert inbox.status_code==200 and 'Mentioned you' in inbox.text
        page=client.get(url)
        assert 'Unread</span>' in page.text
        assert updates.read_revision(c,u[1]['id'],cid)==0
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        result=client.post(url+'/preferences',data={'action':'read','csrf':csrf,'observed':json.dumps([[cid,1]])})
        assert result.status_code==200
        assert 'No unread updates in this page.' in client.get('/work/updates').text


def test_updates_revoked_page_does_not_hide_older_permitted_alert(workspace):
    c,u,unit,_=workspace
    visible=case(c,u[0],unit)
    wanted=discussion.post(c,u[1],visible['id'],'Still permitted',mentions=[u[0]['id']])
    doc=document(c,u[0],unit)
    hidden=case(c,u[0],unit,source_document_id=doc['id'])
    updates.follow(c,u[0],hidden['id'])
    for n in range(251):
        discussion.post(c,u[1],hidden['id'],f'Now restricted {n}')
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
    first,cursor=updates.inbox(c,u[0])
    assert not first and cursor
    second,_=updates.inbox(c,u[0],cursor)
    assert [n['comment_id'] for n in second]==[wanted]
    assert updates.bell_rows(c,u[0])


# P2.3: blockers and same-case dependencies preserve deadlines and authority.
import work_blockers as blockers
import work_inbox


def change_block(c,user,task,action,**fields):
    return blockers.mutate(c,user,task['case_id'],task['id'],task['revision'],action,
                           {'reason':'Recorded blocker decision',**fields})


def test_blocker_owner_date_gate_and_unchanged_deadlines(workspace):
    c,u,unit,_=workspace
    doc=document(c,u[0],unit)
    item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[0]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    task=advance(c,u[0],task,'acknowledge')
    before_doc=tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())
    task=change_block(c,u[0],task,'block',reason='Waiting for regional totals',followup_owner_id=u[0]['id'],followup_date='2026-10-20')
    assert task['status']=='in_progress' and task['due_date'] is None
    with pytest.raises(ValueError,match='Resolve'):
        advance(c,u[0],task,'submit',submission='Premature')
    entries,_=work_inbox.page(c,u[0])
    assert entries[0]['action']=='Follow up on blocker'
    assert entries[0]['followup_date']=='2026-10-20'
    assert tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())==before_doc
    assert work.get(c,u[0],item['id'])['revision']==item['revision']
    blocked_revision=task['revision']
    task=change_block(c,u[0],task,'unblock',reason='Regional totals received')
    with pytest.raises(docs.Conflict):
        blockers.mutate(c,u[0],item['id'],task['id'],blocked_revision,'block',{'reason':'Stale','followup_owner_id':u[0]['id'],'followup_date':'2026-10-21'})
    task=advance(c,u[0],task,'submit',submission='Validated totals')
    assert task['status']=='for_review'
    history=json.loads(c.execute("SELECT detail_json FROM work_event WHERE action='task_unblock'").fetchone()[0])
    assert history['previous_blocker']=='Waiting for regional totals'


def test_dependency_cycles_cross_case_and_completion_gate(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    task=[]
    for _ in range(3):
        t=propose(c,u[0],item,unit,u[0]['id']);t=advance(c,u[1],t,'confirm',owner_id=u[0]['id'])
        task.append(advance(c,u[0],t,'acknowledge'))
    a,b,d=task
    a=change_block(c,u[1],a,'dependency_add',prerequisite_id=b['id'])
    b=change_block(c,u[1],b,'dependency_add',prerequisite_id=d['id'])
    with pytest.raises(ValueError,match='cycle'):
        change_block(c,u[1],d,'dependency_add',prerequisite_id=a['id'])
    with pytest.raises(ValueError):
        change_block(c,u[1],a,'dependency_add',prerequisite_id=a['id'])
    other=case(c,u[0],unit);outside=propose(c,u[0],other,unit)
    with pytest.raises(ValueError):
        change_block(c,u[1],a,'dependency_add',prerequisite_id=outside['id'])
    with pytest.raises(ValueError,match='Resolve'):
        advance(c,u[0],a,'submit',submission='Too soon')
    d=advance(c,u[0],d,'submit',submission='Upstream input')
    d=advance(c,u[1],d,'accept')
    b=advance(c,u[0],b,'submit',submission='Middle input')
    b=advance(c,u[1],b,'accept')
    a=advance(c,u[0],a,'submit',submission='Combined input')
    # Upstream reopened while A awaits review: current prerequisites checked at acceptance.
    b=advance(c,u[1],b,'reopen')
    with pytest.raises(ValueError,match='Resolve'):
        advance(c,u[1],a,'accept')
    b=advance(c,u[1],b,'cancel')
    assert blockers.waiting(c,a)  # cancelled prerequisite is not implicitly satisfied
    a=change_block(c,u[1],a,'dependency_remove',prerequisite_id=b['id'],reason='Requirement explicitly withdrawn')
    assert advance(c,u[1],a,'accept')['status']=='done'


def test_blocker_authority_followup_membership_and_revocation(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    item=work.confirm_lead(c,u[1],item['id'],1,u[2]['id'],'Lead confirmed')
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    with pytest.raises(permissions.Denied):
        change_block(c,u[4],task,'block',followup_owner_id=u[4]['id'],followup_date='2026-10-20')
    with pytest.raises(permissions.Denied):
        change_block(c,u[0],task,'block',followup_owner_id=u[2]['id'],followup_date='2026-10-20')
    with pytest.raises(permissions.Denied):
        change_block(c,u[2],task,'block',followup_owner_id=u[3]['id'],followup_date='2026-10-20')
    task=change_block(c,u[2],task,'block',followup_owner_id=u[1]['id'],followup_date='2026-10-20')
    entries,_=work_inbox.page(c,u[1]);assert any(e['action']=='Follow up on blocker' for e in entries)
    st.set_setting(c,'work.enabled','0')
    with pytest.raises(ValueError,match='not enabled'):
        change_block(c,u[1],task,'unblock')
    st.set_setting(c,'work.enabled','1')
    c.execute("UPDATE document_role_grant SET revoked_at='2026-10-16' WHERE user_id=?",(u[1]['id'],));c.commit()
    with pytest.raises(permissions.Denied):
        change_block(c,u[1],task,'unblock')
    assert not work_inbox.page(c,u[1])[0]
    task=change_block(c,u[2],task,'block',followup_owner_id=u[2]['id'],followup_date='2026-10-21')
    assert change_block(c,u[2],task,'unblock')['blocker_reason']==''


def test_dependency_concurrent_opposite_links_and_audit_rollback(workspace,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    c,u,unit,path=workspace
    item=case(c,u[0],unit);a=propose(c,u[0],item,unit);b=propose(c,u[0],item,unit)
    def link(pair):
        conn=st.connect(path)
        try:
            change_block(conn,u[1],pair[0],'dependency_add',prerequisite_id=pair[1]['id'])
            return 'saved'
        except ValueError:
            return 'cycle'
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(link,[(a,b),(b,a)]))==['cycle','saved']
    assert c.execute('SELECT COUNT(*) FROM work_dependency').fetchone()[0]==1
    task=propose(c,u[0],item,unit)
    def fail(*args,**kwargs): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(work,'_event',fail)
    with pytest.raises(RuntimeError):
        change_block(c,u[1],task,'block',followup_owner_id=u[1]['id'],followup_date='2026-10-20')
    stored=c.execute('SELECT blocker_reason,revision FROM work_task WHERE id=?',(task['id'],)).fetchone()
    assert stored==('',1)
    st.init_db(c)
    assert c.execute('SELECT COUNT(*) FROM work_dependency').fetchone()[0]==1


def test_blocker_http_forms_csrf_history_and_source_visibility(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace
    doc=document(c,u[0],unit);item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    monkeypatch.setattr(app_mod,'DB',path)
    url=f"/work/{item['id']}";target=url+f"/tasks/{task['id']}/block"
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        page=client.get(url);assert 'Report a blocker' in page.text
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        form={'revision':task['revision'],'reason':'<script>Need totals</script>','followup_owner_id':u[0]['id'],'followup_date':'2026-10-20'}
        assert client.post(target,data=form).status_code==403
        result=client.post(target,data={**form,'csrf':csrf})
        assert result.status_code==200 and 'Blocker recorded or updated' in result.text
        assert '&lt;script&gt;Need totals&lt;/script&gt;' in result.text
        assert '<script>Need totals</script>' not in result.text
        assert client.post(target,data={**form,'csrf':csrf}).status_code==409
        docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
        assert client.get(url).status_code==404
        assert client.post(target,data={**form,'csrf':csrf}).status_code==403


# P2.4: discussion-derived proposals and decisions retain exact source/affected-work evidence.
import work_decisions as decisions


def decision_fields(c,task_list,**extra):
    return {'kind':'change','body':'Use the revised regional breakdown.','affected_tasks':[str(t['id']) for t in task_list],
            'task_revisions':{str(t['id']):c.execute('SELECT revision FROM work_task WHERE id=?',(t['id'],)).fetchone()[0] for t in task_list},**extra}


def test_message_proposal_exact_source_duplicate_and_no_authority_grant(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    cid=discussion.post(c,u[0],item['id'],'Please prepare a regional breakdown.')
    fields={'title':'Regional breakdown','expected_output':'Validated table','unit_id':unit,'proposed_owner_id':u[3]['id']}
    task=decisions.propose(c,u[0],item['id'],cid,1,fields)
    assert task['status']=='proposed' and task['owner_id'] is None
    with pytest.raises(permissions.Denied):work.get(c,u[3],item['id'])
    with pytest.raises(docs.Conflict):decisions.propose(c,u[0],item['id'],cid,1,fields)
    discussion.edit(c,u[0],item['id'],None,cid,1,'Changed request later.')
    source=decisions.task_source(c,u[0],item['id'],task['id'])
    assert source['source_revision']==1 and source['body']=='Please prepare a regional breakdown.'
    stale=discussion.post(c,u[0],item['id'],'First draft')
    discussion.edit(c,u[0],item['id'],None,stale,1,'Latest draft')
    with pytest.raises(docs.Conflict):decisions.propose(c,u[0],item['id'],stale,1,fields)
    assert c.execute('SELECT COUNT(*) FROM work_task').fetchone()[0]==1


def test_changed_direction_preserves_acceptance_and_requires_explicit_review(workspace):
    c,u,unit,_=workspace
    doc=document(c,u[0],unit)
    item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    task=advance(c,u[0],task,'acknowledge');task=advance(c,u[0],task,'submit',submission='Original accepted regional totals')
    task=advance(c,u[1],task,'accept')
    before=tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())
    cid=discussion.post(c,u[0],item['id'],'Director requests a new regional grouping.')
    did=decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task],document_id=doc['id'],document_revisions={str(doc['id']):doc['revision']}))
    _,decision,affected=decisions.detail(c,u[0],item['id'],did)
    assert affected[0]['status']=='done' and affected[0]['snapshot']['submission']=='Original accepted regional totals'
    assert affected[0]['revision']==task['revision']+1
    assert decision['document_revision']==doc['revision']
    assert tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())==before
    for user in (u[0],u[1]):
        assert any(e['action']=='Review changed work direction' for e in work_inbox.page(c,user)[0])
    with pytest.raises(permissions.Denied):
        decisions.resolve(c,u[0],item['id'],did,task['id'],affected[0]['revision'],'retain','Self acceptance')
    decisions.resolve(c,u[1],item['id'],did,task['id'],affected[0]['revision'],'revise','Rework the grouping; preserve the original totals.')
    _,_,updated=decisions.detail(c,u[0],item['id'],did)
    assert updated[0]['status']=='in_progress'
    assert updated[0]['submission']=='Original accepted regional totals'
    assert updated[0]['snapshot']['status']=='done'
    assert not decisions.pending(c,task['id'])
    assert tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())==before
    with pytest.raises(docs.Conflict):
        decisions.resolve(c,u[1],item['id'],did,task['id'],updated[0]['revision'],'retain','Duplicate')


def test_decision_gates_submission_retains_output_and_old_forms_are_stale(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id']);task=advance(c,u[0],task,'acknowledge')
    cid=discussion.post(c,u[0],item['id'],'Revise the scope')
    did=decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task]))
    with pytest.raises(docs.Conflict):advance(c,u[0],task,'submit',submission='Stale submission')
    current=tasks.list_for_case(c,u[0],item['id'])[0]
    with pytest.raises(ValueError,match='changed-decision'):
        advance(c,u[0],current,'submit',submission='Not reviewed')
    decisions.resolve(c,u[1],item['id'],did,task['id'],current['revision'],'retain','The current scope already meets the changed instruction.')
    current=tasks.list_for_case(c,u[0],item['id'])[0]
    assert advance(c,u[0],current,'submit',submission='Reviewed scope')['status']=='for_review'


def test_decision_supersession_keeps_all_affected_work_and_stale_sources(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit);a=propose(c,u[0],item,unit);b=propose(c,u[0],item,unit)
    first=discussion.post(c,u[0],item['id'],'First direction')
    old=decisions.record(c,u[1],item['id'],first,1,decision_fields(c,[a,b]))
    second=discussion.post(c,u[0],item['id'],'Replacement direction')
    with pytest.raises(ValueError,match='every contribution'):
        decisions.record(c,u[1],item['id'],second,1,decision_fields(c,[a],supersedes_id=old))
    with pytest.raises(ValueError,match='Replacing'):
        decisions.record(c,u[1],item['id'],second,1,decision_fields(c,[a,b],kind='coordination',supersedes_id=old))
    new=decisions.record(c,u[1],item['id'],second,1,decision_fields(c,[a,b],supersedes_id=old))
    assert [d['id'] for d in decisions.pending(c,a['id'])]==[new]
    assert decisions.detail(c,u[0],item['id'],old)[1]['successor_id']==new
    with pytest.raises(docs.Conflict):decisions.resolve(c,u[1],item['id'],old,a['id'],3,'retain','Old review')
    third=discussion.post(c,u[0],item['id'],'Another direction')
    with pytest.raises(docs.Conflict):decisions.record(c,u[1],item['id'],third,1,decision_fields(c,[a,b],supersedes_id=old))
    discussion.edit(c,u[0],item['id'],None,second,1,'Edited replacement text')
    assert decisions.detail(c,u[0],item['id'],new)[1]['source_body']=='Replacement direction'


def test_decision_authority_scope_read_revocation_and_immutable_history(workspace):
    c,u,unit,_=workspace
    doc=document(c,u[0],unit);item=case(c,u[0],unit,source_document_id=doc['id']);task=propose(c,u[0],item,unit)
    cid=discussion.post(c,u[0],item['id'],'Discuss this')
    for user in (u[0],u[4]):
        with pytest.raises(permissions.Denied):decisions.record(c,user,item['id'],cid,1,decision_fields(c,[task]))
    other=case(c,u[0],unit);outside=propose(c,u[0],other,unit)
    with pytest.raises(ValueError):decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[outside]))
    did=decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task],kind='coordination'))
    assert not decisions.pending(c,task['id']) and tasks.list_for_case(c,u[0],item['id'])[0]['revision']==1
    with pytest.raises(docs.Conflict):decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task]))
    st.init_db(c)
    for table in ('work_decision','work_decision_task'):
        with pytest.raises(sqlite3.IntegrityError,match='append-only'):c.execute('DELETE FROM '+table)
        c.rollback()
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
    with pytest.raises(permissions.Denied):decisions.detail(c,u[0],item['id'],did)
    with pytest.raises(permissions.Denied):decisions.propose(c,u[0],item['id'],cid,1,{'title':'Bypass','expected_output':'Bypass'})


def test_decision_atomic_audit_failure_and_revision_checks(workspace,monkeypatch):
    c,u,unit,_=workspace
    item=case(c,u[0],unit);task=propose(c,u[0],item,unit);cid=discussion.post(c,u[0],item['id'],'Source')
    fields=decision_fields(c,[task]);fields['task_revisions'][str(task['id'])]=0
    with pytest.raises(docs.Conflict):decisions.record(c,u[1],item['id'],cid,1,fields)
    def fail(*args,**kwargs):raise RuntimeError('audit unavailable')
    monkeypatch.setattr(work,'_event',fail)
    with pytest.raises(RuntimeError):decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task]))
    assert not c.execute('SELECT 1 FROM work_decision').fetchone()
    assert c.execute('SELECT revision FROM work_task WHERE id=?',(task['id'],)).fetchone()[0]==1
    with pytest.raises(RuntimeError):decisions.propose(c,u[0],item['id'],cid,1,{'title':'Proposal','expected_output':'Output','unit_id':unit})
    assert c.execute('SELECT COUNT(*) FROM work_task').fetchone()[0]==1
    assert not c.execute('SELECT 1 FROM work_task_source').fetchone()


def test_decision_http_source_forms_csrf_and_review(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    import html
    c,u,unit,path=workspace;item=case(c,u[0],unit)
    cid=discussion.post(c,u[0],item['id'],'A <script>source</script> request')
    monkeypatch.setattr(app_mod,'DB',path)
    url=f"/work/{item['id']}/messages/{cid}/actions"
    def hidden(page,name):return html.unescape(re.search('name="'+name+'" value="([^"]*)"',page.text)[1])
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]));page=client.get(url)
        assert page.status_code==200 and '&lt;script&gt;source&lt;/script&gt;' in page.text
        assert 'Record work decision</button>' not in page.text
        data={'action':'task','source_revision':1,'title':'Derived task','expected_output':'Supported output','unit_id':unit}
        assert client.post(url,data=data).status_code==403
        result=client.post(url,data={**data,'csrf':hidden(page,'csrf')})
        assert result.status_code==200 and 'Proposed from a discussion message' in result.text
        task=tasks.list_for_case(c,u[0],item['id'])[0]
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]));page=client.get(url)
        data={k:hidden(page,k) for k in ('csrf','source_revision','task_revisions','document_revisions')}
        result=client.post(url,data={**data,'action':'decision','kind':'change','body':'Use the revised grouping','affected_tasks':str(task['id'])})
        assert result.status_code==200 and 'Needs review against the changed direction' in result.text
        did=c.execute('SELECT id FROM work_decision').fetchone()[0]
        target=f"/work/{item['id']}/decisions/{did}/resolve"
        review={'csrf':hidden(result,'csrf'),'task_id':task['id'],'revision':2,'outcome':'retain','reason':'Already covered by expected output.'}
        assert client.post(target,data=review).status_code==200
        assert client.post(target,data=review).status_code==409
        assert client.get(f"/work/{item['id']}/decisions").status_code==200
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert client.get(url).status_code==404
        assert client.get(f"/work/{item['id']}/decisions/{did}").status_code==404


def test_decision_concurrent_proposals_and_disabled_changes(workspace):
    from concurrent.futures import ThreadPoolExecutor
    c,u,unit,path=workspace;item=case(c,u[0],unit);cid=discussion.post(c,u[0],item['id'],'One source')
    fields={'title':'One contribution','expected_output':'Output','unit_id':unit}
    def create(_):
        conn=st.connect(path)
        try:
            decisions.propose(conn,u[0],item['id'],cid,1,fields)
            return 'created'
        except docs.Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create,range(2)))==['conflict','created']
    task=tasks.list_for_case(c,u[0],item['id'])[0]
    did=decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task]))
    st.set_setting(c,'work.enabled','0')
    assert decisions.detail(c,u[0],item['id'],did)[1]['body']
    with pytest.raises(ValueError,match='not enabled'):decisions.resolve(c,u[1],item['id'],did,task['id'],2,'retain','Reviewed')
    with pytest.raises(ValueError,match='not enabled'):decisions.record(c,u[1],item['id'],cid,1,decision_fields(c,[task]))
    with pytest.raises(ValueError,match='not enabled'):decisions.propose(c,u[0],item['id'],cid,1,fields)


def test_decision_document_reference_version_and_stale_review(workspace):
    c,u,unit,_=workspace;doc=document(c,u[0],unit);item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit);cid=discussion.post(c,u[0],item['id'],'Approved source context')
    version=c.execute("INSERT INTO document_file_version(document_id,url,file_id,fingerprint,role,actor_id,created_at) VALUES (?,?,?,?,?,?,?)",(doc['id'],'https://docs.google.com/document/d/synthetic/edit','synthetic','synthetic-fingerprint','source',u[0]['id'],'2026-10-16')).lastrowid
    c.execute("UPDATE document SET current_version=?,approved_version=?,status='approved' WHERE id=?",(version,version,doc['id']));c.commit()
    fields=decision_fields(c,[task],document_id=doc['id'],document_revisions={str(doc['id']):doc['revision']-1})
    with pytest.raises(docs.Conflict):decisions.record(c,u[1],item['id'],cid,1,fields)
    fields['document_revisions'][str(doc['id'])]=doc['revision']
    did=decisions.record(c,u[1],item['id'],cid,1,fields)
    assert decisions.detail(c,u[0],item['id'],did)[1]['document_version_id']==version
    current=tasks.list_for_case(c,u[0],item['id'])[0]
    current=advance(c,u[1],current,'confirm',owner_id=u[0]['id'])
    with pytest.raises(docs.Conflict):decisions.resolve(c,u[1],item['id'],did,task['id'],2,'retain','Stale review')
    decisions.resolve(c,u[1],item['id'],did,task['id'],current['revision'],'retain','Scope still applies.')
    assert c.execute('SELECT status,approved_version,current_version FROM document WHERE id=?',(doc['id'],)).fetchone()==('approved',version,version)


# P2.5: draft pointers and contribution notes never imply Drive or approval authority.
import work_handoff as handoff

DRAFT_URL='https://docs.google.com/document/d/synthetic_draft_123/edit'
SHEET_URL='https://docs.google.com/spreadsheets/d/synthetic_sheet_456/edit'
SUPPORT_URL='https://drive.google.com/file/d/synthetic_support_789/view'


def test_handoff_retains_draft_support_and_task_snapshot_without_state_changes(workspace):
    c,u,unit,_=workspace;doc=document(c,u[0],unit);item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    draft=handoff.set_draft(c,u[0],item['id'],0,{'title':'Response draft','url':DRAFT_URL,'reason':'Start consolidation'})
    support=handoff.add_file(c,u[0],item['id'],{'title':'Evidence table','url':SUPPORT_URL})
    before_doc=tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())
    before_task=tuple(c.execute('SELECT * FROM work_task WHERE id=?',(task['id'],)).fetchone())
    hid=handoff.post(c,u[0],item['id'],task['id'],task['revision'],draft,'Insert totals into section two.',support)
    newdraft=handoff.set_draft(c,u[1],item['id'],draft,{'title':'Calculation sheet','url':SHEET_URL,'reason':'Changed consolidation format'})
    handoff.retire_file(c,u[0],item['id'],support,'Superseded evidence list')
    page=handoff.page(c,u[0],item['id']);note=page['notes'][0]
    assert note['id']==hid and note['draft_id']==draft and note['draft_url']==DRAFT_URL
    assert note['support_url']==SUPPORT_URL and note['snapshot']['status']=='todo'
    assert page['draft']['id']==newdraft and not page['support_files']
    assert page['archived_files'][0]['title']=='Evidence table'
    assert tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())==before_doc
    assert tuple(c.execute('SELECT * FROM work_task WHERE id=?',(task['id'],)).fetchone())==before_task
    assert work.get(c,u[0],item['id'])['revision']==item['revision']


@pytest.mark.parametrize('url', ['javascript:alert(1)','https://evil.test/document/d/synthetic_draft_123/edit',
    'https://docs.google.com@evil.test/document/d/synthetic_draft_123/edit',
    'https://user:pass@docs.google.com/document/d/synthetic_draft_123/edit',
    'http://docs.google.com/document/d/synthetic_draft_123/edit',
    'https://docs.google.com:invalid/document/d/synthetic_draft_123/edit',
    'https://drive.google.com/drive/folders/synthetic_draft_123',
    'https://docs.google.com/document/d/short/edit'])
def test_handoff_rejects_unsafe_or_nonfile_urls(url):
    with pytest.raises(ValueError):handoff.link(url)


def test_handoff_canonical_google_links_resource_keys_and_draft_types():
    url,fid,kind=handoff.link(DRAFT_URL+'?utm_source=other&resourcekey=0-share_key#heading=x',draft=True)
    assert url==DRAFT_URL+'?resourcekey=0-share_key' and kind=='Docs'
    assert handoff.link(SHEET_URL,draft=True)[2]=='Sheets'
    assert handoff.link('https://drive.google.com/open?id=synthetic_support_789')[0]==SUPPORT_URL
    with pytest.raises(ValueError):handoff.link(SUPPORT_URL,draft=True)
    with pytest.raises(ValueError):handoff.link(DRAFT_URL+'?resourcekey=invalid%20key')


def test_handoff_authority_cross_case_and_revoked_source_access(workspace):
    c,u,unit,_=workspace;doc=document(c,u[0],unit);item=case(c,u[0],unit,source_document_id=doc['id'])
    doc=docs.mutate(c,u[1],doc['id'],doc['revision'],'verify',{'verification':'verified','reason':'Checked'})
    a=propose(c,u[0],item,unit,u[0]['id']);a=advance(c,u[1],a,'confirm',owner_id=u[0]['id'])
    b=propose(c,u[0],item,unit,u[3]['id']);b=advance(c,u[1],b,'confirm',owner_id=u[3]['id'])
    fields={'title':'Draft','url':DRAFT_URL,'reason':'Selected'}
    with pytest.raises(permissions.Denied):handoff.set_draft(c,u[3],item['id'],0,fields)
    with pytest.raises(permissions.Denied):handoff.post(c,u[3],item['id'],a['id'],a['revision'],0,'Other person handoff')
    with pytest.raises(permissions.Denied):handoff.set_draft(c,u[4],item['id'],0,fields)
    other=case(c,u[0],unit);outside=handoff.add_file(c,u[0],other['id'],{'title':'Other file','url':SUPPORT_URL})
    with pytest.raises(ValueError):handoff.post(c,u[0],item['id'],a['id'],a['revision'],0,'Cross case',outside)
    file=handoff.add_file(c,u[0],item['id'],{'title':'Source table','url':SUPPORT_URL})
    with pytest.raises(permissions.Denied):handoff.retire_file(c,u[3],item['id'],file,'Not mine')
    assert handoff.post(c,u[3],item['id'],b['id'],b['revision'],0,'My own handoff')
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restricted'})
    with pytest.raises(permissions.Denied):handoff.page(c,u[3],item['id'])
    with pytest.raises(permissions.Denied):handoff.post(c,u[3],item['id'],b['id'],b['revision'],0,'Revoked')


def test_handoff_stale_draft_task_removed_link_and_disabled_writes(workspace):
    c,u,unit,_=workspace;item=case(c,u[0],unit);task=propose(c,u[0],item,unit,u[0]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    draft=handoff.set_draft(c,u[0],item['id'],0,{'title':'Draft','url':DRAFT_URL,'reason':'Selected'})
    with pytest.raises(docs.Conflict):handoff.post(c,u[0],item['id'],task['id'],task['revision'],0,'Stale draft')
    with pytest.raises(docs.Conflict):handoff.set_draft(c,u[0],item['id'],0,{'title':'Replacement','url':SHEET_URL,'reason':'Stale'})
    stale_revision=task['revision'];task=advance(c,u[0],task,'acknowledge')
    with pytest.raises(docs.Conflict):handoff.post(c,u[0],item['id'],task['id'],stale_revision,draft,'Stale task')
    sid=handoff.add_file(c,u[0],item['id'],{'title':'Table','url':SUPPORT_URL})
    with pytest.raises(docs.Conflict):handoff.add_file(c,u[0],item['id'],{'title':'Duplicate name','url':SUPPORT_URL})
    handoff.retire_file(c,u[0],item['id'],sid,'Removed')
    with pytest.raises(ValueError):handoff.post(c,u[0],item['id'],task['id'],task['revision'],draft,'Removed file',sid)
    cleared=handoff.set_draft(c,u[0],item['id'],draft,{'reason':'No draft needed'},clear=True)
    assert handoff.post(c,u[0],item['id'],task['id'],task['revision'],cleared,'Handoff without draft')
    st.set_setting(c,'work.enabled','0')
    assert handoff.page(c,u[0],item['id'])['notes']
    with pytest.raises(ValueError):handoff.post(c,u[0],item['id'],task['id'],task['revision'],cleared,'Disabled')
    with pytest.raises(ValueError):handoff.add_file(c,u[0],item['id'],{'title':'No','url':SUPPORT_URL})


def test_handoff_concurrent_draft_selection_and_atomic_audit(workspace,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    c,u,unit,path=workspace;item=case(c,u[0],unit)
    def select(url):
        conn=st.connect(path)
        try:
            handoff.set_draft(conn,u[0],item['id'],0,{'title':'Shared draft','url':url,'reason':'Selected'})
            return 'saved'
        except docs.Conflict:return 'conflict'
        finally:conn.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(select,[DRAFT_URL,SHEET_URL]))==['conflict','saved']
    def fail(*args,**kwargs):raise RuntimeError('audit unavailable')
    monkeypatch.setattr(work,'_event',fail)
    with pytest.raises(RuntimeError):handoff.add_file(c,u[0],item['id'],{'title':'Rollback','url':SUPPORT_URL})
    assert not handoff.files(c,item['id'])
    assert c.execute('SELECT COUNT(*) FROM work_draft').fetchone()[0]==1
    st.init_db(c)
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):c.execute('DELETE FROM work_draft')
    c.rollback()


def test_handoff_history_pagination_and_http_forms(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    import html
    c,u,unit,path=workspace;item=case(c,u[0],unit);task=propose(c,u[0],item,unit,u[0]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    ids=[handoff.post(c,u[0],item['id'],task['id'],task['revision'],0,f'Note {i}') for i in range(31)]
    first=handoff.page(c,u[0],item['id']);older=handoff.page(c,u[0],item['id'],before=first['next_cursor'])
    assert [n['id'] for n in first['notes']+older['notes']]==list(reversed(ids))
    monkeypatch.setattr(app_mod,'DB',path);url=f"/work/{item['id']}/draft"
    def hidden(page,name):return html.unescape(re.search('name="'+name+'" value="([^"]*)"',page.text)[1])
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]));page=client.get(url)
        assert page.status_code==200 and 'does not grant Drive permissions' in page.text
        form={'action':'set_draft','draft_id':0,'title':'<script>Draft</script>','url':DRAFT_URL,'reason':'Working copy'}
        assert client.post(url,data=form).status_code==403
        form['csrf']=hidden(page,'csrf');page=client.post(url,data=form)
        assert page.status_code==200 and '&lt;script&gt;Draft&lt;/script&gt;' in page.text
        assert 'Open in Google Docs' in page.text and 'rel="noopener noreferrer"' in page.text
        assert client.post(url,data=form).status_code==409
        assert 'Working draft' in client.get(f"/work/{item['id']}").text
        payload={'action':'handoff','csrf':hidden(page,'csrf'),'task_id':task['id'],'task_revisions':hidden(page,'task_revisions'),'draft_id':hidden(page,'draft_id'),'note':'Place the table in section two.'}
        page=client.post(url,data=payload)
        assert page.status_code==200 and 'Place the table in section two.' in page.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert client.get(url).status_code==404


def test_phase2_question_dependency_decision_and_handoff_journey(workspace):
    """Phase gate: two contributors resolve a dependency; official source stays intact."""
    c,u,unit,_=workspace
    doc=document(c,u[0],unit)
    doc=docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[0]['id'],u[3]['id']],'reason':'Authorize the contributors'})
    item=case(c,u[0],unit,source_document_id=doc['id'])
    before=tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())
    question=discussion.post(c,u[0],item['id'],'Please validate the regional totals.')
    upstream=decisions.propose(c,u[0],item['id'],question,1,{
        'title':'Validate totals','expected_output':'Checked totals','unit_id':unit,'proposed_owner_id':u[3]['id']})
    upstream=advance(c,u[1],upstream,'confirm',owner_id=u[3]['id'])
    upstream=advance(c,u[3],upstream,'acknowledge')
    downstream=propose(c,u[0],item,unit,u[0]['id'])
    downstream=advance(c,u[1],downstream,'confirm',owner_id=u[0]['id'])
    downstream=advance(c,u[0],downstream,'acknowledge')
    downstream=change_block(c,u[1],downstream,'dependency_add',prerequisite_id=upstream['id'])
    updates.follow(c,u[0],item['id'])
    reply=discussion.post(c,u[3],item['id'],'Totals checked; use the revised grouping.',parent_id=question,mentions=[u[0]['id']])
    assert len([n for n in updates.inbox(c,u[0])[0] if n['comment_id']==reply])==1
    with pytest.raises(ValueError,match='Resolve'):
        advance(c,u[0],downstream,'submit',submission='Premature consolidation')
    upstream=change_block(c,u[3],upstream,'block',reason='Need confirmation',followup_owner_id=u[3]['id'],followup_date='2026-10-20')
    upstream=change_block(c,u[3],upstream,'unblock',reason='Confirmation received in discussion')
    upstream=advance(c,u[3],upstream,'submit',submission='Validated regional totals')
    upstream=advance(c,u[1],upstream,'accept')
    did=decisions.record(c,u[1],item['id'],reply,1,decision_fields(c,[downstream]))
    downstream=next(t for t in tasks.list_for_case(c,u[0],item['id']) if t['id']==downstream['id'])
    decisions.resolve(c,u[1],item['id'],did,downstream['id'],downstream['revision'],'retain','The planned consolidation includes this grouping.')
    downstream=next(t for t in tasks.list_for_case(c,u[0],item['id']) if t['id']==downstream['id'])
    draft=handoff.set_draft(c,u[0],item['id'],0,{'title':'Response','url':DRAFT_URL,'reason':'Consolidate inputs'})
    support=handoff.add_file(c,u[3],item['id'],{'title':'Validated totals','url':SUPPORT_URL})
    handoff.post(c,u[3],item['id'],upstream['id'],upstream['revision'],draft,'Use these totals in the response.',support)
    downstream=advance(c,u[0],downstream,'submit',submission='Consolidated response')
    assert advance(c,u[1],downstream,'accept')['status']=='done'
    assert handoff.page(c,u[0],item['id'])['notes'][0]['snapshot']['status']=='done'
    assert decisions.task_source(c,u[0],item['id'],upstream['id'])['body']=='Please validate the regional totals.'
    assert tuple(c.execute('SELECT * FROM document WHERE id=?',(doc['id'],)).fetchone())==before


# P3.1: shared views use the canonical task store, permissions and transitions.
import work_team as team


def test_team_filters_scope_and_unchanged_reads(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit,title='Regional response')
    task=propose(c,u[0],item,unit,u[0]['id'],title='Check totals')
    task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    proposal=propose(c,u[0],item,unit,title='Unassigned research')
    other=st.add_org_unit(c,'Another unit','division','WORK/D2')
    hidden=case(c,u[2],other,title='Restricted initiative')
    propose(c,u[2],hidden,other,title='Hidden contribution')
    before=c.total_changes
    for view in ('list','board'):
        items,cursor=team.page(c,u[0],{'view':view,'q':'regional','unit':str(unit),'owner':'mine'})
        assert [t['id'] for t in items]==[task['id']] and cursor is None
        assert items[0]['case']['title']=='Regional response'
    assert [t['id'] for t in team.page(c,u[0],{'owner':'unassigned'})[0]]==[proposal['id']]
    assert not team.page(c,u[0],{'unit':other})[0]
    assert not team.page(c,u[4],{'status':'all'})[0]  # no technical-admin bypass
    assert c.total_changes==before


def test_team_waiting_deadlines_and_terminal_filters(workspace):
    c,u,unit,_=workspace;item=case(c,u[0],unit)
    task=propose(c,u[0],item,unit,u[0]['id'],due_date='2020-01-01')
    task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    task=advance(c,u[0],task,'acknowledge')
    task=change_block(c,u[0],task,'block',reason='Missing totals',followup_owner_id=u[0]['id'],followup_date='2026-10-20')
    assert team.page(c,u[0],{'attention':'overdue'})[0][0]['overdue']
    visible=team.page(c,u[0],{'attention':'waiting'})[0][0]
    assert 'submit' not in visible['actions']
    task=change_block(c,u[0],task,'unblock',reason='Totals received')
    assert not team.page(c,u[0],{'attention':'waiting'})[0]
    task=advance(c,u[0],task,'submit',submission='Checked totals');task=advance(c,u[1],task,'accept')
    assert not team.page(c,u[0],{})[0]
    assert team.page(c,u[0],{'status':'done'})[0][0]['id']==task['id']
    assert not team.page(c,u[0],{'status':'all','attention':'overdue'})[0]


def test_team_bounded_pagination_past_hidden_rows(workspace):
    c,u,unit,_=workspace
    visible=case(c,u[0],unit);old=propose(c,u[0],visible,unit)
    hidden=case(c,u[2],unit,title='Private case')
    for i in range(250):
        propose(c,u[2],hidden,unit,title=f'Private {i}')
    page,cursor=team.page(c,u[0],{})
    assert page==[] and cursor
    page,end=team.page(c,u[0],{'before':cursor})
    assert [t['id'] for t in page]==[old['id']] and end is None
    for i in range(27):propose(c,u[0],visible,unit,title=f'Visible {i}')
    a,cursor=team.page(c,u[0],{})
    b,end=team.page(c,u[0],{'before':cursor})
    assert len(a)==25 and len(b)==2 and end is not None
    tail,final=team.page(c,u[0],{'before':end})
    assert [t['id'] for t in tail]==[old['id']] and final is None
    assert not {t['id'] for t in a}&{t['id'] for t in b}


def test_team_revocation_disabled_and_inactive_owner(workspace):
    c,u,unit,_=workspace;doc=document(c,u[0],unit)
    item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    st.set_setting(c,'work.enabled','0')
    assert team.page(c,u[0],{})[0][0]['actions']==[]
    st.set_setting(c,'work.enabled','1')
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    assert team.page(c,u[1],{})[0][0]['owner_warning']
    assert 'acknowledge' not in team.page(c,u[1],{})[0][0]['actions']
    with pytest.raises(permissions.Denied):team.page(c,u[0],{})
    c.execute('UPDATE admin_user SET active=1 WHERE id=?',(u[0]['id'],));c.commit()
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
    assert not team.page(c,u[0],{'q':task['title'],'status':'all'})[0]
    with pytest.raises(permissions.Denied):team.one(c,u[0],item['id'],task['id'])


@pytest.mark.parametrize('selection',[{'view':'grid'},{'status':'approved'},{'owner':'-1'},
    {'unit':'no'},{'before':str(2**64)},{'attention':'secret'},{'q':'x'*121}])
def test_team_rejects_invalid_filters(selection):
    with pytest.raises(ValueError):team.filters(selection)


def test_team_http_actions_consistency_csrf_and_stale_forms(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    item=case(c,u[0],unit,title='Regional collaboration')
    task=propose(c,u[0],item,unit,u[0]['id'],title='<script>unsafe</script>')
    task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        url='/work/team?view=board&owner=mine'
        page=client.get(url)
        assert page.status_code==200,page.text
        assert '&lt;script&gt;unsafe&lt;/script&gt;' in page.text and '<script>unsafe</script>' not in page.text
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        target=f"/work/team/{item['id']}/{task['id']}/acknowledge?view=board&owner=mine"
        fields={'csrf':csrf,'revision':task['revision'],'reason':'Starting the review'}
        assert client.post(target,data={**fields,'csrf':''}).status_code==403
        response=client.post(target,data=fields,follow_redirects=False)
        assert response.status_code==303 and 'view=board' in response.headers['location']
        assert 'owner=mine' in response.headers['location']
        for view in ('list','board'):
            html=client.get('/work/team?view='+view).text
            assert 'In progress' in html and 'Submit for review' in html
        assert 'Prepare and submit output' in client.get('/work/mine').text
        assert 'In progress' in client.get(f"/work/{item['id']}").text
        stale=client.post(target,data=fields)
        assert stale.status_code==409 and 'Starting the review' in stale.text
        task=tasks.list_for_case(c,u[0],item['id'])[0]
        submit=f"/work/team/{item['id']}/{task['id']}/submit?view=list&status=in_progress"
        invalid=client.post(submit,data={'csrf':csrf,'revision':task['revision'],'reason':'Keep my note','submission':''})
        assert invalid.status_code==400 and 'Keep my note' in invalid.text
        sent=client.post(submit,data={'csrf':csrf,'revision':task['revision'],'reason':'Ready','submission':'Checked output'},follow_redirects=False)
        assert sent.status_code==303
        assert 'Waiting for contribution review' in client.get('/work/mine?view=waiting').text
        assert 'Checked output' in client.get('/work/team?status=for_review').text
        task=tasks.list_for_case(c,u[0],item['id'])[0]
        assert client.post(f"/work/team/{item['id']}/{task['id']}/accept",data={'csrf':csrf,'revision':task['revision'],'reason':'Self accept'}).status_code==403
        assert client.get('/work/team?view=invalid').status_code==400
        assert client.get('/work/team?before=invalid').status_code==400
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert 'Regional collaboration' not in client.get('/work/team?view=board').text


def test_team_dependency_and_decision_gates_share_task_authority(workspace):
    c,u,unit,_=workspace;item=case(c,u[0],unit)
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id']);task=advance(c,u[0],task,'acknowledge')
    upstream=propose(c,u[0],item,unit)
    task=change_block(c,u[1],task,'dependency_add',prerequisite_id=upstream['id'])
    entry=team.one(c,u[0],item['id'],task['id'])
    assert entry['waiting_on'][0]['id']==upstream['id'] and 'submit' not in entry['actions']
    task=change_block(c,u[1],task,'dependency_remove',prerequisite_id=upstream['id'],reason='Withdraw prerequisite')
    message=discussion.post(c,u[0],item['id'],'Recheck scope')
    did=decisions.record(c,u[1],item['id'],message,1,decision_fields(c,[task]))
    entry=team.one(c,u[0],item['id'],task['id'])
    assert entry['pending_decisions'][0]['id']==did and 'submit' not in entry['actions']
    assert [t['id'] for t in team.page(c,u[0],{'attention':'waiting'})[0]]==[task['id']]


def test_team_http_revocation_disabled_and_cross_case_reject(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    doc=document(c,u[0],unit);item=case(c,u[0],unit,source_document_id=doc['id'])
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    other=case(c,u[0],unit)
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        html=client.get('/work/team').text
        csrf=re.search(r'name="csrf" value="([a-f0-9]+)"',html)[1]
        fields={'csrf':csrf,'revision':task['revision'],'reason':'Start'}
        assert client.post(f"/work/team/{other['id']}/{task['id']}/acknowledge",data=fields).status_code==403
        target=f"/work/team/{item['id']}/{task['id']}/acknowledge"
        st.set_setting(c,'work.enabled','0')
        assert client.post(target,data=fields).status_code==400
        assert 'Start contribution' not in client.get('/work/team').text
        st.set_setting(c,'work.enabled','1')
        docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Withdraw access'})
        assert client.post(target,data=fields).status_code==403
        assert task['title'] not in client.get('/work/team?view=board').text
        assert tasks.list_for_case(c,u[1],item['id'])[0]['status']=='todo'


# P3.2: formal review retains the precise consolidation context.
import work_review as review
import documents_operations as doc_ops


class ConsolidationAdapter:
    def call(self,action,payload,operation):
        assert action=='inspect'
        return {'accessible':True,'file_id':payload['file_id'],'fingerprint':'checked-v1','size':100}


def consolidation_fixture(workspace):
    c,u,unit,_=workspace
    bureau=st.add_org_unit(c,'Work Bureau','bureau','WORK')
    rp=st.add_rp(c,'Director Reviewer',is_internal=True,org_unit_id=bureau)
    c.execute("UPDATE resource_person SET position='Director' WHERE id=?",(rp,))
    c.execute('UPDATE admin_user SET rp_id=? WHERE id=?',(rp,u[2]['id']))
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'signatory',?,'2026-10-16')",(u[2]['id'],unit));c.commit()
    u[2]=st.get_admin_user_by_id(c,u[2]['id'])
    source=document(c,u[0],unit)
    source=docs.mutate(c,u[1],source['id'],source['revision'],'verify',{'verification':'verified','reason':'Checked incoming source'})
    output=document(c,u[0],unit,direction='OUT',subject='Consolidated response')
    output=docs.mutate(c,u[1],output['id'],output['revision'],'verify',{'verification':'verified','reason':'Checked response'})
    output=doc_ops.attach(c,u[0],output['id'],output['revision'],DRAFT_URL,'material','Exact response',ConsolidationAdapter())
    item=case(c,u[0],unit,source_document_id=source['id'])
    item=work.link_document(c,u[0],item['id'],item['revision'],output['id'])
    item=work.confirm_lead(c,u[1],item['id'],item['revision'],u[2]['id'],'Accountable review lead')
    task=propose(c,u[0],item,unit,u[0]['id']);task=advance(c,u[1],task,'confirm',owner_id=u[0]['id'])
    task=advance(c,u[0],task,'acknowledge');task=advance(c,u[0],task,'submit',submission='Validated regional evidence')
    task=advance(c,u[2],task,'accept')
    return source,output,item,task


def request_consolidation(c,u,output,item,**extra):
    output=docs.raw(c,output['id'])
    return docs.mutate(c,u[1],output['id'],output['revision'],'review_route',{
        'review_class':'director','reviewer_id':u[2]['id'],'reason':'Authority and scope checked',
        'work_case_id':item['id'],'work_snapshot':review.snapshot(c,item['id'],output['id'])[1],
        'version_id':output['current_version'],**extra})


def formal_review(c,u,output,decision='approved'):
    return docs.mutate(c,u[2],output['id'],output['revision'],'review',{
        'version_id':output['current_version'],'decision':decision,'reason':'Revise the summary' if decision=='changes_requested' else 'Reviewed exact response and inputs'})


def test_consolidation_return_rerequest_feedback_and_exact_version(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    pending=propose(c,u[0],item,unit,title='Release preparation')
    output=request_consolidation(c,u,output,item)
    first=review.latest(c,output['id'])
    context=review.summaries(c,u[2],[output])[output['id']]
    assert context['accepted']==1 and context['missing']==1
    with pytest.raises(docs.Conflict):
        docs.mutate(c,u[2],output['id'],output['revision'],'review',{'decision':'approved','reason':'Wrong version','version_id':999})
    output=formal_review(c,u,output,'changes_requested')
    assert output['approved_version'] is None
    output=request_consolidation(c,u,output,item)
    second=review.latest(c,output['id']);assert second['id']!=first['id']
    output=formal_review(c,u,output)
    assert output['approved_version']==output['current_version']
    history=review.page(c,u[2],item['id'])['review_history']
    assert history[0]['reviews'][0]['decision']=='approved'
    assert history[1]['reviews'][0]['reason']=='Revise the summary'
    assert tasks.list_for_case(c,u[0],item['id'])[1]['status']=='proposed'
    assert docs.raw(c,source['id'])==source
    with pytest.raises(ValueError,match='consolidation'):
        docs.mutate(c,u[1],output['id'],output['revision'],'review_route',{'review_class':'director','reviewer_id':u[2]['id'],'reason':'Omit bound context'})


def test_consolidation_source_change_invalidates_approval_and_stale_request(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    digest=review.snapshot(c,item['id'],output['id'])[1]
    source=docs.mutate(c,u[1],source['id'],source['revision'],'deadline',{'due_date':'2026-12-01','reason':'Authorized extension'})
    with pytest.raises(docs.Conflict):request_consolidation(c,u,output,item,work_snapshot=digest)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    source=docs.mutate(c,u[2],source['id'],source['revision'],'directive',{'reason':'Use revised regional grouping'})
    changed=docs.raw(c,output['id'])
    assert changed['status']=='changes_requested' and changed['approved_version'] is None and changed['signed_version'] is None
    assert changed['revision']>output['revision']
    assert c.execute('SELECT COUNT(*) FROM document_review WHERE document_id=?',(output['id'],)).fetchone()[0]==1
    assert c.execute('SELECT COUNT(*) FROM work_review_invalidation').fetchone()[0]==1
    with pytest.raises(docs.Conflict):review.require_current(c,changed)
    with pytest.raises(docs.Conflict):formal_review(c,u,output)


def test_consolidation_conversation_preserves_approval_but_reopened_input_invalidates(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    discussion.post(c,u[0],item['id'],'Clarifying wording without changing input')
    handoff.post(c,u[0],item['id'],task['id'],task['revision'],0,'Totals are ready for consolidation.')
    assert docs.raw(c,output['id'])==output
    advance(c,u[2],task,'reopen',reason='Correct the supporting totals')
    assert docs.raw(c,output['id'])['approved_version'] is None
    assert review.page(c,u[2],item['id'])['review_history'][0]['inputs'][0]['status']=='done'


def test_consolidation_new_draft_and_signed_lineage(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    output=doc_ops.external_signature(c,u[2],output['id'],output['revision'],SUPPORT_URL,'checked-v1','Signed approved contents',ConsolidationAdapter())
    assert output['status']=='ready_to_release' and review.current(c,review.latest(c,output['id']))
    output=doc_ops.attach(c,u[1],output['id'],output['revision'],SHEET_URL,'minor','Typography correction',ConsolidationAdapter())
    assert output['approved_version'] is None and output['status']=='changes_requested'
    output=request_consolidation(c,u,output,item)
    assert review.current(c,review.latest(c,output['id']))


def test_consolidation_lock_and_audit_rollback(workspace,monkeypatch):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    c.execute("INSERT INTO document_job(id,document_id,actor_id,kind,version_id,payload_json,created_at,updated_at,state) VALUES ('test-lock',?,?,'sign',?,'{}','2026-10-16','2026-10-16','unknown')",(output['id'],u[2]['id'],output['current_version']));c.commit()
    with pytest.raises(docs.Conflict,match='external operation'):
        advance(c,u[2],task,'reopen')
    assert tasks.list_for_case(c,u[0],item['id'])[0]['revision']==task['revision']
    assert docs.raw(c,output['id'])==output
    c.execute("UPDATE document_job SET state='failed' WHERE id='test-lock'");c.commit()
    original=st.audit
    def fail(conn,*args,**kwargs):
        if len(args)>1 and args[1]=='document_consolidation_changed':raise RuntimeError('audit unavailable')
        return original(conn,*args,**kwargs)
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError,match='audit unavailable'):advance(c,u[2],task,'reopen')
    assert docs.raw(c,output['id'])==output
    assert not c.execute('SELECT 1 FROM work_review_invalidation').fetchone()


def test_consolidation_permissions_revocation_and_immutable_history(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    with pytest.raises(permissions.Denied):review.page(c,u[4],item['id'])
    with pytest.raises(permissions.Denied):request_consolidation(c,u,output,item,reviewer_id=u[4]['id'])
    output=request_consolidation(c,u,output,item)
    st.init_db(c)
    assert len(review.page(c,u[2],item['id'])['review_history'])==1
    with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM work_review_packet')
    c.rollback()
    docs.mutate(c,u[1],source['id'],source['revision'],'access',{'visibility':'restricted','viewers':[u[0]['id']],'reason':'Restrict source'})
    assert review.summaries(c,u[2],[output])=={}
    with pytest.raises(permissions.Denied):formal_review(c,u,output)


def test_consolidation_http_request_return_inbox_and_stale_note(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    source,output,item,task=consolidation_fixture(workspace)
    url=f"/work/{item['id']}/consolidation";target=url+f"/{output['id']}"
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
        page=client.get(url);assert page.status_code==200,page.text
        token=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        fields={'csrf':token,'action':'review_route','revision':output['revision'],'version_id':output['current_version'],
            'work_snapshot':review.snapshot(c,item['id'],output['id'])[1],'review_class':'director','reviewer_id':u[2]['id'],'reason':'Review consolidated evidence'}
        assert client.post(target,data={**fields,'csrf':''}).status_code==403
        assert client.post(target,data=fields,follow_redirects=False).status_code==303
        client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
        inbox=client.get('/approvals');assert inbox.status_code==200,inbox.text
        assert 'checked-v1' in inbox.text and '1 accepted inputs' in inbox.text
        page=client.get(url);token=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        output=docs.raw(c,output['id'])
        fields={'csrf':token,'action':'review','revision':output['revision'],'version_id':output['current_version'],'decision':'changes_requested','reason':'<script>Clarify totals</script>'}
        assert client.post(target,data=fields).status_code==200
        assert '&lt;script&gt;Clarify totals&lt;/script&gt;' in client.get(url).text
        assert '&lt;script&gt;Clarify totals&lt;/script&gt;' in client.get(f"/documents/{output['id']}").text
        response=client.post(target,data={**fields,'reason':'Retain my stale feedback'})
        assert response.status_code==409 and 'Retain my stale feedback' in response.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[4]))
        assert client.get(url).status_code==404


def test_consolidation_downstream_invalidation_propagates(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    downstream=document(c,u[0],unit,direction='OUT',subject='Downstream response')
    downstream=docs.mutate(c,u[1],downstream['id'],downstream['revision'],'verify',{'verification':'verified','reason':'Verified'})
    downstream=doc_ops.attach(c,u[0],downstream['id'],downstream['revision'],SHEET_URL,'material','Downstream draft',ConsolidationAdapter())
    second=case(c,u[0],unit,source_document_id=output['id'])
    second=work.link_document(c,u[0],second['id'],second['revision'],downstream['id'])
    second=work.confirm_lead(c,u[1],second['id'],second['revision'],u[2]['id'],'Review lead')
    downstream=formal_review(c,u,request_consolidation(c,u,downstream,second))
    advance(c,u[2],task,'reopen',reason='Correct evidence')
    assert docs.raw(c,output['id'])['approved_version'] is None
    assert docs.raw(c,downstream['id'])['approved_version'] is None
    assert c.execute('SELECT COUNT(*) FROM work_review_invalidation').fetchone()[0]==2


def test_consolidation_changed_decisions_and_draft_selection_require_review(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    handoff.set_draft(c,u[0],item['id'],0,{'title':'New working draft','url':SHEET_URL,'reason':'Rework consolidation'})
    assert docs.raw(c,output['id'])['approved_version'] is None
    message=discussion.post(c,u[0],item['id'],'Director requests a new grouping')
    decisions.record(c,u[2],item['id'],message,1,decision_fields(c,[task]))
    with pytest.raises(ValueError,match='Reconcile changed work decisions'):request_consolidation(c,u,output,item)



def test_consolidation_cancelled_source_invalidates_review(workspace):
    c,u,unit,_=workspace;source,output,item,task=consolidation_fixture(workspace)
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    docs.mutate(c,u[1],source['id'],source['revision'],'cancel',{'reason':'Request withdrawn'})
    assert docs.raw(c,output['id'])['approved_version'] is None
    assert docs.raw(c,output['id'])['status']=='changes_requested'


# P3.3: shared completion uses actual formal release/closure evidence.
import work_completion as completion
import uuid


def finish_document_lead(c,u,doc):
    assignment=c.execute("SELECT id FROM document_assignment WHERE document_id=? AND role='lead' ORDER BY id DESC LIMIT 1",(doc['id'],)).fetchone()[0]
    for status in ('acknowledged','submitted','completed'):
        doc=docs.mutate(c,u[2],doc['id'],doc['revision'],'contribution',{'assignment_id':assignment,'status':status,'outcome':'Formal coordination and required lead work completed'})
    return doc


def completion_fixture(workspace,signature=True,ack=True):
    c,u,unit,_=workspace
    source,output,item,task=consolidation_fixture(workspace)
    # Set the synthetic document policy before review; no live adapters are used.
    c.execute('UPDATE document SET policy_json=? WHERE id=?',(json.dumps({'signature_required':signature,'ack_required':ack,'release':['authority'],'closure':['filed']}),output['id']));c.commit()
    output=docs.raw(c,output['id'])
    output=docs.mutate(c,u[1],output['id'],output['revision'],'lead',{'user_id':u[2]['id'],'task':'Lead the formal response','reason':'Confirm lead'})
    output=finish_document_lead(c,u,output)
    completion.configure(c,u[1],item['id'],item['revision'],'formal',[output['id']],'Official response is required for this outcome')
    item=work.get(c,u[0],item['id'])
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    return source,output,item,task


def release_and_close(c,u,output,signature=True,ack=True):
    output=docs.raw(c,output['id'])
    if signature:
        output=doc_ops.external_signature(c,u[2],output['id'],output['revision'],SUPPORT_URL,'checked-v1','Signed reviewed response',ConsolidationAdapter())
    output=doc_ops.record_dispatch(c,u[1],output['id'],output['revision'],{'operation_id':str(uuid.uuid4()),'channel':'email',
        'sender':'office@example.test','recipients':['recipient@example.test'],'evidence':'Confirmed delivery message-id',
        'checklist':{'authority':'Authorized response'}},ConsolidationAdapter())
    dispatch=c.execute('SELECT MAX(id) FROM document_dispatch WHERE document_id=?',(output['id'],)).fetchone()[0]
    if ack:output=doc_ops.acknowledge(c,u[1],output['id'],output['revision'],dispatch,'recipient@example.test','Received and acknowledged')
    return docs.mutate(c,u[2],output['id'],output['revision'],'close',{'evidence':{'filed':'Filed with the incoming request'}})


def finish_case(c,u,item,evidence='Delivered response and filed closure evidence'):
    page=completion.page(c,u[2],item['id'])
    completion.complete(c,u[2],item['id'],page['case']['revision'],page['digest'],evidence)


def test_completion_signed_release_ack_closure_and_reopen(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    with pytest.raises(ValueError,match='official records'):finish_case(c,u,item)
    output=release_and_close(c,u,output)
    page=completion.page(c,u[2],item['id']);assert page['issues']==[],page
    finish_case(c,u,item)
    closed=work.get(c,u[0],item['id']);assert closed['status']=='completed'
    stored=c.execute('SELECT snapshot_json FROM work_completion').fetchone()[0]
    assert 'Confirmed delivery message-id' in stored and 'Received and acknowledged' in stored
    assert 'Signed reviewed response' in stored and 'Reviewed exact response and inputs' in stored
    with pytest.raises(ValueError,match='Reopen'):advance(c,u[2],task,'reopen')
    with pytest.raises(ValueError,match='Reopen'):handoff.set_draft(c,u[0],item['id'],0,{'title':'Late change','url':DRAFT_URL,'reason':'Change'})
    with pytest.raises(ValueError,match='Reopen'):work.link_document(c,u[0],item['id'],closed['revision'],source['id'])
    discussion.post(c,u[0],item['id'],'Post-completion clarification retained')
    assert work.get(c,u[0],item['id'])['status']=='completed'
    completion.reopen(c,u[2],item['id'],closed['revision'],'Follow-up needed')
    assert work.get(c,u[0],item['id'])['status']=='open'
    assert c.execute('SELECT snapshot_json FROM work_completion').fetchone()[0]==stored
    assert docs.raw(c,output['id'])['status']=='closed'  # case reopening cannot reopen official records


def test_completion_internal_scope_authority_and_required_tasks(workspace):
    c,u,unit,_=workspace;item=case(c,u[0],unit)
    item=work.confirm_lead(c,u[1],item['id'],item['revision'],u[2]['id'],'Lead')
    task=propose(c,u[0],item,unit)
    with pytest.raises(permissions.Denied):completion.configure(c,u[0],item['id'],item['revision'],'internal',[],'Creator cannot declare scope')
    completion.configure(c,u[1],item['id'],item['revision'],'internal',[],'Internal coordination; no formal release required')
    with pytest.raises(ValueError,match='outstanding'):finish_case(c,u,item)
    task=advance(c,u[1],task,'cancel',reason='Requirement withdrawn by authorized officer')
    finish_case(c,u,item,'Agreed internal outcome documented')
    assert work.get(c,u[0],item['id'])['status']=='completed'
    with pytest.raises(permissions.Denied):completion.page(c,u[4],item['id'])


def test_completion_release_blocks_late_required_contribution(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace,signature=False,ack=False)
    proposed=propose(c,u[0],item,unit,title='Missing required input')
    # Renewed review can explicitly acknowledge outstanding input; release cannot bypass it.
    output=formal_review(c,u,request_consolidation(c,u,output,item))
    with pytest.raises(ValueError,match='outstanding contributions'):
        doc_ops.record_dispatch(c,u[1],output['id'],output['revision'],{'operation_id':str(uuid.uuid4()),'channel':'email','sender':'office@example.test','recipients':['r@example.test'],'evidence':'Try bypass','checklist':{'authority':'checked'}},ConsolidationAdapter())
    assert not c.execute('SELECT 1 FROM document_dispatch').fetchone()


def test_completion_unknown_delivery_and_missing_ack_cannot_pass(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    output=release_and_close(c,u,output)
    c.execute("INSERT INTO document_job(id,document_id,actor_id,kind,version_id,payload_json,created_at,updated_at,state) VALUES ('uncertain-send',?,?,'dispatch',?,'{}','2026-10-16','2026-10-16','unknown')",(output['id'],u[1]['id'],output['current_version']));c.commit()
    assert completion.page(c,u[2],item['id'])['issues']
    with pytest.raises(ValueError):finish_case(c,u,item)
    c.execute("UPDATE document_job SET state='confirmed' WHERE id='uncertain-send'")
    c.execute('UPDATE document_dispatch_recipient SET acknowledged_at=NULL');c.commit()
    assert 'Required recipient acknowledgment is missing.' in completion.page(c,u[2],item['id'])['requirements'][0]['issues']
    with pytest.raises(ValueError):finish_case(c,u,item)
    assert not c.execute('SELECT 1 FROM work_completion').fetchone()


def test_completion_snapshot_stale_disabled_and_atomic_audit(workspace,monkeypatch):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    output=release_and_close(c,u,output)
    page=completion.page(c,u[2],item['id'])
    docs.mutate(c,u[1],output['id'],output['revision'],'receipt',{'channel':'email','sender':'recipient','received_at':'2026-10-16T12:00:00','evidence':'Additional receipt'})
    with pytest.raises(docs.Conflict):completion.complete(c,u[2],item['id'],page['case']['revision'],page['digest'],'Stale evidence')
    st.set_setting(c,'work.enabled','0')
    assert completion.page(c,u[2],item['id'])
    with pytest.raises(ValueError,match='not enabled'):finish_case(c,u,item)
    st.set_setting(c,'work.enabled','1')
    def fail(*a,**k):raise RuntimeError('audit unavailable')
    monkeypatch.setattr(st,'audit',fail)
    with pytest.raises(RuntimeError):finish_case(c,u,item)
    assert work.get(c,u[0],item['id'])['status']=='open'
    assert not c.execute('SELECT 1 FROM work_completion').fetchone()


def test_completion_official_reopening_reactivates_case_and_keeps_history(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    output=release_and_close(c,u,output);finish_case(c,u,item)
    before=c.execute('SELECT snapshot_json FROM work_completion').fetchone()[0]
    docs.mutate(c,u[2],output['id'],output['revision'],'reopen',{'due_date':'2026-12-01','reason':'Official correction required'})
    assert work.get(c,u[0],item['id'])['status']=='open'
    assert c.execute('SELECT snapshot_json FROM work_completion').fetchone()[0]==before
    assert c.execute("SELECT 1 FROM work_event WHERE action='completion_invalidated'").fetchone()
    st.init_db(c)
    with pytest.raises(sqlite3.IntegrityError):c.execute('DELETE FROM work_completion')
    c.rollback()


def test_completion_scope_cannot_drop_automatic_formal_requirements(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    assert output['id'] in completion.required_ids(c,item['id'])
    with pytest.raises(ValueError,match='cannot be removed'):
        completion.configure(c,u[1],item['id'],item['revision'],'internal',[],'Try to avoid delivery')
    outsider=case(c,u[0],unit);other=document(c,u[0],unit)
    with pytest.raises(permissions.Denied):completion.configure(c,u[1],outsider['id'],outsider['revision'],'formal',[other['id']],'Unlinked document')


def test_completion_changed_released_input_requires_closed_followup(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    output=release_and_close(c,u,output)
    task=advance(c,u[2],task,'reopen');task=advance(c,u[0],task,'submit',submission='Corrected regional evidence');task=advance(c,u[2],task,'accept')
    with pytest.raises(ValueError):finish_case(c,u,item)
    followup=document(c,u[0],unit,direction='OUT',subject='Corrected formal follow-up')
    c.execute('UPDATE document SET policy_json=? WHERE id=?',(output['policy_json'],followup['id']));c.commit()
    followup=docs.raw(c,followup['id'])
    followup=docs.mutate(c,u[1],followup['id'],followup['revision'],'verify',{'verification':'verified','reason':'Checked correction'})
    followup=docs.mutate(c,u[1],followup['id'],followup['revision'],'lead',{'user_id':u[2]['id'],'task':'Lead corrected response','reason':'Confirmed'})
    followup=finish_document_lead(c,u,followup)
    followup=doc_ops.attach(c,u[0],followup['id'],followup['revision'],SHEET_URL,'material','Corrected response',ConsolidationAdapter())
    item=work.get(c,u[0],item['id']);item=work.link_document(c,u[0],item['id'],item['revision'],followup['id'])
    followup=formal_review(c,u,request_consolidation(c,u,followup,item))
    followup=release_and_close(c,u,followup)
    with pytest.raises(ValueError):finish_case(c,u,item)  # an unrelated new release cannot stand in for a follow-up
    docs.mutate(c,u[2],followup['id'],followup['revision'],'relate',{'target_id':output['id'],'kind':'follow_up'})
    finish_case(c,u,item)
    assert work.get(c,u[0],item['id'])['status']=='completed'


@pytest.mark.parametrize('missing',['approval','signature','delivery','closure'])
def test_completion_legacy_status_alone_cannot_replace_evidence(workspace,missing):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    output=release_and_close(c,u,output)
    if missing=='approval':c.execute('DELETE FROM document_review WHERE document_id=?',(output['id'],))
    elif missing=='signature':c.execute('DELETE FROM document_signature WHERE document_id=?',(output['id'],))
    elif missing=='delivery':c.execute('DELETE FROM document_dispatch_recipient')
    else:c.execute('UPDATE document SET policy_json=? WHERE id=?',(json.dumps({**json.loads(output['policy_json']),'closure':['new_required_evidence']}),output['id']))
    c.commit()
    assert docs.raw(c,output['id'])['status']=='closed'
    with pytest.raises(ValueError):finish_case(c,u,item)


def test_completion_http_permissions_csrf_retained_note_and_state(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    source,output,item,task=completion_fixture(workspace);output=release_and_close(c,u,output)
    url=f"/work/{item['id']}/completion"
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[0]))
        page=client.get(url);assert page.status_code==200,page.text
        # No completion form for an ordinary contributor.
        assert 'Record completion</button>' not in page.text
        client.cookies.set(auth.COOKIE_NAME,session_token(u[2]))
        page=client.get(url);token=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        data=completion.page(c,u[2],item['id'])
        fields={'action':'complete','csrf':token,'revision':data['case']['revision'],'digest':data['digest'],'evidence':'<script>Outcome confirmed</script>'}
        assert client.post(url,data={**fields,'csrf':''}).status_code==403
        stale=client.post(url,data={**fields,'digest':'stale'})
        assert stale.status_code==409 and '&lt;script&gt;Outcome confirmed&lt;/script&gt;' in stale.text
        response=client.post(url,data=fields)
        assert response.status_code==200 and 'Reopen work item' in response.text
        assert '&lt;script&gt;Outcome confirmed&lt;/script&gt;' in response.text
        assert 'Completed' in client.get(f"/work/{item['id']}").text
        assert client.post(url,data=fields).status_code==409
        docs.mutate(c,u[1],source['id'],source['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Withdraw case access'})
        assert client.get(url).status_code==404
        assert client.post(url,data=fields).status_code==403


# P3.4: preferences change optional discussion delivery, never required workflows.
import work_digests as digests
from datetime import datetime, timedelta


def digest_fixture(workspace, monkeypatch, cadence='daily'):
    c,u,unit,_=workspace
    item=case(c,u[0],unit)
    updates.follow(c,u[1],item['id'])
    digests.save(c,u[1],0,'hide',cadence)
    monkeypatch.setattr(digests.mailer,'email_configured',lambda:True)
    sent=[]
    def send(to,subject,body,html=None):
        sent.append((to,subject,body))
        return {'sent':True,'detail':'Synthetic acceptance'}
    monkeypatch.setattr(digests.mailer,'send',send)
    cid=discussion.post(c,u[0],item['id'],'Private discussion body')
    return item,cid,sent


def test_notification_preferences_defaults_scope_conflict_and_disabled_work(workspace):
    c,u,unit,_=workspace
    assert digests.preferences(c,u[0])['digest']=='off'
    assert digests.preferences(c,u[0])['routine_bell']=='show'
    st.set_setting(c,'work.enabled','0')
    digests.save(c,u[0],0,'hide','weekly')  # personal preferences remain editable
    assert digests.preferences(c,u[1])['digest']=='off'
    with pytest.raises(docs.Conflict):digests.save(c,u[0],0,'show','off')
    with pytest.raises(ValueError):digests.save(c,u[0],1,'hide','hourly')
    st.init_db(c)
    assert digests.preferences(c,u[0])['digest']=='weekly'
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[0]['id'],));c.commit()
    with pytest.raises(permissions.Denied):digests.save(c,u[0],1,'show','off')


def test_routine_bell_control_preserves_direct_alerts_and_unread(workspace):
    c,u,unit,_=workspace
    item=case(c,u[0],unit);updates.follow(c,u[1],item['id'])
    cid=discussion.post(c,u[0],item['id'],'Routine progress')
    assert updates.bell_rows(c,u[1])
    digests.save(c,u[1],0,'hide','off')
    assert not updates.bell_rows(c,u[1])
    assert len(updates.inbox(c,u[1],category='following')[0])==1
    assert updates.read_revision(c,u[1]['id'],cid)==0
    # A later explicit mention promotes a routine notice without creating duplicates.
    discussion.edit(c,u[0],item['id'],None,cid,1,'Please look',mentions=[u[1]['id']])
    assert updates.bell_rows(c,u[1])
    assert len(updates.inbox(c,u[1],category='direct')[0])==1
    assert not updates.inbox(c,u[1],category='following')[0]
    assert c.execute('SELECT COUNT(*) FROM work_notice').fetchone()[0]==1
    parent=discussion.post(c,u[1],item['id'],'Question')
    discussion.post(c,u[0],item['id'],'Answer',parent_id=parent)
    assert len(updates.inbox(c,u[1],category='direct')[0])==2
    with pytest.raises(ValueError):updates.inbox(c,u[1],category='untrusted')


def test_digest_daily_dedup_read_state_privacy_and_next_day(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    now=datetime(2026,10,19,7)
    assert digests.deliver(c,'https://office.example.test',dry_run=True,now=now)==1
    assert not c.execute('SELECT 1 FROM work_digest').fetchone() and not sent
    assert digests.deliver(c,'https://office.example.test',now=now)==1
    assert len(sent)==1 and sent[0][0]==u[1]['username']
    assert 'Private discussion body' not in sent[0][2] and item['title'] not in sent[0][2]
    assert '/work/updates' in sent[0][2]
    assert updates.read_revision(c,u[1]['id'],cid)==0
    assert digests.deliver(c,'https://office.example.test',now=now)==0
    later=discussion.post(c,u[0],item['id'],'Next update')
    read=discussion.post(c,u[0],item['id'],'Already read')
    updates.mark_read(c,u[1],item['id'],None,[[read,1]])
    assert digests.deliver(c,'https://office.example.test',now=now)==0
    assert digests.deliver(c,'https://office.example.test',now=now+timedelta(days=1))==1
    assert c.execute('SELECT COUNT(*) FROM work_digest_notice').fetchone()[0]==2
    assert digests.deliver(c,'https://office.example.test',now=now+timedelta(days=2))==0
    assert len(digests.history(c,u[1]))==2 and not digests.history(c,u[0])


def test_digest_weekly_and_cadence_changes_do_not_replay(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch,'weekly')
    monday=datetime(2026,10,19,7)
    assert digests.deliver(c,'https://office.test',now=monday-timedelta(days=1))==0
    assert digests.deliver(c,'https://office.test',now=monday)==1
    discussion.post(c,u[0],item['id'],'New update')
    digests.save(c,u[1],1,'show','daily')
    assert digests.deliver(c,'https://office.test',now=monday)==0
    digests.save(c,u[1],2,'show','weekly')
    assert digests.deliver(c,'https://office.test',now=monday+timedelta(days=1))==0
    assert digests.deliver(c,'https://office.test',now=monday+timedelta(days=7))==1
    assert len(sent)==2


@pytest.mark.parametrize('outcome',['false','exception','crash'])
def test_digest_uncertain_attempt_never_replayed(workspace,monkeypatch,outcome):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    class Interrupted(BaseException):pass
    def uncertain(*args,**kwargs):
        sent.append('attempt')
        if outcome=='crash':raise Interrupted()
        if outcome=='exception':raise RuntimeError('Transport timed out')
        return {'sent':False}
    monkeypatch.setattr(digests.mailer,'send',uncertain)
    now=datetime(2026,10,19,7)
    if outcome=='crash':
        with pytest.raises(Interrupted):digests.deliver(c,'https://office.test',now=now)
    else:
        assert digests.deliver(c,'https://office.test',now=now)==0
    assert digests.history(c,u[1])[0]['state']==('sending' if outcome=='crash' else 'unknown')
    assert digests.deliver(c,'https://office.test',now=now+timedelta(days=1))==0
    assert len(sent)==1


def test_digest_reentrant_worker_does_not_duplicate_claim(workspace,monkeypatch):
    c,u,unit,path=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    now=datetime(2026,10,19,7)
    def competing(*args,**kwargs):
        other=st.connect(path)
        try:assert digests.deliver(other,'https://office.test',now=now)==0
        finally:other.close()
        sent.append('one');return {'sent':True}
    monkeypatch.setattr(digests.mailer,'send',competing)
    assert digests.deliver(c,'https://office.test',now=now)==1
    assert sent==['one']


@pytest.mark.parametrize('gate',['work','documents','email','transport','inactive','opt_out'])
def test_digest_disabled_gates_do_not_claim_or_send(workspace,monkeypatch,gate):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    if gate in ('work','documents'):st.set_setting(c,gate+'.enabled','0')
    elif gate=='email':st.set_email_feature(c,'job_work_updates',False)
    elif gate=='transport':monkeypatch.setattr(digests.mailer,'email_configured',lambda:False)
    elif gate=='opt_out':digests.save(c,u[1],1,'hide','off')
    else:c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[1]['id'],));c.commit()
    assert digests.deliver(c,'https://office.test',now=datetime(2026,10,19,7))==0
    assert not sent and not c.execute('SELECT 1 FROM work_digest').fetchone()


def test_digest_access_revocation_omits_hidden_notices(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    doc=document(c,u[0],unit)
    hidden=case(c,u[0],unit,source_document_id=doc['id'])
    updates.follow(c,u[0],hidden['id'])
    digests.save(c,u[0],0,'show','daily')
    discussion.post(c,u[1],hidden['id'],'Hidden after revocation')
    docs.mutate(c,u[1],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[1]['id']],'reason':'Restrict'})
    assert not digests.eligible(c,u[0])
    assert digests.deliver(c,'https://office.test',now=datetime(2026,10,19,7))==1
    assert len(sent)==1 and sent[0][0]==u[1]['username']


def test_digest_rechecks_revocation_after_claim(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    original=digests.eligible
    def revoke(conn,user):
        ids=original(conn,user)
        conn.execute('UPDATE admin_user SET active=0 WHERE id=?',(user['id'],))
        return ids
    monkeypatch.setattr(digests,'eligible',revoke)
    assert digests.deliver(c,'https://office.test',now=datetime(2026,10,19,7))==0
    assert not sent
    assert c.execute('SELECT state FROM work_digest').fetchone()[0]=='cancelled'


def test_digest_claim_failure_rolls_back(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    c.execute("CREATE TRIGGER fail_digest BEFORE INSERT ON work_digest_notice BEGIN SELECT RAISE(ABORT,'broken queue'); END;");c.commit()
    with pytest.raises(sqlite3.IntegrityError):digests.deliver(c,'https://office.test',now=datetime(2026,10,19,7))
    assert not sent and not c.execute('SELECT 1 FROM work_digest').fetchone()


def test_digest_scheduler_and_email_catalog(workspace,monkeypatch):
    import send_reminders
    c,u,unit,path=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    monkeypatch.setenv('CSS_BASE_URL','https://office.test')
    monkeypatch.setattr(digests.tz,'now_local',lambda:datetime(2026,10,19,7))
    assert send_reminders.run(path,jobs=['work_updates'])=={'work_updates':1}
    assert send_reminders.run(path,jobs=['work_updates'])=={'work_updates':0}
    st.set_email_feature(c,'job_work_updates',False)
    assert send_reminders.run(path,jobs=['work_updates'])=={}
    assert 'job_work_updates' in digests.mailer._PREVIEWS


def test_notification_preferences_http_csrf_conflicts_and_categories(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    item=case(c,u[0],unit);updates.follow(c,u[1],item['id'])
    discussion.post(c,u[0],item['id'],'Routine body')
    discussion.post(c,u[0],item['id'],'Direct body',mentions=[u[1]['id']])
    url='/work/notification-preferences'
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
        page=client.get(url);assert page.status_code==200,page.text
        token=re.search(r'name="csrf" value="([a-f0-9]+)"',page.text)[1]
        assert not c.execute('SELECT 1 FROM work_notification_preference').fetchone()
        fields={'csrf':token,'revision':'0','routine_bell':'hide','digest':'weekly','user_id':u[0]['id']}
        assert client.post(url,data={**fields,'csrf':''}).status_code==403
        assert client.post(url,data=fields,follow_redirects=False).status_code==303
        assert digests.preferences(c,u[0])['digest']=='off'
        assert client.post(url,data=fields).status_code==409
        assert client.post(url,data={**fields,'revision':'1','digest':'<script>'}).status_code==400
        direct=client.get('/work/updates?category=direct')
        assert 'Direct body' in direct.text and 'Routine body' not in direct.text
        followed=client.get('/work/updates?category=following')
        assert 'Routine body' in followed.text and 'Direct body' not in followed.text
        assert client.get('/work/updates?category=invalid').status_code==400


def test_quiet_preferences_preserve_required_task_and_review_alerts(workspace):
    import documents_notify as notices
    c,u,unit,_=workspace
    item=inbox_case(c,u,unit);task=propose(c,u[0],item,unit,u[3]['id'])
    task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    before=notices.bell_rows(c,u[3]['id'])
    assert before
    digests.save(c,u[3],0,'hide','off')
    assert notices.bell_rows(c,u[3]['id'])==before
    task=advance(c,u[3],task,'acknowledge');task=advance(c,u[3],task,'submit',submission='Ready')
    before=notices.bell_rows(c,u[2]['id'])
    assert before
    digests.save(c,u[2],0,'hide','weekly')
    assert notices.bell_rows(c,u[2]['id'])==before


def test_digest_optout_after_claim_cancels_without_consuming_notices(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    original=digests.eligible
    def optout(conn,user):
        ids=original(conn,user)
        conn.execute("UPDATE work_notification_preference SET digest='off',revision=revision+1 WHERE user_id=?",(user['id'],))
        return ids
    monkeypatch.setattr(digests,'eligible',optout)
    assert digests.deliver(c,'https://office.test',now=datetime(2026,10,19,7))==0
    assert not sent and digests.history(c,u[1])[0]['state']=='cancelled'
    assert not c.execute('SELECT 1 FROM work_digest_notice').fetchone()


def test_digest_read_between_claim_and_send_is_omitted(workspace,monkeypatch):
    c,u,unit,_=workspace;item,cid,sent=digest_fixture(workspace,monkeypatch)
    second=discussion.post(c,u[0],item['id'],'Still unread')
    original=digests.eligible
    def mark(conn,user):
        ids=original(conn,user)
        conn.execute('INSERT INTO work_comment_read VALUES (?,?,1)',(cid,user['id']))
        return ids
    monkeypatch.setattr(digests,'eligible',mark)
    assert digests.deliver(c,'https://office.test',now=datetime(2026,10,19,7))==1
    claimed=c.execute('SELECT n.comment_id FROM work_digest_notice dn JOIN work_notice n ON n.id=dn.notice_id').fetchall()
    assert claimed==[(second,)]


# P3.5: exact, permission-scoped support counts and matching drill-downs.
import work_support as support
from datetime import date


def support_counts(report):
    return {m['key']:m['count'] for m in report['metrics']}


def test_support_counts_overlap_without_conflating_cases_and_contributions(workspace):
    c,u,unit,_=workspace
    item=inbox_case(c,u,unit)
    a=propose(c,u[0],item,unit,title='Unassigned and overdue',due_date='2026-10-19')
    b=propose(c,u[0],item,unit,title='Waiting for upstream')
    b=advance(c,u[1],b,'confirm',owner_id=u[3]['id'])
    b=change_block(c,u[2],b,'dependency_add',prerequisite_id=a['id'],reason='Need upstream')
    result=support.report(c,u[1],today=date(2026,10,20));counts=support_counts(result)
    assert result['managed_count']==1
    assert counts['risk']==1 and counts['unassigned']==1 and counts['waiting']==1
    assert counts['overdue']==1 and counts['no_date']==1 and counts['case_no_date']==1
    assert len(result['items'])==1 and len(result['items'][0]['reasons'])==3
    for key in support.METRICS:
        drill=support.report(c,u[1],{'metric':key},today=date(2026,10,20))
        assert drill['total']==counts[key] and len(drill['items'])==counts[key]
    target=support.report(c,u[1],{'metric':'unassigned'},today=date(2026,10,20))['items'][0]
    assert target['url']==f"/work/{item['id']}#task-{a['id']}"


def test_support_today_missing_targets_and_seven_day_boundary(workspace):
    c,u,unit,_=workspace
    for due in (None,'2026-10-20','2026-10-27','2026-10-28'):
        item=case(c,u[0],unit,due_date=due)
        work.confirm_lead(c,u[1],item['id'],item['revision'],u[2]['id'],'Confirmed')
    result=support.report(c,u[1],today=date(2026,10,20))
    assert support_counts(result)['risk']==2  # today through day 7 inclusive
    assert support_counts(result)['case_no_date']==1
    assert support_counts(result)['overdue']==0
    item=inbox_case(c,u,unit)
    task=propose(c,u[0],item,unit,due_date='2026-10-20')
    advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    assert support_counts(support.report(c,u[1],today=date(2026,10,20)))['overdue']==0
    assert support_counts(support.report(c,u[1],today=date(2026,10,21)))['overdue']==1


def test_support_authority_is_not_membership_or_technical_admin(workspace):
    c,u,unit,_=workspace;item=inbox_case(c,u,unit)
    task=propose(c,u[0],item,unit);advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    assert support.report(c,u[1])['managed_count']==1
    assert support.report(c,u[2])['managed_count']==1
    for user in (u[0],u[3],u[4],{**u[4],'role':'section_manager'}):
        assert support.report(c,user)['managed_count']==0
        assert not support.report(c,user)['support_units']
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[1]['id'],));c.commit()
    with pytest.raises(permissions.Denied):support.report(c,u[1])


def test_support_revocation_hides_counts_titles_units_and_drilldowns(workspace):
    c,u,unit,_=workspace
    doc=document(c,u[0],unit)
    item=case(c,u[0],unit,source_document_id=doc['id'])
    propose(c,u[0],item,unit,title='Restricted contribution')
    assert support_counts(support.report(c,u[1]))['unassigned']==1
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-17')",(u[0]['id'],unit));c.commit()
    docs.mutate(c,u[0],doc['id'],doc['revision'],'access',{'visibility':'restricted','viewers':[u[0]['id']],'reason':'Restrict officer access'})
    report=support.report(c,u[1],{'metric':'unassigned'})
    assert not report['items'] and not report['support_units'] and not report['managed_count']
    assert all(m['count']==0 for m in report['metrics'])


def test_support_unit_filter_uses_case_unit_and_preserves_links(workspace):
    c,u,unit,_=workspace
    other=st.add_org_unit(c,'Other case unit','division','OTHER/P35')
    c.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-17')",(u[1]['id'],other));c.commit()
    item=case(c,u[0],unit);propose(c,u[0],item,other)
    another=case(c,u[0],other);propose(c,u[0],another,unit)
    result=support.report(c,u[1],{'unit':str(unit),'metric':'unassigned'})
    assert result['managed_count']==1 and result['total']==1
    assert result['items'][0]['url'].startswith(f"/work/{item['id']}#")
    assert all(f'unit={unit}' in m['url'] for m in result['metrics'])


def test_support_review_age_from_submission_not_later_changes(workspace):
    c,u,unit,_=workspace;item=inbox_case(c,u,unit)
    task=propose(c,u[0],item,unit);task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    task=advance(c,u[3],task,'acknowledge')
    import tzutil
    # A genuine submission at a fixed timestamp, followed by an unrelated milestone edit.
    from unittest.mock import patch
    with patch.object(tzutil,'now_iso',return_value='2026-10-18T15:00:00'):
        task=advance(c,u[3],task,'submit',submission='Ready')
    task=advance(c,u[1],task,'milestone',due_date='2026-10-25')
    result=support.report(c,u[2],{'metric':'review'},today=date(2026,10,20))
    assert result['total']==1 and result['items'][0]['wait_days']==2
    assert support.age(None,date(2026,10,20)) is None
    assert support.age('2026-10-21T00:00:00',date(2026,10,20)) is None
    advance(c,u[2],task,'accept')
    assert support.report(c,u[2],{'metric':'review'})['total']==0


def test_support_owner_inactive_and_completed_tasks_excluded(workspace):
    c,u,unit,_=workspace;item=inbox_case(c,u,unit)
    task=propose(c,u[0],item,unit);task=advance(c,u[1],task,'confirm',owner_id=u[3]['id'])
    cancelled=propose(c,u[0],item,unit,due_date='2026-10-01');advance(c,u[1],cancelled,'cancel')
    c.execute('UPDATE admin_user SET active=0 WHERE id=?',(u[3]['id'],));c.commit()
    result=support.report(c,u[1],{'metric':'owner_unavailable'})
    assert result['total']==1 and result['items'][0]['id']==task['id']
    assert support_counts(result)['unassigned']==0 and support_counts(result)['overdue']==0
    assert support_counts(result)['risk']==1


def test_support_formal_review_deduplicates_shared_documents(workspace,monkeypatch):
    c,u,unit,_=workspace
    source,output,item,task=completion_fixture(workspace)
    # This fixture has approved the output; request a fresh actual review.
    output=request_consolidation(c,u,output,item)
    another=case(c,u[0],unit,source_document_id=output['id'])
    result=support.report(c,u[1],{'metric':'formal_review'})
    assert result['total']==1 and result['items'][0]['id']==output['id']
    assert result['items'][0]['url']==f"/documents/{output['id']}"
    assert result['items'][0]['waiting_since']


def test_support_pagination_exact_totals_beyond_one_page(workspace):
    c,u,unit,_=workspace;item=case(c,u[0],unit)
    for n in range(27):propose(c,u[0],item,unit,title=f'Contribution {n}')
    first=support.report(c,u[1],{'metric':'unassigned'})
    second=support.report(c,u[1],{'metric':'unassigned','page':2})
    assert first['total']==second['total']==27
    assert len(first['items'])==25 and len(second['items'])==2
    assert first['next_url'] and not second['next_url'] and second['previous_url']
    assert not {i['id'] for i in first['items']} & {i['id'] for i in second['items']}


def test_support_read_only_disabled_work_and_closed_migration(workspace):
    c,u,unit,_=workspace
    doc=legacy_setup(c,u,unit);migrate(c,u,doc)
    assert support.report(c,u[1])['managed_count']==1
    # Historical closed migrated workflow should not become a live support backlog.
    c.execute("UPDATE document SET status='closed' WHERE id=?",(doc['id'],));c.commit()
    assert support.report(c,u[1])['managed_count']==0
    case(c,u[0],unit)
    st.set_setting(c,'work.enabled','0')
    before=c.total_changes
    assert support.report(c,u[1])['managed_count']==1
    assert c.total_changes==before and not c.in_transaction


@pytest.mark.parametrize('values',[{'metric':'private'},{'unit':'-1'},{'unit':'1 OR 1=1'},{'page':'0'},{'page':'99999999999999999999999'}])
def test_support_invalid_filters(workspace,values):
    c,u,unit,_=workspace
    with pytest.raises(ValueError):support.report(c,u[1],values)


def test_support_http_counts_links_escape_and_revocation(workspace,app_mod,monkeypatch):
    from starlette.testclient import TestClient
    c,u,unit,path=workspace;monkeypatch.setattr(app_mod,'DB',path)
    item=case(c,u[0],unit);task=propose(c,u[0],item,unit,title='<script>unsafe()</script>')
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME,session_token(u[1]))
        page=client.get('/work/support?metric=unassigned')
        assert page.status_code==200,page.text
        assert '&lt;script&gt;unsafe()&lt;/script&gt;' in page.text
        assert f"/work/{item['id']}#task-{task['id']}" in page.text
        assert 'Unassigned contributions · 1 contribution' in page.text
        assert client.get('/work/support?metric=invalid').status_code==400
        c.execute("UPDATE document_role_grant SET revoked_at='2026-10-17' WHERE user_id=?",(u[1]['id'],));c.commit()
        page=client.get('/work/support?metric=unassigned')
        assert page.status_code==200 and 'unsafe()' not in page.text


def test_support_completed_case_disappears_and_reopening_restores(workspace):
    c,u,unit,_=workspace;item=inbox_case(c,u,unit)
    completion.configure(c,u[1],item['id'],item['revision'],'internal',[],'Internal work completed')
    assert support.report(c,u[1])['managed_count']==1
    finish_case(c,u,item)
    assert support.report(c,u[1])['managed_count']==0
    item=work.get(c,u[1],item['id'])
    completion.reopen(c,u[2],item['id'],item['revision'],'Follow-up is needed')
    assert support.report(c,u[1])['managed_count']==1


def test_support_required_deadline_risk_does_not_use_reference_deadlines(workspace):
    c,u,unit,_=workspace;source,output,item,task=completion_fixture(workspace)
    c.execute("UPDATE document SET due_date='2026-10-01' WHERE id=?",(source['id'],));c.commit()
    baseline=support.report(c,u[1],today=date(2026,10,20))
    assert support_counts(baseline)['risk']==0  # incoming reference is not declared required
    c.execute("UPDATE document SET due_date='2026-10-01' WHERE id=?",(output['id'],));c.commit()
    result=support.report(c,u[1],today=date(2026,10,20))
    assert support_counts(result)['risk']==1
    assert result['items'][0]['reasons']==['Required official record deadline overdue']
