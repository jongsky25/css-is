"""P1.1: synthetic work items, no external files, signatures, or mail."""
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
        result.cookies.set(auth.COOKIE_NAME, auth.make_token(user))
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
            client.cookies.set(auth.COOKIE_NAME, auth.make_token(user))
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
        client.cookies.set(auth.COOKIE_NAME,auth.make_token(u[3]))
        page=client.get(f"/documents/{doc['id']}")
        assert page.status_code==200 and 'Confidential collaborative evidence' in page.text
        assert f'/work/{cid}' in page.text and 'Assignment number' not in page.text
        client.cookies.set(auth.COOKIE_NAME,auth.make_token(u[4]))
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
        client.cookies.set(auth.COOKIE_NAME,auth.make_token(u[3]))
        page=client.get('/work/mine')
        assert page.status_code==200 and 'Prepare the regional input' in page.text
        assert 'October 23, 2026' in page.text and 'Acknowledge and start' in page.text
        assert 'Prepare the regional input' in client.get('/').text
        assert 'Prepare the regional input' not in client.get('/work/mine?view=waiting').text.split('<div class="work-wrap">',1)[1]
        assert client.get('/work/mine?view=bogus').status_code==400
        assert client.get('/work/mine?before=-3').status_code==400
        client.cookies.set(auth.COOKIE_NAME,auth.make_token(u[4]))
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
