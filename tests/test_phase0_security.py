"""Phase 0 security regressions: real login, isolated data, no providers."""
import hashlib
import hmac
import json
import time

import pytest
from starlette.testclient import TestClient

import auth
import documents
import documents_permissions as permissions
import monitoring
import storage as st


@pytest.fixture
def system(app_mod, tmp_path, monkeypatch):
    path = str(tmp_path / 'security.db')
    monkeypatch.setattr(app_mod, 'DB', path)
    monkeypatch.setattr(monitoring, 'LOG_PATH', str(tmp_path / 'requests.log'))
    conn = app_mod.get_conn()
    unit = st.add_org_unit(conn, 'Test section', 'section', 'TEST/D1/S1')
    pw = 'Synthetic-Phase0-Password!'
    hashed, salt = auth.hash_password(pw)
    users = {}
    for name, role in [('admin', 'admin'), ('staff', 'viewer')]:
        rp = st.add_rp(conn, name, True, org_unit_id=unit, designation='Analyst')
        uid = st.create_admin_user(conn, name+'@example.test', hashed, salt, role,
                                   active=True, rp_id=rp)
        st.mark_onboarded(conn, uid)
        users[name] = st.get_admin_user_by_id(conn, uid)
    st.set_setting(conn, 'documents.enabled', '1')
    def login(name='admin'):
        client = TestClient(app_mod.app)
        response = client.post('/login', data={'username': users[name]['username'],
                                               'password': pw}, follow_redirects=False)
        assert response.status_code == 303, response.text
        assert client.cookies.get(auth.COOKIE_NAME)
        return client
    yield app_mod, conn, users, unit, login
    conn.close()


@pytest.mark.parametrize('title', ['Director', 'Division Chief', 'Section Head', ''])
def test_profile_text_cannot_grant_authority_or_document_access(system, title):
    app, conn, users, unit, login = system
    conn.execute("INSERT INTO document_role_grant(user_id,role,created_at) VALUES (?,?,?)",
                 (users['admin']['id'], 'records', '2026-10-19'))
    conn.commit()
    staff = users['staff']
    doc = documents.register(conn, users['admin'], {'subject': 'Private draft',
        'type': 'request', 'unit_id': unit, 'direction': 'IN'})
    restricted = documents.register(conn, users['admin'], {'subject': 'Restricted draft',
        'type': 'request', 'unit_id': unit, 'direction': 'IN'})
    restricted = documents.mutate(conn, users['admin'], restricted['id'],
        restricted['revision'], 'access', {'visibility': 'restricted', 'reason': 'Test'})
    assert not permissions.can_view(conn, staff, doc)
    client = login('staff')
    response = client.post('/me', data={'avatar_kind': 'cat', 'avatar_name': 'Milo',
                                       'designation': title}, follow_redirects=False)
    assert response.status_code == 303
    assert st.get_rp(conn, staff['rp_id'])['designation'] == 'Analyst'
    assert not permissions.director(conn, staff)
    assert not st.user_is_approving_chief(conn, staff)
    assert not st._is_director(conn, staff['id'])
    assert not permissions.can_view(conn, staff, doc)
    assert not permissions.can_view(conn, staff, restricted)
    assert client.get('/documents/'+str(doc['id'])).status_code != 200


def test_profile_cannot_remove_legitimate_directory_authority(system):
    app, conn, users, unit, login = system
    staff = users['staff']
    st.update_rp(conn, staff['rp_id'], designation='Director')
    client = login('staff')
    client.post('/me', data={'avatar_kind': 'cat', 'avatar_name': 'Milo', 'designation': ''})
    assert st.get_rp(conn, staff['rp_id'])['designation'] == 'Director'
    assert permissions.director(conn, staff)
    page = client.get('/me').text
    assert 'readonly' in page.split('id="designation"', 1)[1].split('>', 1)[0]


def test_logout_revokes_only_that_session_and_blocks_replay(system):
    app, conn, users, unit, login = system
    first, second = login(), login()
    retained = first.cookies.get(auth.COOKIE_NAME)
    assert retained != second.cookies.get(auth.COOKIE_NAME)
    assert first.get('/admin/users').status_code == 200
    assert first.post('/logout', follow_redirects=False).status_code == 303
    replay = TestClient(app.app)
    replay.cookies.set(auth.COOKIE_NAME, retained)
    assert replay.get('/admin/users', follow_redirects=False).status_code == 303
    assert replay.post('/admin/feedback/toggle').status_code == 401
    assert second.get('/admin/users').status_code == 200


@pytest.mark.parametrize('change', ['demote', 'password', 'deactivate', 'force_reset',
                                    'rename', 'delete'])
def test_account_changes_revoke_all_sessions_without_render_errors(system, change):
    app, conn, users, unit, login = system
    clients = [login(), login()]
    uid = users['admin']['id']
    if change == 'demote':
        st.set_admin_role(conn, uid, 'viewer')
        st.set_admin_role(conn, uid, 'admin')  # restoring role must not revive cookies
    elif change == 'password':
        hashed, salt = auth.hash_password('Another-Synthetic-Password!')
        st.set_admin_password(conn, uid, hashed, salt)
    elif change == 'deactivate':
        st.set_admin_active(conn, uid, False)
    elif change == 'force_reset':
        conn.execute('UPDATE admin_user SET must_change=1 WHERE id=?', (uid,))
        conn.commit()
    elif change == 'rename':
        st.set_admin_username(conn, uid, 'changed@example.test')
    else:
        conn.execute('DELETE FROM admin_user WHERE id=?', (uid,))
        conn.commit()
    for client in clients:
        for path in ['/admin/users', '/documents', '/me']:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303 and '/login' in response.headers['location']
        assert client.post('/me', data={}).status_code == 401
    assert conn.execute('SELECT count(*) FROM login_session WHERE user_id=?', (uid,)).fetchone()[0] == 0
    if change == 'deactivate':
        st.set_admin_active(conn, uid, True)
        assert clients[0].get('/admin/users', follow_redirects=False).status_code == 303
        assert login().get('/admin/users').status_code == 200


