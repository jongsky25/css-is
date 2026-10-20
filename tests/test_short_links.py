"""Public-link outbox: durability, provider failures, boundaries and sharing UI."""
from tests.conftest import session_token
import concurrent.futures
import sqlite3

import httpx
import pytest

import short_links as sl

BASE = 'https://office.example.org'
URL = BASE + '/e/abc123'
SHORT = 'https://blhsd.s.gy/Ab3xYz'


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv('CSS_SHORT_LINKS', '1')
    monkeypatch.setenv('CSS_BASE_URL', BASE)
    monkeypatch.setenv('SHORT_IO_API_KEY', 'test-key-not-real')
    monkeypatch.setenv('SHORT_IO_DOMAIN', 'blhsd.s.gy')
    db = str(tmp_path / 'links.db')
    with sqlite3.connect(db) as conn:
        sl.init_db(conn)
    return db


def request_link(db, url):
    with sqlite3.connect(db) as conn:
        sl.enqueue(conn, url)
    return sl.share(db, url)


def reply(body, status=200):
    return httpx.Response(status, json=body, request=httpx.Request('POST', 'https://api.short.io/links'))


def test_saved_mapping_reused(queue):
    request_link(queue, URL)
    assert sl.share(queue, URL) == URL
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return reply({'secureShortURL': SHORT})
    assert sl.process_one(queue, now=100, post=post)
    assert sl.share(queue, URL) == SHORT
    assert sl.share(queue, URL) == SHORT
    assert not sl.process_one(queue, now=200, post=post)
    assert len(calls) == 1
    assert calls[0]['json'] == {'domain': 'blhsd.s.gy', 'originalURL': URL, 'allowDuplicates': False}
    assert calls[0]['headers'] == {'Authorization': 'test-key-not-real'}


@pytest.mark.parametrize('tail', ['/e/a?att=secret', '/e/a/resume?rt=secret',
    '/e/a/certificate?att=secret', '/login', '/r/a?seq=a,b', '/seq?tokens=a&rt=secret',
    '/seq?tokens=', '/seq?tokens=a&tokens=b', '/e/a#secret'])
def test_personal_and_non_public_urls_never_queued(queue, tail):
    assert sl.share(queue, BASE + tail) == BASE + tail
    with sqlite3.connect(queue) as c:
        assert c.execute('SELECT COUNT(*) FROM short_links').fetchone()[0] == 0


@pytest.mark.parametrize('base', ['http://office.example.org', 'https://localhost',
    'https://192.168.1.5', 'https://x.local', 'https://user:pass@office.example.org',
    'https://office.example.org/path', 'https://office.example.org:bad'])
def test_requires_canonical_public_https(queue, monkeypatch, base):
    monkeypatch.setenv('CSS_BASE_URL', base)
    assert not sl.origin()
    assert not sl.eligible(base + '/e/a')


def test_other_origin_and_disabled(queue, monkeypatch):
    assert not sl.eligible('https://other.example.org/e/a')
    assert not sl.eligible('https://[invalid/e/a')
    request_link(queue, URL)
    monkeypatch.setenv('CSS_SHORT_LINKS', '0')
    assert not sl.process_one(queue, post=lambda *a, **k: pytest.fail('Network when disabled'))
    assert sl.share(queue, URL) == URL


def test_combined_query_preserved(queue):
    url = BASE + '/seq?tokens=abc,def'
    request_link(queue, url)
    def post(endpoint, **kwargs):
        assert kwargs['json']['originalURL'] == url
        return reply({'secureShortURL': SHORT})
    assert sl.process_one(queue, post=post)
    assert sl.share(queue, url) == SHORT


def test_rate_limit_shared_and_restart_retry(queue):
    request_link(queue, URL)
    request_link(queue, BASE + '/r/form')
    assert sl.process_one(queue, now=100, post=lambda *a, **k: httpx.Response(429, headers={'Retry-After': '3600'}))
    # New connection/process observes provider-wide cooldown, not just this job.
    assert not sl.process_one(queue, now=200, post=lambda *a, **k: pytest.fail('Rate limited'))
    assert sl.process_one(queue, now=3700, post=lambda *a, **k: reply({'secureShortURL': SHORT}))
    assert sl.share(queue, URL) == SHORT
    assert not sl.process_one(queue, now=3710, post=lambda *a, **k: pytest.fail('Too soon'))
    assert sl.process_one(queue, now=3725, post=lambda *a, **k: reply({'secureShortURL': SHORT}))


