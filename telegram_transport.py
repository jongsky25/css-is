"""One bounded Bot API attempt. Never log provider exceptions or token URLs."""
import hashlib
import logging
import os
import socket
import ssl
import time
from datetime import datetime, timezone
from threading import Lock

import requests
import httpx
import telegram_outbound_client as outbound
# Installs the existing urllib3 token-URL logging filter; no digest configuration is read.
from apprise_transport import TOKEN


MAX_RESPONSE = 65536
_SEND_LOCK = Lock()
_LAST_SEND = None
_PROBE_LOCK = Lock()
_LAST_PROBE = None
_PROBE_AT = None
NETWORK_ERRORS = frozenset({'tls_certificate', 'tls', 'dns', 'proxy', 'connect_timeout',
                           'read_timeout', 'timeout', 'connection', 'protocol', 'client_error',
                           'transport_failure'})


def connection_error(error):
    """Classify wrapped client exceptions without reading their sensitive text."""
    if isinstance(error, outbound.OutboundError):
        return error.category if error.category in NETWORK_ERRORS else 'transport_failure'
    chain, pending, seen = [], [error], set()
    while pending and len(chain) < 16:
        item = pending.pop()
        if not isinstance(item, BaseException) or id(item) in seen:
            continue
        seen.add(id(item))
        chain.append(item)
        pending.extend((item.__cause__, item.__context__, getattr(item, 'reason', None)))
        pending.extend(arg for arg in item.args if isinstance(arg, BaseException))
    for category, classes in (
        ('tls_certificate', (ssl.SSLCertVerificationError,)),
        ('tls', (ssl.SSLError, requests.exceptions.SSLError)),
        ('dns', (socket.gaierror,)),
        ('proxy', (requests.exceptions.ProxyError, httpx.ProxyError)),
        ('connect_timeout', (requests.exceptions.ConnectTimeout, httpx.ConnectTimeout)),
        ('read_timeout', (requests.exceptions.ReadTimeout, httpx.ReadTimeout)),
        ('timeout', (requests.exceptions.Timeout, httpx.TimeoutException)),
        ('connection', (requests.exceptions.ConnectionError, httpx.ConnectError)),
        ('protocol', (httpx.ProtocolError,)),
        ('client_error', (TypeError, ValueError)),
    ):
        if any(isinstance(item, classes) for item in chain):
            return category
    return 'transport_failure'


def last_connection_probe():
    with _SEND_LOCK:
        return {name: dict(value) for name, value in _LAST_PROBE.items()} if _LAST_PROBE else None


def _probe_response(status, chunks, identifier, started):
    result = {'http_status': status}
    if status != 200:
        return dict(result, state='http_error')
    body = bytearray()
    for chunk in chunks:
        body.extend(chunk)
        if len(body) > MAX_RESPONSE or time.monotonic() - started > 10:
            return dict(result, state='invalid_response')
    import json
    try:
        value = json.loads(body)
    except (ValueError, RecursionError):
        return dict(result, state='invalid_response')
    bot = value.get('result') if isinstance(value, dict) else None
    valid = (isinstance(value, dict) and value.get('ok') is True and isinstance(bot, dict)
             and bot.get('is_bot') is True and type(bot.get('id')) is int and bot['id'] == identifier)
    if valid and type(bot.get('username_matches')) is bool:
        result['bot_username_matches'] = bot['username_matches']
    return dict(result, state='ok' if valid else 'invalid_response')


def probe_connection():
    """Admin-requested getMe reads only; no sends, retries, proxy bypass or DB writes."""
    global _LAST_PROBE, _PROBE_AT
    if not _PROBE_LOCK.acquire(blocking=False):
        return
    try:
        if _PROBE_AT is not None and time.monotonic() - _PROBE_AT < 60:
            return
        bot = config()
        results = {}
        for name in ('requests', 'httpx') + (('outbound',) if outbound.configured() else ()):
            if bot is None:
                results[name] = {'state': 'not_configured'}
                continue
            status = None
            started = time.monotonic()
            try:
                url = 'https://api.telegram.org/bot' + bot[1] + '/getMe'
                if name == 'outbound':
                    if not outbound.ready():
                        results[name] = {'state': 'not_ready'}
                        continue
                    with outbound.request(bot[1], 'getMe', {}) as response:
                        status = response.status_code
                        results[name] = _probe_response(status, response.iter_content(4096), bot[0], started)
                elif name == 'requests':
                    with requests.Session() as session:
                        with session.get(url, timeout=(3, 7), verify=True,
                                         allow_redirects=False, stream=True) as response:
                            status = response.status_code
                            results[name] = _probe_response(status, response.iter_content(4096), bot[0], started)
                else:
                    with httpx.Client(verify=True, trust_env=True, follow_redirects=False,
                                      timeout=httpx.Timeout(7, connect=3)) as client:
                        with client.stream('GET', url) as response:
                            status = response.status_code
                            results[name] = _probe_response(status, response.iter_bytes(4096), bot[0], started)
            except Exception as error:
                results[name] = {'state': 'failed', 'error': connection_error(error)}
                if status is not None:
                    results[name]['http_status'] = status
        with _SEND_LOCK:
            _LAST_PROBE = results
            _PROBE_AT = time.monotonic()
    finally:
        _PROBE_LOCK.release()


