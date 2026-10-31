"""Contingency service: only signed requests from one Office Connect deployment."""
import asyncio
import json
import os
import re
import time
from threading import Lock

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import telegram_outbound_protocol as protocol
from telegram_transport import connection_error

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_CLAIMS = {}
_CLAIM_LOCK = Lock()
_KEY_LOCK = Lock()
_KEY = None
_KEY_AT = None
_BUSY = asyncio.Semaphore(8)
_NETWORK_LOCK = Lock()
_NETWORK = None
_NETWORK_AT = None


def issuer_key():
    global _KEY, _KEY_AT
    with _KEY_LOCK:
        if _KEY is not None and time.monotonic() - _KEY_AT < 60:
            return _KEY
        with httpx.Client(verify=True, trust_env=True, follow_redirects=False,
                          timeout=httpx.Timeout(5, connect=3)) as client:
            with client.stream('GET', protocol.SOURCE + protocol.KEY_PATH) as response:
                if response.status_code != 200:
                    raise ValueError('Issuer unavailable')
                body = bytearray()
                for chunk in response.iter_bytes(1024):
                    body.extend(chunk)
                    if len(body) > 1024:
                        raise ValueError('Invalid issuer response')
        value = json.loads(body)
        key = value.get('key') if isinstance(value, dict) else None
        if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key):
            raise ValueError('Invalid issuer key')
        _KEY, _KEY_AT = key, time.monotonic()
        return key


def claim(value):
    with _CLAIM_LOCK:
        now = time.time()
        for nonce in [nonce for nonce, expires in _CLAIMS.items() if expires <= now]:
            del _CLAIMS[nonce]
        if value['expires_at'] <= now or value['nonce'] in _CLAIMS or len(_CLAIMS) >= 1024:
            return False
        _CLAIMS[value['nonce']] = value['expires_at']
        return True


def compact(method, params, body):
    """Return only fields the source needs to validate the provider result."""
    if not isinstance(body, dict):
        return {}
    if body.get('ok') is False:
        value = {'ok': False}
        retry = body.get('parameters', {})
        retry = retry.get('retry_after') if isinstance(retry, dict) else None
        if type(retry) is int and retry > 0:
            value['parameters'] = {'retry_after': min(retry, 86401)}
        return value
    result = body.get('result')
    if body.get('ok') is not True or not isinstance(result, dict):
        return {}
    if method == 'sendMessage':
        chat = result.get('chat')
        message = result.get('message_id')
        if (type(message) is int and 0 < message < 2**63 and isinstance(chat, dict)
                and type(chat.get('id')) is int and chat['id'] == params['chat_id']
                and ('message_thread_id' not in params or (type(result.get('message_thread_id')) is int
                     and result['message_thread_id'] == params['message_thread_id']))):
            safe = {'message_id': message, 'chat': {'id': chat['id']}}
            if 'message_thread_id' in params:
                safe['message_thread_id'] = params['message_thread_id']
            return {'ok': True, 'result': safe}
    elif method == 'getMe':
        if type(result.get('id')) is int and result.get('is_bot') is True:
            username = result.get('username')
            return {'ok': True, 'result': {'id': result['id'], 'is_bot': True,
                    'username_matches': isinstance(username, str) and username.casefold() == 'blhsd_bot'}}
    elif method == 'getChatMember':
        user = result.get('user')
        status = result.get('status')
        if (isinstance(user, dict) and type(user.get('id')) is int and user['id'] == params['user_id']
                and status in ('creator', 'administrator', 'member', 'restricted', 'left', 'kicked')):
            return {'ok': True, 'result': {'user': {'id': user['id']}, 'status': status}}
    return {}


def execute(value):
    if not claim(value):
        return {'nonce': value['nonce'], 'outcome': 'refused'}
    try:
        with httpx.Client(verify=True, trust_env=True, follow_redirects=False,
                          timeout=httpx.Timeout(7, connect=3)) as client:
            with client.stream('POST', 'https://api.telegram.org/bot'+value['token']+'/'+value['method'],
                               json=value['params']) as response:
                body = bytearray()
                started = time.monotonic()
                for chunk in response.iter_bytes(4096):
                    body.extend(chunk)
                    if len(body) > protocol.MAX_BODY or time.monotonic()-started > 10:
                        raise ValueError('Invalid provider response')
                return {'nonce': value['nonce'], 'outcome': 'response', 'provider_status': response.status_code,
                        'provider': compact(value['method'], value['params'], json.loads(body))}
    except Exception as error:
        return {'nonce': value['nonce'], 'outcome': 'uncertain', 'error': connection_error(error)}


def consume_permit(body, proof):
    with httpx.Client(verify=True, trust_env=True, follow_redirects=False,
                      timeout=httpx.Timeout(7, connect=3)) as client:
        with client.stream('POST', protocol.SOURCE + protocol.PERMIT_PATH, content=body,
                           headers={'Content-Type': 'application/json', 'X-Office-Proof': proof}) as response:
            if response.status_code != 200:
                return False
            raw = bytearray()
            for chunk in response.iter_bytes(1024):
                raw.extend(chunk)
                if len(raw) > 1024:
                    return False
            value = json.loads(raw)
            return isinstance(value, dict) and value == {'ok': True}


@app.get('/health')
def health():
    value = {'ok': True, 'protocol': 1, 'source': protocol.SOURCE}
    commit = os.environ.get('RENDER_GIT_COMMIT', '')
    if re.fullmatch('[a-f0-9]{40}', commit):
        value['commit'] = commit
    return value


@app.get('/connection')
def connection():
    """Cached public reachability check: no token, user data or message."""
    global _NETWORK, _NETWORK_AT
    with _NETWORK_LOCK:
        if _NETWORK is not None and time.monotonic()-_NETWORK_AT < 60:
            return dict(_NETWORK)
        try:
            with httpx.Client(verify=True, trust_env=True, follow_redirects=False,
                              timeout=httpx.Timeout(4, connect=3)) as client:
                with client.stream('GET', 'https://api.telegram.org') as response:
                    value = {'state': 'reached', 'http_status': response.status_code}
        except Exception as error:
            value = {'state': 'failed', 'error': connection_error(error)}
        _NETWORK, _NETWORK_AT = value, time.monotonic()
        return dict(value)


@app.post('/telegram')
async def telegram(request: Request):
    try:
        length = request.headers.get('content-length', '')
        proof = request.headers.get('x-office-proof', '')
        if not length.isdecimal() or int(length) > protocol.MAX_BODY or len(proof) != 86:
            return JSONResponse({'error': 'invalid_request'}, status_code=400)
        async with _BUSY:
            async def read_body():
                result = bytearray()
                async for chunk in request.stream():
                    result.extend(chunk)
                    if len(result) > protocol.MAX_BODY:
                        raise ValueError('Request too large')
                return bytes(result)
            body = await asyncio.wait_for(read_body(), timeout=5)
            key = await asyncio.to_thread(issuer_key)
            value = protocol.verify(body, proof, key)
            if value['method'] == 'sendMessage' and not await asyncio.to_thread(consume_permit, body, proof):
                return JSONResponse({'nonce': value['nonce'], 'outcome': 'refused'})
            return JSONResponse(await asyncio.to_thread(execute, value))
    except ValueError:
        return JSONResponse({'error': 'invalid_request'}, status_code=403)
    except Exception:
        return JSONResponse({'error': 'unavailable'}, status_code=503)