def test_deleted_account_id_reuse_does_not_revive_session(system):
    app, conn, users, unit, login = system
    client = login('staff')
    uid = users['staff']['id']
    conn.execute('DELETE FROM admin_user WHERE id=?', (uid,))
    conn.execute('INSERT INTO admin_user(id,username,pw_hash,salt,role) VALUES (?,?,?,?,?)',
                 (uid, 'replacement@example.test', 'unused', 'unused', 'admin'))
    conn.commit()
    assert client.get('/admin/users', follow_redirects=False).status_code == 303


def test_signed_cookie_role_is_not_authoritative(system):
    app, conn, users, unit, login = system
    # Even a correctly signed/registered token cannot override the database role.
    token = auth.make_token({**users['staff'], 'role': 'admin'})
    st.register_login_session(conn, auth.parse_token(token)); conn.commit()
    client = TestClient(app.app); client.cookies.set(auth.COOKIE_NAME, token)
    assert client.get('/admin/users', follow_redirects=False).status_code == 403


def test_signed_but_unregistered_cookie_is_rejected(system):
    app, conn, users, unit, login = system
    client = TestClient(app.app)
    client.cookies.set(auth.COOKIE_NAME, auth.make_token(users['admin']))
    assert client.get('/admin/users', follow_redirects=False).status_code == 303


def test_session_expiry_is_enforced_in_storage_and_migration_is_idempotent(system):
    app, conn, users, unit, login = system
    client = login()
    st.init_db(conn); st.init_db(conn)
    assert client.get('/admin/users').status_code == 200
    conn.execute('UPDATE login_session SET expires_at=?', (int(time.time())-1,)); conn.commit()
    assert client.get('/admin/users', follow_redirects=False).status_code == 303
    assert login().get('/admin/users').status_code == 200
    assert conn.execute('SELECT count(*) FROM login_session').fetchone()[0] == 1


def test_restore_does_not_resurrect_logged_out_session(system, tmp_path, monkeypatch):
    import backups as bk
    app, conn, users, unit, login = system
    monkeypatch.setattr(bk, 'SCHED_DIR', str(tmp_path / 'backups'))
    client = login()
    retained = client.cookies.get(auth.COOKIE_NAME)
    snapshot = bk.make_backup(app.DB, kind='manual')
    client.post('/logout')
    bk.restore_backup(snapshot['name'], app.DB)
    client.cookies.set(auth.COOKIE_NAME, retained)
    assert client.get('/admin/users', follow_redirects=False).status_code == 303
    assert conn.execute('SELECT count(*) FROM login_session').fetchone()[0] == 0
    assert login().get('/admin/users').status_code == 200


def test_http_restore_of_pre_session_schema_reapplies_migration(system, tmp_path, monkeypatch):
    import backups as bk
    import sqlite3
    from pathlib import Path
    app, conn, users, unit, login = system
    monkeypatch.setattr(bk, 'SCHED_DIR', str(tmp_path / 'backups'))
    client = login()
    snapshot = bk.make_backup(app.DB, kind='manual')
    with sqlite3.connect(Path(bk.SCHED_DIR) / snapshot['name']) as old:
        old.execute('DROP TRIGGER revoke_sessions_on_account_change')
        old.execute('DROP TRIGGER revoke_sessions_on_account_delete')
        old.execute('DROP TABLE login_session')
    response = client.post('/admin/backups/restore', data={'name': snapshot['name'],
                           'confirm': 'RESTORE'}, follow_redirects=False)
    assert response.status_code == 303
    assert 'Restored' in response.headers['location']
    assert client.get('/admin/users', follow_redirects=False).status_code == 303
    assert login().get('/admin/users').status_code == 200


def test_account_change_between_password_check_and_issuance_is_rejected(system):
    app, conn, users, unit, login = system
    verified = users['admin']
    hashed, salt = auth.hash_password('Changed-Before-Issuance!')
    st.set_admin_password(conn, verified['id'], hashed, salt)
    assert app._issue_session(verified) is None


def signed_payload(payload):
    body = auth._b64e(json.dumps(payload).encode())
    return body+'.'+hmac.new(auth._secret(), body.encode(), hashlib.sha256).hexdigest()


@pytest.mark.parametrize('patch', [{'uid': True}, {'uid': -1}, {'iat': 'bad'},
    {'iat': True}, {'iat': int(time.time())+3600}, {'sid': None}, {'r': []}, {'u': None}, {'v': 1}])
def test_malformed_signed_session_is_rejected(patch):
    payload = {'uid': 1, 'u': 'test@example.test', 'r': 'viewer', 'iat': int(time.time()),
               'v': 2, 'sid': 'a'*64}
    assert auth.parse_token(signed_payload({**payload, **patch})) is None


@pytest.mark.parametrize('payload', [[], None, 'text', {'uid': 1, 'u': 'old', 'r': 'admin', 'iat': int(time.time())}])
def test_invalid_shapes_and_legacy_cookies_require_login(payload):
    assert auth.parse_token(signed_payload(payload)) is None


@pytest.mark.parametrize('token', ['é.signature', 'body.é', 'x'*5000, None, 17])
def test_invalid_cookie_encoding_never_raises(token):
    assert auth.parse_token(token) is None
