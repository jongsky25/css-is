"""Browser response policy; independent of account/password policy.

The script policy is deliberately report-only while legacy inline scripts are
migrated. Reports stay in the browser console; no report endpoint collects URLs.
"""
import os
import re
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders


ENFORCED_CSP = "base-uri 'self'; object-src 'none'; frame-ancestors 'self'"
REPORT_ONLY_CSP = (
    "default-src 'self'; script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
    "font-src 'self' data:; connect-src 'self'; "
    "frame-src 'self' https://drive.google.com; worker-src 'self' blob:; "
    "manifest-src 'self'; base-uri 'self'; object-src 'none'; form-action 'self'"
)
_SECURE_ATTRIBUTE = re.compile(rb'(?:^|;)\s*secure\s*(?:;|$)', re.I)


def https_deployment(environ=None):
    """Use server configuration, never client-supplied forwarding headers."""
    env = os.environ if environ is None else environ
    try:
        return bool(env.get('SPACE_HOST') or
                    urlsplit(env.get('CSS_BASE_URL', '')).scheme.lower() == 'https')
    except ValueError:
        return bool(env.get('SPACE_HOST'))


def secure_cookies_enabled(environ=None):
    env = os.environ if environ is None else environ
    # HTTPS production cannot accidentally opt out; local HTTP still works.
    return https_deployment(env) or env.get('CSS_SECURE_COOKIES', '').strip().lower() not in (
        '', '0', 'false', 'no', 'off', 'auto')


def protect_response(scope, raw_headers, status, *, secure_cookies=False):
    """Mutate response-start headers without buffering bodies or streams."""
    secure = secure_cookies or scope.get('scheme') == 'https'
    for i, (name, value) in enumerate(raw_headers):
        if name.lower() == b'set-cookie' and secure and not _SECURE_ATTRIBUTE.search(value):
            raw_headers[i] = (name, value + b'; Secure')
    headers = MutableHeaders(raw=raw_headers)
    headers.setdefault('X-Content-Type-Options', 'nosniff')
    headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    headers.setdefault('Referrer-Policy', 'no-referrer')
    headers.setdefault('Content-Security-Policy', ENFORCED_CSP)
    headers.setdefault('Content-Security-Policy-Report-Only', REPORT_ONLY_CSP)
    if scope.get('scheme') == 'https' or https_deployment():
        # Begin with one day, only this hostname. No preload/includeSubDomains.
        headers.setdefault('Strict-Transport-Security', 'max-age=86400')

    path = scope.get('path', '')
    public_asset = (path.startswith('/static/') and
                    scope.get('method') in ('GET', 'HEAD') and
                    status in (200, 206, 304) and 'set-cookie' not in headers)
    if not public_asset:
        if path == '/sw.js' and status == 200 and 'set-cookie' not in headers:
            headers['Cache-Control'] = 'no-cache'
        else:
            # Retain stricter route-specific policy, including private,no-store.
            if not any(v.strip().lower() == 'no-store' for v in
                       headers.get('Cache-Control', '').split(',')):
                private = any(v.strip().lower().split('=', 1)[0] == 'private' for v in
                              headers.get('Cache-Control', '').split(','))
                headers['Cache-Control'] = 'private, no-store' if private else 'no-store'
            headers['Pragma'] = 'no-cache'
            headers['Expires'] = '0'
            headers.add_vary_header('Cookie')
            headers.add_vary_header('Authorization')


class BrowserSecurityMiddleware:
    def __init__(self, app, secure_cookies):
        self.app = app
        self.secure_cookies = secure_cookies

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def protected_send(message):
            if message['type'] == 'http.response.start':
                protect_response(scope, message['headers'], message['status'],
                                 secure_cookies=self.secure_cookies())
            await send(message)

        await self.app(scope, receive, protected_send)
