"""Unpublished contingency: authentication before fixed-provider I/O."""
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import time

import httpx
import pytest
from starlette.testclient import TestClient

import telegram_outbound_protocol as proof
import telegram_outbound_service as service
from tests.test_telegram_bot import TOKEN

PARAMS = {'chat_id': 101, 'text': 'private notice', 'link_preview_options': {'is_disabled': True}}


@pytest.fixture(autouse=True)
def clean_claims(monkeypatch):
    monkeypatch.setattr(service, '_CLAIMS', {})
    monkeypatch.setattr(service, 'issuer_key', lambda: proof.public_key(TOKEN))
    monkeypatch.setattr(service, 'consume_permit', lambda *args: True)


def test_proof_contains_no_private_key_and_covers_entire_packet():
    body, signature = proof.packet(TOKEN, 'sendMessage', PARAMS, now=100)
    key = proof.public_key(TOKEN)
    value = proof.verify(body, signature, key, now=110)
    assert value['params'] == PARAMS and len(key) == 64 and TOKEN not in key
    for raw, sig, pub, at in ((body+b' ', signature, key, 110), (body, signature, '0'*64, 110),
                              (body, signature, key, 120), (body, signature, key, 90)):
        with pytest.raises(ValueError, match='^Invalid outbound proof or request$'):
            proof.verify(raw, sig, pub, now=at)


@pytest.mark.parametrize('method,params', [
    ('deleteMessage', {'chat_id': 101, 'message_id': 1}),
    ('https://evil.example', {}),
    ('getMe', {'url': 'https://evil.example'}),
    ('getChatMember', {'chat_id': 101, 'user_id': True}),
    ('sendMessage', dict(PARAMS, chat_id=True)),
    ('sendMessage', dict(PARAMS, text='x'*4097)),
    ('sendMessage', dict(PARAMS, text='😀'*2049)),
    ('sendMessage', dict(PARAMS, message_thread_id=True)),
    ('sendMessage', dict(PARAMS, link_preview_options={'is_disabled': False})),
    ('sendMessage', dict(PARAMS, arbitrary_url='https://evil.example')),
])
def test_signed_but_unsupported_request_is_still_denied(method, params):
    raw, signature = proof.packet(TOKEN, method, params)
    with pytest.raises(ValueError):
        proof.verify(raw, signature, proof.public_key(TOKEN))


def provider(monkeypatch, status=200, body=None):
    calls = []
    payload = body or {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 101},
                                           'text': 'private returned content', 'secret': TOKEN}}
    class Response:
        status_code = status
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self, chunk_size): yield json.dumps(payload).encode()
    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {'verify': True, 'trust_env': True, 'follow_redirects': False,
                              'timeout': httpx.Timeout(7, connect=3)}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url, **kwargs):
            calls.append((method, url, kwargs))
            logging.getLogger('httpx').info('%s %s', method, url)
            return Response()
    monkeypatch.setattr(httpx, 'Client', Client)
    return calls


def test_valid_proof_sends_once_to_fixed_api_and_replay_is_refused(monkeypatch, caplog):
    calls = provider(monkeypatch)
    raw, signature = proof.packet(TOKEN, 'sendMessage', PARAMS)
    with TestClient(service.app) as client, caplog.at_level(logging.DEBUG):
        result = client.post('/telegram', content=raw, headers={'x-office-proof': signature})
        replay = client.post('/telegram', content=raw, headers={'x-office-proof': signature})
    value = result.json()
    assert value['outcome'] == 'response' and value['provider_status'] == 200
    assert value['provider'] == {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 101}}}
    assert replay.json()['outcome'] == 'refused'
    assert calls == [('POST', 'https://api.telegram.org/bot'+TOKEN+'/sendMessage', {'json': PARAMS})]
    assert TOKEN not in result.text + replay.text + caplog.text
    assert 'private returned content' not in result.text


def test_invalid_proof_and_oversize_actual_body_never_reach_provider(monkeypatch):
    calls = provider(monkeypatch)
    raw, signature = proof.packet(TOKEN, 'sendMessage', PARAMS)
    with TestClient(service.app) as client:
        assert client.post('/telegram', content=raw, headers={'x-office-proof': 'A'*86}).status_code == 403
        assert client.post('/telegram', content=b'x'*65537,
                           headers={'x-office-proof': signature, 'content-length': '1'}).status_code == 403
    assert not calls


def test_simultaneous_duplicate_claims_allow_one_attempt():
    value = {'nonce': 'a'*32, 'expires_at': time.time()+20}
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(lambda _: service.claim(value), range(20))) == 1


def test_private_provider_error_is_not_forwarded(monkeypatch):
    calls = provider(monkeypatch, 403, {'ok': False, 'description': TOKEN+' private provider text'})
    raw, signature = proof.packet(TOKEN, 'sendMessage', PARAMS)
    with TestClient(service.app) as client:
        response = client.post('/telegram', content=raw, headers={'x-office-proof': signature})
    assert len(calls) == 1 and response.json()['provider'] == {'ok': False}
    assert TOKEN not in response.text and 'private' not in response.text


def test_bad_thread_field_is_not_laundered_into_valid_acceptance():
    result = service.compact('sendMessage', dict(PARAMS, message_thread_id=1),
                             {'ok': True, 'result': {'message_id': 1, 'chat': {'id': 101}, 'message_thread_id': True}})
    assert result == {}


def test_bot_name_check_exposes_only_a_boolean():
    for username, expected in [('BLHSD_BOT', True), ('another_private_bot', False)]:
        value = service.compact('getMe', {}, {'ok': True, 'result': {'id': 123456, 'is_bot': True, 'username': username}})
        assert value['result']['username_matches'] is expected
        assert username not in json.dumps(value)