def last_send_status():
    """Per-process operational metadata only; no destination, ID or content."""
    with _SEND_LOCK:
        return dict(_LAST_SEND) if _LAST_SEND is not None else None


def config():
    token = os.environ.get('CSS_TELEGRAM_BOT_TOKEN', '')
    if not TOKEN.fullmatch(token):
        return None
    identifier = int(token.split(':', 1)[0])
    if identifier > 2**63 - 1:
        return None
    return identifier, token, hashlib.sha256(token.encode()).hexdigest()


def send(token, chat_id, text, topic_id=None, *, dispatch_nonce=None):
    """Keep one bounded attempt's safe status without retaining its content."""
    global _LAST_SEND
    http_status = None
    transport_error = None
    def observe(value):
        nonlocal http_status, transport_error
        if type(value) is int and 100 <= value <= 599:
            http_status = value
        elif isinstance(value, str) and value in NETWORK_ERRORS:
            transport_error = value
    result = _send(token, chat_id, text, topic_id, observe, dispatch_nonce=dispatch_nonce)
    state = result[0]
    error = (None if state == 'accepted' else 'provider_rejected' if state == 'failed' else
             'rate_limited' if state == 'retry_wait' else
             'transport_failure' if http_status is None else 'response_unverified')
    with _SEND_LOCK:
        _LAST_SEND = {'state': state, 'http_status': http_status, 'error': error,
                      'transport_error': transport_error,
                      'observed_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return result


def _send(token, chat_id, text, topic_id, observe, *, dispatch_nonce=None):
    """Return (state, provider message ID, retry seconds); uncertainty never retries."""
    payload = {'chat_id': chat_id, 'text': text, 'link_preview_options': {'is_disabled': True}}
    if topic_id is not None:
        payload['message_thread_id'] = topic_id
    started = time.monotonic()
    try:
        with requests.Session() as session:
            response = (outbound.request(token, 'sendMessage', payload, nonce=dispatch_nonce) if outbound.configured() else
                session.post('https://api.telegram.org/bot' + token + '/sendMessage',
                json=payload,
                timeout=(3, 7), verify=True, allow_redirects=False, stream=True))
            observe(response.status_code)
            with response:
                body = bytearray()
                for chunk in response.iter_content(4096):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE or time.monotonic() - started > 10:
                        return 'uncertain', None, None
                import json
                try:
                    value = json.loads(body)
                except (ValueError, RecursionError):
                    return 'uncertain', None, None
                if not isinstance(value, dict):
                    return 'uncertain', None, None
                if response.status_code == 429 and value.get('ok') is False:
                    seconds = value.get('parameters', {})
                    seconds = seconds.get('retry_after') if isinstance(seconds, dict) else None
                    if type(seconds) is int and seconds > 86400:
                        return 'failed', None, None  # Retry would outlive the help receipt.
                    seconds = seconds if type(seconds) is int and 1 <= seconds <= 86400 else 60
                    return 'retry_wait', None, seconds
                if 400 <= response.status_code < 500 and value.get('ok') is False:
                    logging.getLogger(__name__).warning('Telegram delivery rejected: HTTP %s', response.status_code)
                    return 'failed', None, None
                result = value.get('result')
                if response.status_code == 200 and value.get('ok') is True and isinstance(result, dict):
                    message_id = result.get('message_id')
                    chat = result.get('chat')
                    if (type(message_id) is int and 0 < message_id < 2**63 and isinstance(chat, dict)
                            and type(chat.get('id')) is int and chat['id'] == chat_id
                            and (topic_id is None or (type(result.get('message_thread_id')) is int and result['message_thread_id']==topic_id))):
                        return 'accepted', message_id, None
    except Exception as error:
        # Errors can contain the secret-bearing URL or provider body. Persist neither.
        category = connection_error(error)
        observe(category)
        logging.getLogger(__name__).warning('Telegram delivery uncertain: %s; automatic resend suppressed', category)
    return 'uncertain', None, None


def member_status(token, chat_id, user_id):
    """One bounded getChatMember call; return only a validated membership state."""
    started=time.monotonic()
    try:
        with requests.Session() as session:
            payload = {'chat_id':chat_id,'user_id':user_id}
            response=(outbound.request(token, 'getChatMember', payload) if outbound.configured() else
                session.post('https://api.telegram.org/bot'+token+'/getChatMember',
                json=payload,timeout=(3,7),verify=True,allow_redirects=False,stream=True))
            with response:
                body=bytearray()
                for chunk in response.iter_content(4096):
                    body.extend(chunk)
                    if len(body)>MAX_RESPONSE or time.monotonic()-started>10:
                        return None
                import json
                value=json.loads(body)
                if response.status_code!=200 or not isinstance(value,dict) or value.get('ok') is not True:
                    return None
                result=value.get('result')
                if not isinstance(result,dict) or not isinstance(result.get('user'),dict):
                    return None
                user=result['user']
                if type(user.get('id')) is not int or user['id']!=user_id:
                    return None
                status=result.get('status')
                return status if status in ('creator','administrator','member','restricted','left','kicked') else None
    except Exception:
        return None  # Never log token URLs or provider bodies.
