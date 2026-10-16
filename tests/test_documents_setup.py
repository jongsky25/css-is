"""Initial appointments are explicit, atomic, session-bound and never enable Documents."""
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor

import pytest
import auth
import documents as d
import documents_permissions as permissions
import storage as st


@pytest.fixture
def setup_db(tmp_path):
    path = str(tmp_path / 'setup.db')
    conn = st.connect(path)
    st.init_db(conn)
    users = []
    for index in range(4):
        uid = st.create_admin_user(conn, f'setup{index}@example.test', 'hash', 'salt',
                                   'admin' if index == 0 else 'viewer', active=True)
        st.mark_onboarded(conn, uid)
        users.append(st.get_admin_user_by_id(conn, uid))
    yield conn, users, path
    conn.close()


def appointment(conn, users):
    return d.preview_admin_setup(conn, users[0], '\n'.join(u['username'] for u in users[1:]),
                                 'Named by the records owner for acceptance setup')


def test_three_explicit_accounts_audited_and_switches_unchanged(setup_db):
    conn, users, _ = setup_db
    preview = appointment(conn, users)
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0
    d.bootstrap_admins(conn, users[0], preview)
    grants = conn.execute('SELECT user_id,role,granted_by,unit_id FROM document_role_grant').fetchall()
    assert {tuple(g) for g in grants} == {
        (u['id'], role, users[0]['id'], None)
        for u in users[1:] for role in ('grant_admin', 'workflow_admin')}
    assert st.get_setting(conn, 'documents.enabled') == '0'
    assert st.get_setting(conn, 'documents.sending_enabled') == '0'
    event = conn.execute("SELECT actor_id,detail_json FROM document_event WHERE action='bootstrap_grants'").fetchone()
    assert event[0] == users[0]['id']
    assert json.loads(event[1])['accounts'] == preview['accounts']
    assert conn.execute("SELECT count(*) FROM audit_log WHERE action='document_bootstrap_grants'").fetchone()[0] == 1
    with pytest.raises(d.Conflict):
        d.bootstrap_admins(conn, users[0], preview)
    # Revocation cannot reopen the initial setup path, even if the setting is removed.
    conn.execute("UPDATE document_role_grant SET revoked_at='2026-10-16'")
    conn.execute("DELETE FROM app_setting WHERE key='documents.admin_setup_completed'")
    conn.commit()
    assert 'complete' in d.setup_blocker(conn)


@pytest.mark.parametrize('invalid', ['missing@example.test', 'setup1@example.test\nmissing@example.test', ''])
def test_missing_accounts_fail_the_entire_preview(setup_db, invalid):
    conn, users, _ = setup_db
    with pytest.raises(ValueError):
        d.preview_admin_setup(conn, users[0], invalid, 'Owner approved')
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0


@pytest.mark.parametrize('setting', ['documents.enabled', 'documents.sending_enabled'])
def test_enablement_after_preview_blocks_confirmation(setup_db, setting):
    conn, users, _ = setup_db
    preview = appointment(conn, users)
    st.set_setting(conn, setting, '1')
    with pytest.raises(d.Conflict):
        d.bootstrap_admins(conn, users[0], preview)
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0
    assert st.get_setting(conn, setting) == '1'


def test_authority_and_active_accounts_rechecked_on_confirmation(setup_db):
    conn, users, _ = setup_db
    preview = appointment(conn, users)
    with pytest.raises(permissions.Denied):
        d.bootstrap_admins(conn, {**users[1], 'role': 'admin'}, preview)
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[2]['id'],)); conn.commit()
    with pytest.raises(ValueError):
        d.bootstrap_admins(conn, users[0], preview)
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0


@pytest.mark.parametrize('change', ['rename', 'demote', 'deactivate_operator'])
def test_changed_account_or_operator_invalidates_preview(setup_db, change):
    conn, users, _ = setup_db
    preview = appointment(conn, users)
    if change == 'rename':
        conn.execute("UPDATE admin_user SET username='changed@example.test' WHERE id=?", (users[1]['id'],))
    elif change == 'demote':
        conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?", (users[0]['id'],))
    else:
        conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[0]['id'],))
    conn.commit()
    with pytest.raises(ValueError):
        d.bootstrap_admins(conn, users[0], preview)
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0


