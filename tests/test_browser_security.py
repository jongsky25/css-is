"""Browser policy at actual response boundaries, including early errors."""
from http.cookies import SimpleCookie

import pytest
from starlette.applications import Starlette
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from browser_security import BrowserSecurityMiddleware, secure_cookies_enabled


@pytest.mark.parametrize('env, expected', [
    ({}, False),
    ({'CSS_BASE_URL': 'http://192.168.1.20:8000'}, False),
    ({'CSS_SECURE_COOKIES': '1'}, True),
    ({'CSS_SECURE_COOKIES': 'False'}, False),
    ({'CSS_BASE_URL': 'https://office.example', 'CSS_SECURE_COOKIES': '0'}, True),
    ({'SPACE_HOST': 'office.hf.space', 'CSS_SECURE_COOKIES': 'false'}, True),
])
def test_secure_cookie_configuration(env, expected):
    assert secure_cookies_enabled(env) is expected


@pytest.mark.parametrize('https',[False,True])
def test_isolated_app_configuration_restores_preferences_after_other_import_env(request,monkeypatch,https):
    import app
    base='https://testserver' if https else 'http://testserver'
    monkeypatch.delenv('SPACE_HOST',raising=False)
    monkeypatch.setenv('CSS_BASE_URL',base)
    monkeypatch.setenv('CSS_SECURE_COOKIES','0')
    # Model an app cached under the opposite deployment configuration.
    monkeypatch.setattr(app,'SECURE_COOKIES',not https)
    current=request.getfixturevalue('app_mod')
    assert current.SECURE_COOKIES is https
    viewer=request.getfixturevalue('viewer')
    viewer.base_url=base;viewer.headers['Origin']=base
    response=viewer.post('/calendar/preference',data={'layout':'month','scope':'mine','next':'/calendar'},follow_redirects=False)
    assert response.status_code==303
    cookie=SimpleCookie(response.headers['set-cookie'])['cal_pref']
    assert bool(cookie['secure']) is https
    assert viewer.get('/calendar').context['layout']=='month'


def _assert_headers(response):
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'SAMEORIGIN'
    assert response.headers['referrer-policy'] == 'same-origin'
    policy = response.headers['content-security-policy']
    assert "frame-ancestors 'self'" in policy and "base-uri 'self'" in policy
    assert "object-src 'none'" in policy
    # The script migration must not silently enforce restrictions on legacy JS.
    assert 'script-src' not in policy
    report = response.headers['content-security-policy-report-only']
    assert "script-src 'self'" in report and 'https://drive.google.com' in report
    assert 'report-uri' not in report and 'report-to' not in report


@pytest.mark.parametrize('path,status', [
    ('/login', 200), ('/me', 303), ('/photo/not-a-number', 422),
    ('/static/not-present.js', 404),
])
def test_unauthenticated_responses_and_early_denials(client, path, status):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == status
    _assert_headers(response)
    assert response.headers['cache-control'] == 'no-store'


def test_rejected_browser_write_has_policy(client):
    response = client.post('/login', data={}, headers={'Origin': 'https://foreign.example'})
    assert response.status_code == 403
    _assert_headers(response)
    assert response.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('path', ['/me', '/calendar', '/admin/email', '/travel/new'])
def test_personal_pages_and_redirects_are_not_stored(admin, path):
    response = admin.get(path, follow_redirects=False)
    assert response.status_code in (200, 303)
    _assert_headers(response)
    assert 'no-store' in response.headers['cache-control']
    assert {'cookie', 'authorization'} <= {
        v.strip().lower() for v in response.headers['vary'].split(',')}


def test_https_login_and_logout_preserve_cookie_attributes(app_mod, monkeypatch):
    from tests.conftest import PW, ROLE_USERS
    import auth
    monkeypatch.setattr(app_mod, 'SECURE_COOKIES', False)
    with TestClient(app_mod.app, base_url='https://office.test') as client:
        login = client.post('/login', data={
            'username': ROLE_USERS['admin'], 'password': PW}, follow_redirects=False)
        assert login.status_code == 303
        cookie = SimpleCookie()
        for line in login.headers.get_list('set-cookie'):
            cookie.load(line)
        session = cookie[auth.COOKIE_NAME]
        assert session['secure'] and session['httponly']
        assert session['samesite'].lower() == 'lax' and session['path'] == '/'
        assert client.get('/me').status_code == 200
        logout = client.post('/logout', follow_redirects=False)
        deleted = SimpleCookie()
        for line in logout.headers.get_list('set-cookie'):
            deleted.load(line)
        assert deleted[auth.COOKIE_NAME]['secure']
        assert deleted[auth.COOKIE_NAME]['max-age'] == '0'
        assert login.headers['strict-transport-security'] == 'max-age=86400'


