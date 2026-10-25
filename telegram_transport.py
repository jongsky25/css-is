"""One bounded Bot API attempt. Never log provider exceptions or token URLs."""
import hashlib
import os
import time

import requests
# Installs the existing urllib3 token-URL logging filter; no digest configuration is read.
from apprise_transport import TOKEN


MAX_RESPONSE = 65536


def config():
    token = os.environ.get('CSS_TELEGRAM_BOT_TOKEN', '')
    if not TOKEN.fullmatch(token):
        return None
    identifier = int(token.split(':', 1)[0])
    if identifier > 2**63 - 1:
        return None
    return identifier, token, hashlib.sha256(token.encode()).hexdigest()


def send(token, chat_id, text):
    """Return (state, provider message ID, retry seconds); uncertainty never retries."""
    started = time.monotonic()
    try:
        with requests.Session() as session:
            response = session.post('https://api.telegram.org/bot' + token + '/sendMessage',
                json={'chat_id': chat_id, 'text': text, 'link_preview_options': {'is_disabled': True}},
                timeout=(3, 7), verify=True, allow_redirects=False, stream=True)
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
                    return 'failed', None, None
                result = value.get('result')
                if response.status_code == 200 and value.get('ok') is True and isinstance(result, dict):
                    message_id = result.get('message_id')
                    chat = result.get('chat')
                    if (type(message_id) is int and 0 < message_id < 2**63 and isinstance(chat, dict)
                            and type(chat.get('id')) is int and chat['id'] == chat_id):
                        return 'accepted', message_id, None
    except Exception:
        # Errors can contain the secret-bearing URL or provider body. Persist neither.
        pass
    return 'uncertain', None, None
