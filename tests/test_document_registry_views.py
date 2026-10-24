"""Personal registry preferences never confer access to saved records."""
from copy import deepcopy
from datetime import date
import re

import pytest

import documents_grid as grid
import documents_permissions as permissions
import storage as st
from tests.test_documents import registry, register


def state(**changes):
    return {'schema': 1, 'queue': 'all', 'q': '', 'status': '', 'verification': '',
            'sort': 'registered', 'dir': 'desc',
            'columns': {field: {'visible': True} for field in grid.VISIBLE_COLUMNS}, **changes}


def create(conn, user, name='My view', **changes):
    result = grid.save_view(conn, user, {'action': 'create', 'name': name, 'state': state(**changes)})
    return next(view for view in result['views'] if view['id'] == result['saved_id'])


def test_views_are_private_persist_across_connections_and_do_not_cache_records(registry):
    conn, users, unit, path = registry
    doc = register(conn, users[0], unit, 'OUT', visibility='bureau')
    conn.execute("UPDATE document SET verification='verified',visibility='bureau' WHERE id=?", (doc['id'],))
    conn.commit()
    view = create(conn, users[4], 'Visible records', sort='subject', dir='asc')
    assert grid.views(conn, users[0]) == []
    other = st.connect(path)
    try:
        assert grid.views(other, users[4]) == [view]
        assert grid.page(other, users[4], view['state'])['last_row'] == 1
        conn.execute("UPDATE document SET visibility='restricted' WHERE id=?", (doc['id'],))
        conn.commit()
        assert grid.page(other, users[4], view['state'])['last_row'] == 0
        st.init_db(other)
        assert grid.views(other, users[4]) == [view]
        encoded = other.execute('SELECT state_json FROM document_registry_view').fetchone()[0]
        assert doc['subject'] not in encoded and 'creator_id' not in encoded
    finally:
        other.close()
    for action in ('update', 'delete'):
        with pytest.raises(ValueError, match='not found'):
            grid.save_view(conn, users[0], {'action': action, 'id': view['id'], 'revision': 1,
                           'name': 'Stolen', 'state': state()})
    assert grid.views(conn, users[4]) == [view]


def test_updates_and_deletes_reject_stale_revisions_and_quota_is_per_account(registry):
    conn, users, _, _ = registry
    view = create(conn, users[0])
    changed = deepcopy(view['state'])
    changed['columns']['lead'] = {'visible': False}
    changed['columns']['number']['width'] = 210
    result = grid.save_view(conn, users[0], {'action': 'update', 'id': view['id'], 'revision': 1,
                                          'name': 'Renamed', 'state': changed})
    assert result['views'][0]['revision'] == 2
    assert result['views'][0]['state'] == changed
    for action in ('update', 'delete'):
        with pytest.raises(grid.ViewConflict):
            grid.save_view(conn, users[0], {'action': action, 'id': view['id'], 'revision': 1,
                                          'name': 'Lost update', 'state': state()})
    with pytest.raises(ValueError, match='already have'):
        create(conn, users[0], 'renamed')
    for index in range(9):
        create(conn, users[0], f'View {index}')
    with pytest.raises(ValueError, match='up to 10'):
        create(conn, users[0], 'Overflow')
    create(conn, users[1], 'Renamed')
    grid.save_view(conn, users[0], {'action': 'delete', 'id': view['id'], 'revision': 2})
    create(conn, users[0], 'Replacement')
    assert len(grid.views(conn, users[0])) == 10


def test_deleted_view_id_cannot_target_a_replacement_from_an_old_tab(registry):
    conn, users, _, _ = registry
    old = create(conn, users[0], 'Old view')
    grid.save_view(conn, users[0], {'action': 'delete', 'id': old['id'], 'revision': 1})
    replacement = create(conn, users[0], 'Replacement')
    assert replacement['id'] != old['id']
    for action in ('delete', 'update'):
        with pytest.raises(ValueError, match='not found'):
            grid.save_view(conn, users[0], {'action': action, 'id': old['id'], 'revision': 1,
                                          'name': 'Stale write', 'state': state()})
    assert grid.views(conn, users[0]) == [replacement]


@pytest.mark.parametrize('identifier', [True, 1.5, 0, -1, 9223372036854775808])
def test_invalid_view_identifiers_are_validation_errors(registry, identifier):
    conn, users, _, _ = registry
    with pytest.raises(ValueError):
        grid.save_view(conn, users[0], {'action': 'delete', 'id': identifier, 'revision': 1})


