"""S1.1: synthetic catalog, module grants, transactional audit and HTTP forms."""
import json
import hashlib
import hmac
import re
import sqlite3
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

import auth
import storage as st
import supplies as s
import supplies_permissions as permissions
from supplies_storage import Conflict, Denied, Disabled, Invalid, Missing, transaction
from tests.conftest import session_token


def key():
    return str(uuid4())


def fields(**changes):
    return {'code': 'TEST-PAPER', 'description': 'Synthetic paper', 'unit': 'Ream',
            'critical_level': '5', 'target_level': '20', **changes}


@pytest.fixture
def supplies_db(tmp_path):
    path = str(tmp_path / 'supplies.db')
    c = st.connect(path)
    st.init_db(c)
    users = []
    for i in range(5):
        uid = st.create_admin_user(c, f'supply{i}@example.test', 'unused', 'unused',
                                   'admin' if i == 0 else 'viewer', active=True)
        st.mark_onboarded(c, uid)
        users.append(st.get_admin_user_by_id(c, uid))
    parent = st.add_org_unit(c, 'Synthetic division', 'division', 'TEST/D1')
    child = st.add_org_unit(c, 'Synthetic section', 'section', 'TEST/D1/S1')
    sibling = st.add_org_unit(c, 'Different division', 'division', 'TEST/D10')
    yield c, users, (parent, child, sibling), path
    c.close()


def reader(c, users):
    """A request approver: since Supplies 4.2 the lowest role that may see stock numbers (active items only)."""
    unit = c.execute('SELECT id FROM org_unit ORDER BY id').fetchone()[0]
    s.grant_role(c, users[0], users[2]['id'], 'request_approver', unit_id=unit, operation_key=key())
    return users[2]


def setup_catalog(c, users):
    grant = s.grant_role(c, users[0], users[1]['id'], 'custodian', operation_key=key())
    s.set_enabled(c, users[0], '1', expected_revision=0, operation_key=key())
    return grant


def create(c, user, **changes):
    return s.create_item(c, user, fields(**changes), operation_key=key())


def test_default_off_independent_flags_and_repeat_install(supplies_db):
    c, u, _, _ = supplies_db
    assert not s.enabled(c)
    s.grant_role(c, u[0], u[1]['id'], 'custodian', operation_key=key())
    with pytest.raises(Disabled):
        create(c, u[1])
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0] == 0
    s.set_enabled(c, u[0], '1', expected_revision=0, operation_key=key())
    item = create(c, u[1])
    for setting in ('documents.enabled', 'work.enabled'):
        st.set_setting(c, setting, '0')
    before = {t: c.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall()
              for t in ('supply_item', 'supply_role_grant', 'supply_event', 'supply_operation')}
    st.init_db(c)
    st.init_db(c)
    assert s.enabled(c)
    assert s.get_item(c, u[2], item['id']) == item
    assert before == {t: c.execute(f'SELECT * FROM {t} ORDER BY 1').fetchall() for t in before}
    s.set_enabled(c, u[0], '0', expected_revision=1, operation_key=key())
    assert s.get_item(c, u[2], item['id']) == item
    with pytest.raises(Disabled):
        s.update_item(c, u[1], item['id'], fields(), expected_revision=1, operation_key=key())
    assert c.execute('SELECT COUNT(*) FROM supply_stock_movement').fetchone()[0] == 0


