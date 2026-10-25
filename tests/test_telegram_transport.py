"""Inspect the Bot API request and failure outcomes using only mocked HTTP."""
import json
import logging

import pytest
import requests

import telegram_transport as transport
from tests.test_telegram_bot import TOKEN


class Response:
    def __init__(self, status, body):
        self.status_code = status
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.closed = False
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True
    def iter_content(self, chunk_size):
        for pos in range(0, len(self.body), chunk_size):
            yield self.body[pos:pos+chunk_size]


def response(monkeypatch, status, body, capture=None):
    value = Response(status, body)
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, *args, **kwargs):
            if capture is not None:
                capture.append((args, kwargs))
            return value
    monkeypatch.setattr(requests, 'Session', Session)
    return value


def test_fixed_provider_private_payload_tls_and_one_attempt(monkeypatch):
    calls = []
    result = response(monkeypatch, 200, {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 101}}}, calls)
    assert transport.send(TOKEN, 101, 'neutral help') == ('accepted', 7, None)
    assert result.closed
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == ('https://api.telegram.org/bot' + TOKEN + '/sendMessage',)
    assert kwargs == {'json': {'chat_id': 101, 'text': 'neutral help', 'link_preview_options': {'is_disabled': True}},
                      'timeout': (3,7), 'verify': True, 'allow_redirects': False, 'stream': True}


@pytest.mark.parametrize('status,body,expected', [
    (429, {'ok': False, 'parameters': {'retry_after': 120}}, ('retry_wait', None, 120)),
    (429, {'ok': False, 'parameters': {'retry_after': 999999999999999999999}}, ('failed', None, None)),
    (429, {'ok': False, 'parameters': {'retry_after': True}}, ('retry_wait', None, 60)),
    (403, {'ok': False, 'description': 'private provider text'}, ('failed', None, None)),
    (400, {'ok': False}, ('failed', None, None)),
    (500, {'ok': False}, ('uncertain', None, None)),
    (302, {}, ('uncertain', None, None)),
    (200, b'not json', ('uncertain', None, None)),
    (200, {'ok': True, 'result': {'message_id': 7, 'chat': {'id': 102}}}, ('uncertain', None, None)),
    (200, {'ok': True, 'result': {'message_id': True, 'chat': {'id': 101}}}, ('uncertain', None, None)),
    (200, b'x'*65537, ('uncertain', None, None)),
])
def test_provider_failures_are_bounded_and_sanitized(monkeypatch, status, body, expected):
    value = response(monkeypatch, status, body)
    assert transport.send(TOKEN, 101, 'neutral help') == expected
    assert value.closed


def test_timeout_exception_and_debug_urls_do_not_expose_credentials(monkeypatch, caplog):
    class Session:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, *args, **kwargs):
            logging.getLogger('urllib3.connectionpool').debug('POST %s', args[0])
            raise requests.Timeout('secret=' + TOKEN)
    monkeypatch.setattr(requests, 'Session', Session)
    with caplog.at_level(logging.DEBUG):
        assert transport.send(TOKEN, 101, 'neutral help') == ('uncertain', None, None)
    assert TOKEN not in caplog.text and 'api.telegram.org' not in caplog.text


def test_configuration_rejects_invalid_or_oversized_identity(monkeypatch):
    for value in ('', '12345:bad', str(2**63)+':'+'A'*35):
        monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', value)
        assert transport.config() is None
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', TOKEN)
    identifier, _, fingerprint = transport.config()
    assert identifier == 123456 and len(fingerprint) == 64 and TOKEN not in fingerprint