def test_timeout_then_retry_and_stale_lease(queue):
    request_link(queue, URL)
    def timeout(*a, **k):
        raise httpx.ReadTimeout('timeout')
    assert sl.process_one(queue, now=100, post=timeout)
    assert sl.share(queue, URL) == URL
    assert not sl.process_one(queue, now=130, post=timeout)
    with sqlite3.connect(queue) as c:
        c.execute("UPDATE short_links SET status='processing',next_attempt=160")
    assert sl.process_one(queue, now=160, post=lambda *a, **k: reply({'secureShortURL': SHORT}))
    assert sl.share(queue, URL) == SHORT


def test_concurrent_workers_and_enqueue(queue):
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        assert list(pool.map(lambda _: request_link(queue, URL), range(8))) == [URL] * 8
        results = list(pool.map(lambda _: sl.process_one(queue, now=100,
            post=lambda *a, **k: reply({'secureShortURL': SHORT})), range(4)))
    assert results.count(True) == 1
    with sqlite3.connect(queue) as c:
        assert c.execute('SELECT attempts FROM short_links').fetchone()[0] == 1


@pytest.mark.parametrize('body', [{'secureShortURL': 'https://evil.example/abcde'}, {}, {'errorcode': 1}])
def test_bad_provider_response_keeps_original(queue, body):
    request_link(queue, URL)
    assert sl.process_one(queue, now=100, post=lambda *a, **k: reply(body, 400 if body.get('errorcode') == 1 else 200))
    assert sl.share(queue, URL) == URL
    if body.get('errorcode') == 1:
        assert not sl.process_one(queue, now=10000, post=lambda *a, **k: pytest.fail('Permanent error'))


def test_storage_creation_does_not_queue(queue, monkeypatch):
    import storage as st
    conn = st.connect(queue)
    st.init_db(conn)
    fid = st.create_form_instance(conn, 2, 'F2', '2026-10-16')
    ev = st.create_event(conn, 'Activity', '2026-10-16', form_instance_ids=[fid])
    stable = BASE + '/e/' + ev['event_token']
    assert not conn.execute('SELECT 1 FROM short_links').fetchone()
    assert sl.share(queue, stable) == stable
    assert not conn.execute('SELECT 1 FROM short_links').fetchone()
    assert not sl.process_one(queue, post=lambda *a, **k: pytest.fail('Automatic creation'))
    conn.close()



