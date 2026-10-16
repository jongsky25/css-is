"""Public-link outbox: durability, provider failures, boundaries and sharing UI."""
import concurrent.futures
import sqlite3

import httpx
import pytest

import short_links as sl

BASE = 'https://office.example.org'
URL = BASE + '/e/abc123'
SHORT = 'https://is.gd/Ab3xYz'


@pytest.fixture
def queue(tmp_path, monkeypatch):
    monkeypatch.setenv('CSS_SHORT_LINKS', '1')
    monkeypatch.setenv('CSS_BASE_URL', BASE)
    db = str(tmp_path / 'links.db')
    with sqlite3.connect(db) as conn:
        sl.init_db(conn)
    return db


def reply(body, status=200):
    return httpx.Response(status, json=body, request=httpx.Request('POST', 'https://is.gd/create.php'))


def test_saved_mapping_reused(queue):
    assert sl.share(queue, URL) == URL
    calls = []
    def post(url, **kwargs):
        calls.append(kwargs)
        return reply({'shorturl': SHORT})
    assert sl.process_one(queue, now=100, post=post)
    assert sl.share(queue, URL) == SHORT
    assert sl.share(queue, URL) == SHORT
    assert not sl.process_one(queue, now=200, post=post)
    assert len(calls) == 1
    assert calls[0]['data'] == {'format': 'json', 'url': URL}


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
    sl.share(queue, URL)
    monkeypatch.setenv('CSS_SHORT_LINKS', '0')
    assert not sl.process_one(queue, post=lambda *a, **k: pytest.fail('Network when disabled'))
    assert sl.share(queue, URL) == URL


def test_combined_query_preserved(queue):
    url = BASE + '/seq?tokens=abc,def'
    sl.share(queue, url)
    def post(endpoint, **kwargs):
        assert kwargs['data']['url'] == url
        return reply({'shorturl': SHORT})
    assert sl.process_one(queue, post=post)
    assert sl.share(queue, url) == SHORT


def test_rate_limit_shared_and_restart_retry(queue):
    sl.share(queue, URL)
    sl.share(queue, BASE + '/r/form')
    assert sl.process_one(queue, now=100, post=lambda *a, **k: reply({'errorcode': 3}, 502))
    # New connection/process observes provider-wide cooldown, not just this job.
    assert not sl.process_one(queue, now=200, post=lambda *a, **k: pytest.fail('Rate limited'))
    assert sl.process_one(queue, now=3700, post=lambda *a, **k: reply({'shorturl': SHORT}))
    assert sl.share(queue, URL) == SHORT
    assert not sl.process_one(queue, now=3710, post=lambda *a, **k: pytest.fail('Too soon'))
    assert sl.process_one(queue, now=3725, post=lambda *a, **k: reply({'shorturl': SHORT}))


def test_timeout_then_retry_and_stale_lease(queue):
    sl.share(queue, URL)
    def timeout(*a, **k):
        raise httpx.ReadTimeout('timeout')
    assert sl.process_one(queue, now=100, post=timeout)
    assert sl.share(queue, URL) == URL
    assert not sl.process_one(queue, now=130, post=timeout)
    with sqlite3.connect(queue) as c:
        c.execute("UPDATE short_links SET status='processing',next_attempt=160")
    assert sl.process_one(queue, now=160, post=lambda *a, **k: reply({'shorturl': SHORT}))
    assert sl.share(queue, URL) == SHORT


def test_concurrent_workers_and_enqueue(queue):
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        assert list(pool.map(lambda _: sl.share(queue, URL), range(8))) == [URL] * 8
        results = list(pool.map(lambda _: sl.process_one(queue, now=100,
            post=lambda *a, **k: reply({'shorturl': SHORT})), range(4)))
    assert results.count(True) == 1
    with sqlite3.connect(queue) as c:
        assert c.execute('SELECT attempts FROM short_links').fetchone()[0] == 1


@pytest.mark.parametrize('body', [{'shorturl': 'https://evil.example/abcde'}, {}, {'errorcode': 1}])
def test_bad_provider_response_keeps_original(queue, body):
    sl.share(queue, URL)
    assert sl.process_one(queue, now=100, post=lambda *a, **k: reply(body))
    assert sl.share(queue, URL) == URL
    if body.get('errorcode') == 1:
        assert not sl.process_one(queue, now=10000, post=lambda *a, **k: pytest.fail('Permanent error'))


def test_storage_creation_and_backfill(queue, monkeypatch):
    import storage as st
    conn = st.connect(queue)
    st.init_db(conn)
    fid = st.create_form_instance(conn, 2, 'F2', '2026-10-16')
    ev = st.create_event(conn, 'Activity', '2026-10-16', form_instance_ids=[fid])
    stable = BASE + '/e/' + ev['event_token']
    assert conn.execute('SELECT 1 FROM short_links WHERE original_url=?', (stable,)).fetchone()
    assert st.set_event_slug(conn, ev['id'], 'changed-name')[0]
    assert sl.backfill(conn) == 0
    conn.execute('DELETE FROM short_links'); conn.commit()
    st.set_event_archived(conn, ev['id'], True)
    assert sl.backfill(conn) == 0
    st.set_event_archived(conn, ev['id'], False)
    assert sl.backfill(conn) == 2
    assert sl.backfill(conn) == 0
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
    sl.process_one(queue, post=lambda *a, **k: reply({'shorturl': SHORT}))
    client = TestClient(app.app)
    assert client.get('/short-links/status', params={'url': original}, follow_redirects=False).status_code in (302, 303)
    client.cookies.set(auth.COOKIE_NAME, auth.make_token({'id': uid, 'username': 'short@test.local', 'role': 'admin'}))
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
    sl.share(queue, URL)
    def provider_failure(*a, **k):
        return httpx.Response(200, text='Error, database insert failed',
                              request=httpx.Request('POST', 'https://is.gd/create.php'))
    assert sl.process_one(queue, now=100, post=provider_failure)
    with sqlite3.connect(queue) as conn:
        row = conn.execute('SELECT status,last_error,next_attempt FROM short_links').fetchone()
        assert row == ('pending', 'Provider database unavailable', 160)
        result = sl.status(conn, URL, now=110)
        assert result['state'] == 'retrying' and result['done'] is False
        assert result['retry_after_seconds'] == 50
        assert 'unavailable' in result['message']
        assert 'database insert' not in result['message']
    assert sl.share(queue, URL) == URL
    assert sl.process_one(queue, now=160, post=lambda *a, **k: reply({'shorturl': SHORT}))
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
    sl.process_one(queue, now=100, post=lambda *a, **k: reply({'errorcode': 3}, 502))
    with sqlite3.connect(queue) as conn:
        result = sl.status(conn, URL, now=200)
        assert result['state'] == 'retrying'
        assert result['retry_after_seconds'] == 3500
        assert 'request limit' in result['message']
        conn.execute("UPDATE short_links SET status='failed'")
        assert sl.status(conn, URL)['done'] is True
        assert sl.status(conn, URL)['state'] == 'failed'
