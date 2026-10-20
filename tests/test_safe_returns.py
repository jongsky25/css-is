"""Return targets must survive browser URL parsing without leaving the site."""
import pytest

from tests.conftest import PW, ROLE_USERS


UNSAFE = [
    '//example.invalid', '///example.invalid', 'https://example.invalid',
    'javascript:alert(1)', '/\\example.invalid', '/%5cexample.invalid',
    '/%2fexample.invalid', '/%252fexample.invalid',
    '/%25252fexample.invalid', '/\n/example.invalid', '/%0d%0a/example.invalid',
    '/%2509/example.invalid', '\x00//example.invalid',
]
SAFE = ['/', '/documents/12?tab=files#review', '/calendar?view=week&scope=mine',
        '/directory?q=Juan%20Cruz', '/seq?tokens=abc,def', '/me?name=Jos%C3%A9']


@pytest.mark.parametrize('target', UNSAFE)
def test_return_helpers_reject_ambiguous_targets(app_mod, target):
    assert app_mod._safe_next(target) == '/'
    assert app_mod._safe_back(target) == '/directory'


@pytest.mark.parametrize('target', SAFE)
def test_return_helpers_preserve_deep_links(app_mod, target):
    assert app_mod._safe_next(target) == target
    assert app_mod._safe_back(target) == target


@pytest.mark.parametrize('target', UNSAFE)
def test_login_rejects_external_return(client, target):
    response = client.post('/login', data={
        'username': ROLE_USERS['viewer'], 'password': PW, 'next': target,
    }, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == '/'


@pytest.mark.parametrize('target', SAFE)
def test_login_preserves_deep_link(client, target):
    response = client.post('/login', data={
        'username': ROLE_USERS['viewer'], 'password': PW, 'next': target,
    }, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers['location'] == target


@pytest.mark.parametrize('target', UNSAFE)
def test_language_and_manifest_reject_ambiguous_targets(client, target):
    response = client.get('/lang/en', params={'next': target}, follow_redirects=False)
    assert response.headers['location'] == '/'
    manifest = client.get('/manifest.webmanifest', params={'start': target})
    assert manifest.json()['start_url'] == '/'


def test_language_referer_path_cannot_become_external(client):
    response = client.get('/lang/en', headers={
        'referer': 'https://testserver//example.invalid',
    }, follow_redirects=False)
    assert response.headers['location'] == '/'


def test_language_retains_internal_referer_query(client):
    response = client.get('/lang/en', headers={
        'referer': 'http://testserver/seq?tokens=abc,def',
    }, follow_redirects=False)
    assert response.headers['location'] == '/seq?tokens=abc,def'
