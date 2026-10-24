"""Current-view exports retain authorization, selection, ordering and column scope."""
import csv
import io
from datetime import date

import pytest

import documents_grid as grid
import documents_permissions as permissions
import storage as st
from tests.test_documents import registry
from tests.test_document_registry_pagination import mixed, QUEUES, seed_many
from tests.document_registry_reference import legacy_visible


def exported(conn, user, options):
    content, count = grid.export_csv(conn, user, options)
    assert content.startswith('\ufeff')
    return list(csv.reader(io.StringIO(content.removeprefix('\ufeff')))), count


@pytest.mark.parametrize('queue', QUEUES)
def test_export_matches_independent_queue_authority_reference(mixed, queue):
    conn, users, _, _, _ = mixed
    for user in users:
        options = {'queue': queue, 'columns': 'number,subject'}
        if queue == 'instruction' and not permissions.director(conn, user):
            with pytest.raises(permissions.Denied):
                exported(conn, user, options)
            continue
        expected = legacy_visible(conn, user, '', queue)
        data, count = exported(conn, user, options)
        assert data[0] == ['Number', 'Subject']
        assert count == len(expected)
        assert data[1:] == [[r['number'], r['subject']] for r in expected]


def test_all_pages_combined_filters_columns_sort_and_revoked_access(registry, monkeypatch):
    conn, users, unit, _ = registry
    monkeypatch.setattr(grid.tz, 'today_local', lambda: date(2026, 10, 23))
    ids = seed_many(conn, users[0], unit, 65, subject='Exportneedle')
    seed_many(conn, users[0], unit, 10, subject='Exportneedle hidden', visibility='restricted')
    seed_many(conn, users[0], unit, 10, subject='Unrelated')
    conn.execute("UPDATE document SET due_date='2026-10-22',status='in_action'")
    conn.execute("UPDATE document SET due_date='2026-10-30' WHERE id>? AND id<=?", (ids[30], ids[-1]))
    conn.commit()
    options = {'queue': 'OUT', 'q': 'Exportneedle', 'status': 'in_action', 'verification': 'verified',
               'deadline': 'overdue', 'sort': 'number', 'dir': 'asc', 'columns': 'subject,number,due_date'}
    expected = sorted([(f'Exportneedle {i:04d}', f'REG-{i}', '2026-10-22') for i in ids[:31]], key=lambda r:r[1].lower())
    data, count = exported(conn, users[4], options)
    assert count == 31 and data[0] == ['Subject', 'Number', 'Due date']
    assert data[1:] == [list(r) for r in expected]
    assert len(grid.page(conn, users[4], options)['data']) == 30
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?", (ids[0],))
    conn.commit()
    data, count = exported(conn, users[4], options)
    assert count == 30 and f'REG-{ids[0]}' not in [r[1] for r in data[1:]]
    empty, count = exported(conn, users[4], {**options, 'verification': 'pending'})
    assert count == 0 and empty == [data[0]]


def test_export_formula_text_unicode_quoting_and_unknown_dates(registry):
    conn, users, unit, _ = registry
    dangerous = ['=HYPERLINK("x")', ' +SUM(1,2)', '-1+1', '@SUM(1,2)', '\t=cmd', '\n=cmd']
    subjects = dangerous + ['Pangalan ñ, "quote"\nsecond line']
    ids = seed_many(conn, users[0], unit, len(subjects), verified=False)
    for identifier, subject in zip(ids, subjects):
        conn.execute('UPDATE document SET subject=?,due_date=NULL WHERE id=?', (subject, identifier))
    conn.commit()
    data, count = exported(conn, users[0], {'columns': 'number,subject,verification,status,due_date,lead',
                                          'sort': 'registered', 'dir': 'asc'})
    assert count == len(subjects)
    assert [r[1] for r in data[1:]] == ["'" + text for text in dangerous] + subjects[-1:]
    assert all(r[2:] == ['Awaiting verification', 'registered', 'Unknown', 'Unresolved'] for r in data[1:])


@pytest.mark.parametrize('options', [
    {'columns': ''}, {'columns': 'subject'}, {'columns': 'number,number'},
    {'columns': 'number,creator_id'}, {'columns': 'number;DROP TABLE document'},
    {'sort': 'number;DROP TABLE document'}, {'dir': 'sideways'}, {'queue': 'elsewhere'},
    {'deadline': 'due_soon_only'}, {'status': 'bad'}, {'verification': 'bad'}, {'q': 'x'*121}])
def test_rejects_invalid_export_options(registry, options):
    conn, users, _, _ = registry
    with pytest.raises(ValueError):
        exported(conn, users[0], options)


def test_export_limit_refuses_partial_files_and_counts_only_authorized_matches(registry, monkeypatch):
    conn, users, unit, _ = registry
    monkeypatch.setattr(grid, 'MAX_EXPORT_ROWS', 2)
    ids = seed_many(conn, users[0], unit, 3)
    with pytest.raises(ValueError, match='Narrow'):
        exported(conn, users[4], {})
    conn.execute("UPDATE document SET visibility='restricted' WHERE id=?", (ids[0],))
    conn.commit()
    _, count = exported(conn, users[4], {})
    assert count == 2


def test_export_http_headers_fresh_access_validation_and_login(app_mod, viewer, client):
    conn = st.connect(app_mod.DB)
    st.set_setting(conn, 'documents.enabled', '1')
    user = st.get_admin_user(conn, 'viewer@test.local')
    unit = conn.execute('SELECT id FROM org_unit LIMIT 1').fetchone()[0]
    ids = seed_many(conn, user, unit, 2)
    response = viewer.get('/documents/grid-export.csv?columns=number,subject&sort=subject&dir=asc')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['pragma'] == 'no-cache'
    assert response.headers['x-export-rows'] == '2'
    assert response.headers['content-type'].startswith('text/csv')
    assert 'attachment; filename="document-view.csv"' == response.headers['content-disposition']
    assert response.content.startswith(b'\xef\xbb\xbf')
    other = conn.execute('SELECT id FROM admin_user WHERE id<>? LIMIT 1', (user['id'],)).fetchone()[0]
    conn.execute("UPDATE document SET visibility='restricted',creator_id=? WHERE id=?", (other, ids[0]))
    conn.commit()
    assert viewer.get('/documents/grid-export.csv').headers['x-export-rows'] == '1'
    invalid = viewer.get('/documents/grid-export.csv?columns=number,secret')
    assert invalid.status_code == 400 and invalid.headers['cache-control'] == 'no-store'
    assert viewer.get('/documents/grid-export.csv?queue=instruction').status_code == 403
    assert client.get('/documents/grid-export.csv', follow_redirects=False).status_code in (302,303,401,403)
    conn.close()
