"""Bot identity reads isolate connection failures without replaying a send."""
import json
import logging
import socket
import ssl
from threading import Event, Thread

import httpx
import pytest
import requests

import deploy_hf
import telegram_transport as transport
from tests.test_telegram_bot import TOKEN
from tests.test_telegram_transport import Response


@pytest.fixture(autouse=True)
def isolated_probe(monkeypatch):
    monkeypatch.setenv('CSS_TELEGRAM_BOT_TOKEN', TOKEN)
    monkeypatch.setattr(transport, '_LAST_PROBE', None)
    monkeypatch.setattr(transport, '_PROBE_AT', None)


def clients(monkeypatch, first=None, second=None):
    calls = []
    body = {'ok': True, 'result': {'id': 123456, 'is_bot': True, 'username': 'private_bot'}}
    class Reply(Response):
        def iter_bytes(self, chunk_size):
            return self.iter_content(chunk_size)
    class Requests:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, url, **kwargs):
            calls.append(('requests', url, kwargs))
            if isinstance(first, Exception): raise first
            return first or Reply(200, body)
        def post(self, *args, **kwargs):
            pytest.fail('Read-only connection check attempted a message send')
    class Httpx:
        def __init__(self, **kwargs):
            assert kwargs == {'verify': True, 'trust_env': True, 'follow_redirects': False,
                              'timeout': httpx.Timeout(7, connect=3)}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, method, url):
            calls.append(('httpx', url, {'method': method}))
            if isinstance(second, Exception): raise second
            return second or Reply(200, body)
    monkeypatch.setattr(requests, 'Session', Requests)
    monkeypatch.setattr(httpx, 'Client', Httpx)
    return calls


def test_probe_uses_only_fixed_get_me_and_discards_bot_identity(monkeypatch):
    calls = clients(monkeypatch)
    transport.probe_connection()
    assert transport.last_connection_probe() == {
        'requests': {'state': 'ok', 'http_status': 200},
        'httpx': {'state': 'ok', 'http_status': 200}}
    assert calls == [('requests', 'https://api.telegram.org/bot'+TOKEN+'/getMe',
                      {'timeout': (3, 7), 'verify': True, 'allow_redirects': False, 'stream': True}),
                     ('httpx', 'https://api.telegram.org/bot'+TOKEN+'/getMe', {'method': 'GET'})]
    result = transport.last_connection_probe()
    result['requests']['state'] = 'tampered'
    assert transport.last_connection_probe()['requests']['state'] == 'ok'
    output = json.dumps(transport.last_connection_probe())
    assert not any(value in output for value in (TOKEN, '123456', 'private_bot'))
    transport.probe_connection()
    assert len(calls) == 2  # One process-level check per minute, never a send retry.


@pytest.mark.parametrize('error,category', [
    (requests.exceptions.ConnectTimeout(TOKEN), 'connect_timeout'),
    (requests.exceptions.ReadTimeout(TOKEN), 'read_timeout'),
    (requests.exceptions.ProxyError(TOKEN), 'proxy'),
    (requests.exceptions.SSLError(TOKEN), 'tls'),
    (httpx.ConnectTimeout(TOKEN), 'connect_timeout'),
    (httpx.ReadTimeout(TOKEN), 'read_timeout'),
    (httpx.ProxyError(TOKEN), 'proxy'),
    (httpx.RemoteProtocolError(TOKEN), 'protocol'),
    (socket.gaierror(TOKEN), 'dns'),
    (ssl.SSLCertVerificationError(TOKEN), 'tls_certificate'),
    (TypeError(TOKEN), 'client_error'),
    (RuntimeError(TOKEN), 'transport_failure'),
])
def test_fixed_error_categories_never_include_exception_text(monkeypatch, caplog, error, category):
    clients(monkeypatch, error, error)
    transport.probe_connection()
    assert transport.last_connection_probe() == {
        'requests': {'state': 'failed', 'error': category},
        'httpx': {'state': 'failed', 'error': category}}
    assert TOKEN not in caplog.text + json.dumps(transport.last_connection_probe())


def test_tls_certificate_failure_survives_client_wrappers():
    certificate = ssl.SSLCertVerificationError(TOKEN)
    wrapper = requests.exceptions.SSLError(certificate)
    outer = requests.exceptions.ConnectionError(wrapper)
    outer.__context__ = outer  # A malformed exception chain cannot loop forever.
    assert transport.connection_error(outer) == 'tls_certificate'