def test_current_roles_no_technical_admin_or_stale_cookie_bypass(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    for who in (u[0], u[2], {**u[2], 'role': 'admin'}):
        with pytest.raises(Denied):
            create(c, who)
    with pytest.raises(Denied):
        s.grant_role(c, {**u[2], 'role': 'admin'}, u[2]['id'], 'custodian', operation_key=key())
    c.execute("UPDATE admin_user SET role='viewer' WHERE id=?", (u[0]['id'],))
    c.commit()
    with pytest.raises(Denied):
        s.set_enabled(c, u[0], '0', expected_revision=1, operation_key=key())
    c.execute('UPDATE admin_user SET active=0 WHERE id=?', (u[1]['id'],))
    c.commit()
    with pytest.raises(Denied):
        create(c, u[1])
    with pytest.raises(Denied):
        s.catalog(c, u[1])
    with pytest.raises(Denied):
        permissions.require_actor(c, {'id': True, 'role': 'admin'})


def test_scoped_grants_revocation_and_duplicate_null_scope(supplies_db):
    c, u, units, _ = supplies_db
    parent, child, sibling = units
    grant = s.grant_role(c, u[0], u[1]['id'], 'request_approver', parent, operation_key=key())
    assert permissions.has_role(c, u[1], 'request_approver', parent)
    assert permissions.has_role(c, u[1], 'request_approver', child)
    assert not permissions.has_role(c, u[1], 'request_approver', sibling)
    assert not permissions.has_role(c, u[1], 'request_approver')
    assert not permissions.scope_contains(c, None, child)
    for role, unit in [('request_approver', None), ('request_approver', 999999), ('custodian', parent), ('unknown', None)]:
        with pytest.raises(Invalid):
            s.grant_role(c, u[0], u[2]['id'], role, unit, operation_key=key())
    custodian = s.grant_role(c, u[0], u[2]['id'], 'custodian', operation_key=key())
    with pytest.raises(Conflict):
        s.grant_role(c, u[0], u[2]['id'], 'custodian', operation_key=key())
    with pytest.raises(sqlite3.IntegrityError):
        c.execute('''INSERT INTO supply_role_grant(user_id,role,granted_by,created_at)
          VALUES (?,'custodian',?,'synthetic')''', (u[2]['id'], u[0]['id']))
    c.rollback()
    s.revoke_role(c, u[0], grant['id'], expected_revision=1, operation_key=key())
    assert not permissions.has_role(c, u[1], 'request_approver', child)
    assert c.execute('SELECT revoked_at FROM supply_role_grant WHERE id=?', (grant['id'],)).fetchone()[0]
    s.revoke_role(c, u[0], custodian['id'], expected_revision=1, operation_key=key())
    assert not permissions.has_role(c, u[2], 'custodian')
    s.grant_role(c, u[0], u[2]['id'], 'custodian', operation_key=key())
    assert permissions.has_role(c, u[2], 'custodian')


def test_replay_conflicts_and_stale_revisions(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    op = key()
    item = s.create_item(c, u[1], fields(), operation_key=op)
    assert s.create_item(c, u[1], fields(), operation_key=op) == item
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0] == 1
    with pytest.raises(Conflict):
        s.create_item(c, u[1], fields(description='Different'), operation_key=op)
    with pytest.raises(Conflict):
        create(c, u[1], code='test-paper')
    update_key = key()
    updated = s.update_item(c, u[1], item['id'], fields(description='Updated'),
                            expected_revision=1, operation_key=update_key)
    assert updated['revision'] == 2
    assert s.update_item(c, u[1], item['id'], fields(description='Updated'),
                         expected_revision=1, operation_key=update_key) == updated
    with pytest.raises(Conflict):
        s.update_item(c, u[1], item['id'], fields(), expected_revision=1, operation_key=key())
    grant = c.execute("SELECT id FROM supply_role_grant WHERE role='custodian'").fetchone()[0]
    s.revoke_role(c, u[0], grant, expected_revision=1, operation_key=key())
    with pytest.raises(Denied):
        s.create_item(c, u[1], fields(), operation_key=op)


def test_configuration_replays_and_stale_decisions_do_not_restore_old_state(supplies_db):
    c, u, _, _ = supplies_db
    grant_key, enable_key, revoke_key = key(), key(), key()
    grant = s.grant_role(c, u[0], u[1]['id'], 'custodian', operation_key=grant_key)
    assert s.grant_role(c, u[0], u[1]['id'], 'custodian', operation_key=grant_key) == grant
    enabled = s.set_enabled(c, u[0], '1', expected_revision=0, operation_key=enable_key)
    assert s.set_enabled(c, u[0], '1', expected_revision=0, operation_key=enable_key) == enabled
    with pytest.raises(Conflict):
        s.set_enabled(c, u[0], '0', expected_revision=0, operation_key=key())
    s.set_enabled(c, u[0], '0', expected_revision=1, operation_key=key())
    assert s.set_enabled(c, u[0], '1', expected_revision=0, operation_key=enable_key) == enabled
    assert not s.enabled(c)
    revoked = s.revoke_role(c, u[0], grant['id'], expected_revision=1, operation_key=revoke_key)
    assert s.revoke_role(c, u[0], grant['id'], expected_revision=1, operation_key=revoke_key) == revoked
    assert s.grant_role(c, u[0], u[1]['id'], 'custodian', operation_key=grant_key) == grant
    assert not permissions.has_role(c, u[1], 'custodian')
    with pytest.raises(Conflict):
        s.revoke_role(c, u[0], grant['id'], expected_revision=1, operation_key=key())
    with pytest.raises(Invalid):
        s.grant_role(c, u[0], 999999, 'custodian', operation_key=key())
    with pytest.raises(Invalid):
        s.grant_role(c, u[0], u[2]['id'], 'custodian', operation_key='invalid-key')
    assert c.execute('SELECT COUNT(*) FROM supply_event').fetchone()[0] == 4


@pytest.mark.parametrize('change', [
    {'critical_level': '-1'}, {'critical_level': '1.5'}, {'critical_level': True},
    {'critical_level': 2.0}, {'critical_level': '2147483648'}, {'critical_level': '1e3'},
    {'target_level': '4'}, {'target_level': '-1'}, {'target_level': False},
    {'code': ' '}, {'code': 'A B'}, {'code': 'x' * 41}, {'unit': ''},
    {'unit': 'x' * 41}, {'description': ''}, {'description': 'x' * 241},
])
def test_invalid_fields_do_not_change_inventory_or_history(supplies_db, change):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    count = c.execute('SELECT COUNT(*) FROM supply_event').fetchone()[0]
    with pytest.raises(Invalid):
        create(c, u[1], **change)
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM supply_event').fetchone()[0] == count
    assert not c.in_transaction


def test_inactive_visibility_pagination_and_empty_target(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1], critical_level='0', target_level='')
    assert item['target_level'] is None
    s.deactivate_item(c, u[1], item['id'], expected_revision=1, operation_key=key(), reason='Retired')
    assert s.catalog(c, u[2], include_inactive=True)['count'] == 0
    with pytest.raises(Missing):
        s.get_item(c, u[2], item['id'])
    assert not s.get_item(c, u[1], item['id'])['active']
    s.grant_role(c, u[0], u[3]['id'], 'auditor', operation_key=key())
    assert s.get_item(c, u[3], item['id'])['code'] == 'TEST-PAPER'
    with pytest.raises(Denied):
        create(c, u[3])
    for i in range(51):
        create(c, u[1], code=f'CODE-{i:03}')
    first = s.catalog(c, u[2])
    assert first['count'] == 51 and len(first['items']) == 50 and first['has_next']
    assert len(s.catalog(c, u[2], page=2)['items']) == 1
    assert s.catalog(c, u[2], query='%')['count'] == 0