def test_audit_failure_rolls_back_all_grants_and_completion_marker(setup_db, monkeypatch):
    conn, users, _ = setup_db
    preview = appointment(conn, users)
    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(d, 'event', fail)
    with pytest.raises(RuntimeError):
        d.bootstrap_admins(conn, users[0], preview)
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0
    assert not st.get_setting(conn, 'documents.admin_setup_completed', '')


def test_concurrent_confirmations_only_appoint_once(setup_db):
    conn, users, path = setup_db
    preview = appointment(conn, users)
    def confirm(_):
        db = st.connect(path)
        try:
            d.bootstrap_admins(db, users[0], preview)
            return 'saved'
        except d.Conflict:
            return 'closed'
        finally:
            db.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(confirm, range(2))) == ['closed', 'saved']
    assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 6


def hidden(response, name):
    match = re.search(r'name="' + name + r'" value="([^"]*)"', response.text)
    assert match, response.text[:1000]
    return html.unescape(match[1])


def test_http_preview_confirmation_csrf_and_one_time_access(setup_db, app_mod, monkeypatch):
    from starlette.testclient import TestClient
    conn, users, path = setup_db
    monkeypatch.setattr(app_mod, 'DB', path)
    url = '/admin/documents/setup'
    with TestClient(app_mod.app) as client:
        assert client.get(url, follow_redirects=False).status_code in (302, 303)
        client.cookies.set(auth.COOKIE_NAME, auth.make_token(users[1]))
        assert client.get(url).status_code == 403
        assert client.post(url, data={'action': 'confirm'}).status_code == 403
        admin_token = auth.make_token(users[0])
        client.cookies.set(auth.COOKIE_NAME, admin_token)
        page = client.get(url)
        assert page.status_code == 200
        assert 'Documents setup' in page.text
        csrf = hidden(page, 'csrf')
        form = {'action': 'preview', 'usernames': '\n'.join(u['username'] for u in users[1:]), 'authorization': 'Owner approved'}
        assert client.post(url, data=form).status_code == 403
        form['csrf'] = csrf
        preview = client.post(url, data=form)
        assert preview.status_code == 200, preview.text
        assert 'Review the appointments' in preview.text
        assert conn.execute('SELECT count(*) FROM document_role_grant').fetchone()[0] == 0
        confirm = {k: hidden(preview, k) for k in ('csrf', 'preview', 'preview_signature')}
        confirm['action'] = 'confirm'
        assert client.post(url, data=confirm).status_code == 400
        confirm['confirmed'] = 'yes'
        tampered = {**confirm, 'preview': confirm['preview'].replace(users[1]['username'], users[0]['username'])}
        assert client.post(url, data=tampered).status_code == 403
        # Even another legitimate system administrator cannot replay this preview.
        conn.execute("UPDATE admin_user SET role='admin' WHERE id=?", (users[1]['id'],)); conn.commit()
        other = st.get_admin_user_by_id(conn, users[1]['id'])
        client.cookies.set(auth.COOKIE_NAME, auth.make_token(other))
        other_csrf = hidden(client.get(url), 'csrf')
        assert client.post(url, data={**confirm, 'csrf': other_csrf}).status_code == 403
        conn.execute("UPDATE admin_user SET role='viewer' WHERE id=?", (users[1]['id'],)); conn.commit()
        client.cookies.set(auth.COOKIE_NAME, admin_token)
        saved = client.post(url, data=confirm, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        page = client.get(url)
        assert 'Appointed administrators' in page.text
        assert 'Review appointments</button>' not in page.text
        assert client.post(url, data=confirm).status_code == 409
        assert st.get_setting(conn, 'documents.enabled') == '0'
        assert st.get_setting(conn, 'documents.sending_enabled') == '0'
        # The operator gets no Documents grant by virtue of being system admin.
        assert client.get('/documents/rules').status_code == 403
        client.cookies.set(auth.COOKIE_NAME, auth.make_token(users[1]))
        assert client.get('/documents/rules').status_code == 200
        assert client.get(url).status_code == 403


def test_enable_requires_explicit_global_grant_and_keeps_sending_off(setup_db):
    conn, users, _ = setup_db
    with pytest.raises(permissions.Denied):
        d.set_module_enabled(conn, users[0], True, '0', 'Controlled acceptance')
    preview = d.preview_admin_setup(conn, users[0], users[0]['username'], 'Owner approved')
    d.bootstrap_admins(conn, users[0], preview)
    d.set_module_enabled(conn, users[0], True, '0', 'Controlled acceptance')
    assert d.enabled(conn)
    assert st.get_setting(conn, 'documents.sending_enabled') == '0'
    assert st.get_setting(conn, 'documents.settings_revision') == '1'
    row = conn.execute("SELECT actor_id,detail_json FROM document_event WHERE action='module_enabled'").fetchone()
    assert row[0] == users[0]['id']
    assert json.loads(row[1])['after'] == {'enabled': '1', 'sending_enabled': '0'}
    with pytest.raises(d.Conflict):
        d.set_module_enabled(conn, users[0], False, '0', 'Stale form')
    # Revoking document authority blocks enablement, but does not prevent emergency disabling.
    conn.execute("UPDATE document_role_grant SET revoked_at='2026-10-16'");conn.commit()
    st.set_setting(conn, 'documents.sending_enabled', '1')
    d.set_module_enabled(conn, users[0], False, '1', 'Stop acceptance')
    assert not d.enabled(conn)
    assert st.get_setting(conn, 'documents.sending_enabled') == '0'
    with pytest.raises(permissions.Denied):
        d.set_module_enabled(conn, users[0], True, '2', 'Attempt after revocation')


def test_module_control_audit_failure_rolls_back_switches(setup_db, monkeypatch):
    conn, users, _ = setup_db
    st.set_setting(conn, 'documents.enabled', '1')
    st.set_setting(conn, 'documents.sending_enabled', '1')
    def fail(*args, **kwargs):
        raise RuntimeError('audit unavailable')
    monkeypatch.setattr(d, 'event', fail)
    with pytest.raises(RuntimeError):
        d.set_module_enabled(conn, users[0], False, '0', 'Stop')
    assert d.enabled(conn)
    assert st.get_setting(conn, 'documents.sending_enabled') == '1'
    assert st.get_setting(conn, 'documents.settings_revision', '0') == '0'


def test_scoped_grant_cannot_enable_bureau_wide_module(setup_db):
    conn, users, _ = setup_db
    unit = st.add_org_unit(conn, 'Scoped division', 'division', 'BLHSD/SCOPED')
    conn.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'grant_admin',?,'2026-10-16')", (users[0]['id'], unit));conn.commit()
    with pytest.raises(permissions.Denied):
        d.set_module_enabled(conn, users[0], True, '0', 'Scoped authority only')
    assert not d.enabled(conn)