def test_status_and_qr_ui(queue, monkeypatch):
    import app
    from starlette.testclient import TestClient
    import auth
    import storage as st
    monkeypatch.setattr(app, 'DB', queue)
    conn = st.connect(queue); st.init_db(conn)
    uid = st.create_admin_user(conn, 'short@test.local', '', '', 'admin', active=True)
    st.mark_onboarded(conn, uid)
    ev = st.create_event(conn, 'Sharing', '2026-10-16', created_by='short@test.local')
    conn.close()
    original = BASE + '/e/' + ev['event_token']
    client = TestClient(app.app, base_url=BASE)
    assert client.post('/short-links/create', data={'url': original}, headers={'X-Short-Link-Request': '1'}).status_code == 401
    assert client.get('/short-links/status', params={'url': original}, follow_redirects=False).status_code in (302, 303)
    client.cookies.set(auth.COOKIE_NAME, session_token({'id': uid, 'username': 'short@test.local', 'role': 'admin'}))
    assert client.get('/short-links/status', params={'url': original}).json()['state'] == 'missing'
    assert client.post('/short-links/create', data={'url': original}).status_code == 403
    assert client.post('/short-links/create', data={'url': BASE + '/e/unknown'}, headers={'X-Short-Link-Request': '1'}).status_code == 404
    assert client.post('/short-links/create', data={'url': original}, headers={'X-Short-Link-Request': '1'}).status_code == 200
    assert sl.process_one(queue, post=lambda *a, **k: reply({'secureShortURL': SHORT}))
    data = client.get('/short-links/status', params={'url': original}).json()
    assert data['url'] == SHORT and data['qr'].startswith('data:image/png;base64,')
    page = client.get(f"/activities/{ev['event_token']}/manage")
    assert page.status_code == 200
    assert f'id="pubUrl" data-short-text>{SHORT}</code>' in page.text
    assert f'href="{original}"' in page.text
    qrs = app._build_qrs([], 'combined', BASE, ev['event_token'])
    assert qrs[0]['url'] == SHORT and qrs[0]['original_url'] == original
    assert qrs[0]['img'] == data['qr']
    # A slug edit must not change the stored destination or displayed short URL.
    conn = st.connect(queue)
    assert st.set_event_slug(conn, ev['id'], 'different-slug')[0]
    conn.close()
    page = client.get(f"/activities/{ev['event_token']}/manage")
    assert f'id="pubUrl" data-short-text>{SHORT}</code>' in page.text
    # Polling is read-only, including syntactically valid but unknown public URLs.
    unknown = BASE + '/e/not-created'
    assert client.get('/short-links/status', params={'url': unknown}).json() ['state'] == 'missing'
    conn = sqlite3.connect(queue)
    assert not conn.execute('SELECT 1 FROM short_links WHERE original_url=?', (unknown,)).fetchone()
    conn.close()


def test_actual_plain_text_provider_failure_is_visible_and_retried(queue):
    request_link(queue, URL)
    def provider_failure(*a, **k):
        return httpx.Response(200, text='Error, database insert failed',
                              request=httpx.Request('POST', 'https://api.short.io/links'))
    assert sl.process_one(queue, now=100, post=provider_failure)
    with sqlite3.connect(queue) as conn:
        row = conn.execute('SELECT status,last_error,next_attempt FROM short_links').fetchone()
        assert row == ('pending', 'Shortening request failed', 160)
        result = sl.status(conn, URL, now=110)
        assert result['state'] == 'retrying' and result['done'] is False
        assert result['retry_after_seconds'] == 50
        assert 'unavailable' in result['message']
        assert 'database insert' not in result['message']
    assert sl.share(queue, URL) == URL
    assert sl.process_one(queue, now=160, post=lambda *a, **k: reply({'secureShortURL': SHORT}))
    with sqlite3.connect(queue) as conn:
        assert sl.status(conn, URL)['url'] == SHORT
        assert sl.status(conn, URL)['state'] == 'ready'


def test_status_distinguishes_off_pending_invalid_and_rate_limited(queue, monkeypatch):
    with sqlite3.connect(queue) as conn:
        monkeypatch.setenv('CSS_SHORT_LINKS', '0')
        assert sl.status(conn, URL)['state'] == 'disabled'
        monkeypatch.setenv('CSS_SHORT_LINKS', '1')
        assert sl.status(conn, BASE + '/e/a/resume?rt=secret')['state'] == 'ineligible'
        assert sl.status(conn, URL)['state'] == 'missing'
        sl.enqueue(conn, URL)
        assert sl.status(conn, URL)['state'] == 'pending'
    sl.process_one(queue, now=100, post=lambda *a, **k: httpx.Response(429, headers={'Retry-After': '3600'}))
    with sqlite3.connect(queue) as conn:
        result = sl.status(conn, URL, now=200)
        assert result['state'] == 'retrying'
        assert result['retry_after_seconds'] == 3500
        assert 'request limit' in result['message']
        conn.execute("UPDATE short_links SET status='failed'")
        assert sl.status(conn, URL)['done'] is True
        assert sl.status(conn, URL)['state'] == 'failed'