def test_audit_failure_rolls_back_and_history_is_immutable(supplies_db, monkeypatch):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    before = c.execute('SELECT COUNT(*) FROM supply_operation').fetchone()[0]
    def failed_audit(*args, **kwargs):
        raise RuntimeError('Synthetic audit failure')
    with monkeypatch.context() as patch:
        patch.setattr(st, 'audit', failed_audit)
        with pytest.raises(RuntimeError, match='audit failure'):
            create(c, u[1])
        with pytest.raises(RuntimeError, match='audit failure'):
            s.set_enabled(c, u[0], '0', expected_revision=1, operation_key=key())
    assert s.enabled(c)
    assert c.execute('SELECT COUNT(*) FROM supply_item').fetchone()[0] == 0
    assert c.execute('SELECT COUNT(*) FROM supply_operation').fetchone()[0] == before
    item = create(c, u[1])
    event = c.execute("SELECT detail_json FROM supply_event WHERE action='item_create'").fetchone()[0]
    assert json.loads(event)['code'] == item['code']
    for table in ('supply_event', 'supply_operation'):
        with pytest.raises(sqlite3.IntegrityError):
            c.execute(f'DELETE FROM {table}')
        c.rollback()


def test_transaction_ownership_and_busy_failure_are_explicit(supplies_db):
    c, _, _, path = supplies_db
    c.execute("INSERT INTO app_setting VALUES ('synthetic.caller','keep')")
    with pytest.raises(RuntimeError, match='clean connection'):
        with transaction(c):
            pass
    assert c.in_transaction
    c.rollback()
    other = st.connect(path)
    other.execute('PRAGMA busy_timeout=1')
    try:
        c.execute('BEGIN IMMEDIATE')
        with pytest.raises(Conflict, match='busy'):
            with transaction(other):
                pass
        assert not other.in_transaction
    finally:
        c.rollback()
        other.close()


def test_unit_change_guard_when_stock_movement_exists(supplies_db):
    c, u, _, _ = supplies_db
    setup_catalog(c, u)
    item = create(c, u[1])
    import supplies_stock as stock
    stock.post_opening(c, u[1], item['id'], {'quantity': '0', 'effective_date': '2026-10-19',
        'reason': 'Synthetic physical count'}, expected_revision=1, operation_key=key())
    with pytest.raises(Conflict, match='unit is fixed'):
        s.update_item(c, u[1], item['id'], fields(unit='Piece'), expected_revision=1, operation_key=key())
    assert s.get_item(c, u[1], item['id'])['unit'] == 'Ream'


def hidden(html, name):
    return re.search(r'name="' + name + r'" value="([^"]+)"', html).group(1)


