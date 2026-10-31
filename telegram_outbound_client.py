"""Optional, deployment-configured outbound service. No direct-send fallback."""
import json
import os
import re

import requests

import telegram_outbound_protocol as protocol


class OutboundError(Exception):
    def __init__(self, category='transport_failure'):
        super().__init__('Outbound service did not confirm a provider response')
        self.category = category


def configured():
    return bool(os.environ.get('CSS_TELEGRAM_OUTBOUND_URL', ''))


def base_url():
    value = os.environ.get('CSS_TELEGRAM_OUTBOUND_URL', '').rstrip('/')
    if not re.fullmatch(r'https://[a-z0-9][a-z0-9-]{0,61}[a-z0-9]\.onrender\.com', value):
        raise OutboundError('client_error')
    return value


def ready():
    try:
        with requests.Session() as session:
            with session.get(base_url()+'/health', timeout=(2, 2), verify=True,
                             allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    return False
                body = bytearray()
                for chunk in response.iter_content(1024):
                    body.extend(chunk)
                    if len(body) > 1024:
                        return False
                value = json.loads(body)
                return (isinstance(value, dict) and value.get('ok') is True
                        and type(value.get('protocol')) is int and value['protocol'] == 1
                        and value.get('source') == protocol.SOURCE)
    except Exception:
        return False


class ProviderResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.body = json.dumps(body, separators=(',', ':')).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, chunk_size): yield self.body
    def iter_bytes(self, chunk_size): yield self.body


def request(token, method, params, *, nonce=None):
    body, signature = protocol.packet(token, method, params, nonce=nonce)
    nonce = json.loads(body)['nonce']
    with requests.Session() as session:
        with session.post(base_url()+'/telegram', data=body,
                          headers={'Content-Type': 'application/json', 'X-Office-Proof': signature},
                          timeout=(3, 15), verify=True, allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                raise OutboundError()
            raw = bytearray()
            for chunk in response.iter_content(4096):
                raw.extend(chunk)
                if len(raw) > protocol.MAX_BODY:
                    raise OutboundError()
    try:
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get('nonce') != nonce:
            raise ValueError
        if value.get('outcome') != 'response':
            category = value.get('error')
            raise OutboundError(category if isinstance(category, str) else 'transport_failure')
        status, provider = value.get('provider_status'), value.get('provider')
        if type(status) is not int or not 100 <= status <= 599 or not isinstance(provider, dict):
            raise ValueError
        return ProviderResponse(status, provider)
    except OutboundError:
        raise
    except Exception:
        raise OutboundError() from None
