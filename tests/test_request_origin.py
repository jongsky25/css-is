"""CSRF boundary tests use real handlers and check rejected writes have no effect."""
import re

import pytest
from starlette.requests import Request

import auth
import request_security as security
import storage as st
from tests.conftest import PW, ROLE_USERS


def request(headers=(), scheme='https', host='office.test'):
    return Request({'type': 'http', 'method': 'POST', 'path': '/me',
                    'root_path': '', 'scheme': scheme, 'query_string': b'',
                    'server': (host, 443 if scheme == 'https' else 80),
                    'headers': [(b'host', host.encode())] +
                               [(k.lower().encode(), v.encode()) for k, v in headers]})


@pytest.mark.parametrize('headers', [
    [('Origin', 'https://office.test')], [('Origin', 'https://OFFICE.test:443')],
    [('Referer', 'https://office.test/me?tab=profile')],
    [('Origin', 'https://office.test'), ('Referer', 'https://office.test/me')],
    [('Origin', 'https://office.test'), ('Referer', 'https://office.test/calendar?tags=a,b')],
])
def test_exact_origin_and_referer_fallback(headers):
    assert security.same_origin_write(request(headers))


@pytest.mark.parametrize('headers', [
    [], [('Sec-Fetch-Site', 'same-origin')], [('Origin', '')], [('Origin', 'null')],
    [('Origin', 'https://sibling.office.test')], [('Origin', 'http://office.test')],
    [('Origin', 'https://office.test:444')], [('Origin', 'https://office.test.evil.test')],
    [('Origin', 'https://office.test@evil.test')], [('Origin', 'https://user@office.test')],
    [('Origin', 'https://office.test/path')], [('Origin', 'https://office.test#part')],
    [('Origin', 'https://office.test, https://evil.test')],
    [('Origin', 'https://office.test'), ('Origin', 'https://office.test')],
    [('Origin', 'https://office.test'), ('Referer', 'https://evil.test/page')],
    [('Origin', 'null'), ('Referer', 'https://office.test/page')],
    [('Referer', 'https://evil.test/page')], [('Referer', '//office.test/page')],
    [('Origin', 'https://evil.test'), ('X-Forwarded-Host', 'evil.test')],
    [('Origin', 'https://office.test'), ('Sec-Fetch-Site', 'cross-site')],
    [('Origin', 'https://office.test\x00')], [('Origin', 'https://office.test:bad')],
])
def test_invalid_missing_or_cross_origin_headers_fail_closed(headers):
    assert not security.same_origin_write(request(headers))


def test_canonical_origin_behind_tls_termination():
    req = request([('Origin', 'https://office.test')], scheme='http', host='internal:7860')
    assert security.same_origin_write(req, 'https://office.test')
    assert not security.same_origin_write(req, 'https://other.test')
    assert not security.same_origin_write(req, 'invalid configuration')


@pytest.mark.parametrize('origin', [None, '', 'null', 'https://evil.test',
                                    'http://sibling.testserver', 'https://testserver'])
def test_foreign_write_cannot_toggle_admin_setting(admin, app_mod, origin):
    admin.headers.pop('origin', None)
    headers = {} if origin is None else {'Origin': origin}
    conn = app_mod.get_conn()
    try:
        st.set_setting(conn, 'spot_feedback_enabled', '1')
        before = conn.execute('SELECT count(*) FROM audit_log').fetchone()[0]
        response = admin.post('/admin/feedback/toggle', data={}, headers=headers)
        assert response.status_code == 403
        assert 'could not be verified' in response.text
        assert response.headers['cache-control'] == 'no-store'
        assert st.get_setting(conn, 'spot_feedback_enabled') == '1'
        assert conn.execute('SELECT count(*) FROM audit_log').fetchone()[0] == before
    finally:
        conn.close()


def test_same_origin_and_referer_writes_work(admin, app_mod):
    admin.headers.pop('origin', None)
    for headers, value in [({'Origin': 'http://testserver'}, '0'),
                           ({'Referer': 'http://testserver/admin/feedback'}, '1')]:
        response = admin.post('/admin/feedback/toggle', headers=headers,
                              data={'spot_feedback_enabled': value}, follow_redirects=False)
        assert response.status_code == 303
        with st.connect(app_mod.DB) as conn:
            assert st.get_setting(conn, 'spot_feedback_enabled') == value


@pytest.mark.parametrize('path', ['/login', '/logout', '/forgot', '/set-password', '/reset-password'])
def test_account_writes_are_protected_before_handler(client, app_mod, path):
    client.headers.pop('origin', None)
    with st.connect(app_mod.DB) as conn:
        before = conn.execute('SELECT count(*) FROM login_session').fetchone()[0]
    response = client.post(path, data={'username': ROLE_USERS['viewer'], 'password': PW})
    assert response.status_code == 403
    assert 'could not be verified' in response.text
    assert not response.cookies.get(auth.COOKIE_NAME)
    with st.connect(app_mod.DB) as conn:
        assert conn.execute('SELECT count(*) FROM login_session').fetchone()[0] == before
    # Restore the session-scoped client's normal browser default for other tests.
    client.headers['Origin'] = 'http://testserver'


