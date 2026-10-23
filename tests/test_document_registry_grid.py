"""The grid shares registry authority/search semantics and returns bounded, read-only pages."""
import pytest

import documents as docs
import documents_grid as grid
import documents_permissions as permissions
import storage as st
from tests.test_documents import registry, register
from tests.test_document_registry_pagination import mixed, QUEUES, seed_many
from tests.document_registry_reference import legacy_visible


@pytest.mark.parametrize('queue', QUEUES)
@pytest.mark.parametrize('query', ['', 'Needle', 'Watershed', 'alias receipt'])
def test_grid_selection_matches_existing_registry(mixed, queue, query):
    conn, users, _, _, _ = mixed
    for user in users:
        if queue == 'instruction' and not permissions.director(conn, user):
            with pytest.raises(permissions.Denied):
                grid.page(conn, user, {'queue': queue, 'q': query})
            continue
        expected = legacy_visible(conn, user, '' if queue == 'instruction' else query, queue)
        result = grid.page(conn, user, {'queue': queue, 'q': query})
        assert result['last_row'] == len(expected)
        assert [d['id'] for d in result['data']] == [d['id'] for d in expected[:30]]
        for actual, old in zip(result['data'], expected):
            assert actual.get('search_excerpt') == old.get('search_excerpt')
            assert actual.get('search_source') == old.get('search_source')


def test_sort_and_filter_apply_before_limit_and_only_return_display_fields(registry, monkeypatch):
    conn, users, unit, _ = registry
    ids = seed_many(conn, users[0], unit, 65)
    seed_many(conn, users[0], unit, 50, subject='Hidden', visibility='restricted')
    for index, doc_id in enumerate(ids):
        conn.execute('UPDATE document SET due_date=?,status=? WHERE id=?',
                     (f'2026-{12-index//28:02d}-{28-index%28:02d}', 'in_action' if index % 2 else 'registered', doc_id))
    conn.commit()
    calls, original = [], grid.rows
    def measured(conn, sql, values):
        result = original(conn, sql, values)
        calls.append(len(result))
        return result
    monkeypatch.setattr(grid, 'rows', measured)
    first = grid.page(conn, users[4], {'sort': 'due_date', 'dir': 'asc', 'status': 'registered'})
    second = grid.page(conn, users[4], {'sort': 'due_date', 'dir': 'asc', 'status': 'registered', 'page': '2'})
    expected = [row[0] for row in conn.execute("SELECT id FROM document WHERE visibility='bureau' AND status='registered' ORDER BY due_date,id DESC")]
    assert first['last_row'] == 33 and first['last_page'] == 2
    assert [r['id'] for r in first['data'] + second['data']] == expected
    assert calls == [30, 3]
    assert all(set(row) == {'id', 'number', 'subject', 'verification', 'status', 'due_date',
                           'archived_at', 'reconcile', 'lead', 'registered', 'gmail_imported',
                           'deadline_state', 'deadline_label'} for row in first['data'])


def test_missing_deadlines_sort_last_and_ties_are_stable(registry):
    conn, users, unit, _ = registry
    ids = seed_many(conn, users[0], unit, 4)
    for doc_id, due in zip(ids, [None, '2026-10-20', '', '2026-10-20']):
        conn.execute('UPDATE document SET due_date=? WHERE id=?', (due, doc_id))
    conn.commit()
    for direction in ('asc', 'desc'):
        result = grid.page(conn, users[4], {'sort': 'due_date', 'dir': direction})
        assert [r['id'] for r in result['data']] == [ids[3], ids[1], ids[2], ids[0]]


def test_each_request_rechecks_visibility_and_handles_shrinking_last_page(registry):
    conn, users, unit, _ = registry
    ids = seed_many(conn, users[0], unit, 31)
    assert grid.page(conn, users[4], {'page': '2'})['data'][0]['id'] == ids[0]
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?", (ids[0],))
    conn.commit()
    result = grid.page(conn, users[4], {'page': '2'})
    assert result['last_row'] == 30 and result['last_page'] == result['page'] == 1
    assert ids[0] not in [r['id'] for r in result['data']]


@pytest.mark.parametrize('params', [{'page': '0'}, {'page': '-1'}, {'page': 'bad'}, {'page': '1000001'},
    {'sort': 'sender'}, {'sort': 'subject;DROP TABLE document'}, {'dir': 'desc;SELECT 1'},
    {'status': 'invalid'}, {'verification': 'invalid'}, {'queue': 'invalid'}, {'q': 'x'*121}])
def test_invalid_grid_options_are_rejected(registry, params):
    conn, users, _, _ = registry
    with pytest.raises(ValueError):
        grid.page(conn, users[0], params)


def test_grid_http_authority_cache_and_read_only_contract(app_mod, viewer, admin, client):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    user = st.get_admin_user(conn, 'viewer@test.local')
    doc = docs.register(conn, user, {'subject': 'Private table record', 'type': 'memo', 'direction': 'OUT'})
    before = conn.total_changes
    response = viewer.get('/documents/grid-data')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json()['data'][0]['id'] == doc['id']
    assert admin.get('/documents/grid-data').json()['last_row'] == 0
    assert 'Private table record' not in admin.get('/documents/grid-data').text
    assert viewer.get('/documents/grid-data?sort=invalid').status_code == 400
    assert viewer.get('/documents/grid-data?queue=instruction').status_code == 403
    assert client.get('/documents/grid-data', follow_redirects=False).status_code in (302, 303, 401, 403)
    assert viewer.post('/documents/grid-data').status_code == 405
    assert conn.total_changes == before
    conn.close()
