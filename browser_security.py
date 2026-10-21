"""Browser response policy; independent of account/password policy.

The script policy is deliberately report-only while legacy inline scripts are
migrated. Reports stay in the browser console; no report endpoint collects URLs.
"""
import os
import re
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette._utils import get_route_path


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
    # 'same-origin', not 'no-referrer': under no-referrer Chromium sends a form POST with "Origin: null" and no Referer,
    # so the application's origin check rejects every login and save ("This request could not be verified"). With
    # same-origin the site's own requests carry their real Origin, and nothing is ever sent to another site.
    headers.setdefault('Referrer-Policy', 'same-origin')
    headers.setdefault('Content-Security-Policy', ENFORCED_CSP)
    headers.setdefault('Content-Security-Policy-Report-Only', REPORT_ONLY_CSP)
    if scope.get('scheme') == 'https' or https_deployment():
        # Begin with one day, only this hostname. No preload/includeSubDomains.
        headers.setdefault('Strict-Transport-Security', 'max-age=86400')

    path = get_route_path(scope)
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

        # Mount dispatch mutates root_path before sending the response. Capture
        # the application-relative path now so packaged assets and private files
        # keep the same policy classification before and after dispatch.
        policy_scope = dict(scope, path=get_route_path(scope), root_path='')

        async def protected_send(message):
            if message['type'] == 'http.response.start':
                protect_response(policy_scope, message['headers'], message['status'],
                                 secure_cookies=self.secure_cookies())
            await send(message)

        await self.app(scope, receive, protected_send)