def test_http_enable_requires_confirmation_and_allows_intake(setup_db, app_mod, monkeypatch):
    from starlette.testclient import TestClient
    conn, users, path = setup_db
    monkeypatch.setattr(app_mod, 'DB', path)
    preview = d.preview_admin_setup(conn, users[0], users[0]['username'], 'Owner approved')
    d.bootstrap_admins(conn, users[0], preview)
    url = '/admin/documents/setup'
    with TestClient(app_mod.app) as client:
        client.cookies.set(auth.COOKIE_NAME, auth.make_token(users[0]))
        page = client.get(url)
        assert 'Enable Documents</button>' in page.text
        form = {'action': 'enable_module', 'settings_revision': '0', 'authorization': 'Controlled acceptance'}
        assert client.post(url, data=form).status_code == 403
        form['csrf'] = hidden(page, 'csrf')
        assert client.post(url, data=form).status_code == 400
        form['confirmed'] = 'yes'
        result = client.post(url, data=form, follow_redirects=False)
        assert result.status_code == 303
        assert 'Disable Documents and sending</button>' in client.get(url).text
        assert client.post(url, data=form).status_code == 409
        page = client.get('/documents/new')
        created = client.post('/documents/new', data={'csrf': hidden(page, 'csrf'), 'subject': 'Synthetic enabled intake', 'type': 'memo'}, follow_redirects=False)
        assert created.status_code == 303, created.text
        assert st.get_setting(conn, 'documents.sending_enabled') == '0'
        assert client.post(url, data={**form, 'action': 'disable_module', 'settings_revision': '1'}).status_code == 200
        assert not d.enabled(conn)


