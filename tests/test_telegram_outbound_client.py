"""Application fences remain authoritative when using an owned outbound service."""
import json

import pytest
import requests

import telegram_bot as bot
import telegram_outbound_client as outbound
import telegram_outbound_protocol as protocol
import telegram_transport as transport
from tests.test_telegram_bot import setup, submit, TOKEN, NOW
from tests.test_work import workspace

URL = 'https://office-connect-telegram.onrender.com'


def client(monkeypatch, provider_status=200, provider=None, outer_status=200, wrong_nonce=False):
    monkeypatch.setenv('CSS_TELEGRAM_OUTBOUND_URL', URL)
    calls = []
    class Reply:
        status_code = outer_status
        def __init__(self, packet): self.packet = packet
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, chunk_size):
            value = {'nonce': 'wrong' if wrong_nonce else self.packet['nonce'], 'outcome': 'response',
                     'provider_status': provider_status,
                     'provider': provider or {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 101}}}}
            yield json.dumps(value).encode()
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, **kwargs):
            assert url == URL+'/telegram'
            assert kwargs['timeout'] == (3, 15) and kwargs['verify'] is True
            assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
            assert kwargs['headers']['Content-Type'] == 'application/json'
            value = protocol.verify(kwargs['data'], kwargs['headers']['X-Office-Proof'], protocol.public_key(TOKEN))
            calls.append(value)
            return Reply(value)
    monkeypatch.setattr(requests, 'Session', Session)
    return calls


@pytest.mark.parametrize('status,body,expected', [
    (200, {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 101}}}, ('accepted', 7, None)),
    (403, {'ok': False}, ('failed', None, None)),
    (429, {'ok': False, 'parameters': {'retry_after': 60}}, ('retry_wait', None, 60)),
])
def test_signed_service_response_preserves_provider_semantics(monkeypatch, status, body, expected):
    calls = client(monkeypatch, status, body)
    assert transport.send(TOKEN, 101, 'private notice') == expected
    assert len(calls) == 1 and calls[0]['method'] == 'sendMessage'
    assert calls[0]['params'] == {'chat_id': 101, 'text': 'private notice', 'link_preview_options': {'is_disabled': True}}
    assert transport.last_send_status()['http_status'] == status


@pytest.mark.parametrize('outer_status,wrong_nonce', [(403, False), (503, False), (200, True)])
def test_gateway_failure_is_uncertain_and_never_a_telegram_rejection(monkeypatch, caplog, outer_status, wrong_nonce):
    calls = client(monkeypatch, 403, {'ok': False}, outer_status, wrong_nonce)
    assert transport.send(TOKEN, 101, 'private notice') == ('uncertain', None, None)
    assert len(calls) == 1 and transport.last_send_status()['http_status'] is None
    assert 'Telegram delivery rejected' not in caplog.text and TOKEN not in caplog.text


def test_membership_check_keeps_identity_validation(monkeypatch):
    calls = client(monkeypatch, 200, {'ok': True, 'result': {'user': {'id': 101}, 'status': 'administrator'}})
    assert transport.member_status(TOKEN, -100, 101) == 'administrator'
    assert len(calls) == 1 and calls[0]['method'] == 'getChatMember'
    assert calls[0]['params'] == {'chat_id': -100, 'user_id': 101}


def test_sleeping_service_leaves_delivery_unattempted_then_sends_once(setup, monkeypatch):
    conn, _, _, web = setup
    calls = client(monkeypatch)
    readiness = []
    def ready():
        assert not conn.in_transaction
        readiness.append(True)
        return len(readiness) > 1
    monkeypatch.setattr(outbound, 'ready', ready)
    assert submit(web).status_code == 200
    bot.process_updates(conn, NOW)
    assert bot.deliver(conn, NOW) == 0 and not calls
    row = conn.execute('SELECT state,attempts FROM telegram_delivery').fetchone()
    assert tuple(row) == ('queued', 0)
    assert bot.deliver(conn, NOW) == 1
    assert len(calls) == 1
    assert tuple(conn.execute('SELECT state,attempts FROM telegram_delivery').fetchone()) == ('accepted', 1)
    assert bot.deliver(conn, NOW) == 0 and len(calls) == 1 and len(readiness) == 2


def test_expired_delivery_is_cancelled_while_service_sleeps(setup, monkeypatch):
    from datetime import timedelta
    conn, _, _, web = setup
    calls = client(monkeypatch)
    monkeypatch.setattr(outbound, 'ready', lambda: False)
    assert submit(web).status_code == 200
    bot.process_updates(conn, NOW)
    assert bot.deliver(conn, NOW+timedelta(days=2)) == 0 and not calls
    assert tuple(conn.execute('SELECT state,attempts FROM telegram_delivery').fetchone()) == ('cancelled', 0)


