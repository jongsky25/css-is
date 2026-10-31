"""Proof for one fixed-provider request, derived from the bot's existing secret."""
import base64
import hashlib
import json
import re
import time
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from apprise_transport import TOKEN

SOURCE = 'https://equityinhealth-office-connect.hf.space'
KEY_PATH = '/integrations/telegram/outbound-key'
PERMIT_PATH = '/integrations/telegram/outbound-permit'
MAX_BODY = 65536


def signing_key(token):
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(
        b'Office Connect Telegram outbound v1\0' + SOURCE.encode() + b'\0' + token.encode()).digest())


def public_key(token):
    return signing_key(token).public_key().public_bytes_raw().hex()


def packet(token, method, params, *, now=None, nonce=None):
    issued = int(time.time() if now is None else now)
    value = {'version': 1, 'source': SOURCE, 'token': token, 'method': method, 'params': params,
             'issued_at': issued, 'expires_at': issued + 20, 'nonce': nonce or uuid4().hex}
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    proof = base64.urlsafe_b64encode(signing_key(token).sign(body)).decode().rstrip('=')
    return body, proof


def _integer(value, *, positive=False):
    return type(value) is int and -(2**63) < value < 2**63 and value != 0 and (not positive or value > 0)


def verify(body, proof, expected_key, *, now=None):
    """Reject before I/O; all errors are fixed text, never untrusted values."""
    try:
        if len(body) > MAX_BODY or not re.fullmatch(r'[A-Za-z0-9_-]{86}', proof):
            raise ValueError
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(expected_key))
        key.verify(base64.urlsafe_b64decode(proof + '=='), body)
        value = json.loads(body)
        if (not isinstance(value, dict) or set(value) != {'version', 'source', 'token', 'method', 'params',
                                                         'issued_at', 'expires_at', 'nonce'}
                or type(value['version']) is not int or value['version'] != 1 or value['source'] != SOURCE
                or not isinstance(value['token'], str) or not TOKEN.fullmatch(value['token'])
                or public_key(value['token']) != expected_key
                or not isinstance(value['nonce'], str) or not re.fullmatch('[a-f0-9]{32}', value['nonce'])):
            raise ValueError
        issued, expires = value['issued_at'], value['expires_at']
        clock = time.time() if now is None else now
        if (type(issued) is not int or type(expires) is not int or not 0 < expires-issued <= 30
                or issued > clock + 5 or expires <= clock):
            raise ValueError
        method, params = value['method'], value['params']
        if not isinstance(params, dict):
            raise ValueError
        if method == 'getMe':
            valid = params == {}
        elif method == 'getChatMember':
            valid = (set(params) == {'chat_id', 'user_id'} and _integer(params['chat_id'])
                     and _integer(params['user_id'], positive=True))
        elif method == 'sendMessage':
            valid = (set(params) in ({'chat_id', 'text', 'link_preview_options'},
                                     {'chat_id', 'text', 'link_preview_options', 'message_thread_id'})
                     and _integer(params['chat_id']) and isinstance(params['text'], str)
                     and 0 < len(params['text'].encode('utf-16-le')) // 2 <= 4096
                     and params['link_preview_options'] == {'is_disabled': True}
                     and ('message_thread_id' not in params or _integer(params['message_thread_id'], positive=True)))
        else:
            valid = False
        if not valid:
            raise ValueError
        return value
    except Exception:
        raise ValueError('Invalid outbound proof or request') from None
