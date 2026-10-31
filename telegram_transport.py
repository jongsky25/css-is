"""One bounded Bot API attempt. Never log provider exceptions or token URLs."""
import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock

import requests
# Installs the existing urllib3 token-URL logging filter; no digest configuration is read.
from apprise_transport import TOKEN


MAX_RESPONSE = 65536
_SEND_LOCK = Lock()
_LAST_SEND = None


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


def send(token, chat_id, text, topic_id=None):
    """Keep one bounded attempt's safe status without retaining its content."""
    global _LAST_SEND
    http_status = None
    def observe(value):
        nonlocal http_status
        if type(value) is int and 100 <= value <= 599:
            http_status = value
    result = _send(token, chat_id, text, topic_id, observe)
    state = result[0]
    error = (None if state == 'accepted' else 'provider_rejected' if state == 'failed' else
             'rate_limited' if state == 'retry_wait' else
             'transport_failure' if http_status is None else 'response_unverified')
    with _SEND_LOCK:
        _LAST_SEND = {'state': state, 'http_status': http_status, 'error': error,
                      'observed_at': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    return result


def _send(token, chat_id, text, topic_id, observe):
    """Return (state, provider message ID, retry seconds); uncertainty never retries."""
    payload = {'chat_id': chat_id, 'text': text, 'link_preview_options': {'is_disabled': True}}
    if topic_id is not None:
        payload['message_thread_id'] = topic_id
    started = time.monotonic()
    try:
        with requests.Session() as session:
            response = session.post('https://api.telegram.org/bot' + token + '/sendMessage',
                json=payload,
                timeout=(3, 7), verify=True, allow_redirects=False, stream=True)
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
    except Exception:
        # Errors can contain the secret-bearing URL or provider body. Persist neither.
        logging.getLogger(__name__).warning('Telegram delivery uncertain: transport failure; automatic resend suppressed')
    return 'uncertain', None, None


def member_status(token, chat_id, user_id):
    """One bounded getChatMember call; return only a validated membership state."""
    started=time.monotonic()
    try:
        with requests.Session() as session:
            response=session.post('https://api.telegram.org/bot'+token+'/getChatMember',
                json={'chat_id':chat_id,'user_id':user_id},timeout=(3,7),verify=True,allow_redirects=False,stream=True)
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