def test_send_reports_connection_category_without_changing_uncertain_outcome(monkeypatch, caplog):
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            raise requests.exceptions.SSLError(ssl.SSLCertVerificationError(TOKEN))
    monkeypatch.setattr(requests, 'Session', Session)
    assert transport.send(TOKEN, 101, 'private message') == ('uncertain', None, None)
    assert transport.last_send_status()['transport_error'] == 'tls_certificate'
    assert 'tls_certificate' in caplog.text
    assert TOKEN not in caplog.text + json.dumps(transport.last_send_status())


def test_deployment_parser_discards_arbitrary_network_details():
    from tests.test_telegram_deploy_diagnostics import page
    value = page(network={'requests': {'state': 'failed', 'error': 'dns', 'http_status': True,
                                      'token': TOKEN, 'detail': 'private body'},
                          'httpx': {'state': TOKEN, 'error': TOKEN, 'http_status': 200},
                          'private-client': {'state': TOKEN}},
                 provider={'state': 'uncertain', 'transport_error': 'dns', 'raw_exception': TOKEN})
    summary = deploy_hf.telegram_ops_summary(value)
    assert summary['network'] == {'requests': {'state': 'failed', 'error': 'dns'}, 'httpx': {'http_status': 200}}
    assert summary['provider'] == {'state': 'uncertain', 'transport_error': 'dns'}
    assert TOKEN not in json.dumps(summary) and 'private' not in json.dumps(summary)


@pytest.mark.parametrize('status,body,state', [
    (401, b'private-provider-error', 'http_error'),
    (302, {}, 'http_error'),
    (200, b'not-json', 'invalid_response'),
    (200, b'x'*65537, 'invalid_response'),
    (200, {'ok': True, 'result': {'id': 123457, 'is_bot': True}}, 'invalid_response'),
    (200, {'ok': True, 'result': {'id': 123456, 'is_bot': False}}, 'invalid_response'),
])
def test_probe_validates_bounded_response_and_never_exposes_it(monkeypatch, status, body, state):
    value = Response(status, body)
    value.iter_bytes = value.iter_content
    clients(monkeypatch, value, value)
    transport.probe_connection()
    assert value.closed
    assert transport.last_connection_probe() == {name: {'state': state, 'http_status': status}
                                                  for name in ('requests', 'httpx')}


def test_unconfigured_probe_does_not_call_provider(monkeypatch):
    calls = clients(monkeypatch)
    monkeypatch.delenv('CSS_TELEGRAM_BOT_TOKEN')
    transport.probe_connection()
    assert not calls
    assert transport.last_connection_probe() == {name: {'state': 'not_configured'}
                                                  for name in ('requests', 'httpx')}


def test_concurrent_checks_share_one_probe(monkeypatch):
    calls = clients(monkeypatch)
    entered, release = Event(), Event()
    original = transport._probe_response
    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(transport, '_probe_response', blocked)
    thread = Thread(target=transport.probe_connection)
    thread.start()
    try:
        assert entered.wait(2)
        transport.probe_connection()
        assert len(calls) == 1
        assert transport.last_connection_probe() is None
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and len(calls) == 2


def test_http_client_logs_cannot_expose_token_url(caplog):
    with caplog.at_level(logging.DEBUG):
        for name in ('httpx', 'urllib3.connectionpool', 'httpcore.connection', 'httpcore.http11',
                     'httpcore.http2', 'httpcore.proxy', 'httpcore.socks'):
            logging.getLogger(name).info('GET https://api.telegram.org/bot%s/getMe', TOKEN)
    assert TOKEN not in caplog.text and 'api.telegram.org' not in caplog.text


def test_ops_probe_requires_admin_and_explicit_query(admin, viewer, client, app_mod, monkeypatch):
    calls = clients(monkeypatch)
    conn = app_mod.get_conn()
    try:
        before = {name: conn.execute('SELECT count(*) FROM '+name).fetchone()[0]
                  for name in ('telegram_update', 'telegram_delivery', 'telegram_operation', 'calendar_entry')}
        assert viewer.get('/ops?telegram_probe=1').status_code == 403
        assert client.get('/ops?telegram_probe=1', follow_redirects=False).status_code in (302, 303)
        assert not calls
        assert admin.get('/ops').status_code == 200
        assert not calls
        page = admin.get('/ops?telegram_probe=1')
        assert page.status_code == 200 and len(calls) == 2
        safe = deploy_hf.telegram_ops_summary(page.text)
        assert safe['network']['requests'] == {'state': 'ok', 'http_status': 200}
        assert before == {name: conn.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in before}
        assert not any(value in page.text for value in (TOKEN, '123456', 'private_bot'))
    finally:
        conn.close()