def test_all_write_routes_inherit_boundary(admin, app_mod):
    """Includes JSON, binary and multipart handlers without reading their bodies."""
    admin.headers.pop('origin', None)
    checked = 0
    for path, operations in app_mod.app.openapi()['paths'].items():
        actual = re.sub(r'\{[^}]+\}', '1', path)
        for method in set(operations) & {'post', 'put', 'patch', 'delete'}:
            if security.csrf_exempt(method.upper(), actual):
                continue
            response = admin.request(method.upper(), actual, content=b'not a valid body',
                                     headers={'Content-Type': 'application/octet-stream'},
                                     follow_redirects=False)
            assert response.status_code == 403, (method, path, response.status_code)
            assert 'could not be verified' in response.text, (method, path)
            checked += 1
    assert checked >= 200


def test_public_write_inventory_has_no_broad_exemptions(app_mod):
    paths = app_mod.app.openapi()['paths']
    public = {p for p, ops in paths.items() if 'post' in ops and app_mod._is_public(p)}
    assert public == set(security.CSRF_EXCEPTIONS) | {'/login', '/logout', '/forgot', '/set-password', '/reset-password'}
    for path in security.CSRF_EXCEPTIONS:
        actual = re.sub(r'\{[^}]+\}', '1', path)
        assert security.csrf_exempt('POST', actual)
        assert not security.csrf_exempt('DELETE', actual)
        assert not security.csrf_exempt('POST', actual + '/unlisted')
    assert not security.csrf_exempt('POST', '/integrations/gmail/documents/extra')


def test_callback_requires_own_secret_without_origin(client, monkeypatch, app_mod):
    monkeypatch.setenv('CSS_OFFSITE_PING_TOKEN', 'test-only-backup-secret')
    client.headers.pop('origin', None)
    try:
        assert client.post('/offsite-backup/ping', json={}).status_code == 401
        assert client.post('/offsite-backup/ping', json={'file': 'synthetic.db'},
                           headers={'X-Backup-Token': 'test-only-backup-secret'}).status_code == 204
        assert client.post('/integrations/gmail/documents', json={}).status_code == 401
    finally:
        client.headers['Origin'] = 'http://testserver'


def test_space_origin_uses_server_configuration(admin, monkeypatch):
    monkeypatch.delenv('CSS_BASE_URL', raising=False)
    monkeypatch.setenv('SPACE_HOST', 'office.hf.space')
    good = admin.post('/admin/feedback/toggle', data={},
                      headers={'Origin': 'https://office.hf.space'}, follow_redirects=False)
    assert good.status_code == 303
    bad = admin.post('/admin/feedback/toggle', data={},
                     headers={'Origin': 'https://sibling.hf.space',
                              'X-Forwarded-Host': 'sibling.hf.space'})
    assert bad.status_code == 403


def test_maintenance_client_supplies_origin():
    import pull_backup
    class Opener:
        def open(self, req, timeout):
            assert req.get_header('Origin') == 'https://office.test:8443'
            assert req.method == 'POST'
            return 'sent'
    assert pull_backup._post(Opener(), 'https://office.test:8443/login', {}) == 'sent'


def test_logout_get_and_foreign_post_do_not_revoke_session(admin, app_mod):
    cookie = admin.cookies.get(auth.COOKIE_NAME)
    response = admin.get('/logout', headers={'Referer': 'https://evil.test/'})
    assert response.status_code == 200
    assert 'action="/logout"' in response.text
    denied = admin.post('/logout', headers={'Origin': 'https://evil.test'})
    assert denied.status_code == 403
    payload = auth.parse_token(cookie)
    with st.connect(app_mod.DB) as conn:
        assert st.session_actor(conn, payload)
    assert admin.post('/logout', follow_redirects=False).status_code == 303
    with st.connect(app_mod.DB) as conn:
        assert st.session_actor(conn, payload) is None


@pytest.mark.parametrize('module,path', [('documents_routes', '/documents/new'),
                                        ('work_routes', '/work/new')])
def test_valid_module_token_does_not_override_foreign_origin(admin, module, path):
    import importlib
    cookie = admin.cookies.get(auth.COOKIE_NAME)
    req = request([('Cookie', auth.COOKIE_NAME + '=' + cookie)])
    csrf = importlib.import_module(module).csrf(req)
    response = admin.post(path, data={'csrf': csrf}, headers={'Origin': 'https://evil.test'})
    assert response.status_code == 403
    assert 'could not be verified' in response.text