def test_http_catalog_configuration_and_permission_boundaries(app_mod, supplies_db):
    c, u, _, path = supplies_db
    original_db = app_mod.DB
    app_mod.DB = path
    try:
        with TestClient(app_mod.app) as client:
            def login(user):
                client.cookies.set(auth.COOKIE_NAME, session_token(user))
            login(u[0])
            settings = client.get('/supplies/settings')
            assert settings.status_code == 200 and 'Supplies settings' in settings.text
            token = hidden(settings.text, 'csrf')
            assert client.post('/supplies/settings/grants', data={
                'csrf': token, 'operation_key': key(), 'user_id': u[1]['id'], 'role': 'custodian', 'unit_id': ''},
                follow_redirects=False).status_code == 303
            assert client.post('/supplies/settings/enabled', data={
                'csrf': token, 'operation_key': key(), 'enabled': '1', 'revision': '0'},
                follow_redirects=False).status_code == 303
            assert client.post('/supplies/items', data={**fields(), 'csrf': token,
                'operation_key': key()}).status_code == 403
            login(u[1])
            catalog = client.get('/supplies/items')
            assert catalog.status_code == 200 and 'Add supply item' in catalog.text
            token = hidden(catalog.text, 'csrf')
            assert 'aria-current="page">Supplies' in catalog.text
            data = {**fields(description='<script>bad()</script>'), 'csrf': token, 'operation_key': key()}
            assert client.post('/supplies/items', data={**data, 'csrf': 'invalid'}).status_code == 403
            assert client.post('/supplies/items', data=data, headers={'Origin': 'https://foreign.example'}).status_code == 403
            response = client.post('/supplies/items', data=data, follow_redirects=False)
            assert response.status_code == 303
            target = response.headers['location']
            detail = client.get(target)
            assert detail.status_code == 200 and '&lt;script&gt;bad()&lt;/script&gt;' in detail.text
            assert '<script>bad()</script>' not in detail.text
            assert 'Stock balances are not yet recorded' in detail.text
            assert client.post('/supplies/items', data=data, follow_redirects=False).headers['location'] == target
            assert client.get('/supplies/settings').status_code == 403
            invalid = client.post(target + '/update', data={**data, 'critical_level': '-1',
                'revision': '1', 'operation_key': key()})
            assert invalid.status_code == 422 and 'whole number' in invalid.text
            update = {**fields(description='Changed'), 'csrf': token, 'revision': '1', 'operation_key': key()}
            assert client.post(target + '/update', data=update, follow_redirects=False).status_code == 303
            assert client.post(target + '/update', data={**update, 'operation_key': key()}).status_code == 409
            login(u[2])
            staff_catalog = client.get('/supplies/items?q=paper', follow_redirects=False)      # Supplies 4.1: staff are sent to the request grid
            assert staff_catalog.status_code == 303 and staff_catalog.headers['location'] == '/supplies/requests/new?q=paper'
            assert client.get('/supplies/items', follow_redirects=False).headers['location'] == '/supplies/requests/new'
            assert client.get('/supplies/settings').status_code == 403
            assert client.get('/supplies/items/999999', follow_redirects=False).status_code == 303
            login(u[0])
            current_token = hidden(client.get('/supplies/settings').text, 'csrf')
            # Session-bound tokens cannot be copied to another logged-in account.
            assert client.post('/supplies/settings/enabled', data={'csrf': token,
                'operation_key': key(), 'enabled': '0', 'revision': '1'}).status_code == 403
            assert client.post('/supplies/settings/enabled', data={'csrf': current_token,
                'operation_key': key(), 'enabled': '0', 'revision': '1'}, follow_redirects=False).status_code == 303
            login(u[1])
            disabled = client.get('/supplies/items')
            assert 'Supplies changes are disabled' in disabled.text and 'Add supply item' not in disabled.text
            valid_csrf = hmac.new(auth._secret(), ('supplies:' + client.cookies.get(auth.COOKIE_NAME)).encode(), hashlib.sha256).hexdigest()
            assert client.post('/supplies/items', data={**fields(code='NEW'),
                'csrf': valid_csrf, 'operation_key': key()}).status_code == 409
            login(u[0])
            admin_csrf = hidden(client.get('/supplies/settings').text, 'csrf')
            gid = c.execute("SELECT id FROM supply_role_grant WHERE role='custodian'").fetchone()[0]
            assert client.post(f'/supplies/settings/grants/{gid}/revoke', data={
                'csrf': admin_csrf, 'operation_key': key(), 'revision': '1'},
                follow_redirects=False).status_code == 303
            assert not permissions.has_role(c, u[1], 'custodian')
    finally:
        app_mod.DB = original_db