def test_readiness_inventory_no_side_effects_or_secrets(setup_db, monkeypatch):
    import work_readiness as readiness
    conn, users, _ = setup_db
    monkeypatch.setenv('CSS_DOCS_RELAY_URL', 'https://script.google.com/macros/s/private-deployment/exec')
    monkeypatch.setenv('CSS_DOCS_RELAY_SECRET', 'never-display-this')
    monkeypatch.delenv('CSS_MAIL_RELAY_URL', raising=False)
    before = conn.total_changes
    result = readiness.report(conn, users[0], year=2026)
    assert conn.total_changes == before
    items = {i['key']: i for i in result['items']}
    assert items['drive']['status'] == 'Configured — not verified'
    assert items['email']['status'] == 'Missing or invalid configuration'
    assert items['holidays_2027']['status'] == 'Missing confirmation'
    assert items['signatory']['status'] == 'Missing'
    assert all(i['action'] and i['blocks'] for i in items.values())
    assert 'never-display-this' not in str(result)
    assert 'private-deployment' not in str(result)
    assert not any(result['flags'].values())
    st.set_setting(conn, 'documents.holidays_confirmed.2026', '1')
    updated = {i['key']: i for i in readiness.report(conn, users[0], 2026)['items']}
    assert updated['holidays_2026']['status'] == 'Recorded — review dates'


def test_readiness_scope_inactive_revoked_and_authority(setup_db):
    import work_readiness as readiness
    conn, users, _ = setup_db
    unit = st.add_org_unit(conn, 'Scoped division', 'division', 'BLHSD/SCOPED')
    conn.execute("INSERT INTO document_role_grant(user_id,role,unit_id,created_at) VALUES (?,'records',?,'2026-10-16')", (users[1]['id'], unit))
    conn.commit()
    def item():
        return next(i for i in readiness.report(conn, users[0])['items'] if i['key'] == 'records')
    assert item()['status'] == 'Review required'
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[1]['id'],));conn.commit()
    assert item()['status'] == 'Missing'
    conn.execute('UPDATE admin_user SET active=1 WHERE id=?', (users[1]['id'],))
    conn.execute("UPDATE document_role_grant SET revoked_at='2026-10-16'");conn.commit()
    assert item()['status'] == 'Missing'
    with pytest.raises(permissions.Denied):
        readiness.report(conn, {**users[1], 'role': 'admin'})
    d.bootstrap_admins(conn, users[0], appointment(conn, users))
    assert readiness.report(conn, users[1])
    conn.execute('UPDATE admin_user SET active=0 WHERE id=?', (users[1]['id'],));conn.commit()
    with pytest.raises(permissions.Denied):
        readiness.report(conn, users[1])


@pytest.mark.parametrize('endpoint', ['http://script.google.com/x/exec', 'https://example.test/exec', 'https://script.google.com:invalid/exec', ''])
def test_readiness_rejects_invalid_relay_configuration(monkeypatch, endpoint):
    import work_readiness
    monkeypatch.setenv('CSS_DOCS_RELAY_URL', endpoint)
    monkeypatch.setenv('CSS_DOCS_RELAY_SECRET', 'secret')
    assert not work_readiness.relay_configured('CSS_DOCS_RELAY')


def test_readiness_http_access_and_read_only_page(setup_db, app_mod, monkeypatch):
    from starlette.testclient import TestClient
    conn, users, path = setup_db
    monkeypatch.setattr(app_mod, 'DB', path)
    url = '/admin/documents/readiness'
    with TestClient(app_mod.app) as client:
        assert client.get(url, follow_redirects=False).status_code in (302, 303)
        client.cookies.set(auth.COOKIE_NAME, auth.make_token(users[1]))
        assert client.get(url).status_code == 403
        client.cookies.set(auth.COOKIE_NAME, auth.make_token(users[0]))
        page = client.get(url)
        assert page.status_code == 200
        assert 'Work management readiness' in page.text
        assert 'No external connections are tested' in page.text
        assert 'type="submit"' not in page.text
        assert st.get_setting(conn, 'documents.sending_enabled') == '0'
