"""Public asset reads avoid SQLite without weakening other request boundaries."""
import json
import sqlite3
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import auth


@pytest.fixture(params=['anonymous', 'active', 'revoked', 'malformed'])
def asset_client(request, client, viewer, app_mod):
    if request.param == 'anonymous':
        return client
    if request.param == 'malformed':
        client.cookies.set(auth.COOKIE_NAME, 'not-a-valid-session')
        return client
    if request.param == 'revoked':
        conn = app_mod.get_conn()
        conn.execute("UPDATE admin_user SET active=0 WHERE username='viewer@test.local'")
        conn.commit()
        conn.close()
    return viewer


def test_public_asset_reads_open_no_database(asset_client, app_mod, monkeypatch):
    opened, statements = [], []
    connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        opened.append(True)
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(sqlite3, 'connect', traced_connect)
    paths = [
        ('/static/css/app.css?v=test', 200),
        ('/static/js/app.js', 200),
        ('/static/img/icons/icon-192.png', 200),
        ('/static/not-present.js', 404),
        ('/sw.js', 200),
        ('/manifest.webmanifest?start=/seq?tokens=synthetic', 200),
        ('/favicon.ico', 404),  # Existing route behavior: no root favicon file.
    ]
    for method in ('GET', 'HEAD'):
        for path, status in paths:
            response = asset_client.request(method, path, follow_redirects=False)
            # Root FastAPI GET routes currently do not implement HEAD.
            if method == 'HEAD' and path.startswith(('/sw.js', '/manifest.')):
                status = 405
            assert response.status_code == status, (method, path, response.text)
            assert response.headers['x-css-app'] == '1'
            assert response.headers['x-content-type-options'] == 'nosniff'
            assert response.headers['referrer-policy'] == 'same-origin'
            assert 'set-cookie' not in response.headers
            if method == 'HEAD':
                assert not response.content
    assert not opened and not statements, (len(opened), len(statements))


def test_assets_still_work_when_database_is_unavailable(viewer, app_mod, monkeypatch):
    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError('synthetic database outage')

    monkeypatch.setattr(sqlite3, 'connect', unavailable)
    css = viewer.get('/static/css/app.css')
    assert css.status_code == 200
    assert css.content == (Path(app_mod.__file__).parent / 'static/css/app.css').read_bytes()
    assert viewer.get('/sw.js').status_code == 200
    assert viewer.get('/manifest.webmanifest').status_code == 200


def test_asset_revalidation_ranges_and_metrics(asset_client, app_mod):
    response = asset_client.get('/static/js/app.js')
    assert response.status_code == 200
    assert 'no-store' not in response.headers.get('cache-control', '')
    for headers in ({'If-None-Match': response.headers['etag']},
                    {'If-Modified-Since': response.headers['last-modified']}):
        cached = asset_client.get('/static/js/app.js', headers=headers)
        assert cached.status_code == 304 and not cached.content
        assert cached.headers['x-css-app'] == '1'
    partial = asset_client.get('/static/js/app.js', headers={'Range': 'bytes=0-15'})
    assert partial.status_code == 206
    assert partial.content == response.content[:16]
    assert partial.headers['content-range'].startswith('bytes 0-15/')
    assert asset_client.get('/sw.js').headers['cache-control'] == 'no-cache'
    manifest = asset_client.get('/manifest.webmanifest?start=/seq?tokens=synthetic')
    assert manifest.headers['cache-control'] == 'no-store'
    assert manifest.json()['start_url'] == '/seq?tokens=synthetic'
    records = [json.loads(line) for line in Path(app_mod.mon.LOG_PATH).read_text().splitlines()]
    assets = [r for r in records if r['path'] == '/static/js/app.js']
    assert [r['status'] for r in assets] == [200, 304, 304, 206]
    # Asset requests remain counted/timed, without resolving a session for logging.
    assert all(r['user'] is None and r['ms'] >= 0 for r in assets)


@pytest.mark.parametrize('path', [
    '/static/js/app.js', '/sw.js', '/manifest.webmanifest', '/favicon.ico',
])
@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE'])
def test_asset_paths_do_not_exempt_unsafe_methods(client, path, method):
    denied = client.request(method, path, headers={'Origin': 'https://foreign.example'})
    assert denied.status_code == 403
    assert 'could not be verified' in denied.text
    assert denied.headers['cache-control'] == 'no-store'
    same_origin = client.request(method, path, follow_redirects=False)
    assert same_origin.status_code in (404, 405)


@pytest.mark.parametrize('path', [
    '/me/photo', '/me/signature.png', '/directory/person/1/signature.png',
    '/documents/1/annotate/1', '/admin/export', '/static-private/file.png',
    '/sw.js/extra', '/manifest.webmanifest/extra',
    '/me/signature.png?asset=/static/js/app.js',
])
def test_private_files_and_similar_paths_still_require_login(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'].startswith('/login?next=')
    assert response.headers['cache-control'] == 'no-store'


def test_asset_read_does_not_bypass_revocation_on_next_private_request(viewer, app_mod):
    conn = app_mod.get_conn()
    conn.execute("UPDATE admin_user SET active=0 WHERE username='viewer@test.local'")
    conn.commit()
    conn.close()
    assert viewer.get('/static/js/app.js').status_code == 200
    denied = viewer.get('/me/photo', follow_redirects=False)
    assert denied.status_code == 303
    assert denied.headers['location'].startswith('/login?next=')


@pytest.mark.parametrize('path', [
    '/static/%2e%2e/version.py', '/static/%2e%2e/me/signature.png',
    '/static/%2e%2e%2fversion.py', '/static/%2e%2e%5cversion.py',
])
def test_static_traversal_cannot_serve_application_or_private_files(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 404


def test_database_backed_public_images_still_resolve_current_session(viewer, app_mod, monkeypatch):
    resolved = []
    original = app_mod._user_from_request

    def resolve(request):
        user = original(request)
        resolved.append(user['username'])
        return user

    monkeypatch.setattr(app_mod, '_user_from_request', resolve)
    assert viewer.get('/photo/999999').status_code == 404
    assert resolved == ['viewer@test.local']


@pytest.mark.parametrize('root_path', ['/office', '/static', '/static/js'])
def test_asset_boundary_uses_the_same_path_as_the_router(app_mod, viewer, monkeypatch, root_path):
    # A mount prefix named /static must not turn private routes into asset reads.
    client = TestClient(app_mod.app, root_path=root_path)
    try:
        denied = client.get(root_path + '/me/signature.png', follow_redirects=False)
        assert denied.status_code == 303
        client.cookies.update(viewer.cookies)
        denied = client.get(root_path + '/directory/person/1/signature.png')
        assert denied.status_code == 403

        def unavailable(*args, **kwargs):
            raise sqlite3.OperationalError('synthetic database outage')

        monkeypatch.setattr(sqlite3, 'connect', unavailable)
        assert client.get(root_path + '/static/js/app.js').status_code == 200
        assert client.get(root_path + '/sw.js').status_code == 200
    finally:
        client.close()