def test_uncertain_service_attempt_is_not_replayed(setup, monkeypatch):
    conn, _, _, web = setup
    calls = client(monkeypatch, outer_status=503)
    monkeypatch.setattr(outbound, 'ready', lambda: True)
    assert submit(web).status_code == 200
    bot.process_updates(conn, NOW)
    assert bot.deliver(conn, NOW) == 1
    assert bot.deliver(conn, NOW) == 0
    assert len(calls) == 1
    assert tuple(conn.execute('SELECT state,attempts FROM telegram_delivery').fetchone()) == ('uncertain', 1)


def test_public_verification_key_is_disabled_by_default_and_never_contains_token(client, app_mod, monkeypatch):
    monkeypatch.delenv('CSS_TELEGRAM_OUTBOUND_URL', raising=False)
    assert client.get(protocol.KEY_PATH).status_code == 404
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setenv('CSS_TELEGRAM_OUTBOUND_URL', URL)
    monkeypatch.setenv('CSS_BASE_URL', protocol.SOURCE)
    result = client.get(protocol.KEY_PATH)
    assert result.status_code == 200
    assert result.json() == {'key': protocol.public_key(TOKEN)}
    assert TOKEN not in result.text and result.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('url', ['http://example.onrender.com', 'https://evil.example',
                                  'https://user:pass@example.onrender.com', 'https://example.onrender.com/path',
                                  'https://example.onrender.com?key=private'])
def test_noncanonical_service_url_is_rejected_before_token_leaves_host(monkeypatch, url):
    monkeypatch.setenv('CSS_TELEGRAM_OUTBOUND_URL', url)
    with pytest.raises(outbound.OutboundError):
        outbound.base_url()


@pytest.mark.parametrize('revoke_link', [False, True])
def test_worker_service_permit_provider_and_finalizer_end_to_end(setup, monkeypatch, caplog, revoke_link):
    import httpx
    from starlette.testclient import TestClient
    import telegram_outbound_service as service
    conn, _, path, primary = setup
    monkeypatch.setenv('CSS_TELEGRAM_OUTBOUND_URL', URL)
    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED', '1')
    monkeypatch.setenv('CSS_BASE_URL', 'https://office.example')
    monkeypatch.setattr(outbound, 'ready', lambda: True)
    monkeypatch.setattr(service, '_CLAIMS', {})
    monkeypatch.setattr(service, 'issuer_key', lambda: protocol.public_key(TOKEN))
    sent, packets = [], []
    class Reply:
        def __init__(self, status, body):
            self.status_code, self.body = status, body
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self, chunk_size): yield self.body
        def iter_content(self, chunk_size): yield self.body
    class Provider:
        def __init__(self, **kwargs):
            assert kwargs['verify'] is True and kwargs['follow_redirects'] is False and kwargs['trust_env'] is True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url, **kwargs):
            assert method == 'POST'
            if url == protocol.SOURCE + protocol.PERMIT_PATH:
                if revoke_link:
                    monkeypatch.setenv('CSS_TELEGRAM_LINK_ENABLED', '0')
                result = primary.post(protocol.PERMIT_PATH, content=kwargs['content'], headers=kwargs['headers'])
                return Reply(result.status_code, result.content)
            assert url == 'https://api.telegram.org/bot'+TOKEN+'/sendMessage'
            import storage
            check = storage.connect(path)
            try:
                assert check.execute('SELECT error_code FROM telegram_delivery').fetchone()[0] == 'outbound_started'
            finally:
                check.close()
            sent.append(kwargs['json'])
            return Reply(200, b'{"ok":true,"result":{"message_id":71,"chat":{"id":101}}}')
    monkeypatch.setattr(httpx, 'Client', Provider)
    with TestClient(service.app) as gateway:
        class Session:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def post(self, url, **kwargs):
                assert url == URL+'/telegram' and not conn.in_transaction
                packets.append(kwargs)
                result = gateway.post('/telegram', content=kwargs['data'], headers=kwargs['headers'])
                return Reply(result.status_code, result.content)
        monkeypatch.setattr(requests, 'Session', Session)
        assert submit(primary).status_code == 200
        assert bot.tick(conn, NOW) == (1, 1)
        state, attempts = conn.execute('SELECT state,attempts FROM telegram_delivery').fetchone()
        assert (state, attempts) == ('uncertain' if revoke_link else 'accepted', 1)
        assert len(sent) == (0 if revoke_link else 1)
        # A fresh service process has no local replay cache; the database still refuses the old proof.
        service._CLAIMS.clear()
        replay = gateway.post('/telegram', content=packets[0]['data'], headers=packets[0]['headers'])
        assert replay.json()['outcome'] == 'refused'
        assert len(sent) == (0 if revoke_link else 1)
        assert bot.deliver(conn, NOW) == 0 and len(packets) == 1
    assert TOKEN not in caplog.text and TOKEN not in '\n'.join(conn.iterdump())
