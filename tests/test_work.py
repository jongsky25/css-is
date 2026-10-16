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