def test_legacy_migration_preserves_ready_links_and_retries_failed(queue):
    with sqlite3.connect(queue) as conn:
        sl.enqueue(conn, URL)
        sl.enqueue(conn, BASE + '/r/old')
        conn.execute("UPDATE short_links SET provider='is.gd',status='failed',attempts=10,next_attempt=9999999999")
        conn.execute("UPDATE short_links SET status='ready',short_url='https://is.gd/Old123' WHERE original_url=?", (BASE + '/r/old',))
        conn.execute('UPDATE short_link_rate SET next_call=9999999999')
        conn.commit()
        sl.init_db(conn)
        assert conn.execute('SELECT provider,status,attempts,next_attempt FROM short_links WHERE original_url=?', (URL,)).fetchone() == ('short.io','pending',0,0)
        assert sl.lookup(conn, BASE + '/r/old') == 'https://is.gd/Old123'
        assert conn.execute('SELECT next_call FROM short_link_rate').fetchone()[0] == 0
    assert sl.process_one(queue, now=100, post=lambda *a, **k: reply({'secureShortURL': SHORT}))
    with sqlite3.connect(queue) as conn:
        sl.init_db(conn)
        assert sl.lookup(conn, URL) == SHORT
        assert conn.execute('SELECT attempts FROM short_links WHERE original_url=?', (URL,)).fetchone()[0] == 1


def test_missing_secret_does_not_consume_attempts(queue, monkeypatch):
    request_link(queue, URL)
    monkeypatch.delenv('SHORT_IO_API_KEY')
    assert not sl.process_one(queue, post=lambda *a, **k: pytest.fail('Missing API key'))
    with sqlite3.connect(queue) as conn:
        assert sl.status(conn, URL)['state'] == 'configuration'
        assert conn.execute('SELECT attempts FROM short_links').fetchone()[0] == 0
    monkeypatch.setenv('SHORT_IO_API_KEY', 'restored-test-key')
    assert sl.process_one(queue, post=lambda *a, **k: reply({'secureShortURL': SHORT}))


@pytest.mark.parametrize('http_status,category', [(401,'Provider credentials rejected'),(403,'Provider credentials rejected'),(402,'Provider quota reached')])
def test_account_errors_pause_globally_without_exposing_secret(queue, http_status, category):
    request_link(queue, URL)
    request_link(queue, BASE + '/r/other')
    sl.process_one(queue, now=100, post=lambda *a, **k: reply({'secret':'test-key-not-real'}, http_status))
    with sqlite3.connect(queue) as conn:
        assert conn.execute('SELECT last_error FROM short_links WHERE original_url=?',(URL,)).fetchone()[0] == category
        assert 'test-key-not-real' not in str(sl.status(conn, URL))
    assert not sl.process_one(queue, now=200, post=lambda *a, **k: pytest.fail('Provider cooldown'))
    assert sl.process_one(queue, now=3700, post=lambda *a, **k: reply({'secureShortURL': SHORT}))


@pytest.mark.parametrize('candidate', ['https://evil.example/abc', 'https://blhsd.s.gy.evil.example/abc', 'http://blhsd.s.gy/abc', 'https://blhsd.s.gy@evil.example/abc', 'https://blhsd.s.gy/abc?rt=secret'])
def test_provider_response_must_use_selected_https_domain(queue, candidate):
    request_link(queue, URL)
    sl.process_one(queue, post=lambda *a, **k: reply({'secureShortURL': candidate}))
    assert sl.share(queue, URL) == URL


def test_legacy_queue_waits_for_click_and_ready_mapping_survives(queue):
    with sqlite3.connect(queue) as conn:
        conn.execute("INSERT INTO short_links(original_url,created_at,updated_at) VALUES(?,0,0)", (URL,))
        conn.commit()
        sl.init_db(conn)
        assert sl.status(conn, URL)['state'] == 'missing'
    assert sl.share(queue, URL) == URL
    assert not sl.process_one(queue, post=lambda *a, **k: pytest.fail('Unrequested legacy job'))
    request_link(queue, URL)
    assert sl.process_one(queue, post=lambda *a, **k: reply({'secureShortURL': SHORT}))
    with sqlite3.connect(queue) as conn:
        sl.init_db(conn)
    assert sl.share(queue, URL) == SHORT