@pytest.mark.parametrize('mutate', [
    lambda v: v.update(schema=2), lambda v: v.update(schema=True),
    lambda v: v.update(queue='elsewhere'), lambda v: v.update(q='x'*121),
    lambda v: v.update(sort='subject; DROP TABLE document'), lambda v: v.update(dir='bad'),
    lambda v: v.update(status='bad'), lambda v: v.update(verification='bad'),
    lambda v: v.update(records=[{'subject': 'Private text'}]),
    lambda v: v['columns']['number'].update(visible=False),
    lambda v: v['columns']['lead'].update(visible='false'),
    lambda v: v['columns']['lead'].update(width=True),
    lambda v: v['columns']['lead'].update(width=4097),
    lambda v: v['columns'].update(sender={'visible': True}),
])
def test_reject_unsafe_or_unsupported_preferences(registry, mutate):
    conn, users, _, _ = registry
    value = state()
    mutate(value)
    with pytest.raises(ValueError):
        grid.save_view(conn, users[0], {'action': 'create', 'name': 'Bad', 'state': value})
    assert grid.views(conn, users[0]) == []


def test_names_identity_and_director_queue_are_validated(registry):
    conn, users, _, _ = registry
    for name in ('', ' ', 'x'*61, 'a\nb', 'a\x00b'):
        with pytest.raises(ValueError):
            create(conn, users[0], name)
    with pytest.raises(permissions.Denied):
        create(conn, users[0], queue='instruction')
    create(conn, users[2], queue='instruction', q='Ignored')
    assert grid.views(conn, users[2])[0]['state']['q'] == ''
    with pytest.raises(ValueError):
        grid.save_view(conn, users[0], {'action': 'create', 'name': 'Forged', 'state': state(), 'user_id': users[1]['id']})
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],))
    conn.commit()
    for operation in (lambda: grid.views(conn, users[0]), lambda: create(conn, users[0])):
        with pytest.raises(permissions.Denied):
            operation()


def test_deadlines_use_working_day_boundary_and_exclude_inactive_records(registry):
    conn, _, _, _ = registry
    st.set_holiday(conn, '2026-10-26', 'Monday holiday')
    records = [{'status': status, 'due_date': due} for status, due in [
        ('in_action', '2026-10-22'), ('in_action', '2026-10-23'),
        ('in_action', '2026-10-29'), ('in_action', '2026-10-30'),
        ('in_action', None), ('closed', '2026-10-22'), ('cancelled', None),
        ('in_action', 'not-a-date')]]
    grid.decorate_deadlines(conn, records, today=date(2026, 10, 23))
    assert [r['deadline_state'] for r in records] == [
        'overdue', 'due_today', 'due_soon', 'scheduled', 'unknown', 'inactive', 'inactive', 'unknown']
    assert [r['deadline_label'] for r in records] == [
        'Overdue', 'Due today', 'Due soon', '', 'Unknown deadline', '', '', 'Unknown deadline']


def test_saved_views_http_csrf_owner_revision_and_no_store(app_mod, viewer, admin, client):
    page = viewer.get('/documents')
    csrf = re.search(r'data-csrf="([a-f0-9]+)"', page.text)[1]
    payload = {'action': 'create', 'name': '<img src=x onerror=alert(1)>', 'state': state()}
    assert viewer.post('/documents/grid-views', json=payload).status_code == 403
    response = viewer.post('/documents/grid-views', json=payload, headers={'X-CSRF-Token': csrf})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    view = response.json()['views'][0]
    assert viewer.get('/documents/grid-views').json()['views'] == [view]
    assert admin.get('/documents/grid-views').json()['views'] == []
    assert viewer.get('/documents/grid-views').headers['cache-control'] == 'no-store'
    assert admin.post('/documents/grid-views', json=payload, headers={'X-CSRF-Token': csrf}).status_code == 403
    delete = {'action': 'delete', 'id': view['id'], 'revision': 2}
    assert viewer.post('/documents/grid-views', json=delete, headers={'X-CSRF-Token': csrf}).status_code == 409
    delete['revision'] = 1
    assert viewer.post('/documents/grid-views', json=delete, headers={'X-CSRF-Token': csrf}).json()['views'] == []
    assert client.get('/documents/grid-views', follow_redirects=False).status_code in (302, 303, 401, 403)


def test_old_saved_views_default_to_all_deadlines_and_new_filters_round_trip(registry):
    import json
    conn, users, _, _ = registry
    old = state()
    conn.execute('INSERT INTO document_registry_view(user_id,name,state_json,created_at,updated_at) VALUES (?,?,?,?,?)',
                 (users[0]['id'], 'Before deadline filters', json.dumps(old), '2026-10-23', '2026-10-23'))
    conn.commit()
    restored = grid.views(conn, users[0])[0]['state']
    assert restored == {**old, 'deadline': '', 'lead_id': '', 'due_from': '', 'due_to': ''}
    for deadline in grid.DEADLINES:
        view = create(conn, users[0], deadline, deadline=deadline)
        assert view['state']['deadline'] == deadline
    for invalid in ('inactive', 'scheduled', 'unknown;DROP TABLE document', None, True, []):
        with pytest.raises(ValueError):
            grid.view_state(state(deadline=invalid))