def test_hsts_uses_trusted_transport_or_config_not_forwarded_headers(client, monkeypatch):
    monkeypatch.delenv('SPACE_HOST', raising=False)
    monkeypatch.delenv('CSS_BASE_URL', raising=False)
    response = client.get('/login', headers={'X-Forwarded-Proto': 'https'})
    assert 'strict-transport-security' not in response.headers
    monkeypatch.setenv('SPACE_HOST', 'office.hf.space')
    assert client.get('/login').headers['strict-transport-security'] == 'max-age=86400'


def test_static_assets_keep_validation_but_worker_revalidates(client):
    asset = client.get('/static/js/app.js')
    assert asset.status_code == 200 and 'no-store' not in asset.headers.get('cache-control', '')
    assert asset.headers['etag']
    cached = client.get('/static/js/app.js', headers={'If-None-Match': asset.headers['etag']})
    assert cached.status_code == 304 and not cached.content
    assert client.get('/sw.js').headers['cache-control'] == 'no-cache'
    # The manifest can include a participant's bearer URL.
    assert client.get('/manifest.webmanifest?start=/seq?tokens=secret').headers['cache-control'] == 'no-store'


def test_unhandled_500_has_security_and_cache_policy(app_mod, monkeypatch):
    def crash(_request):
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(app_mod, '_user_from_request', crash)
    with TestClient(app_mod.app, raise_server_exceptions=False) as client:
        response = client.get('/login')
    assert response.status_code == 500
    _assert_headers(response)
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-css-app'] == '1'


def test_streams_and_multiple_cookies_are_preserved(monkeypatch):
    monkeypatch.delenv('SPACE_HOST', raising=False)
    monkeypatch.delenv('CSS_BASE_URL', raising=False)

    async def stream(_request):
        async def chunks():
            yield b'one\n'
            yield b'two\n'
        response = StreamingResponse(chunks(), media_type='text/event-stream', headers={
            'Content-Disposition': 'attachment; filename=events.txt'})
        response.set_cookie('recognition', 'abc', httponly=True, samesite='lax')
        response.set_cookie('calendar_pref', 'month:bureau', httponly=True, samesite='lax')
        return response

    app = Starlette(routes=[Route('/static/cookies', stream)])
    app.add_middleware(BrowserSecurityMiddleware, secure_cookies=lambda: True)
    response = TestClient(app).get('/static/cookies')
    assert response.content == b'one\ntwo\n'
    assert response.headers['content-disposition'] == 'attachment; filename=events.txt'
    assert response.headers['cache-control'] == 'no-store'
    assert len(response.headers.get_list('set-cookie')) == 2
    cookies = SimpleCookie()
    for line in response.headers.get_list('set-cookie'):
        cookies.load(line)
    assert all(cookie['secure'] and cookie['httponly'] for cookie in cookies.values())


# Policies under which a browser still sends the real Origin on a same-origin form POST. Under "no-referrer" (and
# "same-origin" is not in this list by accident: it is) a Chromium form POST would carry "Origin: null", which the
# application's write check rejects, so login and every save would fail with "This request could not be verified".
ORIGIN_PRESERVING_POLICIES = {'same-origin', 'origin', 'origin-when-cross-origin', 'strict-origin',
                              'strict-origin-when-cross-origin', 'no-referrer-when-downgrade', 'unsafe-url'}


def test_the_referrer_policy_lets_a_same_origin_form_post_pass_the_origin_check(client):
    policy = client.get('/login').headers['referrer-policy']
    assert policy in ORIGIN_PRESERVING_POLICIES, (
        f"Referrer-Policy {policy!r} makes browsers send 'Origin: null' on form posts; every write would be rejected")
    # what such a browser sends: the site's own Origin, with or without a Referer
    host = 'http://testserver'
    for headers in ({'Origin': host}, {'Origin': host, 'Referer': host + '/login'}):
        r = client.post('/login', data={'username': 'nobody@example.invalid', 'password': 'x'}, headers=headers,
                        follow_redirects=False)
        assert r.status_code != 403, headers
    # and the request this policy exists to prevent is still refused
    r = client.post('/login', data={'username': 'a', 'password': 'b'}, headers={'Origin': 'null'}, follow_redirects=False)
    assert r.status_code == 403 and 'could not be verified' in r.text
